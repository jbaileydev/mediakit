from __future__ import annotations

import asyncio
import logging
import sys

from mediakit.sources.media_source import AcquisitionJobEvent, EventBus, JobManager, JobStatus
from mediakit.sources.youtube import YoutubeAcquisitionOptions, YoutubeSearchOptions, YouTubeSource

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)


async def aje_handler(event: AcquisitionJobEvent) -> None:
    match event.job.status:
        case JobStatus.RUNNING:
            _logger.info(
                "[%s] %s (%.2f%%)%s",
                event.job.id,
                event.job.status.upper(),
                event.job.progress,
                f" - {event.message}" if event.message else "",
            )
        case _:
            _logger.info(
                "[%s] %s%s",
                event.job.id,
                event.job.status.upper(),
                f" - {event.message}" if event.message else "",
            )


async def main() -> None:
    eb = EventBus()
    eb.subscribe(aje_handler)
    jm = JobManager(eb)
    youtube = YouTubeSource(jm)
    errors = youtube.verify_dependencies()
    if errors:
        for error in errors:
            print(error)
            sys.exit(1)
    results = await youtube.search("The Apothecary Diaries Movie", options=YoutubeSearchOptions(max_results=10))
    print("Search complete, results:")
    for result in results:
        print(result.model_dump())
    job = await youtube.acquire(results[0], options=YoutubeAcquisitionOptions(overwrite=True))
    while True:
        current = await youtube.status(job.id)
        if current.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            break
        await asyncio.sleep(0.25)
    print(current.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
