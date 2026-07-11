# Compatibility shim for legacy imports of ``app.database``.
"""This module re‑exports the canonical database objects from ``app.core.database``
so that existing code importing ``app.database`` continues to function during
migration. It is temporary and should be removed once all imports are updated.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

# Import the canonical implementations from the new location
from app.core.database import Base, engine, SessionLocal, get_db as _core_get_db

__all__ = ["engine", "SessionLocal", "Base", "get_db"]

def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session (FastAPI dependency)."""
    yield from _core_get_db()
