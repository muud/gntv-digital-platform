"""Automated verification suite for Sprint 6.6 (Smart TV, Mobile & Accessibility)."""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.modules.streaming.models import UserPlaybackPreference

pytestmark = pytest.mark.anyio


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_user_playback_preferences_defaults(db_session: Session):
    user = User(
        email="test_sprint66@gntv.com",
        hashed_password="hashed_password",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    pref = UserPlaybackPreference(
        user_id=user.id,
        preferred_subtitle_lang="en",
        preferred_audio_lang="sw",
        caption_font_size="large",
        caption_bg_opacity=0.8,
        tv_mode_enabled=True,
    )
    db_session.add(pref)
    db_session.commit()

    saved = db_session.query(UserPlaybackPreference).filter_by(user_id=user.id).first()
    assert saved is not None
    assert saved.preferred_subtitle_lang == "en"
    assert saved.preferred_audio_lang == "sw"
    assert saved.caption_font_size == "large"
    assert saved.caption_bg_opacity == 0.8
    assert saved.tv_mode_enabled is True


def test_playback_preferences_api_routes(client: TestClient, db_session: Session):
    from app.dependencies.auth import get_current_user
    from app.models.user import Role

    user = User(
        email="pref_api@gntv.com",
        hashed_password="hashed_password",
    )
    user.roles.append(Role(name="viewer"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    app.dependency_overrides[get_current_user] = lambda: user

    # GET default preferences
    res_get = client.get("/api/v1/streaming/preferences")
    assert res_get.status_code == 200, res_get.text
    data_get = res_get.json()
    assert data_get["preferred_subtitle_lang"] == "none"
    assert data_get["preferred_audio_lang"] == "default"

    # PUT updated preferences
    payload = {
        "preferred_subtitle_lang": "sw",
        "preferred_audio_lang": "en",
        "caption_font_size": "large",
        "caption_bg_opacity": 0.5,
        "tv_mode_enabled": True,
    }
    res_put = client.put("/api/v1/streaming/preferences", json=payload)
    assert res_put.status_code == 200, res_put.text
    data_put = res_put.json()
    assert data_put["preferred_subtitle_lang"] == "sw"
    assert data_put["preferred_audio_lang"] == "en"
    assert data_put["tv_mode_enabled"] is True


def test_sprint66_alembic_migration_up_down():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "202608091200_module6_sprint66_player_preferences.py"
    )
    spec = importlib.util.spec_from_file_location("migration_module66", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()

    connection.execute(
        text(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255),
                username VARCHAR(100),
                hashed_password VARCHAR(255),
                role VARCHAR(50)
            )
            """
        )
    )

    context = MigrationContext.configure(connection)
    original_op = module.op
    module.op = Operations(context)
    try:
        module.upgrade()
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        assert "user_playback_preferences" in tables

        module.downgrade()
        tables_after = set(inspect(connection).get_table_names())
        assert "user_playback_preferences" not in tables_after
    finally:
        module.op = original_op
        connection.close()
        engine.dispose()
