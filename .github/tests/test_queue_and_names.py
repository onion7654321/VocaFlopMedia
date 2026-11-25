import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import command_for_job, discard_partial, download, partial_dir
from app.filenames import rename_file, safe_name
from app.helpers import extract_urls
from app.models import DownloadJob


class QueueAndNameTests(unittest.TestCase):
    def job(self, folder, **kwargs):
        return DownloadJob('test-job', 'https://youtu.be/demo', 'Demo', 'video', 'mp4', 720, folder, **kwargs)

    def test_comma_and_space_separators(self):
        self.assertEqual(len(extract_urls('https://youtu.be/a,https://youtu.be/b, https://youtu.be/c https://youtu.be/d')), 4)

    def test_windows_names(self):
        self.assertEqual(safe_name('CON'), '_CON')
        self.assertEqual(safe_name('a/b: c'), 'a_b_ c')
        with self.assertRaises(ValueError):
            safe_name('  ...  ')

    def test_local_rename_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / 'old.mp3'
            original.write_bytes(b'audio')
            target = rename_file(original, 'new.mp3')
            self.assertEqual(target.name, 'new.mp3')
            self.assertFalse(original.exists())
            self.assertEqual(target.read_bytes(), b'audio')
            original.write_bytes(b'other')
            with self.assertRaises(FileExistsError):
                rename_file(original, 'new')
            self.assertEqual(original.read_bytes(), b'other')

    def test_custom_output_template(self):
        with tempfile.TemporaryDirectory() as d, patch('app.core.ffmpeg_dir', return_value=d), \
                patch('app.core.cli_exe', return_value='yt-dlp'), patch('app.core.resolve_tool', return_value=Path(__file__)):
            job = self.job(d, filename='100% done')
            cmd = command_for_job(job, {})
            self.assertEqual(cmd[cmd.index('-o')+1], '100%% done.%(ext)s')
            self.assertIn(f'temp:{partial_dir(job)}', cmd)

    def test_discard_only_job_temp_files(self):
        with tempfile.TemporaryDirectory() as d:
            job = self.job(d)
            part = partial_dir(job)
            part.mkdir(parents=True)
            (part / 'video.part').write_bytes(b'partial')
            other = part.parent / 'other-job'
            other.mkdir()
            final = Path(d) / 'finished.mp4'
            final.write_bytes(b'complete')
            discard_partial(job)
            self.assertFalse(part.exists())
            self.assertTrue(other.exists())
            self.assertTrue(final.exists())

    def test_interrupt_subprocess(self):
        async def run(folder, cancel):
            stop, abort = asyncio.Event(), asyncio.Event()
            async def interrupt():
                await asyncio.sleep(.05)
                (abort if cancel else stop).set()
            task = asyncio.create_task(interrupt())
            with patch('app.core.command_for_job', return_value=[sys.executable, '-c', 'import time; time.sleep(10)']):
                result = await download(self.job(folder), {}, lambda *_: None, abort, stop)
            await task
            return result['status']
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(asyncio.run(run(d, False)), 'Stopped')
            self.assertEqual(asyncio.run(run(d, True)), 'Cancelled')


if __name__ == '__main__':
    unittest.main()
