"""A6: eksport CSV i raport HTML (bez Streamlit)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon.analytics import SentimentAnalytics, render_report, reviews_to_csv
from opimon.models import Prediction, ScoredReview, Sentiment, Target, utcnow
from opimon.ui import nav
from opimon.ui.state import get_services
from tests.conftest import make_review

ROOT = Path(__file__).resolve().parents[1]
P, N = Sentiment.POSITIVE, Sentiment.NEGATIVE


def scored(external_id: str, text: str, hours_ago: float, score: float,
           label: Sentiment | None = None) -> ScoredReview:
    review = make_review(external_id, text, hours_ago, label=label)
    review.url = f"https://example.com/{external_id}"
    review.author = "alice"
    return ScoredReview(review, Prediction(review.id, "m", score))


@pytest.fixture
def sample_rows() -> list[ScoredReview]:
    return [
        scored("r1", "Great game, love the art.", 1, 0.9, P),
        scored("r2", "Terrible crashes after the patch update.", 2, 0.1, N),
        ScoredReview(make_review("r3", "No prediction yet.", 3, label=P), None),
    ]


def test_reviews_to_csv(sample_rows):
    csv_text = reviews_to_csv(sample_rows)
    assert csv_text.startswith("\ufeffid,target_id,created_at")
    assert "Great game" in csv_text and "0.900000" in csv_text
    assert "negative" in csv_text and "alice" in csv_text
    header = csv_text.splitlines()[0]
    assert reviews_to_csv([]) == header + "\n"


def test_render_report_html(sample_rows):
    target = Target("test", "t1", "Gra pierwsza")
    html = render_report(sample_rows, target, SentimentAnalytics(), now=utcnow(),
                         model_label="VADER")
    assert html.startswith("<!DOCTYPE html>")
    assert "Gra pierwsza" in html and "VADER" in html
    assert "KPI" in html and "Trend dzienny" in html
    assert "Słowa kluczowe" in html and "Alerty" in html
    assert "test:t1" in html
    # teksty opinii nie trafiają do HTML (tylko termy/KPI); nazwa obiektu jest escapowana
    evil_target = Target("test", "t1", '<img src=x onerror="alert(1)">')
    safe = render_report(sample_rows, evil_target, SentimentAnalytics(), now=utcnow())
    assert "<img" not in safe
    assert "&lt;img" in safe


def test_render_report_all_targets(sample_rows):
    html = render_report(sample_rows, None, SentimentAnalytics(), now=utcnow())
    assert "Wszystkie obiekty" in html


# --------------------------------------------------------------------------- GUI
@pytest.fixture(autouse=True)
def fresh_services(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    get_services.clear()
    yield
    get_services.clear()


def test_download_buttons_on_dashboard_and_reviews():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.switch_page(nav.PAGE_DASHBOARD).run()
    assert not at.exception, at.exception
    assert at.download_button(key="dash_csv").label == "CSV opinii (wybrany okres)"
    assert at.download_button(key="dash_report").label == "Raport HTML"

    at.switch_page(nav.PAGE_REVIEWS).run()
    assert not at.exception, at.exception
    assert at.download_button(key="rev_csv").label == "CSV (przefiltrowane)"
