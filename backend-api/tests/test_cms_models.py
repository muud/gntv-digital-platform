from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.schema import Table
from typing import cast

from app.core.database import Base
from app.modules.cms.models import CMSContent, CMSMediaFile, ContentStatus, ContentType


def test_cms_content_type_enum_matches_architecture() -> None:
    assert {content_type.value for content_type in ContentType} == {
        "live_tv", "movie", "tv_show", "season", "episode", "podcast", "radio",
        "article", "breaking_news", "short", "kids", "education", "community_post",
    }


def test_cms_uses_single_approved_workflow() -> None:
    assert [state.value for state in ContentStatus] == [
        "draft", "review", "fact_check", "approved", "scheduled", "published", "archived",
    ]
    assert "cms_assets" not in Base.metadata.tables
    assert "cms_asset_translations" not in Base.metadata.tables
    assert "cms_workflow_logs" not in Base.metadata.tables


def test_media_files_are_owned_by_canonical_content_relationships() -> None:
    media_table = CMSMediaFile.__table__
    content_table = CMSContent.__table__
    assert isinstance(media_table, Table)
    assert isinstance(content_table, Table)
    assert "asset_id" not in media_table.c
    assert media_table.c.file_type.nullable is False
    assert media_table.c.url.nullable is False
    assert media_table.c.file_size.nullable is False
    assert content_table.c.status.nullable is False
    assert content_table.c.status.server_default is not None


def test_canonical_cms_models_compile_for_postgresql() -> None:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    content_ddl = str(CreateTable(cast(Table, CMSContent.__table__)).compile(dialect=dialect))
    media_ddl = str(CreateTable(cast(Table, CMSMediaFile.__table__)).compile(dialect=dialect))

    assert "cms_content" in content_ddl
    assert "gntv_content_status" in content_ddl
    assert "cms_media_files" in media_ddl
    assert "asset_id" not in media_ddl
