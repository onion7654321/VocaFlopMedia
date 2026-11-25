"""Filename validation and collision-safe local renaming."""
import os
import re
from pathlib import Path


def safe_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value.strip()).rstrip(' .')
    if not name or name in ('.', '..'):
        raise ValueError('Enter a valid filename.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        name = '_' + name
    return name[:150].rstrip(' .')


def rename_file(path: Path, name: str) -> Path:
    name = safe_name(name)
    if name.lower().endswith(path.suffix.lower()):
        name = name[:-len(path.suffix)]
    target = path.with_name(safe_name(name) + path.suffix)
    if path == target:
        return path
    if target.exists():
        raise FileExistsError('A file with that name already exists.')
    if os.name == "nt":
        path.rename(target)
        return target
    # Reserve the destination without overwriting an existing file.
    os.link(path, target)
    try:
        path.unlink()
    except OSError:
        target.unlink()
        raise
    return target


def download_folder(file: str = "", folder: str = "") -> Path:
    """Resolve the actual output location, not the current download setting."""
    if file:
        path = Path(file).expanduser()
        if not path.is_file():
            raise FileNotFoundError("Downloaded file no longer exists.")
        return path.parent.resolve()
    if folder:
        path = Path(folder).expanduser()
        if path.is_dir():
            return path.resolve()
    raise FileNotFoundError("Download folder no longer exists.")


def existing_download(files):
    """Return the first output file still present on disk."""
    return next((str(file) for file in files if file and Path(file).expanduser().is_file()), "")
