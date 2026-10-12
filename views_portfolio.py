"""Portfolio views across all wash plants: overview, CRD crisis, capacity justification, reports."""
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import calc
import reports
from ui import *



def _opts(S, col):
    return sorted(x for x in S[col].dropna().astype(str).unique() if x and x != 'nan')


def filters(X, key, crd=True, expand=True, S=None):
    """Sidebar CRD / Buyer / Sewing-unit selection is applied first; this bar only adds the wash-plant picker and the open-orders switch."""
    S = X.S_all if S is None else S
    if S.empty:
        return S, [], 0
    F = apply_side(S, getattr(X, 'sf', None), X.day)
    if not getattr(X, 'overall', True):
        F = F[F['Wash_Plant'] == X.unit]
    c = st.columns([2, 2])
    opts = sorted(set(_opts(F, 'Wash_Plant')))
    cur = [v for v in st.session_state.get(f'{key}_pl', []) if v in opts]
    pl = c[0].multiselect('Wash plant', opts, default=cur, key=f'{key}_pl', placeholder='All plants')
    if pl:
        F = F[F['Wash_Plant'].isin(pl)]
    only_open = c[1].checkbox('Only orders with balance still to deliver', value=False, key=f'{key}_open')
    if only_open:
        F = F[F['Balance'] > 0]
    sf = getattr(X, 'sf', None) or {}
    if sf.get('sw') and not pl:
        feeders = sorted(set(S[S['Sewing_Unit'].isin(sf['sw'])]['Wash_Plant']))
        note('Selected sewing unit(s) are washed in: ' + ', '.join(feeders))
    return F, pl, len(F)


def _plant_caps(X, plants):
    cp = X.caps[X.caps['Wash_Plant'].isin(plants)] if plants else X.caps
    return cp


def _fmt_group(g, first_cols):
    cols = first_cols + [c for c in reports.GROUP_VIEW if c in g.columns]
    return g[[c for c in cols if c in g.columns]]


def _show_group(g, name, key, labels=None):
    if g.empty:
        st.info('No data for this selection.')
        return
    cfg = auto_cfg(g)
    if 'Achv_Pct' in g:
        cfg['Achv_Pct'] = pct_cfg('Achievement (%)', 130)
    table(g, cfg, height=min(520, 60 + 35 * len(g)))
    downloads(g, name, key, 'Data')


