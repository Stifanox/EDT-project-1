"""Testy GUI (P0): każda strona renderuje się bez wyjątku + nawigacja między widokami.

Wzór dla testów GUI w etapach:
* start od `app.py` + `at.switch_page(...)` (inaczej `st.switch_page` nie znajdzie stron);
* `get_services.clear()` przed testem (świeże `AppServices` na danych testowych);
* elementy wybieraj PO KLUCZU (`at.button(key="…")`), nie po indeksie.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon.ui import nav
from opimon.ui.state import get_services

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pages").glob("*.py"))


@pytest.fixture(autouse=True)
def _fresh_services(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    get_services.clear()
    yield
    get_services.clear()


def _open(page: str | None = None) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    if page:
        at.switch_page(page).run()
        assert not at.exception, at.exception
    return at


def test_home_renders():
    at = _open()
    assert any(m.label == "Opinie w bazie" and m.value == "195" for m in at.metric)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    _open(page)


def test_fetch_flow_on_sources_page():
    at = _open(nav.PAGE_SOURCES)
    at.selectbox(key="src_source").set_value("sample").run()   # offline – bez sieci
    at.text_input(key="src_query").input("pixel").run()
    at.button(key="src_fetch").click().run()
    assert not at.exception, at.exception
    assert any("Pixel Bakery Tycoon" in s.value for s in at.success)


def test_train_flow_on_models_page():
    at = _open(nav.PAGE_MODELS)
    at.button(key="mdl_train").click().run()
    assert not at.exception, at.exception
    assert any("Wytrenowano" in s.value for s in at.success)
    at.text_area(key="mdl_try_text").input("Awful and boring").run()
    assert not at.exception, at.exception


def test_evaluation_page_runs():
    at = _open(nav.PAGE_EVALUATION)
    at.radio(key="ev_mode").set_value("live").run()
    at.button(key="ev_run").click().run()
    assert not at.exception, at.exception
    assert at.session_state["ev_results"]


def test_dashboard_to_reviews_navigation():
    at = _open(nav.PAGE_DASHBOARD)
    at.button(key="dash_open_negative").click().run()
    assert not at.exception, at.exception
    assert at.session_state["rev_sentiment"] == "negative"
    assert any(c.value.endswith("opinii") for c in at.caption)
