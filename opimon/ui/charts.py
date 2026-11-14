"""Wykresy dashboardu (O3, A2): czyste funkcje DataFrame -> `plotly` Figure, bez Streamlit.

Punkty mają `customdata` (wartość sentymentu albo `target_id`), żeby kliknięcie w wykres
mogło prowadzić do opinii lub dashboardu obiektu.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from opimon.models import SentimentSummary

POSITIVE_COLOR = "#2e9d5b"
NEGATIVE_COLOR = "#d6453d"
UNSCORED_COLOR = "#b0b0b0"
SHARE_COLOR = "#1f4e9c"
_MARGIN = dict(l=40, r=20, t=30, b=40)


def trend_chart(trend: pd.DataFrame) -> go.Figure:
    """Słupki pozytywnych / negatywnych (oś lewa) + udział pozytywnych (oś prawa, 0–100%)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for column, name, color in (("positive", "Pozytywne", POSITIVE_COLOR),
                                ("negative", "Negatywne", NEGATIVE_COLOR)):
        fig.add_trace(go.Bar(
            x=trend["period"], y=trend[column], name=name, marker_color=color,
            customdata=[column] * len(trend),
            hovertemplate="%{x|%Y-%m-%d}<br>" + name + ": %{y}<extra></extra>",
        ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=trend["period"], y=trend["positive_share"], name="Udział pozytywnych",
        mode="markers", marker=dict(color=SHARE_COLOR, size=6, opacity=0.5),
        hovertemplate="%{x|%Y-%m-%d}<br>Udział: %{y:.0%}<extra></extra>",
    ), secondary_y=True)
    if "positive_share_smoothed" in trend.columns:
        fig.add_trace(go.Scatter(
            x=trend["period"], y=trend["positive_share_smoothed"],
            name="Udział pozytywnych (wygładzony)", mode="lines",
            line=dict(color=SHARE_COLOR, width=3), connectgaps=True,
            hovertemplate="%{x|%Y-%m-%d}<br>Wygładzony: %{y:.0%}<extra></extra>",
        ), secondary_y=True)
    fig.update_layout(barmode="stack", height=380, margin=_MARGIN, hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15))
    fig.update_yaxes(title_text="Liczba opinii", secondary_y=False)
    fig.update_yaxes(title_text="Udział pozytywnych", range=[0, 1], tickformat=".0%",
                     secondary_y=True, showgrid=False)
    return fig


def distribution_chart(summary: SentimentSummary) -> go.Figure:
    """Rozkład sentymentu (pierścień): pozytywne, negatywne, bez predykcji."""
    parts = [("Pozytywne", summary.positive, POSITIVE_COLOR, "positive"),
             ("Negatywne", summary.negative, NEGATIVE_COLOR, "negative"),
             ("Bez predykcji", summary.unscored, UNSCORED_COLOR, "unscored")]
    parts = [p for p in parts if p[1] > 0]
    fig = go.Figure(go.Pie(
        labels=[p[0] for p in parts], values=[p[1] for p in parts],
        marker=dict(colors=[p[2] for p in parts]), customdata=[p[3] for p in parts],
        hole=0.55, sort=False, textinfo="percent+value",
        hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
    ))
    fig.update_layout(height=300, margin=_MARGIN, showlegend=True,
                      legend=dict(orientation="h", y=-0.1))
    return fig


def compare_chart(compare: pd.DataFrame, name: Callable[[str], str] = str) -> go.Figure:
    """Udział pozytywnych per obiekt z przedziałem ufności (jeśli są kolumny `ci_low`/`ci_high`)."""
    df = compare.dropna(subset=["positive_share"]).sort_values("positive_share")
    error_x = None
    if {"ci_low", "ci_high"} <= set(df.columns):
        error_x = dict(type="data", symmetric=False,
                       array=(df["ci_high"] - df["positive_share"]).tolist(),
                       arrayminus=(df["positive_share"] - df["ci_low"]).tolist(),
                       color="#555")
    fig = go.Figure(go.Bar(
        x=df["positive_share"], y=[name(t) for t in df["target_id"]], orientation="h",
        customdata=df["target_id"].tolist(), error_x=error_x, marker_color=SHARE_COLOR,
        text=[f"{s:.0%} (n={n})" for s, n in zip(df["positive_share"], df["total"], strict=True)],
        textposition="inside",
        hovertemplate="%{y}<br>Udział pozytywnych: %{x:.0%}<extra></extra>",
    ))
    fig.update_layout(height=max(220, 60 * len(df) + 80), margin=_MARGIN,
                      xaxis=dict(range=[0, 1], tickformat=".0%", title="Udział pozytywnych"))
    return fig
