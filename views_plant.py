"""Plant-level views (one wash plant, one date): hourly monitor, machines, dry process, quality, style explorer, trends, data health."""
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import calc
import reports
from ui import *


def memo(X, key, fn):
    if key not in X.cache:
        X.cache[key] = fn()
    return X.cache[key]


def machine_tbl(X):
    def f():
        MT = calc.machine_table(X.w_day, X.mm, X.unit, X.until, X.BASIS, with_plan=not X.filters_on)
        MT['Status'] = calc.status_series(MT['Achv'], MT['Hours_Logged'], X.S)
        MT['Cap_Day'] = MT['Plan_per_hr'] * X.RUN_H
        return MT
    return memo(X, 'MT', f)


def dry_tbl(X):
    def f():
        DT = calc.dry_table(X.d_day, X.mp, X.wip, X.unit, X.day, X.until, X.RUN_H, X.BASIS, with_plan=not X.style_on)
        DT['Status'] = calc.status_series(DT['Achv'], DT['Hours_Logged'], X.S)
        return DT
    return memo(X, 'DT', f)


def hourly_tbl(X):
    def f():
        H = calc.hourly_table(X.w_day, calc.WASH_NUM, X.plan_hr, X.until, X.open_w, X.DAY_START, with_plan=not X.filters_on)
        if X.filters_on:
            H['Closing_WIP'] = np.nan
        # plan INPUT (order plan of the day spread over the hours; falls back to machine plan)
        dp = X.dp
        pin, src = np.nan, 'n/a'
        if len(dp):
            d = dp[dp['Date'] == X.day]
            if X.styles_active:
                d = d[d['Style'].isin(X.styles_active)]
            if len(d) and not X.wtypes:
                pin, src = float(d['Plan_Input'].sum()), 'Order plan of the day'
        if pd.isna(pin) and not X.filters_on:
            pin, src = X.plan_hr * X.RUN_H, 'Machine capacity plan (no order plan for this date)'
        act = H['Hour_Idx'] <= X.until
        H['Plan_Input'] = np.where(act, pin / X.RUN_H if not pd.isna(pin) else np.nan, np.nan)
        H['Cum_Plan_Input'] = H['Plan_Input'].cumsum()
        H['Cum_Input'] = H['Input'].cumsum()
        H['Input_Var'] = H['Input'] - H['Plan_Input']
        H.attrs['plan_in_day'], H.attrs['plan_in_src'] = pin, src
        return H
    return memo(X, 'H', f)


def short_hours(h):
    return h['Hour'].str[:5]


def fig_plan_actual(h, S, title='Hourly Plan vs Output'):
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    x = short_hours(h)
    fig.add_trace(go.Bar(x=x, y=h['Plan'], name='Plan', marker_color=SLATE, opacity=.55), secondary_y=False)
    fig.add_trace(go.Bar(x=x, y=h['Output'], name='Output', marker_color=TEAL), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=h['Achv'] * 100, name='Achv %', mode='lines+markers', line=dict(color=AMBER, width=3), marker=dict(size=6)), secondary_y=True)
    fig.add_trace(go.Scatter(x=x, y=[S['Target_Pct'] * 100] * len(x), name='Target %', mode='lines', line=dict(color=CORAL, width=1.5, dash='dot')), secondary_y=True)
    fig.update_yaxes(range=[0, 140], showgrid=False, ticksuffix='%', secondary_y=True, fixedrange=True)
    return style_fig(fig, title)


def fig_cumulative(h, title='Cumulative Output vs Plan'):
    x = short_hours(h)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=h['Cum_Output'], name='Cum Output', marker_color=INDIGO))
    fig.add_trace(go.Scatter(x=x, y=h['Cum_Plan'], name='Cum Plan', mode='lines', line=dict(color=AMBER, width=3)))
    return style_fig(fig, title)


def fig_flow(h, title='Plan input, actual input, output and closing WIP'):
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    x = short_hours(h)
    if 'Plan_Input' in h:
        fig.add_trace(go.Bar(x=x, y=h['Plan_Input'], name='Plan input', marker_color=SLATE, opacity=.55), secondary_y=False)
    fig.add_trace(go.Bar(x=x, y=h['Input'], name='Input', marker_color=AMBER), secondary_y=False)
    fig.add_trace(go.Bar(x=x, y=h['Output'], name='Output', marker_color=TEAL), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=h['Closing_WIP'], name='Closing WIP', mode='lines+markers', line=dict(color=VIOLET, width=3)), secondary_y=True)
    fig.update_yaxes(showgrid=False, secondary_y=True, fixedrange=True)
    return style_fig(fig, title)


def fig_quality(h, S, second='Rewash_Pct', second_name='Rewash %', title='Defect % and Rewash % by hour'):
    x = short_hours(h)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=h['Defect_Pct'] * 100, name='Defect %', mode='lines+markers', line=dict(color=CORAL, width=3)))
    fig.add_trace(go.Scatter(x=x, y=h[second] * 100, name=second_name, mode='lines+markers', line=dict(color=AMBER, width=3)))
    fig.add_trace(go.Scatter(x=x, y=[S['Max_Defect_Pct'] * 100] * len(x), name='Defect limit', mode='lines', line=dict(color=CORAL, width=1, dash='dot')))
    fig.add_trace(go.Scatter(x=x, y=[S['Max_Rewash_Pct'] * 100] * len(x), name='Rewash limit', mode='lines', line=dict(color=AMBER, width=1, dash='dot')))
    fig.update_yaxes(ticksuffix='%', rangemode='tozero')
    return style_fig(fig, title)


def fig_downtime(h, title='Downtime by hour (machine-minutes)'):
    return style_fig(go.Figure(go.Bar(x=short_hours(h), y=h['Downtime_Min'], name='Downtime', marker_color=PINK)), title, legend=False)


def fig_heat(X, z, title, zmax=1.2, pct=True, height=None):
    fig = go.Figure(go.Heatmap(z=z.values, x=[calc.hour_labels(X.DAY_START)[int(c) - 1][:5] for c in z.columns], y=list(z.index),
                               colorscale=HEAT if pct else 'Viridis', zmin=0, zmax=zmax if pct else None, xgap=1, ygap=1,
                               colorbar=dict(tickformat='.0%' if pct else None, thickness=12)))
    fig.update_yaxes(autorange='reversed')
    return style_fig(fig, title, h=height or max(320, 17 * len(z) + 90), legend=False)


