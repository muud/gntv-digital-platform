import builtins
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from app.modules.catalog.ai import CatalogAIHook
from app.modules.catalog.models import (
    CatalogCollection,
    CatalogCredit,
    CatalogGenre,
    CatalogItem,
    CatalogLanguage,
    CatalogPerson,
    CatalogRating,
    CatalogRegion,
    CatalogStatus,
    CatalogStudio,
    CatalogType,
    ContinueWatching,
)
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.schemas import (
    CatalogItemCreate,
    CatalogItemResponse,
    CatalogItemUpdate,
    CatalogListResponse,
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    CreditInput,
    CreditResponse,
    PersonCreate,
    ProgressResponse,
    ProgressUpdate,
    StudioCreate,
    TaxonomyCreate,
)
from app.repositories.audit_repository import AuditRepository


class CatalogError(RuntimeError):
    pass


class CatalogNotFound(CatalogError):
    pass


class CatalogValidationError(CatalogError):
    pass


class CatalogService:
    def __init__(
        self, repo: CatalogRepository, audit: AuditRepository | None, ai: CatalogAIHook
    ):
        self.repo, self.audit, self.ai = repo, audit, ai

    def create_item(self, p: CatalogItemCreate, actor: int) -> CatalogItemResponse:
        if self.repo.item_by_slug(p.slug):
            raise CatalogValidationError("slug exists")
        self._validate_parent(p.catalog_type, p.parent_id)
        i = CatalogItem(
            **p.model_dump(
                exclude={
                    "genre_ids",
                    "language_ids",
                    "region_ids",
                    "credits",
                    "metadata",
                }
            ),
            metadata_json=p.metadata,
            created_by=actor,
            updated_by=actor,
        )
        self._relations(i, p.genre_ids, p.language_ids, p.region_ids, p.credits)
        self.repo.add(i)
        self._audit(actor, "catalog.item.created", i.id)
        return self.response(i)

    def update_item(
        self, id: UUID, p: CatalogItemUpdate, actor: int
    ) -> CatalogItemResponse:
        i = self._item(id)
        v = p.model_dump(
            exclude_unset=True,
            exclude={"genre_ids", "language_ids", "region_ids", "credits", "metadata"},
        )
        if p.metadata is not None:
            v["metadata_json"] = p.metadata
        for k, x in v.items():
            setattr(i, k, x)
        self._relations(i, p.genre_ids, p.language_ids, p.region_ids, p.credits)
        i.updated_by = actor
        self.repo.add(i)
        self._audit(actor, "catalog.item.updated", i.id)
        return self.response(i)

    def get(self, id: UUID) -> CatalogItemResponse:
        return self.response(self._item(id))

    def list(self, **kw: Any) -> CatalogListResponse:
        x, total = self.repo.list(**kw)
        return CatalogListResponse(
            items=[self.response(i) for i in x],
            total=total,
            limit=kw["limit"],
            offset=kw["offset"],
        )

    def delete(self, id: UUID, actor: int, restore: bool = False) -> None:
        i = self._item(id, include_deleted=restore)
        i.deleted_at = None if restore else datetime.now(UTC)
        i.updated_by = actor
        self.repo.add(i)
        self._audit(
            actor, "catalog.item.restored" if restore else "catalog.item.deleted", id
        )

    def taxonomy(self, kind: str, p: TaxonomyCreate, actor: int) -> dict[str, Any]:
        cls: Any = {
            "genre": CatalogGenre,
            "language": CatalogLanguage,
            "region": CatalogRegion,
        }[kind]
        v = p.model_dump(exclude_none=True)
        obj = cls(**v)
        self.repo.add(obj)
        self._audit(actor, f"catalog.{kind}.created", obj.id)
        return {
            "id": obj.id,
            "name": obj.name,
            "slug": obj.slug,
            **({"code": obj.code} if hasattr(obj, "code") else {}),
        }

    def person(self, p: PersonCreate, actor: int) -> dict[str, Any]:
        o = self.repo.add(CatalogPerson(**p.model_dump()))
        self._audit(actor, "catalog.person.created", o.id)
        return {"id": o.id, "name": o.name}

    def studio(self, p: StudioCreate, actor: int) -> dict[str, Any]:
        o = self.repo.add(CatalogStudio(**p.model_dump()))
        self._audit(actor, "catalog.studio.created", o.id)
        return {"id": o.id, "name": o.name}

    def collection(self, p: CollectionCreate, actor: int) -> CollectionResponse:
        o = CatalogCollection(**p.model_dump(exclude={"item_ids"}))
        o.items = [self._item(x) for x in p.item_ids]
        self.repo.add(o)
        self._audit(actor, "catalog.collection.created", o.id)
        return self.collection_response(o)

    def collections(self) -> builtins.list[CollectionResponse]:
        return [self.collection_response(row) for row in self.repo.collections()]

    def get_collection(self, collection_id: UUID) -> CollectionResponse:
        row = self.repo.collection(collection_id)
        if row is None:
            raise CatalogNotFound(str(collection_id))
        return self.collection_response(row)

    def update_collection(
        self, collection_id: UUID, p: CollectionUpdate, actor: int
    ) -> CollectionResponse:
        row = self.repo.collection(collection_id)
        if row is None:
            raise CatalogNotFound(str(collection_id))
        values = p.model_dump(exclude_unset=True, exclude={"item_ids"})
        for key, value in values.items():
            setattr(row, key, value)
        if p.item_ids is not None:
            row.items = [self._item(item_id) for item_id in p.item_ids]
        self.repo.add(row)
        self._audit(actor, "catalog.collection.updated", row.id)
        return self.collection_response(row)

    def delete_collection(self, collection_id: UUID, actor: int) -> None:
        row = self.repo.collection(collection_id)
        if row is None:
            raise CatalogNotFound(str(collection_id))
        self.repo.db.delete(row)
        self.repo.db.flush()
        self._audit(actor, "catalog.collection.deleted", collection_id)

    def featured(self) -> builtins.list[CollectionResponse]:
        rows = (
            self.repo.db.query(CatalogCollection)
            .filter_by(is_featured=True)
            .order_by(CatalogCollection.position)
            .all()
        )
        return [self.collection_response(x) for x in rows]

    def progress(self, user: int, item_id: UUID, p: ProgressUpdate) -> ProgressResponse:
        i = self._item(item_id)
        row = self.repo.db.query(ContinueWatching).filter_by(
            user_id=user, item_id=item_id
        ).one_or_none() or ContinueWatching(user_id=user, item_id=item_id)
        row.position_seconds = p.position_seconds
        row.duration_seconds = p.duration_seconds
        row.completed = p.completed
        self.repo.add(row)
        return ProgressResponse(
            item=self.response(i),
            position_seconds=row.position_seconds,
            duration_seconds=row.duration_seconds,
            completed=row.completed,
            updated_at=row.updated_at,
        )

    def continue_watching(self, user: int) -> builtins.list[ProgressResponse]:
        rows = (
            self.repo.db.query(ContinueWatching)
            .filter_by(user_id=user, completed=False)
            .order_by(ContinueWatching.updated_at.desc())
            .all()
        )
        return [
            ProgressResponse(
                item=self.response(x.item),
                position_seconds=x.position_seconds,
                duration_seconds=x.duration_seconds,
                completed=x.completed,
                updated_at=x.updated_at,
            )
            for x in rows
        ]

    def rate(self, user: int, item_id: UUID, score: float) -> None:
        self._item(item_id)
        r = self.repo.db.query(CatalogRating).filter_by(
            user_id=user, item_id=item_id
        ).one_or_none() or CatalogRating(user_id=user, item_id=item_id)
        r.score = score
        self.repo.add(r)

    def recommendations(
        self, user: int, limit: int
    ) -> builtins.list[CatalogItemResponse]:
        rated = (
            self.repo.db.query(CatalogRating)
            .filter_by(user_id=user)
            .order_by(CatalogRating.score.desc())
            .all()
        )
        genre_ids = {
            g.id for r in rated if r.score >= 3 for g in self._item(r.item_id).genres
        }
        items, _ = self.repo.list(
            search=None,
            catalog_type=None,
            status=CatalogStatus.PUBLISHED,
            genre_id=next(iter(genre_ids), None),
            language_id=None,
            region_id=None,
            is_kids=None,
            limit=limit,
            offset=0,
        )
        return [self.response(x) for x in items]

    def ai_hook(self, id: UUID, hook: str, actor: int) -> None:
        i = self._item(id)
        i.ai_enrichment_status = "queued"
        i.ai_metadata = {**i.ai_metadata, "last_hook": hook}
        self.repo.add(i)
        self.ai.dispatch(id, hook)
        self._audit(actor, "catalog.ai.queued", id)

    def response(self, i: CatalogItem) -> CatalogItemResponse:
        return CatalogItemResponse(
            id=i.id,
            catalog_type=i.catalog_type,
            status=i.status,
            title=i.title,
            slug=i.slug,
            synopsis=i.synopsis,
            parent_id=i.parent_id,
            season_number=i.season_number,
            episode_number=i.episode_number,
            duration_seconds=i.duration_seconds,
            release_date=i.release_date,
            is_premium=i.is_premium,
            is_kids=i.is_kids,
            age_rating=i.age_rating,
            stream_url=i.stream_url,
            media_asset_id=i.media_asset_id,
            poster_asset_id=i.poster_asset_id,
            studio_id=i.studio_id,
            genre_ids=[x.id for x in i.genres],
            language_ids=[x.id for x in i.languages],
            region_ids=[x.id for x in i.regions],
            credits=[
                CreditResponse(
                    person_id=x.person_id,
                    person_name=x.person.name,
                    role=x.role,
                    character_name=x.character_name,
                    position=x.position,
                )
                for x in i.credits
            ],
            seo={
                "title": i.seo_title,
                "description": i.seo_description,
                "keywords": i.seo_keywords,
            },
            ai_metadata=i.ai_metadata,
            ai_enrichment_status=i.ai_enrichment_status,
            metadata=i.metadata_json,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )

    def collection_response(self, o: CatalogCollection) -> CollectionResponse:
        return CollectionResponse(
            id=o.id,
            title=o.title,
            slug=o.slug,
            description=o.description,
            is_featured=o.is_featured,
            row_style=o.row_style,
            position=o.position,
            items=[self.response(x) for x in o.items],
        )

    def _item(self, id: UUID, include_deleted: bool = False) -> CatalogItem:
        x = self.repo.item(id)
        if not x or (x.deleted_at is not None and not include_deleted):
            raise CatalogNotFound(str(id))
        return x

    def _validate_parent(self, t: CatalogType, parent: UUID | None) -> None:
        expected = {
            CatalogType.SEASON: CatalogType.SERIES,
            CatalogType.EPISODE: CatalogType.SEASON,
        }
        if t in expected and (
            parent is None or self._item(parent).catalog_type != expected[t]
        ):
            raise CatalogValidationError("invalid hierarchy")

    def _relations(
        self,
        i: CatalogItem,
        g: builtins.list[UUID] | None,
        languages: builtins.list[UUID] | None,
        r: builtins.list[UUID] | None,
        c: builtins.list[CreditInput] | None,
    ) -> None:
        if g is not None:
            i.genres = [self.repo.taxonomy("genre", x) or self._bad() for x in g]
        if languages is not None:
            i.languages = [
                self.repo.taxonomy("language", x) or self._bad() for x in languages
            ]
        if r is not None:
            i.regions = [self.repo.taxonomy("region", x) or self._bad() for x in r]
        if c is not None:
            i.credits = [CatalogCredit(**x.model_dump()) for x in c]

    def _bad(self) -> Any:
        raise CatalogValidationError("reference not found")

    def _audit(self, user: int, event: str, id: UUID) -> None:
        if self.audit:
            self.audit.create(user, event, {"catalog_id": str(id)})
