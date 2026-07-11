"""CMS domain model placeholders."""

from app.modules.cms.models.base import (
    AuditBase,
    ContentBase,
    LocalizationBase,
    MediaAssetBase,
    WorkflowBase,
)
from app.modules.cms.models.content import (
    CMSCategory,
    CMSContent,
    CMSGenre,
    CMSLanguage,
    CMSRegion,
    CMSTag,
    cms_content_genres,
    cms_content_media_assets,
    cms_content_regions,
    cms_content_tags,
)
from app.modules.cms.models.enums import ContentStatus, ContentType, ContentVisibility
from app.modules.cms.media.models import AssetType, CMSMediaFile, ProcessingStatus, UploadStatus, URLStrategy

__all__ = [
    "AuditBase",
    "AssetType",
    "CMSCategory",
    "CMSContent",
    "CMSGenre",
    "CMSLanguage",
    "CMSMediaFile",
    "CMSRegion",
    "CMSTag",
    "ContentStatus",
    "ContentBase",
    "ContentType",
    "ContentVisibility",
    "LocalizationBase",
    "ProcessingStatus",
    "UploadStatus",
    "URLStrategy",
    "MediaAssetBase",
    "WorkflowBase",
    "cms_content_genres",
    "cms_content_media_assets",
    "cms_content_regions",
    "cms_content_tags",
]
