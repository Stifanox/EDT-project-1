"""Przepływy widoku M6 przez AppTest, wybór elementów po kluczu."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon.ui import nav
from opimon.ui.state import get_services

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh_services(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    get_services.clear()
    yield
    get_services.clear()


def open_models():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.switch_page(nav.PAGE_MODELS).run()
    assert not at.exception
    return at


def test_missing_imdb_shows_download_instruction():
    at = open_models()
    at.button(key="mdl_train").click().run()
    assert not at.exception
    assert any("download_imdb.py" in error.value for error in at.error)


def test_training_limit_explanation_examples_and_analysis():
    at = open_models()
    at.selectbox(key="mdl_dataset").select("sample_movies").run()
    at.number_input(key="mdl_train_limit").set_value(20).run()
    at.button(key="mdl_train").click().run()
    assert not at.exception
    assert any("20 przykładach" in item.value for item in at.success)
    at.button(key="mdl_example_negation").click().run()
    assert at.text_area(key="mdl_try_text").value.startswith("Not bad")
    assert len(at.metric) == 2
    assert any("Cecha" in item.value.columns for item in at.dataframe)
    at.selectbox(key="mdl_analyze_model").select("tfidf_lr").run()
    at.button(key="mdl_analyze").click().run()
    assert not at.exception
    assert any("0 nowych predykcji" in item.value for item in at.success)


def test_transformer_unavailable_is_a_message(monkeypatch):
    from opimon.models import ModelInfo
    from opimon.services import AppServices

    monkeypatch.setattr(AppServices, "load_model", lambda *args, **kwargs:
                        ModelInfo("distilbert", "DistilBERT", False, False, notes="Brak sieci."))
    at = open_models()
    at.button(key="mdl_load_transformer").click().run()
    assert not at.exception
    assert any("Brak sieci" in item.value for item in at.warning)
