"""Widok „Opinie” – przeglądarka (właściciel: O3, A3)."""

import streamlit as st

from opimon.ui.reviews_view import render_reviews_view
from opimon.ui.state import get_services

st.set_page_config(page_title="Opinie", page_icon="📝", layout="wide")
render_reviews_view(get_services())
