"""Robust, relocation-safe discovery for shipped and user-selected tool folders."""
from __future__ import annotations
import os
import sys
import shutil
from pathlib import Path
from .storage import BIN_DIR, LEGACY_DIR, load_settings


def project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def roots(settings: dict | None = None) -> list[Path]:
    settings = settings if settings is not None else load_settings()
    base = project_root()
    choices = [settings.get('tools_dir', ''), BIN_DIR, base, base / 'tools',
               Path(sys.executable).resolve().parent,
               LEGACY_DIR / 'tools']
    if hasattr(sys, '_MEIPASS'):
        choices += [Path(sys._MEIPASS), Path(sys._MEIPASS) / 'tools']
    ordered = []
    for choice in choices:
        if not choice:
            continue
        root = Path(choice).expanduser()
        if root.is_file():
            root = root.parent
        if root not in ordered:
            ordered.append(root)
    return ordered


def resolve_tool(name: str, settings: dict | None = None) -> Path | None:
    if name not in ('yt-dlp', 'ffmpeg', 'ffprobe', 'deno'):
        raise ValueError('Unsupported tool')
    settings = settings if settings is not None else load_settings()
    exe = f'{name}.exe' if os.name == 'nt' else name
    override = (settings.get('ffmpeg_dir', '') if name in ('ffmpeg', 'ffprobe')
                else settings.get('deno_dir', '') if name == 'deno' else '')
    dirs = [override] if override else []
    if name == 'yt-dlp':
        # Keep the verified app-managed yt-dlp ahead of bundled or custom copies.
        dirs = [BIN_DIR] + [p for p in roots(settings) if p != BIN_DIR]
    else:
        dirs += roots(settings)
    suffixes = (Path('.'), Path('tools'), Path('bin'), Path('ffmpeg'),
                Path('ffmpeg/bin'), Path('tools/ffmpeg'), Path('tools/ffmpeg/bin'),
                Path('deno'), Path('tools/deno'))
    seen = set()
    for folder in dirs:
        base = Path(folder).expanduser()
        if base.is_file() and base.name.lower() == exe.lower():
            return base
        for suffix in suffixes:
            candidate = base / suffix / exe
            if str(candidate) not in seen:
                seen.add(str(candidate))
                if candidate.is_file():
                    return candidate.resolve()
    found = shutil.which(exe)
    if not found and sys.platform == 'darwin':
        found = next((str(p) for d in ('/opt/homebrew/bin', '/usr/local/bin') if (p := Path(d) / exe).is_file() and os.access(p, os.X_OK)), None)
    return Path(found).resolve() if found else None


def executable_dir(name: str, settings: dict | None = None) -> str | None:
    found = resolve_tool(name, settings)
    return str(found.parent) if found else None


def tool_env(settings: dict | None = None) -> dict[str, str]:
    settings = settings if settings is not None else load_settings()
    env = os.environ.copy()
    dirs = []
    for name in ('yt-dlp', 'ffmpeg', 'deno'):
        binary = resolve_tool(name, settings)
        if binary and str(binary.parent) not in dirs:
            dirs.append(str(binary.parent))
    env['PATH'] = os.pathsep.join(dirs + [env.get('PATH', '')])
    return env


def js_args(settings: dict | None = None) -> list[str]:
    binary = resolve_tool('deno', settings)
    # An absolute path avoids dependency on VS Code / Windows environment PATH.
    return ['--js-runtimes', f'deno:{binary}'] if binary else []
