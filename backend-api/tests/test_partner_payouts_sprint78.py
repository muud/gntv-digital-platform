from __future__ import annotations
from uuid import UUID

from datetime import UTC, datetime
from decimal import Decimal

from typing import Any, Iterator, cast
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.partners.models import PartnerPayoutAccount, PartnerSettlementStatement
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


def create_partner(client: TestClient, headers: dict[str, str], name: str = "Payout Partner") -> str:
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


def create_finalized_settlement(client: TestClient, partner_id: str, headers: dict[str, str]) -> dict[str, Any]:
    agreement = client.post(
        f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
        headers=headers,
        json={
            "name": "Payout agreement",
            "rule_type": "fixed_percentage",
            "fixed_partner_percentage": "0.3333",
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
            "content_id": "gntv-live",
            "usage_event_type": "ad_revenue",
            "quantity": 1,
            "gross_revenue_amount": "123.456789",
            "currency": "USD",
            "idempotency_key": f"usage-{uuid4().hex}",
            "occurred_at": datetime(2026, 8, 12, tzinfo=UTC).isoformat(),
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
            "idempotency_key": f"settlement-{uuid4().hex}",
        },
    )
    assert settlement.status_code == 201, settlement.text
    finalized = client.post(
        f"/api/v1/partners/{partner_id}/billing/settlements/{settlement.json()['id']}/status",
        headers=headers,
        json={"status": "finalized", "reason": "Approved for payout"},
    )
    assert finalized.status_code == 200, finalized.text
    return cast(dict[str, Any], finalized.json())


