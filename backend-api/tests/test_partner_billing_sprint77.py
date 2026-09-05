from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import importlib.util
from pathlib import Path
from typing import Generator, cast
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
from app.modules.partners.models import PartnerFinancialAuditLog, PartnerSettlementStatement
from app.utils.jwt import create_access_token


PERIOD_START = datetime(2026, 8, 1, tzinfo=UTC)
PERIOD_END = datetime(2026, 9, 1, tzinfo=UTC)


def make_db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    return testing_session()


def make_client(db: Session) -> TestClient:
    def override_get_db() -> Generator[Session, None, None]:
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


def create_partner(client: TestClient, headers: dict[str, str], name: str = "Billing Partner") -> str:
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


def create_fixed_agreement(
    client: TestClient,
    partner_id: str,
    headers: dict[str, str],
    percentage: str = "0.3000",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
        headers=headers,
        json={
            "name": "Standard revenue share",
            "rule_type": "fixed_percentage",
            "fixed_partner_percentage": percentage,
            "currency": "USD",
            "starts_at": PERIOD_START.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def record_usage(
    client: TestClient,
    partner_id: str,
    headers: dict[str, str],
    idempotency_key: str,
    gross: str,
    quantity: int = 1,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/partners/{partner_id}/billing/usage",
        headers=headers,
        json={
            "content_type": "live_channel",
            "content_id": "gntv-live",
            "usage_event_type": "ad_revenue",
            "quantity": quantity,
            "gross_revenue_amount": gross,
            "currency": "USD",
            "source_event_id": idempotency_key,
            "idempotency_key": idempotency_key,
            "occurred_at": datetime(2026, 8, 10, tzinfo=UTC).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def generate_settlement(
    client: TestClient,
    partner_id: str,
    headers: dict[str, str],
    idempotency_key: str = "settlement-august-2026",
    adjustment: str = "0",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/partners/{partner_id}/billing/settlements",
        headers=headers,
        json={
            "period_start": PERIOD_START.isoformat(),
            "period_end": PERIOD_END.isoformat(),
            "currency": "USD",
            "adjustment_amount": adjustment,
            "idempotency_key": idempotency_key,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def money(value: object) -> Decimal:
    return Decimal(str(value))


def test_sprint77_billing_apis_are_admin_only() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        viewer = create_user(db, "viewer")
        partner_id = create_partner(client, auth_headers(admin))
        forbidden = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=auth_headers(viewer),
            json={
                "name": "Blocked",
                "rule_type": "fixed_percentage",
                "fixed_partner_percentage": "0.2500",
                "starts_at": PERIOD_START.isoformat(),
            },
        )
        assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_fixed_revenue_share_settlement_uses_decimal_money() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        create_fixed_agreement(client, partner_id, headers, "0.3000")
        record_usage(client, partner_id, headers, "usage-one", "100.00", quantity=3)
        record_usage(client, partner_id, headers, "usage-two", "50.00", quantity=2)
        settlement = generate_settlement(client, partner_id, headers, adjustment="5.00")
        assert settlement["usage_count"] == 5
        assert money(settlement["gross_revenue_amount"]) == Decimal("150.000000")
        assert money(settlement["partner_share_amount"]) == Decimal("45.000000")
        assert money(settlement["platform_share_amount"]) == Decimal("105.000000")
        assert money(settlement["adjustment_amount"]) == Decimal("5.000000")
        assert money(settlement["net_settlement_amount"]) == Decimal("50.000000")
        assert settlement["status"] == "draft"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_tiered_revenue_share_uses_highest_matching_tier() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        agreement = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=headers,
            json={
                "name": "Growth tiers",
                "rule_type": "tiered_percentage",
                "tiers": [
                    {"threshold_amount": "0", "partner_percentage": "0.2000"},
                    {"threshold_amount": "100", "partner_percentage": "0.4000"},
                ],
                "currency": "USD",
                "starts_at": PERIOD_START.isoformat(),
            },
        )
        assert agreement.status_code == 201, agreement.text
        record_usage(client, partner_id, headers, "usage-tiered", "150.00")
        settlement = generate_settlement(client, partner_id, headers, idempotency_key="settlement-tiered")
        assert money(settlement["partner_share_amount"]) == Decimal("60.000000")
        assert money(settlement["platform_share_amount"]) == Decimal("90.000000")
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_usage_and_settlement_generation_are_idempotent() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        create_fixed_agreement(client, partner_id, headers)
        first_usage = record_usage(client, partner_id, headers, "usage-idem", "12.34")
        second_usage = record_usage(client, partner_id, headers, "usage-idem", "99.99")
        first_settlement = generate_settlement(client, partner_id, headers, idempotency_key="settlement-idem")
        second_settlement = generate_settlement(client, partner_id, headers, idempotency_key="settlement-idem")
        same_period_settlement = generate_settlement(client, partner_id, headers, idempotency_key="settlement-period")
        assert second_usage["id"] == first_usage["id"]
        assert second_settlement["id"] == first_settlement["id"]
        assert same_period_settlement["id"] == first_settlement["id"]
        assert db.query(PartnerSettlementStatement).count() == 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_status_workflow_and_audit_logging() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        create_fixed_agreement(client, partner_id, headers)
        record_usage(client, partner_id, headers, "usage-status", "80.00")
        statement = generate_settlement(client, partner_id, headers, idempotency_key="settlement-status")
        finalized = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{statement['id']}/status",
            headers=headers,
            json={"status": "finalized", "reason": "Approved by finance"},
        )
        paid = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{statement['id']}/status",
            headers=headers,
            json={"status": "paid", "reason": "Bank transfer confirmed"},
        )
        rejected = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{statement['id']}/status",
            headers=headers,
            json={"status": "void"},
        )
        audits = client.get(f"/api/v1/partners/{partner_id}/billing/audit", headers=headers)
        assert finalized.status_code == 200, finalized.text
        assert finalized.json()["finalized_at"] is not None
        assert paid.status_code == 200, paid.text
        assert paid.json()["paid_at"] is not None
        assert rejected.status_code == 409
        assert audits.status_code == 200, audits.text
        actions = {item["action"] for item in audits.json()}
        assert {"agreement_created", "usage_recorded", "settlement_generated", "settlement_status_changed"} <= actions
        assert db.query(PartnerFinancialAuditLog).count() >= 4
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_partner_tenant_isolation_for_financial_records() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_a = create_partner(client, headers, "Tenant A")
        partner_b = create_partner(client, headers, "Tenant B")
        create_fixed_agreement(client, partner_a, headers)
        record_usage(client, partner_a, headers, "tenant-a-usage", "30.00")
        statement = generate_settlement(client, partner_a, headers, idempotency_key="tenant-a-statement")
        usage_b = client.get(f"/api/v1/partners/{partner_b}/billing/usage", headers=headers)
        wrong_status = client.post(
            f"/api/v1/partners/{partner_b}/billing/settlements/{statement['id']}/status",
            headers=headers,
            json={"status": "finalized"},
        )
        assert usage_b.status_code == 200
        assert usage_b.json() == []
        assert wrong_status.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_no_fabricated_revenue_when_usage_is_empty() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)
        create_fixed_agreement(client, partner_id, headers)
        settlement = generate_settlement(client, partner_id, headers, idempotency_key="empty-revenue")
        assert settlement["usage_count"] == 0
        assert money(settlement["gross_revenue_amount"]) == Decimal("0.000000")
        assert money(settlement["partner_share_amount"]) == Decimal("0.000000")
        assert money(settlement["net_settlement_amount"]) == Decimal("0.000000")
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_openapi_contains_billing_contracts() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/partners/{partner_id}/billing/revenue-share-agreements" in paths
    assert "/api/v1/partners/{partner_id}/billing/usage" in paths
    assert "/api/v1/partners/{partner_id}/billing/settlements" in paths
    assert "/api/v1/partners/{partner_id}/billing/audit" in paths


