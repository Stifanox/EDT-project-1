"""Widok „Źródła danych” (właściciel: O1, etap D4).

Dodawanie obiektów (wyszukiwanie albo identyfikator / URL), pobieranie opinii z paskiem
postępu, lista monitorowanych obiektów (odśwież / dashboard / usuń z potwierdzeniem)
i najnowsze opinie z filtrami. Logika pomocnicza: `opimon/ui/sources_view.py`.
"""

import pandas as pd
import streamlit as st

from opimon import config
from opimon.errors import SourceError
from opimon.models import Target
from opimon.ui import nav
from opimon.ui import sources_view as view
from opimon.ui.components import ALL, SCORE_COLUMN, flash, page_header
from opimon.ui.state import get_services

st.set_page_config(page_title="Źródła danych", page_icon="🌐", layout="wide")
services = get_services()
page_header(services, "🌐 Źródła danych",
            "Wyszukaj obiekt (grę, film…), pobierz jego opinie z Internetu i monitoruj zmiany.")

REMOVE_KEY = "src_confirm_remove"
SEARCH_HINTS = {
    "steam": "nazwa gry, np. Dota 2",
    "metacritic": "tytuł filmu lub gry, np. Dune: Part Two",
    "sample": "np. Starfall",
}
MANUAL_HINTS = {
    "steam": "appid (np. 570) lub URL sklepu Steam",
    "metacritic": "URL strony na metacritic.com lub movie/<slug>, game/<slug>",
}


def run_fetch(source_name: str, target: Target, limit: int) -> None:
    """Pobierz z paskiem postępu, zapisz raport jako komunikat i przeładuj stronę."""
    bar = st.progress(0.0, text=f"Pobieranie: {target.name}…")
    report = services.fetch_reviews(source_name, target, limit,
                                    progress=lambda f, msg: bar.progress(min(f, 1.0), text=msg))
    kind, msg = view.fetch_summary(report, target.name)
    flash(msg, kind)
    for err in report.errors:
        flash(err, "error")
    st.rerun()


def _cancel_remove() -> None:
    st.session_state.pop(REMOVE_KEY, None)


@st.dialog("Usunąć obiekt z monitorowania?", on_dismiss=_cancel_remove)
def confirm_remove(target_id: str) -> None:
    count = services.repository.count_reviews(target_id)
    name = services.target_name(target_id)          # przed usunięciem – potem nazwy już nie ma
    st.write(f"**{name}** i jego **{count}** opinii (z predykcjami) "
             "zostaną usunięte z bazy. Tej operacji nie można cofnąć.")
    c1, c2 = st.columns(2)
    if c1.button("Usuń", key="src_remove_confirm", type="primary", width="stretch"):
        removed = services.remove_target(target_id)
        _cancel_remove()
        flash(f"Usunięto „{name}” i {removed} opinii.")
        st.rerun()
    if c2.button("Anuluj", key="src_remove_cancel", width="stretch"):
        _cancel_remove()
        st.rerun()


if st.session_state.get(REMOVE_KEY):
    confirm_remove(st.session_state[REMOVE_KEY])

# --------------------------------------------------------------------------- dodawanie
st.subheader("Dodaj obiekt i pobierz opinie")
source_name = st.selectbox("Źródło", list(services.sources), key="src_source",
                           format_func=lambda n: services.sources[n].label)
source = services.sources[source_name]
limit = int(st.number_input("Ile opinii pobrać (najwyżej)", 1, 5000,
                            config.DEFAULT_FETCH_LIMIT, key="src_limit"))
if source_name == "metacritic":
    st.caption("Metacritic udostępnia na stronie 50 najnowszych recenzji obiektu; kolejne "
               "pojawią się przy następnych odświeżeniach.")

tab_search, tab_manual = st.tabs(["🔎 Wyszukaj", "🔗 Identyfikator / URL"])
with tab_search:
    query = st.text_input("Szukaj obiektu", key="src_query",
                          placeholder=SEARCH_HINTS.get(source_name, ""))
    targets: list[Target] = []
    if query.strip():
        try:
            targets = source.find_targets(query)
        except SourceError as exc:
            st.error(str(exc))
        else:
            if not targets:
                st.info("Brak wyników. Spróbuj innej nazwy albo zakładki „Identyfikator / URL”.")
    if targets:
        target = st.selectbox("Wynik", targets, key="src_target", format_func=lambda t: t.name)
        if st.button("Pobierz opinie", key="src_fetch", type="primary"):
            run_fetch(source_name, target, limit)

