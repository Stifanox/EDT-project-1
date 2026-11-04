"""Wspólne przetwarzanie tekstu (P0).

Używane przez źródła (O1), modele (O2) i analizę (O3), żeby tekst treningowy i tekst
z Internetu były czyszczone TAK SAMO (wymaganie spójności zbiorów).

Rozwijanie: dozwolone nowe funkcje i opcjonalne parametry; sygnatury istniejących
funkcji muszą zostać (wpis w dzienniku decyzji).
"""

from __future__ import annotations

import html
import re

_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_BBCODE_RE = re.compile(r"\[/?[a-z0-9*]+(=[^\]]*)?\]", re.I)   # Steam używa [b], [spoiler] …
_URL_RE = re.compile(r"https?://\S+")
_SPACES_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

STOPWORDS_EN: frozenset[str] = frozenset(
    """a about above after again all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers herself him himself his how i if in into is
    it it's its itself just me more most my myself of off on once only or other our ours
    ourselves out over own same she should so some such than that that's the their theirs
    them themselves then there these they this those through to too under until up very was
    we were what when where which while who whom why will with would you your yours yourself
    yourselves i'm i've you're it's game games movie film one get got also really even much
    s t im ive dont""".split()
)


def clean_text(text: str) -> str:
    """HTML/BBCode -> zwykły tekst: encje, <br> -> nowa linia, bez tagów i URL-i,
    zredukowane białe znaki. Nie zmienia wielkości liter (modele mogą jej potrzebować)."""
    text = html.unescape(text or "")
    text = _BR_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = _BBCODE_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _NEWLINES_RE.sub("\n\n", text).strip()


def tokenize(text: str) -> list[str]:
    """Małe litery, tokeny alfanumeryczne (z apostrofem: don't, it's)."""
    return _TOKEN_RE.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    """Tokeny bez stop-słów i bez tokenów 1-znakowych / liczbowych."""
    return [t for t in tokenize(text) if t not in STOPWORDS_EN and len(t) > 1 and not t.isdigit()]
