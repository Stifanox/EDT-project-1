"""Lokalny IMDB: CSV Kaggle lub eksport Hugging Face z oficjalnym podziałem."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path

from opimon import config
from opimon.errors import DatasetUnavailableError
from opimon.models import Dataset, LabeledText, Sentiment
from opimon.sentiment.training_data import split_balanced
from opimon.textproc import clean_text


def _limited(data: list[LabeledText], limit: int | None) -> list[LabeledText]:
    if limit is None:
        return data[:]
    if limit < 0:
        raise ValueError("Limit przykładów nie może być ujemny.")
    groups = [[ex for ex in data if ex.label is label] for label in Sentiment]
    out: list[LabeledText] = []
    for i in range(max(map(len, groups), default=0)):
        for group in groups:
            if i < len(group) and len(out) < limit:
                out.append(group[i])
        if len(out) >= limit:
            break
    random.Random(13).shuffle(out)
    return out


class ImdbTrainingData:
    name = "imdb"
    label = "IMDB — recenzje filmów (50 tys.)"

    def load(self, max_train: int | None = None, max_test: int | None = None) -> Dataset:
        path = config.DATASETS_DIR / "IMDB Dataset.csv"
        if not path.is_file():
            raise DatasetUnavailableError(
                f"Brak zbioru IMDB: {path}. Pobierz CSV Kaggle do tej ścieżki albo uruchom "
                "python scripts/download_imdb.py (publiczny zbiór stanfordnlp/imdb)."
            )
        if any(n is not None and n < 0 for n in (max_train, max_test)):
            raise ValueError("Limit przykładów nie może być ujemny.")
        stat = path.stat()
        identity = f"imdb-v3:{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        key = hashlib.sha256(identity.encode()).hexdigest()
        cache = config.CACHE_DIR / f"imdb-{key}.json"
        try:
            parts = json.loads(cache.read_text(encoding="utf-8"))
            train, test = ([LabeledText(t, Sentiment(s)) for t, s in parts[k]]
                           for k in ("train", "test"))
        except (OSError, ValueError, KeyError, TypeError):
            train, test = self._read(path)
            parts = {k: [(ex.text, ex.label.value) for ex in data]
                     for k, data in (("train", train), ("test", test))}
            config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix(".tmp")
            temporary.write_text(json.dumps(parts, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache)
        return Dataset(self.name, _limited(train, max_train), _limited(test, max_test),
                       description="IMDB; wspólne czyszczenie; bez powtórzeń między częściami.")

    def _read(self, path: Path) -> tuple[list[LabeledText], list[LabeledText]]:
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not {"review", "sentiment"} <= set(reader.fieldnames or []):
                    raise ValueError("Wymagane kolumny: review, sentiment.")
                official = "split" in (reader.fieldnames or [])
                # Wspólny tekst trafia do jednej części; konfliktujące etykiety odrzucamy.
                records: dict[str, tuple[Sentiment, str]] = {}
                conflicts: set[str] = set()
                for row in reader:
                    text = clean_text(row["review"])
                    label = Sentiment(row["sentiment"].strip().lower())
                    part = row.get("split", "")
                    if official and part not in {"train", "test"}:
                        raise ValueError("Kolumna split musi zawierać train albo test.")
                    if not text:
                        continue
                    if text in records and records[text][0] != label:
                        conflicts.add(text)
                    else:
                        records.setdefault(text, (label, part))
            if official:
                train, test = ([LabeledText(t, s) for t, (s, p) in records.items()
                                if p == part and t not in conflicts] for part in ("train", "test"))
                for data in (train, test):
                    random.Random(13).shuffle(data)
                train, test = (
                    _limited(data, 2 * min(sum(ex.label is label for ex in data)
                                          for label in Sentiment))
                    for data in (train, test)
                )
            else:
                train, test = split_balanced(
                    [LabeledText(t, s) for t, (s, _) in records.items() if t not in conflicts]
                )
            for data in (train, test):
                if {ex.label for ex in data} != set(Sentiment):
                    raise ValueError("Obie części zbioru muszą zawierać obie klasy.")
            return train, test
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
            raise DatasetUnavailableError(f"Nie można odczytać IMDB {path}: {exc}") from exc
