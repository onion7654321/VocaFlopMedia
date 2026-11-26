from pathlib import Path
import hashlib

root = Path(__file__).resolve().parents[1] / 'release'
lines = []
for path in sorted(root.iterdir()):
    if path.is_file() and path.name.endswith(('.zip', '.tar.gz', '.exe', '.dmg', '.deb', '.AppImage')):
        with path.open('rb') as stream:
            digest = hashlib.sha256()
for chunk in iter(lambda: stream.read(1024 * 1024), b""):
    digest.update(chunk)

lines.append(f"{digest.hexdigest()}  {path.name}")
if not lines:
    raise SystemExit('No release packages found')
(root / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
