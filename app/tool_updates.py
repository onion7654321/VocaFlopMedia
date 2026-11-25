"""Opt-in, checksum-verified Windows tool upgrades.

Checks run on startup. Upgrades never run without a click. Releases are read
from the publishers on GitHub; downloaded archives must match a published SHA256.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from packaging.version import Version, InvalidVersion
from .storage import BIN_DIR, load_settings
from .toolchain import resolve_tool, tool_env
from .platforms import system, architecture, deno_asset, package_manager_hint

HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Vocaflop/2.6'}
DENO_API = 'https://api.github.com/repos/denoland/deno/releases/latest'
FFMPEG_API = 'https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest'


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=16) as response:
        return json.load(response)


def _version(name: str) -> str:
    binary = resolve_tool(name)
    if not binary:
        return ''
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        p = subprocess.run([str(binary), '-version' if name == 'ffmpeg' else '--version'],
                           capture_output=True, text=True, timeout=12,
                           creationflags=flags, env=tool_env(load_settings()))
        if p.returncode:
            return ''
        text = p.stdout or ''
        if name == 'deno':
            m = re.search(r'(?m)^deno\s+(\d+\.\d+\.\d+)', text)
        else:
            m = re.search(r'(?m)^ffmpeg version\s+n?(\d+\.\d+(?:\.\d+)?)', text)
        return m.group(1) if m else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def _asset(release: dict, name: str) -> dict:
    return next((asset for asset in release.get('assets', []) if asset.get('name') == name), {})


def check_deno() -> dict:
    release = _get_json(DENO_API)
    latest = release.get('tag_name', '').lstrip('v')
    installed = _version('deno')
    if not latest or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-.][\w.-]+)?', latest):
        raise ValueError('Invalid Deno release version')
    try:
        newer = not installed or Version(latest) > Version(installed)
    except InvalidVersion:
        newer = not installed
    asset_name = deno_asset()
    if not _asset(release, asset_name):
        raise ValueError('Deno asset unavailable for this platform')
    return {'name': 'deno', 'installed': installed or 'missing', 'latest': latest,
            'needs_update': newer, 'release': release, 'asset_name': asset_name}


def check_ffmpeg() -> dict:
    if system() != "Windows" or architecture() != "x64":
        return {"name": "ffmpeg", "installed": _version("ffmpeg") or "missing", "needs_update": False, "manual": package_manager_hint()}
    release = _get_json(FFMPEG_API)
    # Compare stable branches rather than daily build IDs.
    names = [a.get('name', '') for a in release.get('assets', [])]
    choices = []
    for name in names:
        m = re.fullmatch(r'ffmpeg-n(\d+\.\d+)-latest-win64-gpl-\1\.zip', name)
        if m:
            choices.append((Version(m.group(1)), name))
    if not choices:
        raise ValueError('No stable Windows FFmpeg build in provider release')
    v, asset_name = max(choices)
    installed = _version('ffmpeg')
    if not installed:
        # Unknown format such as N-xxxx git build: do not force an upgrade.
        newer = resolve_tool('ffmpeg') is None
    else:
        try:
            newer = Version(installed) < v
        except InvalidVersion:
            newer = False
    return {'name': 'ffmpeg', 'installed': installed or ('unknown' if resolve_tool('ffmpeg') else 'missing'),
            'latest': str(v), 'needs_update': newer,
            'release': release, 'asset_name': asset_name}


def _expected_sha(release: dict, asset_name: str) -> str:
    asset = _asset(release, asset_name)
    expected = str(asset.get('digest') or '').removeprefix('sha256:').lower()
    if re.fullmatch(r'[0-9a-f]{64}', expected):
        return expected
    # Fallback to published checksum manifest (not a user-supplied URL).
    checksum_name = f'{asset_name}.sha256sum' if asset_name.startswith('deno-') else 'checksums.sha256'
    checksum_asset = _asset(release, checksum_name)
    url = checksum_asset.get('browser_download_url', '')
    if not url.startswith('https://github.com/'):
        raise RuntimeError('Published checksum unavailable; update cancelled.')
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as response:
        content = response.read(200_000).decode('utf-8', errors='replace')
    match = re.search(r'(?m)^([0-9a-fA-F]{64})\s+\*?' + re.escape(asset_name) + r'\s*$', content)
    if not match:
        raise RuntimeError('Checksum not found for tool archive.')
    return match.group(1).lower()


def install_tool(info: dict) -> str:
    """Install to app-owned AppData folder. Never overwrite arbitrary PATH binaries."""
    name = info['name']
    if name not in ('deno', 'ffmpeg'):
        raise ValueError('Unexpected tool')
    if name == 'ffmpeg' and (system() != 'Windows' or architecture() != 'x64'):
        raise RuntimeError(package_manager_hint())
    asset_name = info['asset_name']
    if name == 'deno' and asset_name != deno_asset():
        raise ValueError('Incorrect Deno platform archive')
    release = info['release']
    source = _asset(release, asset_name).get('browser_download_url', '')
    if not source.startswith('https://github.com/'):
        raise RuntimeError('Update download source invalid')
    expected = _expected_sha(release, asset_name)
    limit = 270 * 1024 * 1024 if name == 'ffmpeg' else 65 * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix='vocaflop-tool-') as td:
        archive = Path(td) / 'payload.zip'
        h = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(urllib.request.Request(source, headers=HEADERS), timeout=90) as resp, archive.open('wb') as fp:
            while block := resp.read(1024 * 1024):
                size += len(block)
                if size > limit:
                    raise RuntimeError('Tool archive too large; installation cancelled')
                fp.write(block)
                h.update(block)
        if h.hexdigest() != expected:
            raise RuntimeError('Tool SHA256 mismatch; installation cancelled')
        target = BIN_DIR / ('deno' if name == 'deno' else 'ffmpeg/bin')
        target.mkdir(parents=True, exist_ok=True)
        wanted = {('deno.exe' if system() == 'Windows' else 'deno')} if name == 'deno' else {'ffmpeg.exe', 'ffprobe.exe'}
        with zipfile.ZipFile(archive) as z:
            entries = {Path(x.filename.replace('\\', '/')).name.lower(): x
                       for x in z.infolist() if not x.is_dir() and
                       Path(x.filename.replace('\\', '/')).name.lower() in wanted}
            if not wanted.issubset(entries):
                raise RuntimeError('Required executable missing from verified archive')
            for binary in wanted:
                infofile = entries[binary]
                if infofile.file_size > 350 * 1024 * 1024:
                    raise RuntimeError('Executable size exceeds safe limit')
                temp_out = target / (binary + '.new')
                with z.open(infofile) as src, temp_out.open('wb') as dst:
                    while block := src.read(1024 * 1024):
                        dst.write(block)
            for binary in wanted:
                if system() != 'Windows':
                    (target / (binary + '.new')).chmod(0o755)
                (target / (binary + '.new')).replace(target / binary)
    return f'{name.upper()} {info["latest"]} installed. Restart Vocaflop.'
