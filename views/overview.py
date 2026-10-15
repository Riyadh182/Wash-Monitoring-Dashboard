from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import config as C
from utils import metrics as M
from utils import ui
from utils.export import to_excel_bytes


def render(b, orders: pd.DataFrame):
    ui.section("Filters")
    f1, f2, f3, f4 = st.columns(4)
    plants = f1.multiselect("Wash plant", sorted(orders["Wash_Plant"].unique()), placeholder="All plants", key="ov_plant")
    units = f2.multiselect("Sewing unit", sorted(orders["Sewing_Unit"].unique()), placeholder="All sewing units", key="ov_unit")
    buyers = f3.multiselect("Buyer", sorted(orders["Buyer"].unique()), placeholder="All buyers", key="ov_buyer")
    crd_opts = sorted(orders["CRD"].dropna().dt.strftime("%Y-%m-%d").unique())
    crds = f4.multiselect("CRD", crd_opts, placeholder="All CRDs", key="ov_crd")
    open_only = st.checkbox("Only orders with balance still to deliver", key="ov_open")
    df = M.apply_filters(orders, plants, units, buyers, crds, open_only)
    k = M.kpis(df, b.units, plants)
    if df.empty:
        st.info("No orders for this filter.")
        return

    # ---- KPI cards ---------------------------------------------------------------------------
    r1 = st.columns(5)
    with r1[0]: ui.kpi("Wet process capacity / day", ui.n0(k["wet_cap"]), f'{k["n_plants"]} plants', C.C_PURPLE)
    with r1[1]: ui.kpi("Dry process capacity / day", ui.n0(k["dry_cap"]), f'{k["n_plants"]} plants', C.C_PURPLE)
    with r1[2]: ui.kpi("Running styles", f'{k["orders"]} orders', f'{k["styles_unique"]} unique styles | qty {ui.n0(k["qty"])}', C.C_ACT)
    with r1[3]: ui.kpi("Crisis orders (CRD <= 7 d)", ui.n0(k["crisis_orders"]), f'{ui.n0(k["crisis_pcs"])} pcs still to deliver', C.C_ROSE)
    with r1[4]: ui.kpi("Total WIP", ui.n0(k["wip"]), f'incl. rewash WIP {ui.n0(k["rewash_wip"])}', C.C_AMBER)
    r2 = st.columns(5)
    with r2[0]: ui.kpi("Plan input (till today)", ui.n0(k["plan_in"]), f'Month plan {ui.n0(k["month_in"])}', C.C_PURPLE)
    with r2[1]: ui.kpi("Actual input", ui.n0(k["act_in"]), f'Variation {k["in_var"]:+,.0f}', C.C_ACT)
    with r2[2]: ui.kpi("Input achievement", ui.pct(k["in_ach"]), "", ui.ach_color(k["in_ach"]))
    with r2[3]: ui.kpi("Plan output (till today)", ui.n0(k["plan_out"]), f'Month plan {ui.n0(k["month_out"])}', C.C_PURPLE)
    with r2[4]: ui.kpi("Actual output", ui.n0(k["act_out"]), f'Achv {ui.pct(k["out_ach"])} | var {k["out_var"]:+,.0f}', C.C_GREEN)
    r3 = st.columns(5)
    mh = k["max_hold"]
    with r3[0]:
        ui.kpi("Max holding time (WIP in wash)", f'{mh["days"]} days' if mh else "-",
               f'{mh["buyer"]} | {mh["style"]} | {mh["plant"]}' if mh else "no WIP", C.C_ROSE if mh and mh["days"] >= 3 else C.C_AMBER)
    with r3[1]: ui.kpi("Next 7 days CRD: WIP", ui.n0(k["next7_wip"]), f'{k["next7_orders"]} orders | {k["next7_styles"]} styles | balance {ui.n0(k["next7_balance"])}', C.C_ROSE)
    with r3[2]: ui.kpi("Dry output vs plan", ui.pct(k["dry_ach"]), f'{ui.n0(k["dry_out"])} of {ui.n0(k["dry_plan"])}', ui.ach_color(k["dry_ach"]))
    with r3[3]: ui.kpi("Sewing balance", ui.n0(k["sew_balance"]), "pcs still to be received", C.C_AMBER)
    with r3[4]: ui.kpi("Wash balance", ui.n0(k["balance"]), "pcs still to deliver", C.C_VIOLET)

    # ---- charts -----------------------------------------------------------------------------
    ui.section("Plan vs actual")
    c1, c2 = st.columns(2)
    by_plant = M.group_table(df, "Wash_Plant")
    fig = go.Figure()
    fig.add_bar(x=by_plant["Wash_Plant"], y=by_plant["Output_Plan_Till_Today"], name="Plan output", marker_color=C.C_PLAN)
    fig.add_bar(x=by_plant["Wash_Plant"], y=by_plant["Total_Wash_Output"], name="Actual output", marker_color=C.C_ACT)
    fig.update_layout(barmode="group")
    c1.plotly_chart(ui.fig_layout(fig, "Output: plan vs actual by wash plant"), use_container_width=True)
    fig = go.Figure()
    fig.add_bar(x=by_plant["Wash_Plant"], y=by_plant["Wash_WIP"], name="WIP", marker_color=C.C_PURPLE)
    fig.add_bar(x=by_plant["Wash_Plant"], y=by_plant["Rewash_WIP"], name="Rewash WIP", marker_color=C.C_PINK)
    fig.update_layout(barmode="stack")
    c2.plotly_chart(ui.fig_layout(fig, "WIP by wash plant (stacked)"), use_container_width=True)

    c3, c4 = st.columns(2)
    bb = M.group_table(df, "Buyer").sort_values("Total_WIP", ascending=False).head(12)
    fig = go.Figure()
    fig.add_bar(x=bb["Buyer"], y=bb["Total_WIP"], name="Total WIP", marker_color=C.C_VIOLET)
    fig.add_bar(x=bb["Buyer"], y=bb["Wash_Balance"], name="Balance to deliver", marker_color=C.C_AMBER)
    fig.update_layout(barmode="group")
    c3.plotly_chart(ui.fig_layout(fig, "Buyer-wise WIP and balance (top 12 by WIP)"), use_container_width=True)
    d = df.copy()
    d["Week"] = d["CRD"].dt.to_period("W-SAT").dt.start_time
    wk = d.groupby("Week")["Wash_Balance"].sum().reset_index().dropna()
    cols = [C.C_ROSE if w + pd.Timedelta(days=6) < b.today else (C.C_AMBER if w <= b.today + pd.Timedelta(days=7) else C.C_ACT) for w in wk["Week"]]
    fig = go.Figure(go.Bar(x=wk["Week"], y=wk["Wash_Balance"], marker_color=cols))
    c4.plotly_chart(ui.fig_layout(fig, "Balance to deliver by CRD week (red overdue, amber next 7 days)"), use_container_width=True)

    c5, c6 = st.columns(2)
    dd = b.daily if not plants else b.daily[b.daily["Wash_Plant"].isin(plants)]
    if len(dd):
        dg = dd.groupby("Date")[["Sew_Plan", "Sew_Actual", "Wash_Plan", "Wash_Actual", "Dry_Plan", "Dry_Actual"]].sum().reset_index()
        fig = go.Figure()
        fig.add_scatter(x=dg["Date"], y=dg["Sew_Plan"].cumsum(), name="Input plan (cum)", line=dict(color=C.C_PLAN, width=3))
        fig.add_scatter(x=dg["Date"], y=dg["Sew_Actual"].cumsum(), name="Input actual (cum)", line=dict(color=C.C_PURPLE, width=3))
        fig.add_scatter(x=dg["Date"], y=dg["Wash_Plan"].cumsum(), name="Output plan (cum)", line=dict(color=C.C_PLAN, width=3, dash="dot"))
        fig.add_scatter(x=dg["Date"], y=dg["Wash_Actual"].cumsum(), name="Output actual (cum)", line=dict(color=C.C_ACT, width=3))
        c5.plotly_chart(ui.fig_layout(fig, "Month: cumulative plan vs actual (input and output)"), use_container_width=True)
        fig = go.Figure()
        fig.add_bar(x=dg["Date"], y=dg["Wash_Plan"], name="Output plan", marker_color=C.C_PLAN)
        fig.add_bar(x=dg["Date"], y=dg["Wash_Actual"], name="Output actual", marker_color=C.C_ACT)
        fig.add_bar(x=dg["Date"], y=dg["Dry_Actual"], name="Dry actual", marker_color=C.C_AMBER)
        fig.update_layout(barmode="group")
        c6.plotly_chart(ui.fig_layout(fig, "Daily output: plan vs actual"), use_container_width=True)
    hold = df[df["Total_WIP"] > 0].groupby("Buyer")["Holding_Days"].max().sort_values(ascending=False).head(10).reset_index()
    if len(hold):
        fig = go.Figure(go.Bar(x=hold["Holding_Days"], y=hold["Buyer"], orientation="h", marker_color=C.C_ROSE))
        fig.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(ui.fig_layout(fig, "Max holding time in wash by buyer (days)", 340), use_container_width=True)

    # ---- tables --------------------------------------------------------------------------------
    ui.section("Overview tables (every table is downloadable)")
    view = st.radio("View", ["Overall", "Wash plant", "Sewing unit", "Buyer", "CRD", "Orders"], horizontal=True, key="ov_view", label_visibility="collapsed")
    by = {"Overall": None, "Wash plant": "Wash_Plant", "Sewing unit": "Sewing_Unit", "Buyer": "Buyer", "CRD": "CRD"}.get(view, "Orders")
    if by == "Orders":
        t = M.order_detail(df)
    else:
        t = M.overview_table(df, by)
    t = t.rename(columns=M.LABELS)
    ui.table(t, 360)
    ui.download_buttons(t, f"overview_{view.lower().replace(' ', '_')}", "ov_dl")
    ui.section("Download the whole overview as one Excel workbook")
    pack = {n: M.overview_table(df, by).rename(columns=M.LABELS) for n, by in
            (("Overall", None), ("Wash plant", "Wash_Plant"), ("Sewing unit", "Sewing_Unit"), ("Buyer", "Buyer"), ("CRD", "CRD"))}
    pack["Orders"] = M.order_detail(df).rename(columns=M.LABELS)
    st.download_button("⬇ Overview pack (Excel, all views)", to_excel_bytes(pack), "overview_pack.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ov_pack")
