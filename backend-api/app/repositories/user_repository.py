# repositories/user_repository.py
"""User repository handling CRUD for authentication related entities."""

from sqlalchemy.orm import Session
from typing import Any, Optional
from datetime import datetime, timedelta

from app.models.user import Device, Permission, Role, User, Session as UserSession
from app.models.auth_extra import EmailVerification, FailedLoginAttempt, PasswordReset, RefreshToken


class UserRepository:
    def __init__(self, db: Session):
        self.db = db
    def get_by_id(self, user_id: int) -> Optional[User]:
        """Fetch a User by its primary key.

        Returns ``None`` if no user with the given ID exists.
        """
        return self.db.query(User).filter(User.id == user_id).first()
    # ---------------------------------------------------------------------
    # User CRUD
    # ---------------------------------------------------------------------
    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def create_user(
        self,
        email: str,
        hashed_password: str,
        is_active: bool = True,
        is_verified: bool = False,
        default_role: str = "viewer",
    ) -> User:
        user = User(email=email, hashed_password=hashed_password, is_active=is_active, is_verified=is_verified)
        user.roles.append(self._get_or_create_role(default_role, permissions=("read", "content:read", "asset:read")))
        self.db.add(user)
        self.db.flush()  # obtain ID without committing
        return user

    def _get_or_create_role(self, name: str, permissions: tuple[str, ...] = ()) -> Role:
        role = self.db.query(Role).filter(Role.name == name).first()
        if role is None:
            role = Role(name=name, description=f"Default {name} role")
            self.db.add(role)
            self.db.flush()
        for permission_name in permissions:
            permission = self.db.query(Permission).filter(Permission.name == permission_name).first()
            if permission is None:
                permission = Permission(name=permission_name, description=f"{permission_name} permission")
                self.db.add(permission)
                self.db.flush()
            if permission not in role.permissions:
                role.permissions.append(permission)
        return role

    # ---------------------------------------------------------------------
    # Email verification
    # ---------------------------------------------------------------------
    def create_email_verification(self, user_id: int, token_hash: str, expires_at: datetime) -> EmailVerification:
        ev = EmailVerification(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(ev)
        self.db.flush()
        return ev

    def get_email_verification(self, token_hash: str) -> Optional[EmailVerification]:
        return (
            self.db.query(EmailVerification)
            .filter(EmailVerification.token_hash == token_hash, EmailVerification.expires_at > datetime.utcnow())
            .first()
        )

    # ---------------------------------------------------------------------
    # Password reset
    # ---------------------------------------------------------------------
    def create_password_reset(self, user_id: int, token_hash: str, expires_at: datetime) -> PasswordReset:
        prt = PasswordReset(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(prt)
        self.db.flush()
        return prt

    def get_password_reset(self, token_hash: str) -> Optional[PasswordReset]:
        return (
            self.db.query(PasswordReset)
            .filter(PasswordReset.token_hash == token_hash, PasswordReset.expires_at > datetime.utcnow(), PasswordReset.used == False)  # noqa: E712
            .first()
        )

    # ---------------------------------------------------------------------
    # Refresh token handling
    # ---------------------------------------------------------------------
    def create_refresh_token(self, user_id: int, device_id: Optional[int], token_hash: str, expires_at: datetime) -> RefreshToken:
        rt = RefreshToken(user_id=user_id, device_id=device_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(rt)
        self.db.flush()
        return rt

    def get_refresh_token(self, token_hash: str) -> Optional[RefreshToken]:
        return (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash, RefreshToken.expires_at > datetime.utcnow(), RefreshToken.revoked == False)  # noqa: E712
            .first()
        )

    def revoke_refresh_token(self, token: RefreshToken) -> None:
        token.revoked = True
        self.db.add(token)

    # ---------------------------------------------------------------------
    # Device handling
    # ---------------------------------------------------------------------
    def get_user_devices(self, user_id: int) -> list[Device]:
        return self.db.query(Device).filter(Device.user_id == user_id, ~Device.is_deleted).all()

    def create_device(self, user_id: int, device_name: str, platform: str | None = None, browser: str | None = None, ip_address: str | None = None) -> Device:
        dev = Device(
            user_id=user_id,
            device_name=device_name,
            platform=platform,
            browser=browser,
            ip_address=ip_address,
        )
        self.db.add(dev)
        self.db.flush()
        return dev

    def revoke_device(self, device: Device) -> None:
        device.is_deleted = True
        self.db.add(device)

    # ---------------------------------------------------------------------
    # Session handling
    # ---------------------------------------------------------------------
    def create_session(
        self,
        user_id: int,
        device_id: Optional[int],
        device_name: str | None,
        platform: str | None,
        browser: str | None,
        ip_address: str | None,
        country: str | None,
        city: str | None,
        expires_at: datetime,
    ) -> UserSession:
        sess = UserSession(
            user_id=user_id,
            device_id=device_id,
            device_name=device_name,
            platform=platform,
            browser=browser,
            ip_address=ip_address,
            country=country,
            city=city,
            expires_at=expires_at,
        )
        self.db.add(sess)
        self.db.flush()
        return sess

    def revoke_session(self, session: UserSession) -> None:
        session.revoked = True
        self.db.add(session)

    # ---------------------------------------------------------------------
    # Failed login attempts
    # ---------------------------------------------------------------------
    def record_failed_login(self, user_id: int, ip_address: str | None = None) -> FailedLoginAttempt:
        attempt = FailedLoginAttempt(user_id=user_id, ip_address=ip_address)
        self.db.add(attempt)
        self.db.flush()
        return attempt

    def recent_failed_attempts(self, user_id: int, within_minutes: int = 30) -> int:
        cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)
        return (
            self.db.query(FailedLoginAttempt)
            .filter(FailedLoginAttempt.user_id == user_id, FailedLoginAttempt.attempt_time >= cutoff)
            .count()
        )

    # ---------------------------------------------------------------------
    # Audit log – placeholder (implementation can be extended later)
    # ---------------------------------------------------------------------
    def log_event(self, user_id: int, event: str, details: dict[str, Any] | None = None) -> None:
        # For now we just print – in production replace with proper table write.
        print(f"[AUDIT] user={user_id} event={event} details={details}")
