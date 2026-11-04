"""Widok „Modele” (właściciel: O2, rozbudowa w M6)."""

import pandas as pd
import streamlit as st

from opimon.errors import OpimonError
from opimon.models import Sentiment
from opimon.ui.components import flash, page_header
from opimon.ui.state import get_services

st.set_page_config(page_title="Modele", page_icon="🧠", layout="wide")
services = get_services()
page_header(services, "🧠 Modele sentymentu", "Trening, stan modeli i test na własnym tekście.")

infos = services.model_infos()
st.dataframe(
    pd.DataFrame({
        "Model": [i.label for i in infos],
        "Nazwa": [i.name for i in infos],
        "Gotowy": [i.ready for i in infos],
        "Wymaga treningu": [i.requires_training for i in infos],
        "Wytrenowany": [i.trained_at for i in infos],
        "Przykładów treningowych": [i.train_size for i in infos],
        "Uwagi": [i.notes for i in infos],
    }),
    hide_index=True, use_container_width=True,
)

st.subheader("Trening")
trainable = [i.name for i in infos if i.requires_training]
if trainable:
    c1, c2 = st.columns(2)
    model_name = c1.selectbox("Model", trainable, key="mdl_train_model",
                              format_func=lambda n: services.models[n].label)
    dataset = c2.selectbox("Zbiór treningowy", list(services.training_data), key="mdl_dataset",
                           format_func=lambda n: services.training_data[n].label)
    if st.button("Trenuj", key="mdl_train", type="primary"):
        try:
            with st.spinner("Trening i ponowna analiza opinii…"):
                info = services.train_model(model_name, dataset)
            flash(f"Wytrenowano „{info.label}” na {info.train_size} przykładach.")
        except (OpimonError, ValueError) as exc:
            flash(str(exc), "error")
        st.rerun()
else:
    st.info("Żaden model nie wymaga treningu.")

st.subheader("Wypróbuj na własnym tekście")
text = st.text_area("Tekst opinii (po angielsku)", key="mdl_try_text",
                    placeholder="Not bad at all, I was not expecting it to be this addictive.")
if text.strip():
    rows = []
    for name in services.ready_models():
        score = services.predict_text(text, name)
        s = Sentiment.from_score(score)
        rows.append({"Model": services.models[name].label, "Sentyment": f"{s.icon} {s.label_pl}",
                     "P(pozytywny)": score})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
