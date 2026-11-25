from __future__ import annotations
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class MediaItem:
    url: str
    mode: str = "video"   # video | playlist | stream
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "Loading video..."
    channel: str = ""
    thumbnail: str = ""
    duration: int | None = None
    resolutions: list[int] = field(default_factory=list)
    audio_rates: list[int] = field(default_factory=lambda: [320, 256, 192, 128])
    kind: str = "mp4"  # SoundCloud items override this to mp3 on creation
    quality: int | None = None
    start: str = ""
    end: str = ""
    status: str = "Loading..."
    progress: float = 0
    busy: bool = False
    show_qualities: bool = False
    error: str = ""
    log: str = ""
    is_live: bool = False
    preview_ready: bool = False
    playback_url: str = ""
    downloaded_file: str = ""
    collapsed: bool = False
    filename: str = ""
    cut_error: str = ""
    download_folder: str = ""
    downloaded_files: list[str] = field(default_factory=list)


@dataclass
class DownloadJob:
    id: str
    url: str
    title: str
    mode: str
    kind: str
    quality: int
    folder: str
    start: int | None = None
    end: int | None = None
    filename: str = ""
    partial_key: str = ""
    completed_files: list[str] = field(default_factory=list)
    replace_existing: bool = False
