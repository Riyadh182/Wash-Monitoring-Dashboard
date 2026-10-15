from __future__ import annotations

import calendar

import pandas as pd
import streamlit as st

from utils import metrics as M
from utils import ui
from utils.export import to_csv_bytes, to_excel_bytes

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _pe(df, key):
    ui.section("Plan execution report")
    g = st.radio("Group by", ["Wash plant", "Sewing unit", "Wash plant x Sewing unit", "Buyer", "Orders (detail)"], horizontal=True, key=f"{key}_g")
    by = {"Wash plant": "Wash_Plant", "Sewing unit": "Sewing_Unit", "Wash plant x Sewing unit": ["Wash_Plant", "Sewing_Unit"], "Buyer": "Buyer"}.get(g)
    t = M.order_detail(df) if by is None else M.plan_execution_table(df, by)
    t = t.rename(columns=M.LABELS)
    ui.table(t, 460)
    ui.download_buttons(t, "plan_execution_" + g.lower().replace(" ", "_"), f"{key}_dl")
    pack = {
        "By wash plant": M.plan_execution_table(df, "Wash_Plant").rename(columns=M.LABELS),
        "By sewing unit": M.plan_execution_table(df, "Sewing_Unit").rename(columns=M.LABELS),
        "Plant x Unit": M.plan_execution_table(df, ["Wash_Plant", "Sewing_Unit"]).rename(columns=M.LABELS),
        "Orders": M.order_detail(df).rename(columns=M.LABELS),
    }
    st.download_button("⬇ Plan execution pack (Excel, all groupings)", to_excel_bytes(pack), "plan_execution_report.xlsx", XLSX, key=f"{key}_pack")


def _daily(b, orders, key):
    ui.section("Daily input / output by wash type")
    st.caption("Rows: each wash type with Input and Output. Left column = month total, then one column per day. Source: Input_Board and Output_Board.")
    scope = st.selectbox("Scope", ["All wash plants combined"] + sorted(orders["Wash_Plant"].unique()), key=f"{key}_scope")
    n_days = calendar.monthrange(b.month_start.year, b.month_start.month)[1]
    plants = None if scope.startswith("All") else [scope]
    t = M.daily_wash_type(b.flow_in, b.flow_out, orders, b.month_start, n_days, plants)
    ui.table(t, 420)
    name = "daily_in_out_" + ("all_plants" if plants is None else scope)
    ui.download_buttons(t, name, f"{key}_dl")
    if st.checkbox("Prepare one Excel with all plants (combined + one sheet per plant)", key=f"{key}_allchk"):
        sheets = {"All plants": M.daily_wash_type(b.flow_in, b.flow_out, orders, b.month_start, n_days, None)}
        for p in sorted(orders["Wash_Plant"].unique()):
            sheets[p] = M.daily_wash_type(b.flow_in, b.flow_out, orders, b.month_start, n_days, [p])
        st.download_button("⬇ Daily in/out pack (Excel)", to_excel_bytes(sheets), "daily_input_output_all_plants.xlsx", XLSX, key=f"{key}_allpack")


def _wip(df, key):
    ui.section("WIP report")
    views = {"All wash plants": None, "Wash plant wise": "Wash_Plant", "Sewing unit wise": "Sewing_Unit", "Buyer wise": "Buyer",
             "Sewing unit x Buyer": ["Sewing_Unit", "Buyer"], "CRD wise": "CRD"}
    g = st.radio("WIP view", list(views), horizontal=True, key=f"{key}_g")
    t = M.wip_table(df, views[g]).rename(columns=M.LABELS)
    ui.table(t, 460)
    ui.download_buttons(t, "wip_" + g.lower().replace(" ", "_"), f"{key}_dl")
    pack = {n[:31]: M.wip_table(df, by).rename(columns=M.LABELS) for n, by in views.items()}
    st.download_button("⬇ WIP pack (Excel, all views)", to_excel_bytes(pack), "wip_report.xlsx", XLSX, key=f"{key}_pack")


def render(b, orders: pd.DataFrame):
    f1, f2, f3 = st.columns(3)
    plants = f1.multiselect("Wash plant", sorted(orders["Wash_Plant"].unique()), placeholder="All plants", key="rp_plant")
    units = f2.multiselect("Sewing unit", sorted(orders["Sewing_Unit"].unique()), placeholder="All sewing units", key="rp_unit")
    buyers = f3.multiselect("Buyer", sorted(orders["Buyer"].unique()), placeholder="All buyers", key="rp_buyer")
    df = M.apply_filters(orders, plants, units, buyers)
    which = st.radio("Report", ["Plan execution", "Daily input / output", "WIP"], horizontal=True, key="rp_which", label_visibility="collapsed")
    if which == "Plan execution":
        _pe(df, "rp_pe")
    elif which == "Daily input / output":
        _daily(b, M.apply_filters(orders, plants, units, buyers), "rp_dy")
    else:
        _wip(df, "rp_wip")
