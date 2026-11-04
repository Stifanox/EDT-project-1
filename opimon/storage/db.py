"""Połączenie z SQLite i schemat bazy (D2).

* `journal_mode=WAL` – GUI i CLI (D5) mogą jednocześnie czytać i pisać do jednego pliku;
* `busy_timeout` – drugi proces czeka na blokadę zamiast od razu zgłaszać błąd;
* schemat tworzony przez `CREATE … IF NOT EXISTS`, wersja w `PRAGMA user_version`.
  Migracja 1 -> 2 (D5) to tylko nowa tabela `fetch_log`, więc wystarcza `CREATE … IF NOT EXISTS`.

Daty zapisujemy jako tekst ISO 8601 w UTC o stałej szerokości
(`2026-11-04T16:39:28.000000+00:00`), więc porównania i sortowanie tekstowe w SQL są poprawne.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 2          # 1: targets/reviews/predictions (D2) · 2: fetch_log (D5)

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    id      TEXT PRIMARY KEY,           -- "<source>:<key>"
    source  TEXT NOT NULL,
    key     TEXT NOT NULL,
    name    TEXT NOT NULL,
    url     TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    id          TEXT PRIMARY KEY,       -- "<source>:<external_id>"
    source      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL,          -- ISO 8601 UTC, stała szerokość
    author      TEXT,
    rating      REAL,
    label       TEXT,                   -- 'positive' / 'negative' / NULL
    url         TEXT,
    language    TEXT NOT NULL DEFAULT 'en',
    fetched_at  TEXT NOT NULL,
    extra       TEXT NOT NULL DEFAULT '{}'   -- JSON
);
CREATE INDEX IF NOT EXISTS ix_reviews_target_created ON reviews (target_id, created_at);
CREATE INDEX IF NOT EXISTS ix_reviews_created ON reviews (created_at);

CREATE TABLE IF NOT EXISTS predictions (
    review_id   TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    score       REAL NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (review_id, model_name)
);
CREATE INDEX IF NOT EXISTS ix_predictions_model ON predictions (model_name);

CREATE TABLE IF NOT EXISTS fetch_log (      -- dziennik pobrań (D5)
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    started_at  TEXT NOT NULL,          -- ISO 8601 UTC
    seconds     REAL NOT NULL,
    fetched     INTEGER NOT NULL,
    new         INTEGER NOT NULL,
    analyzed    INTEGER NOT NULL,
    errors      TEXT NOT NULL DEFAULT '[]'   -- JSON: lista komunikatów
);
CREATE INDEX IF NOT EXISTS ix_fetch_log_target ON fetch_log (target_id, started_at);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Otwórz bazę (tworząc katalog i schemat). Połączenie może być używane z wielu wątków,
    ale dostęp trzeba serializować (robi to `SqliteReviewRepository` przez blokadę)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Baza ma nowszy schemat ({version}) niż aplikacja ({SCHEMA_VERSION}). "
            "Zaktualizuj kod (git pull)."
        )
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def to_db_time(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError(f"Data bez strefy czasowej: {value!r}")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def from_db_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)
