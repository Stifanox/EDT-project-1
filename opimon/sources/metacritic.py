"""Źródło: recenzje użytkowników Metacritic (filmy i gry) przez web scraping – etap D3.

Zasady (sprawdzone 2026-11-04, szczegóły w docs/tasks/D3.md):
* `robots.txt` (`User-agent: *`) zakazuje m.in. `/search`, `/user`, `/login`, ale NIE stron
  `/<movie|game>/<slug>/user-reviews/`. Dlatego nie korzystamy z wyszukiwarki serwisu:
  cel wskazuje się tytułem (zamienianym na slug), adresem URL albo zapisem `movie/<slug>`.
* uczciwy User-Agent projektu, odstęp `config.REQUEST_DELAY_S`, jedna strona na pobranie
  (+ krótki cache stron, żeby `find_targets` i `fetch` nie pobierały tego samego dwa razy).

Strona `…/user-reviews/` jest renderowana po stronie serwera (Nuxt) i zawiera:
1. `<script id="__NUXT_DATA__">` – stan aplikacji w formacie *devalue* (spłaszczona tablica
   JSON z odwołaniami po indeksach). Są w nim obiekty recenzji (`id` UUID, `quote` – pełny tekst,
   także recenzji ze spoilerami, `score` 0–10, `date` RRRR-MM-DD, `version` – znacznik czasu w ms,
   `author`, `spoiler`, `thumbsUp`, `thumbsDown`) i produktu (`title`, `slug`, `premiereYear`).
   To podstawowe źródło danych.
2. Karty recenzji w HTML (`data-testid="review-card"`, `review-card-date`, `review-card-header`,
   `review-quote-text`) – parser zapasowy, gdyby osadzony stan zniknął. Karty nie mają
   identyfikatora (id = skrót autora, daty i treści), a recenzje ze spoilerami są w nich ukryte.
Brak obu -> `SourceError` „Nie rozpoznano struktury strony”.

Ograniczenie: strona pokazuje 50 najnowszych recenzji („Recently Added”), kolejne są
doładowywane JavaScriptem z prywatnego API. Nie odtwarzamy go, więc jedno pobranie daje
najwyżej `PAGE_SIZE` opinii; monitorowanie (D5) dociąga nowe przy kolejnych odświeżeniach.

Etykieta jak w zbiorze IMDB: ocena ≥ 7 -> pozytywna, ≤ 4 -> negatywna, 5–6 -> brak.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import time as dtime
from typing import Any

from bs4 import BeautifulSoup

from opimon.errors import SourceError
from opimon.models import Review, Sentiment, Target
from opimon.sources.http import HttpClient, TextGetter
from opimon.textproc import STOPWORDS_EN, clean_text, tokenize

logger = logging.getLogger(__name__)

BASE = "https://www.metacritic.com"
KINDS = {"movie": "film", "game": "gra"}
PAGE_SIZE = 50
POSITIVE_FROM = 7          # ocena >= 7 -> pozytywna (jak w zbiorze IMDB)
NEGATIVE_TO = 4            # ocena <= 4 -> negatywna
PAGE_CACHE_TTL_S = 120.0
_KEY_RE = re.compile(r"^(movie|game)/([a-z0-9][a-z0-9-]*)$")
_URL_RE = re.compile(r"metacritic\.com/(movie|game)/([a-z0-9][a-z0-9-]*)", re.I)
_SPOILER_PLACEHOLDER = "[SPOILER ALERT: This review contains spoilers.]"


# --------------------------------------------------------------------------- #
# Parsowanie (czyste funkcje – testowane na fixture'ach)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class RawReview:
    id: str
    text: str
    score: float | None
    created_at: datetime
    author: str | None
    spoiler: bool = False
    thumbs_up: int | None = None
    thumbs_down: int | None = None


@dataclass(slots=True)
class ParsedPage:
    title: str | None
    year: int | None
    reviews: list[RawReview]
    method: str            # "payload" | "html"


def slugify(title: str) -> str:
    """Tytuł -> slug Metacritic: „Baldur's Gate 3” -> `baldurs-gate-3`."""
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    text = re.sub(r"['’`]", "", text.lower().replace("&", " "))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def page_url(key: str) -> str:
    return f"{BASE}/{key}/user-reviews/"


def label_for(score: float | None) -> Sentiment | None:
    if score is None:
        return None
    if score >= POSITIVE_FROM:
        return Sentiment.POSITIVE
    if score <= NEGATIVE_TO:
        return Sentiment.NEGATIVE
    return None


def guess_language(text: str) -> str:
    """Bardzo prosty detektor: udział angielskich stop-słów. `en` albo `und` (nieustalony).
    Metacritic ma też recenzje po hiszpańsku / portugalsku; filtr jakości to D6."""
    tokens = tokenize(text)
    if len(tokens) < 4:
        return "en"
    return "en" if sum(t in STOPWORDS_EN for t in tokens) / len(tokens) >= 0.15 else "und"


