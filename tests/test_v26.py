import unittest
from unittest.mock import patch
from pathlib import Path
from app.helpers import extract_urls, can_download, source_name
from app.tool_updates import check_deno, check_ffmpeg, _expected_sha


class V26Tests(unittest.TestCase):
    def test_vimeo_threads_bilibili_disabled(self):
        self.assertFalse(can_download('https://www.bilibili.com/video/BV123'))
        self.assertFalse(can_download('https://vimeo.com/123'))
        self.assertFalse(can_download('https://threads.net/@abc/post/123'))

    def test_latest_deno_detected(self):
        release = {'tag_name': 'v2.6.0', 'assets': [
            {'name': 'deno-x86_64-pc-windows-msvc.zip', 'digest': 'sha256:'+'a'*64,
             'browser_download_url': 'https://github.com/denoland/deno/releases/download/v2.6.0/demo.zip'}]}
        with patch('app.tool_updates._get_json', return_value=release), \
             patch('app.tool_updates._version', return_value='2.5.0'):
            self.assertTrue(check_deno()['needs_update'])
        with patch('app.tool_updates._get_json', return_value=release), \
             patch('app.tool_updates._version', return_value='2.6.0'):
            self.assertFalse(check_deno()['needs_update'])

    def test_ffmpeg_stable_branch_version_not_daily_nightly(self):
        release = {'assets': [
            {'name': 'ffmpeg-n8.1-latest-win64-gpl-8.1.zip'},
            {'name': 'ffmpeg-n9.0-latest-win64-gpl-9.0.zip'},
            {'name': 'ffmpeg-master-latest-win64-gpl.zip'}]}
        with patch('app.tool_updates._get_json', return_value=release), \
             patch('app.tool_updates._version', return_value='8.1.2'):
            info = check_ffmpeg()
        self.assertTrue(info['needs_update'])
        self.assertEqual(info['asset_name'], 'ffmpeg-n9.0-latest-win64-gpl-9.0.zip')

    def test_verified_digest_required(self):
        release = {'assets': [{'name': 'deno-x86_64-pc-windows-msvc.zip',
                               'digest': 'sha256:'+'1'*64}]}
        self.assertEqual(_expected_sha(release, 'deno-x86_64-pc-windows-msvc.zip'), '1'*64)

    def test_ui_uses_native_context_menu_only(self):
        ui = (Path(__file__).parent.parent/'app/ui.py').read_text(encoding='utf8')
        self.assertNotIn('ft.ContextMenu(', ui)
        self.assertNotIn("content='Paste clipboard'", ui)
        self.assertNotIn('paste_if_empty', ui)
        self.assertIn('check_deno', ui)
        self.assertIn('check_ffmpeg', ui)

if __name__ == '__main__':
    unittest.main()