def fig_pareto(p, title):
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(x=p['Reason'], y=p['Minutes'], name='Minutes', marker_color=INDIGO), secondary_y=False)
    fig.add_trace(go.Scatter(x=p['Reason'], y=p['Cum_Share'] * 100, name='Cumulative %', mode='lines+markers', line=dict(color=AMBER, width=3)), secondary_y=True)
    fig.update_yaxes(range=[0, 105], ticksuffix='%', showgrid=False, secondary_y=True, fixedrange=True)
    return style_fig(fig, title)


def cap_kpis(X, c):
    """Wet / dry capacity of the selected plant (Unit_Master)."""
    r = X.caps[X.caps['Wash_Plant'] == X.unit]
    wet = float(r['Wet_Capacity_Day'].iloc[0]) if len(r) else np.nan
    dry = float(r['Dry_Capacity_Day'].iloc[0]) if len(r) else np.nan
    kpi(c[0], 'Wet process capacity / day', fi(wet), 'wash plant, all machines', 'info')
    kpi(c[1], 'Dry process capacity / day', fi(dry), 'plant total, no breakdown', 'info')
    return wet, dry


# ================================================================== HOURLY MONITOR
def hourly(X):
    S, K, H = X.S, X.K, hourly_tbl(X)
    pin_day, pin_src = H.attrs.get('plan_in_day', np.nan), H.attrs.get('plan_in_src', '')
    act = H[H['Hour_Idx'] <= X.until]
    plan_in_till = act['Plan_Input'].sum(min_count=1)
    c = st.columns(5)
    cap_kpis(X, c)
    kpi(c[2], 'Plan input (till hr)', fi(plan_in_till), f"Full day {fi(pin_day)} | {pin_src}", 'info')
    kpi(c[3], 'Actual input', fi(K['input']), f"Variation {fi(K['input'] - plan_in_till) if not pd.isna(plan_in_till) else '–'} pcs")
    ia = K['input'] / plan_in_till if plan_in_till and plan_in_till > 0 else np.nan
    kpi(c[4], 'Input achievement', fp(ia), '', tone_achv(ia, S))
    c = st.columns(5)
    kpi(c[0], 'Plan output', fi(K['plan']), f"Full day: {fi(X.plan_hr * X.RUN_H) if not X.filters_on else '–'} pcs")
    kpi(c[1], 'Actual output', fi(K['output']), f"Variance: {fi(K['var'])} pcs" if not pd.isna(K['var']) else 'Plan hidden')
    kpi(c[2], 'Output achievement', fp(K['achv']), f"Target {fp(S['Target_Pct'], 0)} | Alert < {fp(S['Alert_Pct'], 0)}", tone_achv(K['achv'], S))
    kpi(c[3], 'Closing WIP', fi(K['wip']), f"Opening: {fi(X.open_w)}")
    cover = K['wip'] / X.avg_out if X.avg_out and not pd.isna(K['wip']) else np.nan
    kpi(c[4], 'WIP cover (days)', ff(cover), f"vs last-7-day avg output {fi(X.avg_out)}/day")
    c = st.columns(5)
    kpi(c[0], 'Defect %', fp(K['defect_pct']), f"Limit {fp(S['Max_Defect_Pct'])} | Inspected {fi(K['inspected'])}", tone_limit(K['defect_pct'], S['Max_Defect_Pct']))
    kpi(c[1], 'Rewash %', fp(K['rewash_pct']), f"Limit {fp(S['Max_Rewash_Pct'])} | Rewash {fi(K['rewash'])} pcs", tone_limit(K['rewash_pct'], S['Max_Rewash_Pct']))
    kpi(c[2], 'Downtime (hrs)', ff(K['downtime_min'] / 60), f"{fi(K['downtime_min'])} machine-minutes")
    util = K['output'] / (X.std_hr * X.until) if X.std_hr and not X.filters_on else np.nan
    kpi(c[3], 'Capacity utilisation', fp(util), f"Std capacity till hr: {fi(X.std_hr * X.until)}")
    kpi(c[4], 'Machines running', fi(X.w_day[X.w_day['Output'] > 0]['Machine_ID'].nunique()), f"of {fi((X.mm[X.mm['Unit'] == X.unit]['Active'] != 'N').sum())} active")
    a, b = st.columns(2)
    with a:
        show(fig_plan_actual(H, S))
    with b:
        show(fig_cumulative(H))
    a, b = st.columns(2)
    with a:
        show(fig_flow(H))
    with b:
        show(fig_quality(H, S))
    a, b = st.columns(2)
    with a:
        show(fig_downtime(H))
    with b:
        mix = X.w_day.groupby('Wash_Type')['Output'].sum().reset_index()
        mix = mix[mix['Output'] > 0]
        fig = go.Figure(go.Pie(labels=mix['Wash_Type'].replace('', '(not set)'), values=mix['Output'], hole=0.55, marker=dict(colors=PALETTE), sort=False))
        show(style_fig(fig, 'Wash type mix (output)'))
    sec('Hourly table')
    ht = act.copy()
    ht['Achv %'] = ht['Achv'] * 100
    ht['Defect %'] = ht['Defect_Pct'] * 100
    ht['Rewash %'] = ht['Rewash_Pct'] * 100
    cols = ['Hour', 'Shift', 'Plan_Input', 'Input', 'Input_Var', 'Plan', 'Output', 'Var', 'Achv %', 'Cum_Plan', 'Cum_Output', 'Closing_WIP', 'QC_Inspected', 'Defect %', 'Rewash', 'Rewash %', 'Downtime_Min']
    ht = ht[cols]
    lab = {'Plan_Input': 'Plan input', 'Input': 'Actual input', 'Input_Var': 'Input var', 'Plan': 'Plan output', 'Output': 'Actual output', 'Var': 'Output var',
           'Cum_Plan': 'Cum plan', 'Cum_Output': 'Cum output', 'Closing_WIP': 'Closing WIP', 'QC_Inspected': 'QC inspected', 'Downtime_Min': 'Downtime (min)'}
    cfg = {c: (num_cfg(lab.get(c, c), '%.1f') if '%' in c else num_cfg(lab.get(c, c))) for c in cols if c not in ('Hour', 'Shift')}
    cfg['Achv %'] = pct_cfg('Achv %')
    table(ht, cfg, height=420)
    downloads(ht, f'hourly_{X.unit}_{X.day:%Y%m%d}', 'dl_hourly', 'Hourly')


