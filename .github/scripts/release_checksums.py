from pathlib import Path
import hashlib

root = Path(__file__).resolve().parents[1] / 'release'
lines = []
for path in sorted(root.iterdir()):
    if path.name.endswith(('.zip', '.tar.gz')):
        with path.open('rb') as stream:
            lines.append(f'{hashlib.file_digest(stream, "sha256").hexdigest()}  {path.name}')
if not lines:
    raise SystemExit('No release packages found')
(root / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
