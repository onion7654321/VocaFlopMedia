import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.helpers import extract_urls, get_resolutions, to_seconds
from app.models import DownloadJob
from app.core import command_for_job, readable_error


class CoreTests(unittest.TestCase):
    def job(self, **changes):
        d = dict(id="abc", url="https://youtu.be/1234", title="Test", mode="video",
                 kind="mp4", quality=1080, folder=tempfile.gettempdir())
        d.update(changes)
        return DownloadJob(**d)

    @patch("app.core.ffmpeg_dir", return_value="C:/ffmpeg/bin")
    @patch("app.core.cli_exe", return_value="C:/tools/yt-dlp.exe")
    def test_mp4_quality(self, *_):
        cmd = command_for_job(self.job(quality=720), {"max_size_mb": 1500})
        self.assertTrue(any("bv[height<=720][ext=mp4]+ba[ext=m4a]" in part for part in cmd))
        self.assertNotIn("--recode-video", cmd)
        self.assertIn("--merge-output-format", cmd)
        self.assertIn("1500M", cmd)
        self.assertIn("--no-playlist", cmd)

    @patch("app.core.ffmpeg_dir", return_value="C:/ffmpeg/bin")
    @patch("app.core.cli_exe", return_value="C:/tools/yt-dlp.exe")
    def test_mp3_cut(self, *_):
        cmd = command_for_job(self.job(kind="mp3", quality=192, start=60, end=95), {})
        self.assertIn("192K", cmd)
        self.assertIn("*00:01:00-00:01:35", cmd)
        self.assertIn("--download-sections", cmd)

    @patch("app.core.ffmpeg_dir", return_value="C:/ffmpeg/bin")
    @patch("app.core.cli_exe", return_value="C:/tools/yt-dlp.exe")
    def test_playlist_limit(self, *_):
        cmd = command_for_job(self.job(mode="playlist"), {"playlist_max_videos": 35})
        self.assertIn("--yes-playlist", cmd)
        self.assertIn("35", cmd)

    def test_url_parsing(self):
        text = "https://youtu.be/a https://youtu.be/a\nhttps://www.youtube.com/watch?v=some_id"
        self.assertEqual(len(extract_urls(text)), 2)

    def test_times(self):
        self.assertEqual(to_seconds("01:09"), 69)
        self.assertEqual(to_seconds("01:00:01"), 3601)
        with self.assertRaises(ValueError):
            to_seconds("00:99")

    def test_resolutions(self):
        f = {"formats": [{"height": h, "vcodec": "h264"} for h in [360, 720, 1080, 2160, 1440, 480]]}
        self.assertEqual(get_resolutions(f), [2160, 1440, 1080, 720])

    def test_errors(self):
        self.assertIn("Deno", readable_error("WARNING: failed Javascript challenge"))


if __name__ == "__main__":
    unittest.main()
