from __future__ import annotations

from pathlib import Path

from pydantic import Field

from mediakit.models import AsyncJob, AsyncJobEvent, AsyncJobEventBus, AsyncJobEventHandler, AsyncJobManager, AsyncJobOptions, AsyncJobResult


class AcquisitionOptions(AsyncJobOptions): ...


class AcquisitionJobResult(AsyncJobResult):
    files: list[Path] = Field(default_factory=list)


class AcquisitionJob(AsyncJob[AcquisitionJobResult]):
    speed_bps: int | None = None
    eta_s: int | None = None
    result: AcquisitionJobResult | None = None  # Narrow type


class AcquisitionJobEvent(AsyncJobEvent[AcquisitionJob]): ...


# Can remain a type alias since AsyncJobEventHandler itself is also a type alias
type AcquisitionJobEventHandler = AsyncJobEventHandler[AcquisitionJobEvent]


class AcquisitionJobEventBus(AsyncJobEventBus[AcquisitionJobEvent]): ...


class AcquisitionJobManager(AsyncJobManager[AcquisitionJob, AcquisitionJobEvent, AcquisitionJobResult]): ...
