import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch
from app.core import download, FILE_MARK, partial_dir
from app.models import DownloadJob


def run(job, script):
    async def work():
        with patch('app.core.command_for_job', return_value=[sys.executable, '-c', script]):
            return await download(job, {'max_size_mb': 0}, lambda *_: None, asyncio.Event())
    return asyncio.run(work())


def test_unicode_marker(tmp_path):
    file = tmp_path / '日本語 – thử.mp4'
    job = DownloadJob('a', 'https://youtu.be/a', 'test', 'video', 'mp4', 480, str(tmp_path))
    result = run(job, f'from pathlib import Path; Path({str(file)!r}).write_bytes(b"media"); print({(FILE_MARK + json.dumps(str(file)))!r})')
    assert result['status'] == 'Completed'
    assert result['files'] == [str(file)]


def test_replace_preserves_old_on_failure(tmp_path):
    old = tmp_path / 'name.mp4'; old.write_bytes(b'old')
    job = DownloadJob('b', 'https://youtu.be/a', 'test', 'video', 'mp4', 480, str(tmp_path), filename='name', replace_existing=True)
    assert run(job, 'raise SystemExit(1)')['status'] == 'Failed'
    assert old.read_bytes() == b'old'
    new = partial_dir(job) / 'replacement' / old.name
    result = run(job, f'from pathlib import Path; p=Path({str(new)!r}); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"new"); print({(FILE_MARK + json.dumps(str(new)))!r})')
    assert result['status'] == 'Completed'
    assert old.read_bytes() == b'new'
    assert not new.exists()


def test_destination_fallback(tmp_path):
    file = tmp_path / 'video.mp4'
    job = DownloadJob('c', 'https://youtu.be/a', 'test', 'video', 'mp4', 480, str(tmp_path))
    result = run(job, f'from pathlib import Path; Path({str(file)!r}).write_bytes(b"media"); print({("[download] Destination: " + str(file))!r})')
    assert result['status'] == 'Completed'
