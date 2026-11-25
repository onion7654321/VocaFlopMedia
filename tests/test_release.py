"""Regression checks for release validation, output folders and history."""
from __future__ import annotations
import ast
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor

from app.core import download, FILE_MARK
from app.filenames import download_folder, existing_download
from app.helpers import to_seconds
from app.models import MediaItem, DownloadJob
from app.storage import History


def cut_handlers():
    source = Path(__file__).resolve().parents[1] / 'app' / 'ui.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'VocaflopUI')
    funcs = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in
             {'validate_cut', 'check_cut', 'edit_cut', 'clear_notice'}]
    ns = {'MediaItem': MediaItem, 'to_seconds': to_seconds}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(source), 'exec'), ns)
    ui = SimpleNamespace(_notice_scope=None)
    def notice(message, *, error=False, scope=None):
        ui._notice_scope = scope
        ui.message = message
    ui.notice = notice
    for fn in funcs:
        setattr(ui, fn.name, ns[fn.name].__get__(ui))
    return ui


class CutTests(unittest.TestCase):
    def test_corrected_cut_clears_inline_and_footer(self):
        ui = cut_handlers()
        item = MediaItem('https://youtu.be/test', start='02:00', end='01:00', duration=300)
        self.assertIsNone(ui.check_cut(item))
        self.assertEqual(item.cut_error, 'End time must be after start time.')
        warning = SimpleNamespace(controls=[None, SimpleNamespace(value=item.cut_error)], visible=True, update=Mock())
        ui.edit_cut(item, 'start', '00:00', warning)
        self.assertEqual(item.cut_error, '')
        self.assertFalse(warning.visible)
        self.assertEqual(ui.message, 'Ready')
        self.assertEqual(ui.validate_cut(item), (0, 60))

    def test_correction_preserves_unrelated_notice(self):
        ui = cut_handlers()
        item = MediaItem('https://youtu.be/a', start='bad')
        ui.check_cut(item)
        ui.notice('Another download failed', error=True, scope=('download', 'other'))
        item.start = '00:05'
        self.assertEqual(ui.check_cut(item), (5, None))
        self.assertEqual(ui.message, 'Another download failed')

    def test_start_and_end_bounds(self):
        ui = cut_handlers()
        item = MediaItem('https://youtu.be/a', duration=60, start='01:00')
        self.assertIsNone(ui.check_cut(item))
        item.start, item.end = '', '01:01'
        self.assertIsNone(ui.check_cut(item))
        item.end = '01:00'
        self.assertEqual(ui.check_cut(item), (0, 60))
        item.end = ''
        self.assertEqual(ui.check_cut(item), (None, None))


class FolderTests(unittest.TestCase):
    def test_actual_file_folder_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / 'chosen folder'; original.mkdir()
            other = Path(tmp) / 'new default'; other.mkdir()
            file = original / 'video.mp4'; file.write_bytes(b'media')
            self.assertEqual(download_folder(str(file), str(other)), original.resolve())

    def test_deleted_file_does_not_fall_back_to_existing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'video.mp4'
            file.write_bytes(b'media')
            self.assertEqual(existing_download([str(file)]), str(file))
            file.unlink()
            self.assertEqual(existing_download([str(file)]), '')
            with self.assertRaisesRegex(FileNotFoundError, 'Downloaded file'):
                download_folder(str(file), tmp)

    def test_playlist_uses_remaining_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'deleted.mp4'
            remaining = Path(tmp) / 'remaining.mp4'
            remaining.write_bytes(b'media')
            self.assertEqual(existing_download([str(missing), str(remaining)]), str(remaining))

    def test_playlist_and_missing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(download_folder('', tmp), Path(tmp).resolve())
            with self.assertRaises(FileNotFoundError):
                download_folder('', str(Path(tmp) / 'missing'))


class OutputTests(unittest.TestCase):
    def run_download(self, folder, script):
        job = DownloadJob('release-test', 'https://youtu.be/test', 'Test', 'video', 'mp4', 720, folder)
        async def run():
            with patch('app.core.command_for_job', return_value=[sys.executable, '-c', script]):
                return await download(job, {'max_size_mb': 0}, lambda *_: None, asyncio.Event())
        return asyncio.run(run())

    def test_exit_zero_without_file_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_download(tmp, 'pass')['status'], 'Failed')

    def test_zero_byte_output_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'empty.mp4'; file.touch()
            result = self.run_download(tmp, f'print({(FILE_MARK + str(file))!r})')
            self.assertEqual(result['status'], 'Failed')

    def test_existing_nonempty_output_is_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'video.mp4'; file.write_bytes(b'video')
            result = self.run_download(tmp, f'print({(FILE_MARK + str(file))!r})')
            self.assertEqual(result['status'], 'Completed')
            self.assertEqual(result['files'], [str(file)])

    def test_history_worker_thread_operations(self):
        with tempfile.TemporaryDirectory() as tmp, patch('app.storage.DB_FILE', Path(tmp) / 'history.sqlite3'), patch('app.storage.init_dirs'):
            history = History()
            try:
                def add(n):
                    history.create(dict(id=str(n), url='https://youtu.be/a', kind='mp4', quality='720', folder=tmp))
                    history.update(str(n), 'Completed', [str(Path(tmp) / f'{n}.mp4')])
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(add, range(12)))
                self.assertEqual(len(history.rows()), 12)
                self.assertTrue(all(r['status'] == 'Completed' for r in history.rows()))
            finally:
                history.close()


class PackageTests(unittest.TestCase):
    def test_package_full_folder_and_checksum(self):
        import hashlib
        import zipfile
        from scripts.package_release import package
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'app').mkdir()
            (root / 'app' / '__init__.py').write_text('__version__ = "2.11.4"', encoding='utf-8')
            build = root / 'dist' / 'Vocaflop'
            (build / '_internal').mkdir(parents=True)
            (build / 'Vocaflop.exe').write_bytes(b'fake executable')
            (build / '_internal' / 'runtime.dll').write_bytes(b'fake runtime')
            archive, checksum = package(root)
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), {'Vocaflop/Vocaflop.exe', 'Vocaflop/_internal/runtime.dll'})
                self.assertIsNone(z.testzip())
            self.assertEqual(checksum.read_text().split()[0], hashlib.sha256(archive.read_bytes()).hexdigest())
