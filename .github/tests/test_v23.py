"""Offline regressions for multi-source, browser auth, migrated history and URL input logic."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import auth_args, command_for_job
from app.helpers import extract_urls, source_name, source_counts, parse_source_summary
from app.models import DownloadJob
from app.storage import History


class V23Tests(unittest.TestCase):
    def test_extended_domains(self):
        links = extract_urls('''
          https://x.com/example/status/123
          https://twitter.com/example/status/123
          https://www.facebook.com/watch/?v=123
          https://fb.watch/ABC123/
          https://www.threads.net/@demo/post/C123
          https://www.threads.com/@demo/post/C124
          https://vimeo.com/121212
          https://www.bilibili.com/video/BV1123
          https://x.com.evil.test/status/fake
          https://threads.net.evil.test/wrong
        ''')
        self.assertEqual(len(links), 5)
        self.assertEqual(source_name(links[0]), 'X')
        self.assertEqual(source_name(links[2]), 'Facebook')
        self.assertEqual(source_name(links[4]), 'Vimeo')
        self.assertNotIn('Threads', source_counts(links))
        self.assertIn('X 2', parse_source_summary(links))

    def test_browser_auth_off_default(self):
        self.assertEqual(auth_args({'cookies_browser': 'none'}), [])
        self.assertEqual(auth_args({'cookies_browser': 'edge'}), [])
        self.assertEqual(auth_args({'cookies_browser': 'edge', 'use_browser_cookies': True}), ['--cookies-from-browser', 'edge'])
        self.assertEqual(auth_args({'cookies_browser': 'unexpected'}), [])

    def test_cookie_command_is_opt_in(self):
        job = DownloadJob(id='test', url='https://x.com/demo/status/123', title='Example',
                          mode='video', kind='mp3', quality=192, folder='ignored')
        settings = {'cookies_browser': 'firefox', 'use_browser_cookies': True, 'max_size_mb': 0, 'ffmpeg_dir': 'any'}
        with patch('app.core.ffmpeg_dir', return_value='/example/ffmpeg'), \
             patch('app.core.cli_exe', return_value='yt-dlp.exe'), \
             patch('pathlib.Path.mkdir'):
            cmd = command_for_job(job, settings)
        self.assertIn('--cookies-from-browser', cmd)
        self.assertEqual(cmd[cmd.index('--cookies-from-browser')+1], 'firefox')

    def test_existing_database_migration_and_delete(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'history.sqlite3'
            with closing(sqlite3.connect(file)) as db, db:
                db.execute('''CREATE TABLE downloads (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, finished_at TEXT,
                    url TEXT NOT NULL, title TEXT, kind TEXT NOT NULL, quality TEXT NOT NULL,
                    folder TEXT NOT NULL, status TEXT NOT NULL, files TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT '', log TEXT NOT NULL DEFAULT '')''')
                db.execute("INSERT INTO downloads (id,created_at,url,kind,quality,folder,status) VALUES (?,?,?,?,?,?,?)",
                           ('old', '2026-10-25 11:00:00', 'https://vimeo.com/1', 'mp4', '720', root, 'Completed'))
            with patch('app.storage.DB_FILE', file), patch('app.storage.init_dirs'):
                history = History()
                self.assertEqual(history.rows()[0]['mode'], 'video')
                history.create({'id': 'new', 'url': 'https://x.com/demo/status/123',
                                'title': 'New', 'kind': 'mp3', 'quality': '320', 'folder': root,
                                'mode': 'video', 'start_seconds': 30, 'end_seconds': 60})
                rec = next(r for r in history.rows() if r['id']=='new')
                self.assertEqual((rec['start_seconds'], rec['end_seconds']), (30, 60))
                history.delete('old')
                self.assertEqual([r['id'] for r in history.rows()], ['new'])
                history.close()


if __name__ == '__main__':
    unittest.main()
