"""Plan-execution pages: sequence (EDD then FIFO), red flags, forecast, daily board, PO tracker, audit and plan history."""
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import board
import calc
import reports
from ui import *
from views_portfolio import filters

VERDICT_COL = {'On time': GREEN, 'Will miss CRD': CORAL}
SEQ_VIEW = ['Priority', 'Wash_Plant', 'Sewing_Unit', 'Buyer', 'Style', 'PO', 'Color', 'Eff_CRD', 'Days_to_CRD', 'Order_Qty', 'Input', 'Output', 'WIP', 'Balance',
            'Pending_Input', 'First_Receive_Date', 'Plan_End', 'Overrun_Days', 'Forecast_Date', 'Late_Days', 'Verdict', 'Flags', 'Plan_Revisions', 'Edited']


def _caps(X, basis, util):
    caps = X.caps.set_index('Wash_Plant')['Wet_Capacity_Day'].to_dict()
    if basis.startswith('Recent'):
        pdl = board.board_plant_daily(X.D['board_orders'], X.D['board_daily'], X.units, X.day - pd.Timedelta(days=6), X.day)
        rec = pdl.groupby('Wash_Plant')['Output'].mean().to_dict()
        return {u: float(rec.get(u, 0.0)) for u in X.units}
    return {u: float(caps.get(u, np.nan)) * util / 100.0 for u in X.units}


def forecast(X, basis, util):
    key = ('fc', basis, util, str(X.day), X.D['version'])
    if key not in X.cache:
        cap = _caps(X, basis, util)
        X.cache[key] = board.wash_forecast(X.S_all, X.D['board_daily'], cap, X.day)
    return X.cache[key]


