"""Testy A1: trend z wygładzaniem, przedziały Wilsona, filtr okresu, zgodność z etykietą."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from opimon.analytics import (
    PERIOD_OPTIONS,
    SentimentAnalytics,
    filter_period,
    label_agreement,
    wilson_interval,
)
from opimon.models import Prediction, ScoredReview, Sentiment
from opimon.services import _make_analytics
from tests.conftest import NOW, make_review

P, N = Sentiment.POSITIVE, Sentiment.NEGATIVE


def scored(review, score: float | None) -> ScoredReview:
    return ScoredReview(review, None if score is None else Prediction(review.id, "m", score))


@pytest.fixture
def analytics() -> SentimentAnalytics:
    return SentimentAnalytics()


@pytest.fixture
def daily_rows() -> list[ScoredReview]:
    """NOW = 2026-11-01 12:00 UTC.
    29.10: 2 poz. · 30.10: brak · 31.10: 1 neg. + 1 bez predykcji · 01.11: 1 poz. + 1 neg."""
    return [
        scored(make_review("a", "x", 1), 0.9),
        scored(make_review("b", "x", 2), 0.1),
        scored(make_review("c", "x", 25), 0.2),
        scored(make_review("d", "x", 26), None),
        scored(make_review("e", "x", 73), 0.8),
        scored(make_review("f", "x", 74), 0.7),
    ]


# ----------------------------------------------------------------------------- trend
def test_trend_fills_empty_periods(analytics, daily_rows):
    df = analytics.trend(daily_rows, "D", window=2)
    assert list(df["period"]) == list(pd.date_range("2026-10-29", periods=4, freq="D", tz="UTC"))
    assert list(df["total"]) == [2, 0, 2, 2]
    assert list(df["positive"]) == [2, 0, 0, 1]
    assert list(df["negative"]) == [0, 0, 1, 1]
    share = df["positive_share"].tolist()
    assert share[0] == 1.0 and math.isnan(share[1]) and share[2] == 0.0 and share[3] == 0.5
    for col in ("positive", "negative", "total"):
        assert pd.api.types.is_integer_dtype(df[col])


def test_trend_smoothed_is_count_weighted_rolling_share(analytics, daily_rows):
    df = analytics.trend(daily_rows, "D", window=2)
    # okno 2: (2)/(2), (2+0)/(2+0), (0+0)/(0+1), (0+1)/(1+2)
    assert df["positive_share_smoothed"].tolist() == pytest.approx([1.0, 1.0, 0.0, 1 / 3])


def test_trend_default_window_depends_on_freq(analytics, daily_rows):
    assert analytics.smoothing_window("D") == 7
    assert analytics.smoothing_window("W") == 4
    df = analytics.trend(daily_rows, "D")
    # okno 7 obejmuje wszystkie dni: 3 poz. / 5 przeanalizowanych
    assert df["positive_share_smoothed"].iloc[-1] == pytest.approx(3 / 5)


def test_trend_weekly_and_monthly(analytics, daily_rows):
    rows = [*daily_rows, scored(make_review("old", "x", 15 * 24), 0.9)]   # sobota 17.10
    weekly = analytics.trend(rows, "W")
    assert list(weekly["period"]) == list(
        pd.to_datetime(["2026-10-12", "2026-10-19", "2026-10-26"]).tz_localize("UTC")
    )
    assert list(weekly["total"]) == [1, 0, 6]
    monthly = analytics.trend(rows, "MS")
    assert list(monthly["period"]) == list(
        pd.to_datetime(["2026-10-01", "2026-11-01"]).tz_localize("UTC")
    )
    assert list(monthly["total"]) == [5, 2]


def test_trend_empty_and_unscored_only(analytics):
    empty = analytics.trend([], "D")
    assert empty.empty and "positive_share_smoothed" in empty.columns
    df = analytics.trend([scored(make_review("u", "x"), None)], "D")
    assert list(df["total"]) == [1]
    assert math.isnan(df["positive_share"].iloc[0])
    assert math.isnan(df["positive_share_smoothed"].iloc[0])


# ------------------------------------------------------------------------ Wilson / CI
@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [(2, 3, 0.2077, 0.9385), (8, 10, 0.4902, 0.9433), (0, 1, 0.0, 0.7935), (5, 5, 0.5655, 1.0)],
)
def test_wilson_interval_known_values(k, n, low, high):
    lo, hi = wilson_interval(k, n)
    assert (lo, hi) == pytest.approx((low, high), abs=1e-4)


def test_wilson_interval_edge_cases():
    assert all(math.isnan(v) for v in wilson_interval(0, 0))
    with pytest.raises(ValueError):
        wilson_interval(4, 3)


def test_compare_targets_has_wilson_ci(analytics, tiny_reviews):
    rows = [scored(r, None if r.external_id == "r5" else (0.9 if r.label is P else 0.1))
            for r in tiny_reviews]
    rows.append(scored(make_review("u", "x", target="t3"), None))
    df = analytics.compare_targets(rows)
    assert list(df["target_id"]) == ["test:t1", "test:t2", "test:t3"]
    t1, t2, t3 = (df.iloc[i] for i in range(3))
    assert (t1["ci_low"], t1["ci_high"]) == pytest.approx((0.2077, 0.9385), abs=1e-4)
    assert (t2["ci_low"], t2["ci_high"]) == pytest.approx((0.0, 0.7935), abs=1e-4)
    assert math.isnan(t3["positive_share"]) and math.isnan(t3["ci_low"])
    assert t1["ci_low"] <= t1["positive_share"] <= t1["ci_high"]
    assert pd.api.types.is_float_dtype(df["ci_low"])
    assert "ci_low" in analytics.compare_targets([]).columns


# ---------------------------------------------------------------------- filter_period
def test_filter_period(tiny_reviews):
    rows = [scored(r, 0.5) for r in tiny_reviews]          # 1, 2, 30, 50, 80 godzin temu
    ids = lambda out: [r.review.external_id for r in out]  # noqa: E731
    assert ids(filter_period(rows, 1, NOW)) == ["r1", "r2"]
    assert ids(filter_period(rows, 3, NOW)) == ["r1", "r2", "r3", "r4"]
    assert ids(filter_period(rows, None, NOW)) == ["r1", "r2", "r3", "r4", "r5"]
    assert filter_period([], 7, NOW) == []
    with pytest.raises(ValueError):
        filter_period(rows, 0, NOW)
    assert list(PERIOD_OPTIONS) == [7, 30, 90, None]


# -------------------------------------------------------------------- label_agreement
def test_label_agreement(tiny_reviews):
    scores = {"r1": 0.9, "r2": 0.8, "r3": 0.7, "r4": 0.2, "r5": None}   # r2 błędnie poz.
    rows = [scored(r, scores[r.external_id]) for r in tiny_reviews]
    rows.append(scored(make_review("nolabel", "x"), 0.9))                # bez etykiety
    agreement = label_agreement(rows)
    assert (agreement.n, agreement.agree, agreement.disagree) == (4, 3, 1)
    assert agreement.share == 0.75
    assert agreement.ci_low < 0.75 < agreement.ci_high


def test_label_agreement_empty():
    agreement = label_agreement([scored(make_review("u", "x", label=P), None)])
    assert agreement.n == 0 and agreement.share is None and math.isnan(agreement.ci_low)


def test_factory_uses_full_analytics():
    assert isinstance(_make_analytics(), SentimentAnalytics)
