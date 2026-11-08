"""Prezentacja modeli, treningu i wyjaśnień; operacje wyłącznie przez fasadę."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from opimon.errors import OpimonError
from opimon.models import Sentiment
from opimon.services import AppServices
from opimon.ui.components import flash, page_header

EXAMPLES = {
    "negation": ("Negacja", "Not bad at all, I was not expecting it to be this addictive."),
    "irony": ("Ironia", "Great, another update that breaks my save files."),
    "contrast": ("Kontrast", "I wanted to love it, but the performance is a joke."),
}


def _choose_example(text: str) -> None:
    st.session_state["mdl_try_text"] = text


def render_models_view(services: AppServices) -> None:
    page_header(services, "🧠 Modele sentymentu", "Trening, stan modeli i test własnego tekstu.")
    infos = services.model_infos()
    table = pd.DataFrame({
        "Model": [i.label for i in infos], "Nazwa": [i.name for i in infos],
        "Gotowy": [i.ready for i in infos], "Wymaga treningu": [i.requires_training for i in infos],
        "Wytrenowany": pd.to_datetime([i.trained_at for i in infos], utc=True),
        "Przykładów treningowych": pd.array([i.train_size for i in infos], dtype="Int64"),
        "Uwagi": [i.notes for i in infos],
    })
    st.dataframe(table, hide_index=True, use_container_width=True, key="mdl_models_table")

    if "distilbert" in services.models:
        st.caption("DistilBERT pobiera wagi przy pierwszym użyciu. Działa na CPU; "
                   "długie recenzje obcina do 512 tokenów.")
        if st.button("Wczytaj / pobierz DistilBERT", key="mdl_load_transformer"):
            with st.spinner("Wczytywanie modelu; pierwsze pobranie może potrwać…"):
                info = services.load_model("distilbert", allow_download=True)
            flash("DistilBERT gotowy." if info.ready else info.notes,
                  "success" if info.ready else "warning")
            st.rerun()

    st.subheader("Trening")
    trainable = [i.name for i in infos if i.requires_training]
    if trainable and services.training_data:
        c1, c2, c3 = st.columns(3)
        model_name = c1.selectbox("Model", trainable, key="mdl_train_model",
                                  format_func=lambda n: services.models[n].label)
        dataset_name = c2.selectbox("Zbiór", list(services.training_data), key="mdl_dataset",
                                    format_func=lambda n: services.training_data[n].label)
        limit = c3.number_input("Limit treningu (0 = wszystkie)", min_value=0,
                                 max_value=100_000, value=0, step=100, key="mdl_train_limit")
        if st.button("Trenuj i przelicz opinie", key="mdl_train", type="primary"):
            try:
                with st.spinner("Trening i ponowna analiza opinii…"):
                    info = services.train_model(
                        model_name, dataset_name, max_train=int(limit) or None
                    )
                flash(f"Wytrenowano „{info.label}” na {info.train_size} przykładach.")
            except (OpimonError, ValueError, OSError) as exc:
                flash(str(exc), "error")
            st.rerun()
    else:
        st.info("Brak modeli wymagających treningu lub zbiorów treningowych.")

    ready = services.ready_models()
    st.subheader("Analiza zapisanych opinii")
    if ready:
        selected = st.selectbox("Model do analizy", ready, key="mdl_analyze_model",
                                format_func=lambda n: services.models[n].label)
        st.caption("Opinie mające już predykcję tego modelu są pomijane. "
                   "Trening automatycznie usuwa stare predykcje i przelicza je ponownie.")
        if st.button("Przeanalizuj wszystkie opinie", key="mdl_analyze"):
            with st.spinner("Analiza opinii bez predykcji…"):
                count = services.analyze_pending(selected)
            error = services.module_errors.get(f"model:{selected}")
            flash(error or f"Zapisano {count} nowych predykcji.", "error" if error else "success")
            st.rerun()
    else:
        st.info("Wytrenuj model lub wczytaj wagi, aby analizować opinie.")

    st.subheader("Wypróbuj na własnym tekście")
    for column, (key, (label, text)) in zip(st.columns(3), EXAMPLES.items(), strict=True):
        column.button(label, key=f"mdl_example_{key}", on_click=_choose_example, args=(text,))
    text = st.text_area("Tekst opinii (po angielsku)", key="mdl_try_text")
    if text.strip() and ready:
        for column, name in zip(st.columns(len(ready)), ready, strict=True):
            with column:
                st.markdown(f"**{services.models[name].label}**")
                try:
                    score = services.predict_text(text, name)
                    sentiment = Sentiment.from_score(score)
                    st.metric("P(pozytywny)", f"{score:.3f}")
                    st.write(f"{sentiment.icon} {sentiment.label_pl}")
                    explanation = services.explain_text(text, name)
                    if explanation:
                        st.caption("Wkład w logit pozytywny: dodatni wzmacnia, ujemny osłabia.")
                        st.dataframe(pd.DataFrame(explanation, columns=["Cecha", "Wkład"]),
                                     hide_index=True, key=f"mdl_explain_{name}")
                except Exception as exc:
                    st.error(f"Nie można uzyskać wyniku: {exc}")
        st.caption("VADER: przeskalowany wynik słownikowy bez kalibracji; "
                   "model może błędnie odczytać sarkazm i negację.")
