"""Offline regression coverage for URLs, cookie lock handling and page flow."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.helpers import clean_url, clean_pasted_text, extract_urls, can_download, source_name
from app.core import auth_args, command_for_job, readable_error, ProbeError, _run_probe
from app.models import DownloadJob
from app.storage import DEFAULT_SETTINGS


class V24Tests(unittest.TestCase):
    def test_tracking_stripped_and_noise_removed(self):
        raw = '''Click https://www.youtube.com/watch?v=abc123&si=qwer&feature=share !!!
        Bilibili https://www.bilibili.com/video/BV123/?spm_id_from=333.999&p=3&vd_source=secret
        More text! https://youtu.be/xyz?si=abc .
        https://www.youtube.com/watch?v=abc123&list=PLABC&si=123'''
        cleaned = clean_pasted_text(raw)
        lines = cleaned.splitlines()
        self.assertEqual(lines[0], 'https://www.youtube.com/watch?v=abc123')
        self.assertEqual(lines[1], 'https://youtu.be/xyz')
        self.assertEqual(len(lines), 2)  # Bilibili omitted, duplicates collapse

    def test_playlist_preserves_list(self):
        url = 'https://www.youtube.com/watch?v=abc&list=PLXYZ&si=share'
        self.assertEqual(clean_url(url, 'playlist'), 'https://www.youtube.com/playlist?list=PLXYZ')
        self.assertEqual(clean_url('https://youtube.com/playlist?list=PLXYZ&feature=share'),
                         'https://youtube.com/playlist?list=PLXYZ')

    def test_unlisted_vimeo_key_preserved(self):
        u = 'https://vimeo.com/12345678?h=abcdef123&share=copy'
        self.assertEqual(clean_url(u), 'https://vimeo.com/12345678?h=abcdef123')

    def test_facebook_video_id_preserved(self):
        self.assertEqual(clean_url('https://www.facebook.com/watch/?v=1234&ref=sharing'),
                         'https://www.facebook.com/watch/?v=1234')

    def test_no_forged_host(self):
        links = extract_urls('url: https://youtube.com.evil.test/watch?v=1 https://www.youtube.com/watch?v=a')
        self.assertEqual(links, ['https://www.youtube.com/watch?v=a'])

    def test_threads_explicitly_unavailable(self):
        link = 'https://www.threads.net/@user/post/123'
        self.assertEqual(extract_urls(link), [])
        self.assertFalse(can_download(link))
        with self.assertRaises(ProbeError):
            _run_probe(link, False)

    def test_existing_chrome_selection_does_not_force_cookies(self):
        self.assertEqual(auth_args({'cookies_browser': 'chrome'}), [])
        self.assertEqual(auth_args({'cookies_browser': 'chrome', 'use_browser_cookies': True}),
                         ['--cookies-from-browser', 'chrome'])
        self.assertIs(DEFAULT_SETTINGS['use_browser_cookies'], False)

    def test_cookiefile_explicit_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie_file = Path(tmp)/'cookies.txt'
            cookie_file.write_text('# Netscape HTTP Cookie File\n', encoding='utf8')
            self.assertEqual(auth_args({'cookies_file': str(cookie_file),
                                        'cookies_browser': 'chrome', 'use_browser_cookies': False}),
                             ['--cookies', str(cookie_file)])

    def test_specific_error_messages(self):
        self.assertIn('Chrome', readable_error('ERROR: Could not copy Chrome cookie database'))
        self.assertIn('FFprobe', readable_error('Postprocessing: WARNING: unable to obtain file audio codec with ffprobe'))
        self.assertIn('FFmpeg', readable_error('Invalid data found when processing input'))

    def test_bilibili_disabled_after_http_412(self):
        self.assertFalse(can_download('https://www.bilibili.com/video/BVabc'))

    def test_full_page_scroll_structure_is_statically_present(self):
        ui_src = (Path(__file__).parent.parent/'app/ui.py').read_text(encoding='utf8')
        self.assertIn('self.video_list = ft.Column(', ui_src)
        self.assertNotIn('self.video_list = ft.ListView(', ui_src)
        self.assertIn('scroll=ft.ScrollMode.AUTO,', ui_src)
        self.assertIn('def clean_links(', ui_src)


if __name__ == '__main__':
    unittest.main()
