"""Widok modeli sentymentu (O2, M6)."""

from __future__ import annotations

import streamlit as st

from opimon.ui.models_view import render_models_view
from opimon.ui.state import get_services

st.set_page_config(page_title="Modele", page_icon="🧠", layout="wide")
render_models_view(get_services())