# ================================================================== OVERVIEW
def overview(X):
    S = X.S
    if X.S_all.empty:
        st.warning('No orders found. Fill the Order_Master tab (Wash_Plant, Buyer, Style, PO, Color, CRD, Order_Qty ...).')
        return
    F, pl, n = filters(X, 'ov')
    if F.empty:
        st.info('No orders match these filters.')
        return
    plants_sel = pl or list(X.units)
    caps = _plant_caps(X, sorted(set(F['Wash_Plant'])))
    wet, dryc = caps['Wet_Capacity_Day'].sum(), caps['Dry_Capacity_Day'].sum(min_count=1)
    G = calc.group_summary(F, ['Wash_Plant'])
    T = G[['Input_Plan', 'Input', 'Output_Plan', 'Output', 'Total_WIP', 'Balance', 'Order_Qty', 'Crisis_Orders', 'Crisis_Pcs', 'Rewash_WIP']].sum()
    ia = T['Input'] / T['Input_Plan'] if T['Input_Plan'] else np.nan
    oa = T['Output'] / T['Output_Plan'] if T['Output_Plan'] else np.nan
    lab = ', '.join(sorted(set(F['Wash_Plant']))) if len(set(F['Wash_Plant'])) <= 4 else f"{F['Wash_Plant'].nunique()} plants"
    c = st.columns(5)
    kpi(c[0], 'Wet process capacity / day', fi(wet), lab, 'info')
    kpi(c[1], 'Dry process capacity / day', fi(dryc), lab, 'info')
    kpi(c[2], 'Orders in view', fi(len(F)), f"{F['Style'].nunique()} styles | qty {fi(T['Order_Qty'])}")
    kpi(c[3], 'Crisis orders (CRD <= 7 d)', fi(T['Crisis_Orders']), f"{fi(T['Crisis_Pcs'])} pcs still to deliver", 'bad' if T['Crisis_Orders'] else 'ok')
    kpi(c[4], 'Total WIP', fi(T['Total_WIP']), f"incl. rewash WIP {fi(T['Rewash_WIP'])}", 'warn')
    c = st.columns(5)
    kpi(c[0], 'Plan input (till today)', fi(T['Input_Plan']), 'from Daily_Plan / Order plan', 'info')
    kpi(c[1], 'Actual input', fi(T['Input']), f"Variation {fi(T['Input'] - T['Input_Plan'])}")
    kpi(c[2], 'Input achievement', fp(ia), '', tone_achv(ia, S_(X)))
    kpi(c[3], 'Plan output (till today)', fi(T['Output_Plan']), '', 'info')
    kpi(c[4], 'Actual output', fi(T['Output']), f"Achv {fp(oa)} | var {fi(T['Output'] - T['Output_Plan'])}", tone_achv(oa, S_(X)))
    a, b = st.columns(2)
    with a:
        g = G.sort_values('Wash_Plant')
        show(bar_plan_actual(g['Wash_Plant'], g['Output_Plan'], g['Output'], 'Output: plan vs actual by wash plant', plan_name='Plan output', act_name='Actual output'))
    with b:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=g['Wash_Plant'], y=g['WIP'], name='WIP', marker_color=INDIGO))
        fig.add_trace(go.Bar(x=g['Wash_Plant'], y=g['Rewash_WIP'], name='Rewash WIP', marker_color=PINK))
        show(style_fig(fig, 'WIP by wash plant (stacked)', grouped=False))
    a, b = st.columns(2)
    with a:
        gb = calc.group_summary(F, ['Buyer']).head(12)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=gb['Buyer'], y=gb['Total_WIP'], name='Total WIP', marker_color=VIOLET))
        fig.add_trace(go.Bar(x=gb['Buyer'], y=gb['Balance'], name='Balance to deliver', marker_color=AMBER))
        show(style_fig(fig, 'Buyer-wise WIP and balance (top 12 by WIP)'))
    with b:
        cs = calc.crd_summary(F, X.day, 'week')
        if len(cs):
            fig = go.Figure(go.Bar(x=cs['CRD_Group'], y=cs['Balance'], marker_color=[CORAL if d < 0 else (AMBER if d <= 7 else TEAL) for d in cs['Days_to_CRD']], name='Balance'))
            show(style_fig(fig, 'Balance to deliver by CRD week (red overdue, amber next 7 days)', legend=False))
    sec('Overview tables (every table is downloadable)')
    view = st.radio('Overview by', ['Overall', 'Wash plant', 'Sewing unit', 'Buyer', 'CRD', 'Orders'], horizontal=True, key='ov_view', label_visibility='collapsed')
    nm = f'overview_{view.lower().replace(" ", "_")}_{X.day:%Y%m%d}'
    if view == 'Overall':
        F2 = F.assign(All='All selected plants')
        g = _fmt_group(calc.group_summary(F2, ['All']), [])
        _show_group(g, nm, 'ov_all')
    elif view == 'Wash plant':
        g = calc.group_summary(F, ['Wash_Plant']).merge(X.caps[['Wash_Plant', 'Wet_Capacity_Day', 'Dry_Capacity_Day']], on='Wash_Plant', how='left')
        g = g[['Wash_Plant', 'Wet_Capacity_Day', 'Dry_Capacity_Day'] + [c for c in reports.GROUP_VIEW if c in g.columns]].sort_values('Wash_Plant')
        _show_group(g, nm, 'ov_pl')
    elif view == 'Sewing unit':
        g = _fmt_group(calc.group_summary(F, ['Sewing_Unit']), ['Sewing_Unit'])
        feed = F.groupby('Sewing_Unit')['Wash_Plant'].agg(lambda s: ', '.join(sorted(set(s)))).rename('Washed_In').reset_index()
        g = g.merge(feed, on='Sewing_Unit', how='left')
        g.insert(1, 'Washed_In', g.pop('Washed_In'))
        _show_group(g.rename(columns={'Washed_In': 'Washed_In'}), nm, 'ov_sw')
        sec('Sewing unit x wash plant (plan vs given)')
        g2 = _fmt_group(calc.group_summary(F, ['Sewing_Unit', 'Wash_Plant']), ['Sewing_Unit', 'Wash_Plant'])
        _show_group(g2, nm + '_by_plant', 'ov_sw2')
    elif view == 'Buyer':
        _show_group(_fmt_group(calc.group_summary(F, ['Buyer']), ['Buyer']), nm, 'ov_by')
    elif view == 'CRD':
        fr = st.radio('Group CRD by', ['date', 'week'], horizontal=True, key='ov_crdf')
        g = calc.crd_summary(F, X.day, fr)
        g = g[['CRD_Group', 'Days_to_CRD', 'Status'] + [c for c in reports.GROUP_VIEW if c in g.columns and c != 'Next_CRD']]
        _show_group(g, nm, 'ov_crd')
    else:
        g = reports.cols(F.sort_values(['Wash_Plant', 'Eff_CRD']), reports.ORDER_VIEW)
        _show_group(g, nm, 'ov_ord')
    sec('Download the whole overview as one Excel workbook')
    pack = {'Overall': _fmt_group(calc.group_summary(F.assign(All='All selected'), ['All']), []),
            'Wash plant': _fmt_group(calc.group_summary(F, ['Wash_Plant']), ['Wash_Plant']),
            'Sewing unit': _fmt_group(calc.group_summary(F, ['Sewing_Unit']), ['Sewing_Unit']),
            'Buyer': _fmt_group(calc.group_summary(F, ['Buyer']), ['Buyer']),
            'CRD': _fmt_group(calc.crd_summary(F, X.day, 'date').rename(columns={}), ['CRD_Group', 'Days_to_CRD', 'Status']),
            'Orders': reports.cols(F, reports.ORDER_VIEW)}
    st.download_button('⬇ Overview pack (Excel, all views)', xlsx_of(pack), file_name=f'overview_pack_{X.day:%Y%m%d}.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='dl_ov_pack')


def S_(X):
    return X.S


# ================================================================== CRD CRISIS
def crisis(X):
    S = X.S
    if X.S_all.empty:
        st.warning('No order data.')
        return
    hz = st.slider('Crisis horizon (days from selected date): orders with balance still to deliver and CRD within', 1, 21, 7, key='cr_h')
    F, pl, n = filters(X, 'cr', crd=False)
    C = calc.crisis_table(F, hz)
    if len(C) and 'Overrun_Days' in C.columns:
        import board
        C['Flags'] = board.red_flags(C)
    if C.empty:
        st.success(f'No crisis: every open order in this selection has CRD later than {hz} days or is delivered.')
        return
    c = st.columns(5)
    kpi(c[0], 'Crisis orders', fi(len(C)), f"{C['Buyer'].nunique()} buyers | {C['Wash_Plant'].nunique()} plants", 'bad')
    kpi(c[1], 'Balance to deliver', fi(C['Balance'].sum()), 'pcs', 'bad')
    kpi(c[2], 'Overdue', fi((C['Risk'] == 'Overdue').sum()), f"{fi(C.loc[C['Risk'] == 'Overdue', 'Balance'].sum())} pcs", 'bad')
    kpi(c[3], 'Critical | Plan overrun', f"{fi((C['Risk'] == 'Critical').sum())} | {fi((C['Risk'] == 'Overrun').sum())}", 'critical: <= 3 days or too slow; overrun: plan end passed, CRD later', 'warn')
    kpi(c[4], 'WIP already inside wash', fi(C['Total_WIP'].sum()), f"Not yet received: {fi(C['Pending_Input'].sum())}", 'info')
    a, b = st.columns(2)
    with a:
        gb = C.groupby(['Buyer', 'Risk'])['Balance'].sum().reset_index()
        fig = go.Figure()
        for rk in ['Overdue', 'Critical', 'Watch', 'Overrun']:
            d = gb[gb['Risk'] == rk]
            fig.add_trace(go.Bar(x=d['Buyer'], y=d['Balance'], name=rk, marker_color=RISK_COL.get(rk, VIOLET)))
        show(style_fig(fig, 'Balance to deliver by buyer and risk', grouped=False))
    with b:
        gp = C.groupby(['Wash_Plant', 'Risk'])['Balance'].sum().reset_index()
        fig = go.Figure()
        for rk in ['Overdue', 'Critical', 'Watch', 'Overrun']:
            d = gp[gp['Risk'] == rk]
            fig.add_trace(go.Bar(x=d['Wash_Plant'], y=d['Balance'], name=rk, marker_color=RISK_COL.get(rk, VIOLET)))
        show(style_fig(fig, 'Balance to deliver by wash plant and risk', grouped=False))
    gd = C.groupby('Days_to_CRD')['Balance'].sum().reset_index()
    fig = go.Figure(go.Bar(x=gd['Days_to_CRD'].map(lambda d: f'{d:+d} d'), y=gd['Balance'], marker_color=[RISK_COL['Overdue'] if d < 0 else (RISK_COL['Critical'] if d <= 3 else RISK_COL['Watch']) for d in gd['Days_to_CRD']], name='Balance'))
    show(style_fig(fig, 'Balance to deliver by days left to CRD', h=280, legend=False))
    sec('Crisis orders (most urgent first)')
    V = reports.cols(C, reports.CRISIS_VIEW)
    cfg = auto_cfg(V)
    table(V, cfg, height=min(560, 60 + 35 * len(V)))
    downloads(V, f'crd_crisis_{X.day:%Y%m%d}', 'dl_cr', 'CRD crisis')
    sec('Buyer-wise crisis')
    B = reports.buyer_crisis(C)
    table(B, auto_cfg(B), height=min(420, 60 + 35 * len(B)))
    downloads(B, f'buyer_crisis_{X.day:%Y%m%d}', 'dl_crb', 'Buyer crisis')
    note('Risk: Overrun = plan end date passed with balance still open although CRD is later (possible crisis); Overdue = CRD passed; Critical = 3 days or less, or the last-3-day output rate cannot clear the balance before CRD; Watch = the rest. '
         'Where stuck: In wash = WIP is at least half of the balance; Not yet received = input still pending.')


# ================================================================== CAPACITY JUSTIFICATION
def capacity(X):
    S, unit = X.S, X.unit
    st.caption('Capacity justification: capacity of each machine / process per day, plan allotted to it, actual output, utilisation and downtime. '
               'Allotted plan comes from the Allotment tab when filled; otherwise it is derived from the hours the resource ran a style.')
    c1, c2, c3 = st.columns([1.2, 1, 2])
    kind = c1.radio('Resource', ['Machine-wise', 'Process-wise'], horizontal=True, key='cap_kind')
    per = c2.radio('Period', ['Day-wise', 'Month-wise'], horizontal=True, key='cap_per')
    lo = max(X.first, X.last - dt.timedelta(days=29))
    rng = c3.date_input('Date range', value=(lo, X.last), min_value=X.first, max_value=X.last, key='cap_range')
    d0, d1 = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (lo, X.last)
    if kind == 'Machine-wise':
        m = X.mm[(X.mm['Unit'] == unit) & (X.mm['Active'] != 'N')]
        cap_hr, res, log = m.set_index('Machine_ID')['Plan_per_hr'].astype(float), 'Machine_ID', X.wash
    else:
        p = X.mp[(X.mp['Unit'] == unit) & (X.mp['Active'] != 'N')]
        cap_hr, res, log = (p.set_index('Process')['Capacity_per_day'] / X.RUN_H).astype(float), 'Process', X.dry
    if cap_hr.empty:
        st.info('No active ' + ('machines' if res == 'Machine_ID' else 'processes') + ' defined for this plant in the master tab.')
        return
    key = ('cap', unit, res, str(d0), str(d1), str(X.day), X.until, X.D['version'])
    t = X.cache.get(key)
    if t is None:
        t = calc.resource_daily(log, X.D['alloc'], cap_hr, unit, res, d0, d1, X.day, X.until, X.RUN_H)
        X.cache[key] = t
    if t.empty:
        st.info('No data in this range.')
        return
    typ = X.mm.set_index('Machine_ID')['Type'] if res == 'Machine_ID' else None
    sel = st.multiselect(('Machine' if res == 'Machine_ID' else 'Process') + ' filter (empty = all)', list(cap_hr.index), default=[], key=f'cap_sel_{res}')
    if sel:
        t = t[t[res].isin(sel)]
    tot = calc.cap_rollup(t.assign(_k='all'), ['_k']).iloc[0]
    src = ', '.join(sorted(t['Allot_Source'].unique()))
    c = st.columns(5)
    kpi(c[0], 'Capacity (pcs)', fi(tot['Capacity']), f"{fi(cap_hr.loc[sel].sum() * X.RUN_H if sel else cap_hr.sum() * X.RUN_H)} per day", 'info')
    kpi(c[1], 'Allotted plan (pcs)', fi(tot['Allotted']), f"Allotment {ff(tot['Allot_Pct'])}% | idle {fi(tot['Idle_Capacity'])}", 'info')
    kpi(c[2], 'Actual output (pcs)', fi(tot['Output']), f"Plan achievement {ff(tot['Plan_Achv_Pct'])}%", tone_achv(tot['Plan_Achv_Pct'] / 100, S))
    kpi(c[3], 'Capacity utilisation', f"{ff(tot['Util_Pct'])}%", 'output / capacity', tone_achv(tot['Util_Pct'] / 100, S))
    kpi(c[4], 'Downtime', f"{ff(tot['Downtime_Min'] / 60)} h", f"{ff(tot['Down_Pct'])}% of time | lost {fi(tot['Lost_Pcs'])} pcs", 'bad' if tot['Down_Pct'] > 8 else 'warn')
    note('Allotted source: ' + src)
    # trend of the whole selection
    by_t = calc.cap_rollup(t, ['Month' if per == 'Month-wise' else 'Date'])
    xcol = 'Month' if per == 'Month-wise' else 'Date'
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(x=by_t[xcol], y=by_t['Capacity'], name='Capacity', marker_color=SLATE, opacity=.5), secondary_y=False)
    fig.add_trace(go.Bar(x=by_t[xcol], y=by_t['Allotted'], name='Allotted plan', marker_color=INDIGO), secondary_y=False)
    fig.add_trace(go.Bar(x=by_t[xcol], y=by_t['Output'], name='Actual output', marker_color=TEAL), secondary_y=False)
    fig.add_trace(go.Scatter(x=by_t[xcol], y=by_t['Util_Pct'], name='Utilisation %', mode='lines+markers', line=dict(color=AMBER, width=3)), secondary_y=True)
    fig.update_yaxes(ticksuffix='%', showgrid=False, rangemode='tozero', secondary_y=True, fixedrange=True)
    if per == 'Month-wise':
        fig.update_xaxes(type='category')
    show(style_fig(fig, f'{per}: capacity vs allotted plan vs actual output', h=360))
    a, b = st.columns(2)
    with a:
        r = calc.cap_rollup(t, [res])
        low = r[r['Capacity'] > 0].sort_values('Util_Pct').head(12)
        show(hbar(low, 'Util_Pct', res, 'Lowest capacity utilisation (%)', colors=rag_colors(low['Util_Pct']), fmt=lambda v: f'{v:.0f}%'))
    with b:
        dn = r.sort_values('Lost_Pcs', ascending=False).head(12)
        dn = dn[dn['Lost_Pcs'] > 0]
        show(hbar(dn, 'Lost_Pcs', res, 'Pcs lost to downtime (top 12)', color=PINK, fmt=lambda v: f'{v:,.0f}'))
    # utilisation heatmap resource x date
    if per == 'Day-wise':
        z = t.pivot_table(index=res, columns='Date', values='Output', aggfunc='sum') / t.pivot_table(index=res, columns='Date', values='Capacity', aggfunc='sum').replace(0, np.nan)
        fig = go.Figure(go.Heatmap(z=z.values, x=[d.strftime('%d %b') for d in z.columns], y=list(z.index), colorscale=HEAT, zmin=0, zmax=1.2, xgap=1, ygap=1,
                                   colorbar=dict(tickformat='.0%', thickness=12)))
        fig.update_yaxes(autorange='reversed')
        show(style_fig(fig, 'Capacity utilisation: resource x day', h=max(320, 16 * len(z) + 90), legend=False))
    sec(f'{per} table')
    R = reports.cols(t, ['Date', res, 'Cap_hr', 'Capacity', 'Allotted', 'Output', 'Downtime_Min', 'Lost_Pcs', 'Defect', 'Rework', 'Allot_Source'])
    if per == 'Day-wise':
        g = t.copy()
        g['Idle_Capacity'] = (g['Capacity'] - g['Allotted']).clip(lower=0)
        g['Allot_Pct'] = calc.safe_div(g['Allotted'], g['Capacity']) * 100
        g['Plan_Achv_Pct'] = calc.safe_div(g['Output'], g['Allotted']) * 100
        g['Util_Pct'] = calc.safe_div(g['Output'], g['Capacity']) * 100
        g['Down_Pct'] = calc.safe_div(g['Downtime_Min'], g['Avail_Hours'] * 60) * 100
        cols = ['Date', res, 'Cap_hr', 'Capacity', 'Allotted', 'Idle_Capacity', 'Allot_Pct', 'Output', 'Plan_Achv_Pct', 'Util_Pct', 'Downtime_Min', 'Down_Pct', 'Lost_Pcs', 'Defect', 'Rework', 'Allot_Source']
        out = g[cols].sort_values(['Date', res], ascending=[False, True])
    else:
        g = calc.cap_rollup(t, ['Month', res])
        reasons = calc.top_reasons(log, unit, res, d0, d1, X.day, X.until)
        g = g.merge(reasons, on=res, how='left')
        cols = ['Month', res, 'Cap_hr', 'Days', 'Capacity', 'Allotted', 'Idle_Capacity', 'Allot_Pct', 'Output', 'Plan_Achv_Pct', 'Util_Pct', 'Downtime_Min', 'Down_Pct', 'Lost_Pcs', 'Defect_Pct', 'Rework_Pct', 'Top_Downtime_Reasons']
        out = g[[c for c in cols if c in g.columns]].sort_values(['Month', res])
    cfg = auto_cfg(out)
    for k in ('Util_Pct', 'Plan_Achv_Pct', 'Allot_Pct'):
        if k in cfg:
            cfg[k] = st.column_config.ProgressColumn(reports.LABELS[k], format='%.1f', min_value=0, max_value=130)
    table(out, cfg, height=480)
    downloads(out, f'capacity_{res.lower()}_{per.lower().replace("-", "")}_{unit}_{X.day:%Y%m%d}', 'dl_cap', 'Capacity')
    sec('Drill down: one ' + ('machine' if res == 'Machine_ID' else 'process'))
    pick = st.selectbox('Pick', list(t[res].unique()), key=f'cap_pick_{res}')
    one = t[t[res] == pick]
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(x=one['Date'], y=one['Capacity'], name='Capacity', marker_color=SLATE, opacity=.5), secondary_y=False)
    fig.add_trace(go.Bar(x=one['Date'], y=one['Allotted'], name='Allotted plan', marker_color=INDIGO), secondary_y=False)
    fig.add_trace(go.Bar(x=one['Date'], y=one['Output'], name='Actual output', marker_color=TEAL), secondary_y=False)
    fig.add_trace(go.Scatter(x=one['Date'], y=one['Downtime_Min'], name='Downtime (min)', mode='lines+markers', line=dict(color=PINK, width=3)), secondary_y=True)
    fig.update_yaxes(showgrid=False, rangemode='tozero', secondary_y=True, fixedrange=True)
    show(style_fig(fig, f'{pick}: daily capacity, allotted plan, output and downtime', h=340))
    note('Capacity = pcs/hr x available hours (selected date counts only up to the Till-hour). Allotted plan is capped at capacity. Utilisation = output / capacity. '
         'Plan achievement = output / allotted plan. Lost pcs = downtime hours x pcs/hr.')


