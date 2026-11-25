"""Vocaflop settings/history live under AppData, independent from the app folder."""
from __future__ import annotations
import json
import os
import sqlite3
import shutil
from threading import RLock
from datetime import datetime
from pathlib import Path

DATA_HOME = Path(os.environ.get('APPDATA') or (Path.home() / '.config'))
APP_DIR = DATA_HOME / 'Vocaflop'
LEGACY_DIR = DATA_HOME / 'ClipForge'
BIN_DIR = APP_DIR / 'tools'
SETTINGS_FILE = APP_DIR / 'settings.json'
DB_FILE = APP_DIR / 'history.sqlite3'
DEFAULT_SETTINGS = {
    'download_dir': str(Path.home() / 'Downloads'),
    'ask_folder': False,
    'max_size_mb': 2048,
    'parallel_jobs': 2,
    'playlist_max_videos': 100,
    'stream_limit_minutes': 60,
    'theme': 'dark',
    'video_preview': False,
    'check_updates': True,
    'tools_dir': '',
    'ffmpeg_dir': '',
    'deno_dir': '',
    'app_update_manifest': '',
    'cookies_browser': 'none',
    'use_browser_cookies': False,
    'cookies_file': '',
}


def init_dirs():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    # One-way migration, never remove the legacy data. Existing Vocaflop files win.
    for filename in ('settings.json', 'history.sqlite3'):
        src, dst = LEGACY_DIR / filename, APP_DIR / filename
        if not dst.exists() and src.is_file():
            shutil.copy2(src, dst)


def load_settings():
    init_dirs()
    config = DEFAULT_SETTINGS.copy()
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
            for key in config:
                if key in saved and type(saved[key]) is type(config[key]):
                    config[key] = saved[key]
        except (ValueError, OSError):
            pass
    return config


def save_settings(config):
    init_dirs()
    tmp = SETTINGS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(SETTINGS_FILE)


class History:
    def __init__(self):
        init_dirs()
        self._lock = RLock()
        self.db = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS downloads (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, finished_at TEXT,
            url TEXT NOT NULL, title TEXT, kind TEXT NOT NULL, quality TEXT NOT NULL,
            folder TEXT NOT NULL, status TEXT NOT NULL, files TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT '', log TEXT NOT NULL DEFAULT ''
        )''')
        cols = {r[1] for r in self.db.execute('PRAGMA table_info(downloads)')}
        if 'log' not in cols:
            self.db.execute("ALTER TABLE downloads ADD COLUMN log TEXT NOT NULL DEFAULT ''")
        for col, datatype in (("mode", "TEXT NOT NULL DEFAULT 'video'"),
                              ("start_seconds", "INTEGER"), ("end_seconds", "INTEGER")):
            if col not in cols:
                self.db.execute(f"ALTER TABLE downloads ADD COLUMN {col} {datatype}")
        self.db.commit()

    def create(self, record):
        with self._lock, self.db:
            self.db.execute('''INSERT INTO downloads
                (id, created_at, url, title, kind, quality, folder, status, mode, start_seconds, end_seconds)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
                record['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                record['url'], record.get('title', ''), record['kind'], record['quality'],
                record['folder'], 'Queued', record.get('mode', 'video'),
                record.get('start_seconds'), record.get('end_seconds')))

    def update(self, id_, status, files=None, error='', log=''):
        with self._lock, self.db:
            self.db.execute('''UPDATE downloads
                SET status=?, files=?, error=?, log=?, finished_at=? WHERE id=?''', (
                status, json.dumps(files or [], ensure_ascii=False), error, log[-50000:],
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), id_))

    def rename_path(self, old: str, new: str, title: str):
        with self._lock, self.db:
            for row in self.rows():
                files = json.loads(row['files'])
                if old in files:
                    files = [new if path == old else path for path in files]
                    self.db.execute('UPDATE downloads SET files=?, title=? WHERE id=?',
                                    (json.dumps(files, ensure_ascii=False), title, row['id']))

    def rows(self):
        with self._lock:
            return list(self.db.execute('SELECT * FROM downloads ORDER BY created_at DESC, rowid DESC'))

    def delete(self, id_: str):
        with self._lock, self.db:
            self.db.execute('DELETE FROM downloads WHERE id=?', (id_,))

    def clear(self):
        with self._lock, self.db:
            self.db.execute('DELETE FROM downloads')

    def close(self):
        with self._lock:
            self.db.close()
