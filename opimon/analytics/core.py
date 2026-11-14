"""Pełna analityka sentymentu (A1–A5): trend z wygładzaniem, porównanie obiektów,
filtrowanie okresu, zgodność z etykietą, słowa kluczowe i alerty.

Wszystkie funkcje są czyste (bez Streamlit).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from opimon.analytics.stub import COMPARE_COLUMNS, TREND_COLUMNS, BasicAnalytics, to_frame
from opimon.interfaces import OpinionAnalytics
from opimon.models import Alert, ScoredReview, Sentiment, SentimentSummary, TermStat, utcnow

SMOOTHED_COLUMN = "positive_share_smoothed"
TREND_COLUMNS_EXT = [*TREND_COLUMNS, SMOOTHED_COLUMN]
COMPARE_COLUMNS_EXT = [*COMPARE_COLUMNS, "ci_low", "ci_high"]

Z_95 = 1.959963984540054
# Okno średniej kroczącej (liczba okresów) zależnie od częstotliwości trendu.
SMOOTHING_WINDOWS = {"D": 7, "W": 4, "M": 3}
DEFAULT_SMOOTHING_WINDOW = 3

# Okresy do wyboru w GUI: liczba dni -> etykieta; None = wszystko.
PERIOD_OPTIONS: dict[int | None, str] = {
    7: "Ostatnie 7 dni",
    30: "Ostatnie 30 dni",
    90: "Ostatnie 90 dni",
    None: "Wszystko",
}

# Częstotliwości „początek okresu” z pandas, których nie przyjmuje `Period`.
_PERIOD_FREQ = {"MS": "M", "QS": "Q", "YS": "Y", "AS": "Y"}


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Przedział ufności Wilsona dla proporcji `successes / n`; `n == 0` -> (NaN, NaN)."""
    if n <= 0:
        return math.nan, math.nan
    if not 0 <= successes <= n:
        raise ValueError(f"successes={successes} poza zakresem [0, {n}]")
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def filter_period(
    rows: Sequence[ScoredReview], days: int | None, now: datetime | None = None
) -> list[ScoredReview]:
    """Opinie z ostatnich `days` dni (`created_at >= now - days`); `days=None` -> wszystkie."""
    if days is None:
        return list(rows)
    if days <= 0:
        raise ValueError(f"days musi być dodatnie albo None, dostano {days}")
    cutoff = (now or utcnow()) - timedelta(days=days)
    return [r for r in rows if r.review.created_at >= cutoff]


def previous_period(
    rows: Sequence[ScoredReview], days: int | None, now: datetime | None = None
) -> list[ScoredReview]:
    """Opinie z okresu bezpośrednio poprzedzającego `filter_period` (tej samej długości):
    `now - 2·days <= created_at < now - days`; `days=None` -> `[]` (brak okresu odniesienia)."""
    if days is None:
        return []
    if days <= 0:
        raise ValueError(f"days musi być dodatnie albo None, dostano {days}")
    now = now or utcnow()
    start, end = now - timedelta(days=2 * days), now - timedelta(days=days)
    return [r for r in rows if start <= r.review.created_at < end]


@dataclass(frozen=True, slots=True)
class PeriodKpis:
    """KPI wybranego okresu z porównaniem do poprzedniego okresu tej samej długości."""

    current: SentimentSummary
    previous: SentimentSummary | None     # None, gdy okres = „wszystko”
    ci_low: float                         # Wilson 95% dla udziału pozytywnych; NaN gdy brak
    ci_high: float

    @property
    def total_change(self) -> int | None:
        return None if self.previous is None else self.current.total - self.previous.total

    @property
    def negative_change(self) -> int | None:
        return None if self.previous is None else self.current.negative - self.previous.negative

    @property
    def share_change_pp(self) -> float | None:
        """Zmiana udziału pozytywnych w punktach procentowych; None, gdy brak danych."""
        if self.previous is None:
            return None
        cur, prev = self.current.positive_share, self.previous.positive_share
        return None if cur is None or prev is None else (cur - prev) * 100


def period_kpis(
    analytics: OpinionAnalytics,
    rows: Sequence[ScoredReview],
    days: int | None,
    now: datetime | None = None,
) -> PeriodKpis:
    """KPI dla ostatnich `days` dni (`None` = wszystko) i zmiana względem poprzedniego okresu."""
    now = now or utcnow()
    current = analytics.summary(filter_period(rows, days, now))
    previous = None if days is None else analytics.summary(previous_period(rows, days, now))
    low, high = wilson_interval(current.positive, current.positive + current.negative)
    return PeriodKpis(current, previous, low, high)


