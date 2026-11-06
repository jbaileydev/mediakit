from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field

from mediakit.models import (
    AsyncJob,
    AsyncJobEvent,
    AsyncJobEventBus,
    AsyncJobEventHandler,
    AsyncJobManager,
    AsyncJobOptions,
    AsyncJobResult,
    AsyncJobStatus,
)


class SearchOptions(AsyncJobOptions): ...


class SearchJobResult(AsyncJobResult):
    source: str


class SearchJob(AsyncJob[SearchJobResult]):
    query: str
    completed_plugins: int = 0
    total_plugins: int = 0
    result: Sequence[SearchJobResult] | None = None  # Narrow type

    @property
    def cancelled(self) -> bool:
        return self.status == AsyncJobStatus.CANCELLED

    @property
    def result_count(self) -> int:
        return len(self.result) if self.result else 0


class SearchJobEvent(AsyncJobEvent[SearchJob]):
    newly_discovered: list[SearchJobResult] = Field(default_factory=list)


# Can remain a type alias since AsyncJobEventHandler itself is also a type alias
type SearchJobEventHandler = AsyncJobEventHandler[SearchJobEvent]


class SearchJobEventBus(AsyncJobEventBus[SearchJobEvent]): ...


class SearchJobManager(AsyncJobManager[SearchJob, SearchJobEvent, SearchJobResult]): ...
