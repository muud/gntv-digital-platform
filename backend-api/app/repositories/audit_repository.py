from sqlalchemy.orm import Session
from typing import Any

from ..models.audit import AuditLog

class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: int, event_type: str, metadata: dict[str, Any] | None = None) -> AuditLog:
        audit = AuditLog(user_id=user_id, event_type=event_type, metadata_=metadata)
        self.db.add(audit)
        self.db.flush()
        return audit