with tab_manual:
    manual = st.text_input("Identyfikator lub URL", key="src_manual",
                           placeholder=MANUAL_HINTS.get(source_name, "identyfikator obiektu"))
    if st.button("Dodaj i pobierz", key="src_manual_add", disabled=not manual.strip()):
        try:
            target = view.resolve_manual_target(source, manual)
        except SourceError as exc:
            st.error(str(exc))
        else:
            run_fetch(source_name, target, limit)

# --------------------------------------------------------------------------- monitorowane
st.subheader("Monitorowane obiekty")
watch = view.watchlist_frame(services)
if watch.empty:
    st.info("Brak monitorowanych obiektów – dodaj obiekt powyżej.")
else:
    if st.button("🔄 Odśwież wszystkie (tylko nowe opinie)", key="src_refresh_all"):
        bar = st.progress(0.0, text="Odświeżanie…")
        reports = services.refresh_all(
            progress=lambda f, msg: bar.progress(min(f, 1.0), text=msg))
        kind, msg = view.refresh_summary(reports)
        flash(msg, kind)
        for r in reports:
            for err in r.errors:
                flash(f"{services.target_name(r.target_id)}: {err}", "error")
        st.rerun()
    header = st.columns([4, 3, 1, 2, 3])
    for col, title in zip(header, ["Obiekt", "Źródło", "Opinie", "Najnowsza opinia", ""],
                          strict=True):
        col.markdown(f"**{title}**")
    for row in watch.to_dict("records"):
        tid = row["id"]
        c1, c2, c3, c4, c5 = st.columns([4, 3, 1, 2, 3], vertical_alignment="center")
        c1.markdown(f"[{row['Obiekt']}]({row['Strona']})" if row["Strona"] else row["Obiekt"])
        c2.write(row["Źródło"])
        c3.write(str(row["Opinie"]))
        latest = row["Najnowsza opinia"]
        c4.write("–" if pd.isna(latest) else latest.strftime("%Y-%m-%d %H:%M"))
        b1, b2, b3 = c5.columns(3)
        if b1.button("🔄", key=f"src_refresh_{tid}", help="Pobierz nowe opinie"):
            target = services.repository.get_target(tid)
            run_fetch(target.source, target, limit)
        if b2.button("📊", key=f"src_dash_{tid}", help="Dashboard"):
            nav.open_dashboard(tid)
        if b3.button("🗑️", key=f"src_remove_{tid}", help="Usuń z monitorowania"):
            st.session_state[REMOVE_KEY] = tid
            st.rerun()

# --------------------------------------------------------------------------- opinie
st.subheader("Najnowsze opinie")
f1, f2 = st.columns(2)
present = sorted({t.source for t in services.repository.list_targets()})
filter_source = f1.selectbox("Źródło", [ALL, *present], key="src_filter_source",
                             format_func=lambda n: "Wszystkie" if n == ALL
                             else view.source_label(services, n))
source_filter = None if filter_source == ALL else filter_source
target_options = [ALL] + [t.id for t in services.repository.list_targets()
                          if source_filter is None or t.source == source_filter]
if st.session_state.get("src_filter_target") not in target_options:
    st.session_state["src_filter_target"] = ALL
filter_target = f2.selectbox("Obiekt", target_options, key="src_filter_target",
                             format_func=lambda t: "Wszystkie" if t == ALL
                             else services.target_name(t))
rows = view.latest_reviews(services, source_filter,
                           None if filter_target == ALL else filter_target, limit=50)
default_model = services.default_model_name
model_label = services.models[default_model].label if default_model else "–"
st.caption(f"{len(rows)} najnowszych opinii (domyślny model: {model_label})")
st.dataframe(
    view.reviews_frame(services, rows),
    hide_index=True,
    width="stretch",
    column_order=[c for c in view.REVIEW_COLUMNS if c != "id"],
    column_config={
        "P(pozytywny)": SCORE_COLUMN,
        "Data": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        "Ocena autora": st.column_config.NumberColumn(format="%.0f"),
        "Link": st.column_config.LinkColumn(display_text="Otwórz"),
        "Treść": st.column_config.TextColumn(width="large"),
    },
    key="src_reviews",
)