# ================================================================== MACHINES
def machines(X):
    S = X.S
    MT = machine_tbl(X)
    act = MT[MT['Active'] != 'N']
    c = st.columns(5)
    kpi(c[0], 'Total machine capacity / day', fi(act['Cap_Day'].sum()), f"{fi(len(act))} active machines (standard rate x {X.RUN_H:g} h)", 'info')
    kpi(c[1], 'Capacity till selected hr', fi(act['Plan_per_hr'].sum() * X.until), f"Actual output {fi(MT['Output'].sum())}")
    kpi(c[2], 'On target', fi((MT['Status'] == 'On target').sum()), '', 'ok')
    kpi(c[3], 'Watch / Behind', f"{fi((MT['Status'] == 'Watch').sum())} / {fi((MT['Status'] == 'Behind').sum())}", '', 'warn')
    kpi(c[4], 'No data', fi((MT['Status'] == 'No data').sum()), 'nothing logged')
    f1, f2 = st.columns(2)
    types = sorted(MT['Type'].unique())
    ftype = f1.multiselect('Machine type', types, default=types)
    allst = ['Behind', 'Watch', 'On target', 'No data', '-']
    fstat = f2.multiselect('Status', allst, default=allst)
    V = MT[MT['Type'].isin(ftype) & MT['Status'].isin(fstat)].sort_values('Achv', na_position='last')
    sec('Machine-wise capacity, plan vs actual')
    V = V.assign(**{'Achv %': V['Achv'] * 100, 'Defect %': V['Defect_Pct'] * 100, 'Rewash %': V['Rewash_Pct'] * 100})
    cols = ['Machine_ID', 'Type', 'Cap_Day', 'Plan', 'Output', 'Var', 'Achv %', 'Input', 'Defect %', 'Rewash', 'Rewash %', 'Downtime_Min', 'Hours_Logged', 'Status']
    table(V[cols], {'Achv %': pct_cfg('Achv %'), 'Cap_Day': num_cfg('Capacity / day'), 'Plan': num_cfg('Plan (till hr)'), 'Output': num_cfg('Output'), 'Var': num_cfg('Var'),
                    'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f'), 'Downtime_Min': num_cfg('Downtime (min)'),
                    'Hours_Logged': num_cfg('Hours logged')}, height=430)
    downloads(V[cols], f'machines_{X.unit}_{X.day:%Y%m%d}', 'dl_mach', 'Machines')
    a, b = st.columns(2)
    with a:
        low = MT[(MT['Hours_Logged'] > 0) & MT['Achv'].notna()].sort_values('Achv').head(10)
        show(hbar(low.assign(v=low['Achv'] * 100), 'v', 'Machine_ID', '10 lowest-achieving machines (%)', colors=rag_colors(low['Achv'] * 100), fmt=lambda v: f'{v:.0f}%'))
    with b:
        top = MT.sort_values('Downtime_Min', ascending=False).head(10)
        top = top[top['Downtime_Min'] > 0]
        show(hbar(top, 'Downtime_Min', 'Machine_ID', '10 highest downtime machines (min)', color=PINK, fmt=lambda v: f'{v:.0f}'))
    sec('Machine x Hour heatmap')
    if X.filters_on:
        z = X.w_day[X.w_day['Hour_Idx'] <= X.until].pivot_table(index='Machine_ID', columns='Hour_Idx', values='Output', aggfunc='sum')
        show(fig_heat(X, z.reindex(columns=[x for x in calc.HOURS if x <= X.until]), 'Output pcs by machine and hour (filtered)', pct=False))
    else:
        show(fig_heat(X, calc.machine_heatmap(X.w_day, X.mm, X.unit, X.until, X.BASIS), 'Achievement % by machine and hour (red = behind, green = on target)'))