# ================================================================== REPORTS
def _capacity_reports(X, d0, d1):
    out = {}
    for u in X.units:
        m = X.mm[(X.mm['Unit'] == u) & (X.mm['Active'] != 'N')]
        if len(m):
            t = calc.resource_daily(X.wash, X.D['alloc'], m.set_index('Machine_ID')['Plan_per_hr'].astype(float), u, 'Machine_ID', d0, d1, X.day, X.until, X.RUN_H)
            if len(t):
                out.setdefault('Machine capacity', []).append(calc.cap_rollup(t, ['Month', 'Machine_ID']).assign(Wash_Plant=u))
        p = X.mp[(X.mp['Unit'] == u) & (X.mp['Active'] != 'N')]
        if len(p):
            t = calc.resource_daily(X.dry, X.D['alloc'], (p.set_index('Process')['Capacity_per_day'] / X.RUN_H).astype(float), u, 'Process', d0, d1, X.day, X.until, X.RUN_H)
            if len(t):
                out.setdefault('Process capacity', []).append(calc.cap_rollup(t, ['Month', 'Process']).assign(Wash_Plant=u))
    res = {}
    for k, v in out.items():
        df = pd.concat(v, ignore_index=True)
        first = ['Wash_Plant', 'Month'] + (['Machine_ID'] if k.startswith('Machine') else ['Process'])
        res['11 ' + k + ' (month)'] = df[first + [c for c in df.columns if c not in first]]
    return res


