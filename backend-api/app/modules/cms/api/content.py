"""FastAPI routes for CMS Content Core."""

from collections.abc import Callable, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.cms.models import CMSCategory, CMSGenre, CMSLanguage, CMSRegion, CMSTag, ContentStatus, ContentType, ContentVisibility
from app.modules.cms.permissions import CMSScope, has_scope
from app.modules.cms.repositories import CMSContentRepository
from app.modules.cms.schemas import (
    CMSCategoryCreate,
    CMSCategoryResponse,
    CMSContentCreate,
    CMSContentListResponse,
    CMSContentResponse,
    CMSContentTransitionRequest,
    CMSContentUpdate,
    CMSGenreResponse,
    CMSLanguageCreate,
    CMSLanguageResponse,
    CMSRegionCreate,
    CMSRegionResponse,
    CMSTagResponse,
    CMSTaxonomyCreate,
)
from app.modules.cms.services import (
    CMSContentCoreService,
    CMSContentNotFoundError,
    CMSInvalidTransitionError,
    CMSValidationError,
)
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/api/v1/cms", tags=["cms-content"])


def get_content_core_service(db: Session = Depends(get_db)) -> CMSContentCoreService:
    return CMSContentCoreService(CMSContentRepository(db), AuditRepository(db))


def require_cms_scope(required_scope: CMSScope) -> Callable[..., User]:
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_scope(roles=current_user.role_names, required_scope=required_scope):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"CMS scope required: {required_scope}")
        return current_user

    return dependency


def _validation_error(exc: Exception) -> HTTPException:
    del exc
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "cms_validation_error"})


def _not_found(exc: Exception) -> HTTPException:
    del exc
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "cms_content_not_found"})


@router.post("/languages", response_model=CMSLanguageResponse, status_code=status.HTTP_201_CREATED)
def create_language(
    payload: CMSLanguageCreate,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSLanguage:
    try:
        return service.create_language(payload, actor_id=current_user.id)
    except CMSValidationError as exc:
        raise _validation_error(exc) from exc


@router.get("/languages", response_model=list[CMSLanguageResponse])
def list_languages(service: CMSContentCoreService = Depends(get_content_core_service)) -> Sequence[CMSLanguage]:
    return service.list_languages()


@router.post("/categories", response_model=CMSCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CMSCategoryCreate,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSCategory:
    try:
        return service.create_category(payload, actor_id=current_user.id)
    except CMSValidationError as exc:
        raise _validation_error(exc) from exc


@router.get("/categories", response_model=list[CMSCategoryResponse])
def list_categories(service: CMSContentCoreService = Depends(get_content_core_service)) -> Sequence[CMSCategory]:
    return service.list_categories()


@router.post("/tags", response_model=CMSTagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: CMSTaxonomyCreate,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSTag:
    return service.create_tag(payload, actor_id=current_user.id)


@router.get("/tags", response_model=list[CMSTagResponse])
def list_tags(service: CMSContentCoreService = Depends(get_content_core_service)) -> Sequence[CMSTag]:
    return service.list_tags()


@router.post("/genres", response_model=CMSGenreResponse, status_code=status.HTTP_201_CREATED)
def create_genre(
    payload: CMSTaxonomyCreate,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSGenre:
    return service.create_genre(payload, actor_id=current_user.id)


@router.get("/genres", response_model=list[CMSGenreResponse])
def list_genres(service: CMSContentCoreService = Depends(get_content_core_service)) -> Sequence[CMSGenre]:
    return service.list_genres()


@router.post("/regions", response_model=CMSRegionResponse, status_code=status.HTTP_201_CREATED)
def create_region(
    payload: CMSRegionCreate,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSRegion:
    return service.create_region(payload, actor_id=current_user.id)


@router.get("/regions", response_model=list[CMSRegionResponse])
def list_regions(service: CMSContentCoreService = Depends(get_content_core_service)) -> Sequence[CMSRegion]:
    return service.list_regions()


@router.post("/content", response_model=CMSContentResponse, status_code=status.HTTP_201_CREATED)
def create_content(
    payload: CMSContentCreate,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSContentResponse:
    try:
        return service.create_content(payload, author_id=current_user.id)
    except CMSValidationError as exc:
        raise _validation_error(exc) from exc


@router.get("/content", response_model=CMSContentListResponse)
def list_content(
    status_filter: ContentStatus | None = Query(default=None, alias="status"),
    visibility: ContentVisibility | None = None,
    content_type: ContentType | None = None,
    language_id: UUID | None = None,
    category_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_cms_scope("content:read-draft")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSContentListResponse:
    del current_user
    return service.list_content(
        status=status_filter,
        visibility=visibility,
        content_type=content_type,
        language_id=language_id,
        category_id=category_id,
        limit=limit,
        offset=offset,
    )


@router.get("/content/{content_id}", response_model=CMSContentResponse)
def get_content(
    content_id: UUID,
    current_user: User = Depends(require_cms_scope("content:read-draft")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSContentResponse:
    del current_user
    try:
        return service.get_content(content_id)
    except CMSContentNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch("/content/{content_id}", response_model=CMSContentResponse)
def update_content(
    content_id: UUID,
    payload: CMSContentUpdate,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSContentResponse:
    try:
        return service.update_content(content_id, payload, actor_id=current_user.id)
    except CMSContentNotFoundError as exc:
        raise _not_found(exc) from exc
    except CMSValidationError as exc:
        raise _validation_error(exc) from exc


@router.delete("/content/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content(
    content_id: UUID,
    current_user: User = Depends(require_cms_scope("content:write")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> None:
    try:
        service.delete_content(content_id, actor_id=current_user.id)
    except CMSContentNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/content/{content_id}/workflow", response_model=CMSContentResponse)
def transition_content(
    content_id: UUID,
    payload: CMSContentTransitionRequest,
    current_user: User = Depends(require_cms_scope("content:approve")),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> CMSContentResponse:
    try:
        return service.transition_content(content_id, payload, actor_id=current_user.id)
    except CMSContentNotFoundError as exc:
        raise _not_found(exc) from exc
    except (CMSInvalidTransitionError, CMSValidationError) as exc:
        raise _validation_error(exc) from exc
