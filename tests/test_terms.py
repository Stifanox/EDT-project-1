"""A4: słowa kluczowe – log-odds z bigramami, próg liczności, usuwanie powtórzeń, nowe tematy."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from opimon.analytics.terms import (
    drop_redundant,
    effective_min_count,
    emerging_terms,
    log_odds_z,
    review_terms,
    top_terms,
)
from opimon.models import Prediction, ScoredReview, Sentiment
from tests.conftest import NOW, make_review

P, N = Sentiment.POSITIVE, Sentiment.NEGATIVE


def scored(i: int, text: str, score: float | None, hours_ago: float = 1.0) -> ScoredReview:
    review = make_review(str(i), text, hours_ago)
    return ScoredReview(review, None if score is None else Prediction(review.id, "m", score))


def corpus(spec: list[tuple[str, float | None, int]], hours_ago: float = 1.0):
    out, i = [], 0
    for text, score, copies in spec:
        for _ in range(copies):
            out.append(scored(i, text, score, hours_ago))
            i += 1
    return out


def test_review_terms_bigrams_within_sentences():
    terms = review_terms("Honestly a waste of money. Frame rate drops!")
    assert {"waste", "money", "waste money", "frame rate", "rate drops"} <= terms
    assert "money frame" not in terms               # bez łączenia przez granicę zdania
    assert "the" not in terms and "of" not in terms
    assert "waste money" not in review_terms("waste of money", bigrams=False)


def test_log_odds_matches_hand_computation():
    # grupa A: 2 opinie, termy x, y; grupa B: 2 opinie, termy y, z
    a, b = Counter({"x": 2, "y": 1}), Counter({"y": 1, "z": 2})
    out = dict((t, z) for t, _, z in log_odds_z(a, 2, b, 2, min_count=1, prior_strength=1.0))
    # α0 = 1·4 = 4, łącznie 6 wystąpień; x: α = 4·2/6 = 4/3, y nie jest częstsze w A
    alpha = 4 / 3
    delta = math.log((2 + alpha) / (3 + 4 - 2 - alpha)) - math.log(alpha / (3 + 4 - alpha))
    expected = delta / math.sqrt(1 / (2 + alpha) + 1 / alpha)
    assert out["x"] == pytest.approx(expected)
    assert set(out) == {"x"}


def test_top_terms_ranks_characteristic_bigrams():
    rows = corpus([
        ("The frame rate is great and smooth", 0.9, 6),
        ("Great story and lovely art", 0.9, 6),
        ("Honestly a waste of money, constant crashes", 0.1, 5),
        ("The story is great but a waste of money", 0.1, 1),
        ("No prediction about waste of money", None, 4),
    ])
    neg = top_terms(rows, N, n=5)
    assert neg[0].term in {"waste money", "constant crashes"}
    assert {t.term for t in neg} >= {"waste money", "constant crashes"}
    assert "waste money" in {t.term for t in neg} and "waste" not in {t.term for t in neg}
    waste = next(t for t in neg if t.term == "waste money")
    assert waste.count == 6 and waste.sentiment is N    # bez opinii bez predykcji
    pos = [t.term for t in top_terms(rows, P, n=10)]
    assert "frame rate" in pos and "lovely art" in pos
    weights = [t.weight for t in top_terms(rows, P, n=10)]
    assert weights == sorted(weights, reverse=True)


def test_min_count_blocks_rare_words():
    rows = corpus([("solid fun gameplay", 0.9, 20), ("boring grind", 0.1, 20),
                   ("exquisite", 0.9, 1), ("perfect fun gameplay", 0.9, 1)])
    pos = {t.term for t in top_terms(rows, P, n=50)}
    assert "exquisite" not in pos and "perfect" not in pos     # 1 opinia < próg 2 (5% z 22)
    assert "fun gameplay" in pos
    assert "exquisite" in {t.term for t in top_terms(rows, P, n=50, min_count=1)}
    assert effective_min_count(2) == 1 and effective_min_count(40) == 2
    assert effective_min_count(1000) == 3


def test_drop_redundant_collapses_phrase_chain():
    scored_terms = [("old laptop", 25, 2.0), ("perfectly old", 25, 2.0),
                    ("runs perfectly", 25, 2.0), ("laptop", 25, 2.0), ("great", 24, 1.9),
                    ("old", 40, 1.5)]
    kept = [t for t, _, _ in drop_redundant(scored_terms)]
    assert kept == ["old laptop", "great", "old"]      # „old” występuje też poza frazą


def test_emerging_terms_detects_recent_topic():
    earlier = corpus([("Great game, fun co op", 0.9, 30), ("Boring grind", 0.1, 10),
                      ("The patch was fine", 0.9, 1)], hours_ago=24 * 20)
    recent = corpus([("The new patch broke my saves", 0.1, 5), ("Great game, fun co op", 0.9, 4),
                     ("After the update it crashes", 0.1, 3)], hours_ago=24)
    recent = [ScoredReview(make_review(f"r{i}", r.review.text, 24), r.prediction)
              for i, r in enumerate(recent)]
    terms = emerging_terms(earlier + recent, recent_days=7, now=NOW)
    names = [t.term for t in terms]
    # „patch” występuje zawsze jako „new patch”, więc zostaje sama fraza
    assert "new patch" in names and "patch" not in names
    assert any("update" in name for name in names)
    assert "great" not in names and "co op" not in names
    assert all(t.sentiment is N for t in terms)
    assert next(t for t in terms if t.term == "new patch").count == 5


def test_emerging_terms_needs_both_periods():
    rows = corpus([("new patch", 0.1, 5)], hours_ago=1)
    assert emerging_terms(rows, 7, NOW) == []
    assert emerging_terms([], 7, NOW) == []