def reports_view(X):
    S = X.S
    if X.S_all.empty:
        st.warning('No order data.')
        return
    st.caption('Regular reports. Pick the filters, preview a report, download it alone or build the whole pack as one Excel workbook.')
    F, pl, n = filters(X, 'rp', crd=False)
    c1, c2 = st.columns([2, 1])
    lo = max(X.first, X.last - dt.timedelta(days=29))
    rng = c1.date_input('Date range for day-wise reports', value=(lo, X.last), min_value=X.first, max_value=X.last, key='rp_range')
    d0, d1 = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (lo, X.last)
    hz = c2.slider('Crisis horizon (days)', 1, 21, 7, key='rp_h')
    pd_ = X.pdaily if not pl else X.pdaily[X.pdaily['Wash_Plant'].isin(pl)]
    R = reports.report_set(F, pd_, X.day, hz, d0, d1)
    SD = reports.cols(F.rename(columns={}), [c for c, _ in calc.DETAIL_COLS if c in F.columns])
    SD = SD.assign(Machines=F['Machines_Full']).rename(columns={**dict(calc.DETAIL_COLS), 'Input_Var': 'Variation (Input)', 'Output_Var': 'Variation (Output)'})
    R['12 Style details (all plants)'] = SD
    if getattr(X, 'board_mode', False):
        import board
        import views_board as VB
        Fx, _ = VB.forecast(X, 'Plant capacity (Unit_Master)', 90)
        Sx = F.merge(Fx[['Wash_Plant', 'Style', 'PO', 'Color', 'Forecast_Date', 'Late_Days', 'Verdict']], on=['Wash_Plant'] + calc.KEYS, how='left')
        Sx['Flags'] = board.red_flags(Sx)
        R['13 Wash sequence EDD-FIFO'] = reports.cols(Sx[Sx['Priority'].notna()].sort_values(['Wash_Plant', 'Priority']), VB.SEQ_VIEW)
        R['14 Red flags'] = reports.cols(Sx[Sx['Flags'] != ''].sort_values('Days_to_CRD'), ['Wash_Plant', 'Buyer', 'Style', 'PO', 'Color', 'Eff_CRD', 'Days_to_CRD', 'Balance', 'WIP', 'Plan_End', 'Overrun_Days', 'Verdict', 'Flags'])
        pos, order = board.stage_position(X.D['stage'], X.day, X.D['mstage'])
        if len(pos):
            R['15 PO position by stage'] = pos
        if len(X.D['audit']):
            R['16 Edited entries'] = X.D['audit']
        if len(X.D['hist']):
            R['17 Plan history'] = X.D['hist']
    names = list(R)
    pick = st.selectbox('Preview report', names, key='rp_pick')
    df = R[pick]
    if df is None or df.empty:
        st.info('This report is empty for the current selection.')
    else:
        table(df, auto_cfg(df) if pick != '12 Style details (all plants)' else None, height=480)
        downloads(df, 'report_' + pick.split(' ', 1)[1].lower().replace(' ', '_').replace('(', '').replace(')', '') + f'_{X.day:%Y%m%d}', 'dl_rp', pick[:25])
        if pick.startswith('1 '):
            show(bar_plan_actual(df['Wash_Plant'], df['WIP_Yesterday'], df['WIP_Today'], 'WIP: yesterday vs today', plan_name='Yesterday', act_name='Today'))
    sec('Complete pack')
    st.caption('Pack contains: plant WIP vs yesterday, daily receive/delivery, plant / sewing-unit / buyer / CRD summaries, sewing-unit and buyer style details, crisis, buyer crisis, '
               'machine and process capacity (month-wise) and style details.')
    if st.button('Build full Excel pack', key='rp_build'):
        with st.spinner('Building...'):
            pack = dict(R)
            pack.update(_capacity_reports(X, d0, d1))
            st.session_state['rp_pack'] = (f'{X.day:%Y%m%d}', xlsx_of(pack))
    got = st.session_state.get('rp_pack')
    if got:
        st.download_button(f'⬇ Download pack ({got[0]})', got[1], file_name=f'wash_reports_{got[0]}.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='rp_dl_pack')
