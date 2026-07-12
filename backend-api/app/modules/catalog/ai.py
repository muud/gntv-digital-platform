from typing import Protocol
from uuid import UUID


class CatalogAIHook(Protocol):
    def dispatch(self, item_id: UUID, hook: str) -> None: ...


class NullCatalogAIHook:
    def dispatch(self, item_id: UUID, hook: str) -> None:
        del item_id, hook
