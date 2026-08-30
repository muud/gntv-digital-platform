from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from app.modules.partners.models import PartnerEmbedEvent, PartnerEmbedEventType, PartnerStatus
from app.modules.partners.repository import PartnerRepository
from app.modules.partners.service import PartnerSecurityError, PartnerSyndicationService
from app.utils.jwt import create_access_token


def make_db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    return testing_session()


def make_client(db: Session) -> TestClient:
    def override_get_db():
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


def create_partner_bundle(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/partners",
        headers=headers,
        json={
            "name": "Horn Africa Public Media",
            "slug": f"horn-africa-{uuid4().hex[:8]}",
            "status": "active",
            "branding": {
                "display_name": "Horn Africa Media",
                "accent_color": "#ff8a00",
                "show_gntv_attribution": True,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def grant_domain_and_entitlement(
    client: TestClient,
    partner_id: str,
    headers: dict[str, str],
    domain_pattern: str = "*.partner.test",
    content_id: str = "live-news",
) -> None:
    domain = client.post(
        f"/api/v1/partners/{partner_id}/domains",
        headers=headers,
        json={"domain_pattern": domain_pattern},
    )
    assert domain.status_code == 201, domain.text
    entitlement = client.post(
        f"/api/v1/partners/{partner_id}/entitlements",
        headers=headers,
        json={"content_type": "live_channel", "content_id": content_id, "scopes": ["embed:play"]},
    )
    assert entitlement.status_code == 201, entitlement.text


def issue_token(
    client: TestClient,
    partner_id: str,
    headers: dict[str, str],
    domain: str = "player.partner.test",
    content_id: str = "live-news",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/partners/{partner_id}/embed-token",
        headers=headers,
        json={
            "content_type": "live_channel",
            "content_id": content_id,
            "domain": domain,
            "viewer_session_id": "viewer-123",
            "playback_session_id": "playback-123",
            "scopes": ["embed:play"],
            "ttl_seconds": 300,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_sprint76_partner_creation_requires_admin_and_hides_api_secret() -> None:
    db = make_db()
    client = make_client(db)
    try:
        viewer = create_user(db, "viewer")
        admin = create_user(db, "admin")
        forbidden = client.post(
            "/api/v1/partners",
            headers=auth_headers(viewer),
            json={"name": "Blocked Partner", "slug": "blocked-partner", "status": "active"},
        )
        created = create_partner_bundle(client, auth_headers(admin))
        response_text = str(created)
        assert forbidden.status_code == 403
        assert created["partner"]["status"] == PartnerStatus.ACTIVE
        assert "secret_hash" not in response_text
        assert "token_urlsafe" not in response_text
        assert created["credential"]["key_prefix"]
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint76_domain_wildcard_token_and_embed_authorization() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)
        partner_id = create_partner_bundle(client, headers)["partner"]["id"]
        grant_domain_and_entitlement(client, partner_id, headers)
        token_response = issue_token(client, partner_id, headers)
        allowed = client.get(
            "/api/v1/embed/authorize",
            params={"token": token_response["token"], "domain": "player.partner.test"},
        )
        denied = client.get(
            "/api/v1/embed/authorize",
            params={"token": token_response["token"], "domain": "partner.test"},
        )
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["branding"]["display_name"] == "Horn Africa Media"
        assert "embed_token=" in allowed.json()["playback_url"]
        assert denied.status_code == 403
        assert db.query(PartnerEmbedEvent).filter_by(event_type=PartnerEmbedEventType.AUTHORIZE).count() == 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint76_token_expiry_and_invalid_signature_rejected() -> None:
    db = make_db()
    try:
        service = PartnerSyndicationService(PartnerRepository(db), signing_secret="test-sprint76-signing-secret")
        expired_token = service._sign_payload(
            {
                "pid": str(uuid4()),
                "cty": "live_channel",
                "cid": "live-news",
                "dom": "player.partner.test",
                "iat": int((datetime.now(UTC) - timedelta(minutes=10)).timestamp()),
                "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
                "scp": ["embed:play"],
            }
        )
        tampered = f"{expired_token[:-1]}x"
        try:
            service.verify_token(expired_token)
        except PartnerSecurityError as exc:
            assert "expired" in str(exc)
        else:
            raise AssertionError("expired token was accepted")
        try:
            service.verify_token(tampered)
        except PartnerSecurityError as exc:
            assert "signature" in str(exc)
        else:
            raise AssertionError("tampered token was accepted")
    finally:
        db.close()


def test_sprint76_cross_partner_entitlement_denial_and_allowed_content() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)
        partner_a = create_partner_bundle(client, headers)["partner"]["id"]
        partner_b = client.post(
            "/api/v1/partners",
            headers=headers,
            json={"name": "Other Partner", "slug": f"other-{uuid4().hex[:8]}", "status": "active"},
        ).json()["partner"]["id"]
        grant_domain_and_entitlement(client, partner_a, headers, content_id="channel-a")
        client.post(
            f"/api/v1/partners/{partner_b}/domains",
            headers=headers,
            json={"domain_pattern": "*.partner.test"},
        )
        denied = client.post(
            f"/api/v1/partners/{partner_b}/embed-token",
            headers=headers,
            json={
                "content_type": "live_channel",
                "content_id": "channel-a",
                "domain": "player.partner.test",
                "scopes": ["embed:play"],
            },
        )
        allowed = issue_token(client, partner_a, headers, content_id="channel-a")
        assert denied.status_code == 403
        assert allowed["content_id"] == "channel-a"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint76_embed_events_are_attributed_to_partner_analytics() -> None:
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "operator")
        headers = auth_headers(admin)
        partner_id = create_partner_bundle(client, headers)["partner"]["id"]
        grant_domain_and_entitlement(client, partner_id, headers)
        token = issue_token(client, partner_id, headers)["token"]
        event = client.post(
            "/api/v1/embed/events",
            json={
                "token": token,
                "event_type": "playback_start",
                "domain": "player.partner.test",
                "playback_session_id": "session-abc",
            },
        )
        analytics = client.get("/api/v1/partners/analytics/overview", headers=headers)
        assert event.status_code == 201, event.text
        assert event.json()["partner_id"] == partner_id
        assert analytics.json()["playback_start_count"] == 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint76_embed_sdk_and_studio_integration_are_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sdk_source = (repo_root / "shared/src/embed/gntv-embed-sdk.js").read_text()
    studio = (repo_root / "frontend-studio/src/components/StudioDashboard.js").read_text()
    dashboard = (repo_root / "frontend-studio/src/components/PartnerSyndicationDashboard.js").read_text()
    assert "window.GNTV.embed" in sdk_source
    assert "partner-syndication" in studio
    assert "/api/v1/partners" in dashboard


def test_sprint76_embed_sdk_route_serves_browser_javascript() -> None:
    db = make_db()
    client = make_client(db)
    try:
        response = client.get("/api/v1/embed/sdk.js")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/javascript")
        assert "GNTV.embed" in response.text
        assert "apiBaseUrl" in response.text
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint76_migration_upgrade_and_downgrade() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    migration_path = repo_root / "backend-api/alembic/versions/202608221200_module7_sprint76_partner_syndication.py"
    spec = importlib.util.spec_from_file_location("sprint76_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert {
            "partners",
            "partner_domains",
            "partner_entitlements",
            "partner_api_credentials",
            "partner_branding",
            "partner_embed_events",
        }.issubset(tables)
        migration.downgrade()
        tables_after = set(inspect(connection).get_table_names())
        assert "partners" not in tables_after
