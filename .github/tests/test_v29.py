"""SoundCloud/Spotify platform and playlist regressions, all network-free."""
import asyncio
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.helpers import (
    extract_urls, clean_url, source_name, can_download, is_playlist,
    parse_source_summary, supported_host,
)
from app.core import command_for_job, _run_probe, ProbeError
from app.models import DownloadJob


class SoundCloudV29Tests(unittest.TestCase):
    def test_music_url_detection_with_noise(self):
        data = """listen: https://soundcloud.com/creator/song?si=track-token&utm_medium=share
        https://on.soundcloud.com/abc123?si=tracking
        https://snd.sc/abcXYZ
        irrelevant https://soundcloud.com.attacker.test/evil"""
        self.assertEqual(extract_urls(data), [
            'https://soundcloud.com/creator/song',
            'https://on.soundcloud.com/abc123',
            'https://snd.sc/abcXYZ',
        ])
        self.assertEqual(source_name('https://soundcloud.com/creator/song'), 'SoundCloud')
        self.assertEqual(source_name('https://on.soundcloud.com/abc123'), 'SoundCloud')
        self.assertIn('SoundCloud 3', parse_source_summary(extract_urls(data)))
        self.assertFalse(supported_host('soundcloud.com.attacker.test'))

    def test_private_share_preserves_access_token(self):
        raw = 'https://soundcloud.com/creator/private-song?secret_token=s-AbCd1&si=abc&utm_source=clipboard'
        self.assertEqual(clean_url(raw),
                         'https://soundcloud.com/creator/private-song?secret_token=s-AbCd1')

    def test_soundcloud_playlist_recognition(self):
        self.assertTrue(is_playlist('https://soundcloud.com/creator/sets/my-mix'))
        self.assertTrue(is_playlist('https://soundcloud.com/creator/likes'))
        self.assertTrue(is_playlist('https://soundcloud.com/creator'))
        self.assertTrue(is_playlist('https://on.soundcloud.com/a12'))
        self.assertFalse(is_playlist('https://soundcloud.com/creator/single-song'))
        self.assertTrue(can_download('https://soundcloud.com/creator/sets/my-mix'))

    def test_retired_platforms_removed(self):
        self.assertEqual(extract_urls('https://www.bilibili.com/video/BVxxxx '
                                      'https://www.threads.net/@a/post/1'), [])
        self.assertFalse(can_download('https://www.bilibili.com/video/BVxxxx'))
        self.assertFalse(can_download('https://www.threads.net/@a/post/1'))

    def test_spotify_is_classification_only(self):
        url = 'https://open.spotify.com/track/abcdefgh?si=something'
        self.assertEqual(extract_urls(url), ['https://open.spotify.com/track/abcdefgh'])
        self.assertEqual(source_name(url), 'Spotify')
        self.assertFalse(can_download(url))
        with self.assertRaises(ProbeError):
            _run_probe(url, False)

    def test_mp3_command_and_playlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            ffprobe = Path(tmp) / 'ffprobe.exe'
            ffprobe.write_bytes(b'test')
            settings = {'max_size_mb': 0, 'playlist_max_videos': 25,
                        'ffmpeg_dir': tmp, 'use_browser_cookies': False}
            job = DownloadJob(id='x', url='https://soundcloud.com/creator/sets/my-mix',
                              title='Set', mode='playlist', kind='mp3', quality=192, folder=tmp)
            with patch('app.core.ffmpeg_dir', return_value=tmp), \
                 patch('app.core.resolve_tool', return_value=ffprobe), \
                 patch('app.core.cli_exe', return_value='yt-dlp.exe'), \
                 patch('app.core.js_args', return_value=[]):
                cmd = command_for_job(job, settings)
            self.assertIn('--yes-playlist', cmd)
            self.assertEqual(cmd[cmd.index('--playlist-end')+1], '25')
            self.assertEqual(cmd[cmd.index('--audio-format')+1], 'mp3')
            self.assertEqual(cmd[cmd.index('--audio-quality')+1], '192K')
            self.assertIn('bestaudio/best', cmd)
            self.assertEqual(cmd[-1], job.url)

    def test_soundcloud_mp4_rejected_before_file_changes(self):
        job = DownloadJob(id='x', url='https://soundcloud.com/a/b',
                          title='Audio', mode='video', kind='mp4', quality=720,
                          folder='should-not-create-this-folder')
        with self.assertRaisesRegex(RuntimeError, 'audio-only'):
            command_for_job(job, {})

    def test_ui_has_audio_only_and_global_validation(self):
        src = (Path(__file__).parent.parent/'app/ui.py').read_text(encoding='utf-8')
        self.assertIn("item.kind = 'mp3'", src)
        self.assertIn("if kind not in available_formats(source_name(item.url) == 'SoundCloud'):", src)
        self.assertIn("if (kind_override or item.kind) not in available_formats(source_name(item.url) == 'SoundCloud'):", src)
        self.assertIn('Choose an audio format for SoundCloud items', src)
        self.assertIn('SoundCloud', src)

    def test_supported_video_sources_remain(self):
        for link in ('https://www.youtube.com/watch?v=A', 'https://x.com/demo/status/1',
                     'https://www.facebook.com/watch/?v=1', 'https://www.nicovideo.jp/watch/sm1'):
            self.assertTrue(can_download(link))


if __name__ == '__main__':
    unittest.main()
