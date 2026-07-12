"""Real-JWT local E2E validation for CMS Module 3."""

from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.main import app
from app.models.audit import AuditLog
from app.repositories.user_repository import UserRepository
from app.utils.security import hash_password


@pytest.fixture()
def e2e() -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    repo = UserRepository(db)
    repo.create_user(
        "catalog-admin@gntv.example",
        hash_password("StrongPass123"),
        is_verified=True,
        default_role="admin",
    )
    repo.create_user(
        "catalog-viewer@gntv.example", hash_password("StrongPass123"), is_verified=True
    )
    db.commit()

    def odb() -> Generator[Session, None, None]:
        yield db
        db.commit()

    app.dependency_overrides[get_db] = odb
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def login(c: TestClient, email: str) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={
            "req": {
                "email": email,
                "password": "StrongPass123",
                "device_name": "Catalog E2E",
            },
            "location": None,
        },
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_real_jwt_catalog_crud_and_personalization(
    e2e: tuple[TestClient, Session],
) -> None:
    c, db = e2e
    admin = login(c, "catalog-admin@gntv.example")
    viewer = login(c, "catalog-viewer@gntv.example")
    genre = c.post(
        "/api/v1/catalog/taxonomies/genre",
        headers=admin,
        json={"name": "Drama", "slug": "e2e-drama"},
    ).json()["id"]
    language = c.post(
        "/api/v1/catalog/taxonomies/language",
        headers=admin,
        json={"name": "Somali", "slug": "e2e-somali", "code": "so"},
    ).json()["id"]
    region = c.post(
        "/api/v1/catalog/taxonomies/region",
        headers=admin,
        json={"name": "Horn", "slug": "e2e-horn", "code": "HOA"},
    ).json()["id"]
    people = {
        role: c.post(
            "/api/v1/catalog/people", headers=admin, json={"name": f"E2E {role}"}
        ).json()["id"]
        for role in ["cast", "crew", "director", "producer"]
    }
    studio = c.post(
        "/api/v1/catalog/studios", headers=admin, json={"name": "E2E Studio"}
    ).json()["id"]

    def create(
        kind: str, slug: str, parent: str | None = None, **extra: object
    ) -> dict[str, object]:
        body = {
            "catalog_type": kind,
            "title": slug.replace("-", " ").title(),
            "slug": slug,
            "parent_id": parent,
            "genre_ids": [genre],
            "language_ids": [language],
            "region_ids": [region],
            "studio_id": studio,
            "seo_title": f"SEO {slug}",
            "seo_description": "Premium catalog",
            "seo_keywords": [kind],
            **extra,
        }
        r = c.post("/api/v1/catalog/items", headers=admin, json=body)
        assert r.status_code == 201, r.text
        return r.json()

    movie = create(
        "movie",
        "e2e-movie",
        status="published",
        credits=[
            {"person_id": pid, "role": role, "position": n}
            for n, (role, pid) in enumerate(people.items())
        ],
    )
    series = create("series", "e2e-series")
    season = create("season", "e2e-season", str(series["id"]), season_number=1)
    episode = create(
        "episode",
        "e2e-episode",
        str(season["id"]),
        episode_number=1,
        duration_seconds=1200,
    )
    for item in [movie, series, season, episode]:
        item_id = str(item["id"])
        assert (
            c.get(f"/api/v1/catalog/items/{item_id}", headers=admin).status_code == 200
        )
        assert (
            c.patch(
                f"/api/v1/catalog/items/{item_id}",
                headers=admin,
                json={"synopsis": "Updated through E2E"},
            ).json()["synopsis"]
            == "Updated through E2E"
        )
    assert (
        c.get(f"/api/v1/catalog/items/{series['id']}", headers=viewer).status_code
        == 404
    )
    assert (
        c.get(
            "/api/v1/catalog/items", headers=viewer, params={"status": "draft"}
        ).json()["total"]
        == 1
    )
    row = c.post(
        "/api/v1/catalog/collections",
        headers=admin,
        json={
            "title": "E2E Featured",
            "slug": "e2e-featured",
            "is_featured": True,
            "item_ids": [movie["id"]],
        },
    ).json()
    row_id = str(row["id"])
    assert c.get("/api/v1/catalog/collections", headers=admin).status_code == 200
    assert (
        c.patch(
            f"/api/v1/catalog/collections/{row_id}",
            headers=admin,
            json={"row_style": "hero"},
        ).json()["row_style"]
        == "hero"
    )
    assert len(c.get("/api/v1/catalog/featured-rows", headers=viewer).json()) == 1
    assert (
        c.put(
            f"/api/v1/catalog/items/{movie['id']}/progress",
            headers=viewer,
            json={"position_seconds": 30, "duration_seconds": 120},
        ).status_code
        == 200
    )
    assert len(c.get("/api/v1/catalog/continue-watching", headers=viewer).json()) == 1
    assert (
        c.put(
            f"/api/v1/catalog/items/{movie['id']}/rating",
            headers=viewer,
            json={"score": 5},
        ).status_code
        == 204
    )
    assert len(c.get("/api/v1/catalog/recommendations", headers=viewer).json()) >= 1
    assert (
        c.post(
            f"/api/v1/catalog/items/{movie['id']}/ai-hooks",
            headers=admin,
            json={"hook": "seo"},
        ).status_code
        == 202
    )
    for item in [episode, season, series]:
        item_id = str(item["id"])
        assert (
            c.delete(f"/api/v1/catalog/items/{item_id}", headers=admin).status_code
            == 204
        )
        assert (
            c.get(f"/api/v1/catalog/items/{item_id}", headers=admin).status_code == 404
        )
        assert (
            c.post(
                f"/api/v1/catalog/items/{item_id}/restore", headers=admin
            ).status_code
            == 204
        )
    assert (
        c.delete(f"/api/v1/catalog/collections/{row_id}", headers=admin).status_code
        == 204
    )
    assert (
        c.post(
            "/api/v1/catalog/items",
            headers=viewer,
            json={"catalog_type": "movie", "title": "No", "slug": "no"},
        ).status_code
        == 403
    )
    assert (
        db.query(AuditLog).filter(AuditLog.event_type.like("catalog.%")).count() >= 15
    )
