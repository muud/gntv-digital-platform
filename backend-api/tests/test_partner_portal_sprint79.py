from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import importlib.util
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.partners.models import (
    Partner,
    PartnerApiCredential,
    PartnerCredentialStatus,
    PartnerPortalUser,
    PartnerPortalUserRole,
    PartnerStatus,
)
from app.modules.partners.providers import ProviderPayoutRequest, get_payment_provider
from app.modules.partners.providers.mock_provider import MockPaymentProvider
from app.modules.partners.repository import PartnerRepository
from app.modules.partners.service import PartnerSyndicationService
from app.utils.jwt import create_access_token


PERIOD_START = datetime(2026, 8, 1, tzinfo=UTC)
PERIOD_END = datetime(2026, 9, 1, tzinfo=UTC)


def make_db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    return testing_session()


def make_client(db: Session) -> TestClient:
    def override_get_db() -> Iterator[Session]:
        try:
            yield db
        finally:
            db.rollback()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def create_user(db: Session, role_name: str) -> User:
    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        db.flush()
    user = User(
        email=f"{role_name}-{uuid4()}@gntv.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    user.name = role_name
    user.roles.append(role)
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def money(value: object) -> Decimal:
    return Decimal(str(value))


def create_partner(client: TestClient, headers: dict[str, str], name: str = "Portal Partner") -> str:
    response = client.post(
        "/api/v1/partners",
        headers=headers,
        json={
            "name": name,
            "slug": f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}",
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["partner"]["id"])


def create_partner_portal_key(db: Session, partner_id: str) -> str:
    raw_key = f"gntv_pk_{uuid4().hex}{uuid4().hex}"
    service = PartnerSyndicationService(PartnerRepository(db))
    credential = PartnerApiCredential(
        partner_id=UUID(partner_id),
        key_prefix=raw_key[:14],
        secret_hash=service.hash_api_secret(raw_key),
        status=PartnerCredentialStatus.ACTIVE,
    )
    db.add(credential)
    db.commit()
    return raw_key


def portal_headers(key: str) -> dict[str, str]:
    return {"X-Partner-Key": key}


def seed_financial_flow(client: TestClient, partner_id: str, headers: dict[str, str]) -> dict[str, Any]:
    domain = client.post(
        f"/api/v1/partners/{partner_id}/domains",
        headers=headers,
        json={"domain_pattern": "*.portal.test"},
    )
    assert domain.status_code == 201, domain.text
    entitlement = client.post(
        f"/api/v1/partners/{partner_id}/entitlements",
        headers=headers,
        json={"content_type": "live_channel", "content_id": "gntv-live", "scopes": ["embed:play"]},
    )
    assert entitlement.status_code == 201, entitlement.text
    agreement = client.post(
        f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
        headers=headers,
        json={
            "name": "Portal revenue share",
            "rule_type": "fixed_percentage",
            "fixed_partner_percentage": "0.4000",
            "currency": "USD",
            "starts_at": PERIOD_START.isoformat(),
        },
    )
    assert agreement.status_code == 201, agreement.text
    for idx, content_id in enumerate(["=FORMULA()", "gntv-live"]):
        usage = client.post(
            f"/api/v1/partners/{partner_id}/billing/usage",
            headers=headers,
            json={
                "content_type": "live_channel",
                "content_id": content_id,
                "usage_event_type": "ad_revenue",
                "quantity": idx + 1,
                "gross_revenue_amount": "100.123456",
                "currency": "USD",
                "idempotency_key": f"portal-usage-{uuid4().hex}",
                "occurred_at": datetime(2026, 8, 12 + idx, tzinfo=UTC).isoformat(),
            },
        )
        assert usage.status_code == 201, usage.text
    settlement = client.post(
        f"/api/v1/partners/{partner_id}/billing/settlements",
        headers=headers,
        json={
            "period_start": PERIOD_START.isoformat(),
            "period_end": PERIOD_END.isoformat(),
            "currency": "USD",
            "adjustment_amount": "1.111111",
            "idempotency_key": f"portal-settlement-{uuid4().hex}",
        },
    )
    assert settlement.status_code == 201, settlement.text
    finalized = client.post(
        f"/api/v1/partners/{partner_id}/billing/settlements/{settlement.json()['id']}/status",
        headers=headers,
        json={"status": "finalized", "reason": "Ready for partner review"},
    )
    assert finalized.status_code == 200, finalized.text
    account = client.post(
        f"/api/v1/partners/{partner_id}/payout-accounts",
        headers=headers,
        json={
            "provider_type": "mock",
            "destination_label": "Portal Sandbox",
            "destination_reference": "portal-destination-1234",
            "provider_metadata": {"rail": "sandbox"},
            "currency": "USD",
            "verification_status": "verified",
            "idempotency_key": f"portal-account-{uuid4().hex}",
        },
    )
    assert account.status_code == 201, account.text
    payout = client.post(
        f"/api/v1/partners/{partner_id}/payouts",
        headers=headers,
        json={
            "settlement_id": finalized.json()["id"],
            "payout_account_id": account.json()["id"],
            "idempotency_key": f"portal-payout-{uuid4().hex}",
        },
    )
    assert payout.status_code == 201, payout.text
    approved = client.post(
        f"/api/v1/partners/{partner_id}/payouts/{payout.json()['id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    paid = client.post(
        f"/api/v1/partners/{partner_id}/payouts/{payout.json()['id']}/execute",
        headers=headers,
        json={"idempotency_key": f"portal-execute-{uuid4().hex}"},
    )
    assert paid.status_code == 200, paid.text
    reconciliation = client.post(
        f"/api/v1/partners/{partner_id}/reconciliation",
        headers=headers,
        json={
            "provider_type": "mock",
            "provider_transaction_id": paid.json()["provider_transaction_id"],
            "reported_amount": "0.01",
            "reported_currency": "USD",
            "provider_status": "paid",
            "idempotency_key": f"portal-recon-{uuid4().hex}",
        },
    )
    assert reconciliation.status_code == 201, reconciliation.text
    return {
        "settlement": finalized.json(),
        "payout": paid.json(),
        "reconciliation": reconciliation.json(),
    }


def test_sprint79_partner_portal_requires_partner_scoped_auth_and_blocks_operator_tokens() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        no_key = client.get("/api/v1/partner-portal/me")
        admin_token = client.get("/api/v1/partner-portal/me", headers=auth_headers(admin))
        assert no_key.status_code == 401
        assert admin_token.status_code in {400, 401, 403}
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_partner_portal_rejects_inactive_partner_key_and_invalid_admin_target() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)
        partner_id = create_partner(client, headers)
        key = create_partner_portal_key(db, partner_id)
        partner = db.query(Partner).filter_by(id=UUID(partner_id)).one()
        partner.status = PartnerStatus.SUSPENDED
        db.commit()
        suspended = client.get("/api/v1/partner-portal/me", headers=portal_headers(key))
        invalid_admin_target = client.get(
            "/api/v1/partner-portal/me",
            headers={**headers, "X-Partner-Id": "not-a-uuid"},
        )
        assert suspended.status_code == 401
        assert invalid_admin_target.status_code == 400
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_partner_portal_supports_jwt_membership_and_admin_readonly_inspection() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        viewer = create_user(db, "viewer")
        headers = auth_headers(admin)
        partner_id = create_partner(client, headers)
        portal_user = PartnerPortalUser(
            partner_id=UUID(partner_id),
            user_id=viewer.id,
            role=PartnerPortalUserRole.FINANCE.value,
        )
        db.add(portal_user)
        db.commit()
        member_response = client.get("/api/v1/partner-portal/me", headers=auth_headers(viewer))
        admin_response = client.get(
            "/api/v1/partner-portal/me",
            headers={**headers, "X-Partner-Id": partner_id},
        )
        assert member_response.status_code == 200, member_response.text
        assert member_response.json()["partner"]["id"] == partner_id
        assert admin_response.status_code == 200, admin_response.text
        assert admin_response.json()["partner"]["id"] == partner_id
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_mock_provider_supports_deterministic_retrieval_cancellation_and_reconciliation() -> None:
    provider = MockPaymentProvider()
    payout_id = uuid4()
    partner_id = uuid4()
    request = ProviderPayoutRequest(
        payout_id=payout_id,
        partner_id=partner_id,
        amount=Decimal("12.340000"),
        currency="USD",
        destination_reference="portal-destination",
        destination_routing=None,
        idempotency_key="provider-idempotent-key",
    )
    result = provider.create_payout(request)
    same_result = provider.create_payout(request)
    status_result = provider.get_payout_status(result.provider_transaction_id)
    mismatch = provider.reconcile_transaction(result.provider_transaction_id, Decimal("12.340000"), "EUR")
    cancelled = provider.cancel_payout(result.provider_transaction_id, "duplicate instruction")
    returned = provider.reconcile_transaction(result.provider_transaction_id, Decimal("12.340000"), "USD")
    missing_status = provider.get_payout_status("missing-tx")
    missing_reconciliation = provider.reconcile_transaction("missing-tx", Decimal("1"), "USD")
    provider.set_simulate_failure(True)
    failed = provider.create_payout(request)
    registry_provider = get_payment_provider("sandbox")
    assert provider.provider_name == "mock_sandbox_provider"
    assert result.success is True
    assert same_result.provider_transaction_id == result.provider_transaction_id
    assert status_result.status == "paid"
    assert mismatch.status == "currency_mismatch"
    assert cancelled.status == "cancelled"
    assert returned.status == "matched"
    assert missing_status.success is False
    assert missing_reconciliation.status == "unknown_transaction"
    assert failed.success is False
    assert registry_provider.provider_name == "mock_sandbox_provider"


