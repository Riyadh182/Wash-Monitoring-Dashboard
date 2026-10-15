from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import config as C
from utils import metrics as M
from utils import ui


def _hour_fig(g: pd.DataFrame, kind: str, title: str):
    out, tgt, ach = f"{kind}_Output", f"{kind}_Target", f"{kind}_Ach"
    def col(a):
        if pd.isna(a):
            return C.C_PLAN
        return C.C_GREEN if a >= 95 else (C.C_AMBER if a >= 80 else C.C_ROSE)
    colors = [col(a) for a in g[ach]]
    fig = go.Figure()
    fig.add_bar(x=g["Time"], y=g[out], name="Output", marker_color=colors)
    fig.add_scatter(x=g["Time"], y=g[tgt], name="Target / plan", mode="lines+markers", line=dict(color=C.C_PURPLE, width=3))
    fig.add_scatter(x=g["Time"], y=g[ach], name="Achievement %", mode="lines+markers", yaxis="y2",
                    line=dict(color=C.C_AMBER, width=2, dash="dot"))
    fig.update_layout(yaxis=dict(title="pcs"), yaxis2=dict(title="Achv %", overlaying="y", side="right", showgrid=False, rangemode="tozero"),
                      xaxis=dict(tickangle=-45))
    return ui.fig_layout(fig, title, 420)


