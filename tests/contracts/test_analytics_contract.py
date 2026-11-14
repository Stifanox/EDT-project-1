"""Test kontraktu OpinionAnalytics. O3: dopisz swoją implementację do ANALYTICS_FACTORIES."""

from __future__ import annotations

import pandas as pd
import pytest

from opimon.analytics import BasicAnalytics, SentimentAnalytics
from opimon.interfaces import OpinionAnalytics
from opimon.models import Alert, Prediction, ScoredReview, Sentiment, SentimentSummary, TermStat

ANALYTICS_FACTORIES = [
    pytest.param(BasicAnalytics, id="basic_stub"),
    pytest.param(SentimentAnalytics, id="sentiment_analytics"),
]

TREND_COLUMNS = ["period", "positive", "negative", "total", "positive_share"]
COMPARE_COLUMNS = ["target_id", "total", "positive", "negative", "positive_share"]


def _required_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    """Wymagane kolumny są pierwsze i w tej kolejności; dodatkowe dalej są dozwolone."""
    return list(df.columns)[: len(required)]


@pytest.fixture(params=ANALYTICS_FACTORIES)
def analytics(request) -> OpinionAnalytics:
    return request.param()


@pytest.fixture
def rows(tiny_reviews) -> list[ScoredReview]:
    """r1..r5 z predykcją zgodną z etykietą, r5 bez predykcji."""
    out = []
    for r in tiny_reviews:
        pred = None
        if r.external_id != "r5":
            pred = Prediction(r.id, "m", 0.9 if r.label is Sentiment.POSITIVE else 0.1)
        out.append(ScoredReview(r, pred))
    return out


def test_implements_protocol(analytics):
    assert isinstance(analytics, OpinionAnalytics)


def test_summary(analytics, rows):
    s = analytics.summary(rows)
    assert isinstance(s, SentimentSummary)
    assert (s.total, s.positive, s.negative, s.unscored) == (5, 2, 2, 1)
    assert s.positive_share == 0.5 and s.avg_score == pytest.approx(0.5)
    empty = analytics.summary([])
    assert (empty.total, empty.positive_share, empty.avg_score) == (0, None, None)


def test_trend(analytics, rows):
    df = analytics.trend(rows, "D")
    assert _required_columns(df, TREND_COLUMNS) == TREND_COLUMNS
    assert df["period"].is_monotonic_increasing
    assert int(df["total"].sum()) == 5
    assert int(df["positive"].sum()) == 2 and int(df["negative"].sum()) == 2
    assert pd.api.types.is_numeric_dtype(df["positive_share"])
    assert str(df["period"].dt.tz) == "UTC"
    assert _required_columns(analytics.trend([], "D"), TREND_COLUMNS) == TREND_COLUMNS


def test_compare_targets(analytics, rows):
    df = analytics.compare_targets(rows)
    assert _required_columns(df, COMPARE_COLUMNS) == COMPARE_COLUMNS
    assert list(df["target_id"]) == ["test:t1", "test:t2"]
    assert list(df["total"]) == [3, 2]
    t1 = df.iloc[0]
    assert (t1["positive"], t1["negative"]) == (2, 1)
    assert t1["positive_share"] == pytest.approx(2 / 3)
    assert _required_columns(analytics.compare_targets([]), COMPARE_COLUMNS) == COMPARE_COLUMNS


def test_top_terms(analytics, rows):
    neg = analytics.top_terms(rows, Sentiment.NEGATIVE, n=5)
    assert 0 < len(neg) <= 5 and all(isinstance(t, TermStat) for t in neg)
    terms = {t.term for t in neg}
    assert terms & {"terrible", "boring", "crashes", "repetitive", "waste", "grind"}
    assert not terms & {"the", "and", "of"}, "stop-słowa"
    assert all(t.sentiment is Sentiment.NEGATIVE for t in neg)
    pos_terms = {t.term for t in analytics.top_terms(rows, Sentiment.POSITIVE, n=50)}
    assert "relaxing" not in pos_terms, "r5 nie ma predykcji"
    assert analytics.top_terms([], Sentiment.POSITIVE) == []


def test_alerts_types(analytics, rows):
    alerts = analytics.alerts(rows)
    assert isinstance(alerts, list) and all(isinstance(a, Alert) for a in alerts)
    assert analytics.alerts([]) == []
