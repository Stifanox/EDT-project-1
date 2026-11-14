"""A3: filtry przeglądarki opinii, paginacja i podświetlanie – bez Streamlit."""

from __future__ import annotations

from datetime import date

import pytest

from opimon.analytics.filters import (
    ReviewQuery,
    apply_filters,
    highlight_html,
    is_misclassified,
    paginate,
)
from opimon.models import Prediction, ScoredReview, Sentiment
from tests.conftest import make_review

P, N = Sentiment.POSITIVE, Sentiment.NEGATIVE


def scored(external_id, text="x", hours_ago=1.0, label=None, score=None) -> ScoredReview:
    review = make_review(external_id, text, hours_ago, label=label)
    return ScoredReview(review, None if score is None else Prediction(review.id, "m", score))


@pytest.fixture
def rows() -> list[ScoredReview]:
    # NOW = 2026-11-01 12:00 UTC
    return [
        scored("a", "Great PATCH, love it", 1, P, 0.95),      # 01.11, zgodna
        scored("b", "Broken after the patch", 13, P, 0.10),   # 31.10 23:00, model się myli
        scored("c", "Fine game", 30, N, 0.55),                # 31.10, model się myli, niepewna
        scored("d", "Awful", 60, N, 0.05),                    # 30.10, zgodna
        scored("e", "No prediction yet", 80, P, None),        # 29.10, bez predykcji
    ]


def ids(out: list[ScoredReview]) -> list[str]:
    return [r.review.external_id for r in out]


def test_no_filters_keeps_everything_in_order(rows):
    assert ids(apply_filters(rows, ReviewQuery())) == ["a", "b", "c", "d", "e"]


@pytest.mark.parametrize(("sentiment", "expected"), [
    ("positive", ["a", "c"]), ("negative", ["b", "d"]), ("unscored", ["e"]),
])
def test_sentiment_filter(rows, sentiment, expected):
    assert ids(apply_filters(rows, ReviewQuery(sentiment=sentiment))) == expected


def test_unknown_sentiment_raises(rows):
    with pytest.raises(ValueError):
        apply_filters(rows, ReviewQuery(sentiment="neutral"))


def test_term_is_case_insensitive_phrase(rows):
    assert ids(apply_filters(rows, ReviewQuery(term="patch"))) == ["a", "b"]
    assert ids(apply_filters(rows, ReviewQuery(term="  the PATCH "))) == ["b"]


def test_keyword_phrase_matches_across_stopwords():
    rows = [scored("w", "Honestly a waste of money."), scored("x", "Money is a waste")]
    assert ids(apply_filters(rows, ReviewQuery(term="waste money"))) == ["w"]
    out = highlight_html("Honestly a Waste of money.", "waste money")
    assert '<mark style="background:#ffe066">Waste of money</mark>' in out


def test_date_range_is_inclusive_whole_days(rows):
    q = ReviewQuery(date_from=date(2026, 10, 30), date_to=date(2026, 10, 31))
    assert ids(apply_filters(rows, q)) == ["b", "c", "d"]
    assert ids(apply_filters(rows, ReviewQuery(date_from=date(2026, 11, 1)))) == ["a"]
    assert ids(apply_filters(rows, ReviewQuery(date_to=date(2026, 10, 29)))) == ["e"]


def test_score_range_excludes_unscored_only_when_narrowed(rows):
    assert ids(apply_filters(rows, ReviewQuery(score_min=0.4, score_max=0.6))) == ["c"]
    assert ids(apply_filters(rows, ReviewQuery(score_min=0.0, score_max=0.1))) == ["b", "d"]
    assert "e" in ids(apply_filters(rows, ReviewQuery(score_min=0.0, score_max=1.0)))


def test_only_wrong(rows):
    assert ids(apply_filters(rows, ReviewQuery(only_wrong=True))) == ["b", "c"]
    assert not is_misclassified(rows[4])                     # bez predykcji
    assert not is_misclassified(scored("x", score=0.9))      # bez etykiety


def test_filters_combine(rows):
    q = ReviewQuery(sentiment="negative", term="patch", only_wrong=True)
    assert ids(apply_filters(rows, q)) == ["b"]


def test_paginate():
    many = [scored(str(i)) for i in range(1201)]
    page = paginate(many, 1, 50)
    assert (len(page.rows), page.number, page.count, page.start) == (50, 1, 25, 0)
    last = paginate(many, 25, 50)
    assert (len(last.rows), last.start) == (1, 1200)
    assert paginate(many, 99, 50).number == 25
    assert paginate(many, 0, 50).number == 1
    empty = paginate([], 3, 50)
    assert (empty.rows, empty.number, empty.count) == ([], 1, 1)
    with pytest.raises(ValueError):
        paginate(many, 1, 0)


def test_highlight_term_escapes_and_keeps_case():
    out = highlight_html("<b>Patch</b> broke the patch\nagain", "patch")
    assert "&lt;b&gt;" in out and "<b>" not in out
    assert out.count("<mark") == 2
    assert ">Patch</mark>" in out and ">patch</mark>" in out
    assert "<br>" in out


def test_highlight_explanation_words():
    out = highlight_html("Great art but boring start", weights=[("great", 1.2), ("boring", -0.8),
                                                                ("art", 0.3), ("zero", 0.0)])
    assert 'background:#c9f2d5">Great</mark>' in out
    assert 'background:#f9d0cd">boring</mark>' in out
    assert out.count("<mark") == 3                         # „start” nie zawiera słowa „art”


def test_highlight_without_patterns_is_escaped_text():
    assert highlight_html("a < b") == "a &lt; b"
