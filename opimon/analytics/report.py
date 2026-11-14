"""Eksport CSV i raport HTML monitoringu (A6). Czyste funkcje bez Streamlit."""

from __future__ import annotations

import csv
import html
import io
from collections.abc import Sequence
from datetime import datetime

from opimon.analytics.terms import emerging_terms, top_terms
from opimon.interfaces import OpinionAnalytics
from opimon.models import Alert, ScoredReview, Sentiment, Target, utcnow

CSV_COLUMNS = (
    "id", "target_id", "created_at", "author", "sentiment", "score",
    "source_label", "url", "text",
)


def reviews_to_csv(rows: Sequence[ScoredReview]) -> str:
    """Przefiltrowane opinie z predykcją wybranego modelu -> CSV (UTF-8 z BOM dla Excela)."""
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "id": r.review.id,
            "target_id": r.review.target_id,
            "created_at": r.review.created_at.isoformat(),
            "author": r.review.author or "",
            "sentiment": r.sentiment.value if r.sentiment else "",
            "score": "" if r.score is None else f"{r.score:.6f}",
            "source_label": r.review.label.value if r.review.label else "",
            "url": r.review.url or "",
            "text": r.review.text,
        })
    return buf.getvalue()


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{100 * value:.1f}%".replace(".", ",")


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _terms_list(terms: Sequence) -> str:
    if not terms:
        return "<p><em>Brak danych.</em></p>"
    items = "".join(
        f"<li><strong>{_escape(t.term)}</strong> "
        f"({t.count}, waga {_escape(f'{t.weight:.2f}'.replace('.', ','))})</li>"
        for t in terms
    )
    return f"<ul>{items}</ul>"


def _alerts_list(alerts: Sequence[Alert], name: str) -> str:
    if not alerts:
        return f"<p><em>Brak alertów dla {_escape(name)}.</em></p>"
    items = "".join(
        f"<li><strong>{_escape(a.level.value)}</strong>: {_escape(a.message)}</li>"
        for a in alerts
    )
    return f"<ul>{items}</ul>"


def render_report(
    rows: Sequence[ScoredReview],
    target: Target | None,
    analytics: OpinionAnalytics,
    *,
    now: datetime | None = None,
    model_label: str | None = None,
) -> str:
    """Raport HTML dla obiektu (lub wszystkich, gdy `target is None`): KPI, trend, słowa, alerty."""
    now = now or utcnow()
    name = target.name if target else "Wszystkie obiekty"
    summary = analytics.summary(rows)
    trend = analytics.trend(rows, "D")
    pos_terms = top_terms(rows, Sentiment.POSITIVE, n=10)
    neg_terms = top_terms(rows, Sentiment.NEGATIVE, n=10)
    emerging = emerging_terms(rows, now=now, n=10)
    alerts = analytics.alerts(rows, now)
    if target is not None:
        alerts = [a for a in alerts if a.target_id == target.id]

    trend_rows = ""
    if not trend.empty:
        for _, row in trend.iterrows():
            share = row["positive_share"]
            share_s = "–" if share != share else _pct(float(share))  # NaN != NaN
            period = row["period"].strftime("%Y-%m-%d")
            trend_rows += (
                f"<tr><td>{period}</td><td>{int(row['positive'])}</td>"
                f"<td>{int(row['negative'])}</td><td>{int(row['total'])}</td>"
                f"<td>{share_s}</td></tr>"
            )
    trend_table = (
        "<table><thead><tr><th>Dzień</th><th>Poz.</th><th>Neg.</th><th>Razem</th>"
        "<th>Udział poz.</th></tr></thead><tbody>"
        + (trend_rows or "<tr><td colspan='5'><em>Brak danych.</em></td></tr>")
        + "</tbody></table>"
    )

    model_line = f"<p>Model: <strong>{_escape(model_label)}</strong></p>" if model_label else ""
    return f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8">
<title>Raport – {_escape(name)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
h1, h2 {{ color: #0b3d5c; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.6rem; text-align: left; }}
th {{ background: #f0f4f8; }}
.kpi {{ display: flex; gap: 1.5rem; flex-wrap: wrap; margin: 1rem 0; }}
.kpi div {{ background: #f7fafc; padding: 0.8rem 1.2rem; border-radius: 6px; min-width: 8rem; }}
.kpi strong {{ display: block; font-size: 1.4rem; }}
</style></head><body>
<h1>Raport sentymentu: {_escape(name)}</h1>
<p>Wygenerowano: {_escape(now.strftime('%Y-%m-%d %H:%M UTC'))}</p>
{model_line}
<p>Opinie w raporcie: <strong>{len(rows)}</strong>
{" · cel: " + _escape(target.id) if target else ""}</p>

<h2>KPI</h2>
<div class="kpi">
<div>Opinie<strong>{summary.total}</strong></div>
<div>Pozytywne<strong>{summary.positive}</strong></div>
<div>Negatywne<strong>{summary.negative}</strong></div>
<div>Bez predykcji<strong>{summary.unscored}</strong></div>
<div>Udział pozytywnych<strong>{_pct(summary.positive_share)}</strong></div>
</div>

<h2>Trend dzienny</h2>
{trend_table}

<h2>Słowa kluczowe</h2>
<h3>Pozytywne</h3>
{_terms_list(pos_terms)}
<h3>Negatywne</h3>
{_terms_list(neg_terms)}
<h3>Co się zmieniło ostatnio</h3>
{_terms_list(emerging)}

<h2>Alerty</h2>
{_alerts_list(alerts, name)}
</body></html>
"""
