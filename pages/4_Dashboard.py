"""Widok „Dashboard” (właściciel: O3, A2)."""

import streamlit as st

from opimon.ui.dashboard_view import render_dashboard_view
from opimon.ui.state import get_services

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
render_dashboard_view(get_services())
