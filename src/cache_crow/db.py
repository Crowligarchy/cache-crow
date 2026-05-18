"""
SQLite persistence layer for cache-crow.

Tracks extracted files to avoid re-extraction across runs, and provides
cumulative statistics on what has been discovered and saved.

Schema
------
extractions
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  cache_path    TEXT UNIQUE   -- absolute path to the original cache file
  extracted_path TEXT         -- destination file (output-dir copy), NULL if dump-only
  dump_path     TEXT          -- path in permanent dump dir, NULL if not dumped
  mime_type     TEXT
  size_bytes    INTEGER
  cdn_url       TEXT          -- CDN URL recovered from cache entry header, NULL if unknown
  discovered_at REAL          -- unix timestamp of first scan (float)
  extracted_at  REAL          -- unix timestamp of extraction, NULL if only scanned
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

# Schema version — bump when adding columns
_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS extractions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_path      TEXT    UNIQUE NOT NULL,
    extracted_path  TEXT,
    dump_path       TEXT,
    mime_type       TEXT    NOT NULL DEFAULT 'application/octet-stream',
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    cdn_url         TEXT,
    discovered_at   REAL    NOT NULL,
    extracted_at    REAL
);

CREATE INDEX IF NOT EXISTS idx_extractions_mime ON extractions(mime_type);
CREATE INDEX IF NOT EXISTS idx_extractions_discovered ON extractions(discovered_at);
CREATE INDEX IF NOT EXISTS idx_extractions_extracted ON extractions(extracted_at);
"""


class CrowDB:
    """
    Thin wrapper around SQLite providing cache-crow's persistence operations.

    Usage
    -----
    db = CrowDB(Path("~/.cache/cache-crow/state.db"))
    with db:
        db.mark_seen("/path/to/f_000001", mime_type="image/png", size_bytes=4096)
        db.mark_extracted("/path/to/f_000001", extracted_path="/out/f_000001.png")
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser().resolve()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ #
    # Context manager                                                      #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "CrowDB":
        self.open()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Connection management                                                #
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        """Open (and initialise) the database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("DB not open — use CrowDB as a context manager or call .open()")
        return self._conn

    # ------------------------------------------------------------------ #
    # Write operations                                                     #
    # ------------------------------------------------------------------ #

    def mark_seen(
        self,
        cache_path: str | Path,
        *,
        mime_type: str = "application/octet-stream",
        size_bytes: int = 0,
        cdn_url: str | None = None,
        now: float | None = None,
    ) -> bool:
        """
        Record that a cache file was seen during a scan.

        Returns True if the row was newly inserted, False if it already existed.
        Does NOT overwrite an existing row (INSERT OR IGNORE).
        """
        ts = now if now is not None else time.time()
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO extractions
                (cache_path, mime_type, size_bytes, cdn_url, discovered_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(cache_path), mime_type, size_bytes, cdn_url, ts),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def mark_extracted(
        self,
        cache_path: str | Path,
        *,
        extracted_path: str | Path | None = None,
        dump_path: str | Path | None = None,
        now: float | None = None,
    ) -> None:
        """
        Record that a cache file was successfully extracted.

        Upserts extracted_path and extracted_at for the given cache_path.
        If the row doesn't exist yet, it is created (this handles callers that
        skip mark_seen).
        """
        ts = now if now is not None else time.time()
        self.conn.execute(
            """
            INSERT INTO extractions
                (cache_path, extracted_path, dump_path, mime_type, size_bytes, discovered_at, extracted_at)
            VALUES (?, ?, ?, 'application/octet-stream', 0, ?, ?)
            ON CONFLICT(cache_path) DO UPDATE SET
                extracted_path = COALESCE(excluded.extracted_path, extracted_path),
                dump_path      = COALESCE(excluded.dump_path, dump_path),
                extracted_at   = excluded.extracted_at
            """,
            (
                str(cache_path),
                str(extracted_path) if extracted_path else None,
                str(dump_path) if dump_path else None,
                ts,
                ts,
            ),
        )
        self.conn.commit()

    def mark_dumped(
        self,
        cache_path: str | Path,
        dump_path: str | Path,
        *,
        now: float | None = None,
    ) -> None:
        """Record that a file was saved to the permanent dump directory."""
        ts = now if now is not None else time.time()
        self.conn.execute(
            """
            INSERT INTO extractions
                (cache_path, dump_path, mime_type, size_bytes, discovered_at, extracted_at)
            VALUES (?, ?, 'application/octet-stream', 0, ?, ?)
            ON CONFLICT(cache_path) DO UPDATE SET
                dump_path    = excluded.dump_path,
                extracted_at = excluded.extracted_at
            """,
            (str(cache_path), str(dump_path), ts, ts),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Read operations                                                      #
    # ------------------------------------------------------------------ #

    def is_extracted(self, cache_path: str | Path) -> bool:
        """Return True if this cache_path already has an extracted_path recorded."""
        row = self.conn.execute(
            "SELECT extracted_at FROM extractions WHERE cache_path = ?",
            (str(cache_path),),
        ).fetchone()
        return row is not None and row["extracted_at"] is not None

    def is_seen(self, cache_path: str | Path) -> bool:
        """Return True if this cache_path has ever been recorded."""
        row = self.conn.execute(
            "SELECT id FROM extractions WHERE cache_path = ?",
            (str(cache_path),),
        ).fetchone()
        return row is not None

    def history(
        self,
        limit: int = 20,
        *,
        only_extracted: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Return the most recent extraction records.

        Parameters
        ----------
        limit:
            Maximum number of rows to return.
        only_extracted:
            If True (default), only return rows where extracted_at IS NOT NULL.
        """
        if only_extracted:
            rows = self.conn.execute(
                """
                SELECT id, cache_path, extracted_path, dump_path, mime_type,
                       size_bytes, cdn_url, discovered_at, extracted_at
                FROM extractions
                WHERE extracted_at IS NOT NULL
                ORDER BY extracted_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT id, cache_path, extracted_path, dump_path, mime_type,
                       size_bytes, cdn_url, discovered_at, extracted_at
                FROM extractions
                ORDER BY discovered_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics from the DB."""
        row = self.conn.execute(
            """
            SELECT
                COUNT(*)                          AS total_seen,
                SUM(extracted_at IS NOT NULL)     AS total_extracted,
                SUM(dump_path IS NOT NULL)        AS total_dumped,
                SUM(size_bytes)                   AS total_bytes
            FROM extractions
            """
        ).fetchone()
        return dict(row) if row else {}

    def count_by_mime(self) -> list[dict[str, Any]]:
        """Return per-MIME-type counts for extracted files."""
        rows = self.conn.execute(
            """
            SELECT mime_type, COUNT(*) AS count
            FROM extractions
            WHERE extracted_at IS NOT NULL
            GROUP BY mime_type
            ORDER BY count DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
