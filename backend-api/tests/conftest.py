from collections.abc import Generator
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.auth_extra import EmailVerification, FailedLoginAttempt, PasswordReset, RefreshToken
from app.models.user import Device, Permission, Profile, Role, User, UserSession

AUTH_TABLES: list[Table] = [
    cast(Table, User.__table__),
    cast(Table, Profile.__table__),
    cast(Table, Role.__table__),
    cast(Table, Permission.__table__),
    cast(Table, Device.__table__),
    cast(Table, UserSession.__table__),
    cast(Table, EmailVerification.__table__),
    cast(Table, PasswordReset.__table__),
    cast(Table, RefreshToken.__table__),
    cast(Table, FailedLoginAttempt.__table__),
    cast(Table, AuditLog.__table__),
]


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=AUTH_TABLES)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=AUTH_TABLES)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def disable_email_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    class CompletedTask:
        def done(self) -> bool:
            return True

    def close_coroutine(coro: object) -> CompletedTask:
        close = getattr(coro, "close", None)
        if close:
            close()
        return CompletedTask()

    import asyncio

    monkeypatch.setattr(asyncio, "create_task", close_coroutine)
