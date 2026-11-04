"""Transport offline dla `SteamReviewSource` – odpowiada nagranymi fixture'ami.

* `search_dota.json`, `appdetails_*.json` – prawdziwe odpowiedzi API (nagrane 2026-11-04,
  usunięte tylko adresy obrazków / zbędne pola `appdetails`);
* `live_570_page{1,2}.json`, `reviews_unknown.json` – prawdziwe odpowiedzi `GetAppReviews`
  (nagrane 2026-11-04, Dota 2, 5 recenzji na stronę);
* `reviews_570_page{1,2,3}.json` – odpowiedzi `GetAppReviews` przygotowane ręcznie w formacie
  API, z przypadkami brzegowymi (BBCode, encje HTML, URL, pusta recenzja, duplikat między
  stronami, koniec paginacji powtórzonym kursorem).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from opimon.sources.steam import SteamReviewSource

DIR = Path(__file__).parent


def load(name: str) -> Any:
    return json.loads((DIR / name).read_text(encoding="utf-8"))


class FakeSteamHttp:
    def __init__(self, apps_without_reviews: frozenset[str] = frozenset({"440"})) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.pages = [load(f"reviews_570_page{i}.json") for i in (1, 2, 3)]
        self.apps_without_reviews = apps_without_reviews

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        params = dict(params or {})
        self.calls.append((url, params))
        if url.endswith("/api/storesearch/"):
            if "dota" in params["term"].lower():
                return load("search_dota.json")
            return {"total": 0, "items": []}
        if url.endswith("/api/appdetails"):
            appid = params["appids"]
            if appid == "570":
                return load("appdetails_570.json")
            if appid in self.apps_without_reviews:
                return {appid: {"success": True, "data": {"type": "game", "name": f"App {appid}"}}}
            return {appid: {"success": False}}
        if "GetAppReviews" in url:
            query = json.loads(params["input_json"])
            appid = str(query["appid"])
            if appid in self.apps_without_reviews:
                return {"response": {"query_summary": {"num_reviews": 0}, "cursor": "*"}}
            if appid != "570":
                return load("reviews_unknown.json")
            cursor = query["cursor"]
            index = 0 if cursor == "*" else 1 + [p["response"]["cursor"]
                                                  for p in self.pages].index(cursor)
            return copy.deepcopy(self.pages[min(index, 2)])
        raise AssertionError(f"nieoczekiwany URL: {url}")

    def review_calls(self) -> list[dict]:
        """Zdekodowane `input_json` kolejnych zapytań o recenzje."""
        return [json.loads(p["input_json"]) for u, p in self.calls if "GetAppReviews" in u]


def make_offline_steam_source() -> SteamReviewSource:
    return SteamReviewSource(http=FakeSteamHttp())
