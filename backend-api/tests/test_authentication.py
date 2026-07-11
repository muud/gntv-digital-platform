from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.services.auth_service as auth_service_module
from app.dependencies.auth import get_current_user, require_permission, require_role
from app.models.audit import AuditLog
from app.models.auth_extra import EmailVerification, PasswordReset, RefreshToken
from app.models.user import Device, Session as UserSession
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.services.auth_service import AuthService, _hash_token
from app.utils.jwt import create_access_token, decode_token
from app.utils.security import hash_password


def register_verified_user(db: Session, email: str = "viewer@example.com") -> int:
    repo = UserRepository(db)
    user = repo.create_user(
        email=email,
        hashed_password=hash_password("StrongPass123"),
        is_active=True,
        is_verified=True,
    )
    user.name = "GNTV Viewer"
    db.flush()
    return user.id


def login_request(email: str = "viewer@example.com") -> LoginRequest:
    return LoginRequest(
        email=email,
        password="StrongPass123",
        device_name="Studio Laptop",
        platform="macOS",
        browser="Safari",
    )


def test_register_creates_user_verification_and_audit(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_service_module, "_generate_token", lambda: "verify-token")
    result = AuthService(db_session).register(
        RegisterRequest(email="new@example.com", password="StrongPass123", name="New User")
    )

    user = UserRepository(db_session).get_by_email("new@example.com")
    assert result["detail"].startswith("Registration successful")
    assert user is not None
    assert user.is_verified is False
    assert db_session.query(EmailVerification).filter_by(user_id=user.id).one().token_hash == _hash_token("verify-token")
    assert db_session.query(AuditLog).filter_by(user_id=user.id, event_type="register").count() == 1


def test_email_verification_marks_user_verified_and_audits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_service_module, "_generate_token", lambda: "verify-token")
    service = AuthService(db_session)
    service.register(RegisterRequest(email="verify@example.com", password="StrongPass123", name=None))

    response = service.verify_email("verify-token")
    user = UserRepository(db_session).get_by_email("verify@example.com")

    assert response.detail == "Email verified successfully"
    assert user is not None
    assert user.is_verified is True
    assert db_session.query(EmailVerification).count() == 0
    assert db_session.query(AuditLog).filter_by(user_id=user.id, event_type="email_verified").count() == 1


def test_login_refresh_logout_and_session_revocation(db_session: Session) -> None:
    user_id = register_verified_user(db_session)
    service = AuthService(db_session)

    token_response = service.login(login_request(), "127.0.0.1", "pytest", {"country": "KE", "city": "Nairobi"})
    refresh_row = db_session.query(RefreshToken).filter_by(user_id=user_id).one()
    session_row = db_session.query(UserSession).filter_by(user_id=user_id).one()

    assert decode_token(token_response.access_token)["sub"] == str(user_id)
    assert refresh_row.revoked is False
    assert session_row.revoked is False
    assert db_session.query(Device).filter_by(user_id=user_id).count() == 1
    assert db_session.query(AuditLog).filter_by(user_id=user_id, event_type="login_success").count() == 1

    rotated = service.refresh(RefreshRequest(refresh_token=token_response.refresh_token))
    assert rotated.refresh_token != token_response.refresh_token
    assert refresh_row.revoked is True
    assert db_session.query(AuditLog).filter_by(user_id=user_id, event_type="token_refreshed").count() == 1

    service.logout(rotated.refresh_token)
    assert db_session.query(RefreshToken).filter_by(token_hash=_hash_token(rotated.refresh_token)).one().revoked is True
    assert session_row.revoked is True
    assert db_session.query(AuditLog).filter_by(user_id=user_id, event_type="logout").count() == 1


def test_logout_all_revokes_all_sessions_and_tokens(db_session: Session) -> None:
    user_id = register_verified_user(db_session)
    service = AuthService(db_session)
    service.login(login_request(), "127.0.0.1", "pytest")

    service.logout_all(user_id)

    assert all(token.revoked for token in db_session.query(RefreshToken).filter_by(user_id=user_id).all())
    assert all(session.revoked for session in db_session.query(UserSession).filter_by(user_id=user_id).all())
    assert db_session.query(AuditLog).filter_by(user_id=user_id, event_type="logout_all").count() == 1


