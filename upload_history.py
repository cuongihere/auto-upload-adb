"""Durable, content-based upload reservations. No platform credentials are stored."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATABASE = Path(__file__).resolve().parent / 'data' / 'upload_history.sqlite3'
BLOCKING = ('in_progress', 'prepared', 'manual_required', 'submitting',
            'submitted_unverified', 'published', 'published_manual', 'needs_review')


def fingerprint(video: Path, cancelled=None) -> str:
    digest = hashlib.sha256()
    with video.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Đã dừng tính mã video.')
            digest.update(chunk)
    return digest.hexdigest()


class UploadHistory:
    def __init__(self, path: Path = DATABASE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, platform TEXT NOT NULL,
                serial TEXT NOT NULL, video TEXT NOT NULL, status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '', remote TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS uploads_content ON uploads(sha256, platform)')
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, sha256: str, platform: str, serial: str, video: Path) -> tuple[str | None, dict | None]:
        """Serialize duplicate checks across threads and app instances."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute(
                'SELECT * FROM uploads WHERE sha256=? AND platform=? AND status IN ('
                + ','.join('?' for _ in BLOCKING) + ') ORDER BY updated_at DESC LIMIT 1',
                (sha256, platform, *BLOCKING),
            ).fetchone()
            if row:
                return None, dict(row)
            ident = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO uploads VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (ident, sha256, platform, serial, str(video), 'in_progress', '', '', now, now))
            return ident, None

    def update(self, ident: str, status: str, detail: str = '', remote: str | None = None):
        with self.connect() as db:
            db.execute('UPDATE uploads SET status=?, detail=?, remote=COALESCE(?,remote), updated_at=? WHERE id=?',
                       (status, detail, remote, datetime.now(timezone.utc).isoformat(), ident))

    def rows(self, limit: int = 500) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM uploads ORDER BY updated_at DESC LIMIT ?', (limit,))]

    def import_legacy(self, source: Path):
        """Old manual handoffs may have been posted; require explicit review."""
        key = 'legacy:' + str(source.resolve())
        with self.connect() as db:
            if db.execute('SELECT 1 FROM metadata WHERE key=?', (key,)).fetchone():
                return
        if not source.exists():
            return
        entries = []
        for line in source.read_text(encoding='utf-8').splitlines():
            try:
                item = json.loads(line)
                video = Path(item['video'])
                if item.get('status') == 'error' or not video.is_file():
                    continue
                sha = fingerprint(video)
                entries.append((sha, item, video))
            except (ValueError, KeyError, OSError):
                continue
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM metadata WHERE key=?', (key,)).fetchone():
                return
            for sha, item, video in entries:
                if db.execute('SELECT 1 FROM uploads WHERE sha256=? AND platform=?', (sha, item['platform'])).fetchone():
                    continue
                now = datetime.now(timezone.utc).isoformat()
                db.execute('INSERT INTO uploads VALUES (?,?,?,?,?,?,?,?,?,?)', (
                    uuid.uuid4().hex, sha, item['platform'], item.get('serial', ''), str(video),
                    'needs_review', 'Lịch sử cũ: xác nhận đã đăng hoặc chưa đăng trước khi chạy lại.',
                    item.get('remote', ''), item.get('at', now), now))
            db.execute('INSERT INTO metadata VALUES (?,?)', (key, 'done'))