def test_sprint77_migration_upgrade_and_downgrade() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "202609041200_module7_sprint77_partner_billing.py"
    )
    spec = importlib.util.spec_from_file_location("migration_202609041200", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE partners (id CHAR(32) PRIMARY KEY)")
        context = MigrationContext.configure(connection)
        op = Operations(context)
        previous_op = getattr(migration, "op", None)
        setattr(migration, "op", op)
        try:
            migration.upgrade()
            tables_after_upgrade = set(inspect(connection).get_table_names())
            assert "partner_usage_metering" in tables_after_upgrade
            assert "partner_revenue_share_agreements" in tables_after_upgrade
            assert "partner_settlement_statements" in tables_after_upgrade
            assert "partner_financial_audit_logs" in tables_after_upgrade
            migration.downgrade()
            tables_after_downgrade = set(inspect(connection).get_table_names())
            assert "partner_usage_metering" not in tables_after_downgrade
            assert "partner_revenue_share_agreements" not in tables_after_downgrade
        finally:
            setattr(migration, "op", previous_op)


def test_sprint77_listing_and_not_found_routes() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)
        partner_id = create_partner(client, headers, "List Test Partner")
        fake_id = str(uuid4())

        # List agreements
        create_fixed_agreement(client, partner_id, headers)
        agreements = client.get(f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements", headers=headers)
        assert agreements.status_code == 200
        assert len(agreements.json()) == 1

        # 404 for unknown partner on agreements
        agreements_404 = client.get(f"/api/v1/partners/{fake_id}/billing/revenue-share-agreements", headers=headers)
        assert agreements_404.status_code == 404

        # Record usage and list usage
        record_usage(client, partner_id, headers, "usage-filter", "200.00")
        start_str = PERIOD_START.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = PERIOD_END.strftime("%Y-%m-%dT%H:%M:%SZ")
        usage_res = client.get(
            f"/api/v1/partners/{partner_id}/billing/usage?period_start={start_str}&period_end={end_str}&currency=USD",
            headers=headers,
        )
        assert usage_res.status_code == 200
        assert len(usage_res.json()) == 1

        # Invalid usage period query
        bad_usage_period = client.get(
            f"/api/v1/partners/{partner_id}/billing/usage?period_start={end_str}&period_end={start_str}",
            headers=headers,
        )
        assert bad_usage_period.status_code == 400

        # List settlements
        generate_settlement(client, partner_id, headers, "settlement-list-test")
        settlements = client.get(f"/api/v1/partners/{partner_id}/billing/settlements", headers=headers)
        assert settlements.status_code == 200
        assert len(settlements.json()) == 1

        settlements_404 = client.get(f"/api/v1/partners/{fake_id}/billing/settlements", headers=headers)
        assert settlements_404.status_code == 404

        # List audits
        audits = client.get(f"/api/v1/partners/{partner_id}/billing/audit", headers=headers)
        assert audits.status_code == 200
        assert len(audits.json()) >= 3

        audits_404 = client.get(f"/api/v1/partners/{fake_id}/billing/audit", headers=headers)
        assert audits_404.status_code == 404

        # Statement not found for status update
        bad_stmt = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{fake_id}/status",
            headers=headers,
            json={"status": "finalized"},
        )
        assert bad_stmt.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_settlement_dispute_and_void_lifecycle() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "operator"))
        partner_id = create_partner(client, headers)
        create_fixed_agreement(client, partner_id, headers)
        record_usage(client, partner_id, headers, "usage-dispute", "500.00")
        stmt = generate_settlement(client, partner_id, headers, "settlement-dispute-flow")

        # draft -> disputed -> finalized -> disputed -> void
        dispute1 = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{stmt['id']}/status",
            headers=headers,
            json={"status": "disputed", "reason": "Metric discrepancies"},
        )
        assert dispute1.status_code == 200
        assert dispute1.json()["status"] == "disputed"

        fin1 = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{stmt['id']}/status",
            headers=headers,
            json={"status": "finalized", "reason": "Audit cleared"},
        )
        assert fin1.status_code == 200
        assert fin1.json()["status"] == "finalized"

        dispute2 = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{stmt['id']}/status",
            headers=headers,
            json={"status": "disputed", "reason": "Secondary discrepancy"},
        )
        assert dispute2.status_code == 200
        assert dispute2.json()["status"] == "disputed"

        voided = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{stmt['id']}/status",
            headers=headers,
            json={"status": "void", "reason": "Cancelled by operator"},
        )
        assert voided.status_code == 200
        assert voided.json()["status"] == "void"

        # voided cannot transition to paid or anything else
        invalid_after_void = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements/{stmt['id']}/status",
            headers=headers,
            json={"status": "paid"},
        )
        assert invalid_after_void.status_code == 409
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_agreement_and_settlement_validation_rules() -> None:
    db = make_db()
    client = make_client(db)
    try:
        headers = auth_headers(create_user(db, "admin"))
        partner_id = create_partner(client, headers)

        # 1. ends_at <= starts_at
        bad_dates = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=headers,
            json={
                "name": "Bad dates",
                "rule_type": "fixed_percentage",
                "fixed_partner_percentage": "0.3000",
                "starts_at": "2026-09-01T00:00:00Z",
                "ends_at": "2026-08-01T00:00:00Z",
            },
        )
        assert bad_dates.status_code == 422

        # 2. Fixed rule without fixed_partner_percentage
        missing_pct = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=headers,
            json={
                "name": "Missing percentage",
                "rule_type": "fixed_percentage",
                "starts_at": "2026-08-01T00:00:00Z",
            },
        )
        assert missing_pct.status_code == 422

        # 3. Tiered rule without tiers
        missing_tiers = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=headers,
            json={
                "name": "Missing tiers",
                "rule_type": "tiered_percentage",
                "starts_at": "2026-08-01T00:00:00Z",
            },
        )
        assert missing_tiers.status_code == 422

        # 4. Tiered rule with unsorted thresholds
        unsorted_tiers = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=headers,
            json={
                "name": "Unsorted tiers",
                "rule_type": "tiered_percentage",
                "tiers": [
                    {"threshold_amount": "500", "partner_percentage": "0.4000"},
                    {"threshold_amount": "100", "partner_percentage": "0.2000"},
                ],
                "starts_at": "2026-08-01T00:00:00Z",
            },
        )
        assert unsorted_tiers.status_code == 422

        # 5. Settlement period_start >= period_end
        bad_settlement_period = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements",
            headers=headers,
            json={
                "period_start": "2026-09-01T00:00:00Z",
                "period_end": "2026-08-01T00:00:00Z",
                "idempotency_key": "bad-period",
            },
        )
        assert bad_settlement_period.status_code == 422

        # 6. Settlement generation without any agreement covering period
        no_agreement = client.post(
            f"/api/v1/partners/{partner_id}/billing/settlements",
            headers=headers,
            json={
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-02-01T00:00:00Z",
                "idempotency_key": "no-agreement-period",
            },
        )
        assert no_agreement.status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint77_partner_api_key_auth_and_partner_management() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        admin_headers = auth_headers(admin)

        # Create partner with raw credential response
        res = client.post(
            "/api/v1/partners",
            headers=admin_headers,
            json={"name": "SDK Partner", "slug": f"sdk-{uuid4().hex[:8]}", "status": "active"},
        )
        assert res.status_code == 201
        partner_id = res.json()["partner"]["id"]
        partner_slug = res.json()["partner"]["slug"]

        # List partners
        partners_list = client.get("/api/v1/partners", headers=admin_headers)
        assert partners_list.status_code == 200
        assert any(p["id"] == partner_id for p in partners_list.json())

        # Get partner by ID
        partner_detail = client.get(f"/api/v1/partners/{partner_id}", headers=admin_headers)
        assert partner_detail.status_code == 200
        assert partner_detail.json()["slug"] == partner_slug

        # Analytics overview
        analytics = client.get("/api/v1/partners/analytics/overview", headers=admin_headers)
        assert analytics.status_code == 200
        assert analytics.json()["partner_count"] >= 1

        # Add domain and list domains
        add_dom = client.post(
            f"/api/v1/partners/{partner_id}/domains",
            headers=admin_headers,
            json={"domain_pattern": "sdk.partner.com"},
        )
        assert add_dom.status_code == 201
        dom_list = client.get(f"/api/v1/partners/{partner_id}/domains", headers=admin_headers)
        assert dom_list.status_code == 200
        assert len(dom_list.json()) == 1

        # Add entitlement and list entitlements
        add_ent = client.post(
            f"/api/v1/partners/{partner_id}/entitlements",
            headers=admin_headers,
            json={"content_type": "vod", "content_id": "vod-movie-1"},
        )
        assert add_ent.status_code == 201
        ent_list = client.get(f"/api/v1/partners/{partner_id}/entitlements", headers=admin_headers)
        assert ent_list.status_code == 200
        assert len(ent_list.json()) == 1

        # Get embed SDK
        sdk_res = client.get("/api/v1/embed/sdk.js")
        assert sdk_res.status_code == 200
        assert "GNTV.embed" in sdk_res.text
    finally:
        app.dependency_overrides.clear()
        db.close()