def test_password_reset_request_and_confirm(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = register_verified_user(db_session)
    monkeypatch.setattr(auth_service_module, "_generate_token", lambda: "reset-token")
    service = AuthService(db_session)

    service.password_reset_request(PasswordResetRequest(email="viewer@example.com"))
    reset = db_session.query(PasswordReset).filter_by(user_id=user_id).one()

    assert reset.token_hash == _hash_token("reset-token")
    service.password_reset_confirm(PasswordResetConfirm(token="reset-token", new_password="BetterPass123"))
    assert reset.used is True
    assert db_session.query(AuditLog).filter_by(user_id=user_id, event_type="password_reset").count() == 1


def test_device_management_lists_and_revokes_device(db_session: Session) -> None:
    user_id = register_verified_user(db_session)
    service = AuthService(db_session)
    service.login(login_request(), "127.0.0.1", "pytest")
    device = db_session.query(Device).filter_by(user_id=user_id).one()

    devices = service.list_devices(user_id)
    service.revoke_device(user_id, device.id)

    assert devices[0].device_name == "Studio Laptop"
    assert device.is_deleted is True
    assert db_session.query(RefreshToken).filter_by(device_id=device.id).one().revoked is True
    assert db_session.query(UserSession).filter_by(device_id=device.id).one().revoked is True


def test_rbac_permissions_and_jwt_dependency(db_session: Session) -> None:
    user_id = register_verified_user(db_session)
    token = create_access_token(subject=str(user_id), additional_claims={"email": "viewer@example.com"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    current_user = get_current_user(credentials=credentials, db=db_session)
    assert current_user.id == user_id
    assert require_permission("read")(user=current_user).id == user_id

    with pytest.raises(HTTPException) as role_error:
        require_role("admin")(user=current_user)
    assert role_error.value.status_code == 403

    with pytest.raises(HTTPException) as permission_error:
        require_permission("delete")(user=current_user)
    assert permission_error.value.status_code == 403


def test_auth_api_routes_cover_full_flow(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated_tokens = iter(["verify-token", "login-refresh", "rotated-refresh", "reset-token"])
    monkeypatch.setattr(auth_service_module, "_generate_token", lambda: next(generated_tokens))

    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "api@example.com", "password": "StrongPass123", "name": "API User"},
    )
    assert register_response.status_code == 200

    verify_response = client.get("/api/v1/auth/verify-email", params={"token": "verify-token"})
    assert verify_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "req": {
                "email": "api@example.com",
                "password": "StrongPass123",
                "device_name": "Browser",
                "platform": "web",
                "browser": "Firefox",
            },
            "location": None,
        },
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.patch("/api/v1/auth/me", headers=headers, params={"name": "Updated API"}).status_code == 200
    devices_response = client.get("/api/v1/auth/devices", headers=headers)
    assert devices_response.status_code == 200
    device_id = devices_response.json()[0]["id"]

    refresh_response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 200
    rotated_refresh = refresh_response.json()["refresh_token"]

    reset_response = client.post("/api/v1/auth/password-reset-request", json={"email": "api@example.com"})
    assert reset_response.status_code == 202
    reset_confirm = client.post(
        "/api/v1/auth/password-reset-confirm",
        json={"token": "reset-token", "new_password": "EvenBetter123"},
    )
    assert reset_confirm.status_code == 200

    assert client.delete(f"/api/v1/auth/devices/{device_id}", headers=headers).status_code == 204
    assert client.post("/api/v1/auth/logout", params={"refresh_token": rotated_refresh}).status_code == 400
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 204

    user = UserRepository(db_session).get_by_email("api@example.com")
    assert user is not None
    assert db_session.query(AuditLog).filter_by(user_id=user.id).count() >= 5


def test_auth_api_error_routes(client: TestClient, db_session: Session) -> None:
    user_id = register_verified_user(db_session, "route-errors@example.com")
    db_session.commit()
    token = create_access_token(subject=str(user_id), additional_claims={"email": "route-errors@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "route-errors@example.com", "password": "StrongPass123"},
    )
    assert duplicate.status_code == 400

    assert client.get("/api/v1/auth/verify-email", params={"token": "missing"}).status_code == 400
    bad_login = client.post(
        "/api/v1/auth/login",
        json={
            "req": {
                "email": "route-errors@example.com",
                "password": "WrongPass123",
                "device_name": "Browser",
            },
            "location": None,
        },
    )
    assert bad_login.status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "missing"}).status_code == 401
    assert client.post("/api/v1/auth/logout", params={"refresh_token": "missing"}).status_code == 400
    reset_confirm = client.post(
        "/api/v1/auth/password-reset-confirm",
        json={"token": "missing", "new_password": "EvenBetter123"},
    )
    assert reset_confirm.status_code == 400
    assert client.delete("/api/v1/auth/devices/999", headers=headers).status_code == 404


