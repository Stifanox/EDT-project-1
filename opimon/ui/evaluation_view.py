"""Widok M7: zapisane wyniki M5, macierz pomyłek oraz przykłady błędów."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from opimon.services import AppServices
from opimon.ui import nav
from opimon.ui.components import page_header, target_selector

LABELS = {"model_name": "Model", "dataset_name": "Dane", "n": "n", "accuracy": "Accuracy",
          "precision": "Precision", "recall": "Recall", "f1": "F1", "seconds": "Czas [s]",
          "tp": "TP", "fp": "FP", "tn": "TN", "fn": "FN", "positive_n": "Pozytywne",
          "majority_accuracy": "Accuracy klasy większościowej", "evaluated_at": "Data pomiaru"}


def _dataset_label(name: str) -> str:
    if name.startswith("demo:"):
        return "Demo offline: " + name.removeprefix("demo:")
    if name.startswith("live:"):
        return "Internet: " + name.removeprefix("live:")
    return "Test: " + name


def confusion_chart(row: dict) -> go.Figure:
    """Wiersze = etykiety źródła, kolumny = predykcje modelu."""
    figure = go.Figure(go.Heatmap(
        z=[[int(row["tn"]), int(row["fp"])], [int(row["fn"]), int(row["tp"])]],
        x=["negatywny", "pozytywny"], y=["negatywny", "pozytywny"],
        texttemplate="%{z}", colorscale="Blues", showscale=False,
        hovertemplate="Etykieta: %{y}<br>Predykcja: %{x}<br>Liczba: %{z}<extra></extra>",
    ))
    figure.update_layout(xaxis_title="Predykcja", yaxis_title="Etykieta referencyjna",
                         height=350, margin=dict(l=40, r=20, t=20, b=40))
    return figure


def metrics_chart(table: pd.DataFrame) -> go.Figure:
    long = table.melt(id_vars=["model_name", "dataset_name"], value_vars=["accuracy", "f1"],
                      var_name="Metryka", value_name="Wynik")
    long["dataset_name"] = long["dataset_name"].map(_dataset_label)
    long["Metryka"] = long["Metryka"].map({"accuracy": "Accuracy", "f1": "F1"})
    return px.bar(long, x="model_name", y="Wynik", color="Metryka", facet_col="dataset_name",
                  barmode="group", range_y=[0, 1], labels={"model_name": "Model"}, height=400)


def _run_evaluation(
    services: AppServices, mode: str, dataset: str | None, target_id: str | None,
    sources: list[str], limit: int, force: bool,
) -> None:
    tables, details, warnings = [], [], []
    groups = ([("test", None)] if mode in {"test", "compare"} else []) + (
        [("live", source) for source in sources] if mode in {"live", "compare"} else [])
    for on, source in groups:
        try:
            table = services.compare_models(on=on, dataset_name=dataset, target_id=target_id,
                                            source_name=source, max_test=limit, force=force)
            tables.append(table)
            detail = services.evaluation_details(
                on=on, dataset_name=dataset, target_id=target_id, source_name=source,
                max_test=limit, limit=10)
            detail["dataset_name"] = table.iloc[0]["dataset_name"] if not table.empty else on
            details.append(detail)
        except Exception as exc:
            warnings.append(f"{source or dataset}: {exc}")
    st.session_state["ev_results"] = (pd.concat(tables, ignore_index=True).to_dict("records")
                                        if tables else [])
    st.session_state["ev_details"] = details
    st.session_state["ev_warnings"] = warnings
    st.session_state["ev_context"] = f"Tryb: {mode}, zbiór: {dataset or '—'}, limit: {limit}."
    st.session_state.pop("ev_confusion", None)


def _render_examples(services: AppServices) -> None:
    errors, differences = [], []
    for group in st.session_state.get("ev_details", []):
        label = _dataset_label(group["dataset_name"])
        errors.extend({**row, "Dane": label} for row in group["errors"])
        differences.extend({**row, "Dane": label} for row in group["disagreements"])
        for warning in group["warnings"]:
            st.warning(warning)
    st.subheader("Przykłady błędów i niezgodności")
    st.caption("Etykieta referencyjna pochodzi ze zbioru lub oceny autora, niezależnie od modelu.")
    if errors:
        st.dataframe(pd.DataFrame(errors).rename(columns={"text": "Treść", "label": "Etykieta",
                     "predicted": "Predykcja", "score": "P(pozytywny)", "model_name": "Model"}),
                     hide_index=True, use_container_width=True, key="ev_errors_table")
    if differences:
        st.dataframe(pd.DataFrame([
            {"id": row["review_id"], "Dane": row["Dane"],
             "Treść": row["text"], "Etykieta": row["label"],
             **row["scores"]} for row in differences
        ]), hide_index=True, use_container_width=True, key="ev_disagreements_table")
    if not errors and not differences:
        st.info("W tej próbie nie znaleziono błędów ani niezgodności gotowych modeli.")
    # O3 obsługuje docelowo review_id. Cel i pełny tekst zapewniają też przejście na zaślepce A3.
    ids = list(dict.fromkeys(row["review_id"] for row in [*errors, *differences]
                            if row.get("review_id")))
    ids = [review_id for review_id in ids if services.repository.get_review(review_id) is not None]
    if ids:
        selected = st.selectbox("Opinia do otwarcia", ids, key="ev_example_review")
        if st.button("Otwórz opinię", key="ev_open_review"):
            review = services.repository.get_review(selected)
            nav.open_reviews(target_id=review.target_id, term=review.text, review_id=selected)


def render_evaluation_view(services: AppServices) -> None:
    page_header(services, "📏 Ewaluacja i porównanie modeli",
                "Te same przykłady dla modeli; IMDB test oraz etykiety autorów z Internetu.")
    mode = st.radio("Dane", ["test", "live", "compare"], key="ev_mode", horizontal=True,
                    format_func=lambda value: {
                        "test": "Zbiór testowy", "live": "Opinie z Internetu",
                        "compare": "Test i Internet"}[value])
    dataset = None
    if mode in {"test", "compare"} and services.training_data:
        dataset = st.selectbox("Zbiór", list(services.training_data), key="ev_dataset",
                                format_func=lambda name: services.training_data[name].label)
    target_id, sources = None, []
    if mode in {"live", "compare"}:
        target_id = target_selector(services, key="ev_target")
        available = services.evaluation_sources(target_id)
        if "ev_sources" in st.session_state:
            valid = [s for s in st.session_state["ev_sources"] if s in available]
            if valid != st.session_state["ev_sources"]:
                st.session_state["ev_sources"] = valid
        default = available if "ev_sources" not in st.session_state else None
        sources = st.multiselect("Źródła (osobno)", available, default=default, key="ev_sources",
                                  format_func=lambda s: "Demo offline" if s == "sample" else s)
        if "sample" in sources:
            st.warning("Źródło demo zawiera syntetyczne opinie. Wynik nie jest ewaluacją na żywo.")
        if not available:
            st.info("Brak opinii z etykietą źródła. Pobierz dane w widoku Źródła danych.")
    limit = st.number_input("Limit przykładów na zbiór / źródło", min_value=2, max_value=100_000,
                            value=1000, step=100, key="ev_limit")
    force = st.checkbox("Przelicz mimo zapisanego wyniku", key="ev_force")
    st.caption("DistilBERT na 1000 długich recenzjach może potrzebować kilku minut na CPU.")
    if st.button("Oceń gotowe modele", key="ev_run", type="primary",
                 disabled=not services.ready_models()):
        with st.spinner("Porównanie modeli na tych samych danych…"):
            _run_evaluation(services, mode, dataset, target_id, sources, int(limit), force)
    for warning in st.session_state.get("ev_warnings", []):
        st.warning(warning)
    results = st.session_state.get("ev_results", [])
    if not results:
        st.info("Uruchom ocenę, aby zobaczyć wyniki.")
        return
    st.caption("Wyniki ostatniej oceny. Zmiana filtrów wymaga ponownego użycia przycisku. "
               + st.session_state.get("ev_context", ""))
    table = pd.DataFrame(results)
    failures = table[table["error"].fillna("") != ""]
    for row in failures.to_dict("records"):
        st.error(f"{row['model_name']}: {row['error']}")
    successful = table[table["error"].fillna("") == ""].reset_index(drop=True)
    if successful.empty:
        return
    display = successful.drop(columns=["error"]).rename(columns=LABELS)
    display["Dane"] = display["Dane"].map(_dataset_label)
    st.dataframe(display, hide_index=True, use_container_width=True, key="ev_comparison_table",
                 column_config={LABELS[key]: st.column_config.NumberColumn(format="%.3f")
                                for key in ("accuracy", "precision", "recall", "f1", "seconds",
                                            "majority_accuracy")})
    st.caption("Klasa większościowa to punkt odniesienia przewidujący zawsze częstszą etykietę. "
               "F1 dotyczy klasy pozytywnej; uwzględnij liczność i rozkład etykiet.")
    st.plotly_chart(metrics_chart(successful), use_container_width=True, key="ev_metrics_chart")
    st.subheader("Macierz pomyłek")
    chosen = st.selectbox("Model i dane", list(range(len(successful))), key="ev_confusion",
                          format_func=lambda i: f"{successful.iloc[i]['model_name']} · "
                          + _dataset_label(successful.iloc[i]["dataset_name"]))
    st.plotly_chart(confusion_chart(successful.iloc[chosen].to_dict()),
                    use_container_width=True, key="ev_confusion_chart")
    _render_examples(services)
