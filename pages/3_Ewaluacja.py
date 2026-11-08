"""Widok ewaluacji i porównania modeli (O2, M7)."""

from __future__ import annotations

import streamlit as st

from opimon.ui.evaluation_view import render_evaluation_view
from opimon.ui.state import get_services

st.set_page_config(page_title="Ewaluacja", page_icon="📏", layout="wide")
render_evaluation_view(get_services())
