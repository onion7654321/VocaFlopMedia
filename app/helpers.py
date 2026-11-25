"""Pure functions for URL/quality/time/diagnostic processing."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from html import unescape

URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.IGNORECASE)
# Limit recognition to supported domains; other hosts are never passed silently.
SUPPORTED_DOMAINS = (
    "youtube.com", "youtu.be", "youtube-nocookie.com",
    "vimeo.com", "nicovideo.jp", "niconico.jp", "nico.ms",
    "x.com", "twitter.com", "facebook.com", "fb.watch", "fb.com",
    "soundcloud.com", "snd.sc", "spotify.com",
)


def supported_host(hostname: str | None) -> bool:
    host = (hostname or "").lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in SUPPORTED_DOMAINS)


def source_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    # Keep source labels for legacy history entries.
    if host.endswith(("bilibili.com", "b23.tv")):
        return "Bilibili"
    if host.endswith(("soundcloud.com", "snd.sc")):
        return "SoundCloud"
    if host.endswith("spotify.com"):
        return "Spotify"
    if host.endswith("vimeo.com"):
        return "Vimeo"
    if host.endswith(("nicovideo.jp", "niconico.jp", "nico.ms")):
        return "Niconico"
    if host == "x.com" or host.endswith(".x.com") or host.endswith("twitter.com"):
        return "X"
    if host.endswith(("facebook.com", "fb.com", "fb.watch")):
        return "Facebook"
    if host.endswith(("threads.net", "threads.com")):
        return "Threads"
    if host.endswith(("youtube.com", "youtu.be", "youtube-nocookie.com")):
        return "YouTube"
    return "Unknown"



def source_counts(urls: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for url in urls:
        name = source_name(url)
        counts[name] = counts.get(name, 0) + 1
    return counts


def parse_source_summary(urls: list[str]) -> str:
    counts = source_counts(urls)
    return "  ·  ".join(f"{name} {count}" for name, count in counts.items()) or "No links"


# Bilibili/Threads are removed from link parsing, and Spotify is classification-
# only: full-track downloads are not provided. Vimeo remains disabled.
UNAVAILABLE_SOURCES = {'Vimeo', 'Threads', 'Bilibili', 'Spotify', 'Unknown'}


def can_download(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme in ('http', 'https') and supported_host(parsed.hostname)
            and source_name(url) not in UNAVAILABLE_SOURCES)


def clean_url(url: str, mode: str = 'video') -> str:
    """Remove known tracking parameters without breaking access keys or part IDs.

    Preserve Vimeo h (unlisted video key), Bilibili p (multi-part page),
    Facebook video IDs and playlist identifiers. Never blindly remove all query.
    """
    raw = unescape(url.strip()).strip('\\')
    raw = raw.rstrip('.,;:!?)]}\u3002\uff0c')
    if raw.lower().startswith('www.'):
        raw = 'https://' + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ('https', 'http') or not supported_host(parsed.hostname):
        return ''
    host = (parsed.hostname or '').lower().rstrip('.')
    path = parsed.path or '/'
    params = parse_qs(parsed.query, keep_blank_values=False)
    retained: dict[str, list[str]] = {}

    def preserve(*keys: str):
        for key in keys:
            if key in params:
                retained[key] = params[key][:1]

    if host.endswith(('youtube.com', 'youtube-nocookie.com')):
        if path.rstrip('/') == '/watch':
            if mode == 'playlist' and params.get('list'):
                path = '/playlist'
                preserve('list')
            else:
                preserve('v')
                # A watch URL with only list= is a valid playlist link.
                if not params.get('v'):
                    preserve('list')
        elif path.rstrip('/') == '/playlist':
            preserve('list')
    elif host == 'youtu.be' or host.endswith('.youtu.be'):
        if mode == 'playlist' and params.get('list'):
            return clean_url('https://www.youtube.com/playlist?list=' + params['list'][0], 'playlist')
    elif host.endswith('bilibili.com'):
        if '/video/' in path.lower():
            preserve('p')  # Bilibili multi-part selection matters
    elif host.endswith('vimeo.com'):
        preserve('h')  # Vimeo unlisted links need their hash
    elif host.endswith('soundcloud.com'):
        # Preserve private SoundCloud access tokens.
        preserve('secret_token')
    elif host.endswith(('facebook.com', 'fb.com')):
        if path.rstrip('/') in ('/watch', '/watch/', '/video.php'):
            preserve('v')
        elif path.rstrip('/') in ('/story.php', '/permalink.php'):
            preserve('story_fbid', 'id')
        # Some Facebook links need the original video id in the query string.
        elif params.get('v') and 'video' in path.lower():
            preserve('v')
    # X, Niconico, fb.watch etc: keep URL path, remove known tracking query.
    query = urlencode(retained, doseq=True)
    # Preserve case-sensitive media IDs and redirect URLs.
    return urlunparse(('https', parsed.netloc.lower(), path, '', query, ''))


def extract_urls(text: str, mode: str = 'video') -> list[str]:
    """Pull supported, normalized, unique URLs out of captions or pasted prose."""
    seen: set[str] = set()
    found: list[str] = []
    for raw in URL_PATTERN.findall(re.sub(r"[,，](?=\s*(?:https?://|www\.))", " ", unescape(text), flags=re.I)):
        url = clean_url(raw, mode=mode)
        if url and url not in seen:
            found.append(url)
            seen.add(url)
    return found


def clean_pasted_text(text: str, mode: str = 'video') -> str:
    return '\n'.join(extract_urls(text, mode))


def is_playlist(url: str) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    path = p.path.lower().rstrip("/")
    if "youtube.com" in host or "youtu.be" in host:
        return bool(parse_qs(p.query).get("list")) or path.endswith("/playlist")
    if host.endswith(('soundcloud.com', 'snd.sc')):
        if host.endswith('snd.sc') or host.startswith('on.soundcloud.com'):
            return True  # Redirect target may be a set; yt-dlp resolves it.
        parts = [p for p in path.split('/') if p]
        if not parts:
            return False
        return (len(parts) == 1 or any(seg in path for seg in
                ('/sets/', '/albums/', '/likes', '/reposts', '/tracks', '/popular-tracks')))
    if "vimeo.com" in host:
        return any(segment in path for segment in ("/showcase/", "/album/", "/channels/", "/groups/"))
    if "bilibili.com" in host:
        return any(segment in path for segment in ("/list/", "/medialist/", "/favlist", "/space/", "/bangumi/play/ss"))
    if host.endswith(("nicovideo.jp", "niconico.jp", "nico.ms")):
        return any(segment in path for segment in ("/mylist/", "/series/", "/user/", "/search/"))
    return False


def get_resolutions(info: dict) -> list[int]:
    """Return up to four actual advertised video heights, descending."""
    formats = info.get("formats") or []
    values = set()
    for fmt in formats:
        height = fmt.get("height")
        if fmt.get("vcodec") != "none" and isinstance(height, (int, float)) and height > 0:
            values.add(int(height))
    if not values and info.get("height"):
        values.add(int(info["height"]))
    return sorted(values, reverse=True)[:4]


def to_seconds(s: str) -> int:
    s = s.strip()
    if not s:
        raise ValueError("Enter time as MM:SS or HH:MM:SS.")
    parts = s.split(":")
    if len(parts) not in (2, 3) or any(not p.isdigit() for p in parts):
        raise ValueError("Use MM:SS or HH:MM:SS.")
    numbers = list(map(int, parts))
    if any(x >= 60 for x in numbers[-2:]):
        raise ValueError("Minutes and seconds must be less than 60.")
    return numbers[0] * 60 + numbers[1] if len(numbers) == 2 else numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


def fmt_time(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02}:{m:02}:{s:02}"


def ffmpeg_location(setting: str = "") -> str | None:
    """Return directory usable by --ffmpeg-location (or None when missing)."""
    if setting:
        p = Path(setting).expanduser()
        if p.is_file() and p.name.lower() in ("ffmpeg.exe", "ffmpeg"):
            p = p.parent
        if (p / "ffmpeg.exe").is_file() or (p / "ffmpeg").is_file():
            return str(p)
    binary = shutil.which("ffmpeg")
    return str(Path(binary).parent) if binary else None


def readable_error(raw: str) -> str:
    low = raw.lower()
    if "javascript runtime" in low or "challenge solving" in low or "js runtime" in low or "deno" in low or "ejs" in low:
        return "Thiếu runtime JavaScript hoặc lỗi challenge solver. Cài Deno 2.x (install_deno_windows.bat), khởi động lại app rồi cập nhật yt-dlp."
    if "sign in to confirm" in low or "not a bot" in low:
        return "YouTube yêu cầu xác minh phiên truy cập. Hãy mở video trên trình duyệt; cập nhật yt-dlp và thử lại. Nếu video cần tài khoản, phiên bản này không tự lấy cookies."
    if "ffmpeg" in low and ("not found" in low or "not installed" in low or "could not" in low):
        return "Không thấy FFmpeg. Cài FFmpeg, mở lại ứng dụng hoặc chọn thư mục chứa ffmpeg.exe trong Cài đặt."
    if "requested format is not available" in low:
        return "Chất lượng đã chọn không khả dụng cho video này. Hãy chọn mức thấp hơn và thử lại."
    if "private video" in low or "video is private" in low:
        return "Video riêng tư, không thể tải nếu không có quyền truy cập."
    if "unavailable" in low or "not available" in low:
        return "Video không khả dụng / bị giới hạn vùng / đã xoá. Kiểm tra link trên YouTube."
    if "http error 429" in low or "too many requests" in low:
        return "YouTube đang giới hạn số yêu cầu. Hãy giảm số luồng tải và thử lại sau."
    if "http error 403" in low:
        return "HTTP 403: máy chủ từ chối truy cập. Hãy cập nhật yt-dlp, kiểm tra mạng và thử lại."
    if "max-filesize" in low or "larger than max" in low or "file is larger" in low:
        return "Dung lượng vượt giới hạn đã đặt trong Cài đặt. Hãy tăng giới hạn hoặc chọn chất lượng thấp hơn."
    if "unsupported url" in low:
        return "Link không được yt-dlp hỗ trợ. Kiểm tra định dạng link."
    if "unable to download webpage" in low or "timed out" in low or "certificate verify failed" in low:
        return "Lỗi kết nối mạng/chứng chỉ. Kiểm tra Internet, đồng hồ Windows, proxy và tường lửa."
    return "Không tải được. Mở 'Xem chi tiết lỗi' để xem log yt-dlp và kiểm tra URL, FFmpeg, mạng hoặc cập nhật yt-dlp."


def open_folder(path: str):
    if os.name == "nt":
        os.startfile(path)
    else:
        import subprocess
        subprocess.Popen(["xdg-open", path])
