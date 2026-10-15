from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import config as C
from utils import metrics as M
from utils import ui


def render(b, orders: pd.DataFrame):
    with st.expander("Crisis rules", expanded=False):
        c1, c2 = st.columns(2)
        days = c1.number_input("CRD within (days, overdue included) and balance still open", 1, 30, C.CRISIS_DAYS, key="cr_days")
        behind = c2.slider("or wash output below this % of plan till today", 10, 100, int(C.BEHIND_PCT * 100), key="cr_beh") / 100
    f1, f2, f3 = st.columns(3)
    plants = f1.multiselect("Wash plant", sorted(orders["Wash_Plant"].unique()), placeholder="All plants", key="cr_plant")
    buyers = f2.multiselect("Buyer", sorted(orders["Buyer"].unique()), placeholder="All buyers", key="cr_buyer")
    levels = f3.multiselect("Level", ["Overdue", "Critical", "Watch"], placeholder="All levels", key="cr_level")
    df = M.apply_filters(orders, plants, None, buyers)
    cr = M.crisis_table(df, b.today, int(days), behind)
    if len(cr) and levels:
        cr = cr[cr["Level"].isin(levels)]
    if cr.empty:
        st.success("No crisis style found with these rules.")
        return
    k = st.columns(5)
    with k[0]: ui.kpi("Crisis styles", ui.n0(len(cr)), f'{cr["Style"].nunique()} unique styles', C.C_ROSE)
    with k[1]: ui.kpi("Overdue CRD", ui.n0((cr["Level"] == "Overdue").sum()), "orders", C.C_ROSE)
    with k[2]: ui.kpi("Wash balance", ui.n0(cr["Wash_Balance"].sum()), "pcs still to deliver", C.C_AMBER)
    with k[3]: ui.kpi("Gap vs plan", ui.n0(cr["Gap_Pcs"].clip(lower=0).sum()), "pcs behind plan till now", C.C_PURPLE)
    with k[4]: ui.kpi("Sewing balance pending", ui.n0(cr["Sewing_Balance"].sum()), f'{(cr["Sewing_Balance"] > 0).sum()} styles', C.C_VIOLET)
    c1, c2 = st.columns(2)
    g = cr.groupby("Wash_Plant")[["Wash_Balance", "Gap_Pcs"]].sum().reset_index()
    fig = go.Figure()
    fig.add_bar(x=g["Wash_Plant"], y=g["Wash_Balance"], name="Wash balance", marker_color=C.C_AMBER)
    fig.add_bar(x=g["Wash_Plant"], y=g["Gap_Pcs"].clip(lower=0), name="Gap vs plan", marker_color=C.C_ROSE)
    fig.update_layout(barmode="group")
    c1.plotly_chart(ui.fig_layout(fig, "Crisis by wash plant"), use_container_width=True)
    top = cr.sort_values("Wash_Balance", ascending=False).head(12)
    fig = go.Figure()
    fig.add_bar(y=top["Style"] + " | " + top["Wash_Plant"], x=top["Total_Wash_Output"], name="Wash output", orientation="h", marker_color=C.C_ACT)
    fig.add_bar(y=top["Style"] + " | " + top["Wash_Plant"], x=top["Output_Plan_Till_Today"], name="Plan till now", orientation="h", marker_color=C.C_PLAN)
    fig.update_layout(barmode="group", yaxis=dict(autorange="reversed"))
    c2.plotly_chart(ui.fig_layout(fig, "Top 12 by balance: output vs plan"), use_container_width=True)
    ui.section("Crisis styles at a glance")
    t = M.crisis_display(cr)
    ui.table(t, 520)
    ui.download_buttons(t, "crisis_styles", "cr_dl")