# ================================================================== DRY PROCESS
def dry(X):
    S = X.S
    DT = dry_tbl(X)
    r = X.caps[X.caps['Wash_Plant'] == X.unit]
    drycap = float(r['Dry_Capacity_Day'].iloc[0]) if len(r) else np.nan
    c = st.columns(5)
    kpi(c[0], 'DRY capacity / day (plant total)', fi(drycap), f"Sum of process capacity: {fi(DT['Capacity_per_day'].sum())} process-pcs", 'info')
    dplan, dout = DT['Plan'].sum(min_count=1), DT['Output'].sum()
    dach = dout / dplan if dplan and dplan > 0 else np.nan
    ddef = DT['Defect'].sum() / dout if dout > 0 else np.nan
    drew = DT['Rework'].sum() / dout if dout > 0 else np.nan
    crit = calc.critical_process(DT)
    kpi(c[1], 'Plan (process-pcs)', fi(dplan), 'a garment can pass several processes')
    kpi(c[2], 'Output (process-pcs)', fi(dout), f"Achievement {fp(dach)}", tone_achv(dach, S))
    kpi(c[3], 'Defect % | Rework %', f"{fp(ddef)} | {fp(drew)}", f"Limit {fp(S['Max_Defect_Pct'])} | {fp(S['Max_Rewash_Pct'])}", tone_limit(ddef, S['Max_Defect_Pct']))
    ok = crit is not None and not X.style_on
    kpi(c[4], 'Critical process', crit['Process'] if ok else '–', f"Achv {fp(crit['Achv'])} | loss {fi(crit['Loss_Pcs'])} pcs" if ok else '',
        'bad' if ok and crit['Achv'] < S['Alert_Pct'] else '')
    if DT.empty:
        st.info('No dry processes are defined for this plant in Master_Process.')
        return
    sec('Process-wise capacity, plan vs actual')
    P = DT.sort_values('Achv', na_position='last').assign(**{'Achv %': lambda x: x['Achv'] * 100, 'Defect %': lambda x: x['Defect_Pct'] * 100, 'Rework %': lambda x: x['Rework_Pct'] * 100})
    cols = ['Process', 'Machines', 'Capacity_per_day', 'Plan', 'Output', 'Var', 'Achv %', 'Input', 'WIP', 'Defect %', 'Rework %', 'Downtime_Min', 'Loss_Pcs', 'Status']
    table(P[cols], {'Achv %': pct_cfg('Achv %'), 'Capacity_per_day': num_cfg('Capacity / day'), 'Plan': num_cfg('Plan (till hr)'), 'Output': num_cfg('Output'),
                    'Var': num_cfg('Var'), 'WIP': num_cfg('WIP (pcs)'), 'Defect %': num_cfg('Defect %', '%.1f'), 'Rework %': num_cfg('Rework %', '%.1f'),
                    'Downtime_Min': num_cfg('Downtime (min)'), 'Loss_Pcs': num_cfg('Loss pcs')}, height=420)
    downloads(P[cols], f'dry_process_{X.unit}_{X.day:%Y%m%d}', 'dl_dry', 'Dry process')
    a, b = st.columns(2)
    with a:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=DT['Process'], y=DT['Plan'], name='Plan', marker_color=SLATE, opacity=.55))
        fig.add_trace(go.Bar(x=DT['Process'], y=DT['Output'], name='Output', marker_color=TEAL))
        fig.update_xaxes(tickangle=-35)
        show(style_fig(fig, 'Plan vs Output by process', h=380))
    with b:
        fig = go.Figure(go.Bar(x=DT['Process'], y=DT['WIP'], marker_color=VIOLET, name='WIP'))
        fig.update_xaxes(tickangle=-35)
        show(style_fig(fig, 'WIP by process (opening + input - output)', h=380, legend=False))
    sec('Process x Hour heatmap')
    if X.style_on:
        z = X.d_day[X.d_day['Hour_Idx'] <= X.until].pivot_table(index='Process', columns='Hour_Idx', values='Output', aggfunc='sum')
        show(fig_heat(X, z.reindex(columns=[x for x in calc.HOURS if x <= X.until]), 'Output pcs by process and hour (style filtered)', pct=False))
    else:
        show(fig_heat(X, calc.dry_heatmap(X.d_day, X.mp, X.unit, X.until, X.RUN_H, X.BASIS), 'Achievement % by process and hour'))
    sec('Process drill-down (hourly)')
    pick = st.selectbox('Process', list(DT['Process']), key='dry_pick')
    cap_day = float(X.mp[(X.mp['Unit'] == X.unit) & (X.mp['Process'] == pick)]['Capacity_per_day'].iloc[0])
    hp = calc.hourly_table(X.d_day[X.d_day['Process'] == pick], calc.DRY_NUM, cap_day / X.RUN_H * X.BASIS, X.until, calc.opening_wip(X.wip, X.unit, X.day, pick), X.DAY_START, with_plan=not X.style_on)
    a, b = st.columns(2)
    with a:
        show(fig_plan_actual(hp, S, f'{pick}: hourly plan vs output'))
    with b:
        show(fig_flow(hp, f'{pick}: input, output and WIP'))


# ================================================================== QUALITY & DOWNTIME
def quality(X):
    S, MT, DT = X.S, machine_tbl(X), dry_tbl(X)
    sec('Wash quality and rewash')
    a, b = st.columns(2)
    with a:
        g = X.w_day[X.w_day['Hour_Idx'] <= X.until].groupby('Wash_Type').agg(O=('Output', 'sum'), Q=('QC_Inspected', 'sum'), D=('Defect', 'sum'), R=('Rewash', 'sum')).reset_index()
        g['Defect %'] = calc.safe_div(g['D'], g['Q']) * 100
        g['Rewash %'] = calc.safe_div(g['R'], g['O']) * 100
        xs = g['Wash_Type'].replace('', '(not set)')
        fig = go.Figure()
        fig.add_trace(go.Bar(x=xs, y=g['Defect %'], name='Defect %', marker_color=CORAL))
        fig.add_trace(go.Bar(x=xs, y=g['Rewash %'], name='Rewash %', marker_color=AMBER))
        show(style_fig(fig, 'Defect % and Rewash % by wash type'))
    with b:
        mq = MT[MT['Output'] >= 100].sort_values('Rewash_Pct', ascending=False).head(10)
        show(hbar(mq.assign(v=mq['Rewash_Pct'] * 100), 'v', 'Machine_ID', 'Top 10 machines by Rewash % (min 100 pcs output)', color=AMBER, fmt=lambda v: f'{v:.1f}%'))
    sec('Style quality (selected date)')
    sd = calc.style_summary(X.w_day[X.w_day['Hour_Idx'] <= X.until], X.d_day[X.d_day['Hour_Idx'] <= X.until])
    if len(sd):
        sd = sd.assign(**{'Defect %': sd['Defect_Pct'] * 100, 'Rewash %': sd['Rewash_Pct'] * 100}).sort_values('Rewash %', ascending=False)
        table(sd[['Style', 'Output', 'Input', 'Defect %', 'Rewash %', 'Machines', 'Downtime_Min']],
              {'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f')}, height=280)
    else:
        st.caption('No style data for this selection.')
    sec('Dry process quality')
    dq = DT[DT['Output'] > 0]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=dq['Process'], y=dq['Defect_Pct'] * 100, name='Defect %', marker_color=CORAL))
    fig.add_trace(go.Bar(x=dq['Process'], y=dq['Rework_Pct'] * 100, name='Rework %', marker_color=AMBER))
    fig.update_xaxes(tickangle=-35)
    show(style_fig(fig, 'Dry process: defect % and rework % by process', h=360))
    sec('Downtime Pareto')
    a, b = st.columns(2)
    with a:
        show(fig_pareto(calc.pareto(X.w_day[X.w_day['Hour_Idx'] <= X.until]), 'Wash downtime by reason'))
    with b:
        show(fig_pareto(calc.pareto(X.d_day[X.d_day['Hour_Idx'] <= X.until]), 'Dry process downtime by reason'))


