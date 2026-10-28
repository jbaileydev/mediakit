from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import ConfigDict, Field
from yt_dlp import YoutubeDL

from mediakit.enums import AudioFormat, AudioQuality, JobStatus, MediaVariant, VideoFormat, VideoQuality
from mediakit.sources.media_source import (
    AcquisitionJob,
    AcquisitionJobEvent,
    AcquisitionOptions,
    AcquisitionResult,
    JobManager,
    SearchOptions,
    SearchResult,
    SearchResultMetadata,
)


class YouTubeSearchResult(SearchResult):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    title: str
    metadata: YouTubeSearchResultMetadata  # Narrowing type


class YouTubeSearchResultMetadata(SearchResultMetadata):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    webpage_url: str | None
    channel: str | None
    duration_s: int | None
    thumbnail: str | None


class YouTubeSearchType(StrEnum):
    VIDEO = "video"
    PLAYLIST = "playlist"
    CHANNEL = "channel"
    ANY = "any"


class YoutubeSearchOptions(SearchOptions):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    max_results: int = 25
    search_type: YouTubeSearchType = YouTubeSearchType.VIDEO
    safe_search: bool = False
    channel: str | None = None
    min_duration_s: int | None = None
    max_duration_s: int | None = None
    uploaded_before: date | None = None
    uploaded_after: date | None = None


class YoutubeAcquisitionOptions(AcquisitionOptions):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    variant: MediaVariant = MediaVariant.AUDIO_VIDEO
    video_format: VideoFormat = VideoFormat.MP4
    video_quality: VideoQuality = VideoQuality.BEST
    audio_format: AudioFormat = AudioFormat.MP3
    audio_quality: AudioQuality = AudioQuality.ORIGINAL
    overwrite: bool = False
    playlist: bool = False
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    subtitles: bool = False
    srt: bool = False
    subtitle_languages: list[str] = Field(default_factory=list)
    output_dir: Path | None = None


class YouTubeSource:
    def __init__(self, job_manager: JobManager) -> None:
        self._job_manager = job_manager

    @property
    def name(self) -> str:
        return "youtube"

    @staticmethod
    def verify_dependencies() -> list[str]:
        errors: list[str] = []

        for dependency in ("ffmpeg", "ffprobe"):
            if shutil.which(dependency) is None:
                errors.append(f"{dependency} not found")

        return errors

    async def search(self, query: str, options: YoutubeSearchOptions | None = None) -> list[YouTubeSearchResult]:
        if options is None:
            options = YoutubeSearchOptions()

        search_query = f"ytsearch{options.max_results}:{query}"

        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
        }

        def run_search():
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(
                    search_query,
                    download=False,
                )

        data = await asyncio.to_thread(run_search)
        results: list[YouTubeSearchResult] = []
        for entry in data.get("entries", []):
            duration = entry.get("duration")
            if options.min_duration_s and duration and duration < options.min_duration_s:
                continue
            if options.max_duration_s and duration and duration > options.max_duration_s:
                continue
            channel = entry.get("channel")
            if options.channel and channel and options.channel != channel:
                continue
            results.append(
                YouTubeSearchResult(
                    source=self.name,
                    video_id=entry["id"],
                    title=entry["title"],
                    metadata=YouTubeSearchResultMetadata(
                        webpage_url=entry.get("webpage_url"),
                        channel=channel,
                        duration_s=duration,
                        thumbnail=entry.get("thumbnail"),
                    ),
                )
            )
        return results

    async def acquire(self, result: YouTubeSearchResult, options: YoutubeAcquisitionOptions | None = None) -> AcquisitionJob:
        if options is None:
            options = YoutubeAcquisitionOptions()
        job = AcquisitionJob(id=str(uuid.uuid4()), source=self.name, status=JobStatus.QUEUED)
        self._job_manager.create_job(job)
        asyncio.create_task(self._download(job, result, options))
        return job

    async def status(self, job_id: str) -> AcquisitionJob:
        return self._job_manager.get(job_id)

    async def _publish(self, job: AcquisitionJob, message: str | None = None, error: bool = False) -> None:
        await self._job_manager.update(AcquisitionJobEvent(job=job, message=message, error=error))

    async def _download(self, job: AcquisitionJob, result: YouTubeSearchResult, options: YoutubeAcquisitionOptions) -> None:
        loop = asyncio.get_running_loop()
        acquisition_result = AcquisitionResult()
        job.status = JobStatus.RUNNING
        job.progress = 0.0
        await self._publish(job, "Starting download")

        def progress_hook(data: dict) -> None:
            status = data.get("status")
            match status:
                case "downloading":
                    downloaded = data.get("downloaded_bytes", 0)
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    job.progress = downloaded / total * 100 if total else 0
                    job.speed_bps = data.get("speed")
                    job.eta_s = data.get("eta")
                    asyncio.run_coroutine_threadsafe(self._publish(job), loop)
                case "finished":
                    filename = data.get("filename")
                    if filename:
                        acquisition_result.files.append(Path(filename))
                case _:
                    pass

        try:
            ydl_opts = self._build_ydl_options(options, progress_hook=progress_hook)
            video_url = result.metadata.webpage_url or f"https://www.youtube.com/watch?v={result.video_id}"

            def run_download() -> dict:
                with YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(
                        video_url,
                        download=True,
                    )

            info = await asyncio.to_thread(run_download)

            acquisition_result.metadata = {
                "youtube_id": info.get("id"),
                "title": info.get("title"),
                "uploader": info.get(
                    "uploader",
                ),
                "channel": info.get(
                    "channel",
                ),
                "duration_s": info.get(
                    "duration",
                ),
                "thumbnail": info.get(
                    "thumbnail",
                ),
                "webpage_url": info.get(
                    "webpage_url",
                ),
                "upload_date": info.get(
                    "upload_date",
                ),
                "tags": info.get(
                    "tags",
                ),
                "categories": info.get(
                    "categories",
                ),
            }

            job.result = acquisition_result
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.speed_bps = None
            job.eta_s = None

            await self._publish(
                job,
                "Download complete",
            )

        except Exception as ex:
            job.status = JobStatus.FAILED
            job.speed_bps = None
            job.eta_s = None
            await self._publish(
                job,
                f"Download failed: {ex}",
                error=True,
            )

    def _build_ydl_options(self, options: YoutubeAcquisitionOptions, progress_hook: Callable[[dict], None] | None = None) -> dict[str, Any]:
        ydl_options = {
            "writethumbnail": options.embed_thumbnail,
            "embedmetadata": options.embed_metadata,
            "noplaylist": not options.playlist,
        }

        if options.output_dir:
            ydl_options["paths"] = {"home": str(options.output_dir)}

        if options.variant is MediaVariant.AUDIO:
            ydl_options["format"] = "bestaudio"
            ydl_options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": options.audio_format.value,
                }
            ]
        else:
            ydl_options["format"] = "bestvideo+bestaudio/best"
            ydl_options["merge_output_format"] = options.video_format.value

        if options.subtitles:
            ydl_options["writesubtitles"] = True
            if options.subtitle_languages:
                ydl_options["subtitleslangs"] = options.subtitle_languages
            if options.srt:
                ydl_options["subtitlesformat"] = "srt"

        if progress_hook:
            ydl_options["progress_hooks"] = [progress_hook]

        if options.overwrite:
            ydl_options["overwrites"] = True
            ydl_options["nooverwrites"] = False
        else:
            ydl_options["overwrites"] = False
            # ydl_options["download_archive"] = archive_file  # TODO: Implement me

        return ydl_options