def render(b, plants, date: pd.Timestamp, till_idx: int):
    hv = M.hourly_view(b.hourly, date, plants, till_idx)
    if hv.empty:
        st.info(f"No hourly data for {date:%d %b %Y}. Check Hourly_Monitor in the Google Sheet (date inside the plan month?).")
        return
    dry_t, dry_o = hv["Dry_Target"].sum(), hv["Dry_Output"].sum()
    wet_t, wet_o = hv["Wet_Target"].sum(), hv["Wet_Output"].sum()
    dry_a = dry_o / dry_t if dry_t else float("nan")
    wet_a = wet_o / wet_t if wet_t else float("nan")
    last = M.last_hour_with_output(hv)

    k = st.columns(5)
    with k[0]: ui.kpi("Dry target (till hour)", ui.n0(dry_t), "plant plan / 24 per hour", C.C_PURPLE)
    with k[1]: ui.kpi("Dry output", ui.n0(dry_o), f"Variance {dry_o - dry_t:+,.0f}", C.C_ACT)
    with k[2]: ui.kpi("Dry achievement", ui.pct(dry_a), "", ui.ach_color(dry_a))
    with k[3]: ui.kpi("Wet target (till hour)", ui.n0(wet_t), "plant plan / 24 per hour", C.C_PURPLE)
    with k[4]: ui.kpi("Wet output", ui.n0(wet_o), f"Variance {wet_o - wet_t:+,.0f}", C.C_ACT)
    k2 = st.columns(5)
    with k2[0]: ui.kpi("Wet achievement", ui.pct(wet_a), "", ui.ach_color(wet_a))
    with k2[1]: ui.kpi("Last hour with output", last["Time"] if last is not None else "-", "", C.C_AMBER)
    with k2[2]: ui.kpi("Last hour dry / wet", f'{ui.n0(last["Dry_Output"])} / {ui.n0(last["Wet_Output"])}' if last is not None else "-", "", C.C_ACT)
    o = b.orders if not plants else b.orders[b.orders["Wash_Plant"].isin(plants)]
    with k2[3]: ui.kpi("Today input (orders)", ui.n0(o["Today_Input"].sum()), f'plan {ui.n0(o["Today_Input_Plan"].sum())}', C.C_PURPLE)
    with k2[4]: ui.kpi("Today output (orders)", ui.n0(o["Today_Output"].sum()), f'plan {ui.n0(o["Today_Output_Plan"].sum())}', C.C_GREEN)

    ui.section("Dry process: hour by hour")
    st.plotly_chart(_hour_fig(hv, "Dry", "Dry process: output vs target by hour"), use_container_width=True)
    ui.section("Wet process: hour by hour")
    st.plotly_chart(_hour_fig(hv, "Wet", "Wet process: output vs target by hour"), use_container_width=True)

    ui.section("Final hourly output")
    c1, c2 = st.columns(2)
    fig = go.Figure()
    fig.add_bar(x=hv["Time"], y=hv["Dry_Output"], name="Dry output", marker_color=C.C_AMBER)
    fig.add_bar(x=hv["Time"], y=hv["Wet_Output"], name="Wet output", marker_color=C.C_ACT)
    fig.update_layout(barmode="stack", xaxis=dict(tickangle=-45))
    c1.plotly_chart(ui.fig_layout(fig, "Hourly output (dry + wet)"), use_container_width=True)
    fig = go.Figure()
    fig.add_scatter(x=hv["Time"], y=hv["Wet_Target"].cumsum(), name="Wet target (cum)", line=dict(color=C.C_PLAN, width=3))
    fig.add_scatter(x=hv["Time"], y=hv["Wet_Output"].cumsum(), name="Wet output (cum)", line=dict(color=C.C_ACT, width=3))
    fig.add_scatter(x=hv["Time"], y=hv["Dry_Target"].cumsum(), name="Dry target (cum)", line=dict(color=C.C_PLAN, width=3, dash="dot"))
    fig.add_scatter(x=hv["Time"], y=hv["Dry_Output"].cumsum(), name="Dry output (cum)", line=dict(color=C.C_AMBER, width=3))
    fig.update_layout(xaxis=dict(tickangle=-45))
    c2.plotly_chart(ui.fig_layout(fig, "Cumulative output vs target"), use_container_width=True)

    ui.section("Last days: input and output")
    dd = b.daily if not plants else b.daily[b.daily["Wash_Plant"].isin(plants)]
    dg = dd.groupby("Date")[["Sew_Actual", "Wash_Actual", "Dry_Actual", "Sew_Plan", "Wash_Plan", "Rewash_Input", "Defect", "WashLog_Output"]].sum().reset_index()
    dg = dg[dg["Date"] <= date].tail(10)
    c3, c4 = st.columns([3, 2])
    fig = go.Figure()
    fig.add_bar(x=dg["Date"], y=dg["Sew_Actual"], name="Input (sewing)", marker_color=C.C_PURPLE)
    fig.add_bar(x=dg["Date"], y=dg["Wash_Actual"], name="Output (final)", marker_color=C.C_ACT)
    fig.add_scatter(x=dg["Date"], y=dg["Wash_Plan"], name="Output plan", mode="lines+markers", line=dict(color=C.C_AMBER, width=3))
    fig.update_layout(barmode="group")
    c3.plotly_chart(ui.fig_layout(fig, "Last 10 days: input vs output", 360), use_container_width=True)
    with c4:
        wo = dg["WashLog_Output"].sum()
        ui.kpi("Defect % (last 10 days)", ui.pct(dg["Defect"].sum() / wo if wo else float("nan")), f'{ui.n0(dg["Defect"].sum())} pcs', C.C_AMBER)
        ui.kpi("Rewash % (last 10 days)", ui.pct(dg["Rewash_Input"].sum() / wo if wo else float("nan")), f'{ui.n0(dg["Rewash_Input"].sum())} pcs', C.C_PINK)
    top = o[o["Today_Output"] > 0].sort_values("Today_Output", ascending=False).head(10)
    if len(top):
        ui.section("Top orders by output today")
        ui.table(top[["Wash_Plant", "Buyer", "Style", "PO", "Wash_Type", "Today_Input", "Today_Output", "Today_Output_Plan"]].rename(columns={
            "Wash_Plant": "Wash plant", "Wash_Type": "Wash type", "Today_Input": "Input today", "Today_Output": "Output today", "Today_Output_Plan": "Output plan today"}), 300)
    ui.section("Hourly table")
    t = hv[["Time", "Dry_Target", "Dry_Output", "Dry_Ach", "Wet_Target", "Wet_Output", "Wet_Ach"]].round(1).rename(columns={
        "Dry_Target": "Dry target", "Dry_Output": "Dry output", "Dry_Ach": "Dry achv %", "Wet_Target": "Wet target", "Wet_Output": "Wet output", "Wet_Ach": "Wet achv %"})
    ui.table(t, 360)
    ui.download_buttons(t, f"hourly_{date:%Y%m%d}", "hr_dl")
