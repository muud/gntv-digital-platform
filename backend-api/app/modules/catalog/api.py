from collections.abc import Callable
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.catalog.ai import NullCatalogAIHook
from app.modules.catalog.models import CatalogStatus, CatalogType
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.schemas import (
    AIHookRequest,
    CatalogItemCreate,
    CatalogItemResponse,
    CatalogItemUpdate,
    CatalogListResponse,
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    PersonCreate,
    ProgressResponse,
    ProgressUpdate,
    RatingUpdate,
    StudioCreate,
    TaxonomyCreate,
)
from app.modules.catalog.service import CatalogError, CatalogNotFound, CatalogService
from app.modules.cms.permissions import CMSScope, has_scope
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/api/v1/catalog", tags=["Premium Streaming Catalog"])


def service(db: Session = Depends(get_db)) -> CatalogService:
    return CatalogService(
        CatalogRepository(db), AuditRepository(db), NullCatalogAIHook()
    )


def scope(name: str) -> Callable[..., User]:
    def dep(user: User = Depends(get_current_user)) -> User:
        required: CMSScope = "content:write" if name == "write" else "content:read"
        if not has_scope(roles=user.role_names, required_scope=required):
            raise HTTPException(403, detail={"code": "catalog_forbidden"})
        return user

    return dep


def err(e: CatalogError) -> HTTPException:
    return HTTPException(
        404 if isinstance(e, CatalogNotFound) else 400,
        detail={
            "code": "catalog_not_found"
            if isinstance(e, CatalogNotFound)
            else "catalog_validation_error"
        },
    )


@router.post("/items", response_model=CatalogItemResponse, status_code=201)
def create(
    p: CatalogItemCreate,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> CatalogItemResponse:
    try:
        return s.create_item(p, u.id)
    except CatalogError as e:
        raise err(e) from e


@router.get("/items", response_model=CatalogListResponse)
def listing(
    search: str | None = None,
    catalog_type: CatalogType | None = None,
    status_filter: CatalogStatus | None = Query(None, alias="status"),
    genre_id: UUID | None = None,
    language_id: UUID | None = None,
    region_id: UUID | None = None,
    is_kids: bool | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    u: User = Depends(scope("read")),
    s: CatalogService = Depends(service),
) -> CatalogListResponse:
    if not has_scope(roles=u.role_names, required_scope="content:read-draft"):
        status_filter = CatalogStatus.PUBLISHED
    return s.list(
        search=search,
        catalog_type=catalog_type,
        status=status_filter,
        genre_id=genre_id,
        language_id=language_id,
        region_id=region_id,
        is_kids=is_kids,
        limit=limit,
        offset=offset,
    )


@router.get("/items/{id}", response_model=CatalogItemResponse)
def detail(
    id: UUID, u: User = Depends(scope("read")), s: CatalogService = Depends(service)
) -> CatalogItemResponse:
    try:
        item = s.get(id)
        if item.status != CatalogStatus.PUBLISHED and not has_scope(
            roles=u.role_names, required_scope="content:read-draft"
        ):
            raise CatalogNotFound(str(id))
        return item
    except CatalogError as e:
        raise err(e) from e


@router.patch("/items/{id}", response_model=CatalogItemResponse)
def update(
    id: UUID,
    p: CatalogItemUpdate,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> CatalogItemResponse:
    try:
        return s.update_item(id, p, u.id)
    except CatalogError as e:
        raise err(e) from e


@router.delete("/items/{id}", status_code=204)
def delete(
    id: UUID, u: User = Depends(scope("write")), s: CatalogService = Depends(service)
) -> Response:
    s.delete(id, u.id)
    return Response(status_code=204)


@router.post("/items/{id}/restore", status_code=204)
def restore(
    id: UUID, u: User = Depends(scope("write")), s: CatalogService = Depends(service)
) -> Response:
    s.delete(id, u.id, True)
    return Response(status_code=204)


@router.post("/taxonomies/{kind}", response_model=dict[str, Any], status_code=201)
def taxonomy(
    kind: str,
    p: TaxonomyCreate,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> dict[str, Any]:
    if kind not in {"genre", "language", "region"}:
        raise HTTPException(400, detail={"code": "catalog_taxonomy_invalid"})
    return s.taxonomy(kind, p, u.id)


@router.post("/people", response_model=dict[str, Any], status_code=201)
def person(
    p: PersonCreate,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> dict[str, Any]:
    return s.person(p, u.id)


@router.post("/studios", response_model=dict[str, Any], status_code=201)
def studio(
    p: StudioCreate,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> dict[str, Any]:
    return s.studio(p, u.id)


@router.post("/collections", response_model=CollectionResponse, status_code=201)
def collection(
    p: CollectionCreate,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> CollectionResponse:
    return s.collection(p, u.id)


@router.get("/collections", response_model=list[CollectionResponse])
def collections(
    u: User = Depends(scope("read")), s: CatalogService = Depends(service)
) -> list[CollectionResponse]:
    del u
    return s.collections()


@router.get("/collections/{collection_id}", response_model=CollectionResponse)
def collection_detail(
    collection_id: UUID,
    u: User = Depends(scope("read")),
    s: CatalogService = Depends(service),
) -> CollectionResponse:
    del u
    try:
        return s.get_collection(collection_id)
    except CatalogError as e:
        raise err(e) from e


@router.patch("/collections/{collection_id}", response_model=CollectionResponse)
def collection_update(
    collection_id: UUID,
    p: CollectionUpdate,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> CollectionResponse:
    try:
        return s.update_collection(collection_id, p, u.id)
    except CatalogError as e:
        raise err(e) from e


@router.delete("/collections/{collection_id}", status_code=204)
def collection_delete(
    collection_id: UUID,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> Response:
    try:
        s.delete_collection(collection_id, u.id)
        return Response(status_code=204)
    except CatalogError as e:
        raise err(e) from e


@router.get("/featured-rows", response_model=list[CollectionResponse])
def featured(
    u: User = Depends(scope("read")), s: CatalogService = Depends(service)
) -> list[CollectionResponse]:
    del u
    return s.featured()


@router.put("/items/{id}/progress", response_model=ProgressResponse)
def progress(
    id: UUID,
    p: ProgressUpdate,
    u: User = Depends(get_current_user),
    s: CatalogService = Depends(service),
) -> ProgressResponse:
    return s.progress(u.id, id, p)


@router.get("/continue-watching", response_model=list[ProgressResponse])
def watching(
    u: User = Depends(get_current_user), s: CatalogService = Depends(service)
) -> list[ProgressResponse]:
    return s.continue_watching(u.id)


@router.put("/items/{id}/rating", status_code=204)
def rating(
    id: UUID,
    p: RatingUpdate,
    u: User = Depends(get_current_user),
    s: CatalogService = Depends(service),
) -> Response:
    s.rate(u.id, id, p.score)
    return Response(status_code=204)


@router.get("/recommendations", response_model=list[CatalogItemResponse])
def recommendations(
    limit: int = Query(20, ge=1, le=100),
    u: User = Depends(get_current_user),
    s: CatalogService = Depends(service),
) -> list[CatalogItemResponse]:
    return s.recommendations(u.id, limit)


@router.post("/items/{id}/ai-hooks", status_code=202)
def ai(
    id: UUID,
    p: AIHookRequest,
    u: User = Depends(scope("write")),
    s: CatalogService = Depends(service),
) -> dict[str, str]:
    s.ai_hook(id, p.hook, u.id)
    return {"status": "queued"}
