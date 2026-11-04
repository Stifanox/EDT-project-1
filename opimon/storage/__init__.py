"""Przechowywanie opinii i predykcji (właściciel: O1). D2: SQLite."""

from opimon.storage.memory import InMemoryReviewRepository
from opimon.storage.sqlite_repo import SqliteReviewRepository

__all__ = ["InMemoryReviewRepository", "SqliteReviewRepository"]
