from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AsyncJobStatus(StrEnum):
    UNKNOWN = "unknown"
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    STALLED = "stalled"
    PAUSED = "paused"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class AsyncJobResult(BaseModel): ...


class AsyncJobOptions(BaseModel): ...


class AsyncJob[TResult: AsyncJobResult](BaseModel):
    source: str
    status: AsyncJobStatus = AsyncJobStatus.QUEUED
    id: UUID = Field(default_factory=uuid4)
    status_msg: str | None = None
    progress: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: TResult | Sequence[TResult] | None = None


class AsyncJobEvent[TJob: AsyncJob](BaseModel):
    job: TJob
    message: str | None = None
    error: bool = False


type AsyncJobEventHandler[TEvent: AsyncJobEvent] = Callable[[TEvent], Awaitable[None]]


class AsyncJobEventBus[TEvent: AsyncJobEvent]:
    def __init__(self) -> None:
        self._handlers: list[AsyncJobEventHandler[TEvent]] = []

    def subscribe(self, handler: AsyncJobEventHandler[TEvent]) -> None:
        self._handlers.append(handler)

    async def publish(self, event: TEvent) -> None:
        if not self._handlers:
            return
        await asyncio.gather(*(handler(event) for handler in self._handlers))


class AsyncJobManager[TJob: AsyncJob, TEvent: AsyncJobEvent, TResult: AsyncJobResult]:
    def __init__(self, event_bus: AsyncJobEventBus[TEvent]) -> None:
        self._jobs: dict[UUID, AsyncJob[TResult]] = {}
        self._bus = event_bus

    def create_job(self, job: AsyncJob[TResult]) -> None:
        if job.id in self._jobs:
            raise ValueError(f"Job with ID {job.id} already exists")
        self._jobs[job.id] = job

    def get_job(self, job_id: UUID) -> AsyncJob[TResult]:
        return self._jobs[job_id]

    def remove_job(self, job_id: UUID) -> AsyncJob[TResult]:
        return self._jobs.pop(job_id, default=None)

    async def update(self, event: AsyncJobEvent[TJob]) -> None:
        if event.job.id not in self._jobs:
            raise ValueError(f"Unable to update event with unknown job ID: {event.job.id}")
        event.job.updated_at = datetime.now(UTC)
        self._jobs[event.job.id] = event.job
        await self._bus.publish(event)
