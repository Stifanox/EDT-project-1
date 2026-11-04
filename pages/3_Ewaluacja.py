"""Widok „Ewaluacja i porównanie modeli” (właściciel: O2, rozbudowa w M7)."""

import pandas as pd
import streamlit as st

from opimon.errors import OpimonError
from opimon.ui.components import page_header, target_selector
from opimon.ui.state import get_services

st.set_page_config(page_title="Ewaluacja", page_icon="📏", layout="wide")
services = get_services()
page_header(
    services, "📏 Ewaluacja i porównanie modeli",
    "Zbiór testowy (ta sama domena co trening) vs opinie z Internetu z etykietą ze źródła.",
)

mode = st.radio("Dane", ["test", "live"], key="ev_mode", horizontal=True,
                format_func=lambda m: {"test": "Zbiór testowy", "live": "Opinie z Internetu"}[m])
dataset = None
target_id = None
if mode == "test":
    dataset = st.selectbox("Zbiór", list(services.training_data), key="ev_dataset",
                           format_func=lambda n: services.training_data[n].label)
else:
    target_id = target_selector(services, key="ev_target")

if st.button("Oceń gotowe modele", key="ev_run", type="primary"):
    rows = []
    for name in services.ready_models():
        try:
            r = services.evaluate_model(name, on=mode, dataset_name=dataset, target_id=target_id)
        except (OpimonError, ValueError) as exc:
            st.error(f"{services.models[name].label}: {exc}")
            continue
        rows.append({"Model": services.models[name].label, "n": r.n, "Accuracy": r.accuracy,
                     "Precision": r.precision, "Recall": r.recall, "F1": r.f1,
                     "TP": r.tp, "FP": r.fp, "TN": r.tn, "FN": r.fn, "Czas [s]": r.seconds})
    st.session_state["ev_results"] = rows
if st.session_state.get("ev_results"):
    st.dataframe(pd.DataFrame(st.session_state["ev_results"]), hide_index=True,
                 use_container_width=True,
                 column_config={k: st.column_config.NumberColumn(format="%.3f")
                                for k in ("Accuracy", "Precision", "Recall", "F1", "Czas [s]")})
