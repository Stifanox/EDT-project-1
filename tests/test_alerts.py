"""A5: alerty o spadku udziału pozytywnych i skoku liczby negatywnych opinii."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon.analytics.alerts import VOLUME_MIN_NEGATIVE, compute_alerts
from opimon.models import AlertLevel, Prediction, ScoredReview, Sentiment
from opimon.services import build_services
from opimon.ui import nav
from opimon.ui.state import get_services
from tests.conftest import NOW, make_review

ROOT = Path(__file__).resolve().parents[1]
P, N = Sentiment.POSITIVE, Sentiment.NEGATIVE
STARFALL = "sample:starfall"


def scored(
    external_id: str,
    hours_ago: float,
    score: float,
    target: str = "t1",
    label: Sentiment | None = None,
) -> ScoredReview:
    review = make_review(external_id, "x", hours_ago, target=target, label=label)
    return ScoredReview(review, Prediction(review.id, "m", score))


def batch(
    target: str, start_hours: float, scores: list[float], step_hours: float = 1.0
) -> list[ScoredReview]:
    return [
        scored(f"{target}-{i}", start_hours + i * step_hours, score, target=target)
        for i, score in enumerate(scores)
    ]


# --------------------------------------------------------------------------- logika
def test_share_drop_warning_and_critical():
    # okno bieżące (0–7 dni): 3 poz. / 10 = 30%; odniesienie (7–37 dni): 9 / 10 = 90%
    current = batch("t1", 1, [0.9, 0.9, 0.9] + [0.1] * 7)
    baseline = batch("t1", 8 * 24, [0.9] * 9 + [0.1], step_hours=24)
    alerts = [a for a in compute_alerts([*current, *baseline], NOW)
              if "udział pozytywnych" in a.message]
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.target_id == "test:t1"
    assert alert.level is AlertLevel.CRITICAL          # spadek 60 p.p. ≥ 2 × 15
    assert alert.current_share == pytest.approx(0.3)
    assert alert.baseline_share == pytest.approx(0.9)
    assert "udział pozytywnych spadł z 90% do 30%" in alert.message
    assert "ostatnich 7 dniach" in alert.message and "−60 p.p." in alert.message


def test_share_drop_warning_below_double_threshold():
    # 50% teraz vs 70% wcześniej = −20 p.p. (warning, nie critical)
    current = batch("t1", 1, [0.9] * 5 + [0.1] * 5)
    baseline = batch("t1", 8 * 24, [0.9] * 7 + [0.1] * 3, step_hours=24)
    alerts = [a for a in compute_alerts([*current, *baseline], NOW)
              if "udział pozytywnych" in a.message]
    assert len(alerts) == 1 and alerts[0].level is AlertLevel.WARNING


def test_no_alert_when_below_min_reviews_or_threshold(monkeypatch):
    monkeypatch.setattr(config, "ALERT_MIN_REVIEWS", 10)
    few = batch("t1", 1, [0.1] * 5) + batch("t1", 8 * 24, [0.9] * 5, step_hours=24)
    assert compute_alerts(few, NOW) == []
    mild = batch("t1", 1, [0.9] * 6 + [0.1] * 4) + batch(
        "t1", 8 * 24, [0.9] * 7 + [0.1] * 3, step_hours=24)
    assert all("udział pozytywnych" not in a.message for a in compute_alerts(mild, NOW))


def test_volume_spike_alert():
    # bieżące: 8 negatywnych w 7 dniach (~1,14/dzień); odniesienie: 2 w 30 dniach
    # (tempo odniesienia z +1 ≈ 0,1/dzień) -> × ≈ 11,4 → CRITICAL (≥ 4×)
    current = batch("t1", 1, [0.1] * 8 + [0.9] * 4)
    baseline = batch("t1", 8 * 24, [0.9] * 10 + [0.1] * 2, step_hours=48)
    alerts = [a for a in compute_alerts([*current, *baseline], NOW)
              if "negatywnych opinii" in a.message]
    assert len(alerts) == 1
    assert alerts[0].level is AlertLevel.CRITICAL
    assert "8 w ostatnich 7 dniach" in alerts[0].message
    assert alerts[0].message.startswith("liczba negatywnych opinii wzrosła")

    # mniejszy skok: 5 negatywnych teraz vs 6 w odniesieniu → ×≈3,1 → WARNING
    mild_cur = batch("t2", 1, [0.1] * 5 + [0.9] * 10)
    mild_base = batch("t2", 8 * 24, [0.9] * 12 + [0.1] * 6, step_hours=40)
    mild = [a for a in compute_alerts([*mild_cur, *mild_base], NOW)
            if "negatywnych opinii" in a.message]
    assert len(mild) == 1 and mild[0].level is AlertLevel.WARNING


def test_volume_ignores_small_negative_counts():
    current = batch("t1", 1, [0.1] * (VOLUME_MIN_NEGATIVE - 1) + [0.9] * 10)
    baseline = batch("t1", 8 * 24, [0.9] * 12, step_hours=48)
    assert all("negatywnych opinii" not in a.message
               for a in compute_alerts([*current, *baseline], NOW))


def test_alerts_per_target_and_empty():
    bad = batch("bad", 1, [0.1] * 10) + batch("bad", 8 * 24, [0.9] * 10, step_hours=24)
    good = batch("good", 1, [0.9] * 10) + batch("good", 8 * 24, [0.9] * 8 + [0.1] * 2,
                                                 step_hours=24)
    alerts = compute_alerts([*bad, *good], NOW)
    assert {a.target_id for a in alerts} == {"test:bad"}
    assert compute_alerts([], NOW) == []


def test_sample_data_alerts_only_starfall():
    services = build_services(load_samples=True)
    services.load_samples_if_empty()
    rows = services.scored_reviews()
    # Dane demo mają daty względne do „dziś”, więc używamy bieżącego czasu UTC.
    from opimon.models import utcnow

    now = utcnow()
    alerts = services.analytics.alerts(rows, now)
    targets = {a.target_id for a in alerts}
    assert STARFALL in targets
    assert "sample:harbor" not in targets and "sample:bakery" not in targets
    starfall = [a for a in alerts if a.target_id == STARFALL]
    assert any("udział pozytywnych spadł" in a.message for a in starfall)
    share = next(a for a in starfall if "udział pozytywnych" in a.message)
    assert share.current_share is not None and share.baseline_share is not None
    assert share.baseline_share - share.current_share >= config.ALERT_DROP_PP / 100


# --------------------------------------------------------------------------- GUI
@pytest.fixture(autouse=True)
def fresh_services(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    get_services.clear()
    yield
    get_services.clear()


def open_dashboard() -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.switch_page(nav.PAGE_DASHBOARD).run()
    assert not at.exception, at.exception
    return at


def test_dashboard_shows_starfall_alert_and_opens_reviews():
    at = open_dashboard()
    texts = [w.value for w in at.warning] + [e.value for e in at.error]
    assert any("Starfall Odyssey" in t and "udział pozytywnych" in t for t in texts)
    assert not any("Iron Harbor" in t or "Pixel Bakery" in t for t in texts)
    at.button(key="dash_alert_reviews_0").click().run()
    assert not at.exception, at.exception
    assert at.session_state["rev_target"] == STARFALL
    assert at.session_state["rev_sentiment"] == "negative"
    assert at.session_state["rev_date_from"] is not None


def test_alert_dashboard_button_opens_target():
    at = open_dashboard()
    at.button(key="dash_alert_dash_0").click().run()
    assert not at.exception, at.exception
    assert at.session_state["dash_target"] == STARFALL
