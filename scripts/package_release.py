"""Package the Windows onedir build and write its SHA-256 checksum."""
from pathlib import Path
import hashlib
import re
import zipfile


def package(root: Path) -> tuple[Path, Path]:
    version_source = (root / 'app' / '__init__.py').read_text(encoding='utf-8')
    match = re.search(r'__version__\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+)["\']', version_source)
    if not match:
        raise ValueError('App version not found.')
    build = root / 'dist' / 'Vocaflop'
    if not (build / 'Vocaflop.exe').is_file() or not (build / '_internal').is_dir():
        raise FileNotFoundError('Build the complete Windows onedir application first.')
    release = root / 'release'
    release.mkdir(exist_ok=True)
    archive = release / f'Vocaflop-{match.group(1)}-Windows-x64.zip'
    temporary = archive.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(build.rglob('*')):
                if path.is_file():
                    z.write(path, path.relative_to(build.parent).as_posix())
        with zipfile.ZipFile(temporary) as z:
            bad = z.testzip()
            if bad:
                raise OSError(f'Archive verification failed: {bad}')
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    checksum = release / 'SHA256SUMS.txt'
    checksum.write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    return archive, checksum


if __name__ == '__main__':
    for output in package(Path(__file__).resolve().parents[1]):
        print(output)
