"""Rozpoznawanie celu z tekstu wpisanego przez użytkownika (GUI D4 i CLI D5)."""

from __future__ import annotations

import re

from opimon.errors import SourceError
from opimon.interfaces import ReviewSource
from opimon.models import Target

_STEAM_URL_RE = re.compile(r"store\.steampowered\.com/app/(\d+)", re.I)


def resolve_target(source: ReviewSource, text: str) -> Target:
    """Identyfikator, URL lub nazwa -> cel. Nic nie znaleziono -> `SourceError` po polsku.

    * Steam: appid (`570`) albo URL sklepu (`https://store.steampowered.com/app/570/...`);
    * pozostałe źródła i nazwy: pierwszy wynik `find_targets` (Metacritic rozumie też URL
      i `movie/<slug>`).
    """
    value = text.strip()
    if not value:
        raise SourceError("Podaj identyfikator lub adres URL.")
    from_appid = getattr(source, "target_from_appid", None)
    if callable(from_appid):
        if m := _STEAM_URL_RE.search(value):
            return from_appid(m.group(1))
        if value.isdigit():
            return from_appid(value)
    found = source.find_targets(value, limit=1)
    if not found:
        raise SourceError(f"{source.label}: nie znaleziono obiektu „{value}”.")
    return found[0]