# ================================================================== DATA HEALTH
def health(X):
    MT, DT, H = machine_tbl(X), dry_tbl(X), hourly_tbl(X)
    w0 = X.w_day if not X.filters_on else calc.apply_filters(X.wash, unit=X.unit, date=X.day)
    d0 = X.d_day if not X.style_on else calc.apply_filters(X.dry, unit=X.unit, date=X.day)
    HC = calc.health_checks(w0, d0, X.mm, X.mp, X.unit, X.until, X.BASIS, X.D['rej_w'], X.D['rej_d'], X.RUN_H)
    c = st.columns(5)
    kpi(c[0], 'Wash coverage', fp(HC['wash_coverage'], 0), 'machine-hours logged / expected', 'ok' if (HC['wash_coverage'] or 0) >= 0.95 else 'warn')
    kpi(c[1], 'Dry coverage', fp(HC['dry_coverage'], 0), 'process-hours logged / expected', 'ok' if (HC['dry_coverage'] or 0) >= 0.95 else 'warn')
    nd = len(HC['dup_wash']) + len(HC['dup_dry'])
    ns = len(HC['suspicious_wash']) + len(HC['suspicious_dry'])
    nr = len(HC['rejected_wash']) + len(HC['rejected_dry'])
    kpi(c[2], 'Duplicate rows', fi(nd), '', 'bad' if nd else 'ok')
    kpi(c[3], 'Suspicious rows', fi(ns), 'output > 150% plan, defect > inspected ...', 'warn' if ns else 'ok')
    kpi(c[4], 'Rejected rows (all dates)', fi(nr), 'bad date / hour / ID', 'bad' if nr else 'ok')
    if HC['missing_hours']:
        st.warning('Hours with NO wash entries (up to the selected hour): ' + ', '.join(X.LABELS[h - 1][:5] for h in HC['missing_hours']))
    for title, df in [('Duplicate wash rows (same date, hour, machine)', HC['dup_wash']), ('Duplicate dry rows', HC['dup_dry']), ('Suspicious wash rows', HC['suspicious_wash']),
                      ('Suspicious dry rows', HC['suspicious_dry']), ('Rejected wash rows', HC['rejected_wash']), ('Rejected dry rows', HC['rejected_dry'])]:
        if len(df):
            sec(title)
            table(df.drop(columns=[c_ for c_ in ('Hour_Idx', 'Shift') if c_ in df.columns]).head(300), height=240)
    sec('Order master checks')
    O = X.D['order']
    if O.empty:
        st.warning('Order_Master is empty: buyer / CRD / crisis / sewing-unit views will be blank.')
    else:
        miss = []
        for col in ['Buyer', 'Sewing_Unit', 'Wash_Plant']:
            n = int((O[col].astype(str).str.strip() == '').sum())
            if n:
                miss.append(f'{n} order(s) with blank {col}')
        n = int(O['CRD'].isna().sum() + 0)
        if n:
            miss.append(f'{n} order(s) with no CRD')
        st.success('Order master looks complete.') if not miss else st.warning('; '.join(miss))
    sec('Export (selected date and plant)')
    e = st.columns(4)
    e[0].download_button('Hourly table (CSV)', H.to_csv(index=False).encode(), file_name=f'hourly_{X.unit}_{X.day:%Y%m%d}.csv', mime='text/csv')
    e[1].download_button('Machine table (CSV)', MT.to_csv(index=False).encode(), file_name=f'machines_{X.unit}_{X.day:%Y%m%d}.csv', mime='text/csv')
    e[2].download_button('Dry process table (CSV)', DT.to_csv(index=False).encode(), file_name=f'dry_{X.unit}_{X.day:%Y%m%d}.csv', mime='text/csv')
    e[3].download_button('Raw wash rows (CSV)', X.w_day.to_csv(index=False).encode(), file_name=f'wash_rows_{X.unit}_{X.day:%Y%m%d}.csv', mime='text/csv')


# ================================================================== STYLE EXPLORER
def _style_details_frame(X):
    def f():
        T = calc.style_details(X.wash, X.D['order'], X.unit, X.day, X.until, X.DAY_START, X.S['Output_Lag_Days'], X.D['plan'])
        if X.styles_active:
            T = T[T['Style'].isin(X.styles_active)]
        if X.wtypes:
            T = T[T['Wash_Type'].isin(X.wtypes)]
        return T
    return memo(X, 'T', f)


