import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import toolchain


class RelocatedToolsTests(unittest.TestCase):
    def test_tools_folder_with_nested_deno_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / 'VOC AFLOP'
            tools = root / 'tools'
            for relative in ('deno', 'ffmpeg/bin'):
                (tools / relative).mkdir(parents=True, exist_ok=True)
            suffix = '.exe' if os.name == 'nt' else ''
            (tools / 'deno' / ('deno'+suffix)).write_bytes(b'fake')
            (tools / 'ffmpeg' / 'bin' / ('ffmpeg'+suffix)).write_bytes(b'fake')
            (tools / ('yt-dlp'+suffix)).write_bytes(b'fake')
            settings = {'tools_dir': str(root), 'ffmpeg_dir': '', 'deno_dir': ''}
            with patch.object(toolchain, 'BIN_DIR', Path(temp) / 'empty'), \
                 patch.object(toolchain, 'LEGACY_DIR', Path(temp) / 'old'):
                self.assertEqual(toolchain.resolve_tool('deno', settings).parent, tools / 'deno')
                self.assertEqual(toolchain.resolve_tool('ffmpeg', settings).parent, tools / 'ffmpeg/bin')
                self.assertEqual(toolchain.resolve_tool('yt-dlp', settings).parent, tools)
                self.assertIn('deno:', toolchain.js_args(settings)[1])
                self.assertIn(str(tools / 'deno'), toolchain.tool_env(settings)['PATH'])

    def test_select_nested_directory_directly(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / ('deno.exe' if os.name == 'nt' else 'deno')
            exe.write_bytes(b'fake')
            settings = {'tools_dir': '', 'ffmpeg_dir': '', 'deno_dir': temp}
            self.assertEqual(toolchain.resolve_tool('deno', settings), exe.resolve())


if __name__ == '__main__':
    unittest.main()
