from __future__ import annotations

from enum import StrEnum


class MediaVariant(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    AUDIO_VIDEO = "audio-video"


class AudioFormat(StrEnum):
    MP3 = "mp3"
    M4A = "m4a"
    FLAC = "flac"
    OPUS = "opus"


class AudioQuality(StrEnum):
    ORIGINAL = "original"
    BEST = "best"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class VideoFormat(StrEnum):
    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"


class VideoQuality(StrEnum):
    BEST = "best"
    UHD_2160P = "2160p"
    QHD_1440P = "1440p"
    FHD_1080P = "1080p"
    HD_720P = "720p"
    SD_480P = "480p"
    WORST = "worst"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
