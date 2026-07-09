"""CMS repository interface placeholders."""

from app.modules.cms.repositories.interfaces import (
    CMSAssetRepositoryInterface,
    CMSMediaRepositoryInterface,
    CMSRepositoryInterface,
    CMSTranslationRepositoryInterface,
    CMSWorkflowRepositoryInterface,
)
from app.modules.cms.repositories.sqlalchemy_repository import SQLAlchemyCMSRepository

__all__ = [
    "CMSAssetRepositoryInterface",
    "CMSMediaRepositoryInterface",
    "CMSRepositoryInterface",
    "CMSTranslationRepositoryInterface",
    "CMSWorkflowRepositoryInterface",
    "SQLAlchemyCMSRepository",
]
