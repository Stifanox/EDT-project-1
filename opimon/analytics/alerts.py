"""Alerty o pogorszeniu sentymentu (A5), liczone osobno dla każdego obiektu.

Okno bieżące = ostatnie `ALERT_WINDOW_DAYS` dni; okno odniesienia = `ALERT_BASELINE_DAYS` dni
bezpośrednio przed nim. Progi czytane z `config` w chwili wywołania.

* Spadek udziału pozytywnych o ≥ `ALERT_DROP_PP` p.p. (oba okna z ≥ `ALERT_MIN_REVIEWS`
  opiniami z predykcją) -> WARNING; spadek ≥ 2 × próg -> CRITICAL.
* Skok liczby negatywnych opinii: ≥ `VOLUME_MIN_NEGATIVE` w oknie bieżącym i dzienne tempo
  ≥ `VOLUME_RATIO` × tempo w oknie odniesienia (z wygładzeniem +1, okno odniesienia z ≥
  `ALERT_MIN_REVIEWS` opiniami) -> WARNING; ≥ `VOLUME_CRITICAL_RATIO` × -> CRITICAL.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from opimon import config
from opimon.models import Alert, AlertLevel, ScoredReview, Sentiment, utcnow

VOLUME_MIN_NEGATIVE = 5
VOLUME_RATIO = 2.0
VOLUME_CRITICAL_RATIO = 4.0


def _num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _counts(rows: Sequence[ScoredReview]) -> tuple[int, int, int]:
    pos = sum(r.sentiment is Sentiment.POSITIVE for r in rows)
    neg = sum(r.sentiment is Sentiment.NEGATIVE for r in rows)
    return pos, neg, len(rows)


def _share_alert(target_id: str, current: Sequence[ScoredReview],
                 baseline: Sequence[ScoredReview], now: datetime) -> Alert | None:
    window, base_days = config.ALERT_WINDOW_DAYS, config.ALERT_BASELINE_DAYS
    min_reviews, threshold = config.ALERT_MIN_REVIEWS, config.ALERT_DROP_PP
    c_pos, c_neg, _ = _counts(current)
    b_pos, b_neg, _ = _counts(baseline)
    c_n, b_n = c_pos + c_neg, b_pos + b_neg
    if c_n < min_reviews or b_n < min_reviews:
        return None
    cur, base = c_pos / c_n, b_pos / b_n
    drop = (base - cur) * 100
    if drop < threshold:
        return None
    level = AlertLevel.CRITICAL if drop >= 2 * threshold else AlertLevel.WARNING
    message = (
        f"udział pozytywnych spadł z {base:.0%} do {cur:.0%} w ostatnich {window} dniach "
        f"(−{_num(drop, 0)} p.p.; {c_n} opinii wobec {b_n} w poprzednich {base_days} dniach)"
    )
    return Alert(target_id, level, message, current_share=cur, baseline_share=base,
                 detected_at=now)


def _volume_alert(target_id: str, current: Sequence[ScoredReview],
                  baseline: Sequence[ScoredReview], now: datetime) -> Alert | None:
    window, base_days = config.ALERT_WINDOW_DAYS, config.ALERT_BASELINE_DAYS
    c_pos, c_neg, _ = _counts(current)
    b_pos, b_neg, b_total = _counts(baseline)
    if c_neg < VOLUME_MIN_NEGATIVE or b_total < config.ALERT_MIN_REVIEWS:
        return None
    cur_rate, base_rate = c_neg / window, (b_neg + 1) / base_days
    ratio = cur_rate / base_rate
    if ratio < VOLUME_RATIO:
        return None
    level = AlertLevel.CRITICAL if ratio >= VOLUME_CRITICAL_RATIO else AlertLevel.WARNING
    message = (f"liczba negatywnych opinii wzrosła: {c_neg} w ostatnich {window} dniach "
               f"({_num(cur_rate)} dziennie) wobec {_num(b_neg / base_days)} dziennie "
               f"w poprzednich {base_days} dniach (×{_num(ratio)})")
    c_n, b_n = c_pos + c_neg, b_pos + b_neg
    return Alert(target_id, level, message,
                 current_share=c_pos / c_n if c_n else None,
                 baseline_share=b_pos / b_n if b_n else None, detected_at=now)


def compute_alerts(rows: Sequence[ScoredReview], now: datetime | None = None) -> list[Alert]:
    """Alerty dla wszystkich obiektów w `rows`; najpierw CRITICAL, potem wg obiektu."""
    now = now or utcnow()
    window_start = now - timedelta(days=config.ALERT_WINDOW_DAYS)
    baseline_start = window_start - timedelta(days=config.ALERT_BASELINE_DAYS)
    current: dict[str, list[ScoredReview]] = defaultdict(list)
    baseline: dict[str, list[ScoredReview]] = defaultdict(list)
    for r in rows:
        created = r.review.created_at
        if window_start <= created <= now:
            current[r.review.target_id].append(r)
        elif baseline_start <= created < window_start:
            baseline[r.review.target_id].append(r)
    alerts = []
    for target_id in sorted(set(current) | set(baseline)):
        for check in (_share_alert, _volume_alert):
            alert = check(target_id, current[target_id], baseline[target_id], now)
            if alert is not None:
                alerts.append(alert)
    alerts.sort(key=lambda a: (a.level is not AlertLevel.CRITICAL, a.target_id))
    return alerts
