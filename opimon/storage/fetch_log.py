"""Dziennik pobrań (D5): kiedy, z jakim wynikiem i z jakimi błędami pobierano opinie celu.

Osobno od `ReviewRepository` (kontrakt zamrożony): fasada zapisuje wpis po każdym
`fetch_reviews`, widok „Źródła danych” (D4) i CLI (`list`, `log`) go czytają.
`SqliteFetchLog` korzysta z tego samego pliku bazy co repozytorium (tabela `fetch_log`).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from opimon import config
from opimon.models import FetchReport
from opimon.storage.db import connect, from_db_time, to_db_time


@dataclass(frozen=True, slots=True)
class FetchLogEntry:
    target_id: str
    source: str
    started_at: datetime
    seconds: float
    fetched: int
    new: int
    analyzed: int
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors

    @classmethod
    def from_report(cls, report: FetchReport, source: str, started_at: datetime) -> FetchLogEntry:
        return cls(report.target_id, source, started_at, report.seconds, report.fetched,
                   report.new, report.analyzed, tuple(report.errors))


class FetchLog(Protocol):
    def record(self, entry: FetchLogEntry) -> None: ...

    def last(self, target_id: str) -> FetchLogEntry | None: ...

    def history(self, target_id: str | None = None, limit: int = 50) -> list[FetchLogEntry]:
        """Wpisy od najnowszego."""
        ...

    def remove_target(self, target_id: str) -> None: ...


class InMemoryFetchLog:
    def __init__(self) -> None:
        self._entries: list[FetchLogEntry] = []

    def record(self, entry: FetchLogEntry) -> None:
        self._entries.append(entry)

    def last(self, target_id: str) -> FetchLogEntry | None:
        found = self.history(target_id, limit=1)
        return found[0] if found else None

    def history(self, target_id: str | None = None, limit: int = 50) -> list[FetchLogEntry]:
        rows = [e for e in reversed(self._entries) if target_id is None or e.target_id == target_id]
        rows.sort(key=lambda e: e.started_at, reverse=True)       # stabilne: najpóźniej dodany
        return rows[:limit]

    def remove_target(self, target_id: str) -> None:
        self._entries = [e for e in self._entries if e.target_id != target_id]


class SqliteFetchLog:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else config.DB_PATH
        self._conn = connect(self.path)
        self._lock = threading.RLock()

    def record(self, entry: FetchLogEntry) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO fetch_log (target_id, source, started_at, seconds, fetched, new, "
                "analyzed, errors) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (entry.target_id, entry.source, to_db_time(entry.started_at), entry.seconds,
                 entry.fetched, entry.new, entry.analyzed,
                 json.dumps(list(entry.errors), ensure_ascii=False)),
            )

    def last(self, target_id: str) -> FetchLogEntry | None:
        found = self.history(target_id, limit=1)
        return found[0] if found else None

    def history(self, target_id: str | None = None, limit: int = 50) -> list[FetchLogEntry]:
        sql = ("SELECT target_id, source, started_at, seconds, fetched, new, analyzed, errors "
               "FROM fetch_log")
        params: list = []
        if target_id is not None:
            sql += " WHERE target_id = ?"
            params.append(target_id)
        sql += " ORDER BY started_at DESC, id DESC LIMIT ?"
        params.append(max(limit, 0))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            FetchLogEntry(r["target_id"], r["source"], from_db_time(r["started_at"]),
                          r["seconds"], r["fetched"], r["new"], r["analyzed"],
                          tuple(json.loads(r["errors"] or "[]")))
            for r in rows
        ]

    def remove_target(self, target_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM fetch_log WHERE target_id = ?", (target_id,))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
