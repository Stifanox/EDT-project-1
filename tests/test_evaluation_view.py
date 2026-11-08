"""M7: porównania, zapisane wyniki, wykresy i przejście do błędnej opinii."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon.services import AppServices
from opimon.ui import nav
from opimon.ui.evaluation_view import confusion_chart, metrics_chart
from opimon.ui.state import get_services

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh_services(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    get_services.clear()
    yield
    get_services.clear()


def open_evaluation():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.switch_page(nav.PAGE_EVALUATION).run()
    assert not at.exception
    return at


def test_test_and_demo_comparison_persists_without_recomputing(monkeypatch):
    at = open_evaluation()
    at.radio(key="ev_mode").set_value("compare").run()
    at.selectbox(key="ev_dataset").select("sample_movies").run()
    at.button(key="ev_run").click().run()
    assert not at.exception
    assert any("syntetyczne" in item.value for item in at.warning)
    results = at.session_state["ev_results"]
    assert {row["dataset_name"] for row in results} == {"sample_movies", "demo:sample"}
    assert len(at.get("plotly_chart")) == 2
    assert all(isinstance(row["accuracy"], float) for row in results)
    monkeypatch.setattr(AppServices, "compare_models", lambda *a, **kw:
                        pytest.fail("Odświeżenie przeliczyło modele"))
    at.selectbox(key="ev_confusion").set_value(1).run()
    assert not at.exception
    assert at.session_state["ev_results"] == results


def test_missing_dataset_message_and_empty_live_data(monkeypatch):
    at = open_evaluation()
    at.button(key="ev_run").click().run()
    assert not at.exception
    assert any("download_imdb.py" in item.value for item in at.warning)
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", False)
    get_services.clear()
    at = open_evaluation()
    at.radio(key="ev_mode").set_value("live").run()
    at.button(key="ev_run").click().run()
    assert not at.exception and not at.session_state["ev_results"]
    assert any("Brak opinii" in item.value for item in at.info)


def test_error_example_opens_reviews():
    at = open_evaluation()
    at.radio(key="ev_mode").set_value("live").run()
    at.button(key="ev_run").click().run()
    assert not at.exception
    review_id = at.selectbox(key="ev_example_review").value
    at.button(key="ev_open_review").click().run()
    assert not at.exception
    review = get_services().repository.get_review(review_id)
    assert at.session_state["rev_target"] == review.target_id
    assert at.text_input(key="rev_term").value == review.text


def test_confusion_axes_and_metric_values():
    import pandas as pd

    row = {"tn": 7, "fp": 2, "fn": 3, "tp": 11}
    matrix = confusion_chart(row)
    assert list(map(list, matrix.data[0].z)) == [[7, 2], [3, 11]]
    assert matrix.layout.xaxis.title.text == "Predykcja"
    table = pd.DataFrame([{"model_name": "vader", "dataset_name": "imdb",
                           "accuracy": 0.75, "f1": 0.8}])
    chart = metrics_chart(table)
    assert {float(trace.y[0]) for trace in chart.data} == {0.75, 0.8}
