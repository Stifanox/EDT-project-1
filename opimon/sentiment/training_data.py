"""Zaślepka zbioru treningowego (P0): `data/sample/train_sample.csv` (240 recenzji filmowych).

M1 dodaje prawdziwy zbiór (IMDB 50k z Kaggle / Hugging Face) jako osobny provider.
"""

from __future__ import annotations

import csv
import random

from opimon import config
from opimon.errors import DatasetUnavailableError
from opimon.models import Dataset, LabeledText, Sentiment
from opimon.textproc import clean_text


def split_balanced(
    examples: list[LabeledText],
    test_ratio: float = 0.25,
    seed: int = 13,
    max_train: int | None = None,
    max_test: int | None = None,
) -> tuple[list[LabeledText], list[LabeledText]]:
    """Deterministyczny podział stratyfikowany; limity rozkładane po równo na klasy."""
    rng = random.Random(seed)
    train: list[LabeledText] = []
    test: list[LabeledText] = []
    for label in (Sentiment.POSITIVE, Sentiment.NEGATIVE):
        group = [ex for ex in examples if ex.label is label]
        rng.shuffle(group)
        n_test = max(1, round(len(group) * test_ratio))
        g_test, g_train = group[:n_test], group[n_test:]
        if max_test is not None:
            g_test = g_test[: max(1, max_test // 2)]
        if max_train is not None:
            g_train = g_train[: max(1, max_train // 2)]
        train += g_train
        test += g_test
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


class SampleTrainingData:
    name = "sample_movies"
    label = "Przykładowe recenzje filmów (240, zaślepka)"

    def load(self, max_train: int | None = None, max_test: int | None = None) -> Dataset:
        path = config.SAMPLE_DIR / "train_sample.csv"
        if not path.exists():
            raise DatasetUnavailableError(
                f"Brak pliku {path}. Wygeneruj go: python scripts/make_sample_data.py"
            )
        with path.open(encoding="utf-8", newline="") as fh:
            examples = [
                LabeledText(clean_text(row["text"]), Sentiment(row["label"]))
                for row in csv.DictReader(fh)
            ]
        train, test = split_balanced(examples, max_train=max_train, max_test=max_test)
        return Dataset(self.name, train, test, description=self.label)
