"""Słowa kluczowe (A4): co chwalą, co krytykują i co pojawiło się ostatnio.

Waga termu = z-score log-odds z informacyjnym priorem Dirichleta (Monroe, Colaresi, Quinn 2008,
„Fightin' Words”). Liczymy liczbę OPINII zawierających term (nie wystąpień), więc jedna długa
opinia z powtórzeniami nie dominuje. Rzadkie słowa mają dużą wariancję, czyli mały z-score,
a dodatkowo obowiązuje minimalna liczba opinii (`min_count`).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta

from opimon.models import ScoredReview, Sentiment, TermStat, utcnow
from opimon.textproc import content_tokens

DEFAULT_MIN_COUNT = 3
MIN_COUNT_SHARE = 0.05       # przy małych próbkach próg = 5% opinii grupy (co najmniej 1)
PRIOR_STRENGTH = 10.0        # siła priora (α0) względem liczby opinii
REDUNDANT_OVERLAP = 0.8
MIN_EMERGING_Z = 1.0         # „rosnące” termy: odrzuć słabe różnice (szum losowy)
_SENTENCE_RE = re.compile(r"[.!?;:,\n()\[\]\"]+")


def review_terms(text: str, bigrams: bool = True) -> set[str]:
    """Unikalne termy opinii: słowa bez stop-słów + bigramy sąsiednich słów w obrębie zdania."""
    terms: set[str] = set()
    for sentence in _SENTENCE_RE.split(text):
        tokens = content_tokens(sentence)
        terms.update(tokens)
        if bigrams:
            terms.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False) if a != b)
    return terms


def _doc_counts(texts: Iterable[str], bigrams: bool) -> tuple[Counter[str], int]:
    counts: Counter[str] = Counter()
    n = 0
    for text in texts:
        counts.update(review_terms(text, bigrams))
        n += 1
    return counts, n


def effective_min_count(n_docs: int, min_count: int = DEFAULT_MIN_COUNT) -> int:
    """Próg liczby opinii: `min_count`, ale przy bardzo małych grupach 5% opinii (≥ 1)."""
    return max(1, min(min_count, math.ceil(n_docs * MIN_COUNT_SHARE)))


def log_odds_z(
    target: Counter[str], n_target: int, other: Counter[str], n_other: int,
    min_count: int, prior_strength: float = PRIOR_STRENGTH,
) -> list[tuple[str, int, float]]:
    """(term, liczba opinii w grupie docelowej, z-score) dla termów częstszych w grupie
    docelowej niż w drugiej; `n_*` = liczba opinii w grupie. Malejąco po z-score."""
    total_target, total_other = sum(target.values()), sum(other.values())
    vocab_total = total_target + total_other
    if not vocab_total or not n_target:
        return []
    alpha0 = prior_strength * (n_target + n_other)
    out = []
    for term, y_t in target.items():
        if y_t < min_count:
            continue
        y_o = other.get(term, 0)
        alpha = alpha0 * (y_t + y_o) / vocab_total
        delta = (math.log((y_t + alpha) / (total_target + alpha0 - y_t - alpha))
                 - math.log((y_o + alpha) / (total_other + alpha0 - y_o - alpha)))
        z = delta / math.sqrt(1 / (y_t + alpha) + 1 / (y_o + alpha))
        if z > 0:
            out.append((term, y_t, z))
    out.sort(key=lambda t: (-t[2], -t[1], t[0]))
    return out


def drop_redundant(
    scored: list[tuple[str, int, float]], overlap: float = REDUNDANT_OVERLAP,
    min_count: int = DEFAULT_MIN_COUNT,
) -> list[tuple[str, int, float]]:
    """Usuwa powtórzenia tej samej frazy: słowo, które prawie zawsze (≥ `overlap` jego opinii)
    występuje w bigramie z listy, oraz bigram zachodzący słowem na wyżej oceniony bigram
    o podobnej liczności („runs perfectly”, „perfectly old”, „old laptop” -> jedna fraza).
    Termy z mniej niż `min_count` opiniami zostają (za mało danych, żeby ocenić powtórzenie)."""
    bigrams = [(t, c) for t, c, _ in scored if " " in t]
    kept = []
    for i, (term, count, z) in enumerate(scored):
        words = set(term.split())
        if count < min_count:
            redundant = False
        elif len(words) == 1:
            redundant = any(term in b.split() and c >= overlap * count for b, c in bigrams)
        else:
            redundant = any(
                " " in other and words & set(other.split()) and c >= overlap * count
                for other, c, _ in scored[:i]
            )
        if not redundant:
            kept.append((term, count, z))
    return kept


def top_terms(
    rows: Sequence[ScoredReview], sentiment: Sentiment, n: int = 20,
    min_count: int = DEFAULT_MIN_COUNT, bigrams: bool = True,
) -> list[TermStat]:
    """Termy charakterystyczne dla opinii o danym sentymencie (wg predykcji) względem opinii
    o sentymencie przeciwnym. `weight` = z-score log-odds, `count` = liczba opinii z termem."""
    target = [r.review.text for r in rows if r.sentiment is sentiment]
    other = [r.review.text for r in rows
             if r.sentiment is not None and r.sentiment is not sentiment]
    t_counts, n_t = _doc_counts(target, bigrams)
    o_counts, n_o = _doc_counts(other, bigrams)
    scored = drop_redundant(
        log_odds_z(t_counts, n_t, o_counts, n_o, effective_min_count(n_t, min_count)))
    return [TermStat(term, count, sentiment, round(z, 4)) for term, count, z in scored[:n]]


def emerging_terms(
    rows: Sequence[ScoredReview], recent_days: int = 7, now: datetime | None = None,
    n: int = 15, min_count: int = DEFAULT_MIN_COUNT, bigrams: bool = True,
    min_z: float = MIN_EMERGING_Z,
) -> list[TermStat]:
    """Termy częstsze w ostatnich `recent_days` dniach niż wcześniej (wszystkie opinie, także
    bez predykcji); ścisły próg `min_count` opinii w ostatnim okresie i z-score ≥ `min_z`.
    `sentiment` = przeważający sentyment opinii z termem w ostatnim okresie
    (remis lub brak predykcji -> negatywny, bo nowe tematy zwykle dotyczą problemów).
    Brak opinii w którymś z okresów -> `[]` (nie ma czego porównać)."""
    cutoff = (now or utcnow()) - timedelta(days=recent_days)
    recent = [r for r in rows if r.review.created_at >= cutoff]
    earlier = [r for r in rows if r.review.created_at < cutoff]
    if not recent or not earlier:
        return []
    r_counts, n_r = _doc_counts((r.review.text for r in recent), bigrams)
    e_counts, n_e = _doc_counts((r.review.text for r in earlier), bigrams)
    scored = [t for t in drop_redundant(log_odds_z(r_counts, n_r, e_counts, n_e, min_count))
              if t[2] >= min_z][:n]
    balance: Counter[str] = Counter()
    wanted = {term for term, _, _ in scored}
    for r in recent:
        if r.sentiment is None:
            continue
        for term in review_terms(r.review.text, bigrams) & wanted:
            balance[term] += 1 if r.sentiment is Sentiment.POSITIVE else -1
    return [
        TermStat(term, count,
                 Sentiment.POSITIVE if balance[term] > 0 else Sentiment.NEGATIVE, round(z, 4))
        for term, count, z in scored
    ]