def create_payout_account(
    client: TestClient,
    partner_id: str,
    headers: dict[str, str],
    destination_reference: str = "mock_dest_main",
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/partners/{partner_id}/payout-accounts",
        headers=headers,
        json={
            "provider_type": "mock",
            "destination_label": "Verified sandbox destination",
            "destination_reference": destination_reference,
            "provider_metadata": {"rail": "sandbox", "country": "KE"},
            "currency": "USD",
            "verification_status": "verified",
            "idempotency_key": f"account-{uuid4().hex}",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def create_payout(
    client: TestClient,
    partner_id: str,
    headers: dict[str, str],
    settlement_id: str,
    account_id: str,
    idempotency_key: str = "payout-main-key",
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/partners/{partner_id}/payouts",
        headers=headers,
        json={
            "settlement_id": settlement_id,
            "payout_account_id": account_id,
            "idempotency_key": idempotency_key,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_sprint78_payout_account_security_and_rbac() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        viewer = create_user(db, "viewer")
        partner_id = create_partner(client, auth_headers(admin))
        forbidden = client.get(f"/api/v1/partners/{partner_id}/payout-accounts", headers=auth_headers(viewer))
        sensitive = client.post(
            f"/api/v1/partners/{partner_id}/payout-accounts",
            headers=auth_headers(admin),
            json={
                "provider_type": "mock",
                "destination_label": "Unsafe",
                "destination_reference": "mock_dest_unsafe",
                "provider_metadata": {"account_number": "123456"},
                "currency": "USD",
                "verification_status": "verified",
                "idempotency_key": "unsafe-account-key",
            },
        )
        account = create_payout_account(client, partner_id, auth_headers(admin))
        stored = db.query(PartnerPayoutAccount).filter_by(id=UUID(str(account["id"]))).one()
        assert forbidden.status_code == 403
        assert sensitive.status_code == 422
        assert "encrypted_provider_metadata" not in str(account)
        assert stored.encrypted_provider_metadata is not None
        assert "sandbox" not in stored.encrypted_provider_metadata
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint78_payout_requires_finalized_settlement_and_verified_account() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        account = create_payout_account(client, partner_id, headers)
        draft = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements",
            headers=headers,
            json={
                "period_start": PERIOD_START.isoformat(),
                "period_end": PERIOD_END.isoformat(),
                "currency": "USD",
                "idempotency_key": "draft-settlement-key",
            },
        )
        assert draft.status_code == 403
        settlement = create_finalized_settlement(client, partner_id, headers)
        disabled = client.patch(
            f"/api/v1/partners/{partner_id}/payout-accounts/{account['id']}",
            headers=headers,
            json={"status": "disabled"},
        )
        assert disabled.status_code == 200
        blocked = client.post(
            f"/api/v1/partners/{partner_id}/payouts",
            headers=headers,
            json={
                "settlement_id": settlement["id"],
                "payout_account_id": account["id"],
                "idempotency_key": "blocked-payout-key",
            },
        )
        assert blocked.status_code == 409
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint78_payout_approval_execution_idempotency_and_decimal_precision() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        settlement = create_finalized_settlement(client, partner_id, headers)
        account = create_payout_account(client, partner_id, headers)
        payout = create_payout(client, partner_id, headers, str(settlement["id"]), str(account["id"]), "payout-idem-key")
        duplicate = create_payout(client, partner_id, headers, str(settlement["id"]), str(account["id"]), "payout-idem-key")
        early_execute = client.post(
            f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/execute",
            headers=headers,
            json={"idempotency_key": "execute-before-approval"},
        )
        approved = client.post(f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/approve", headers=headers)
        executed = client.post(
            f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/execute",
            headers=headers,
            json={"idempotency_key": "execute-main-key"},
        )
        repeated = client.post(
            f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/execute",
            headers=headers,
            json={"idempotency_key": "execute-main-key"},
        )
        refreshed_settlement = db.query(PartnerSettlementStatement).filter_by(id=UUID(str(settlement["id"]))).one()
        assert duplicate["id"] == payout["id"]
        assert early_execute.status_code == 409
        assert approved.status_code == 200
        assert executed.status_code == 200, executed.text
        assert executed.json()["status"] == "paid"
        assert repeated.json()["id"] == payout["id"]
        assert repeated.json()["provider_transaction_id"] == executed.json()["provider_transaction_id"]
        assert money(executed.json()["amount"]) == money(settlement["net_settlement_amount"])
        assert refreshed_settlement.status.value == "finalized"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint78_duplicate_payout_prevention_and_tenant_isolation() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_a = create_partner(client, headers, "Payout Tenant A")
        partner_b = create_partner(client, headers, "Payout Tenant B")
        settlement = create_finalized_settlement(client, partner_a, headers)
        account = create_payout_account(client, partner_a, headers)
        payout = create_payout(client, partner_a, headers, str(settlement["id"]), str(account["id"]), "payout-tenant-key")
        duplicate_settlement = client.post(
            f"/api/v1/partners/{partner_a}/payouts",
            headers=headers,
            json={
                "settlement_id": settlement["id"],
                "payout_account_id": account["id"],
                "idempotency_key": "different-payout-key",
            },
        )
        wrong_partner_get = client.get(f"/api/v1/partners/{partner_b}/payouts/{payout['id']}", headers=headers)
        wrong_partner_account = client.patch(
            f"/api/v1/partners/{partner_b}/payout-accounts/{account['id']}",
            headers=headers,
            json={"destination_label": "Cross tenant"},
        )
        assert duplicate_settlement.status_code == 409
        assert wrong_partner_get.status_code == 404
        assert wrong_partner_account.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint78_provider_failure_and_cancel_state_rules() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        settlement = create_finalized_settlement(client, partner_id, headers)
        account = create_payout_account(client, partner_id, headers, destination_reference="mock_dest_fail")
        payout = create_payout(client, partner_id, headers, str(settlement["id"]), str(account["id"]), "payout-fail-key")
        approved = client.post(f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/approve", headers=headers)
        failed = client.post(
            f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/execute",
            headers=headers,
            json={"idempotency_key": "execute-fail-key"},
        )
        cancelled = client.post(
            f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/cancel?reason=manual-review",
            headers=headers,
        )
        assert approved.status_code == 200
        assert failed.status_code == 200
        assert failed.json()["status"] == "failed"
        assert failed.json()["failure_code"] == "provider_failure"
        assert cancelled.status_code == 409
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint78_reconciliation_outcomes_are_deterministic() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        settlement = create_finalized_settlement(client, partner_id, headers)
        account = create_payout_account(client, partner_id, headers)
        payout = create_payout(client, partner_id, headers, str(settlement["id"]), str(account["id"]), "payout-recon-key")
        client.post(f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/approve", headers=headers)
        paid = client.post(
            f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/execute",
            headers=headers,
            json={"idempotency_key": "execute-recon-key"},
        ).json()
        transaction_id = paid["provider_transaction_id"]
        matched = client.post(
            f"/api/v1/partners/{partner_id}/reconciliation",
            headers=headers,
            json={
                "provider_type": "mock",
                "provider_transaction_id": transaction_id,
                "reported_amount": paid["amount"],
                "reported_currency": paid["currency"],
                "provider_status": "paid",
                "idempotency_key": "recon-match-key",
            },
        )
        duplicate = client.post(
            f"/api/v1/partners/{partner_id}/reconciliation",
            headers=headers,
            json={
                "provider_type": "mock",
                "provider_transaction_id": transaction_id,
                "reported_amount": paid["amount"],
                "reported_currency": paid["currency"],
                "provider_status": "paid",
                "idempotency_key": "recon-duplicate-key",
            },
        )
        unknown = client.post(
            f"/api/v1/partners/{partner_id}/reconciliation",
            headers=headers,
            json={
                "provider_type": "mock",
                "provider_transaction_id": "mock-unknown-transaction",
                "reported_amount": "1.00",
                "reported_currency": "USD",
                "provider_status": "paid",
                "idempotency_key": "recon-unknown-key",
            },
        )
        assert matched.status_code == 201, matched.text
        assert matched.json()["outcome"] == "matched"
        assert duplicate.json()["outcome"] == "duplicate_provider_transaction"
        assert unknown.json()["outcome"] == "unknown_transaction"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint78_reconciliation_detects_amount_currency_and_returned_mismatches() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))

        def execute_case(name: str) -> dict[str, Any]:
            partner_id = create_partner(client, headers, name)
            settlement = create_finalized_settlement(client, partner_id, headers)
            account = create_payout_account(client, partner_id, headers)
            payout = create_payout(client, partner_id, headers, str(settlement["id"]), str(account["id"]), f"payout-{name}")
            client.post(f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/approve", headers=headers)
            paid = cast(dict[str, Any], client.post(
                f"/api/v1/partners/{partner_id}/payouts/{payout['id']}/execute",
                headers=headers,
                json={"idempotency_key": f"execute-{name}"},
            ).json())
            paid["partner_id"] = partner_id
            return paid

        amount_case = execute_case("amount-case")
        amount_mismatch = client.post(
            f"/api/v1/partners/{amount_case['partner_id']}/reconciliation",
            headers=headers,
            json={
                "provider_type": "mock",
                "provider_transaction_id": amount_case["provider_transaction_id"],
                "reported_amount": "9.99",
                "reported_currency": amount_case["currency"],
                "provider_status": "paid",
                "idempotency_key": "recon-amount-key",
            },
        )
        currency_case = execute_case("currency-case")
        currency_mismatch = client.post(
            f"/api/v1/partners/{currency_case['partner_id']}/reconciliation",
            headers=headers,
            json={
                "provider_type": "mock",
                "provider_transaction_id": currency_case["provider_transaction_id"],
                "reported_amount": currency_case["amount"],
                "reported_currency": "EUR",
                "provider_status": "paid",
                "idempotency_key": "recon-currency-key",
            },
        )
        returned_case = execute_case("returned-case")
        returned = client.post(
            f"/api/v1/partners/{returned_case['partner_id']}/reconciliation",
            headers=headers,
            json={
                "provider_type": "mock",
                "provider_transaction_id": returned_case["provider_transaction_id"],
                "reported_amount": returned_case["amount"],
                "reported_currency": returned_case["currency"],
                "provider_status": "returned",
                "idempotency_key": "recon-returned-key",
            },
        )
        assert amount_mismatch.json()["outcome"] == "amount_mismatch"
        assert currency_mismatch.json()["outcome"] == "currency_mismatch"
        assert returned.json()["outcome"] == "failed_or_returned"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint78_openapi_contains_payout_contracts() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/partners/{partner_id}/payout-accounts" in paths
    assert "/api/v1/partners/{partner_id}/payouts" in paths
    assert "/api/v1/partners/{partner_id}/payouts/{payout_id}" in paths
    assert "/api/v1/partners/{partner_id}/payouts/{payout_id}/approve" in paths
    assert "/api/v1/partners/{partner_id}/payouts/{payout_id}/execute" in paths
    assert "/api/v1/partners/{partner_id}/reconciliation" in paths


def test_sprint78_migration_upgrade_and_downgrade() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "202609051200_module7_sprint78_partner_payouts.py"
    )
    spec = importlib.util.spec_from_file_location("migration_202609051200", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE partners (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE partner_settlement_statements (id CHAR(32) PRIMARY KEY)")
        context = MigrationContext.configure(connection)
        op = Operations(context)
        previous_op = getattr(migration, "op")
        setattr(migration, "op", op)
        try:
            migration.upgrade()
            tables_after_upgrade = set(inspect(connection).get_table_names())
            assert "partner_payout_accounts" in tables_after_upgrade
            assert "partner_payouts" in tables_after_upgrade
            assert "partner_payout_reconciliations" in tables_after_upgrade
            assert "partner_payout_audit_logs" in tables_after_upgrade
            migration.downgrade()
            tables_after_downgrade = set(inspect(connection).get_table_names())
            assert "partner_payout_accounts" not in tables_after_downgrade
            assert "partner_payouts" not in tables_after_downgrade
        finally:
            setattr(migration, "op", previous_op)
