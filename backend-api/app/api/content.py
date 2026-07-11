"""Public content catalog compatibility routes."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.modules.cms.api.content import get_content_core_service
from app.modules.cms.models import ContentStatus, ContentVisibility
from app.modules.cms.schemas import CMSContentResponse
from app.modules.cms.services import CMSContentCoreService

router = APIRouter(prefix="/api/v1/content", tags=["content-catalog"])


def _catalog_item(content: CMSContentResponse) -> dict[str, Any]:
    content_type = content.content_type.value
    seo = content.seo
    default_type = "channel" if content_type == "live_tv" else "vod"
    item_type = str(seo.get("catalog_type") or default_type)
    presenter = str(seo.get("presenter") or f"Author #{content.author_id}")
    return {
        "id": str(content.id),
        "type": item_type,
        "title": content.title,
        "category": str(seo.get("category") or "General"),
        "presenter": presenter,
        "host": presenter,
        "duration": str(seo.get("duration") or "45:00"),
        "premium": content.visibility.value != "public",
        "description": content.summary or content.body,
        "quality": "1080p HD",
        "year": str(content.created_at.year),
        "status": content.status.value,
        "slug": content.slug,
    }


@router.get("/catalog")
def list_catalog(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: CMSContentCoreService = Depends(get_content_core_service),
) -> list[dict[str, Any]]:
    page = service.list_content(
        status=ContentStatus.PUBLISHED,
        visibility=ContentVisibility.PUBLIC,
        limit=limit,
        offset=offset,
    )
    return [_catalog_item(item) for item in page.items]
