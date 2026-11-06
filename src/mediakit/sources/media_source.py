from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mediakit.acquisition.models import AcquisitionJob, AcquisitionOptions
from mediakit.search.models import SearchJobResult, SearchOptions


class MediaSource(Protocol):
    @property
    def name(self) -> str: ...

    @staticmethod
    def verify_dependencies() -> list[str]: ...

    async def search(self, query: str, options: SearchOptions | None = None) -> Sequence[SearchJobResult]: ...

    async def acquire(self, result: SearchJobResult, options: AcquisitionOptions | None = None) -> AcquisitionJob: ...

    async def status(self, job_id: str) -> AcquisitionJob: ...
