"""v2.8 UI/HTTP412 regressions."""
import ast
import asyncio
import unittest
from pathlib import Path
from app.helpers import clean_pasted_text, can_download, extract_urls, source_name
from app.core import _run_probe, ProbeError, download
from app.models import DownloadJob


class V28Tests(unittest.TestCase):
    def test_click_reads_clipboard_and_keeps_change_handler(self):
        source = (Path(__file__).parent.parent/'app/ui.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        class_node = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'VocaflopUI')
        init = next(x for x in class_node.body if isinstance(x, ast.FunctionDef) and x.name == '__init__')
        assignments = [node for node in ast.walk(init) if isinstance(node, ast.Assign) and
                       any(isinstance(t, ast.Attribute) and t.attr == 'url_input' for t in node.targets)]
        self.assertEqual(len(assignments), 1)
        text_field = assignments[0].value
        self.assertIsInstance(text_field, ast.Call)
        kwargs = {k.arg:k.value for k in text_field.keywords}
        self.assertEqual(kwargs['on_click'].attr, 'paste_clipboard_links')
        self.assertNotIn('on_focus', kwargs)
        self.assertIn('on_change', kwargs)
        self.assertNotIn('paste_if_empty', source)
        self.assertNotIn('Clipboard().get()', source)

    def test_bili_is_recognized_not_downloaded(self):
        urls = extract_urls('Some text https://www.bilibili.com/video/BV1xx411c7mD?p=1 more text')
        self.assertEqual(urls, [])
        self.assertFalse(can_download('https://www.bilibili.com/video/BV1xx411c7mD?p=1'))
        with self.assertRaises(ProbeError):
            _run_probe('https://www.bilibili.com/video/BV1xx411c7mD?p=1', False)

    def test_disabled_source_never_calls_download_api(self):
        job = DownloadJob(id='demo', url='https://www.bilibili.com/video/BV1xx411c7mD',
                          title='demo', mode='video', kind='mp4', quality=720, folder='.')
        class Flag:
            def is_set(self): return False
        result = asyncio.run(download(job, {}, lambda *_: None, Flag()))
        self.assertEqual(result['status'], 'Failed')
        self.assertIn('unsupported', result['error'])

    def test_others_still_enabled(self):
        for url in ('https://youtu.be/abc', 'https://www.nicovideo.jp/watch/sm1',
                    'https://www.facebook.com/watch/?v=1', 'https://x.com/name/status/1'):
            self.assertTrue(can_download(url), url)
