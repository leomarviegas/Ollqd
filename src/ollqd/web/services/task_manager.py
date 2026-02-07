"""In-memory background task tracking for indexing jobs."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    id: str
    type: str
    status: TaskStatus
    progress: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    cancelled: bool = False
    request_params: Optional[dict] = None

    def to_dict(self) -> dict:
        duration_ms = None
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            if self.completed_at:
                end = datetime.fromisoformat(self.completed_at)
            else:
                end = datetime.now()
            duration_ms = int((end - start).total_seconds() * 1000)

        return {
            "id": self.id,
            "type": self.type,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": duration_ms,
            "request_params": self.request_params,
        }


class TaskManager:
    """In-memory task tracker. Stores up to 100 recent tasks."""

    def __init__(self):
        self._tasks: dict[str, TaskInfo] = {}

    def create(self, task_type: str) -> str:
        task_id = uuid.uuid4().hex[:12]
        self._tasks[task_id] = TaskInfo(
            id=task_id, type=task_type, status=TaskStatus.PENDING
        )
        self._prune()
        return task_id

    def create_with_params(self, task_type: str, params: dict) -> str:
        task_id = uuid.uuid4().hex[:12]
        self._tasks[task_id] = TaskInfo(
            id=task_id, type=task_type, status=TaskStatus.PENDING,
            request_params=params,
        )
        self._prune()
        return task_id

    def start(self, task_id: str):
        if task_id in self._tasks:
            self._tasks[task_id].status = TaskStatus.RUNNING
            self._tasks[task_id].started_at = datetime.now().isoformat()

    def update_progress(self, task_id: str, progress: float):
        if task_id in self._tasks:
            self._tasks[task_id].progress = min(progress, 1.0)

    def complete(self, task_id: str, result: dict):
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.COMPLETED
            t.progress = 1.0
            t.result = result
            t.completed_at = datetime.now().isoformat()

    def fail(self, task_id: str, error: str):
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.FAILED
            t.error = error
            t.completed_at = datetime.now().isoformat()

    def cancel(self, task_id: str) -> bool:
        t = self._tasks.get(task_id)
        if not t:
            return False
        if t.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        t.cancelled = True
        t.status = TaskStatus.CANCELLED
        t.completed_at = datetime.now().isoformat()
        return True

    def is_cancelled(self, task_id: str) -> bool:
        t = self._tasks.get(task_id)
        return t.cancelled if t else False

    def get_retry_params(self, task_id: str) -> Optional[dict]:
        t = self._tasks.get(task_id)
        if t and t.request_params:
            return dict(t.request_params)
        return None

    def get(self, task_id: str) -> Optional[dict]:
        t = self._tasks.get(task_id)
        return t.to_dict() if t else None

    def list_all(self) -> list[dict]:
        return [t.to_dict() for t in reversed(self._tasks.values())]

    def clear_finished(self):
        """Remove all completed, failed, and cancelled tasks."""
        to_remove = [
            k for k, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]
        for k in to_remove:
            del self._tasks[k]
        return len(to_remove)

    def _prune(self):
        if len(self._tasks) > 100:
            oldest = list(self._tasks.keys())[: len(self._tasks) - 100]
            for k in oldest:
                del self._tasks[k]
