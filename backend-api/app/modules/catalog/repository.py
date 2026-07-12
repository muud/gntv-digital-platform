from collections.abc import Sequence
from typing import Any
from uuid import UUID
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload
from app.modules.catalog.models import (
    CatalogCollection,
    CatalogCredit,
    CatalogGenre,
    CatalogItem,
    CatalogLanguage,
    CatalogRegion,
    CatalogStatus,
    CatalogType,
)


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, obj: Any) -> Any:
        self.db.add(obj)
        self.db.flush()
        return obj

    def item(self, id: UUID) -> CatalogItem | None:
        return self.db.execute(
            select(CatalogItem)
            .where(CatalogItem.id == id)
            .options(
                selectinload(CatalogItem.genres),
                selectinload(CatalogItem.languages),
                selectinload(CatalogItem.regions),
                selectinload(CatalogItem.credits).selectinload(CatalogCredit.person),
            )
        ).scalar_one_or_none()

    def item_by_slug(self, slug: str) -> CatalogItem | None:
        return self.db.execute(
            select(CatalogItem).where(CatalogItem.slug == slug)
        ).scalar_one_or_none()

    def list(
        self,
        *,
        search: str | None,
        catalog_type: CatalogType | None,
        status: CatalogStatus | None,
        genre_id: UUID | None,
        language_id: UUID | None,
        region_id: UUID | None,
        is_kids: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[CatalogItem], int]:
        f: list[Any] = [CatalogItem.deleted_at.is_(None)]
        q = select(CatalogItem)
        if search:
            f.append(
                or_(
                    CatalogItem.title.ilike(f"%{search}%"),
                    CatalogItem.synopsis.ilike(f"%{search}%"),
                )
            )
        if catalog_type:
            f.append(CatalogItem.catalog_type == catalog_type)
        if status:
            f.append(CatalogItem.status == status)
        if is_kids is not None:
            f.append(CatalogItem.is_kids == is_kids)
        if genre_id:
            q = q.join(CatalogItem.genres)
            f.append(CatalogGenre.id == genre_id)
        if language_id:
            q = q.join(CatalogItem.languages)
            f.append(CatalogLanguage.id == language_id)
        if region_id:
            q = q.join(CatalogItem.regions)
            f.append(CatalogRegion.id == region_id)
        base = q.where(*f)
        items = (
            self.db.execute(
                base.options(
                    selectinload(CatalogItem.genres),
                    selectinload(CatalogItem.languages),
                    selectinload(CatalogItem.regions),
                    selectinload(CatalogItem.credits).selectinload(
                        CatalogCredit.person
                    ),
                )
                .order_by(CatalogItem.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .unique()
            .all()
        )
        total = len(self.db.execute(base).scalars().unique().all())
        return items, total

    def taxonomy(self, kind: str, id: UUID) -> Any:
        return self.db.get(
            {
                "genre": CatalogGenre,
                "language": CatalogLanguage,
                "region": CatalogRegion,
            }[kind],
            id,
        )

    def collection(self, id: UUID) -> CatalogCollection | None:
        return self.db.execute(
            select(CatalogCollection)
            .where(CatalogCollection.id == id)
            .options(
                selectinload(CatalogCollection.items).selectinload(CatalogItem.genres),
                selectinload(CatalogCollection.items).selectinload(
                    CatalogItem.languages
                ),
                selectinload(CatalogCollection.items).selectinload(CatalogItem.regions),
                selectinload(CatalogCollection.items)
                .selectinload(CatalogItem.credits)
                .selectinload(CatalogCredit.person),
            )
        ).scalar_one_or_none()

    def collections(self) -> Sequence[CatalogCollection]:
        return (
            self.db.execute(
                select(CatalogCollection)
                .options(
                    selectinload(CatalogCollection.items).selectinload(
                        CatalogItem.genres
                    ),
                    selectinload(CatalogCollection.items).selectinload(
                        CatalogItem.languages
                    ),
                    selectinload(CatalogCollection.items).selectinload(
                        CatalogItem.regions
                    ),
                    selectinload(CatalogCollection.items)
                    .selectinload(CatalogItem.credits)
                    .selectinload(CatalogCredit.person),
                )
                .order_by(CatalogCollection.position)
            )
            .scalars()
            .unique()
            .all()
        )
