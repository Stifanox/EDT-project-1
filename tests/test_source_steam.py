"""Testy `SteamReviewSource` i `HttpClient` (D1). Domyślnie offline; `-m network` = na żywo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import requests

from opimon import config
from opimon.errors import SourceError
from opimon.models import Sentiment, Target
from opimon.sources import HttpClient, SteamReviewSource
from tests.fixtures.steam.fake import FakeSteamHttp, load

DOTA = Target("steam", "570", "Dota 2")
T0 = datetime.fromtimestamp(1793000000, UTC)


@pytest.fixture
def http() -> FakeSteamHttp:
    return FakeSteamHttp()


@pytest.fixture
def steam(http) -> SteamReviewSource:
    return SteamReviewSource(http=http)


# ------------------------------------------------------------------ wyszukiwanie
def test_find_targets(steam, http):
    targets = steam.find_targets("Dota", limit=3)
    assert [t.key for t in targets] == ["570", "1046930", "652720"]
    assert targets[0] == Target("steam", "570", "Dota 2", "https://store.steampowered.com/app/570/")
    assert http.calls[0][1] == {"term": "Dota", "l": "english", "cc": "US"}


def test_find_targets_empty_query_makes_no_request(steam, http):
    assert steam.find_targets("  ") == []
    assert steam.find_targets("zzz-no-such-game") == []
    assert len(http.calls) == 1


def test_find_targets_bad_response():
    class Broken:
        def get_json(self, url, params=None):
            return {"unexpected": True}

    with pytest.raises(SourceError, match="wyszukiwarki"):
        SteamReviewSource(http=Broken()).find_targets("dota")


def test_target_from_appid(steam):
    assert steam.target_from_appid(" 570 ").name == "Dota 2"
    with pytest.raises(SourceError, match="nie zna gry"):
        steam.target_from_appid("999999999")


# ------------------------------------------------------------------ recenzje
def test_mapping_of_first_review(steam):
    r = steam.fetch(DOTA, limit=1)[0]
    assert r.id == "steam:210000001" and r.target_id == "steam:570"
    assert r.text == ("Best MOBA ever Still playing after 10 years. "
                      "The new hero is great & balanced.")
    assert r.created_at == T0 and r.label is Sentiment.POSITIVE and r.language == "en"
    assert r.author == "76561198000000001"
    assert r.url == "https://steamcommunity.com/profiles/76561198000000001/recommended/570/"
    assert r.extra["playtime_hours"] == 1500.0 and r.extra["votes_up"] == 1
    assert r.extra["steam_purchase"] is True


def test_negative_label_and_cleaning(steam):
    reviews = {r.external_id: r for r in steam.fetch(DOTA, limit=50)}
    assert reviews["210000002"].label is Sentiment.NEGATIVE
    assert reviews["210000002"].text == (
        "Matchmaking is broken again.\nLost 8 games in a row because of leavers.")
    assert "https://" not in reviews["210000004"].text
    assert "[spoiler]" not in reviews["210000003"].text


def test_pagination_dedup_and_empty_reviews(steam, http):
    reviews = steam.fetch(DOTA, limit=50)
    ids = [r.external_id for r in reviews]
    assert len(ids) == len(set(ids)) == 9                  # 10 pozycji: 1 duplikat, 1 pusta
    assert "210000006" not in ids
    calls = http.review_calls()
    assert [c["cursor"] for c in calls] == ["*", "AoJ4tey90tECdcOtxwI=", "AoJ43+Lr0NECeKmv8QI="]
    assert all(c["appid"] == 570 and c["filter"] == 1 and c["languages"] == ["english"]
               and c["purchase_type"] == 1 and c["filter_offtopic_activity"] is False
               for c in calls)
    times = [r.created_at for r in reviews]
    assert times == sorted(times, reverse=True)


def test_limit_stops_paging(steam, http):
    assert len(steam.fetch(DOTA, limit=3)) == 3
    assert len(http.review_calls()) == 1 and http.review_calls()[0]["num_per_page"] == 3
    assert len(steam.fetch(DOTA, limit=7)) == 7
    assert steam.fetch(DOTA, limit=0) == []


def test_since_stops_paging_early(steam, http):
    since = T0 - timedelta(hours=2)                        # 3 najnowsze recenzje są nowsze
    reviews = steam.fetch(DOTA, limit=50, since=since)
    assert [r.external_id for r in reviews] == ["210000001", "210000002"]
    assert len(http.review_calls()) == 1


def test_unknown_and_invalid_targets(steam):
    with pytest.raises(SourceError, match="nie zna gry"):
        steam.fetch(Target("steam", "999999999", "?"))
    with pytest.raises(SourceError, match="nieprawidłowy identyfikator"):
        steam.fetch(Target("steam", "dota", "?"))
    with pytest.raises(SourceError, match="nie pochodzi ze Steam"):
        steam.fetch(Target("sample", "570", "?"))


def test_existing_game_without_reviews_returns_empty(steam):
    assert steam.fetch(Target("steam", "440", "App 440")) == []


@pytest.mark.parametrize("response", [
    {"success": 1, "reviews": []},                         # stary format /appreviews
    {"response": "nope"},
    {"response": {"reviews": "nope"}},
    {"response": {"reviews": [{"id": 1, "text": "x"}], "cursor": "a"}},
    ["not", "a", "dict"],
])
def test_bad_review_responses_raise(response):
    class Http:
        def get_json(self, url, params=None):
            return response

    with pytest.raises(SourceError):
        SteamReviewSource(http=Http()).fetch(DOTA)


def test_repeated_cursor_does_not_loop():
    page = load("reviews_570_page1.json")

    class Loop:
        calls = 0

        def get_json(self, url, params=None):
            Loop.calls += 1
            return page                                    # zawsze ten sam kursor

    assert len(SteamReviewSource(http=Loop()).fetch(DOTA, limit=100)) == 5
    assert Loop.calls == 2


def test_recorded_live_pages():
    """Prawdziwe odpowiedzi GetAppReviews (nagrane 2026-11-04) parsują się poprawnie."""
    pages = [load("live_570_page1.json"), load("live_570_page2.json")]

    class Recorded(FakeSteamHttp):
        def get_json(self, url, params=None):
            if "GetAppReviews" in url:
                self.calls.append((url, dict(params)))
                n = len(self.review_calls()) - 1
                return pages[n] if n < 2 else {"response": {"reviews": [], "cursor": "x"}}
            return super().get_json(url, params)

    http = Recorded()
    reviews = SteamReviewSource(http=http).fetch(DOTA, limit=10)
    assert len(reviews) == 10 and len({r.id for r in reviews}) == 10
    assert http.review_calls()[1]["cursor"] == pages[0]["response"]["cursor"]
    assert all(r.label in (Sentiment.POSITIVE, Sentiment.NEGATIVE) and r.text for r in reviews)
    assert all(isinstance(r.extra["weighted_vote_score"], float) for r in reviews)
    assert all(r.extra["playtime_hours"] is not None for r in reviews)
    assert reviews[0].id == "steam:239367903" and reviews[0].text == "nice game"


# ------------------------------------------------------------------ HttpClient
class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, bad_json=False):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_http_client_sends_headers_and_no_redirects():
    session = FakeSession(FakeResponse(payload={"ok": 1}))
    assert HttpClient("Steam", session=session, delay_s=0).get_json("u", {"a": 1}) == {"ok": 1}
    assert session.kwargs["headers"]["User-Agent"] == config.HTTP_USER_AGENT
    assert session.kwargs["timeout"] == config.HTTP_TIMEOUT_S
    assert session.kwargs["allow_redirects"] is False and session.kwargs["params"] == {"a": 1}


@pytest.mark.parametrize("result, fragment", [
    (FakeResponse(429), "limit zapytań"),
    (FakeResponse(302, headers={"Location": "https://store.steampowered.com/"}), "przekierował"),
    (FakeResponse(503), "HTTP 503"),
    (FakeResponse(200, bad_json=True), "JSON"),
    (requests.Timeout(), "czas oczekiwania"),
    (requests.ConnectionError(), "brak połączenia"),
    (requests.TooManyRedirects(), "błąd zapytania"),
])
def test_http_client_errors_are_source_errors(result, fragment):
    with pytest.raises(SourceError, match=fragment):
        HttpClient("Steam", session=FakeSession(result), delay_s=0).get_json("u")


def test_http_client_respects_delay():
    now = [100.0]
    slept: list[float] = []
    client = HttpClient("Steam", session=FakeSession(FakeResponse(payload={})), delay_s=1.0,
                        sleep=slept.append, clock=lambda: now[0])
    client.get_json("u")
    now[0] += 0.25
    client.get_json("u")
    assert slept == [pytest.approx(0.75)]


def test_http_client_reads_delay_from_config(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_DELAY_S", 2.0)
    slept: list[float] = []
    client = HttpClient("Steam", session=FakeSession(FakeResponse(payload={})),
                        sleep=slept.append, clock=lambda: 0.0)
    client.get_json("u")
    client.get_json("u")
    assert slept == [2.0]


# ------------------------------------------------------------------ na żywo
@pytest.mark.network
def test_live_steam():
    steam = SteamReviewSource()
    target = steam.find_targets("Dota 2", limit=5)[0]
    assert target.key == "570"
    reviews = steam.fetch(target, limit=30)
    assert 0 < len(reviews) <= 30
    assert all(r.label is not None and r.text for r in reviews)
    newer = steam.fetch(target, limit=30, since=reviews[len(reviews) // 2].created_at)
    assert all(r.created_at > reviews[len(reviews) // 2].created_at for r in newer)
