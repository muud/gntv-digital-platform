"""Queue abstraction and in-memory implementation for workflow job execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
import threading
from uuid import UUID


class WorkflowQueue(ABC):
    """Abstract interface for workflow execution queuing."""

    @abstractmethod
    def enqueue(self, run_id: UUID, priority: int = 0) -> None:
        """Enqueue a workflow run ID for execution."""
        pass

    @abstractmethod
    def dequeue(self) -> UUID | None:
        """Dequeue the next workflow run ID, or None if empty."""
        pass

    @abstractmethod
    def peek(self) -> UUID | None:
        """Inspect the next workflow run ID without removing it."""
        pass

    @abstractmethod
    def size(self) -> int:
        """Return the current queue depth."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all pending items from the queue."""
        pass


class InMemoryWorkflowQueue(WorkflowQueue):
    """Thread-safe in-memory queue implementation suitable for testing and in-process execution."""

    def __init__(self) -> None:
        self._queue: deque[UUID] = deque()
        self._lock = threading.Lock()

    def enqueue(self, run_id: UUID, priority: int = 0) -> None:
        with self._lock:
            if run_id not in self._queue:
                self._queue.append(run_id)

    def dequeue(self) -> UUID | None:
        with self._lock:
            if not self._queue:
                return None
            return self._queue.popleft()

    def peek(self) -> UUID | None:
        with self._lock:
            if not self._queue:
                return None
            return self._queue[0]

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()


# Default singleton instance for application runtime
default_workflow_queue = InMemoryWorkflowQueue()
