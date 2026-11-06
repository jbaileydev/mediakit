from __future__ import annotations

from pydantic import BaseModel, Field

from mediakit.search import SearchJobResult, SearchOptions


class QBitTorrentSearchOptions(SearchOptions):
    plugins: list[str] = Field(default_factory=lambda: ["enabled"])
    category: str = "all"
    min_seeders: int | None = None


class QBitTorrentSearchResultMetadata(BaseModel):
    size_bytes: int | None
    seeders: int
    leechers: int
    engine: str
    torrent_url: str
    site_url: str | None


class QBitTorrentSearchJobResult(SearchJobResult):
    metadata: QBitTorrentSearchResultMetadata  # Narrow type
    # new fields
    id: str
    title: str
    thumbnail_url: str | None = None