# ================================================================== PLAN EXECUTION
def plan_exec(X):
    S = X.S
    if X.S_all.empty:
        st.warning('No Plan_Board data yet. Fill the Plan_Board tab (one row per PO).')
        return
    st.caption('Work sequence = earliest delivery date (CRD) first; same CRD -> first received first (FIFO); then PO number. Red flags: plan end passed with balance, CRD close, '
               'sewing behind plan, data edited after entry. Daily resolution: numbers are cumulative till the selected date.')
    c1, c2 = st.columns([2, 1])
    basis = c1.radio('Forecast capacity basis', ['Plant capacity (Unit_Master)', 'Recent actual (last 7 days average)'], horizontal=True, key='pe_basis')
    util = c2.slider('Capacity used for the forecast (%)', 50, 110, 90, key='pe_util')
    F, P = forecast(X, basis, util)
    Sx = X.S_all.merge(F[['Wash_Plant', 'Style', 'PO', 'Color', 'Forecast_Date', 'Late_Days', 'Verdict']], on=['Wash_Plant'] + calc.KEYS, how='left')
    Sx['Flags'] = board.red_flags(Sx)
    Fl, pl, n = filters(X, 'pe', crd=False, S=Sx)
    open_ = Fl[Fl['Priority'].notna()]
    flag = open_[open_['Flags'] != '']
    c = st.columns(5)
    kpi(c[0], 'Open orders', fi(len(open_)), f"{open_['Wash_Plant'].nunique()} plants | balance {fi(open_['Balance'].sum())} pcs", 'info')
    kpi(c[1], 'WIP inside plants', fi(open_['WIP'].clip(lower=0).sum()), 'received, not yet washed', 'warn')
    kpi(c[2], 'Plan end passed, still open', fi((open_['Overrun_Days'] > 0).sum()), f"{fi(open_.loc[open_['Overrun_Days'] > 0, 'Balance'].sum())} pcs balance", 'bad' if (open_['Overrun_Days'] > 0).any() else 'ok')
    kpi(c[3], 'Forecast: will miss CRD', fi((open_['Verdict'] == 'Will miss CRD').sum()), f"{fi(open_['Verdict'].astype(str).str.startswith('No sewing plan').sum())} with no sewing plan", 'bad' if (open_['Verdict'] == 'Will miss CRD').any() else 'ok')
    kpi(c[4], 'Edited after entry', fi(int((Fl['Edited'] > 0).sum())), 'orders with changed past entries', 'bad' if (Fl['Edited'] > 0).any() else 'ok')
    sec('Wash sequence (EDD, then FIFO)')
    plants = sorted(open_['Wash_Plant'].unique())
    seq = reports.cols(open_.sort_values(['Wash_Plant', 'Priority']), SEQ_VIEW)
    cfg = auto_cfg(seq)
    table(seq, cfg, height=min(560, 60 + 35 * len(seq)))
    downloads(seq, f'wash_sequence_{X.day:%Y%m%d}', 'dl_seq', 'Wash sequence')
    a, b = st.columns(2)
    with a:
        top = open_[open_['Wash_Plant'] == (plants[0] if len(plants) == 1 else None)].head(15) if len(plants) == 1 else open_.sort_values('Days_to_CRD').head(15)
        if len(top):
            top = top.assign(Label=top['Wash_Plant'] + ' ' + top['PO'])
            fig = go.Figure(go.Bar(x=top['Balance'], y=top['Label'], orientation='h', marker_color=[VERDICT_COL.get(v, AMBER) for v in top['Verdict']], name='Balance',
                                   text=top['Days_to_CRD'].map(lambda d: f'{d:+.0f} d'), textposition='outside', cliponaxis=False))
            fig.update_yaxes(autorange='reversed')
            show(style_fig(fig, 'Balance to wash (green on time, red will miss CRD, amber unknown); label = days to CRD', h=430, legend=False))
    with b:
        verdict = open_['Verdict'].replace('', '(none)').astype(str).str.replace(r'No sewing plan.*', 'No sewing plan', regex=True).str.replace(r'Short.*', 'Short (reject/missing)', regex=True)
        vc = open_.assign(V=verdict).groupby('V')['Balance'].sum().reset_index()
        fig = go.Figure(go.Pie(labels=vc['V'], values=vc['Balance'], hole=.55, marker=dict(colors=PALETTE), sort=False))
        show(style_fig(fig, 'Balance pcs by forecast verdict'))
    sec('Red flags')
    if flag.empty:
        st.success('No red flags in this selection.')
    else:
        fl = reports.cols(flag.sort_values(['Days_to_CRD']), ['Wash_Plant', 'Buyer', 'Style', 'PO', 'Color', 'Eff_CRD', 'Days_to_CRD', 'Balance', 'WIP', 'Plan_End', 'Overrun_Days', 'Verdict', 'Flags'])
        table(fl, auto_cfg(fl), height=min(420, 60 + 35 * len(fl)))
        downloads(fl, f'red_flags_{X.day:%Y%m%d}', 'dl_flags', 'Red flags')
    sec('Suggested wash plan (next 14 days) from the sequence and capacity')
    if len(plants) == 0:
        return
    pick = st.selectbox('Plant', plants, key='pe_plant')
    Pp = P[P['Wash_Plant'] == pick]
    if Pp.empty:
        st.info('Nothing to schedule for this plant.')
        return
    days = pd.date_range(X.day + pd.Timedelta(days=1), periods=14, freq='D')
    W = Pp[Pp['Date'].isin(days)].pivot_table(index=['Style', 'PO', 'Color'], columns='Date', values='Suggested_Wash', aggfunc='sum').reindex(columns=days).fillna(0.0)
    pri = Sx[Sx['Wash_Plant'] == pick].set_index(calc.KEYS)['Priority']
    W = W.reset_index()
    W.insert(0, 'Priority', [pri.get((r.Style, r.PO, r.Color), np.nan) for r in W.itertuples()])
    W = W.sort_values('Priority')
    W.columns = [c if isinstance(c, str) else c.strftime('%d-%b') for c in W.columns]
    cap_day = _caps(X, basis, util).get(pick, np.nan)
    tot = Pp[Pp['Date'].isin(days)].groupby('Date')['Suggested_Wash'].sum().reindex(days).fillna(0.0)
    fig = go.Figure(go.Bar(x=[d.strftime('%d-%b') for d in days], y=tot.values, marker_color=TEAL, name='Suggested wash'))
    fig.add_trace(go.Scatter(x=[d.strftime('%d-%b') for d in days], y=[cap_day] * len(days), mode='lines', name='Capacity used', line=dict(color=AMBER, width=3, dash='dot')))
    show(style_fig(fig, f'{pick}: suggested wash pcs per day vs capacity', h=300))
    table(W, {c: num_cfg(c) for c in W.columns if c not in ('Style', 'PO', 'Color')}, height=min(420, 60 + 35 * len(W)))
    downloads(W, f'suggested_plan_{pick}_{X.day:%Y%m%d}', 'dl_sug', 'Suggested plan')
    note('Suggested plan fills the daily capacity in priority order from pieces already in the plant plus sewing deliveries planned for later days. '
         'It does not replace the planner: copy the numbers into the Plan Board if you accept them.')