def test_sprint79_partner_profile_masks_payout_destinations_and_hides_secrets() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        seed_financial_flow(client, partner_id, headers)
        key = create_partner_portal_key(db, partner_id)
        response = client.get("/api/v1/partner-portal/me", headers=portal_headers(key))
        body = response.json()
        assert response.status_code == 200, response.text
        assert body["partner"]["id"] == partner_id
        assert body["payout_accounts"][0]["masked_destination_reference"] == "****1234"
        assert "encrypted_provider_metadata" not in str(body)
        assert "secret_hash" not in str(body)
        assert "portal-destination-1234" not in str(body)
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_overview_statements_and_revenue_use_persisted_decimal_values() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        seeded = seed_financial_flow(client, partner_id, headers)
        key = create_partner_portal_key(db, partner_id)
        overview = client.get("/api/v1/partner-portal/overview?currency=USD", headers=portal_headers(key))
        revenue = client.get("/api/v1/partner-portal/revenue?currency=USD", headers=portal_headers(key))
        statements = client.get("/api/v1/partner-portal/statements?currency=USD", headers=portal_headers(key))
        assert overview.status_code == 200, overview.text
        assert revenue.status_code == 200, revenue.text
        assert statements.status_code == 200, statements.text
        assert overview.json()["usage_total"] == 3
        assert money(revenue.json()["gross_revenue_amount"]) == Decimal("200.246912")
        assert money(revenue.json()["partner_share_amount"]) == Decimal("80.098765")
        assert money(revenue.json()["net_settlement_amount"]) == Decimal("81.209876")
        statement = statements.json()[0]
        assert statement["settlement"]["id"] == seeded["settlement"]["id"]
        assert statement["payouts"][0]["provider_transaction_reference"] == seeded["payout"]["provider_transaction_id"]
        assert statement["reconciliation"][0]["outcome"] == "amount_mismatch"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_reports_support_pagination_date_and_currency_filters() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        seed_financial_flow(client, partner_id, headers)
        key = create_partner_portal_key(db, partner_id)
        page = client.get(
            "/api/v1/partner-portal/usage",
            headers=portal_headers(key),
            params={
                "period_start": datetime(2026, 8, 13, tzinfo=UTC).isoformat(),
                "period_end": PERIOD_END.isoformat(),
                "currency": "USD",
                "limit": 1,
                "offset": 0,
            },
        )
        invalid = client.get(
            "/api/v1/partner-portal/usage",
            headers=portal_headers(key),
            params={"period_start": PERIOD_END.isoformat(), "period_end": PERIOD_START.isoformat()},
        )
        assert page.status_code == 200, page.text
        assert page.json()["usage_total"] == 2
        assert len(page.json()["rows"]) == 1
        assert page.json()["rows"][0]["content_id"] == "gntv-live"
        assert invalid.status_code == 400
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_partner_portal_isolates_tenants_and_cannot_call_operator_endpoint() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_a = create_partner(client, headers, "Portal Partner A")
        partner_b = create_partner(client, headers, "Portal Partner B")
        seed_financial_flow(client, partner_a, headers)
        key_a = create_partner_portal_key(db, partner_a)
        key_b = create_partner_portal_key(db, partner_b)
        me_a = client.get("/api/v1/partner-portal/me", headers=portal_headers(key_a))
        overview_b = client.get("/api/v1/partner-portal/overview", headers=portal_headers(key_b))
        operator_endpoint = client.get(f"/api/v1/partners/{partner_a}/payouts", headers=portal_headers(key_a))
        assert me_a.status_code == 200
        assert me_a.json()["partner"]["id"] == partner_a
        assert overview_b.status_code == 200
        assert overview_b.json()["usage_total"] == 0
        assert partner_a not in str(overview_b.json())
        assert operator_endpoint.status_code in {401, 403}
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_exports_neutralize_csv_formula_injection_and_offer_json_manifest() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        seed_financial_flow(client, partner_id, headers)
        key = create_partner_portal_key(db, partner_id)
        csv_response = client.get(
            "/api/v1/partner-portal/exports?report_type=usage&format=csv",
            headers=portal_headers(key),
        )
        json_response = client.get(
            "/api/v1/partner-portal/exports?report_type=statements&format=json",
            headers=portal_headers(key),
        )
        assert csv_response.status_code == 200, csv_response.text
        assert "'=FORMULA()" in csv_response.text
        assert "\n=FORMULA()" not in csv_response.text
        assert json_response.status_code == 200, json_response.text
        assert json_response.json()["report_type"] == "statements"
        unsupported = client.get(
            "/api/v1/partner-portal/exports?report_type=unknown&format=json",
            headers=portal_headers(key),
        )
        assert unsupported.status_code == 422
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_statement_detail_and_empty_export_are_partner_safe() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        seeded = seed_financial_flow(client, partner_id, headers)
        empty_partner = create_partner(client, headers, "Empty Portal Partner")
        key = create_partner_portal_key(db, partner_id)
        empty_key = create_partner_portal_key(db, empty_partner)
        detail = client.get(
            f"/api/v1/partner-portal/statements/{seeded['settlement']['id']}",
            headers=portal_headers(key),
        )
        missing_detail = client.get(
            f"/api/v1/partner-portal/statements/{uuid4()}",
            headers=portal_headers(key),
        )
        empty_csv = client.get(
            "/api/v1/partner-portal/exports?report_type=payouts&format=csv",
            headers=portal_headers(empty_key),
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["settlement"]["id"] == seeded["settlement"]["id"]
        assert detail.json()["payouts"][0]["provider_transaction_reference"]
        assert missing_detail.status_code == 400
        assert empty_csv.status_code == 200, empty_csv.text
        assert "payout_id" not in empty_csv.text
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_portal_safe_service_errors_and_cancelled_payout_state() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        service = PartnerSyndicationService(PartnerRepository(db))
        with pytest.raises(Exception, match="Valid partner portal key required"):
            service.authenticate_partner_portal_key("not-a-partner-key")
        with pytest.raises(ValueError, match="Payout account not found"):
            service.get_payout_account(UUID(partner_id), uuid4())

        agreement = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=headers,
            json={
                "name": "Cancel test agreement",
                "rule_type": "fixed_percentage",
                "fixed_partner_percentage": "0.5000",
                "currency": "USD",
                "starts_at": PERIOD_START.isoformat(),
            },
        )
        assert agreement.status_code == 201, agreement.text
        usage = client.post(
            f"/api/v1/partners/{partner_id}/billing/usage",
            headers=headers,
            json={
                "content_type": "live_channel",
                "content_id": "cancel-live",
                "usage_event_type": "ad_revenue",
                "quantity": 1,
                "gross_revenue_amount": "20.000000",
                "currency": "USD",
                "idempotency_key": f"cancel-usage-{uuid4().hex}",
                "occurred_at": datetime(2026, 8, 14, tzinfo=UTC).isoformat(),
            },
        )
        assert usage.status_code == 201, usage.text
        settlement = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements",
            headers=headers,
            json={
                "period_start": PERIOD_START.isoformat(),
                "period_end": PERIOD_END.isoformat(),
                "currency": "USD",
                "idempotency_key": f"cancel-settlement-{uuid4().hex}",
            },
        )
        assert settlement.status_code == 201, settlement.text
        finalized = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{settlement.json()['id']}/status",
            headers=headers,
            json={"status": "finalized", "reason": "cancel test"},
        )
        assert finalized.status_code == 200, finalized.text
        unverified_account = client.post(
            f"/api/v1/partners/{partner_id}/payout-accounts",
            headers=headers,
            json={
                "provider_type": "mock",
                "destination_label": "Needs Verification",
                "destination_reference": "needs-verification-4321",
                "currency": "USD",
                "verification_status": "pending",
                "idempotency_key": f"pending-account-{uuid4().hex}",
            },
        )
        assert unverified_account.status_code == 201, unverified_account.text
        blocked_payout = client.post(
            f"/api/v1/partners/{partner_id}/payouts",
            headers=headers,
            json={
                "settlement_id": finalized.json()["id"],
                "payout_account_id": unverified_account.json()["id"],
                "idempotency_key": f"blocked-payout-{uuid4().hex}",
            },
        )
        assert blocked_payout.status_code == 409
        verified_account = client.patch(
            f"/api/v1/partners/{partner_id}/payout-accounts/{unverified_account.json()['id']}",
            headers=headers,
            json={"verification_status": "verified", "destination_label": "Verified Destination"},
        )
        assert verified_account.status_code == 200, verified_account.text
        payout = client.post(
            f"/api/v1/partners/{partner_id}/payouts",
            headers=headers,
            json={
                "settlement_id": finalized.json()["id"],
                "payout_account_id": verified_account.json()["id"],
                "idempotency_key": f"cancel-payout-{uuid4().hex}",
            },
        )
        assert payout.status_code == 201, payout.text
        cancelled = client.post(
            f"/api/v1/partners/{partner_id}/payouts/{payout.json()['id']}/cancel",
            headers=headers,
            params={"reason": "partner requested bank review"},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_partner_visible_events_are_persisted_for_financial_status_feed() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        seed_financial_flow(client, partner_id, headers)
        key = create_partner_portal_key(db, partner_id)
        events = client.get("/api/v1/partner-portal/events", headers=portal_headers(key))
        event_types = {event["event_type"] for event in events.json()}
        assert events.status_code == 200, events.text
        assert "settlement_finalized" in event_types
        assert "payout_approved" in event_types
        assert "payout_paid" in event_types
        assert "reconciliation_exception" in event_types
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_migration_upgrade_and_downgrade_creates_partner_portal_events() -> None:
    module_path = (

        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "202609071200_module7_sprint79_partner_portal.py"
    )
    spec = importlib.util.spec_from_file_location("sprint79_migration", module_path)

    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE partners (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = getattr(migration, "op")
        setattr(migration, "op", operations)
        try:
            migration.upgrade()
            inspector = inspect(connection)
            assert "partner_portal_users" in inspector.get_table_names()
            assert "partner_portal_events" in inspector.get_table_names()
            assert "ix_partner_portal_events_partner_created" in {
                index["name"] for index in inspector.get_indexes("partner_portal_events")
            }
            migration.downgrade()
            inspector = inspect(connection)
            assert "partner_portal_users" not in inspector.get_table_names()
            assert "partner_portal_events" not in inspector.get_table_names()
        finally:
            setattr(migration, "op", original_op)



def test_sprint79_dedicated_csv_endpoints_and_portal_user_service() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        admin_hdr = auth_headers(admin)
        partner_id = create_partner(client, admin_hdr)
        seed_financial_flow(client, partner_id, admin_hdr)
        key = create_partner_portal_key(db, partner_id)
        p_hdr = portal_headers(key)

        # 1. /api/v1/partner-portal/exports/usage
        usage_csv = client.get("/api/v1/partner-portal/exports/usage", headers=p_hdr)
        assert usage_csv.status_code == 200
        assert "text/csv" in usage_csv.headers["Content-Type"]
        assert f"gntv-partner-usage-{partner_id}.csv" in usage_csv.headers["Content-Disposition"]

        # 2. /api/v1/partner-portal/exports/financial
        fin_csv = client.get("/api/v1/partner-portal/exports/financial", headers=p_hdr)
        assert fin_csv.status_code == 200
        assert "text/csv" in fin_csv.headers["Content-Type"]
        assert f"gntv-partner-financial-{partner_id}.csv" in fin_csv.headers["Content-Disposition"]

        # 3. Test portal user service methods
        service = PartnerSyndicationService(PartnerRepository(db))
        new_user = create_user(db, "portal_finance_user")
        created_portal_user = service.add_portal_user(UUID(partner_id), new_user.id, "partner_finance")
        assert created_portal_user.role == "partner_finance"

        user_list = service.list_portal_users(UUID(partner_id))
        assert len(user_list) >= 1
        assert any(u.user_id == new_user.id for u in user_list)

        # 4. Inactive partner credential rejection
        inactive_key = f"gntv_pk_{uuid4().hex}{uuid4().hex}"
        inactive_cred = PartnerApiCredential(
            partner_id=UUID(partner_id),
            key_prefix=inactive_key[:14],
            secret_hash=service.hash_api_secret(inactive_key),
            status=PartnerCredentialStatus.REVOKED,
        )
        db.add(inactive_cred)
        db.commit()

        bad_auth = client.get("/api/v1/partner-portal/me", headers=portal_headers(inactive_key))
        assert bad_auth.status_code == 401

        # 5. Non-existent statement returns 400
        bad_stmt = client.get(f"/api/v1/partner-portal/statements/{uuid4()}", headers=p_hdr)
        assert bad_stmt.status_code == 400
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint79_openapi_contains_partner_portal_contracts() -> None:
    openapi = app.openapi()
    paths = openapi.get("paths", {})

    expected_portal_paths = [
        "/api/v1/partner-portal/me",
        "/api/v1/partner-portal/overview",
        "/api/v1/partner-portal/usage",
        "/api/v1/partner-portal/revenue",
        "/api/v1/partner-portal/settlements",
        "/api/v1/partner-portal/statements",
        "/api/v1/partner-portal/statements/{statement_id}",
        "/api/v1/partner-portal/payouts",
        "/api/v1/partner-portal/reconciliation",
        "/api/v1/partner-portal/exports",
        "/api/v1/partner-portal/exports/usage",
        "/api/v1/partner-portal/exports/financial",
        "/api/v1/partner-portal/events",
    ]

    for path in expected_portal_paths:
        assert path in paths, f"Path {path} missing from OpenAPI contracts"
        methods = paths[path]
        # Partner portal endpoints MUST be read-only GET operations
        assert "get" in methods, f"GET method missing on {path}"
        assert not any(m in methods for m in ["post", "put", "patch", "delete"]), f"Forbidden mutation method on {path}"
