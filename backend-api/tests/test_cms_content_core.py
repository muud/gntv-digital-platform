from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Table
from sqlalchemy.schema import CreateTable

from app.modules.cms.models import (
    CMSCategory,
    CMSContent,
    CMSGenre,
    CMSLanguage,
    CMSRegion,
    CMSTag,
    ContentStatus,
    ContentType,
    ContentVisibility,
)
from app.modules.cms.schemas import CMSContentCreate, CMSContentTransitionRequest, CMSLanguageCreate, CMSRegionCreate


def test_content_core_model_tables() -> None:
    assert isinstance(CMSContent.__table__, Table)
    assert CMSContent.__table__.name == "cms_content"
    assert "slug" in CMSContent.__table__.columns
    assert "seo" in CMSContent.__table__.columns
    assert "published_at" in CMSContent.__table__.columns
    assert "archived_at" in CMSContent.__table__.columns


def test_taxonomy_model_tables() -> None:
    assert cast(Table, CMSLanguage.__table__).name == "cms_languages"
    assert cast(Table, CMSCategory.__table__).name == "cms_categories"
    assert cast(Table, CMSTag.__table__).name == "cms_tags"
    assert cast(Table, CMSGenre.__table__).name == "cms_genres"
    assert cast(Table, CMSRegion.__table__).name == "cms_regions"


def test_content_schema_validation_accepts_required_fields() -> None:
    language_id = uuid4()
    payload = CMSContentCreate(
        title="Horn of Africa Trade Reform",
        slug="horn-of-africa-trade-reform",
        summary="Regional business analysis",
        body="Long-form editorial body",
        content_type=ContentType.ARTICLE,
        language_id=language_id,
        visibility=ContentVisibility.PUBLIC,
    )

    assert payload.language_id == language_id
    assert payload.content_type == ContentType.ARTICLE
    assert payload.visibility == ContentVisibility.PUBLIC
    assert payload.seo.keywords == []


def test_content_schema_rejects_invalid_slug() -> None:
    with pytest.raises(ValidationError):
        CMSContentCreate(
            title="Bad Slug",
            slug="Bad Slug",
            body="Body",
            content_type=ContentType.ARTICLE,
            language_id=uuid4(),
        )


def test_language_and_region_codes_normalize() -> None:
    language = CMSLanguageCreate(code="SO", name="Somali")
    region = CMSRegionCreate(code="ke", name="Kenya")

    assert language.code == "so"
    assert region.code == "KE"


def test_content_transition_payload() -> None:
    scheduled = datetime.now(UTC)
    payload = CMSContentTransitionRequest(transition="schedule", scheduled_publish_at=scheduled)

    assert payload.transition == "schedule"
    assert payload.scheduled_publish_at == scheduled


def test_content_status_and_visibility_values() -> None:
    assert [status.value for status in ContentStatus] == [
        "draft",
        "review",
        "fact_check",
        "approved",
        "scheduled",
        "published",
        "archived",
    ]
    assert [visibility.value for visibility in ContentVisibility] == ["public", "private", "unlisted", "members"]


def test_content_core_ddl_compiles() -> None:
    ddl = str(CreateTable(cast(Table, CMSContent.__table__)).compile())

    assert "cms_content" in ddl
    assert "title" in ddl
    assert "slug" in ddl
