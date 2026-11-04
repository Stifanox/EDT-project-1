"""Transport offline dla `MetacriticReviewSource` – odpowiada nagranymi stronami HTML.

Strony nagrane 2026-11-04 (`…/user-reviews/`) i przycięte: usunięte style, SVG, obrazki,
skrypty poza `__NUXT_DATA__` i atrybuty poza `data-testid`, `href`, `aria-label`, `title`, `id`.
* `movie_dune-part-two.html`, `game_elden-ring.html` – pełne strony (osadzony stan + karty HTML);
* `movie_dune-part-two_no_payload.html` – ta sama strona bez `__NUXT_DATA__` (parser zapasowy);
* `unrecognized.html` – strona bez recenzji i bez znanej struktury.
"""

from __future__ import annotations

from pathlib import Path

from opimon.errors import SourceError
from opimon.sources.metacritic import BASE, MetacriticReviewSource

DIR = Path(__file__).parent
PAGES = {
    "movie/dune-part-two": "movie_dune-part-two.html",
    "game/elden-ring": "game_elden-ring.html",
}


def load(name: str) -> str:
    return (DIR / name).read_text(encoding="utf-8")


class FakeMetacriticHttp:
    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = dict(PAGES if pages is None else pages)
        self.calls: list[str] = []

    def get_text(self, url: str, params=None, missing_ok: bool = False) -> str | None:
        self.calls.append(url)
        assert url.startswith(BASE + "/") and url.endswith("/user-reviews/"), url
        key = url[len(BASE) + 1 : -len("/user-reviews/")]
        if key in self.pages:
            return load(self.pages[key])
        if missing_ok:
            return None
        raise SourceError("Metacritic: serwis zwrócił błąd HTTP 404.")


def make_offline_metacritic_source() -> MetacriticReviewSource:
    return MetacriticReviewSource(http=FakeMetacriticHttp())
