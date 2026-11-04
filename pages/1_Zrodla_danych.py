"""Widok „Źródła danych” (właściciel: O1, rozbudowa w D4)."""

import streamlit as st

from opimon import config
from opimon.errors import SourceError
from opimon.ui import nav
from opimon.ui.components import SCORE_COLUMN, flash, page_header, reviews_table
from opimon.ui.state import get_services

st.set_page_config(page_title="Źródła danych", page_icon="🌐", layout="wide")
services = get_services()
page_header(services, "🌐 Źródła danych", "Wyszukaj obiekt (grę, film…) i pobierz jego opinie.")

source_name = st.selectbox(
    "Źródło", list(services.sources), key="src_source",
    format_func=lambda n: services.sources[n].label,
)
source = services.sources[source_name]
query = st.text_input("Szukaj obiektu", key="src_query", placeholder="np. Starfall")
targets = []
if query:
    try:
        targets = source.find_targets(query)
    except SourceError as exc:
        st.error(str(exc))
        query = ""
if query and not targets:
    st.info("Brak wyników dla tego zapytania.")
if targets:
    target = st.selectbox("Wynik", targets, key="src_target", format_func=lambda t: t.name)
    limit = st.number_input(
        "Ile opinii pobrać (najwyżej)", 1, 5000, config.DEFAULT_FETCH_LIMIT, key="src_limit"
    )
    if st.button("Pobierz opinie", key="src_fetch", type="primary"):
        with st.spinner("Pobieranie i analiza…"):
            report = services.fetch_reviews(source_name, target, int(limit))
        msg = (f"{target.name}: pobrano {report.fetched}, nowych {report.new}, "
               f"duplikatów {report.duplicates}, przeanalizowano {report.analyzed} "
               f"({report.seconds:.1f} s).")
        flash(msg, "success" if report.ok else "warning")
        for err in report.errors:
            flash(err, "error")
        st.rerun()

st.subheader("Monitorowane obiekty")
watch = services.repository.list_targets()
if not watch:
    st.info("Brak obiektów – pobierz opinie powyżej.")
for t in watch:
    c1, c2, c3 = st.columns([4, 2, 1])
    c1.markdown(f"**{t.name}** · `{t.id}`")
    c2.write(f"{services.repository.count_reviews(t.id)} opinii")
    if c3.button("Dashboard", key=f"src_dash_{t.id}"):
        nav.open_dashboard(t.id)
if watch and st.button("Odśwież wszystkie (tylko nowe opinie)", key="src_refresh_all"):
    reports = services.refresh_all()
    flash(f"Odświeżono {len(reports)} obiektów, nowych opinii: {sum(r.new for r in reports)}.")
    st.rerun()

st.subheader("Najnowsze opinie")
rows = services.scored_reviews(limit=50)
st.dataframe(reviews_table(services, rows), hide_index=True, use_container_width=True,
             column_config={"P(pozytywny)": SCORE_COLUMN})
