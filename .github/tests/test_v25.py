"""Regression tests for v2.5 settings/clipboard/batch fixes and supported sources."""
from pathlib import Path
import ast
import unittest
from unittest.mock import patch
from app.helpers import extract_urls, can_download, source_name
from app.core import _tool_version, _run_probe, ProbeError


class V25Tests(unittest.TestCase):
    def test_supported_sources_only(self):
        text = """https://youtu.be/demo
        https://www.nicovideo.jp/watch/sm123
        https://x.com/demo/status/777
        https://www.facebook.com/watch/?v=123
        https://www.bilibili.com/video/BV11
        https://vimeo.com/1234
        https://threads.net/@demo/post/123"""
        urls = extract_urls(text)
        enabled = [source_name(url) for url in urls if can_download(url)]
        self.assertEqual(enabled, ['YouTube', 'Niconico', 'X', 'Facebook'])
        self.assertEqual(len(urls), 5)

    def test_disabled_extractors_blocked_before_probe(self):
        for url in ('https://vimeo.com/1234',
                    'https://threads.net/@x/post/1'):
            with self.subTest(url=url), self.assertRaises(ProbeError):
                _run_probe(url, False)

    def test_version_check_no_undefined_settings(self):
        class Proc:
            stdout = '2026.10.25\n'
            returncode = 0
        with patch('app.core.cli_exe', return_value='yt-dlp.exe'), \
             patch('app.core.subprocess.run', return_value=Proc()) as run:
            self.assertEqual(_tool_version(), '2026.10.25')
            self.assertTrue(run.called)

    def test_settings_does_not_reconstruct_page_on_control_change(self):
        ui = (Path(__file__).parent.parent/'app/ui.py').read_text(encoding='utf8')
        tree = ast.parse(ui)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'VocaflopUI')
        functions = {node.name: node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ('persist','browse_download_dir','browse_tool_dir','clear_cookie_file','set_preview_setting'):
            method = functions[name]
            calls = [node.func.attr for node in ast.walk(method)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
            self.assertNotIn('render_settings', calls, msg=name)
            self.assertNotIn('select_tab', calls, msg=name)

    def test_shared_mode_and_native_clipboard_are_connected_to_ui(self):
        ui = (Path(__file__).parent.parent/'app/ui.py').read_text(encoding='utf8')
        self.assertIn('self.batch_area.controls = self.batch_controls()', ui)
        self.assertIn('self.batch_area,', ui)
        self.assertIn('self.refresh_batch_controls()', ui)
        self.assertNotIn("content='Paste clipboard'", ui)
        self.assertNotIn('ft.ContextMenu(', ui)
        self.assertNotIn('paste_if_empty', ui)
        self.assertNotIn('await ft.Clipboard().get()', ui)

if __name__ == '__main__':
    unittest.main()
