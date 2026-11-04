"""Źródło: recenzje gier ze Steam (publiczne API, bez klucza) – etap D1.

Endpointy:
* wyszukiwanie gier:  `GET /api/storesearch/?term=<q>&l=english&cc=US`
* recenzje:           `GET https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/
                       ?input_json={"appid":…,"filter":1,"languages":["english"],…}`
  Oficjalny następca `store.steampowered.com/appreviews/<appid>?json=1`, który Valve wyłączył
  22.10.2026 (stary adres przekierowuje na stronę główną sklepu). Dokumentacja:
  https://partner.steamgames.com/doc/webapi/IUserReviewsService (klucz niepotrzebny; bez klucza
  niższy limit -> HTTP 429, odpowiedzi mogą być cache'owane do 10 min).
  Enumy: `filter` 1 = Recent (od najnowszych po dacie utworzenia), `purchase_type` 1 = All.
  Odpowiedź w `{"response": {...}}`, bez pola `success` (o błędzie mówi status HTTP).
  Kolejna strona przez `cursor` (pierwsza: `*`; koniec: pusta lista albo powtórzony kursor).
  Nieznany appid -> `{"response": {}}`.
* istnienie gry:      `GET store.steampowered.com/api/appdetails?appids=<appid>&filters=basic`
  (tylko gdy pierwsza strona nie ma recenzji: odróżnia „nieznany appid” od „brak recenzji”).

Mapowanie: `recommendationid` -> `external_id`, `voted_up` -> `label`,
`timestamp_created` -> `created_at` (UTC), czas gry i głosy -> `extra`.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from opimon.errors import SourceError
from opimon.models import Review, Sentiment, Target
from opimon.sources.http import HttpClient, JsonGetter
from opimon.textproc import clean_text

logger = logging.getLogger(__name__)

STORE = "https://store.steampowered.com"
SEARCH_URL = f"{STORE}/api/storesearch/"
REVIEWS_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
FILTER_RECENT = 1          # EUserReviewsAppReviewsFilter
PURCHASE_ALL = 1           # EUserReviewsPurchaseType
DETAILS_URL = f"{STORE}/api/appdetails"
MAX_PER_PAGE = 100
MAX_PAGES = 200            # bezpiecznik na wypadek zapętlenia kursora


def store_url(appid: str) -> str:
    return f"{STORE}/app/{appid}/"


class SteamReviewSource:
    name = "steam"
    label = "Steam – recenzje gier (API)"

    def __init__(self, http: JsonGetter | None = None, language: str = "english") -> None:
        self._http = http or HttpClient("Steam")
        self._language = language

    # ------------------------------------------------------------- wyszukiwanie
    def find_targets(self, query: str, limit: int = 10) -> list[Target]:
        q = query.strip()
        if not q or limit <= 0:
            return []
        data = self._http.get_json(SEARCH_URL, {"term": q, "l": "english", "cc": "US"})
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise SourceError("Steam: nie rozpoznano odpowiedzi wyszukiwarki gier.")
        targets = []
        for item in items:
            if not isinstance(item, dict) or item.get("type", "app") != "app":
                continue
            appid, name = item.get("id"), item.get("name")
            if appid is None or not name:
                continue
            targets.append(Target(self.name, str(appid), str(name), store_url(str(appid))))
        return targets[:limit]

    def target_from_appid(self, appid: str | int) -> Target:
        """Cel po samym appid (ręczne dodanie w D4). Nieznany appid -> `SourceError`."""
        key = self._validate_appid(str(appid).strip())
        return Target(self.name, key, self._app_name(key), store_url(key))

    # ------------------------------------------------------------- recenzje
    def fetch(
        self, target: Target, limit: int = 100, since: datetime | None = None
    ) -> list[Review]:
        if target.source != self.name:
            raise SourceError(f"Steam: cel {target.id} nie pochodzi ze Steam.")
        appid = self._validate_appid(target.key)
        if limit <= 0:
            return []

        reviews: list[Review] = []
        seen_ids: set[str] = set()
        cursor = "*"
        used_cursors: set[str] = set()
        for page in range(MAX_PAGES):
            query = {
                "appid": int(appid),
                "filter": FILTER_RECENT,
                "languages": [self._language],
                "purchase_type": PURCHASE_ALL,
                "num_per_page": min(MAX_PER_PAGE, limit - len(reviews)),
                "cursor": cursor,
                # recenzje „off-topic” (review bomb) są sygnałem, który chcemy monitorować
                "filter_offtopic_activity": False,
            }
            data = self._http.get_json(REVIEWS_URL, {"input_json": json.dumps(query)})
            response = data.get("response") if isinstance(data, dict) else None
            if not isinstance(response, dict):
                raise SourceError("Steam: nie rozpoznano struktury odpowiedzi z recenzjami.")
            raw = response.get("reviews", [])
            if not isinstance(raw, list):
                raise SourceError("Steam: nie rozpoznano struktury odpowiedzi z recenzjami.")
            if page == 0 and not raw:
                self._app_name(appid)      # nieznany appid -> SourceError, inaczej brak recenzji

            reached_older, parsed = False, 0
            for item in raw:
                review = self._to_review(item, target, appid)
                if review is None:
                    continue
                parsed += 1
                if review.id in seen_ids:
                    continue
                if since is not None and review.created_at <= since:
                    reached_older = True       # filter=recent: dalej są już tylko starsze
                    continue
                seen_ids.add(review.id)
                reviews.append(review)
                if len(reviews) >= limit:
                    break
            if raw and parsed == 0 and all(not _looks_like_review(i) for i in raw):
                raise SourceError("Steam: nie rozpoznano struktury recenzji (zmiana API?).")

            next_cursor = response.get("cursor")
            used_cursors.add(cursor)
            if (len(reviews) >= limit or reached_older or not raw or not next_cursor
                    or next_cursor in used_cursors):
                break
            cursor = next_cursor

        reviews.sort(key=lambda r: (r.created_at, r.id), reverse=True)
        return reviews[:limit]

    # ------------------------------------------------------------- pomocnicze
    def _validate_appid(self, key: str) -> str:
        if not key.isdigit():
            raise SourceError(f"Steam: nieprawidłowy identyfikator gry (appid): „{key}”.")
        return key

    def _app_name(self, appid: str) -> str:
        data = self._http.get_json(DETAILS_URL, {"appids": appid, "filters": "basic"})
        entry = data.get(appid) if isinstance(data, dict) else None
        if not isinstance(entry, dict) or not entry.get("success"):
            raise SourceError(f"Steam nie zna gry o appid {appid}.")
        return str((entry.get("data") or {}).get("name") or appid)

    def _to_review(self, item: Any, target: Target, appid: str) -> Review | None:
        """Pozycja z API -> `Review`; None dla pustej lub uszkodzonej pozycji."""
        if not _looks_like_review(item):
            logger.warning("Steam: pominięto pozycję bez wymaganych pól: %r", item)
            return None
        text = clean_text(str(item["review"]))
        if not text:
            return None
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        steamid = author.get("steamid")
        return Review(
            source=self.name,
            external_id=str(item["recommendationid"]),
            target_id=target.id,
            text=text,
            created_at=datetime.fromtimestamp(int(item["timestamp_created"]), UTC),
            author=str(steamid) if steamid else None,
            label=Sentiment.POSITIVE if item["voted_up"] else Sentiment.NEGATIVE,
            url=(f"https://steamcommunity.com/profiles/{steamid}/recommended/{appid}/"
                 if steamid else store_url(appid)),
            language="en",
            extra={
                "playtime_hours": _hours(author.get("playtime_forever")),
                "playtime_at_review_hours": _hours(author.get("playtime_at_review")),
                "votes_up": int(item.get("votes_up") or 0),
                "votes_funny": int(item.get("votes_funny") or 0),
                "weighted_vote_score": float(item.get("weighted_vote_score") or 0.0),
                "steam_purchase": bool(item.get("steam_purchase")),
                "received_for_free": bool(item.get("received_for_free")),
                "early_access": bool(item.get("written_during_early_access")),
                "refunded": bool(item.get("refunded")),
            },
        )


def _looks_like_review(item: Any) -> bool:
    return isinstance(item, dict) and all(
        k in item for k in ("recommendationid", "review", "timestamp_created", "voted_up")
    )


def _hours(minutes: Any) -> float | None:
    try:
        return round(int(minutes) / 60, 1)
    except (TypeError, ValueError):
        return None
