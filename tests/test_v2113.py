"""Output formats, filename handling and clipboard regression tests."""
import ast
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.core import command_for_job, finalize_output_names
from app.filenames import safe_name, rename_file
from app.formats import AUDIO_FORMATS, VIDEO_FORMATS, available_formats, quality_choices, quality_label, output_extension
from app.helpers import extract_urls, can_download
from app.models import DownloadJob, MediaItem


def ui_methods(*names):
    """Load selected UI handlers without requiring a graphical Flet runtime."""
    source = Path(__file__).resolve().parents[1] / 'app' / 'ui.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'VocaflopUI')
    chosen = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    namespace = dict(Path=Path, safe_name=safe_name, rename_file=rename_file, output_extension=output_extension,
                     extract_urls=extract_urls, can_download=can_download)
    exec(compile(ast.Module(body=chosen, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


class OutputTests(unittest.TestCase):
    def test_all_output_formats_have_a_quality_and_command(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.core.ffmpeg_dir', return_value=folder), \
                patch('app.core.resolve_tool', return_value=Path(__file__)), patch('app.core.cli_exe', return_value='yt-dlp'):
            for kind in available_formats():
                with self.subTest(kind=kind):
                    q = quality_choices(kind, [1080, 720])[0]
                    job = DownloadJob('a', 'https://youtu.be/demo', 'Old', 'video', kind, q, folder, filename='New name')
                    cmd = command_for_job(job, {})
                    self.assertEqual(cmd[cmd.index('-o')+1], 'New name.%(ext)s')
                    if kind in AUDIO_FORMATS:
                        self.assertEqual(cmd[cmd.index('--audio-format')+1], 'vorbis' if kind == 'ogg' else kind)
                    else:
                        option = '--remux-video' if kind in ('mp4','mkv') else '--recode-video'
                        self.assertEqual(cmd[cmd.index(option)+1], kind)
                    self.assertTrue(quality_label(kind, q))

    def test_audio_only_choices(self):
        self.assertEqual(available_formats(True), AUDIO_FORMATS)
        self.assertEqual(quality_choices('wav'), [0])
        self.assertEqual(quality_choices('flac'), [0])
        self.assertNotIn(320, quality_choices('opus'))
        self.assertEqual(quality_label('mp4', 0), 'Best available')

    def test_pending_name_committed_before_job(self):
        methods = ui_methods('save_item_name', 'commit_pending_name')
        item = MediaItem('https://youtu.be/a', title='Old', kind='mp4')
        ui = SimpleNamespace(rename_drafts={item.id: 'New name.mp4'})
        ui.save_item_name = lambda i, v: methods['save_item_name'](ui, i, v)
        methods['commit_pending_name'](ui, item)
        self.assertEqual(item.filename, 'New name')
        self.assertNotIn(item.id, ui.rename_drafts)

    def test_final_output_uses_custom_name_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            job = DownloadJob('a', 'https://youtu.be/a', 'Old', 'video', 'mp4', 720, folder, filename='New')
            old = Path(folder) / 'Original.mp4'
            old.write_bytes(b'video')
            files = finalize_output_names(job, [str(old)])
            self.assertEqual(Path(files[0]).name, 'New.mp4')
            self.assertEqual(Path(files[0]).read_bytes(), b'video')
            old.write_bytes(b'other')
            with self.assertRaises(FileExistsError):
                finalize_output_names(job, [str(old)])
            self.assertEqual(old.read_bytes(), b'other')

    def test_clipboard_appends_new_links_once(self):
        paste = ui_methods('paste_clipboard_links')['paste_clipboard_links']
        field = SimpleNamespace(value='https://youtu.be/a', update=Mock())
        ui = SimpleNamespace(url_input=field, mode='video', last_clipboard_links=None,
                             clipboard=SimpleNamespace(get=AsyncMock(return_value='https://youtu.be/a, https://youtu.be/b')),
                             on_urls_changed=Mock())
        event = SimpleNamespace(control=field)
        asyncio.run(paste(ui, event))
        asyncio.run(paste(ui, event))
        self.assertEqual(extract_urls(field.value), ['https://youtu.be/a', 'https://youtu.be/b'])
        ui.on_urls_changed.assert_called_once()
        ui.clipboard.get.return_value = 'not a link'
        asyncio.run(paste(ui, event))
        self.assertEqual(len(extract_urls(field.value)), 2)

if __name__ == '__main__':
    unittest.main()
