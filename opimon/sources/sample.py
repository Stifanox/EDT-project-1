"""Zaślepka źródła (P0): opinie z `data/sample/reviews.jsonl`, BEZ sieci.

Spełnia kontrakt `ReviewSource`, dzięki czemu GUI, modele i dashboard działają od dnia 1.
Wymaganie projektu „dane do predykcji pochodzą z Internetu” realizują prawdziwe źródła
O1: `SteamReviewSource` (D1, API) i źródło scrapujące (D3). Ta zaślepka zostaje jako
tryb offline do testów i demo bez sieci.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import cached_property

from opimon import config
from opimon.errors import SourceError
from opimon.models import Review, Sentiment, Target, utcnow
from opimon.textproc import clean_text


class SampleSource:
    name = "sample"
    label = "Przykładowe opinie (offline, zaślepka)"

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or utcnow()   # `age_hours` liczone względem chwili utworzenia źródła

    @cached_property
    def _rows(self) -> list[dict]:
        path = config.SAMPLE_DIR / "reviews.jsonl"
        with path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def targets(self) -> list[Target]:
        seen: dict[str, Target] = {}
        for r in self._rows:
            seen.setdefault(r["target_key"], Target(self.name, r["target_key"], r["target_name"]))
        return sorted(seen.values(), key=lambda t: t.name)

    def find_targets(self, query: str, limit: int = 10) -> list[Target]:
        q = query.strip().lower()
        if not q:
            return []
        return [t for t in self.targets() if q in t.name.lower() or q == t.key][:limit]

    def fetch(
        self, target: Target, limit: int = 100, since: datetime | None = None
    ) -> list[Review]:
        if target.source != self.name or target.key not in {t.key for t in self.targets()}:
            raise SourceError(f"Nieznany cel w źródle przykładowym: {target.id}")
        reviews = []
        for r in self._rows:
            if r["target_key"] != target.key:
                continue
            created = self._now - timedelta(hours=r["age_hours"])
            text = clean_text(r["text"])
            if not text or (since is not None and created <= since):
                continue
            reviews.append(Review(
                source=self.name,
                external_id=r["external_id"],
                target_id=target.id,
                text=text,
                created_at=created,
                author=r.get("author"),
                label=Sentiment.POSITIVE if r["voted_up"] else Sentiment.NEGATIVE,
                extra={"playtime_hours": r.get("playtime_hours")},
            ))
        reviews.sort(key=lambda rv: rv.created_at, reverse=True)
        return reviews[: max(limit, 0)]