def test_auth_error_paths(db_session: Session) -> None:
    service = AuthService(db_session)

    with pytest.raises(ValueError):
        service.login(login_request("missing@example.com"), "127.0.0.1", "pytest")

    with pytest.raises(ValueError):
        service.verify_email("missing-token")

    with pytest.raises(ValueError):
        service.refresh(RefreshRequest(refresh_token="missing-token"))

    with pytest.raises(ValueError):
        service.logout("missing-token")

    register_verified_user(db_session)
    with pytest.raises(ValueError):
        service.revoke_device(1, 999)


def test_get_current_user_rejects_missing_and_unverified(db_session: Session) -> None:
    with pytest.raises(HTTPException) as missing_error:
        get_current_user(credentials=None, db=db_session)  # type: ignore[arg-type]
    assert missing_error.value.status_code == 401

    repo = UserRepository(db_session)
    user = repo.create_user(
        email="unverified@example.com",
        hashed_password=hash_password("StrongPass123"),
        is_active=True,
        is_verified=False,
    )
    db_session.flush()
    token = create_access_token(subject=str(user.id))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as unverified_error:
        get_current_user(credentials=credentials, db=db_session)
    assert unverified_error.value.status_code == 403


def test_get_current_user_rejects_invalid_missing_disabled_and_session(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")
    with pytest.raises(HTTPException) as invalid_error:
        get_current_user(credentials=bad_credentials, db=db_session)
    assert invalid_error.value.status_code == 401

    monkeypatch.setattr("app.dependencies.auth.decode_token", lambda token: {})
    with pytest.raises(HTTPException) as missing_subject_error:
        get_current_user(credentials=bad_credentials, db=db_session)
    assert missing_subject_error.value.status_code == 401

    monkeypatch.setattr("app.dependencies.auth.decode_token", lambda token: {"sub": "999"})
    with pytest.raises(HTTPException) as missing_user_error:
        get_current_user(credentials=bad_credentials, db=db_session)
    assert missing_user_error.value.status_code == 401

    user_id = register_verified_user(db_session, "disabled@example.com")
    user = UserRepository(db_session).get_by_id(user_id)
    assert user is not None
    user.is_active = False
    db_session.flush()
    monkeypatch.setattr("app.dependencies.auth.decode_token", lambda token: {"sub": str(user_id)})
    with pytest.raises(HTTPException) as disabled_error:
        get_current_user(credentials=bad_credentials, db=db_session)
    assert disabled_error.value.status_code == 403

    user.is_active = True
    db_session.flush()
    monkeypatch.setattr("app.dependencies.auth.decode_token", lambda token: {"sub": str(user_id), "jti": "999"})
    with pytest.raises(HTTPException) as session_error:
        get_current_user(credentials=bad_credentials, db=db_session)
    assert session_error.value.status_code == 403

    assert require_role("viewer")(user=user).id == user_id


def test_locked_account_and_expired_reset_paths(db_session: Session) -> None:
    user_id = register_verified_user(db_session)
    repo = UserRepository(db_session)
    for _ in range(auth_service_module.LOCKOUT_ATTEMPTS):
        repo.record_failed_login(user_id, "127.0.0.1")

    with pytest.raises(ValueError):
        AuthService(db_session).login(login_request(), "127.0.0.1", "pytest")

    db_session.add(
        PasswordReset(
            user_id=user_id,
            token_hash=_hash_token("expired"),
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    db_session.flush()
    with pytest.raises(ValueError):
        AuthService(db_session).password_reset_confirm(
            PasswordResetConfirm(token="expired", new_password="BetterPass123")
        )