_DEVALUE_SPECIAL = {-1: None, -2: None, -3: float("nan"), -4: float("inf"),
                    -5: float("-inf"), -6: -0.0}
_DEVALUE_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef",
                     "EmptyShallowRef"}


def _devalue(data: list, index: int, depth: int = 0) -> Any:
    """Rozwiń wartość spod `index` ze spłaszczonego formatu devalue (Nuxt 3)."""
    if index in _DEVALUE_SPECIAL:
        return _DEVALUE_SPECIAL[index]
    if depth > 40:
        return None
    value = data[index]
    if isinstance(value, dict):
        return {k: _devalue(data, v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        if value and isinstance(value[0], str):
            tag = value[0]
            if tag in _DEVALUE_WRAPPERS:
                return _devalue(data, value[1], depth + 1) if len(value) > 1 else None
            if tag == "Date":
                return value[1]
            if tag in ("Set", "Map", "Object", "RegExp", "BigInt", "null"):
                return None
        return [_devalue(data, v, depth + 1) for v in value]
    return value


def _payload_time(date: str, version: Any) -> datetime:
    """`date` (dzień) + `version` (ms) -> dokładny czas, jeśli `version` jest z tego samego
    dnia; inaczej (recenzja edytowana później) południe UTC danego dnia."""
    day = datetime.fromisoformat(date).date()
    if isinstance(version, int | float) and version > 0:
        exact = datetime.fromtimestamp(version / 1000, UTC)
        if exact.date() == day:
            return exact
    return datetime.combine(day, dtime(12, 0), UTC)


def _parse_payload(soup: BeautifulSoup, key: str | None) -> ParsedPage | None:
    script = soup.find("script", id="__NUXT_DATA__")
    if script is None or not script.string:
        return None
    try:
        data = json.loads(script.string)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    product_url = f"/{key}/" if key else None
    reviews: list[RawReview] = []
    products: list[tuple[str | None, str | None, int | None]] = []   # (slug, title, rok)
    for i, raw in enumerate(data):
        if not isinstance(raw, dict):
            continue
        keys = raw.keys()
        if {"id", "quote", "score", "date"} <= keys:
            r = _devalue(data, i)
            if not r.get("id") or not isinstance(r.get("date"), str):
                continue
            reviewed = r.get("reviewedProduct")
            if (product_url and isinstance(reviewed, dict) and reviewed.get("url")
                    and reviewed["url"] != product_url):
                continue                                    # recenzja innego produktu
            reviews.append(RawReview(
                id=str(r["id"]),
                text=str(r.get("quote") or ""),
                score=float(r["score"]) if isinstance(r.get("score"), int | float) else None,
                created_at=_payload_time(r["date"], r.get("version")),
                author=r.get("author"),
                spoiler=bool(r.get("spoiler")),
                thumbs_up=r.get("thumbsUp"),
                thumbs_down=r.get("thumbsDown"),
            ))
        elif {"title", "slug", "premiereYear"} <= keys:
            fields = [_devalue(data, raw[k]) if isinstance(raw[k], int) else None
                      for k in ("slug", "title", "premiereYear")]
            slug, title, year = fields
            products.append((
                slug if isinstance(slug, str) else None,
                title if isinstance(title, str) else None,
                year if isinstance(year, int) and not isinstance(year, bool) else None,
            ))
    wanted = key.split("/", 1)[1] if key else None
    match = next((p for p in products if p[0] == wanted), products[0] if products else None)
    title, year = (match[1], match[2]) if match else (None, None)
    return ParsedPage(title, year, reviews, "payload")


def _parse_cards(soup: BeautifulSoup) -> ParsedPage | None:
    cards = soup.select('[data-testid="review-card"]')
    if not cards and soup.select_one('[data-testid="product-reviews"]') is None:
        return None
    reviews = []
    for card in cards:
        date_el = card.select_one('[data-testid="review-card-date"]')
        text_el = card.select_one('[data-testid="review-quote-text"]')
        header = card.select_one('[data-testid="review-card-header"]')
        if date_el is None or text_el is None:
            continue
        text = text_el.get_text(" ", strip=True)
        if text == _SPOILER_PLACEHOLDER:
            continue                                        # treść ukryta w HTML
        try:
            day = datetime.strptime(date_el.get_text(strip=True), "%b %d, %Y").date()
        except ValueError:
            continue
        score = None
        score_el = header.select_one("[aria-label]") if header else None
        if score_el and (m := re.search(r"(\d+(?:\.\d+)?) out of 10", score_el["aria-label"])):
            score = float(m.group(1))
        author = None
        if header is not None:
            href = header.get("href", "")
            author = href.strip("/").split("/")[-1] if href.startswith("/user/") else None
            author = author or header.get_text(" ", strip=True).split()[-1]
        digest = hashlib.sha1(f"{author}|{day}|{text}".encode()).hexdigest()[:20]
        reviews.append(RawReview(f"h-{digest}", text, score,
                                 datetime.combine(day, dtime(12, 0), UTC), author))
    title = None
    if soup.title and (t := soup.title.get_text(strip=True)):
        title = t.split(" user reviews")[0].strip() or None
    return ParsedPage(title, None, reviews, "html")


def parse_user_reviews(html: str, key: str | None = None) -> ParsedPage:
    """Strona `…/user-reviews/` -> tytuł, rok i recenzje (`key` = `movie/<slug>`, wybiera
    właściwy produkt, gdy strona zawiera też powiązane). Nierozpoznana -> `SourceError`."""
    soup = BeautifulSoup(html, "html.parser")
    page = _parse_payload(soup, key)
    if page is None or (not page.reviews and soup.select('[data-testid="review-card"]')):
        page = _parse_cards(soup) or page
    if page is None:
        raise SourceError(
            "Metacritic: nie rozpoznano struktury strony z recenzjami (zmiana serwisu?)."
        )
    return page


# --------------------------------------------------------------------------- #
# Źródło
# --------------------------------------------------------------------------- #
class MetacriticReviewSource:
    name = "metacritic"
    label = "Metacritic – recenzje filmów i gier (web scraping)"

    def __init__(self, http: TextGetter | None = None, clock=time.monotonic) -> None:
        self._http = http or HttpClient("Metacritic")
        self._clock = clock
        self._cache: dict[str, tuple[float, str | None]] = {}

    # ------------------------------------------------------------- wyszukiwanie
    def find_targets(self, query: str, limit: int = 10) -> list[Target]:
        """Tytuł („Dune: Part Two”), URL albo `movie/<slug>` / `game/<slug>`.
        Dla samego tytułu sprawdzamy film i grę o tym slugu (bez wyszukiwarki serwisu)."""
        q = query.strip()
        if not q or limit <= 0:
            return []
        if m := _URL_RE.search(q):
            keys = [f"{m.group(1).lower()}/{m.group(2).lower()}"]
        elif _KEY_RE.match(q.lower()):
            keys = [q.lower()]
        else:
            slug = slugify(q)
            keys = [f"{kind}/{slug}" for kind in KINDS] if slug else []
        targets = []
        for key in keys:
            html = self._page(key)
            if html is None:
                continue
            page = parse_user_reviews(html, key)
            title = page.title or key.split("/", 1)[1]
            year = f" ({page.year})" if page.year else ""
            kind = KINDS[key.split("/", 1)[0]]
            targets.append(Target(self.name, key, f"{title}{year} – {kind}", page_url(key)))
        return targets[:limit]

    # ------------------------------------------------------------- recenzje
    def fetch(
        self, target: Target, limit: int = 100, since: datetime | None = None
    ) -> list[Review]:
        if target.source != self.name:
            raise SourceError(f"Metacritic: cel {target.id} nie pochodzi z Metacritic.")
        if not _KEY_RE.match(target.key):
            raise SourceError(
                f"Metacritic: nieprawidłowy identyfikator „{target.key}” "
                "(oczekiwano movie/<slug> lub game/<slug>)."
            )
        if limit <= 0:
            return []
        html = self._page(target.key, fresh=True)
        if html is None:
            raise SourceError(f"Metacritic nie ma strony recenzji dla „{target.key}”.")
        page = parse_user_reviews(html, target.key)
        reviews: dict[str, Review] = {}
        for raw in page.reviews:
            text = clean_text(raw.text)
            if not text or (since is not None and raw.created_at <= since):
                continue
            review = Review(
                source=self.name,
                external_id=raw.id,
                target_id=target.id,
                text=text,
                created_at=raw.created_at,
                author=raw.author,
                rating=raw.score,
                label=label_for(raw.score),
                url=page_url(target.key),
                language=guess_language(text),
                extra={
                    "spoiler": raw.spoiler,
                    "thumbs_up": raw.thumbs_up,
                    "thumbs_down": raw.thumbs_down,
                    "parser": page.method,
                },
            )
            reviews.setdefault(review.id, review)
        ordered = sorted(reviews.values(), key=lambda r: (r.created_at, r.id), reverse=True)
        return ordered[:limit]

    # ------------------------------------------------------------- pomocnicze
    def _page(self, key: str, fresh: bool = False) -> str | None:
        """Strona recenzji (None = 404). `find_targets` wypełnia cache; `fetch` korzysta z niego
        tylko, jeśli wpis jest świeży (TTL), żeby od razu po wyszukaniu nie pobierać drugi raz."""
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < PAGE_CACHE_TTL_S:
            if not fresh or cached[1] is not None:
                return cached[1]
        html = self._http.get_text(page_url(key), missing_ok=True)
        self._cache[key] = (now, html)
        if len(self._cache) > 16:
            self._cache.pop(next(iter(self._cache)))
        return html
