from collections.abc import Sequence
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.cms.models import CMSAsset, CMSAssetTranslation, CMSMediaFile, CMSWorkflowLog, ContentType, WorkflowState
from app.modules.cms.repositories import SQLAlchemyCMSRepository


class FakeScalars:
    def __init__(self, items: Sequence[Any]) -> None:
        self.items = list(items)

    def all(self) -> list[Any]:
        return self.items


class FakeResult:
    def __init__(self, *, scalar: Any = None, items: Sequence[Any] = ()) -> None:
        self.scalar = scalar
        self.items = list(items)

    def scalar_one_or_none(self) -> Any:
        return self.scalar

    def scalars(self) -> FakeScalars:
        return FakeScalars(self.items)


class FakeSession:
    def __init__(self, results: Sequence[FakeResult] = ()) -> None:
        self.added: list[Any] = []
        self.flushed = False
        self.get_calls: list[tuple[type[Any], Any]] = []
        self.statements: list[Any] = []
        self.results = list(results)

    def add(self, value: Any) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flushed = True

    def get(self, model: type[Any], identity: Any) -> Any:
        self.get_calls.append((model, identity))
        return None

    def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return self.results.pop(0) if self.results else FakeResult()


def make_repository(session: FakeSession) -> SQLAlchemyCMSRepository:
    return SQLAlchemyCMSRepository(cast(Session, session))


def test_create_asset_persists_cms_asset() -> None:
    session = FakeSession()
    repository = make_repository(session)
    parent_id = uuid4()

    asset = repository.create_asset(
        content_type=ContentType.MOVIE,
        parent_asset_id=parent_id,
        duration=timedelta(hours=1, minutes=45),
        is_premium=True,
        age_rating="PG-13",
    )

    assert asset in session.added
    assert session.flushed is True
    assert asset.content_type == ContentType.MOVIE
    assert asset.parent_asset_id == parent_id
    assert asset.is_premium is True


def test_get_and_list_assets_dispatch_queries() -> None:
    asset_id = uuid4()
    asset = CMSAsset(content_type=ContentType.ARTICLE)
    session = FakeSession(results=[FakeResult(items=[asset])])
    repository = make_repository(session)

    assert repository.get_asset(asset_id) is None
    assets = repository.list_assets(content_type=ContentType.ARTICLE, publish_state=WorkflowState.DRAFT)

    assert session.get_calls == [(CMSAsset, asset_id)]
    assert assets == [asset]
    assert len(session.statements) == 1


def test_upsert_translation_updates_existing_translation() -> None:
    asset_id = uuid4()
    translation = CMSAssetTranslation(asset_id=asset_id, language_code="so", title="Old title")
    session = FakeSession(results=[FakeResult(scalar=translation)])
    repository = make_repository(session)

    result = repository.upsert_translation(
        asset_id=asset_id,
        language_code="so",
        title="New title",
        description="Description",
        summary="Summary",
        tags=["news", "somali"],
    )

    assert result is translation
    assert translation.title == "New title"
    assert translation.description == "Description"
    assert translation.summary == "Summary"
    assert translation.tags == ["news", "somali"]
    assert translation in session.added
    assert session.flushed is True


def test_upsert_translation_creates_missing_translation() -> None:
    asset_id = uuid4()
    session = FakeSession(results=[FakeResult(scalar=None)])
    repository = make_repository(session)

    translation = repository.upsert_translation(asset_id=asset_id, language_code="en", title="Title")

    assert isinstance(translation, CMSAssetTranslation)
    assert translation.asset_id == asset_id
    assert translation.language_code == "en"
    assert translation.title == "Title"
    assert translation.tags == []
    assert translation in session.added


def test_media_file_repository_methods() -> None:
    asset_id = uuid4()
    media_file = CMSMediaFile(asset_id=asset_id, file_type="video_hls", url="https://cdn.example/video.m3u8", file_size=12)
    session = FakeSession(results=[FakeResult(items=[media_file])])
    repository = make_repository(session)

    created = repository.add_media_file(
        asset_id=asset_id,
        file_type="thumbnail",
        url="https://cdn.example/thumb.jpg",
        file_size=1024,
        resolution="720p",
    )
    files = repository.list_media_files(asset_id)

    assert isinstance(created, CMSMediaFile)
    assert created in session.added
    assert files == [media_file]


def test_workflow_log_repository_methods() -> None:
    asset_id = uuid4()
    workflow_log = CMSWorkflowLog(
        asset_id=asset_id,
        actor_id=7,
        old_state=WorkflowState.DRAFT,
        new_state=WorkflowState.REVIEW,
    )
    session = FakeSession(results=[FakeResult(items=[workflow_log])])
    repository = make_repository(session)

    created = repository.add_workflow_log(
        asset_id=asset_id,
        actor_id=7,
        old_state=WorkflowState.DRAFT,
        new_state=WorkflowState.REVIEW,
        comment="Ready for review",
    )
    logs = repository.list_workflow_logs(asset_id)

    assert isinstance(created, CMSWorkflowLog)
    assert created.comment == "Ready for review"
    assert created in session.added
    assert logs == [workflow_log]
