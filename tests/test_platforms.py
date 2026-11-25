import unittest
from unittest.mock import patch
from app import platforms, tool_updates

class PlatformTests(unittest.TestCase):
    def test_release_assets(self):
        for system, machine, yt, deno in [
            ('Windows','AMD64','yt-dlp.exe','deno-x86_64-pc-windows-msvc.zip'),
            ('Linux','x86_64','yt-dlp_linux','deno-x86_64-unknown-linux-gnu.zip'),
            ('Linux','aarch64','yt-dlp_linux_aarch64','deno-aarch64-unknown-linux-gnu.zip'),
            ('Darwin','arm64','yt-dlp_macos','deno-aarch64-apple-darwin.zip')]:
            with self.subTest(system=system, machine=machine), patch('platform.system', return_value=system), patch('platform.machine', return_value=machine):
                self.assertEqual(platforms.ytdlp_asset(), yt)
                self.assertEqual(platforms.deno_asset(), deno)
    def test_open_folder_linux_mac(self):
        for system, cmd in [('Linux','xdg-open'), ('Darwin','open')]:
            with patch('app.platforms.system', return_value=system), patch('app.platforms.subprocess.Popen') as run:
                platforms.open_directory('.')
                self.assertEqual(run.call_args.args[0][0], cmd)
    def test_linux_shutdown(self):
        with patch('app.platforms.system', return_value='Linux'), patch('app.platforms.shutil.which', return_value='/usr/bin/systemctl'):
            self.assertEqual(platforms.shutdown_command(), ['systemctl','poweroff'])
    def test_mac_shutdown_disabled(self):
        with patch('app.platforms.system', return_value='Darwin'):
            self.assertIsNone(platforms.shutdown_command())
    def test_nonwindows_ffmpeg_no_windows_download(self):
        with patch('app.tool_updates.system', return_value='Linux'), patch('app.tool_updates._version', return_value=''), patch('app.tool_updates._get_json') as request:
            result = tool_updates.check_ffmpeg()
            self.assertFalse(result['needs_update'])
            request.assert_not_called()
