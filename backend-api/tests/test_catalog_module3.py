from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.modules.catalog.models import CatalogItem


@pytest.fixture()
def catalog_client() -> Generator[tuple[TestClient, Session], None, None]:
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(e)
    db = sessionmaker(bind=e)()
    u = User(
        email="catalog@gntv.example",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    u.roles = [Role(name="admin")]
    db.add(u)
    db.commit()
    db.refresh(u)

    def odb() -> Generator[Session, None, None]:
        yield db
        db.commit()

    app.dependency_overrides[get_db] = odb
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(e)
        e.dispose()


def test_complete_premium_catalog_engine(
    catalog_client: tuple[TestClient, Session],
) -> None:
    c, db = catalog_client
    genre = c.post(
        "/api/v1/catalog/taxonomies/genre", json={"name": "Drama", "slug": "drama"}
    ).json()["id"]
    language = c.post(
        "/api/v1/catalog/taxonomies/language",
        json={"name": "English", "slug": "english", "code": "en"},
    ).json()["id"]
    region = c.post(
        "/api/v1/catalog/taxonomies/region",
        json={"name": "East Africa", "slug": "east-africa", "code": "EA"},
    ).json()["id"]
    person = c.post("/api/v1/catalog/people", json={"name": "Amina Noor"}).json()["id"]
    studio = c.post("/api/v1/catalog/studios", json={"name": "GNTV Studios"}).json()[
        "id"
    ]
    ids: dict[str, str] = {}
    for kind in ["movie", "live_tv", "radio", "podcast", "short", "kids", "news"]:
        payload = {
            "catalog_type": kind,
            "title": kind.replace("_", " ").title(),
            "slug": f"module3-{kind.replace('_', '-')}",
            "status": "published",
            "genre_ids": [genre],
            "language_ids": [language],
            "region_ids": [region],
            "studio_id": studio,
            "seo_title": f"GNTV {kind}",
            "seo_keywords": [kind],
            "metadata": {"quality": "premium"},
        }
        if kind == "movie":
            payload["credits"] = [
                {"person_id": person, "role": "director", "position": 0},
                {
                    "person_id": person,
                    "role": "cast",
                    "character_name": "Host",
                    "position": 1,
                },
            ]
        r = c.post("/api/v1/catalog/items", json=payload)
        assert r.status_code == 201, r.text
        ids[kind] = r.json()["id"]
    series = c.post(
        "/api/v1/catalog/items",
        json={
            "catalog_type": "series",
            "title": "Horn Stories",
            "slug": "horn-stories",
        },
    ).json()
    ids["series"] = series["id"]
    season = c.post(
        "/api/v1/catalog/items",
        json={
            "catalog_type": "season",
            "title": "Season 1",
            "slug": "horn-stories-s1",
            "parent_id": series["id"],
            "season_number": 1,
        },
    ).json()
    ids["season"] = season["id"]
    episode = c.post(
        "/api/v1/catalog/items",
        json={
            "catalog_type": "episode",
            "title": "Episode 1",
            "slug": "horn-stories-s1e1",
            "parent_id": season["id"],
            "episode_number": 1,
            "duration_seconds": 1800,
        },
    ).json()
    ids["episode"] = episode["id"]
    assert (
        c.post(
            "/api/v1/catalog/items",
            json={"catalog_type": "episode", "title": "Bad", "slug": "bad-parent"},
        ).status_code
        == 400
    )
    listing = c.get(
        "/api/v1/catalog/items",
        params={
            "search": "Movie",
            "catalog_type": "movie",
            "genre_id": genre,
            "language_id": language,
            "region_id": region,
            "limit": 1,
            "offset": 0,
        },
    )
    assert listing.status_code == 200 and listing.json()["total"] == 1
    updated = c.patch(
        f"/api/v1/catalog/items/{ids['movie']}",
        json={"synopsis": "Premium film", "is_premium": True, "age_rating": "PG-13"},
    )
    assert (
        updated.json()["seo"]["title"] == "GNTV movie"
        and updated.json()["credits"][0]["person_name"] == "Amina Noor"
    )
    row = c.post(
        "/api/v1/catalog/collections",
        json={
            "title": "Featured",
            "slug": "featured",
            "is_featured": True,
            "row_style": "hero",
            "item_ids": [ids["movie"], ids["series"]],
        },
    )
    assert row.status_code == 201 and len(row.json()["items"]) == 2
    assert len(c.get("/api/v1/catalog/featured-rows").json()) == 1
    progress = c.put(
        f"/api/v1/catalog/items/{ids['movie']}/progress",
        json={"position_seconds": 120, "duration_seconds": 7200},
    )
    assert progress.json()["position_seconds"] == 120
    assert len(c.get("/api/v1/catalog/continue-watching").json()) == 1
    assert (
        c.put(
            f"/api/v1/catalog/items/{ids['movie']}/rating", json={"score": 5}
        ).status_code
        == 204
    )
    assert len(c.get("/api/v1/catalog/recommendations").json()) >= 1
    assert (
        c.post(
            f"/api/v1/catalog/items/{ids['movie']}/ai-hooks", json={"hook": "seo"}
        ).status_code
        == 202
    )
    assert c.delete(f"/api/v1/catalog/items/{ids['movie']}").status_code == 204
    assert c.post(f"/api/v1/catalog/items/{ids['movie']}/restore").status_code == 204
    assert db.query(CatalogItem).count() == 10
    assert (
        db.query(AuditLog).filter(AuditLog.event_type.like("catalog.%")).count() >= 10
    )


def test_catalog_rbac_and_openapi(catalog_client: tuple[TestClient, Session]) -> None:
    c, _ = catalog_client
    viewer = User(email="v@gntv.example", hashed_password="x", is_verified=True)
    viewer.roles = [Role(name="viewer")]
    app.dependency_overrides[get_current_user] = lambda: viewer
    assert (
        c.post(
            "/api/v1/catalog/items",
            json={"catalog_type": "movie", "title": "X", "slug": "x"},
        ).status_code
        == 403
    )
    assert c.get("/api/v1/catalog/items").status_code == 200
    schema = c.get("/openapi.json").json()
    assert "/api/v1/catalog/recommendations" in schema["paths"]