# ================================================================== DAILY BOARD (the Excel view)
def daily_board(X):
    O, Dd = X.D['board_orders'], X.D['board_daily']
    if O.empty:
        st.warning('No Plan_Board data yet.')
        return
    months = sorted(set(Dd['Date'].dt.strftime('%Y-%m'))) if len(Dd) else sorted(set(O['Sheet_Month']))
    c1, c2, c3, c4 = st.columns(4)
    month = c1.selectbox('Month', months, index=len(months) - 1, key='db_month')
    plants = sorted(O['Wash_Plant'].unique())
    plant = c2.selectbox('Wash plant', plants, index=plants.index(X.unit) if X.unit in plants else 0, key='db_plant')
    section = c3.radio('Section', ['Sewing delivery', 'Wash production'], horizontal=True, key='db_sec')
    metric = c4.radio('Show', ['Plan', 'Actual', 'Variation'], horizontal=True, key='db_met')
    p = pd.Period(month, 'M')
    days = pd.date_range(p.start_time, periods=p.days_in_month, freq='D')
    d = Dd[(Dd['Wash_Plant'] == plant) & (Dd['Date'].dt.to_period('M') == p)]
    pc, ac = ('SEW_PLAN', 'SEW_ACT') if section.startswith('Sewing') else ('WASH_PLAN', 'WASH_ACT')
    # totals per day (chart)
    tot = d.groupby('Date')[['SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT']].sum().reindex(days).fillna(0.0)
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Sewing delivery: plan vs actual', 'Wash production: plan vs actual'))
    lab = [x.strftime('%d') for x in days]
    for ci, (a, b) in enumerate((('SEW_PLAN', 'SEW_ACT'), ('WASH_PLAN', 'WASH_ACT')), 1):
        fig.add_trace(go.Bar(x=lab, y=tot[a], name='Plan', marker_color=SLATE, opacity=.55, showlegend=ci == 1), row=1, col=ci)
        fig.add_trace(go.Bar(x=lab, y=tot[b].where(days <= X.day), name='Actual', marker_color=TEAL if ci == 2 else INDIGO, showlegend=ci == 1), row=1, col=ci)
    fig.update_layout(showlegend=True)
    show(style_fig(fig, f'{plant} | {month} | all orders', h=320))
    if d.empty:
        st.info('No daily numbers for this plant and month.')
        return
    key = ['Style', 'PO', 'Color']
    info = O[O['Wash_Plant'] == plant].set_index(key)[['Buyer', 'Sewing_Unit', 'Eff_CRD' if 'Eff_CRD' in O else 'CRD']] if len(O) else None
    PL = d.pivot_table(index=key, columns='Date', values=pc, aggfunc='sum').reindex(columns=days)
    AC = d.pivot_table(index=key, columns='Date', values=ac, aggfunc='sum').reindex(columns=days)
    upto = np.tile(np.asarray(AC.columns <= X.day), (len(AC), 1))
    if metric == 'Plan':
        M = PL
    elif metric == 'Actual':
        M = AC.where(upto)
    else:
        M = AC.fillna(0).sub(PL.fillna(0)).where((AC.notna().values | PL.notna().values) & upto)
    M = M.reset_index()
    M.columns = [c if isinstance(c, str) else f'{c.day}' for c in M.columns]
    M.insert(3, 'Total', M[[c for c in M.columns if c not in key]].sum(axis=1))
    sec(f'{section} | {metric} per day (rows = orders, columns = day of month)')
    table(M, {**{c: num_cfg(c) for c in M.columns if c not in key}, 'Total': num_cfg('Total')}, height=min(560, 70 + 35 * len(M)))
    full = {}
    for sec_name, (a, b) in {'Sewing': ('SEW_PLAN', 'SEW_ACT'), 'Wash': ('WASH_PLAN', 'WASH_ACT')}.items():
        for nm, src in (('plan', d.pivot_table(index=key, columns='Date', values=a, aggfunc='sum').reindex(columns=days)),
                        ('actual', d.pivot_table(index=key, columns='Date', values=b, aggfunc='sum').reindex(columns=days))):
            x = src.reset_index()
            x.columns = [c if isinstance(c, str) else f'{c.day}' for c in x.columns]
            full[f'{sec_name} {nm}'] = x
    st.download_button('⬇ Whole month, all four blocks (Excel)', xlsx_of(full), file_name=f'daily_board_{plant}_{month}.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='dl_db')
    downloads(M, f'daily_board_{plant}_{month}_{section.split()[0].lower()}_{metric.lower()}', 'dl_db1', 'Board')


# ================================================================== PO TRACKER (where are the pieces now)
def po_tracker(X):
    L = X.D['stage']
    S = X.S_all
    if L.empty:
        st.info('No Stage_Log rows yet. Add rows to the Stage_Log tab: Date, Wash_Plant, Style, PO, Color, Stage, Pcs_In, Pcs_Out (a scan-system export fits this format).')
        return
    st.caption('Pieces currently inside each stage = total in - total out of that stage, cumulative till the selected date. Stage order comes from Master_Stage.')
    F, pl, n = filters(X, 'pt', crd=False, S=S)
    pos, order = board.stage_position(L, X.day, X.D['mstage'])
    K = ['Wash_Plant'] + calc.KEYS
    pos = pos.merge(F[K + ['Buyer', 'Sewing_Unit', 'Eff_CRD', 'Days_to_CRD', 'Order_Qty', 'Input', 'Output', 'Balance', 'Priority']], on=K, how='inner')
    q = st.text_input('Search style or PO', key='pt_q').strip().lower()
    if q:
        pos = pos[pos['Style'].str.lower().str.contains(q) | pos['PO'].str.lower().str.contains(q)]
    pos['In_Plant'] = pos[order].sum(axis=1)
    pos = pos[(pos['In_Plant'].abs() > 0.5)]
    if pos.empty:
        st.info('Nothing inside the plants for this selection.')
        return
    c = st.columns(5)
    kpi(c[0], 'Pieces inside plants', fi(pos['In_Plant'].sum()), f"{len(pos)} orders", 'info')
    for j, s_ in enumerate(order[:4]):
        kpi(c[j + 1], s_, fi(pos[s_].sum()), 'pcs now')
    a, b = st.columns(2)
    with a:
        g = pos.groupby('Wash_Plant')[order].sum().reset_index()
        fig = go.Figure()
        for i_, s_ in enumerate(order):
            fig.add_trace(go.Bar(x=g['Wash_Plant'], y=g[s_], name=s_, marker_color=PALETTE[i_ % len(PALETTE)]))
        show(style_fig(fig, 'Pieces by stage and wash plant', grouped=False))
    with b:
        gs = pos.groupby('Style')[order].sum()
        gs['t'] = gs.sum(axis=1)
        gs = gs.sort_values('t', ascending=False).head(10).drop(columns='t').reset_index()
        fig = go.Figure()
        for i_, s_ in enumerate(order):
            fig.add_trace(go.Bar(y=gs['Style'], x=gs[s_], name=s_, orientation='h', marker_color=PALETTE[i_ % len(PALETTE)]))
        fig.update_yaxes(autorange='reversed')
        show(style_fig(fig, 'Top 10 styles: pieces by stage', grouped=False))
    sec('PO-wise: where are the pieces now')
    cols = ['Wash_Plant', 'Buyer', 'Style', 'PO', 'Color', 'Eff_CRD', 'Days_to_CRD', 'Priority', 'Order_Qty', 'Input', 'Output'] + order + ['In_Plant', 'Balance']
    V = pos.sort_values(['Eff_CRD', 'Priority'])[cols]
    cfg = auto_cfg(V)
    for s_ in order:
        cfg[s_] = num_cfg(s_)
    cfg['In_Plant'] = num_cfg('Total inside plant')
    table(V, cfg, height=min(520, 60 + 35 * len(V)))
    downloads(V, f'po_tracker_{X.day:%Y%m%d}', 'dl_pot', 'PO tracker')
    sec('Style-wise (all POs added up)')
    sw = pos.groupby('Style').agg(POs=('PO', 'nunique'), Order_Qty=('Order_Qty', 'sum'), Output=('Output', 'sum'), **{s_: (s_, 'sum') for s_ in order}, In_Plant=('In_Plant', 'sum')).reset_index()
    sw['Next_CRD'] = sw['Style'].map(pos.groupby('Style')['Eff_CRD'].min())
    cfgs = auto_cfg(sw)
    for s_ in order:
        cfgs[s_] = num_cfg(s_)
    table(sw.sort_values('In_Plant', ascending=False), cfgs, height=min(420, 60 + 35 * len(sw)))
    downloads(sw, f'style_tracker_{X.day:%Y%m%d}', 'dl_stt', 'Style tracker')
    sec('One PO: stage movement by day')
    lab = {(r.Wash_Plant, r.Style, r.PO, r.Color): f'{r.Wash_Plant} | {r.Style} | {r.PO} | {r.Color}' for r in V.itertuples()}
    one = st.selectbox('Order', list(lab.values()), key='pt_one')
    k = [x for x, v in lab.items() if v == one][0]
    d = L[(L['Wash_Plant'] == k[0]) & (L['Style'] == k[1]) & (L['PO'] == k[2]) & (L['Color'] == k[3]) & (L['Date'] <= X.day)]
    cum = d.assign(Net=d['Pcs_In'] - d['Pcs_Out']).pivot_table(index='Date', columns='Stage', values='Net', aggfunc='sum').reindex(columns=order).fillna(0.0).cumsum()
    fig = go.Figure()
    for i_, s_ in enumerate(order):
        fig.add_trace(go.Bar(x=cum.index, y=cum[s_], name=s_, marker_color=PALETTE[i_ % len(PALETTE)]))
    show(style_fig(fig, 'Pieces inside each stage, end of day', grouped=False, h=320))
    mv = d.assign(Date=d['Date'].dt.strftime('%d-%b')).drop(columns=['Wash_Plant', 'Style', 'PO', 'Color'])
    table(mv, auto_cfg(mv), height=300)


# ================================================================== AUDIT AND PLAN HISTORY
def audit_view(X):
    A, H = X.D['audit'], X.D['hist']
    st.caption('Every change to a number that was already entered is logged by the sheet script (old value, new value, who, when) and the cell turns red. '
               'Rows below are the dashboard copy of that log. Edited orders carry a flag in the sequence and crisis tables.')
    edits = A[A['Type'].str.upper().str.startswith('EDIT')] if len(A) else A
    c = st.columns(4)
    kpi(c[0], 'Edited entries', fi(len(edits)), f"{edits[['Wash_Plant', 'Style', 'PO', 'Color']].drop_duplicates().shape[0] if len(edits) else 0} orders", 'bad' if len(edits) else 'ok')
    unack = edits[edits['Ack'] == ''] if len(edits) else edits
    kpi(c[1], 'Not acknowledged', fi(len(unack)), 'ask the planner to acknowledge', 'warn' if len(unack) else 'ok')
    kpi(c[2], 'Plan revisions logged', fi(len(H)), f"{H[['Wash_Plant', 'Style', 'PO', 'Color']].drop_duplicates().shape[0] if len(H) else 0} orders", 'info')
    kpi(c[3], 'Users who edited', fi(edits['User'].replace('', '(unknown)').nunique() if len(edits) else 0), 'blank = anonymous editor', 'info')
    sec('Edited entries (past numbers changed)')
    if edits.empty:
        st.success('No edited entries.')
    else:
        e = edits.copy()
        e['Old_n'] = pd.to_numeric(e['Old'], errors='coerce')
        e['New_n'] = pd.to_numeric(e['New'], errors='coerce')
        e['Change'] = e['New_n'] - e['Old_n']
        e['Field'] = e['Field'].replace({'SEW_ACT': 'Sewing actual', 'WASH_ACT': 'Wash actual', 'SEW_PLAN': 'Sewing plan', 'WASH_PLAN': 'Wash plan'})
        v = e[['Timestamp', 'User', 'Wash_Plant', 'Style', 'PO', 'Color', 'Field', 'Date', 'Old', 'New', 'Change', 'Ack']]
        cfg = {c_: st.column_config.TextColumn(c_.replace('_', ' ')) for c_ in v.columns}
        cfg['Date'] = st.column_config.DateColumn('For date', format='DD-MMM-YY')
        cfg['Timestamp'] = st.column_config.DatetimeColumn('Edited at', format='DD-MMM-YY HH:mm')
        cfg['Change'] = st.column_config.NumberColumn('Change (pcs)', format='%d')
        table(v, cfg, height=min(420, 60 + 35 * len(v)))
        downloads(v, f'edited_entries_{X.day:%Y%m%d}', 'dl_aud', 'Edited entries')
        by = e.groupby('Wash_Plant').size().reset_index(name='Edits')
        show(style_fig(go.Figure(go.Bar(x=by['Wash_Plant'], y=by['Edits'], marker_color=CORAL, name='Edits')), 'Edited entries by wash plant', h=260, legend=False))
    sec('Plan history (start / end date and CRD changes, with version)')
    if H.empty:
        st.info('No plan history logged yet.')
    else:
        q = st.text_input('Filter by PO or style', key='au_q').strip().lower()
        h = H[H['PO'].str.lower().str.contains(q) | H['Style'].str.lower().str.contains(q)] if q else H
        cfg = {c_: st.column_config.TextColumn(c_.replace('_', ' ')) for c_ in h.columns}
        cfg['Timestamp'] = st.column_config.DatetimeColumn('Changed at', format='DD-MMM-YY HH:mm')
        table(h, cfg, height=min(460, 60 + 35 * len(h)))
        downloads(h, f'plan_history_{X.day:%Y%m%d}', 'dl_hist', 'Plan history')
        rv = H.groupby(['Wash_Plant', 'Style', 'PO', 'Color']).agg(Changes=('Field', 'size'), Last_Change=('Timestamp', 'max')).reset_index().sort_values('Changes', ascending=False).head(10)
        show(hbar(rv.assign(L=rv['Wash_Plant'] + ' ' + rv['PO']), 'Changes', 'L', 'Most revised orders', color=VIOLET, fmt=lambda v: f'{v:.0f}'))
