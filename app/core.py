"""Platform-independent yt-dlp CLI integration. All long operations are asynchronous."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Callable

from .helpers import extract_urls, fmt_time, get_resolutions, to_seconds, source_name, can_download
from .storage import APP_DIR, BIN_DIR, load_settings
from .toolchain import resolve_tool, executable_dir, tool_env, js_args
from .models import DownloadJob
from .filenames import safe_name, rename_file
from .formats import AUDIO_FORMATS, VIDEO_FORMATS, LOSSLESS_FORMATS, output_extension
from . import __version__
from .platforms import ytdlp_asset

YTDLP_PATH = BIN_DIR / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")
RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
MARK = "__VOCAFLOP_PROGRESS__"
FILE_MARK = "__VOCAFLOP_FILE__"
HEADERS = {"User-Agent": f"Vocaflop/{__version__}", "Accept": "application/vnd.github+json"}


def cli_exe() -> str:
    found = resolve_tool('yt-dlp')
    if found:
        return str(found)
    raise RuntimeError('yt-dlp not found. Add your tools folder in Settings or install an update.')


def ffmpeg_dir(custom: str = '') -> str | None:
    settings = load_settings()
    if custom:
        settings['ffmpeg_dir'] = custom
    return executable_dir('ffmpeg', settings)


def auth_args(settings: dict | None = None) -> list[str]:
    """Never read an active Chrome cookie database by default.

    Upgrading old installs must NOT enable cookies just because a browser was
    selected previously. A cookie-file is explicit and has precedence.
    """
    settings = settings if settings is not None else load_settings()
    file = str(settings.get('cookies_file', '')).strip()
    if file and Path(file).is_file():
        return ['--cookies', file]
    if not settings.get('use_browser_cookies', False):
        return []
    browser = str(settings.get('cookies_browser', 'none')).lower()
    return ['--cookies-from-browser', browser] if browser in {'chrome', 'edge', 'firefox', 'brave'} else []


def creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def partial_dir(job: DownloadJob) -> Path:
    key = hashlib.sha256((job.partial_key or job.id).encode()).hexdigest()[:24]
    return Path(job.folder) / '.vocaflop-partials' / key


def discard_partial(job: DownloadJob):
    folder = partial_dir(job)
    if folder.is_dir():
        shutil.rmtree(folder)
    try:
        folder.parent.rmdir()
    except OSError:
        pass


async def terminate_job(process):
    if process.returncode is not None:
        return
    if os.name == 'nt':
        killer = await asyncio.create_subprocess_exec('taskkill', '/PID', str(process.pid), '/T', '/F',
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            creationflags=creation_flags())
        await killer.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if process.returncode is None:
        try:
            await asyncio.wait_for(process.wait(), timeout=4)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


def command_for_job(job: DownloadJob, settings: dict) -> list[str]:
    if job.kind not in AUDIO_FORMATS + VIDEO_FORMATS:
        raise ValueError('Unsupported output format.')
    if source_name(job.url) == 'SoundCloud' and job.kind not in AUDIO_FORMATS:
        raise RuntimeError('SoundCloud is audio-only in Vocaflop. Choose an audio format.')
    ffdir = ffmpeg_dir(settings.get("ffmpeg_dir", ""))
    if not ffdir:
        raise RuntimeError("FFmpeg not found. Set its location in Settings.")
    if not can_download(job.url):
        raise RuntimeError(f'{source_name(job.url)} downloads are disabled in this release.')
    # Metadata and merge/extract operations require both executables.
    probe = resolve_tool('ffprobe', settings)
    if not probe or not probe.is_file():
        raise RuntimeError('FFprobe not found. FFmpeg and FFprobe must both be installed in Tools.')
    Path(job.folder).mkdir(parents=True, exist_ok=True)
    arguments = js_args(settings) + auth_args(settings)
    name = ("%(playlist_index)s - " if job.mode == "playlist" else "") + "%(title).180B [%(id)s].%(ext)s"
    if job.filename and job.mode != 'playlist':
        name = safe_name(job.filename).replace('%', '%%') + '.%(ext)s'
    cmd = [cli_exe(), *arguments, "--ignore-config", "--encoding", "utf-8", "--newline", "--no-color", "--windows-filenames",
           "--continue", "--no-overwrites", "--no-mtime", "--no-simulate", "--progress", "--retries", "5", "--fragment-retries", "5",
           "--concurrent-fragments", "3", "--ffmpeg-location", ffdir,
           "-P", str(partial_dir(job) / "replacement") if job.replace_existing else job.folder, "-P", f"temp:{partial_dir(job)}", "-o", name,
           "--progress-template", f"download:{MARK}%(progress._percent_str)s|%(progress.downloaded_bytes)s|%(progress.total_bytes_estimate)s|%(progress.total_bytes)s",
           "--print", "after_move:" + FILE_MARK + "%(filepath)j"]
    if job.mode == "playlist":
        cmd += ["--yes-playlist", "--no-abort-on-error"]
        max_items = int(settings.get("playlist_max_videos", 100))
        if max_items > 0:
            cmd += ["--playlist-end", str(max_items)]
    else:
        cmd += ["--no-playlist"]
    max_mb = int(settings.get("max_size_mb", 0))
    if max_mb:
        cmd += ["--max-filesize", f"{max_mb}M"]
    if job.kind in AUDIO_FORMATS:
        audio_format = "vorbis" if job.kind == "ogg" else job.kind
        cmd += ["-f", "bestaudio/best", "--extract-audio", "--audio-format", audio_format]
        if job.kind not in LOSSLESS_FORMATS:
            cmd += ["--audio-quality", f"{job.quality}K"]
    else:
        height = int(job.quality)
        cap = f'[height<={height}]' if height else ''
        fmt = (f'bv{cap}[ext=mp4]+ba[ext=m4a]/'
               f'b{cap}[ext=mp4]/'
               f'bv{cap}+ba/b{cap}')
        if job.kind == "webm":
            fmt = f'bv{cap}[ext=webm]+ba[ext=webm]/b{cap}[ext=webm]/bv{cap}+ba/b{cap}'
        elif job.kind == "mkv":
            fmt = f'bv{cap}+ba/b{cap}'
        merge_format = "webm/mkv" if job.kind == "webm" else job.kind if job.kind in ("mp4", "mkv") else "mkv"
        cmd += ["-f", fmt, "--merge-output-format", merge_format]
        if job.kind == "mp4":
            cmd += ["--remux-video", "mp4"]
        elif job.kind == "mkv":
            cmd += ["--remux-video", "mkv"]
        else:
            cmd += ["--recode-video", job.kind]
    if job.start is not None or job.end is not None:
        s = fmt_time(job.start or 0)
        end = fmt_time(job.end) if job.end is not None else "inf"
        cmd += ["--download-sections", f"*{s}-{end}", "--force-keyframes-at-cuts"]
    # Stream time is limited by the downloader watchdog; live media can't be guaranteed playable after force stop.
    cmd.append(job.url)
    return cmd


def finalize_output_names(job: DownloadJob, files: list[str]) -> list[str]:
    if not job.filename or job.mode == "playlist" or len(files) != 1:
        return files
    path = Path(files[0])
    if not path.is_file():
        raise FileNotFoundError(f"Downloaded file not found: {path}")
    if path.resolve().parent != Path(job.folder).resolve():
        raise ValueError("Downloaded file is outside the selected folder.")
    target = rename_file(path, job.filename)
    return [str(target)]


def readable_error(raw: str) -> str:
    txt = raw.lower()
    if 'could not copy chrome cookie database' in txt or 'unable to copy chrome cookie database' in txt:
        return ('Chrome is holding its cookie database open. Disable Browser cookies in Settings '
                'for public videos; for private videos, close Chrome fully or use a cookies.txt file.')
    if 'failed to decrypt' in txt and 'cookie' in txt:
        return 'Windows could not decrypt Chrome cookies. Use Firefox or a local cookies.txt file (Settings).'
    if 'unable to obtain file audio codec with ffprobe' in txt:
        return ('FFprobe cannot read the downloaded audio. The source stream may be invalid, incomplete or blocked. '
                'Update yt-dlp and retry; check the full log.')
    if 'invalid data found when processing input' in txt:
        return ('FFmpeg received invalid media data. The source may have returned a blocked or partial stream. '
                'Retry once, update yt-dlp, or try a different available format.')
    if 'ffprobe not found' in txt or ('ffprobe' in txt and 'not found' in txt):
        return 'FFprobe is missing. Place ffprobe next to ffmpeg in Tools.'
    if 'javascript' in txt or 'challenge' in txt or 'deno' in txt:
        return ('JavaScript challenge failed. Update yt-dlp, verify Deno 2.3+, and retry.' if resolve_tool('deno') else
                'A JavaScript challenge may require Deno. Set its folder under Settings → Tools & updates.')
    if any(x in txt for x in ('sign in', 'not a bot', 'login required', 'login to',
                              'cookies', 'authentication required', 'account is required')):
        return ('This video may require access or sign-in. For private videos, enable browser cookies '
                'or select a local cookies.txt file in Settings; public videos need neither.')
    if 'ffmpeg' in txt and ('not found' in txt or 'not installed' in txt or 'could not' in txt):
        return 'FFmpeg missing. Add its location in Settings.'
    if 'requested format' in txt:
        return 'Format unavailable. Try a different quality or format.'
    if 'private' in txt or 'members-only' in txt:
        return 'Video restricted. Access permission is required.'
    if '429' in txt or 'too many requests' in txt:
        return 'Rate limit reached. Reduce concurrent downloads.'
    if '403' in txt:
        return 'HTTP 403: access denied by the source. Check video access or update yt-dlp.'
    if 'timed out' in txt or 'unable to download' in txt:
        return 'Network error. Check the connection and retry.'
    if 'larger than max' in txt or 'max-filesize' in txt:
        return 'File exceeded the configured size limit.'
    if 'unsupported url' in txt or 'no suitable extractor' in txt:
        return 'No extractor for this URL. Check the link and update yt-dlp.'
    if 'unavailable' in txt:
        return 'Video unavailable. Check access, region, and URL.'
    return next((line[7:].strip()[:240] for line in reversed(raw.splitlines()) if line.startswith('ERROR: ')),
                'Download failed. Open Details to view the yt-dlp log.')


def _fetch_release() -> dict:
    req = urllib.request.Request(RELEASE_API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def _tool_version() -> str:
    try:
        result = subprocess.run([cli_exe(), "--version"], capture_output=True, text=True,
                                timeout=12, creationflags=creation_flags(), env=tool_env(load_settings()))
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return ""


def check_ytdlp_update() -> dict:
    """No download: compare local version to latest release tag."""
    latest = _fetch_release().get("tag_name", "")
    installed = _tool_version()
    return {"latest": latest, "installed": installed, "needs_update": not installed or (bool(latest) and latest != installed)}


def install_ytdlp(on_progress: Callable[[int], None] | None = None) -> str:
    """Install verified standalone yt-dlp binary atomically."""
    release = _fetch_release()
    exe_name = ytdlp_asset()
    asset = next((a for a in release.get("assets", []) if a.get("name") == exe_name), None)
    if not asset:
        raise RuntimeError(f"No {exe_name} in the official release.")
    expected = str(asset.get("digest") or "").removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        sums = next((a for a in release.get("assets", []) if a.get("name") == "SHA2-256SUMS"), None)
        if not sums:
            raise RuntimeError("Official SHA256 checksum not available.")
        req = urllib.request.Request(sums["browser_download_url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read(100_000).decode()
        m = re.search(r"(?m)^([0-9a-fA-F]{64})\s+\*?" + re.escape(exe_name) + r"\s*$", data)
        if not m:
            raise RuntimeError("Could not validate yt-dlp checksum.")
        expected = m.group(1).lower()
    url = asset["browser_download_url"]
    if urlparse(url).scheme != "https":
        raise RuntimeError("Unsafe update URL.")
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    temp = YTDLP_PATH.with_name(YTDLP_PATH.name + ".download")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        h = hashlib.sha256()
        loaded = 0
        total = int(asset.get("size") or 0)
        with urllib.request.urlopen(req, timeout=60) as response, temp.open("wb") as dest:
            while chunk := response.read(1024 * 1024):
                dest.write(chunk)
                h.update(chunk)
                loaded += len(chunk)
                if on_progress:
                    on_progress(round(100 * loaded / total) if total else 0)
        if h.hexdigest() != expected:
            raise RuntimeError("SHA256 mismatch. Update cancelled.")
        if os.name == "nt" and temp.open("rb").read(2) != b"MZ":
            raise RuntimeError("Downloaded file is not a valid Windows executable.")
        if os.name != "nt":
            temp.chmod(0o755)
        temp.replace(YTDLP_PATH)
        return str(release.get("tag_name") or "updated")
    finally:
        temp.unlink(missing_ok=True)




def select_playback_url(info: dict) -> str:
    """Find an accessible progressive URL for optional in-app Flet Video playback.

    yt-dlp DASH (video-only + audio-only) formats cannot be played directly this way.
    Some platforms require headers/cookies and will still refuse playback. No proxy.
    """
    choices = []
    for f in info.get("formats") or []:
        url = str(f.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        if f.get("vcodec") in (None, "none") or f.get("acodec") in (None, "none"):
            continue
        if f.get("ext") not in ("mp4", "webm") or f.get("protocol") not in ("https", "http", None):
            continue
        height = int(f.get("height") or 0)
        choices.append((f.get("ext") == "mp4", 0 < height <= 720, min(height, 720), url))
    choices.sort(reverse=True)
    return choices[0][-1] if choices else ""

class ProbeError(RuntimeError):
    """Readable error plus full local diagnostic output for the Details dialog."""
    def __init__(self, message: str, diagnostic: str):
        super().__init__(message)
        self.diagnostic = diagnostic


def _run_probe(url: str, playlist: bool) -> dict:
    if not can_download(url):
        raise ProbeError(f'{source_name(url)} is disabled in this release.',
                         'This source repeatedly failed on Windows; no download was started.')
    def fetch(link: str, extra: list[str]):
        settings = load_settings()
        p = subprocess.run([cli_exe(), *js_args(settings), *auth_args(settings), "--ignore-config", "--no-warnings", *extra,
                            "--dump-single-json", link], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=90,
                            creationflags=creation_flags(), env=tool_env(settings))
        if p.returncode != 0:
            raw = (p.stderr or p.stdout)[-3500:]
            raise ProbeError(readable_error(raw), raw)
        return json.loads(p.stdout)
    if playlist:
        # Flat metadata supports multiple playlist providers.
        flat = fetch(url, ["--yes-playlist", "--flat-playlist", "--playlist-items", "1"])
        if not flat.get("entries"):
            raise RuntimeError("This playlist has no accessible videos.")
        return {"title": flat.get("title") or "Playlist", "thumbnail": flat.get("thumbnail") or "",
                "channel": flat.get("channel") or flat.get("uploader") or "",
                "duration": None, "resolutions": [0], "is_live": False, "playback_url": ""}
    info = fetch(url, ["--no-playlist"])
    return {"title": info.get("title") or "Untitled video",
            "thumbnail": info.get("thumbnail") or "",
            "channel": info.get("channel") or info.get("uploader") or "",
            "duration": info.get("duration"), "resolutions": get_resolutions(info),
            "is_live": info.get("live_status") in {"is_live", "is_upcoming"},
            "playback_url": select_playback_url(info)}


async def probe(url: str, playlist: bool = False) -> dict:
    return await asyncio.to_thread(_run_probe, url, playlist)


async def download(job: DownloadJob, settings: dict, on_progress: Callable[[float, str], None],
                   cancel_event: asyncio.Event, stop_event: asyncio.Event | None = None) -> dict:
    """Stream progress and interrupt the job process tree on request."""
    if not can_download(job.url):
        source = source_name(job.url)
        message = ("Spotify downloads are not offered. Use Spotify's official offline playback."
                   if source == "Spotify" else f"{source} downloads are unsupported.")
        return {"status": "Failed", "files": [], "error": message, "log": message}
    cmd = command_for_job(job, settings)
    partial_dir(job).mkdir(parents=True, exist_ok=True)
    def interrupted():
        return cancel_event.is_set() or (stop_event is not None and stop_event.is_set())
    env = tool_env(settings)
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.STDOUT, "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = creation_flags()
    else:
        kwargs["start_new_session"] = True
    process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
    logs, files = [], []
    ended_by_limit = False
    hit_max = False
    start = time.monotonic()
    max_mb = int(settings.get("max_size_mb", 0))
    max_bytes = max_mb * 1024 * 1024
    live_seconds = max(1, int(settings.get("stream_limit_minutes", 60))) * 60 if job.mode == "stream" else 0
    try:
        while True:
            if interrupted():
                break
            remaining = max(0, live_seconds - (time.monotonic() - start)) if live_seconds else None
            if remaining is not None and remaining <= 0:
                ended_by_limit = True
                break
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=min(1, remaining) if remaining is not None else 1)
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                continue
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if MARK in raw:
                try:
                    values = raw.split(MARK, 1)[1].split("|")
                    pct = float(values[0].strip().strip("%"))
                    downloaded = int(values[1])
                    if max_bytes and downloaded > max_bytes:
                        hit_max = True
                        break
                    on_progress(max(0, min(.99, pct / 100)), f"Downloading {pct:.0f}%")
                except (ValueError, IndexError):
                    pass
            elif FILE_MARK in raw:
                filename = raw.split(FILE_MARK, 1)[1].strip()
                try:
                    decoded = json.loads(filename)
                    if isinstance(decoded, str):
                        filename = decoded
                except (ValueError, TypeError):
                    pass
                if filename not in files:
                    files.append(filename)
                on_progress(.99, "Processing...")
            elif raw:
                logs.append(raw)
                if len(logs) > 220:
                    logs = logs[-220:]
                if any(s in raw for s in ("[ExtractAudio]", "[Merger]", "[VideoRemuxer]", "[VideoConvertor]")):
                    on_progress(.99, "Converting...")
        if process.returncode is None:
            if interrupted() or ended_by_limit or hit_max:
                await terminate_job(process)
            else:
                await process.wait()
        all_logs = "\n".join(logs)
        if cancel_event.is_set():
            return {"status": "Cancelled", "files": files, "error": "Download cancelled.", "log": all_logs}
        if stop_event is not None and stop_event.is_set():
            return {"status": "Stopped", "files": files, "error": "", "log": all_logs}
        if hit_max:
            return {"status": "Failed", "files": files, "error": "Maximum download size exceeded.", "log": all_logs}
        if ended_by_limit:
            return {"status": "Limited", "files": files, "error": "Stream time limit reached; partial media may be unplayable.", "log": all_logs}
        if process.returncode:
            return {"status": "Failed", "files": files, "error": readable_error(all_logs), "log": all_logs}
        if any("ERROR:" in line for line in logs):
            return {"status": "Partial", "files": files, "error": "Some playlist items failed.", "log": all_logs}
        output_dir = partial_dir(job) / "replacement" if job.replace_existing else Path(job.folder)
        def valid_output(value):
            path = Path(value)
            return (path.is_file() and path.stat().st_size > 0
                    and path.resolve().parent == output_dir.resolve()
                    and path.suffix.lower() == "." + output_extension(job.kind))
        files = [str(Path(p)) for p in files if valid_output(p)]
        if not files:
            # Older extractors may report the final path in their normal messages.
            for line in reversed(logs):
                match = re.match(r'\[download\] (?:Destination: (.+)|(.+) has already been downloaded(?: and merged)?)$', line)
                if not match:
                    match = re.match(r'\[(?:Merger|ExtractAudio|VideoRemuxer|VideoConvertor)\].*?(?:Destination: |into ")(.*?)(?:"$|$)', line)
                if match:
                    candidate = next((v for v in match.groups() if v), "").strip('"')
                    if valid_output(candidate):
                        files.append(candidate)
                        if job.mode != "playlist":
                            break
            files = list(dict.fromkeys(files))
        if not files and job.filename and job.mode != "playlist":
            candidate = output_dir / (safe_name(job.filename) + "." + output_extension(job.kind))
            if valid_output(candidate):
                files = [str(candidate)]
        if not files:
            return {"status": "Failed", "files": files, "error": "No valid output file was created.", "log": all_logs}
        if max_bytes and any(Path(p).exists() and Path(p).stat().st_size > max_bytes for p in files):
            return {"status": "Limited", "files": files, "error": "Output exceeds size limit after merging.", "log": all_logs}
        if job.filename and job.mode != "playlist":
            try:
                if job.replace_existing:
                    if len(files) != 1:
                        raise ValueError("Expected one replacement file.")
                    target = Path(job.folder) / (safe_name(job.filename) + "." + output_extension(job.kind))
                    os.replace(files[0], target)
                    files = [str(target)]
                else:
                    files = finalize_output_names(job, files)
            except (OSError, ValueError) as ex:
                return {"status": "Failed", "files": files, "error": str(ex), "log": all_logs}
        return {"status": "Completed", "files": files, "error": "", "log": all_logs}
    finally:
        if process.returncode is None:
            await terminate_job(process)


def check_app_update(manifest_url: str) -> dict | None:
    """Check optional publisher-controlled HTTPS JSON manifest, never auto-run installers."""
    if not manifest_url:
        return None
    if not manifest_url.startswith("https://"):
        raise RuntimeError("App update URL must use HTTPS.")
    with urllib.request.urlopen(urllib.request.Request(manifest_url, headers=HEADERS), timeout=12) as response:
        data = json.loads(response.read(100_000))
    from packaging.version import Version
    if Version(str(data["version"])) <= Version(__version__):
        return None
    url = str(data["url"])
    digest = str(data.get("sha256") or "").lower()
    if urlparse(url).scheme != "https" or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise RuntimeError("Update needs HTTPS installer and SHA256 checksum.")
    return {"version": str(data["version"]), "url": url, "sha256": digest}


def stage_app_update(update: dict) -> Path:
    folder = APP_DIR / "updates"
    folder.mkdir(parents=True, exist_ok=True)
    suffix = next((x for x in (".tar.gz", ".zip", ".dmg", ".exe") if urlparse(update["url"]).path.lower().endswith(x)), ".downloaded")
    out = folder / f"Vocaflop_{re.sub('[^a-zA-Z0-9_.-]', '_', update['version'])}{suffix}"
    temp = out.with_suffix(".download")
    h = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(urllib.request.Request(update["url"], headers=HEADERS), timeout=60) as response, temp.open("wb") as dst:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 500 * 1024 * 1024:
                    raise RuntimeError("Installer exceeds 500 MB.")
                h.update(chunk)
                dst.write(chunk)
        if h.hexdigest() != update["sha256"] or temp.open("rb").read(2) != b"MZ":
            raise RuntimeError("Installer verification failed.")
        temp.replace(out)
        return out
    finally:
        temp.unlink(missing_ok=True)
