"""Testy widoku „Źródła danych” (D4): logika bez GUI + przepływy w `AppTest` (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon import services as services_mod
from opimon.errors import SourceError
from opimon.models import FetchReport
from opimon.services import build_services
from opimon.sources import MetacriticReviewSource, SampleSource, SteamReviewSource
from opimon.ui import nav
from opimon.ui import sources_view as view
from opimon.ui.state import get_services
from tests.fixtures.metacritic.fake import FakeMetacriticHttp
from tests.fixtures.steam.fake import FakeSteamHttp

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ logika bez GUI
@pytest.mark.parametrize("text, key", [
    ("570", "570"),
    (" https://store.steampowered.com/app/570/Dota_2/ ", "570"),
    ("dota", "570"),                                    # fallback: wyszukiwarka
])
def test_resolve_manual_steam(text, key):
    target = view.resolve_manual_target(SteamReviewSource(http=FakeSteamHttp()), text)
    assert target.key == key and target.name == "Dota 2"


def test_resolve_manual_metacritic():
    mc = MetacriticReviewSource(http=FakeMetacriticHttp())
    url = "https://www.metacritic.com/game/elden-ring/user-reviews/"
    assert view.resolve_manual_target(mc, url).key == "game/elden-ring"


@pytest.mark.parametrize("text, fragment", [("", "Podaj"), ("999999999", "nie zna gry"),
                                            ("zzz-nothing", "nie znaleziono")])
def test_resolve_manual_errors(text, fragment):
    with pytest.raises(SourceError, match=fragment):
        view.resolve_manual_target(SteamReviewSource(http=FakeSteamHttp()), text)


def test_fetch_summary_kinds():
    ok = FetchReport("x", fetched=5, new=3, analyzed=3, seconds=1.0)
    assert view.fetch_summary(ok, "Gra") == (
        "success", "Gra: pobrano 5, nowych 3, duplikatów 2, przeanalizowano 3 (1.0 s).")
    assert view.fetch_summary(FetchReport("x"), "Gra")[0] == "info"
    assert view.fetch_summary(FetchReport("x", errors=["błąd"]), "Gra")[0] == "warning"
    assert view.refresh_summary([ok, FetchReport("y", errors=["e"])])[0] == "warning"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    return build_services()


def test_watchlist_frame_numbers(app):
    df = view.watchlist_frame(app)
    assert list(df.columns) == view.WATCHLIST_COLUMNS
    assert list(df["Obiekt"]) == ["Iron Harbor Tactics", "Pixel Bakery Tycoon", "Starfall Odyssey"]
    assert df["Opinie"].dtype.kind == "i" and int(df["Opinie"].sum()) == 195
    assert df["Najnowsza opinia"].notna().all()
    assert view.watchlist_frame(app, "steam").empty


def test_latest_reviews_filters(app):
    assert len(view.latest_reviews(app, limit=10)) == 10
    assert view.latest_reviews(app, "steam") == []
    rows = view.latest_reviews(app, "sample", "sample:pixelbakery", limit=100)
    assert len(rows) == 45 and {r.review.target_id for r in rows} == {"sample:pixelbakery"}
    frame = view.reviews_frame(app, rows)
    assert list(frame.columns) == view.REVIEW_COLUMNS
    assert frame["P(pozytywny)"].dtype.kind == "f"


def test_remove_target_service(app):
    assert app.remove_target("sample:starfall") == 90
    assert app.repository.get_target("sample:starfall") is None
    assert app.repository.count_reviews() == 105
    assert app.remove_target("sample:unknown") == 0


def test_fetch_progress_is_monotonic(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", False)
    app = build_services()
    seen: list[tuple[float, str]] = []
    target = SampleSource().find_targets("starfall")[0]
    report = app.fetch_reviews("sample", target, 1000, progress=lambda f, m: seen.append((f, m)))
    fractions = [f for f, _ in seen]
    assert report.new == 90 and fractions == sorted(fractions)
    assert fractions[0] == 0.0 and fractions[-1] == 1.0 and seen[-1][1] == "Gotowe."
    assert any(m.startswith("Analiza sentymentu") for _, m in seen)


def test_refresh_all_progress(app):
    seen: list[float] = []
    reports = app.refresh_all(progress=lambda f, m: seen.append(f))
    assert len(reports) == 3 and seen == sorted(seen) and seen[-1] == pytest.approx(1.0)


# ------------------------------------------------------------------ GUI (AppTest)
@pytest.fixture
def offline_sources(monkeypatch):
    """Źródła sieciowe na nagranych odpowiedziach – testy GUI nie korzystają z Internetu."""
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    monkeypatch.setattr(services_mod, "_make_sources", lambda: {
        "steam": SteamReviewSource(http=FakeSteamHttp()),
        "metacritic": MetacriticReviewSource(http=FakeMetacriticHttp()),
        "sample": SampleSource(),
    })
    get_services.clear()
    yield
    get_services.clear()


def _open() -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.switch_page(nav.PAGE_SOURCES).run()
    assert not at.exception, at.exception
    return at


def _messages(at: AppTest) -> list[str]:
    return [m.value for m in [*at.success, *at.info, *at.warning, *at.error]]


def test_search_and_fetch_steam(offline_sources):
    at = _open()
    at.text_input(key="src_query").input("dota").run()
    assert at.selectbox(key="src_target").value.name == "Dota 2"
    at.button(key="src_fetch").click().run()
    assert not at.exception, at.exception
    assert any(m.startswith("Dota 2: pobrano 9, nowych 9") for m in _messages(at))
    assert any(r == "Dota 2" for r in view.watchlist_frame(get_services())["Obiekt"])


def test_search_error_is_shown(offline_sources, monkeypatch):
    at = _open()
    steam = get_services().sources["steam"]

    def broken(query, limit=10):
        raise SourceError("Steam: brak połączenia z serwisem.")

    monkeypatch.setattr(steam, "find_targets", broken)
    at.text_input(key="src_query").input("dota").run()
    assert not at.exception, at.exception
    assert any("brak połączenia" in e.value for e in at.error)


def test_manual_add_by_url(offline_sources):
    at = _open()
    at.selectbox(key="src_source").set_value("metacritic").run()
    at.text_input(key="src_manual").input("https://www.metacritic.com/game/elden-ring/").run()
    at.button(key="src_manual_add").click().run()
    assert not at.exception, at.exception
    assert any(m.startswith("Elden Ring (2022) – gra: pobrano 50") for m in _messages(at))


def test_manual_add_unknown_shows_error(offline_sources):
    at = _open()
    at.text_input(key="src_manual").input("999999999").run()
    at.button(key="src_manual_add").click().run()
    assert any("nie zna gry" in e.value for e in at.error)


def test_remove_with_confirmation_and_cancel(offline_sources):
    at = _open()
    at.button(key="src_remove_sample:starfall").click().run()
    assert at.session_state[view_remove_key()] == "sample:starfall"
    at.button(key="src_remove_cancel").click().run()
    assert view_remove_key() not in at.session_state
    assert get_services().repository.get_target("sample:starfall") is not None

    at.button(key="src_remove_sample:starfall").click().run()
    at.button(key="src_remove_confirm").click().run()
    assert not at.exception, at.exception
    assert get_services().repository.get_target("sample:starfall") is None
    assert any("Usunięto „Starfall Odyssey” i 90 opinii" in m for m in _messages(at))


def view_remove_key() -> str:
    return "src_confirm_remove"


def test_refresh_single_and_all(offline_sources):
    at = _open()
    at.button(key="src_refresh_sample:pixelbakery").click().run()
    assert any("Pixel Bakery Tycoon: brak nowych opinii" in m for m in _messages(at))
    at.button(key="src_refresh_all").click().run()
    assert not at.exception, at.exception
    assert any(m.startswith("Odświeżono 3 obiektów") for m in _messages(at))


def test_dashboard_button_navigates(offline_sources):
    at = _open()
    at.button(key="src_dash_sample:ironharbor").click().run()
    assert not at.exception, at.exception
    assert at.session_state["dash_target"] == "sample:ironharbor"


def test_reviews_filters(offline_sources):
    at = _open()
    at.selectbox(key="src_filter_source").set_value("sample").run()
    at.selectbox(key="src_filter_target").set_value("sample:starfall").run()
    assert not at.exception, at.exception
    # AppTest nie wyszukuje st.dataframe po kluczu – szukamy tabeli opinii po jej kolumnach
    df = next(d.value for d in at.dataframe if "Treść" in d.value.columns)
    assert len(df) == 50 and set(df["Obiekt"]) == {"Starfall Odyssey"}
    assert "Link" in df.columns
