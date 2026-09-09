from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.partners.models import (
    PartnerApiCredential,
    PartnerCredentialStatus,
    PartnerLifecycleAuditLog,
    PartnerPortalUser,
)
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


def invite_partner(client: TestClient, headers: dict[str, str], email: str = "partner@gntv.test") -> dict[str, object]:
    response = client.post(
        "/api/v1/partners/lifecycle/invitations",
        headers=headers,
        json={
            "partner": {
                "name": f"Lifecycle Partner {uuid4().hex[:6]}",
                "slug": f"lifecycle-{uuid4().hex[:10]}",
                "contact_email": email,
            },
            "invitation": {"target_email": email},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def portal_headers(token: str) -> dict[str, str]:
    return {"X-Partner-Key": token}


def add_partner_key(db: Session, partner_id: str) -> str:
    raw_key = f"gntv_pk_{uuid4().hex}{uuid4().hex}"
    service = PartnerSyndicationService(PartnerRepository(db))
    db.add(
        PartnerApiCredential(
            partner_id=UUID(partner_id),
            key_prefix=raw_key[:14],
            secret_hash=service.hash_api_secret(raw_key),
            status=PartnerCredentialStatus.ACTIVE,
        )
    )
    db.commit()
    return raw_key


def complete_profile(client: TestClient, headers: dict[str, str]) -> None:
    response = client.patch(
        "/api/v1/partner-portal/onboarding/profile",
        headers=headers,
        json={
            "legal_organization_name": "Horn Civic Media Ltd",
            "display_name": "Horn Civic Media",
            "organization_type": "media_network",
            "country": "KE",
            "primary_business_contact": {"name": "Amina Hassan", "email": "amina@example.test"},
            "finance_contact": {"name": "Finance Team", "email": "finance@example.test"},
            "technical_contact": {"name": "Tech Team", "email": "tech@example.test"},
            "requested_domains": ["player.partner.test"],
            "requested_capabilities": ["live_embed", "api_reporting"],
            "requested_api_embed_access": True,
            "settlement_currency": "USD",
        },
    )
    assert response.status_code == 200, response.text


def submit_and_approve(client: TestClient, partner_id: str, portal_auth: dict[str, str], admin_headers: dict[str, str]) -> None:
    complete_profile(client, portal_auth)
    submitted = client.post("/api/v1/partner-portal/onboarding/submit", headers=portal_auth)
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/api/v1/partners/{partner_id}/lifecycle/approve",
        headers=admin_headers,
        json={"review_notes": "Approved"},
    )
    assert approved.status_code == 200, approved.text


def test_sprint710_invitation_acceptance_is_hashed_and_idempotent() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        partner_user = create_user(db, "viewer")
        invitation = invite_partner(client, auth_headers(admin))
        token = str(invitation["invitation_reference"])
        partner_id = str(invitation["partner_id"])
        assert "gntv_inv_" in token
        assert token not in str(db.query(PartnerApiCredential).all())
        accepted = client.post(
            "/api/v1/partner-portal/invitations/accept",
            json={"token": token, "user_id": partner_user.id},
        )
        accepted_again = client.post(
            "/api/v1/partner-portal/invitations/accept",
            json={"token": token, "user_id": partner_user.id},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted_again.status_code == 200, accepted_again.text
        assert accepted.json()["partner"]["lifecycle_status"] == "onboarding"
        assert accepted_again.json()["partner"]["id"] == partner_id
        assert db.query(PartnerPortalUser).filter_by(partner_id=UUID(partner_id)).count() == 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_expired_and_revoked_invitations_are_rejected() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        expired = client.post(
            "/api/v1/partners/lifecycle/invitations",
            headers=auth_headers(admin),
            json={
                "partner": {"name": "Expired Partner", "slug": f"expired-{uuid4().hex[:8]}"},
                "invitation": {
                    "target_email": "expired@gntv.test",
                    "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                },
            },
        )
        assert expired.status_code == 201, expired.text
        rejected = client.post(
            "/api/v1/partner-portal/invitations/accept",
            json={"token": expired.json()["invitation_reference"]},
        )
        assert rejected.status_code == 403

        pending = invite_partner(client, auth_headers(admin), "revoked@gntv.test")
        revoked = client.post(
            f"/api/v1/partners/{pending['partner_id']}/lifecycle/invitations/{pending['id']}/revoke",
            headers=auth_headers(admin),
        )
        assert revoked.status_code == 200, revoked.text
        rejected_revoked = client.post(
            "/api/v1/partner-portal/invitations/accept",
            json={"token": pending["invitation_reference"]},
        )
        assert rejected_revoked.status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_partner_cannot_approve_or_activate_itself_and_operator_rbac_required() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        viewer = create_user(db, "viewer")
        invitation = invite_partner(client, auth_headers(admin))
        token = str(invitation["invitation_reference"])
        partner_id = str(invitation["partner_id"])
        client.post("/api/v1/partner-portal/invitations/accept", json={"token": token, "user_id": viewer.id})
        forbidden_operator = client.post(
            f"/api/v1/partners/{partner_id}/lifecycle/approve",
            headers=auth_headers(viewer),
            json={"review_notes": "self approval"},
        )
        forbidden_portal = client.post("/api/v1/partner-portal/lifecycle/activate", headers=portal_headers(token))
        assert forbidden_operator.status_code == 403
        assert forbidden_portal.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_onboarding_profile_checklist_approval_and_activation_are_deterministic() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        portal_user = create_user(db, "viewer")
        invitation = invite_partner(client, auth_headers(admin))
        token = str(invitation["invitation_reference"])
        partner_id = str(invitation["partner_id"])
        portal_auth = auth_headers(portal_user)
        client.post("/api/v1/partner-portal/invitations/accept", json={"token": token, "user_id": portal_user.id})
        complete_profile(client, portal_auth)
        status = client.get("/api/v1/partner-portal/onboarding", headers=portal_auth)
        assert status.status_code == 200, status.text
        keys = {item["item_key"]: item["is_complete"] for item in status.json()["checklist"]}
        assert keys["organization_profile_complete"] is True
        submitted = client.post("/api/v1/partner-portal/onboarding/submit", headers=portal_auth)
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["partner"]["lifecycle_status"] == "pending_review"
        approved = client.post(
            f"/api/v1/partners/{partner_id}/lifecycle/approve",
            headers=auth_headers(admin),
            json={"review_notes": "clear"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["partner"]["lifecycle_status"] == "approved"
        activated = client.post(f"/api/v1/partners/{partner_id}/lifecycle/activate", headers=auth_headers(admin))
        activated_again = client.post(f"/api/v1/partners/{partner_id}/lifecycle/activate", headers=auth_headers(admin))
        assert activated.status_code == 200, activated.text
        assert activated_again.status_code == 200, activated_again.text
        assert activated.json()["partner"]["status"] == "active"
        assert db.query(PartnerLifecycleAuditLog).filter_by(partner_id=UUID(partner_id)).count() >= 5
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_invalid_lifecycle_transition_is_rejected() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        invitation = invite_partner(client, auth_headers(admin))
        partner_id = str(invitation["partner_id"])
        response = client.post(f"/api/v1/partners/{partner_id}/lifecycle/activate", headers=auth_headers(admin))
        assert response.status_code == 409
        assert "does not allow" in response.text or "Invalid partner lifecycle transition" in response.text
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_operator_review_fields_and_return_for_changes() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        portal_user = create_user(db, "viewer")
        headers = auth_headers(admin)
        invitation = invite_partner(client, headers)
        token = str(invitation["invitation_reference"])
        partner_id = str(invitation["partner_id"])
        portal_auth = auth_headers(portal_user)
        client.post("/api/v1/partner-portal/invitations/accept", json={"token": token, "user_id": portal_user.id})
        complete_profile(client, portal_auth)
        review = client.patch(
            f"/api/v1/partners/{partner_id}/lifecycle/onboarding",
            headers=headers,
            json={
                "approved_domains": ["player.partner.test"],
                "payout_readiness_status": "configured",
                "review_notes": "Domain reviewed",
            },
        )
        submitted = client.post("/api/v1/partner-portal/onboarding/submit", headers=portal_auth)
        returned = client.post(
            f"/api/v1/partners/{partner_id}/lifecycle/return",
            headers=headers,
            json={"review_notes": "Please verify your technical contact."},
        )
        events = client.get("/api/v1/partner-portal/events", headers=portal_auth)
        assert review.status_code == 200, review.text
        assert review.json()["approved_domains_json"] == ["player.partner.test"]
        assert submitted.status_code == 200, submitted.text
        assert returned.status_code == 200, returned.text
        assert returned.json()["partner"]["lifecycle_status"] == "onboarding"
        assert any(event["event_type"] == "onboarding_returned" for event in events.json())
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_suspension_reactivation_and_termination_preserve_financial_history() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        portal_user = create_user(db, "viewer")
        headers = auth_headers(admin)
        invitation = invite_partner(client, headers)
        token = str(invitation["invitation_reference"])
        partner_id = str(invitation["partner_id"])
        portal_auth = auth_headers(portal_user)
        client.post("/api/v1/partner-portal/invitations/accept", json={"token": token, "user_id": portal_user.id})
        submit_and_approve(client, partner_id, portal_auth, headers)
        activated = client.post(f"/api/v1/partners/{partner_id}/lifecycle/activate", headers=headers)
        assert activated.status_code == 200, activated.text

        agreement = client.post(
            f"/api/v1/partners/{partner_id}/billing/revenue-share-agreements",
            headers=headers,
            json={
                "name": "Lifecycle revshare",
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
                "content_id": "live-news",
                "usage_event_type": "ad_revenue",
                "quantity": 1,
                "gross_revenue_amount": "22.000000",
                "currency": "USD",
                "idempotency_key": f"life-usage-{uuid4().hex}",
                "occurred_at": datetime(2026, 8, 8, tzinfo=UTC).isoformat(),
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
                "idempotency_key": f"life-settlement-{uuid4().hex}",
            },
        )
        assert settlement.status_code == 201, settlement.text

        suspended = client.post(
            f"/api/v1/partners/{partner_id}/lifecycle/suspend",
            headers=headers,
            json={"reason": "policy review"},
        )
        blocked = client.get("/api/v1/partner-portal/overview", headers=portal_auth)
        reactivated = client.post(f"/api/v1/partners/{partner_id}/lifecycle/reactivate", headers=headers)
        terminated = client.post(
            f"/api/v1/partners/{partner_id}/lifecycle/terminate",
            headers=headers,
            json={"reason": "offboarding complete"},
        )
        history = client.get(f"/api/v1/partners/{partner_id}/billing/settlements", headers=headers)
        assert suspended.status_code == 200, suspended.text
        assert blocked.status_code == 403
        assert reactivated.status_code == 200, reactivated.text
        assert terminated.status_code == 200, terminated.text
        assert history.status_code == 200, history.text
        assert history.json()[0]["id"] == settlement.json()["id"]
        assert terminated.json()["partner"]["lifecycle_status"] == "terminated"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_tenant_isolation_and_secret_protection() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)
        first = invite_partner(client, headers, "first@gntv.test")
        second = invite_partner(client, headers, "second@gntv.test")
        token = str(first["invitation_reference"])
        client.post("/api/v1/partner-portal/invitations/accept", json={"token": token})
        key = add_partner_key(db, str(first["partner_id"]))
        me = client.get("/api/v1/partner-portal/me", headers=portal_headers(key))
        other = client.get(
            "/api/v1/partner-portal/overview",
            headers={**auth_headers(admin), "X-Partner-Id": str(second["partner_id"])},
        )
        body = str(me.json())
        assert me.status_code == 200, me.text
        assert me.json()["partner"]["id"] == str(first["partner_id"])
        assert other.status_code == 200, other.text
        assert "secret_hash" not in body
        assert "token_hash" not in body
        assert "encrypted_provider_metadata" not in body
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint710_migration_upgrade_and_downgrade() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    connection = engine.connect()
    context = MigrationContext.configure(connection)
    operations = Operations(context)
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "202609081200_module7_sprint710_partner_onboarding_lifecycle.py"
    )
    spec = importlib.util.spec_from_file_location("sprint710_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    connection.exec_driver_sql(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email VARCHAR(255),
            hashed_password VARCHAR(255),
            is_active BOOLEAN,
            is_verified BOOLEAN
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE partners (
            id CHAR(32) PRIMARY KEY,
            name VARCHAR(160),
            slug VARCHAR(120),
            status VARCHAR(32),
            contact_email VARCHAR(255),
            rate_limit_per_minute INTEGER,
            audit_metadata_json JSON,
            created_by_user_id INTEGER,
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    module.op = operations
    module.upgrade()
    inspector = inspect(connection)
    assert "partner_onboarding_profiles" in inspector.get_table_names()
    assert "partner_invitations" in inspector.get_table_names()
    assert "partner_lifecycle_audit_logs" in inspector.get_table_names()
    module.downgrade()
    inspector = inspect(connection)
    assert "partner_onboarding_profiles" not in inspector.get_table_names()
    connection.close()
