from __future__ import annotations

from pathlib import Path

from pydantic import Field

from mediakit.acquisition import AcquisitionJob, AcquisitionOptions


class QBitTorrentAcquisitionOptions(AcquisitionOptions):
    category: str | None = None
    save_path: Path | None = None
    paused: bool = False
    sequential_download: bool = False
    seed_after_download: bool = False
    tags: list[str] = Field(default_factory=list)


class QBitTorrentAcquisitionJob(AcquisitionJob):
    torrent_hash: str
    torrent_url: str
    title: str
