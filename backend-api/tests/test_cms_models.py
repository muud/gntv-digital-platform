from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.schema import Table
from sqlalchemy.dialects import postgresql

from app.modules.cms.models import (
    CMSAsset,
    CMSAssetTranslation,
    CMSMediaFile,
    CMSWorkflowLog,
    ContentType,
    WorkflowState,
)


def test_cms_content_type_enum_matches_architecture() -> None:
    assert {content_type.value for content_type in ContentType} == {
        "live_tv",
        "movie",
        "tv_show",
        "season",
        "episode",
        "podcast",
        "radio",
        "article",
        "breaking_news",
        "short",
        "kids",
        "education",
        "community_post",
    }


def test_cms_workflow_state_enum_matches_architecture() -> None:
    assert [state.value for state in WorkflowState] == [
        "draft",
        "review",
        "fact_check",
        "editorial_approval",
        "scheduled",
        "published",
        "archived",
    ]


def test_cms_asset_table_contract() -> None:
    table = CMSAsset.__table__
    assert isinstance(table, Table)

    assert table.name == "cms_assets"
    assert table.c.id.primary_key is True
    assert table.c.content_type.nullable is False
    assert table.c.parent_asset_id.foreign_keys
    assert table.c.publish_state.default is not None
    assert table.c.publish_state.server_default is not None
    assert table.c.is_premium.default is not None
    assert table.c.age_rating.server_default is not None
    assert {"idx_cms_assets_type_state", "idx_cms_assets_parent"} <= {index.name for index in table.indexes}


def test_cms_translation_table_contract() -> None:
    table = CMSAssetTranslation.__table__
    assert isinstance(table, Table)

    assert table.name == "cms_asset_translations"
    assert table.c.asset_id.foreign_keys
    assert table.c.language_code.nullable is False
    assert table.c.title.nullable is False
    assert table.c.tags.nullable is False
    assert {"idx_cms_translations_lookup", "idx_cms_translations_tags"} <= {index.name for index in table.indexes}
    assert "uq_asset_language" in {constraint.name for constraint in table.constraints}


def test_cms_media_and_workflow_table_contracts() -> None:
    media_table = CMSMediaFile.__table__
    workflow_table = CMSWorkflowLog.__table__
    assert isinstance(media_table, Table)
    assert isinstance(workflow_table, Table)

    assert media_table.name == "cms_media_files"
    assert media_table.c.asset_id.foreign_keys
    assert media_table.c.file_type.nullable is False
    assert media_table.c.url.nullable is False
    assert media_table.c.file_size.nullable is False
    assert "idx_cms_media_asset" in {index.name for index in media_table.indexes}

    assert workflow_table.name == "cms_workflow_logs"
    assert workflow_table.c.asset_id.foreign_keys
    assert workflow_table.c.actor_id.foreign_keys
    assert workflow_table.c.new_state.nullable is False
    assert "idx_workflow_asset_logs" in {index.name for index in workflow_table.indexes}


def test_cms_models_compile_for_postgresql() -> None:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    asset_table = CMSAsset.__table__
    translation_table = CMSAssetTranslation.__table__
    media_table = CMSMediaFile.__table__
    workflow_table = CMSWorkflowLog.__table__
    assert isinstance(asset_table, Table)
    assert isinstance(translation_table, Table)
    assert isinstance(media_table, Table)
    assert isinstance(workflow_table, Table)

    asset_ddl = str(CreateTable(asset_table).compile(dialect=dialect))
    translation_ddl = str(CreateTable(translation_table).compile(dialect=dialect))
    media_ddl = str(CreateTable(media_table).compile(dialect=dialect))
    workflow_ddl = str(CreateTable(workflow_table).compile(dialect=dialect))

    assert "cms_assets" in asset_ddl
    assert "gntv_content_type" in asset_ddl
    assert "gntv_workflow_state" in asset_ddl
    assert "VARCHAR(50)[]" in translation_ddl
    assert "cms_media_files" in media_ddl
    assert "cms_workflow_logs" in workflow_ddl
