from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from mediakit.enums import JobStatus


class SearchResult(BaseModel):
    source: str
    metadata: SearchResultMetadata


class SearchResultMetadata(BaseModel):
    pass


class SearchOptions(BaseModel):
    pass


class AcquisitionJob(BaseModel):
    id: str
    source: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    speed_bps: int | None = None
    eta_s: int | None = None
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)
    result: AcquisitionResult | None = None


class AcquisitionJobEvent(BaseModel):
    job: AcquisitionJob
    message: str | None = None
    error: bool = False


EventHandler = Callable[[AcquisitionJobEvent], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: AcquisitionJobEvent) -> None:
        if not self._handlers:
            return
        await asyncio.gather(*(handler(event) for handler in self._handlers))


class JobManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._jobs: dict[str, AcquisitionJob] = {}
        self._event_bus = event_bus

    def create_job(self, job: AcquisitionJob) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: str) -> AcquisitionJob:
        return self._jobs[job_id]

    async def update(self, event: AcquisitionJobEvent) -> None:
        event.job.updated_at = datetime.now(UTC)
        self._jobs[event.job.id] = event.job
        await self._event_bus.publish(event)


class AcquisitionOptions(BaseModel):
    pass


class AcquisitionResult(BaseModel):
    files: list[Path] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaSource(Protocol):
    @property
    def name(self) -> str: ...

    @staticmethod
    def verify_dependencies() -> list[str]: ...

    async def search(self, query: str, options: SearchOptions | None = None) -> Sequence[SearchResult]: ...

    async def acquire(self, result: SearchResult, options: AcquisitionOptions | None = None) -> AcquisitionJob: ...

    async def status(self, job_id: str) -> AcquisitionJob: ...
