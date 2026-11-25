"""Offline regression coverage for supported hosts and native player metadata."""
import unittest
from unittest.mock import patch

from app.helpers import extract_urls, is_playlist, source_name, supported_host
from app.core import select_playback_url, _run_probe
from app.storage import DEFAULT_SETTINGS


class SourcesTests(unittest.TestCase):
    def test_four_platforms_and_shortlinks(self):
        links = extract_urls('''
            https://www.youtube.com/watch?v=abc123
            https://www.bilibili.com/video/BV1abc123/
            https://b23.tv/abcdef
            https://vimeo.com/12345678
            https://www.nicovideo.jp/watch/sm123456
            https://nico.ms/sm123456
            https://bilibili.com.evil-site.test/fake
            https://vimeo.com@evil-site.test/123
        ''')
        self.assertEqual(len(links), 4)  # Bilibili removed from parsing
        self.assertFalse(supported_host('evil-bilibili.com'))
        self.assertEqual(source_name(links[1]), 'Vimeo')
        self.assertEqual(source_name(links[2]), 'Niconico')

    def test_playlist_sites(self):
        self.assertTrue(is_playlist('https://www.youtube.com/playlist?list=PL123'))
        self.assertTrue(is_playlist('https://vimeo.com/showcase/1234'))
        self.assertTrue(is_playlist('https://soundcloud.com/artist/sets/album'))
        self.assertTrue(is_playlist('https://www.nicovideo.jp/mylist/12345'))
        self.assertFalse(is_playlist('https://vimeo.com/12345'))

    def test_video_only_formats_do_not_offer_broken_native_player(self):
        data = {'formats': [
            {'url': 'https://example.test/v.webm', 'ext': 'webm',
             'protocol': 'https', 'vcodec': 'vp9', 'acodec': 'none', 'height': 1080},
            {'url': 'https://example.test/a.m4a', 'ext': 'm4a',
             'protocol': 'https', 'vcodec': 'none', 'acodec': 'aac'},
        ]}
        self.assertEqual(select_playback_url(data), '')

    def test_choose_progressive_mp4(self):
        data = {'formats': [
            {'url': 'https://example.test/c.mp4', 'ext': 'mp4', 'protocol': 'https',
             'vcodec': 'avc1', 'acodec': 'mp4a', 'height': 360},
            {'url': 'https://example.test/b.webm', 'ext': 'webm', 'protocol': 'https',
             'vcodec': 'vp9', 'acodec': 'opus', 'height': 720},
            {'url': 'https://example.test/a.mp4', 'ext': 'mp4', 'protocol': 'https',
             'vcodec': 'avc1', 'acodec': 'mp4a', 'height': 720},
        ]}
        self.assertEqual(select_playback_url(data), 'https://example.test/a.mp4')

    def test_preview_defaults_off(self):
        self.assertIs(DEFAULT_SETTINGS['video_preview'], False)


if __name__ == '__main__':
    unittest.main()
