"""Testy `MetacriticReviewSource` (D3). Domyślnie offline na nagranych stronach; `-m network`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from opimon.errors import SourceError
from opimon.models import Sentiment, Target
from opimon.sources import HttpClient, MetacriticReviewSource
from opimon.sources.metacritic import (
    guess_language,
    label_for,
    page_url,
    parse_user_reviews,
    slugify,
)
from opimon.textproc import clean_text
from tests.fixtures.metacritic.fake import FakeMetacriticHttp, load

DUNE = Target("metacritic", "movie/dune-part-two", "Dune: Part Two (2024) – film")


@pytest.fixture
def http() -> FakeMetacriticHttp:
    return FakeMetacriticHttp()


@pytest.fixture
def mc(http) -> MetacriticReviewSource:
    return MetacriticReviewSource(http=http)


# ------------------------------------------------------------------ funkcje pomocnicze
@pytest.mark.parametrize("title, slug", [
    ("Dune: Part Two", "dune-part-two"),
    ("Baldur's Gate 3", "baldurs-gate-3"),
    ("The Witcher 3: Wild Hunt", "the-witcher-3-wild-hunt"),
    ("Amélie", "amelie"),
    ("Ratchet & Clank", "ratchet-clank"),
    ("  !!  ", ""),
])
def test_slugify(title, slug):
    assert slugify(title) == slug


@pytest.mark.parametrize("score, label", [
    (10, Sentiment.POSITIVE), (7, Sentiment.POSITIVE), (6, None), (5, None),
    (4, Sentiment.NEGATIVE), (0, Sentiment.NEGATIVE), (None, None),
])
def test_label_like_imdb(score, label):
    assert label_for(score) is label


def test_guess_language():
    assert guess_language("This is one of the best movies I have ever seen.") == "en"
    assert guess_language("Uno de los mejores juegos de la historia, es una joya.") == "und"
    assert guess_language("Masterpiece!") == "en"                      # za krótki -> en


# ------------------------------------------------------------------ parser
def test_payload_parser_on_movie_page():
    page = parse_user_reviews(load("movie_dune-part-two.html"), "movie/dune-part-two")
    assert page.method == "payload" and (page.title, page.year) == ("Dune: Part Two", 2024)
    assert len(page.reviews) == 50 and len({r.id for r in page.reviews}) == 50
    first = page.reviews[0]
    assert first.id == "cb26b932-06ad-4bc7-b4ca-e3a846008803" and first.score == 2
    assert first.author == "Kaibox02" and first.text.startswith("This movie was so cringe.")
    assert first.created_at == datetime(2026, 10, 30, 11, 39, 17, 693000, tzinfo=UTC)
    spoilers = [r for r in page.reviews if r.spoiler]
    assert len(spoilers) == 5 and all(len(r.text) > 100 for r in spoilers)   # pełny tekst


def test_payload_parser_on_game_page():
    page = parse_user_reviews(load("game_elden-ring.html"), "game/elden-ring")
    assert (page.title, page.year, len(page.reviews)) == ("Elden Ring", 2022, 50)


def test_html_fallback_matches_payload():
    """Parser zapasowy (karty HTML) daje te same teksty i oceny co osadzony stan."""
    payload = parse_user_reviews(load("movie_dune-part-two.html"), "movie/dune-part-two")
    cards = parse_user_reviews(load("movie_dune-part-two_no_payload.html"),
                               "movie/dune-part-two")
    assert cards.method == "html" and cards.title == "Dune: Part Two"
    expected = [(clean_text(r.text), r.score, r.created_at.date())
                for r in payload.reviews if not r.spoiler]
    got = [(clean_text(r.text), r.score, r.created_at.date()) for r in cards.reviews]
    assert got == expected and len(got) == 45
    assert all(r.created_at.hour == 12 and r.id.startswith("h-") for r in cards.reviews)
    assert cards.reviews[0].author == "Kaibox02"


def test_unrecognized_page_raises():
    with pytest.raises(SourceError, match="nie rozpoznano struktury"):
        parse_user_reviews(load("unrecognized.html"))
    truncated = load("movie_dune-part-two.html")[:5000]                  # ucięty HTML
    with pytest.raises(SourceError, match="nie rozpoznano struktury"):
        parse_user_reviews(truncated)


# ------------------------------------------------------------------ wyszukiwanie
def test_find_by_title_checks_movie_and_game(mc, http):
    targets = mc.find_targets("Dune: Part Two")
    assert targets == [Target("metacritic", "movie/dune-part-two",
                              "Dune: Part Two (2024) – film", page_url("movie/dune-part-two"))]
    assert http.calls == [page_url("movie/dune-part-two"), page_url("game/dune-part-two")]
    assert [t.name for t in mc.find_targets("elden ring")] == ["Elden Ring (2022) – gra"]


@pytest.mark.parametrize("query", [
    "https://www.metacritic.com/game/elden-ring/user-reviews/",
    "https://www.metacritic.com/game/elden-ring/",
    "game/elden-ring",
])
def test_find_by_url_or_key(mc, http, query):
    assert [t.key for t in mc.find_targets(query)] == ["game/elden-ring"]
    assert len(http.calls) == 1


def test_find_nothing(mc, http):
    assert mc.find_targets("") == [] and mc.find_targets("   ") == []
    assert mc.find_targets("!!!") == [] and http.calls == []
    assert mc.find_targets("No Such Movie 0000") == []


def test_never_uses_disallowed_search(mc, http):
    """`/search` jest zakazane w robots.txt – źródło nie może go używać."""
    mc.find_targets("Dune: Part Two")
    mc.fetch(DUNE)
    assert all("/search" not in url and "/user/" not in url for url in http.calls)


# ------------------------------------------------------------------ recenzje
def test_fetch_mapping(mc):
    reviews = mc.fetch(DUNE, limit=100)
    assert len(reviews) == 50
    r = next(x for x in reviews if x.external_id == "cb26b932-06ad-4bc7-b4ca-e3a846008803")
    assert r.id == "metacritic:cb26b932-06ad-4bc7-b4ca-e3a846008803"
    assert r.target_id == "metacritic:movie/dune-part-two" and r.rating == 2.0
    assert r.label is Sentiment.NEGATIVE and r.author == "Kaibox02" and r.language == "en"
    assert r.url == "https://www.metacritic.com/movie/dune-part-two/user-reviews/"
    assert r.extra["parser"] == "payload" and r.extra["spoiler"] is False
    assert {x.label for x in reviews} == {Sentiment.POSITIVE, Sentiment.NEGATIVE, None}
    assert sum(x.language == "und" for x in reviews) == 8


def test_fetch_limit_and_since(mc):
    all_reviews = mc.fetch(DUNE, limit=100)
    assert [r.id for r in mc.fetch(DUNE, limit=5)] == [r.id for r in all_reviews[:5]]
    cut = all_reviews[9].created_at
    newer = mc.fetch(DUNE, since=cut)
    assert [r.id for r in newer] == [r.id for r in all_reviews[:9]]
    assert mc.fetch(DUNE, limit=0) == []


def test_find_then_fetch_uses_page_cache(mc, http):
    target = mc.find_targets("game/elden-ring")[0]
    mc.fetch(target)
    assert len(http.calls) == 1


def test_cache_expires():
    now = [0.0]
    http = FakeMetacriticHttp()
    mc = MetacriticReviewSource(http=http, clock=lambda: now[0])
    mc.fetch(DUNE)
    now[0] += 500
    mc.fetch(DUNE)
    assert len(http.calls) == 2


def test_fetch_errors(mc):
    with pytest.raises(SourceError, match="nie ma strony"):
        mc.fetch(Target("metacritic", "movie/no-such-movie", "?"))
    with pytest.raises(SourceError, match="nieprawidłowy identyfikator"):
        mc.fetch(Target("metacritic", "dune", "?"))
    with pytest.raises(SourceError, match="nie pochodzi z Metacritic"):
        mc.fetch(Target("steam", "movie/dune-part-two", "?"))


def test_structure_change_raises_source_error():
    http = FakeMetacriticHttp({"movie/dune-part-two": "unrecognized.html"})
    with pytest.raises(SourceError, match="nie rozpoznano struktury"):
        MetacriticReviewSource(http=http).fetch(DUNE)


def test_fallback_parser_through_source():
    http = FakeMetacriticHttp({"movie/dune-part-two": "movie_dune-part-two_no_payload.html"})
    reviews = MetacriticReviewSource(http=http).fetch(DUNE)
    assert len(reviews) == 45 and all(r.extra["parser"] == "html" for r in reviews)


# ------------------------------------------------------------------ HttpClient.get_text
class _Resp:
    def __init__(self, status, text="", encoding="utf-8"):
        self.status_code, self.text, self.encoding, self.headers = status, text, encoding, {}


class _Session:
    def __init__(self, resp):
        self.resp = resp

    def get(self, url, **kwargs):
        return self.resp


def test_get_text_missing_ok_and_errors():
    ok = HttpClient("Metacritic", session=_Session(_Resp(200, "<html>")), delay_s=0)
    assert ok.get_text("u") == "<html>"
    missing = HttpClient("Metacritic", session=_Session(_Resp(404)), delay_s=0)
    assert missing.get_text("u", missing_ok=True) is None
    with pytest.raises(SourceError, match="HTTP 404"):
        missing.get_text("u")
    forbidden = HttpClient("Metacritic", session=_Session(_Resp(403)), delay_s=0)
    with pytest.raises(SourceError, match="odmówił dostępu"):
        forbidden.get_text("u", missing_ok=True)


# ------------------------------------------------------------------ na żywo
@pytest.mark.network
def test_live_metacritic():
    mc = MetacriticReviewSource()
    targets = mc.find_targets("Elden Ring")
    assert [t.key for t in targets] == ["game/elden-ring"]
    reviews = mc.fetch(targets[0], limit=20)
    assert 0 < len(reviews) <= 20 and all(r.text for r in reviews)
    assert all(r.extra["parser"] == "payload" for r in reviews), "zmienił się osadzony stan"
    assert any(r.label is not None for r in reviews)
