from __future__ import annotations

import asyncio
import base64
import logging
import math
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import qbittorrentapi
from pydantic import BaseModel, Field

from mediakit.acquisition import AcquisitionJobResult
from mediakit.enums import OperatingSystem
from mediakit.models import AsyncJobStatus
from mediakit.search import (
    SearchJob,
    SearchJobEvent,
    SearchJobEventBus,
    SearchJobManager,
)
from mediakit.utilities import detect_os, get_wsl_windows_host

from .acquisition import QBitTorrentAcquisitionJob, QBitTorrentAcquisitionOptions
from .search import (
    QBitTorrentSearchJobResult,
    QBitTorrentSearchOptions,
    QBitTorrentSearchResultMetadata,
)

_logger = logging.getLogger(__name__)


class QBitTorrentEndpoint(BaseModel):
    host: str
    port: int = 8080


class QBitTorrentConfig(QBitTorrentEndpoint):
    username: str = "admin"
    password: str | None = None


class QBitTorrentClientState(BaseModel):
    host: str
    port: int
    version: str
    plugins: list[str] = Field(default_factory=list)
    connected: bool = False

    @property
    def server(self) -> str:
        return f"{self.host}:{self.port}"


class QBitTorrentSource:
    def __init__(self) -> None:
        self._client: qbittorrentapi.Client | None = None
        self._config: QBitTorrentConfig | None = None
        self._jobs: dict[str, QBitTorrentAcquisitionJob] = {}
        self._search_tasks: dict[str, asyncio.Task] = {}
        self._search_event_bus = SearchJobEventBus()
        self._search_job_manager = SearchJobManager(self._search_event_bus)

    @property
    def name(self) -> str:
        return "qbittorrent"

    @staticmethod
    def verify_dependencies() -> list[str]:
        errors: list[str] = []
        return errors

    async def discover(self) -> list[QBitTorrentEndpoint]:
        candidates = [QBitTorrentEndpoint(host="localhost", port=8080), QBitTorrentEndpoint(host="127.0.0.1", port=8080)]
        if detect_os() is OperatingSystem.WSL:  # noqa: SIM102
            if host := get_wsl_windows_host():
                candidates.append(QBitTorrentEndpoint(host=host, port=8080))
        discovered: list[QBitTorrentEndpoint] = []
        for candidate in candidates:
            if await self._test_endpoint(candidate.host, candidate.port):
                discovered.append(candidate)
        return discovered

    async def test_connection(self, endpoint: QBitTorrentEndpoint, username: str = "admin", password: str | None = None) -> QBitTorrentConfig | None:
        try:
            client = qbittorrentapi.Client(host=endpoint.host, port=endpoint.port, username=username, password=password)
            await asyncio.to_thread(client.auth_log_in)
            await asyncio.to_thread(lambda: client.app.version)
            return QBitTorrentConfig(host=endpoint.host, port=endpoint.port, username=username, password=password)
        except Exception as _e:  # noqa: BLE001
            return None

    async def connect(self, config: QBitTorrentConfig) -> None:
        # Keep configuration for reconnects and future persistence via application settings
        self._config = config
        current_os = detect_os()
        self._client = qbittorrentapi.Client(host=config.host, port=config.port, username=config.username, password=config.password)
        try:
            await asyncio.to_thread(self._client.auth_log_in)
        except qbittorrentapi.LoginFailed as lfe:
            self._config = None
            raise ValueError(f"Failed to login to {self.name} media source in {current_os} environment.") from lfe
        except qbittorrentapi.Forbidden403Error as f403e:
            self._config = None
            raise RuntimeError(f"Failed to login to {self.name} media source on {current_os}. User is banned or not logged in.") from f403e

    async def search_status(self, job_id: UUID) -> SearchJob:
        return self._search_job_manager.get_job(job_id)

    async def cancel_search(self, job_id: UUID) -> None:
        job = self._search_job_manager.get_job(job_id)
        if job:
            job.status = AsyncJobStatus.CANCELLED
        task = self._search_tasks.get(job_id)
        if task:
            task.cancel()
        self._search_job_manager.remove_job(job_id)
        self._search_tasks.pop(job_id, default=None)

    async def search(self, query: str, options: QBitTorrentSearchOptions | None = None, timeout_s: float = 10.0) -> list[QBitTorrentSearchJobResult]:
        if self._client is None:
            raise RuntimeError(f"Not connected to {self.name} client")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be a finite positive number")
        options = options or QBitTorrentSearchOptions()
        job = SearchJob(source=self.name, query=query)
        self._search_job_manager.create_job(job)
        task = asyncio.create_task(self._execute_search(job, options, timeout_s))
        self._search_tasks[job.id] = task
        return job

    async def acquire(self, result: QBitTorrentSearchJobResult, options: QBitTorrentAcquisitionOptions | None = None) -> QBitTorrentAcquisitionJob:
        client = self._client
        if client is None:
            raise RuntimeError(f"Not connected to {self.name} client")
        for job in self._jobs.values():
            if job.torrent_url == result.metadata.torrent_url:
                return job

        options = options or QBitTorrentAcquisitionOptions()
        before_hashes = await self._current_hashes()
        try:
            success = await asyncio.to_thread(
                client.torrents_add,
                urls=result.metadata.torrent_url,
                category=options.category,
                save_path=str(options.save_path) if options.save_path else None,
                is_paused=options.paused,
                tags=",".join(options.tags),
                is_sequential_download=options.sequential_download,
            )
        except qbittorrentapi.Conflict409Error as exc:
            torrent_hash = self._magnet_info_hash(result.metadata.torrent_url)
            if torrent_hash is not None:
                for job in self._jobs.values():
                    if job.torrent_hash.lower() == torrent_hash:
                        return job
                torrents = await asyncio.to_thread(client.torrents_info, torrent_hashes=torrent_hash)
                if torrents:
                    return self._track_torrent(result, torrents[0].hash, options.seed_after_download)
            raise RuntimeError(
                "qBittorrent already has this torrent, but its info hash could not be "
                "matched to a tracked acquisition. Reuse an existing job or add it manually."
            ) from exc
        if success is False:
            raise RuntimeError("Failed to add torrent")
        torrent_hash: str | None = None
        for _ in range(20):
            await asyncio.sleep(0.5)
            after_hashes = await self._current_hashes()
            new_torrents = after_hashes - before_hashes
            if new_torrents:
                torrent_hash = next(iter(new_torrents))
                break
        if torrent_hash is None:
            raise RuntimeError("Failed to determine torrent hash for newly added torrent.")
        return self._track_torrent(result, torrent_hash, options.seed_after_download)

    @staticmethod
    def _magnet_info_hash(torrent_url: str) -> str | None:
        parsed_url = urlparse(torrent_url)
        if parsed_url.scheme.lower() != "magnet":
            return None
        for topic in parse_qs(parsed_url.query).get("xt", []):
            prefix = "urn:btih:"
            if not topic.lower().startswith(prefix):
                continue
            digest = topic[len(prefix) :]
            if len(digest) == 40 and all(character in "0123456789abcdefABCDEF" for character in digest):
                return digest.lower()
            if len(digest) == 32:
                try:
                    return base64.b32decode(digest.upper()).hex()
                except (ValueError, base64.binascii.Error):
                    return None
        return None

    def _track_torrent(
        self,
        result: QBitTorrentSearchJobResult,
        torrent_hash: str,
        seed_after_download: bool = False,
    ) -> QBitTorrentAcquisitionJob:
        for job in self._jobs.values():
            if job.torrent_hash.lower() == torrent_hash.lower():
                return job
        job = QBitTorrentAcquisitionJob(
            source=self.name,
            torrent_hash=torrent_hash,
            torrent_url=result.metadata.torrent_url,
            title=result.title,
            result=AcquisitionJobResult(),
        )
        self._jobs[job.id] = job
        asyncio.create_task(self._monitor_torrent(job, torrent_hash, seed_after_download=seed_after_download))
        return job

    async def status(self, job_id: str) -> QBitTorrentAcquisitionJob:
        return self._jobs[job_id]

    async def _monitor_torrent(
        self,
        job: QBitTorrentAcquisitionJob,
        torrent_hash: str,
        interval_s: float = 1.0,
        seed_after_download: bool = False,
    ) -> None:
        while True:
            if self._client is None:
                raise RuntimeError(f"Not connected to {self.name} client")
            torrents = await asyncio.to_thread(self._client.torrents_info, torrent_hashes=torrent_hash)
            if not torrents:
                return
            torrent = torrents[0]
            job_status = self._map_torrent_state(torrent)
            _logger.debug("Torrent status: <state: %s, progress: %f>", torrent.state, torrent.progress)
            _logger.debug("Mapped state: %s", job_status)
            job.progress = torrent.progress * 100
            job.speed_bps = torrent.dlspeed
            job.eta_s = torrent.eta
            job.status = job_status
            job.status_msg = str(torrent.state)
            if job.status == AsyncJobStatus.COMPLETED:
                job.result.files = [Path(torrent.content_path)]
                if not seed_after_download:
                    try:
                        await asyncio.to_thread(self._client.torrents_stop, torrent_hashes=torrent_hash)
                    except Exception as exc:
                        job.status_msg = f"{torrent.state}; failed to stop seeding: {exc}"
                        _logger.exception("Failed to stop seeding completed torrent %s", torrent_hash)
                return
            await asyncio.sleep(interval_s)

    async def _current_hashes(self) -> set[str]:
        if self._client is None:
            raise RuntimeError(f"Not connected to {self.name} client")
        torrents = await asyncio.to_thread(self._client.torrents_info)
        return {torrent.hash for torrent in torrents}

    async def _test_endpoint(self, host: str, port: int = 8080, timeout_s: float = 1.0) -> bool:
        try:
            _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_s)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _map_torrent_state(self, torrent: qbittorrentapi.TorrentDictionary) -> AsyncJobStatus:
        if torrent.progress >= 1.0:
            return AsyncJobStatus.COMPLETED
        state: qbittorrentapi.TorrentState = str(torrent.state)
        job_status = {
            qbittorrentapi.TorrentState.ERROR: AsyncJobStatus.FAILED,
            qbittorrentapi.TorrentState.MISSING_FILES: AsyncJobStatus.FAILED,
            qbittorrentapi.TorrentState.UPLOADING: AsyncJobStatus.RUNNING,
            qbittorrentapi.TorrentState.PAUSED_UPLOAD: AsyncJobStatus.PAUSED,
            qbittorrentapi.TorrentState.STOPPED_UPLOAD: AsyncJobStatus.PAUSED,
            qbittorrentapi.TorrentState.QUEUED_UPLOAD: AsyncJobStatus.QUEUED,
            qbittorrentapi.TorrentState.STALLED_UPLOAD: AsyncJobStatus.STALLED,
            qbittorrentapi.TorrentState.CHECKING_UPLOAD: AsyncJobStatus.VALIDATING,
            qbittorrentapi.TorrentState.FORCED_UPLOAD: AsyncJobStatus.RUNNING,
            qbittorrentapi.TorrentState.ALLOCATING: AsyncJobStatus.PREPARING,
            qbittorrentapi.TorrentState.DOWNLOADING: AsyncJobStatus.RUNNING,
            qbittorrentapi.TorrentState.METADATA_DOWNLOAD: AsyncJobStatus.PREPARING,
            qbittorrentapi.TorrentState.FORCED_METADATA_DOWNLOAD: AsyncJobStatus.PREPARING,
            qbittorrentapi.TorrentState.PAUSED_DOWNLOAD: AsyncJobStatus.PAUSED,
            qbittorrentapi.TorrentState.STOPPED_DOWNLOAD: AsyncJobStatus.PAUSED,
            qbittorrentapi.TorrentState.QUEUED_DOWNLOAD: AsyncJobStatus.QUEUED,
            qbittorrentapi.TorrentState.FORCED_DOWNLOAD: AsyncJobStatus.RUNNING,
            qbittorrentapi.TorrentState.STALLED_DOWNLOAD: AsyncJobStatus.STALLED,
            qbittorrentapi.TorrentState.CHECKING_DOWNLOAD: AsyncJobStatus.VALIDATING,
            qbittorrentapi.TorrentState.CHECKING_RESUME_DATA: AsyncJobStatus.PREPARING,
            qbittorrentapi.TorrentState.MOVING: AsyncJobStatus.VALIDATING,
            qbittorrentapi.TorrentState.UNKNOWN: AsyncJobStatus.UNKNOWN,
        }.get(state, AsyncJobStatus.UNKNOWN)
        return job_status

    async def _execute_search(self, job: SearchJob, options: QBitTorrentSearchOptions, timeout_s: float = 10.0) -> None:
        seen_ids: set[str] = set()
        client = self._client
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        search = None
        timed_out = False

        def request_args() -> dict[str, float]:
            remaining_s = deadline - loop.time()
            if remaining_s <= 0:
                raise TimeoutError
            return {"timeout": remaining_s}

        try:
            if client is None:
                raise RuntimeError(f"Not connected to {self.name} client")
            async with asyncio.timeout(timeout_s):
                job.status = AsyncJobStatus.RUNNING
                search = await asyncio.to_thread(
                    client.search_start,
                    pattern=job.query,
                    plugins=options.plugins,
                    category=options.category,
                    requests_args=request_args(),
                )
                while True:
                    if job.cancelled:
                        job.status = AsyncJobStatus.CANCELLED
                        return
                    results = await asyncio.to_thread(
                        client.search_results,
                        search_id=search.id,
                        requests_args=request_args(),
                    )
                    new_results = []
                    for result in results.results:
                        if result.fileUrl in seen_ids:
                            continue
                        seen_ids.add(result.fileUrl)
                        converted = self._convert_result(result)
                        new_results.append(converted)
                        if job.result is not None:
                            job.result.append(converted)
                        else:
                            job.result = [converted]
                    if new_results:
                        await self._search_job_manager.update(
                            SearchJobEvent(
                                job=job,
                                newly_discovered=new_results,
                            )
                        )
                    status = await asyncio.to_thread(
                        client.search_status,
                        search_id=search.id,
                        requests_args=request_args(),
                    )
                    if status and status[0].status != "Running":
                        break
                    await asyncio.sleep(0.5)
                job.status = AsyncJobStatus.COMPLETED
        except TimeoutError:
            timed_out = True
            job.status = AsyncJobStatus.COMPLETED if job.result_count else AsyncJobStatus.TIMEOUT
        except asyncio.CancelledError:
            job.status = AsyncJobStatus.CANCELLED
            raise
        except Exception as exc:
            if loop.time() >= deadline:
                timed_out = True
                job.status = AsyncJobStatus.COMPLETED if job.result_count else AsyncJobStatus.TIMEOUT
            else:
                job.status = AsyncJobStatus.FAILED
                job.status_msg = str(exc)
            _logger.exception("qBittorrent search %s failed", job.id)
        finally:
            if client is not None and search is not None and (timed_out or job.status == AsyncJobStatus.CANCELLED):
                try:
                    await asyncio.to_thread(
                        client.search_stop,
                        search_id=search.id,
                        requests_args={"timeout": 1.0},
                    )
                except Exception:
                    _logger.exception("Failed to stop qBittorrent search %s", search.id)
            try:
                if client is not None and search is not None:
                    await asyncio.to_thread(
                        client.search_delete,
                        search_id=search.id,
                        requests_args={"timeout": 1.0},
                    )
            except Exception:
                _logger.exception("Failed to delete qBittorrent search %s", search.id)

    def _convert_result(self, result: qbittorrentapi.SearchResultsDictionary) -> QBitTorrentSearchJobResult:
        return QBitTorrentSearchJobResult(
            source=self.name,
            id=result.fileUrl,
            title=result.fileName,
            metadata=QBitTorrentSearchResultMetadata(
                size_bytes=result.fileSize,
                seeders=result.nbSeeders or 0,
                leechers=result.nbLeechers,
                engine=result.fileName,
                torrent_url=result.fileUrl,
                site_url=result.descrLink,
            ),
        )
