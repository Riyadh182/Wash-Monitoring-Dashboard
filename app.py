"""Wash & Dry Monitor - Streamlit dashboard (reads one Google Sheet per wash plant)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Wash & Dry Monitor", page_icon="🧺", layout="wide")

from utils import config as C  # noqa: E402
from utils import data, metrics as M, ui  # noqa: E402
from views import crisis, hourly, overview, reports  # noqa: E402

ui.inject_css()


def _password_gate():
    try:
        pw = st.secrets["auth"]["password"]
    except Exception:
        return
    if st.session_state.get("ok"):
        return
    x = st.text_input("Password", type="password")
    if x and x == pw:
        st.session_state["ok"] = True
        st.rerun()
    st.stop()


_password_gate()

# ------------------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 🧺 Wash & Dry Monitor")
    demo = st.checkbox("Use demo data", value=not data.configured_plants(), help="Fake data in the same shape, to see the design.")
    if st.button("🔄 Refresh data now"):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Loading data..."):
    bundle = data.load_all(demo)

orders = M.add_calc(bundle.orders, bundle.today) if len(bundle.orders) else bundle.orders

with st.sidebar:
    for p, e in bundle.errors.items():
        st.warning(f"{p}: {e}")
    plant_opts = ["All plants"] + sorted(bundle.plants)
    sel_plant = st.selectbox("Wash plant (for hourly view)", plant_opts)
    day = st.date_input("Date", value=bundle.today.date())
    till = st.slider("Till hour (production day starts 08:00)", 1, 24, 24)
    st.markdown("---")
    style_q = st.text_input("Style search", placeholder="e.g. ST-4412 or Snow")
    wt_opts = sorted(orders["Wash_Type"].unique()) if len(orders) else []
    wt_sel = st.multiselect("Wash type", wt_opts, placeholder="All wash types")
    st.caption("Style search and wash type apply to Overview, Reports and Crisis.")

if orders.empty:
    st.error("No order data loaded. Add the Google Sheet ids in Secrets (see README) or tick 'Use demo data'.")
    st.stop()

orders = M.apply_filters(orders, style_q=style_q, wash_types=wt_sel)
plants_hourly = None if sel_plant == "All plants" else [sel_plant]

# ------------------------------------------------------------------------------ header + menu
menu = st.radio("Menu", ["📊 Overview", "⏱ Hourly Monitoring", "📑 Reports", "🚨 Crisis"], horizontal=True, label_visibility="collapsed")
till_label = f"Till hour {till} ({(8 + till) % 24:02d}:00)"
ui.banner("WASH & DRY PROCESS | MONITORING", [
    f"All {len(bundle.plants)} wash plants" if sel_plant == "All plants" else sel_plant,
    pd.Timestamp(day).strftime("%A, %d %b %Y"),
    till_label,
    "DEMO DATA" if bundle.demo else "Live: Google Sheets",
])

if menu.endswith("Overview"):
    overview.render(bundle, orders)
elif menu.endswith("Hourly Monitoring"):
    hourly.render(bundle, plants_hourly, pd.Timestamp(day), till)
elif menu.endswith("Reports"):
    reports.render(bundle, orders)
else:
    crisis.render(bundle, orders)