def style_view(X):
    S, wash, dry, unit, day, until = X.S, X.wash, X.dry, X.unit, X.day, X.until
    view = st.radio('View', ['Style summary', 'Style details'], horizontal=True, key='style_view', label_visibility='collapsed')
    if view == 'Style details':
        ORD = X.D['order']
        st.caption(f"Order-wise details for {unit}, cumulative till {day:%d %b %Y} hour {until}. Plan = Daily_Plan tab if the order has rows there, otherwise Order_Qty spread evenly "
                   f"over Plan_Start..Plan_End (output plan shifted {S['Output_Lag_Days']:.0f} day(s)).")
        if ORD.empty:
            st.info('No Order_Master data found, so Buyer, PO plan, CRD, Shade and Merchant columns stay blank.')
        T = _style_details_frame(X)
        f1, f2, f3, f4 = st.columns(4)
        pb = f1.multiselect('Buyer', sorted(x for x in T['Buyer'].unique() if x), default=[], key='det_buyer')
        pm = f2.multiselect('Merchant', sorted(x for x in T['Merchant'].unique() if x), default=[], key='det_mer')
        ps = f3.multiselect('Sewing unit', sorted(x for x in T['Sewing_Unit'].unique() if x), default=[], key='det_sew')
        hide0 = f4.checkbox('Hide orders with no plan and no input yet', value=True, key='det_hide')
        if pb:
            T = T[T['Buyer'].isin(pb)]
        if pm:
            T = T[T['Merchant'].isin(pm)]
        if ps:
            T = T[T['Sewing_Unit'].isin(ps)]
        if hide0:
            T = T[(T['Input'] > 0) | (T['Input_Plan'].fillna(0) > 0)]
        if T.empty:
            st.info('No orders match.')
            return
        c = st.columns(5)
        kpi(c[0], 'Orders (style / PO / colour)', fi(len(T)), f"{T['Style'].nunique()} styles")
        kpi(c[1], 'Actual input', fi(T['Input'].sum()), f"Plan {fi(T['Input_Plan'].sum(min_count=1))}")
        kpi(c[2], 'Actual output', fi(T['Output'].sum()), f"Plan {fi(T['Output_Plan'].sum(min_count=1))}")
        tot = T['Output'].sum() / T['Output_Plan'].sum() if T['Output_Plan'].sum() > 0 else np.nan
        kpi(c[3], 'Achievement %', fp(tot), '', tone_achv(tot, S))
        kpi(c[4], 'Total WIP (incl. rewash)', fi(T['Total_WIP'].sum()), f"Rewash WIP {fi(T['Rewash_WIP'].sum())}")
        LAB = dict(calc.DETAIL_COLS)
        V = T.copy()
        for dc in calc.DETAIL_DATES:
            V[dc] = V[dc].dt.strftime('%d-%b-%y')
        cols_ = [c_ for c_, _ in calc.DETAIL_COLS]
        cfg = {}
        for c_ in cols_:
            lab = LAB[c_]
            if c_ in ('Wash_Plant', 'Buyer', 'Style', 'PO', 'Color', 'Wash_Type', 'Machines', 'Sewing_Unit', 'Merchant') or c_ in calc.DETAIL_DATES:
                try:
                    cfg[c_] = st.column_config.TextColumn(lab, pinned=c_ in ('Style', 'PO', 'Color'))
                except TypeError:
                    cfg[c_] = st.column_config.TextColumn(lab)
            elif c_ == 'Achv_Pct':
                cfg[c_] = st.column_config.ProgressColumn(lab, format='%.1f', min_value=0, max_value=150)
            elif c_ in ('Rewash_Pct', 'DHU', 'Reject_Pct', 'Hold_First', 'Hold_Last', 'Approval_Days'):
                cfg[c_] = st.column_config.NumberColumn(lab, format='%.1f')
            else:
                cfg[c_] = st.column_config.NumberColumn(lab, format='%d')
        sec('Style details')
        table(V[cols_], cfg, height=560)
        dl = T.copy()
        dl['Machines'] = dl['Machines_Full']
        dl = dl[cols_].rename(columns={**LAB, 'Input_Var': 'Variation (Input)', 'Output_Var': 'Variation (Output)'})
        nm = f'style_details_{unit}_{day:%Y%m%d}'
        c1, c2, _ = st.columns([1, 1, 4])
        c1.download_button('⬇ CSV', dl.to_csv(index=False).encode('utf-8-sig'), file_name=nm + '.csv', mime='text/csv', key='dl_sd_csv')
        c2.download_button('⬇ Excel', xlsx_of({'Style details': dl.assign(**{c: dl[c].dt.strftime('%Y-%m-%d') for c in dl.columns if pd.api.types.is_datetime64_any_dtype(dl[c])})}),
                           file_name=nm + '.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='dl_sd_xls')
        sec('Daily tracking (day-by-day ledger)')
        st.caption('Pick an order to see every day: plan, actual, opening WIP + todays input = available, closing WIP. Opening WIP carries into the next day / month automatically.')
        lab_of = {(r.Style, r.PO, r.Color): f"{r.Style} | {r.PO} | {r.Color}" for r in T.itertuples()}
        picks = st.multiselect('Order(s) (Style | PO | Color)', list(lab_of.values()), default=list(lab_of.values())[:1], key='ledger_pick')
        if picks:
            keys_ = [k for k, v in lab_of.items() if v in picks]
            DPL = X.dp
            pri = T[T.set_index(calc.KEYS).index.isin(keys_)] if keys_ else T.iloc[0:0]
            LG = calc.style_ledger(wash, DPL, unit, keys_, day, until, float(pri['Prior_Input'].sum()), float(pri['Prior_Output'].sum()))
            if LG.empty:
                st.info('No plan or actual rows for this selection up to the selected date.')
            else:
                last_ = LG.iloc[-1]
                ca = last_['Cum_Achv_Pct'] / 100 if pd.notna(last_['Cum_Achv_Pct']) else np.nan
                c = st.columns(5)
                kpi(c[0], 'Cum input', fi(last_['Cum_Input']), f"Plan {fi(last_['Cum_Input_Plan'])} | Var {fi(last_['Cum_Input_Var'])}")
                kpi(c[1], 'Cum output', fi(last_['Cum_Output']), f"Plan {fi(last_['Cum_Output_Plan'])} | Var {fi(last_['Cum_Output_Var'])}")
                kpi(c[2], 'Cum achievement %', fp(ca), '', tone_achv(ca, S))
                kpi(c[3], 'Closing WIP', fi(last_['Closing_WIP']), f"Opening today {fi(last_['Opening_WIP'])}")
                kpi(c[4], 'Total WIP (incl. rewash)', fi(last_['Total_WIP']), f"Rewash WIP {fi(last_['Rewash_WIP'])}")
                fig = make_subplots(specs=[[{'secondary_y': True}]])
                fig.add_trace(go.Bar(x=LG['Date'], y=LG['Plan_Output'], name='Output plan', marker_color=SLATE, opacity=.55), secondary_y=False)
                fig.add_trace(go.Bar(x=LG['Date'], y=LG['Output'], name='Actual output', marker_color=TEAL), secondary_y=False)
                fig.add_trace(go.Scatter(x=LG['Date'], y=LG['Input'], name='Actual input', mode='lines', line=dict(color=AMBER, width=3)), secondary_y=False)
                fig.add_trace(go.Scatter(x=LG['Date'], y=LG['Closing_WIP'], name='Closing WIP', mode='lines+markers', line=dict(color=VIOLET, width=3)), secondary_y=True)
                fig.update_yaxes(showgrid=False, secondary_y=True, fixedrange=True)
                show(style_fig(fig, 'Daily plan vs actual and closing WIP', h=360))
                LGd = LG.assign(Date=LG['Date'].dt.strftime('%d-%b-%y'))
                lcols = ['Date', 'Event', 'Opening_WIP', 'Plan_Input', 'Input', 'Input_Var', 'Available_Input', 'Plan_Output', 'Output', 'Output_Var', 'Achv_Pct', 'Closing_WIP',
                         'Cum_Input_Plan', 'Cum_Input', 'Cum_Output_Plan', 'Cum_Output', 'Cum_Achv_Pct', 'Rewash', 'Rewash_Output', 'Rewash_WIP', 'Total_WIP', 'Reject']
                llab = {'Opening_WIP': 'Opening WIP', 'Plan_Input': 'Input plan', 'Input': 'Actual input', 'Input_Var': 'Input var', 'Available_Input': 'Available input (Opening + todays input)',
                        'Plan_Output': 'Output plan', 'Output': 'Actual output', 'Output_Var': 'Output var', 'Achv_Pct': 'Achv %', 'Closing_WIP': 'Closing WIP',
                        'Cum_Input_Plan': 'Cum input plan', 'Cum_Input': 'Cum input', 'Cum_Output_Plan': 'Cum output plan', 'Cum_Output': 'Cum output', 'Cum_Achv_Pct': 'Cum achv %',
                        'Rewash': 'Rewash in', 'Rewash_Output': 'Rewash out', 'Rewash_WIP': 'Rewash WIP', 'Total_WIP': 'Total WIP', 'Reject': 'Reject'}
                lcfg = {c_: st.column_config.NumberColumn(llab.get(c_, c_), format='%.0f' if 'Pct' not in c_ else '%.1f') for c_ in lcols if c_ not in ('Date', 'Event')}
                lcfg['Date'] = st.column_config.TextColumn('Date')
                lcfg['Event'] = st.column_config.TextColumn('Event')
                table(LGd[lcols], lcfg, height=480)
                lg_out = LGd[lcols].rename(columns=llab)
                c1, c2, _ = st.columns([1, 1, 4])
                c1.download_button('⬇ CSV', lg_out.to_csv(index=False).encode('utf-8-sig'), file_name=f'daily_ledger_{unit}_{day:%Y%m%d}.csv', mime='text/csv', key='dl_lg_csv')
                c2.download_button('⬇ Excel', xlsx_of({'Daily ledger': lg_out}), file_name=f'daily_ledger_{unit}_{day:%Y%m%d}.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='dl_lg_xls')
                sec('Month-wise summary (opening WIP carried forward)')
                LM = calc.ledger_months(LG)
                table(LM[['Month', 'Days', 'Opening_WIP', 'Plan_Input', 'Input', 'Input_Var', 'Plan_Output', 'Output', 'Output_Var', 'Achv_Pct', 'Closing_WIP', 'Rewash', 'Rewash_Output', 'Reject']],
                      {c_: st.column_config.NumberColumn(c_.replace('_', ' '), format='%.0f' if c_ != 'Achv_Pct' else '%.1f') for c_ in LM.columns if c_ != 'Month'})
        with st.expander('How each column is calculated'):
            st.markdown("""
- **Plan till today**: Daily_Plan rows if present, else Order_Qty straight-line over Plan_Start..Plan_End; output plan shifted by Output_Lag_Days.
- **Variation** = Actual - Plan. **Achievement %** = Actual Output / Output Plan. **WIP** = Input - Output. **Total WIP** = WIP + Rewash WIP.
- **Prior_Input / Prior_Output** (Order_Master) = pcs processed before logging started; they are included in Actual Input / Output.
- **Rewash %** = Rewash Input / Output. **DHU %** = defect pcs / QC inspected x 100. **Rejection %** = Rejection / Input.
- **Balance** = Order_Qty - Output (short by less than 2% counts as delivered). Holding times come from the hourly log.
""")
        return
    first, last = X.first, X.last
    st.caption('Cross-date style analysis for this plant. Use the Style search in the sidebar to narrow the list.')
    lo = max(first, last - dt.timedelta(days=13))
    rng = st.date_input('Date range', value=(lo, last), min_value=first, max_value=last, key='style_range')
    r0, r1 = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else ((rng[0],) * 2 if isinstance(rng, (tuple, list)) else (rng, rng))
    ws_ = calc.apply_filters(wash, unit=unit, d0=r0, d1=r1, styles=X.styles_active)
    ds_ = calc.apply_filters(dry, unit=unit, d0=r0, d1=r1, styles=X.styles_active)
    SS = calc.style_summary(ws_, ds_)
    if SS.empty:
        st.info('No style data in this range.')
        return
    c = st.columns(4)
    kpi(c[0], 'Styles in range', fi(len(SS)), f"{r0:%d %b} - {r1:%d %b}")
    kpi(c[1], 'Wash output', fi(SS['Output'].sum()), 'pcs')
    tr = SS.dropna(subset=['Rewash_Pct']).sort_values('Rewash_Pct', ascending=False)
    kpi(c[2], 'Highest rewash %', tr.iloc[0]['Style'] if len(tr) else '–', fp(tr.iloc[0]['Rewash_Pct']) if len(tr) else '', 'bad' if len(tr) and tr.iloc[0]['Rewash_Pct'] > S['Max_Rewash_Pct'] else '')
    td = SS.dropna(subset=['Defect_Pct']).sort_values('Defect_Pct', ascending=False)
    kpi(c[3], 'Highest defect %', td.iloc[0]['Style'] if len(td) else '–', fp(td.iloc[0]['Defect_Pct']) if len(td) else '', 'bad' if len(td) and td.iloc[0]['Defect_Pct'] > S['Max_Defect_Pct'] else '')
    sec('Style summary')
    SSd = SS.assign(**{'Defect %': SS['Defect_Pct'] * 100, 'Rewash %': SS['Rewash_Pct'] * 100, 'Dry Defect %': SS['Dry_Defect_Pct'] * 100, 'Dry Rework %': SS['Dry_Rework_Pct'] * 100})
    cols = ['Style', 'Output', 'Input', 'Defect %', 'Rewash %', 'Machines', 'Days', 'Downtime_Min', 'Dry_Output', 'Dry Defect %', 'Dry Rework %']
    table(SSd[cols], {'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f'), 'Dry Defect %': num_cfg('Dry Defect %', '%.1f'),
                      'Dry Rework %': num_cfg('Dry Rework %', '%.1f'), 'Dry_Output': num_cfg('Dry output (process-pcs)'), 'Downtime_Min': num_cfg('Downtime (min)')}, height=300)
    downloads(SSd[cols], f'style_summary_{unit}', 'dl_ss', 'Style summary')
    pick = st.selectbox('Drill into a style', list(SS['Style']), key='style_pick')
    wsel, dsel = ws_[ws_['Style'] == pick], ds_[ds_['Style'] == pick]
    sec(f'Style detail: {pick}')
    a, b = st.columns(2)
    with a:
        gd = wsel.groupby('Date').agg(Output=('Output', 'sum'), Q=('QC_Inspected', 'sum'), D=('Defect', 'sum'), R=('Rewash', 'sum')).reset_index()
        fig = make_subplots(specs=[[{'secondary_y': True}]])
        fig.add_trace(go.Bar(x=gd['Date'], y=gd['Output'], name='Output', marker_color=TEAL), secondary_y=False)
        fig.add_trace(go.Scatter(x=gd['Date'], y=calc.safe_div(gd['D'], gd['Q']) * 100, name='Defect %', mode='lines+markers', line=dict(color=CORAL, width=3)), secondary_y=True)
        fig.add_trace(go.Scatter(x=gd['Date'], y=calc.safe_div(gd['R'], gd['Output']) * 100, name='Rewash %', mode='lines+markers', line=dict(color=AMBER, width=3)), secondary_y=True)
        fig.update_yaxes(ticksuffix='%', showgrid=False, rangemode='tozero', secondary_y=True, fixedrange=True)
        show(style_fig(fig, 'Daily wash output with defect % and rewash %'))
    with b:
        gh = wsel.groupby('Hour_Idx')['Output'].sum().reindex(calc.HOURS).fillna(0)
        show(style_fig(go.Figure(go.Bar(x=[l[:5] for l in X.LABELS], y=gh.values, marker_color=INDIGO, name='Output')), 'Output by hour of day', legend=False))
    a, b = st.columns(2)
    with a:
        gm = wsel.groupby('Machine_ID').agg(Output=('Output', 'sum')).reset_index().sort_values('Output', ascending=False).head(12)
        show(hbar(gm, 'Output', 'Machine_ID', 'Top machines for this style (output)', color=TEAL, fmt=lambda v: f'{v:,.0f}'))
    with b:
        gp = dsel.groupby('Process')['Output'].sum().sort_values(ascending=False).reset_index()
        fig = go.Figure(go.Bar(x=gp['Process'], y=gp['Output'], marker_color=AMBER, name='Output'))
        fig.update_xaxes(tickangle=-35)
        show(style_fig(fig, 'Dry process output for this style', legend=False))


# ================================================================== TRENDS
def trends(X):
    S, unit, wip = X.S, X.unit, X.wip
    first, last = X.first, X.last
    st.caption('Plant-level trend across dates (style and wash-type filters are not applied here).')
    rng = st.date_input('Trend range', value=(first, last), min_value=first, max_value=last, key='trend_range')
    t0, t1 = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (first, last)
    DY = calc.wash_daily(X.wash, X.mm, unit, t0, t1, X.BASIS)
    if DY.empty:
        st.info('No data in this range.')
        return
    tot_o, tot_p = DY['Output'].sum(), DY['Plan'].sum()
    ach = tot_o / tot_p if tot_p else np.nan
    c = st.columns(5)
    kpi(c[0], 'Days with data', fi(len(DY)), f"{t0:%d %b} - {t1:%d %b}")
    kpi(c[1], 'Total output', fi(tot_o))
    kpi(c[2], 'Achievement %', fp(ach), '', tone_achv(ach, S))
    kpi(c[3], 'Defect %', fp(DY['Defect'].sum() / DY['QC_Inspected'].sum() if DY['QC_Inspected'].sum() else np.nan))
    kpi(c[4], 'Rewash %', fp(DY['Rewash'].sum() / tot_o if tot_o else np.nan))
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(x=DY['Date'], y=DY['Output'], name='Output', marker_color=TEAL), secondary_y=False)
    fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Plan'], name='Plan', mode='lines', line=dict(color=INDIGO, width=3)), secondary_y=False)
    fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Achv'] * 100, name='Achv %', mode='lines+markers', line=dict(color=AMBER, width=3)), secondary_y=True)
    fig.update_yaxes(ticksuffix='%', showgrid=False, rangemode='tozero', secondary_y=True, fixedrange=True)
    show(style_fig(fig, 'Daily wash output vs plan', h=360))
    a, b = st.columns(2)
    with a:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Defect_Pct'] * 100, name='Defect %', mode='lines+markers', line=dict(color=CORAL, width=3)))
        fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Rewash_Pct'] * 100, name='Rewash %', mode='lines+markers', line=dict(color=AMBER, width=3)))
        fig.update_yaxes(ticksuffix='%', rangemode='tozero')
        show(style_fig(fig, 'Daily defect % and rewash %'))
    with b:
        pdl = calc.plant_daily(X.wash, wip, unit, t0, t1)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pdl['Date'], y=pdl['Closing_WIP'], mode='lines+markers', fill='tozeroy', line=dict(color=VIOLET, width=3), name='Closing WIP'))
        show(style_fig(fig, 'Day-end WASH WIP (opening + input - output)', legend=False))
    sec('Monthly summary')
    MO = calc.monthly(DY)
    MOd = MO.assign(**{'Achv %': MO['Achv'] * 100, 'Defect %': MO['Defect_Pct'] * 100, 'Rewash %': MO['Rewash_Pct'] * 100})
    table(MOd[['Month', 'Days', 'Plan', 'Output', 'Achv %', 'Input', 'Defect %', 'Rewash %', 'Downtime_Min']],
          {'Achv %': pct_cfg('Achv %'), 'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f'), 'Plan': num_cfg('Plan'), 'Output': num_cfg('Output'),
           'Input': num_cfg('Input'), 'Downtime_Min': num_cfg('Downtime (min)')})
    sec('Dry process achievement by day')
    DD = calc.dry_daily(X.dry, X.mp, unit, t0, t1, X.RUN_H, X.BASIS)
    if len(DD):
        z = DD.pivot_table(index='Process', columns='Date', values='Achv', aggfunc='mean')
        fig = go.Figure(go.Heatmap(z=z.values, x=[d.strftime('%d %b') for d in z.columns], y=list(z.index), colorscale=HEAT, zmin=0, zmax=1.2, xgap=1, ygap=1,
                                   colorbar=dict(tickformat='.0%', thickness=12)))
        fig.update_yaxes(autorange='reversed')
        show(style_fig(fig, 'Process x Day achievement %', h=max(340, 22 * len(z) + 100), legend=False))
    downloads(DY, f'daily_trend_{unit}', 'dl_trend', 'Daily trend')
