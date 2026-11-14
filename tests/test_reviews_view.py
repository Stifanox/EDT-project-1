"""A3: widok „Opinie” – filtry, zaznaczenie, szczegóły, paginacja i przejścia z innych widoków."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon.models import Review, utcnow
from opimon.ui import nav
from opimon.ui.state import get_services

ROOT = Path(__file__).resolve().parents[1]
SELECT_FIRST = {"selection": {"rows": [0], "columns": [], "cells": []}}


@pytest.fixture(autouse=True)
def fresh_services(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    get_services.clear()
    yield
    get_services.clear()


def open_reviews(preset: dict | None = None) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    if preset is not None:
        at.session_state["nav_review_filters"] = preset
    at.switch_page(nav.PAGE_REVIEWS).run()
    assert not at.exception, at.exception
    return at


def count(at: AppTest) -> int:
    return int(next(c.value for c in at.caption if c.value.endswith(" opinii")).split()[0])


def table_len(at: AppTest) -> int:
    return len(at.dataframe(key="rev_table").value)


def details_text(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_default_view_paginates_sample_data():
    at = open_reviews()
    assert count(at) == 195
    assert table_len(at) == 50
    assert any(c.value.startswith("Strona 1 z 4") for c in at.caption)
    at.number_input(key="rev_page").set_value(4).run()
    assert table_len(at) == 195 - 150
    at.selectbox(key="rev_page_size").set_value(200).run()
    assert table_len(at) == 195


def test_selecting_row_shows_details_and_all_models():
    at = open_reviews()
    first_id = at.dataframe(key="rev_table").value["id"].iloc[0]
    at.session_state["rev_table"] = SELECT_FIRST
    at.run()
    assert not at.exception, at.exception
    assert any(s.value == "Szczegóły opinii" for s in at.subheader)
    assert first_id in details_text(at)
    # tabela bez `on_select` nie ma klucza w AppTest
    predictions = next(d for d in at.dataframe if d.key != "rev_table").value
    assert len(predictions) == len(get_services().models)
    assert predictions["P(pozytywny)"].notna().any()


def test_term_filter_highlights_phrase():
    at = open_reviews()
    at.text_input(key="rev_term").input("patch").run()
    assert 0 < count(at) < 195
    at.session_state["rev_table"] = SELECT_FIRST
    at.run()
    assert "<mark" in details_text(at)


def test_model_explanation_words_are_highlighted(monkeypatch):
    from opimon.services import AppServices

    monkeypatch.setattr(AppServices, "explain_text",
                        lambda self, text, model_name, n=10: [(text.split()[0], -1.0)])
    at = open_reviews()
    at.session_state["rev_table"] = SELECT_FIRST
    at.run()
    assert "background:#f9d0cd" in details_text(at)
    at.checkbox(key="rev_explain").uncheck().run()
    assert "background:#f9d0cd" not in details_text(at)


def test_misclassified_and_score_filters():
    at = open_reviews()
    at.checkbox(key="rev_wrong").check().run()
    wrong = count(at)
    assert 0 < wrong < 195
    at.slider(key="rev_score").set_value((0.4, 0.6)).run()
    assert not at.exception, at.exception
    assert count(at) <= wrong


def test_date_filter_and_reset():
    at = open_reviews()
    at.date_input(key="rev_date_from").set_value(date.today() + timedelta(days=2)).run()
    assert count(at) == 0
    at.button(key="rev_reset").click().run()
    assert not at.exception, at.exception
    assert count(at) == 195


def test_open_reviews_with_review_id_shows_that_review():
    review = get_services().repository.list_reviews()[100]
    at = open_reviews({"target_id": review.target_id, "sentiment": None, "term": None,
                       "review_id": review.id})
    assert at.session_state["rev_target"] == review.target_id
    assert review.id in details_text(at)
    assert any(s.value == "Szczegóły opinii" for s in at.subheader)


def test_review_id_outside_filters_is_still_shown():
    review = get_services().repository.list_reviews()[0]
    at = open_reviews({"target_id": None, "sentiment": None, "term": "zzz-no-match",
                       "review_id": review.id})
    assert count(at) == 0
    assert review.id in details_text(at)
    assert any("nie spełnia bieżących filtrów" in c.value for c in at.caption)


def test_large_repository_is_paginated():
    services = get_services()
    services.repository.add_reviews(
        Review("bulk", str(i), "bulk:game", f"Opinion number {i} is fine",
               utcnow() - timedelta(minutes=i))
        for i in range(1100)
    )
    at = open_reviews()
    assert count(at) == 195 + 1100
    assert table_len(at) == 50