@dataclass(frozen=True, slots=True)
class LabelAgreement:
    """Zgodność predykcji modelu z etykietą ze źródła (opinie mające jedno i drugie)."""

    n: int                 # opinie z predykcją i etykietą
    agree: int             # predykcja == etykieta
    ci_low: float          # przedział Wilsona dla `share`; NaN gdy n == 0
    ci_high: float

    @property
    def disagree(self) -> int:
        return self.n - self.agree

    @property
    def share(self) -> float | None:
        """Udział zgodnych (0–1) albo None, gdy brak opinii z etykietą i predykcją."""
        return self.agree / self.n if self.n else None


def label_agreement(rows: Sequence[ScoredReview]) -> LabelAgreement:
    """Jak często predykcja modelu zgadza się z etykietą ze źródła (np. Steam `voted_up`)."""
    both = [r for r in rows if r.sentiment is not None and r.review.label is not None]
    agree = sum(r.sentiment is r.review.label for r in both)
    low, high = wilson_interval(agree, len(both))
    return LabelAgreement(len(both), agree, low, high)


def _period_freq(freq: str) -> str:
    return _PERIOD_FREQ.get(freq, freq)


def period_bounds(start: datetime, freq: str) -> tuple[date, date]:
    """Pierwszy i ostatni dzień (UTC, włącznie) okresu trendu zaczynającego się w `start`."""
    period = pd.Timestamp(start).tz_convert(None).to_period(_period_freq(freq))
    return period.start_time.date(), period.end_time.date()


class SentimentAnalytics(BasicAnalytics):
    """Implementacja `OpinionAnalytics` (A1; A4 i A5 rozbudowują `top_terms` i `alerts`)."""

    def __init__(self, smoothing_windows: dict[str, int] | None = None) -> None:
        self.smoothing_windows = dict(SMOOTHING_WINDOWS if smoothing_windows is None
                                      else smoothing_windows)

    def smoothing_window(self, freq: str) -> int:
        return self.smoothing_windows.get(_period_freq(freq), DEFAULT_SMOOTHING_WINDOW)

    def trend(
        self, rows: Sequence[ScoredReview], freq: str = "D", window: int | None = None
    ) -> pd.DataFrame:
        """Trend z uzupełnionymi pustymi okresami (`total=0`, udział NaN) i kolumną
        `positive_share_smoothed`: udział pozytywnych w ostatnich `window` okresach
        (średnia krocząca ważona liczbą przeanalizowanych opinii)."""
        if not rows:
            return pd.DataFrame(columns=TREND_COLUMNS_EXT)
        df = to_frame(rows)
        periods = df["created_at"].dt.tz_convert(None).dt.to_period(_period_freq(freq))
        df["positive"] = (df["sentiment"] == "positive").astype(int)
        df["negative"] = (df["sentiment"] == "negative").astype(int)
        df["total"] = 1
        counts = df.groupby(periods)[["positive", "negative", "total"]].sum()
        full = pd.period_range(periods.min(), periods.max(), freq=periods.dt.freq)
        out = counts.reindex(full, fill_value=0).astype(int)

        scored = out["positive"] + out["negative"]
        out["positive_share"] = (out["positive"] / scored.where(scored > 0)).astype(float)
        w = window or self.smoothing_window(freq)
        roll_pos = out["positive"].rolling(w, min_periods=1).sum()
        roll_scored = scored.rolling(w, min_periods=1).sum()
        out[SMOOTHED_COLUMN] = (roll_pos / roll_scored.where(roll_scored > 0)).astype(float)

        out.index = full.start_time.tz_localize("UTC")
        out = out.rename_axis("period").reset_index()
        return out[TREND_COLUMNS_EXT]

    def top_terms(
        self, rows: Sequence[ScoredReview], sentiment: Sentiment, n: int = 20
    ) -> list[TermStat]:
        """Słowa i bigramy ważone z-score log-odds (A4, `analytics.terms`)."""
        from opimon.analytics.terms import top_terms

        return top_terms(rows, sentiment, n)

    def alerts(self, rows: Sequence[ScoredReview], now: datetime | None = None) -> list[Alert]:
        """Spadek udziału pozytywnych i skok liczby negatywnych opinii (A5, `analytics.alerts`)."""
        from opimon.analytics.alerts import compute_alerts

        return compute_alerts(rows, now)

    def compare_targets(self, rows: Sequence[ScoredReview]) -> pd.DataFrame:
        """Porównanie obiektów + przedział Wilsona (95%) udziału pozytywnych."""
        if not rows:
            return pd.DataFrame(columns=COMPARE_COLUMNS_EXT)
        out = super().compare_targets(rows)
        bounds = [
            wilson_interval(int(p), int(p + n))
            for p, n in zip(out["positive"], out["negative"], strict=True)
        ]
        out["ci_low"] = [b[0] for b in bounds]
        out["ci_high"] = [b[1] for b in bounds]
        return out[COMPARE_COLUMNS_EXT]
