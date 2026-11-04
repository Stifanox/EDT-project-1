"""Zaślepka analityki (P0). A1 (statystyki, trend), A4 (słowa kluczowe), A5 (alerty)
zastępują ją pełną implementacją `OpinionAnalytics`.

Działa poprawnie, ale prosto: trend bez wygładzania, top_terms jako zwykłe zliczanie,
`alerts` zawsze zwraca pustą listę.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

import pandas as pd

from opimon.models import Alert, ScoredReview, Sentiment, SentimentSummary, TermStat
from opimon.textproc import content_tokens

TREND_COLUMNS = ["period", "positive", "negative", "total", "positive_share"]
COMPARE_COLUMNS = ["target_id", "total", "positive", "negative", "positive_share"]


def to_frame(rows: Sequence[ScoredReview]) -> pd.DataFrame:
    """Wiersze -> DataFrame (jeden wiersz na opinię). Wspólny pomocnik dla analityki i GUI."""
    return pd.DataFrame(
        {
            "review_id": [r.review.id for r in rows],
            "target_id": [r.review.target_id for r in rows],
            "created_at": pd.to_datetime([r.review.created_at for r in rows], utc=True),
            "sentiment": [r.sentiment.value if r.sentiment else None for r in rows],
            "score": [r.score for r in rows],
        }
    )


def _counts(df: pd.DataFrame, by: str) -> pd.DataFrame:
    out = df.groupby(by).agg(
        positive=("sentiment", lambda s: int((s == "positive").sum())),
        negative=("sentiment", lambda s: int((s == "negative").sum())),
        total=("review_id", "size"),
    ).reset_index()
    scored = out["positive"] + out["negative"]
    out["positive_share"] = (out["positive"] / scored.where(scored > 0)).astype(float)
    return out


class BasicAnalytics:
    def summary(self, rows: Sequence[ScoredReview]) -> SentimentSummary:
        scored = [r for r in rows if r.prediction is not None]
        pos = sum(r.sentiment is Sentiment.POSITIVE for r in scored)
        avg = sum(r.prediction.score for r in scored) / len(scored) if scored else None
        return SentimentSummary(len(rows), pos, len(scored) - pos, len(rows) - len(scored), avg)

    def trend(self, rows: Sequence[ScoredReview], freq: str = "D") -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=TREND_COLUMNS)
        df = to_frame(rows)
        df["period"] = df["created_at"].dt.tz_convert(None).dt.to_period(freq).dt.start_time
        df["period"] = df["period"].dt.tz_localize("UTC")
        return _counts(df, "period")[TREND_COLUMNS].sort_values("period").reset_index(drop=True)

    def compare_targets(self, rows: Sequence[ScoredReview]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=COMPARE_COLUMNS)
        out = _counts(to_frame(rows), "target_id")[COMPARE_COLUMNS]
        return out.sort_values(["total", "target_id"], ascending=[False, True]).reset_index(
            drop=True
        )

    def top_terms(
        self, rows: Sequence[ScoredReview], sentiment: Sentiment, n: int = 20
    ) -> list[TermStat]:
        counter: Counter[str] = Counter()
        for r in rows:
            if r.sentiment is sentiment:
                counter.update(set(content_tokens(r.review.text)))
        return [TermStat(t, c, sentiment, float(c)) for t, c in counter.most_common(n)]

    def alerts(self, rows: Sequence[ScoredReview], now: datetime | None = None) -> list[Alert]:
        return []   # TODO(A5)
