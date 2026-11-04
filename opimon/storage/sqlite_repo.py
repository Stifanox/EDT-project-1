"""Repozytorium opinii w SQLite (D2) – implementacja `ReviewRepository`.

Jedno połączenie na obiekt, chronione blokadą `RLock` (Streamlit obsługuje sesje w wielu
wątkach, a `AppServices` jest współdzielone). Każda metoda zapisująca to jedna transakcja.
Drugi proces (CLI z D5) otwiera własne połączenie; WAL pozwala czytać w trakcie zapisu.

Brak kluczy obcych: opinie mogą być zapisane przed celem, a predykcje przed opinią
(tak jak w zaślepce w pamięci). Kaskadę przy `remove_target` robimy jawnie w transakcji.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from opimon import config
from opimon.models import Prediction, Review, Sentiment, Target
from opimon.storage.db import connect, from_db_time, to_db_time

IN_CHUNK = 500        # maks. liczba parametrów w jednym `IN (...)`

_REVIEW_COLUMNS = (
    "id, source, external_id, target_id, text, created_at, author, rating, label, url, "
    "language, fetched_at, extra"
)
_ORDER = "ORDER BY created_at DESC, id ASC"


def _review_row(r: Review) -> tuple:
    return (
        r.id, r.source, r.external_id, r.target_id, r.text, to_db_time(r.created_at),
        r.author, r.rating, r.label.value if r.label else None, r.url, r.language,
        to_db_time(r.fetched_at), json.dumps(r.extra, ensure_ascii=False, default=str),
    )


def _review_from(row: sqlite3.Row) -> Review:
    return Review(
        source=row["source"],
        external_id=row["external_id"],
        target_id=row["target_id"],
        text=row["text"],
        created_at=from_db_time(row["created_at"]),
        author=row["author"],
        rating=row["rating"],
        label=Sentiment(row["label"]) if row["label"] else None,
        url=row["url"],
        language=row["language"],
        fetched_at=from_db_time(row["fetched_at"]),
        extra=json.loads(row["extra"] or "{}"),
    )


def _chunks(items: list[str], size: int = IN_CHUNK) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class SqliteReviewRepository:
    def __init__(self, path: Path | str | None = None) -> None:
        # `config.DB_PATH` czytany tutaj, w chwili tworzenia (testy podmieniają go na tmp)
        self.path = Path(path) if path is not None else config.DB_PATH
        self._conn = connect(self.path)
        self._lock = threading.RLock()

    # ------------------------------------------------------------- infrastruktura
    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """Transakcja zapisu (BEGIN IMMEDIATE – blokada od razu, bez zakleszczeń z CLI)."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def _query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> SqliteReviewRepository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- opinie
    def add_reviews(self, reviews: Iterable[Review]) -> int:
        rows = [_review_row(r) for r in reviews]
        if not rows:
            return 0
        with self._tx() as conn:
            before = conn.total_changes
            conn.executemany(
                # ON CONFLICT(id) pomija tylko duplikaty; `OR IGNORE` po cichu połykałby też
                # naruszenia NOT NULL (uszkodzona opinia znikałaby bez śladu)
                f"INSERT INTO reviews ({_REVIEW_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                rows,
            )
            return conn.total_changes - before

    def get_review(self, review_id: str) -> Review | None:
        rows = self._query(f"SELECT {_REVIEW_COLUMNS} FROM reviews WHERE id = ?", (review_id,))
        return _review_from(rows[0]) if rows else None

    def list_reviews(
        self,
        target_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[Review]:
        where, params = self._filters(target_id, since, until)
        sql = f"SELECT {_REVIEW_COLUMNS} FROM reviews {where} {_ORDER}"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(limit, 0))
        return [_review_from(r) for r in self._query(sql, params)]

    def count_reviews(self, target_id: str | None = None) -> int:
        where, params = self._filters(target_id, None, None)
        return self._query(f"SELECT COUNT(*) FROM reviews {where}", params)[0][0]

    @staticmethod
    def _filters(
        target_id: str | None, since: datetime | None, until: datetime | None
    ) -> tuple[str, list]:
        clauses, params = [], []
        if target_id is not None:
            clauses.append("target_id = ?")
            params.append(target_id)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(to_db_time(since))
        if until is not None:
            clauses.append("created_at < ?")
            params.append(to_db_time(until))
        return ("WHERE " + " AND ".join(clauses) if clauses else ""), params

    # ------------------------------------------------------------- cele
    def save_target(self, target: Target) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO targets (id, source, key, name, url) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, url = excluded.url",
                (target.id, target.source, target.key, target.name, target.url),
            )

    def get_target(self, target_id: str) -> Target | None:
        rows = self._query("SELECT source, key, name, url FROM targets WHERE id = ?", (target_id,))
        return Target(*rows[0]) if rows else None

    def list_targets(self) -> list[Target]:
        rows = self._query("SELECT source, key, name, url FROM targets ORDER BY name, id")
        return [Target(*r) for r in rows]

    def remove_target(self, target_id: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM predictions WHERE review_id IN "
                "(SELECT id FROM reviews WHERE target_id = ?)",
                (target_id,),
            )
            conn.execute("DELETE FROM reviews WHERE target_id = ?", (target_id,))
            conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))

    def latest_review_time(self, target_id: str) -> datetime | None:
        value = self._query(
            "SELECT MAX(created_at) FROM reviews WHERE target_id = ?", (target_id,)
        )[0][0]
        return from_db_time(value) if value else None

    # ------------------------------------------------------------- predykcje
    def save_predictions(self, predictions: Iterable[Prediction]) -> None:
        rows = [(p.review_id, p.model_name, float(p.score), to_db_time(p.created_at))
                for p in predictions]
        if not rows:
            return
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO predictions (review_id, model_name, score, created_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(review_id, model_name) DO UPDATE SET "
                "score = excluded.score, created_at = excluded.created_at",
                rows,
            )

    def get_predictions(
        self, model_name: str, review_ids: Iterable[str] | None = None
    ) -> dict[str, Prediction]:
        sql = "SELECT review_id, score, created_at FROM predictions WHERE model_name = ?"
        if review_ids is None:
            rows = self._query(sql, (model_name,))
        else:
            ids = list(dict.fromkeys(review_ids))
            rows = []
            for chunk in _chunks(ids):
                marks = ",".join("?" * len(chunk))
                rows += self._query(f"{sql} AND review_id IN ({marks})", (model_name, *chunk))
        return {
            r["review_id"]: Prediction(r["review_id"], model_name, r["score"],
                                       from_db_time(r["created_at"]))
            for r in rows
        }

    def delete_predictions(self, model_name: str) -> int:
        with self._tx() as conn:
            return conn.execute(
                "DELETE FROM predictions WHERE model_name = ?", (model_name,)
            ).rowcount

    def reviews_without_prediction(
        self, model_name: str, target_id: str | None = None
    ) -> list[Review]:
        columns = ", ".join(f"r.{c.strip()}" for c in _REVIEW_COLUMNS.split(","))
        sql = (
            f"SELECT {columns} FROM reviews r LEFT JOIN predictions p "
            "ON p.review_id = r.id AND p.model_name = ? WHERE p.review_id IS NULL"
        )
        params: list = [model_name]
        if target_id is not None:
            sql += " AND r.target_id = ?"
            params.append(target_id)
        sql += " ORDER BY r.created_at DESC, r.id ASC"
        return [_review_from(r) for r in self._query(sql, params)]
