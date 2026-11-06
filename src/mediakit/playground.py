from __future__ import annotations

import asyncio
import logging
import sys
from getpass import getpass

# from pathlib import Path
# from mediakit.acquisition import AcquisitionJobEvent
from mediakit.models import AsyncJobStatus
from mediakit.search import SearchJobEvent
from mediakit.sources.qbittorrent import (
    QBitTorrentConfig,
    QBitTorrentSearchOptions,
    QBitTorrentSource,
)

# from mediakit.sources.youtube import YoutubeAcquisitionOptions, YoutubeSearchOptions, YouTubeSource

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)


# async def aje_handler(event: AcquisitionJobEvent) -> None:
#     match event.job.status:
#         case AsyncJobStatus.RUNNING:
#             _logger.info(
#                 "[%s] %s (%.2f%%)%s",
#                 event.job.id,
#                 event.job.status.upper(),
#                 event.job.progress,
#                 f" - {event.message}" if event.message else "",
#             )
#         case _:
#             _logger.info(
#                 "[%s] %s%s",
#                 event.job.id,
#                 event.job.status.upper(),
#                 f" - {event.message}" if event.message else "",
#             )


# async def main() -> None:
#     eb = EventBus()
#     eb.subscribe(aje_handler)
#     jm = JobManager(eb)
#     youtube = YouTubeSource(jm)
#     errors = youtube.verify_dependencies()
#     if errors:
#         for error in errors:
#             print(error)
#             sys.exit(1)
#     results = await youtube.search("The Apothecary Diaries Movie", options=YoutubeSearchOptions(max_results=10))
#     print("Search complete, results:")
#     for result in results:
#         print(result.model_dump())
#     job = await youtube.acquire(results[0], options=YoutubeAcquisitionOptions(overwrite=True))
#     while True:
#         current = await youtube.status(job.id)
#         if current.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
#             break
#         await asyncio.sleep(0.25)
#     print(current.model_dump())


async def qbt_main() -> None:
    qbt = QBitTorrentSource()
    errors = qbt.verify_dependencies()
    if errors:
        for error in errors:
            print(error)
            sys.exit(1)
    endpoints = await qbt.discover()
    if not endpoints:
        print("No QBT endpoints found")
        host = input("Enter host: ").strip()
        while True:
            try:
                port = int(input("Port [8080]: ").strip() or "8080")
                break
            except ValueError:
                print("Port must be an integer")
        username = input("Username [admin]: ").strip() or "admin"
        password = getpass()
        config = QBitTorrentConfig(host=host, port=port, username=username, password=password)
    else:
        config = None
        ep_iter = iter(endpoints)
        while config is None:
            try:
                ep = next(ep_iter)
            except StopIteration:
                print("Failed to find a suitable endpoint")
                sys.exit(1)
            ep_config = await qbt.test_connection(ep, username="admin", password="password")
            if ep_config is not None:
                config = ep_config

    async def search_handler(event: SearchJobEvent) -> None:
        for result in event.newly_discovered:
            print(f"[SEARCH] {result.title}")

    qbt._search_event_bus.subscribe(search_handler)

    await qbt.connect(config)
    search_job = await qbt.search("Apothecary Diaries", options=QBitTorrentSearchOptions(min_seeders=100))
    last_result_count = 0
    while True:
        current_search = await qbt.search_status(search_job.id)
        if current_search.result_count > last_result_count:
            print(f"Found {current_search.result_count} results...")
            last_result_count = current_search.result_count
        else:
            print(f"[{current_search.status}] Searching...")
        if current_search.status in {
            AsyncJobStatus.COMPLETED,
            AsyncJobStatus.FAILED,
            AsyncJobStatus.CANCELLED,
            AsyncJobStatus.TIMEOUT,
        }:
            print(f"Search job terminated with status {current_search.status}")
            break
        await asyncio.sleep(1)
    if current_search.status != AsyncJobStatus.COMPLETED:
        _logger.error("Search ended without completing: %s", current_search.status)
        return
    search_results = current_search.result
    download_candidate = next((r for r in search_results if r.metadata.size_bytes > 0), None)
    if download_candidate is None:
        sys.exit(1)
    job = await qbt.acquire(download_candidate)
    while True:
        current = await qbt.status(job.id)
        current_status = f"{current.status.value}{'' if not current.status_msg else ' (' + current.status_msg + ') '}"
        current_speed_kbps = 0 if not current.speed_bps else int(current.speed_bps / 1000)
        current_progress = round(current.progress, 2)
        print(f"JOB[{current.id}]: {current_status} - {current_progress}% ({current_speed_kbps} Kbps)")
        if current.status in {AsyncJobStatus.COMPLETED, AsyncJobStatus.FAILED}:
            break
        await asyncio.sleep(1)
    print(current.model_dump())


if __name__ == "__main__":
    asyncio.run(qbt_main())
    # asyncio.run(main())
    # import qbittorrentapi

    # client = qbittorrentapi.Client(host="172.29.80.1", port=8080, username="admin", password="password")
    # client.auth_log_in()
    # job = client.search_start(pattern="The Apothecary Diaries", plugins="enabled", category="all")
    # results = client.search_results(search_id=job.id)
    # print(results)

    # results = await qbt.search
