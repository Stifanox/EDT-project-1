"""Dane przykładowe w repo muszą być zgodne z generatorem i zaprojektowane pod demo."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from opimon import config
from opimon.models import Sentiment
from opimon.sentiment import LexiconStubModel
from opimon.sources import SampleSource

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    spec = importlib.util.spec_from_file_location("make_sample_data",
                                                  ROOT / "scripts" / "make_sample_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_committed_files_match_generator():
    for name, content in _generator().render().items():
        on_disk = (config.SAMPLE_DIR / name).read_text(encoding="utf-8")
        assert on_disk == content, f"{name} nieaktualny: python scripts/make_sample_data.py"


def test_starfall_drops_in_last_week():
    src = SampleSource()
    reviews = src.fetch(src.find_targets("starfall")[0], limit=10_000)
    newest = reviews[0].created_at

    def share(rs):
        return sum(r.label is Sentiment.POSITIVE for r in rs) / len(rs)

    recent = [r for r in reviews if (newest - r.created_at).days < 6]
    older = [r for r in reviews if (newest - r.created_at).days >= 8]
    assert len(recent) >= 10 and share(older) - share(recent) > 0.3


def test_lexicon_is_imperfect_on_tricky_reviews():
    """Dane mają pokazywać różnice między modelami: słownik nie może mieć 100%."""
    src = SampleSource()
    reviews = [r for t in src.targets() for r in src.fetch(t, limit=10_000)]
    scores = LexiconStubModel().predict_proba([r.text for r in reviews])
    acc = sum(Sentiment.from_score(s) is r.label for s, r in zip(scores, reviews, strict=True))
    assert 0.6 < acc / len(reviews) < 0.97
