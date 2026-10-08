"""Wash & Dry Process - Hourly Monitoring Dashboard (Streamlit)."""
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import calc
import data

st.set_page_config(page_title='Wash & Dry Monitoring', page_icon='🧺', layout='wide', initial_sidebar_state='expanded')

NAVY, TEAL, AMBER, RED, ORANGE, GREY, GREY_L = '#1B2A41', '#2A9D8F', '#E9C46A', '#E76F51', '#F4A261', '#8D99AE', '#C9D1DC'
HEAT = [[0, '#E76F51'], [0.55, '#F4D58D'], [0.8, '#A8D8B9'], [1, '#2A9D8F']]

st.markdown("""
<style>
.block-container{padding-top:1.1rem;max-width:1500px}
.hero{background:linear-gradient(120deg,#1B2A41,#2A4365);color:#fff;border-radius:14px;padding:16px 24px;margin-bottom:12px}
.hero h1{font-size:1.55rem;margin:0;color:#fff;letter-spacing:.02em}
.hero .sub{opacity:.85;font-size:.88rem;margin-top:6px}
.chip{display:inline-block;background:rgba(255,255,255,.16);border-radius:20px;padding:2px 11px;margin-right:6px;font-size:.76rem}
.kpi{background:#fff;border:1px solid #E6EAF0;border-top:4px solid #2A9D8F;border-radius:12px;padding:10px 16px;
     box-shadow:0 1px 3px rgba(20,30,50,.06);margin-bottom:10px}
.kpi .l{font-size:.66rem;letter-spacing:.09em;color:#8D99AE;font-weight:700;text-transform:uppercase}
.kpi .v{font-size:1.8rem;font-weight:700;color:#1B2A41;line-height:1.2}
.kpi .s{font-size:.74rem;color:#6B7685}
.kpi.ok .v{color:#1E8449}.kpi.warn .v{color:#D68910}.kpi.bad .v{color:#C0392B}
.kpi.ok{border-top-color:#1E8449}.kpi.warn{border-top-color:#E9C46A}.kpi.bad{border-top-color:#C0392B}
.sec{font-weight:700;color:#1B2A41;font-size:1.02rem;margin:14px 0 4px 0;border-left:4px solid #2A9D8F;padding-left:10px}
.note{font-size:.78rem;color:#6B7685}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ helpers
def fi(x):
    return '–' if x is None or pd.isna(x) else f"{x:,.0f}"


def fp(x, d=1):
    return '–' if x is None or pd.isna(x) else f"{x * 100:.{d}f}%"


def ff(x, d=1):
    return '–' if x is None or pd.isna(x) else f"{x:,.{d}f}"


def kpi(col, label, value, sub='', tone=''):
    col.markdown(f'<div class="kpi {tone}"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>',
                 unsafe_allow_html=True)


def sec(text):
    st.markdown(f'<div class="sec">{text}</div>', unsafe_allow_html=True)


def _try(fn, *a, **kw):
    """Streamlit renamed width options across versions; try new API, then old, then plain."""
    for extra in ({'width': 'stretch'}, {'use_container_width': True}, {}):
        try:
            return fn(*a, **kw, **extra)
        except Exception:
            continue
    return fn(*a, **kw)


def show(fig):
    _try(st.plotly_chart, fig)


def table(df, cfg=None, height=None):
    kw = dict(hide_index=True, column_config=cfg or {})
    if height:
        kw['height'] = height
    _try(st.dataframe, df, **kw)


def style_fig(fig, title, h=330, legend=True):
    fig.update_layout(title=dict(text=title, x=0, font=dict(size=14, color=NAVY)), height=h, template='plotly_white',
                      margin=dict(l=10, r=10, t=44, b=10), showlegend=legend,
                      legend=dict(orientation='h', y=-0.22, x=0), font=dict(family='Arial', size=11), barmode='group',
                      plot_bgcolor='#FFFFFF', paper_bgcolor='#FFFFFF')
    return fig


def tone_achv(a, S):
    if pd.isna(a):
        return ''
    return 'ok' if a >= S['Target_Pct'] else ('warn' if a >= S['Alert_Pct'] else 'bad')


def tone_limit(x, lim):
    if pd.isna(x):
        return ''
    return 'bad' if x > lim else 'ok'


def short_hours(h):
    return h['Hour'].str[:5]


def pct_cfg(label, mx=120):
    return st.column_config.ProgressColumn(label, format='%.1f', min_value=0, max_value=mx)


def num_cfg(label, fmt='%d'):
    return st.column_config.NumberColumn(label, format=fmt)


def fig_plan_actual(h, S, title='Hourly Plan vs Output'):
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    x = short_hours(h)
    fig.add_trace(go.Bar(x=x, y=h['Plan'], name='Plan', marker_color=GREY_L), secondary_y=False)
    fig.add_trace(go.Bar(x=x, y=h['Output'], name='Output', marker_color=TEAL), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=h['Achv'] * 100, name='Achv %', mode='lines+markers', line=dict(color=NAVY, width=2),
                             marker=dict(size=5)), secondary_y=True)
    fig.add_trace(go.Scatter(x=x, y=[S['Target_Pct'] * 100] * len(x), name='Target %', mode='lines',
                             line=dict(color=RED, width=1, dash='dot')), secondary_y=True)
    fig.update_yaxes(range=[0, 140], showgrid=False, ticksuffix='%', secondary_y=True)
    return style_fig(fig, title)


def fig_cumulative(h, title='Cumulative Output vs Plan'):
    x = short_hours(h)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=h['Cum_Output'], name='Cum Output', marker_color=TEAL))
    fig.add_trace(go.Scatter(x=x, y=h['Cum_Plan'], name='Cum Plan', mode='lines', line=dict(color=NAVY, width=3)))
    return style_fig(fig, title)


def fig_flow(h, title='Input vs Output and Closing WIP'):
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    x = short_hours(h)
    fig.add_trace(go.Bar(x=x, y=h['Input'], name='Input', marker_color=AMBER), secondary_y=False)
    fig.add_trace(go.Bar(x=x, y=h['Output'], name='Output', marker_color=TEAL), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=h['Closing_WIP'], name='Closing WIP', mode='lines+markers', line=dict(color=NAVY, width=2)),
                  secondary_y=True)
    fig.update_yaxes(showgrid=False, secondary_y=True)
    return style_fig(fig, title)


def fig_quality(h, S, second='Rewash_Pct', second_name='Rewash %', title='Defect % and Rewash % by hour'):
    x = short_hours(h)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=h['Defect_Pct'] * 100, name='Defect %', mode='lines+markers', line=dict(color=RED, width=2)))
    fig.add_trace(go.Scatter(x=x, y=h[second] * 100, name=second_name, mode='lines+markers', line=dict(color=ORANGE, width=2)))
    fig.add_trace(go.Scatter(x=x, y=[S['Max_Defect_Pct'] * 100] * len(x), name='Defect limit', mode='lines',
                             line=dict(color=RED, width=1, dash='dot')))
    fig.add_trace(go.Scatter(x=x, y=[S['Max_Rewash_Pct'] * 100] * len(x), name='Rewash limit', mode='lines',
                             line=dict(color=ORANGE, width=1, dash='dot')))
    fig.update_yaxes(ticksuffix='%', rangemode='tozero')
    return style_fig(fig, title)


def fig_downtime(h, title='Downtime by hour (machine-minutes)'):
    fig = go.Figure(go.Bar(x=short_hours(h), y=h['Downtime_Min'], name='Downtime', marker_color=GREY))
    return style_fig(fig, title, legend=False)


def fig_heat(z, title, zmax=1.2, pct=True, height=None):
    fig = go.Figure(go.Heatmap(z=z.values, x=[f"{calc.hour_labels(DAY_START)[int(c) - 1][:5]}" for c in z.columns], y=list(z.index),
                               colorscale=HEAT if pct else 'Teal', zmin=0, zmax=zmax if pct else None, xgap=1, ygap=1,
                               colorbar=dict(tickformat='.0%' if pct else None, thickness=12)))
    fig.update_yaxes(autorange='reversed')
    style_fig(fig, title, h=height or max(320, 17 * len(z) + 90), legend=False)
    return fig


def fig_pareto(p, title):
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(x=p['Reason'], y=p['Minutes'], name='Minutes', marker_color=GREY), secondary_y=False)
    fig.add_trace(go.Scatter(x=p['Reason'], y=p['Cum_Share'] * 100, name='Cumulative %', mode='lines+markers',
                             line=dict(color=RED, width=2)), secondary_y=True)
    fig.update_yaxes(range=[0, 105], ticksuffix='%', showgrid=False, secondary_y=True)
    return style_fig(fig, title)


# ------------------------------------------------------------------ data + sidebar
with st.sidebar:
    st.markdown('### 🧺 Wash & Dry Monitor')
    secrets_ok = data.secrets_ready()
    use_demo = st.checkbox('Use demo data', value=not secrets_ok, disabled=not secrets_ok,
                           help='Demo data is bundled with the app. Connect Google Sheets in Secrets to use live data.')

D = data.load_all(use_demo)
S = D['settings']
wash, dry, wip, mm, mp = D['wash'], D['dry'], D['wip'], D['machine'], D['process']
RUN_H, BASIS, DAY_START = S['Run_Hours'], S['Plan_Basis'], S['Day_Start_Hour']
LABELS = calc.hour_labels(DAY_START)

units = sorted(set(mm['Unit']) | set(wash['Unit']) | set(mp['Unit']) | set(dry['Unit']))
units = [u for u in units if u and u != 'nan']
if not units:
    st.error('No units found. Check Master_Machine / Wash_Log tabs.')
    st.stop()

with st.sidebar:
    unit = st.selectbox('Unit', units)
    uw, ud = wash[wash['Unit'] == unit], dry[dry['Unit'] == unit]
    all_dates = sorted(set(uw['Date']) | set(ud['Date']))
    last = all_dates[-1].date() if all_dates else dt.date.today()
    first = all_dates[0].date() if all_dates else last
    date = st.date_input('Date', value=last, min_value=first, max_value=max(last, dt.date.today()))
    day = pd.Timestamp(date)
    w_all = calc.apply_filters(wash, unit=unit, date=day)
    d_all = calc.apply_filters(dry, unit=unit, date=day)
    max_h = int(max(w_all['Hour_Idx'].max() if len(w_all) else 0, d_all['Hour_Idx'].max() if len(d_all) else 0)) or 24
    until = st.select_slider('Till hour', options=calc.HOURS, value=max_h, key=f'until_{unit}_{date}',
                             format_func=lambda i: f"{i}  ({LABELS[i - 1][-5:]})")
    st.markdown('---')
    st.markdown('**Style search**')
    q = st.text_input('Type part of a style name', placeholder='e.g. ST-4412 or Snow', label_visibility='collapsed').strip()
    styles_all = sorted((set(uw['Style']) | set(ud['Style'])) - {calc.NO_STYLE})
    matches = [s for s in styles_all if q.lower() in s.lower()] if q else []
    sel = st.multiselect('Matching styles', matches, default=matches, key=f'sty_{q.lower()}') if q else []
    if q and not matches:
        st.warning('No style matches this search.')
    styles_active = (sel or ['__none__']) if q else None
    wtypes_all = sorted(t for t in uw['Wash_Type'].unique() if t and t != 'nan')
    wtypes = st.multiselect('Wash type', wtypes_all, default=[]) or None
    st.markdown('---')
    auto = st.checkbox('Auto-refresh every 60 s', value=False)
    if auto:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=60000, key='autorefresh')
        except Exception:
            st.caption('Install streamlit-autorefresh to enable.')
    if st.button('Refresh data now'):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Rows loaded: wash {len(wash):,} | dry {len(dry):,}")
    st.caption('Source: ' + ('DEMO data' if D['demo'] else 'Google Sheets (cached 60 s)'))

# ------------------------------------------------------------------ filtered frames and core tables
filters_on = bool(styles_active) or bool(wtypes)
style_on = bool(styles_active)
w_day = calc.apply_filters(wash, unit=unit, date=day, styles=styles_active, wash_types=wtypes)
d_day = calc.apply_filters(dry, unit=unit, date=day, styles=styles_active)
plan_hr = calc.unit_plan_per_hr(mm, unit, BASIS)
std_hr = calc.unit_plan_per_hr(mm, unit, 1.0)
open_w = calc.opening_wip(wip, unit, day, 'WASH')
H = calc.hourly_table(w_day, calc.WASH_NUM, plan_hr, until, open_w, DAY_START, with_plan=not filters_on)
if filters_on:
    H['Closing_WIP'] = np.nan
K = calc.wash_kpis(H, until)
daily_all = calc.wash_daily(wash, mm, unit, first, last, BASIS)
avg_out = daily_all['Output'].tail(7).mean() if len(daily_all) else np.nan

chips = f'<span class="chip">Unit {unit}</span><span class="chip">{day:%A, %d %b %Y}</span><span class="chip">Hours 1-{until} (until {LABELS[until - 1][-5:]})</span>'
if q:
    chips += f'<span class="chip">Style: {q}</span>'
if wtypes:
    chips += f'<span class="chip">Wash: {", ".join(wtypes)}</span>'
if D['demo']:
    chips += '<span class="chip" style="background:#E76F51">DEMO DATA</span>'
st.markdown(f'<div class="hero"><h1>WASH &amp; DRY PROCESS | HOURLY MONITORING</h1><div class="sub">{chips}</div></div>',
            unsafe_allow_html=True)
if filters_on:
    st.info('Style / wash-type filter is ON: plan, achievement and WIP are hidden (plan is not defined per style). Actuals are filtered.')
if not len(w_all) and not len(d_all):
    st.warning('No numbers entered yet for this date and unit. Showing plan only.')

tabs = st.tabs(['📊 Overview', '🏭 Machines', '🔥 Dry Process', '🧪 Quality & Downtime', '👗 Style Explorer', '📈 Trends', '🩺 Data Health'])

# ================================================================== OVERVIEW
with tabs[0]:
    c = st.columns(5)
    kpi(c[0], 'Plan output', fi(K['plan']), f"Full day: {fi(plan_hr * RUN_H) if not filters_on else '–'} pcs")
    kpi(c[1], 'Actual output', fi(K['output']), f"Variance: {fi(K['var'])} pcs" if not pd.isna(K['var']) else 'Plan hidden')
    kpi(c[2], 'Achievement %', fp(K['achv']), f"Target {fp(S['Target_Pct'], 0)} | Alert < {fp(S['Alert_Pct'], 0)}", tone_achv(K['achv'], S))
    kpi(c[3], 'Input (loaded)', fi(K['input']), f"Input - Output: {fi(K['input'] - K['output'])}")
    kpi(c[4], 'Closing WIP', fi(K['wip']), f"Opening: {fi(open_w)}")
    c = st.columns(5)
    cover = K['wip'] / avg_out if avg_out and not pd.isna(K['wip']) else np.nan
    kpi(c[0], 'WIP cover (days)', ff(cover), f"vs last-7-day avg output {fi(avg_out)}/day")
    kpi(c[1], 'Defect %', fp(K['defect_pct']), f"Limit {fp(S['Max_Defect_Pct'])} | Inspected {fi(K['inspected'])}", tone_limit(K['defect_pct'], S['Max_Defect_Pct']))
    kpi(c[2], 'Rewash %', fp(K['rewash_pct']), f"Limit {fp(S['Max_Rewash_Pct'])} | Rewash {fi(K['rewash'])} pcs", tone_limit(K['rewash_pct'], S['Max_Rewash_Pct']))
    kpi(c[3], 'Downtime (hrs)', ff(K['downtime_min'] / 60), f"{fi(K['downtime_min'])} machine-minutes")
    util = K['output'] / (std_hr * until) if std_hr and not filters_on else np.nan
    kpi(c[4], 'Capacity utilisation', fp(util), f"Std capacity till hr: {fi(std_hr * until)}")

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
        mix = w_day.groupby('Wash_Type')['Output'].sum().reset_index()
        mix = mix[mix['Output'] > 0]
        fig = go.Figure(go.Pie(labels=mix['Wash_Type'].replace('', '(not set)'), values=mix['Output'], hole=0.55,
                               marker=dict(colors=[TEAL, AMBER, NAVY, RED, GREY])))
        show(style_fig(fig, 'Wash type mix (output)'))

    sec('Hourly table')
    ht = H[H['Hour_Idx'] <= until].copy()
    ht['Achv %'] = ht['Achv'] * 100
    ht['Defect %'] = ht['Defect_Pct'] * 100
    ht['Rewash %'] = ht['Rewash_Pct'] * 100
    ht = ht[['Hour', 'Shift', 'Plan', 'Output', 'Var', 'Achv %', 'Cum_Plan', 'Cum_Output', 'Input', 'Closing_WIP', 'QC_Inspected',
             'Defect %', 'Rewash', 'Rewash %', 'Downtime_Min']]
    table(ht, {'Achv %': pct_cfg('Achv %'), 'Plan': num_cfg('Plan'), 'Output': num_cfg('Output'), 'Var': num_cfg('Var'),
               'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f'),
               'Cum_Plan': num_cfg('Cum Plan'), 'Cum_Output': num_cfg('Cum Output'), 'Closing_WIP': num_cfg('Closing WIP'),
               'QC_Inspected': num_cfg('QC Inspected'), 'Downtime_Min': num_cfg('Downtime (min)')}, height=420)

# ================================================================== MACHINES
with tabs[1]:
    MT = calc.machine_table(w_day, mm, unit, until, BASIS, with_plan=not filters_on)
    MT['Status'] = calc.status_series(MT['Achv'], MT['Hours_Logged'], S)
    c = st.columns(5)
    kpi(c[0], 'Machines (active)', fi((MT['Active'] != 'N').sum()), f"{fi(len(MT))} in master")
    kpi(c[1], 'On target', fi((MT['Status'] == 'On target').sum()), '', 'ok')
    kpi(c[2], 'Watch', fi((MT['Status'] == 'Watch').sum()), '', 'warn')
    kpi(c[3], 'Behind', fi((MT['Status'] == 'Behind').sum()), '', 'bad')
    kpi(c[4], 'No data', fi((MT['Status'] == 'No data').sum()), 'nothing logged')
    f1, f2 = st.columns(2)
    types = sorted(MT['Type'].unique())
    ftype = f1.multiselect('Machine type', types, default=types)
    fstat = f2.multiselect('Status', ['Behind', 'Watch', 'On target', 'No data', '-'], default=['Behind', 'Watch', 'On target', 'No data', '-'])
    V = MT[MT['Type'].isin(ftype) & MT['Status'].isin(fstat)].sort_values('Achv', na_position='last')
    sec('Machine-wise plan vs actual')
    V = V.assign(**{'Achv %': V['Achv'] * 100, 'Defect %': V['Defect_Pct'] * 100, 'Rewash %': V['Rewash_Pct'] * 100})
    table(V[['Machine_ID', 'Type', 'Plan', 'Output', 'Var', 'Achv %', 'Input', 'Defect %', 'Rewash', 'Rewash %', 'Downtime_Min', 'Hours_Logged', 'Status']],
          {'Achv %': pct_cfg('Achv %'), 'Plan': num_cfg('Plan'), 'Output': num_cfg('Output'), 'Var': num_cfg('Var'),
           'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f'), 'Downtime_Min': num_cfg('Downtime (min)'),
           'Hours_Logged': num_cfg('Hours logged')}, height=430)
    a, b = st.columns(2)
    with a:
        low = MT[(MT['Hours_Logged'] > 0) & MT['Achv'].notna()].sort_values('Achv').head(10)
        fig = go.Figure(go.Bar(x=low['Achv'] * 100, y=low['Machine_ID'], orientation='h', marker_color=RED, name='Achv %'))
        fig.update_yaxes(autorange='reversed')
        show(style_fig(fig, '10 lowest-achieving machines (%)', legend=False))
    with b:
        top = MT.sort_values('Downtime_Min', ascending=False).head(10)
        top = top[top['Downtime_Min'] > 0]
        fig = go.Figure(go.Bar(x=top['Downtime_Min'], y=top['Machine_ID'], orientation='h', marker_color=GREY, name='Minutes'))
        fig.update_yaxes(autorange='reversed')
        show(style_fig(fig, '10 highest downtime machines (min)', legend=False))
    sec('Machine x Hour heatmap')
    if filters_on:
        z = w_day[w_day['Hour_Idx'] <= until].pivot_table(index='Machine_ID', columns='Hour_Idx', values='Output', aggfunc='sum')
        z = z.reindex(columns=[x for x in calc.HOURS if x <= until])
        show(fig_heat(z, 'Output pcs by machine and hour (filtered)', pct=False))
    else:
        show(fig_heat(calc.machine_heatmap(w_day, mm, unit, until, BASIS), 'Achievement % by machine and hour (red = behind, green = on target)'))

# ================================================================== DRY PROCESS
with tabs[2]:
    DT = calc.dry_table(d_day, mp, wip, unit, day, until, RUN_H, BASIS, with_plan=not style_on)
    DT['Status'] = calc.status_series(DT['Achv'], DT['Hours_Logged'], S)
    dplan, dout = DT['Plan'].sum(min_count=1), DT['Output'].sum()
    dach = dout / dplan if dplan and dplan > 0 else np.nan
    ddef = DT['Defect'].sum() / dout if dout > 0 else np.nan
    drew = DT['Rework'].sum() / dout if dout > 0 else np.nan
    crit = calc.critical_process(DT)
    c = st.columns(5)
    kpi(c[0], 'Plan (process-pcs)', fi(dplan), 'a garment can pass several processes')
    kpi(c[1], 'Output (process-pcs)', fi(dout), f"Achievement {fp(dach)}", tone_achv(dach, S))
    kpi(c[2], 'Defect %', fp(ddef), f"Limit {fp(S['Max_Defect_Pct'])}", tone_limit(ddef, S['Max_Defect_Pct']))
    kpi(c[3], 'Rework %', fp(drew), f"Limit {fp(S['Max_Rewash_Pct'])}", tone_limit(drew, S['Max_Rewash_Pct']))
    kpi(c[4], 'Critical process', crit['Process'] if crit is not None and not style_on else '–',
        f"Achv {fp(crit['Achv'])} | loss {fi(crit['Loss_Pcs'])} pcs" if crit is not None and not style_on else '', 'bad' if crit is not None and not style_on and crit['Achv'] < S['Alert_Pct'] else '')
    sec('Process-wise plan vs actual')
    P = DT.sort_values('Achv', na_position='last').assign(**{'Achv %': lambda x: x['Achv'] * 100, 'Defect %': lambda x: x['Defect_Pct'] * 100,
                                                            'Rework %': lambda x: x['Rework_Pct'] * 100})
    table(P[['Process', 'Machines', 'Plan', 'Output', 'Var', 'Achv %', 'Input', 'WIP', 'Defect %', 'Rework %', 'Downtime_Min', 'Loss_Pcs', 'Status']],
          {'Achv %': pct_cfg('Achv %'), 'Plan': num_cfg('Plan'), 'Output': num_cfg('Output'), 'Var': num_cfg('Var'), 'WIP': num_cfg('WIP (pcs)'),
           'Defect %': num_cfg('Defect %', '%.1f'), 'Rework %': num_cfg('Rework %', '%.1f'), 'Downtime_Min': num_cfg('Downtime (min)'),
           'Loss_Pcs': num_cfg('Loss pcs')}, height=420)
    a, b = st.columns(2)
    with a:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=DT['Process'], y=DT['Plan'], name='Plan', marker_color=GREY_L))
        fig.add_trace(go.Bar(x=DT['Process'], y=DT['Output'], name='Output', marker_color=TEAL))
        fig.update_xaxes(tickangle=-35)
        show(style_fig(fig, 'Plan vs Output by process', h=380))
    with b:
        fig = go.Figure(go.Bar(x=DT['Process'], y=DT['WIP'], marker_color=NAVY, name='WIP'))
        fig.update_xaxes(tickangle=-35)
        show(style_fig(fig, 'WIP by process (opening + input - output)', h=380, legend=False))
    sec('Process x Hour heatmap')
    if style_on:
        z = d_day[d_day['Hour_Idx'] <= until].pivot_table(index='Process', columns='Hour_Idx', values='Output', aggfunc='sum')
        show(fig_heat(z.reindex(columns=[x for x in calc.HOURS if x <= until]), 'Output pcs by process and hour (style filtered)', pct=False))
    else:
        show(fig_heat(calc.dry_heatmap(d_day, mp, unit, until, RUN_H, BASIS), 'Achievement % by process and hour'))
    sec('Process drill-down (hourly)')
    procs = list(DT['Process'])
    if procs:
        pick = st.selectbox('Process', procs, key='dry_pick')
        cap_day = float(mp[(mp['Unit'] == unit) & (mp['Process'] == pick)]['Capacity_per_day'].iloc[0])
        hp = calc.hourly_table(d_day[d_day['Process'] == pick], calc.DRY_NUM, cap_day / RUN_H * BASIS, until,
                               calc.opening_wip(wip, unit, day, pick), DAY_START, with_plan=not style_on)
        a, b = st.columns(2)
        with a:
            show(fig_plan_actual(hp, S, f'{pick}: hourly plan vs output'))
        with b:
            show(fig_flow(hp, f'{pick}: input, output and WIP'))

# ================================================================== QUALITY & DOWNTIME
with tabs[3]:
    sec('Wash quality and rewash')
    a, b = st.columns(2)
    with a:
        g = w_day[w_day['Hour_Idx'] <= until].groupby('Wash_Type').agg(O=('Output', 'sum'), Q=('QC_Inspected', 'sum'), D=('Defect', 'sum'), R=('Rewash', 'sum')).reset_index()
        g['Defect %'] = calc.safe_div(g['D'], g['Q']) * 100
        g['Rewash %'] = calc.safe_div(g['R'], g['O']) * 100
        fig = go.Figure()
        fig.add_trace(go.Bar(x=g['Wash_Type'].replace('', '(not set)'), y=g['Defect %'], name='Defect %', marker_color=RED))
        fig.add_trace(go.Bar(x=g['Wash_Type'].replace('', '(not set)'), y=g['Rewash %'], name='Rewash %', marker_color=ORANGE))
        show(style_fig(fig, 'Defect % and Rewash % by wash type'))
    with b:
        mq = MT[MT['Output'] >= 100].sort_values('Rewash_Pct', ascending=False).head(10)
        fig = go.Figure(go.Bar(x=mq['Rewash_Pct'] * 100, y=mq['Machine_ID'], orientation='h', marker_color=ORANGE, name='Rewash %'))
        fig.update_yaxes(autorange='reversed')
        show(style_fig(fig, 'Top 10 machines by Rewash % (min 100 pcs output)', legend=False))
    sec('Style quality (selected date)')
    sd = calc.style_summary(w_day[w_day['Hour_Idx'] <= until], d_day[d_day['Hour_Idx'] <= until])
    if len(sd):
        sd = sd.assign(**{'Defect %': sd['Defect_Pct'] * 100, 'Rewash %': sd['Rewash_Pct'] * 100})
        table(sd[['Style', 'Output', 'Input', 'Defect %', 'Rewash %', 'Machines', 'Downtime_Min']].sort_values('Rewash %', ascending=False),
              {'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f')}, height=280)
    else:
        st.caption('No style data for this selection.')
    sec('Dry process quality')
    dq = DT[DT['Output'] > 0]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=dq['Process'], y=dq['Defect_Pct'] * 100, name='Defect %', marker_color=RED))
    fig.add_trace(go.Bar(x=dq['Process'], y=dq['Rework_Pct'] * 100, name='Rework %', marker_color=ORANGE))
    fig.update_xaxes(tickangle=-35)
    show(style_fig(fig, 'Dry process: defect % and rework % by process', h=360))
    sec('Downtime Pareto')
    a, b = st.columns(2)
    with a:
        show(fig_pareto(calc.pareto(w_day[w_day['Hour_Idx'] <= until]), 'Wash downtime by reason'))
    with b:
        show(fig_pareto(calc.pareto(d_day[d_day['Hour_Idx'] <= until]), 'Dry process downtime by reason'))

# ================================================================== STYLE EXPLORER
with tabs[4]:
    st.caption('Cross-date style analysis. Use the Style search in the sidebar to narrow the list (no search = all styles).')
    lo = max(first, last - dt.timedelta(days=13))
    rng = st.date_input('Date range', value=(lo, last), min_value=first, max_value=last, key='style_range')
    r0, r1 = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (rng if not isinstance(rng, (tuple, list)) else rng[0],) * 2
    ws_ = calc.apply_filters(wash, unit=unit, d0=r0, d1=r1, styles=styles_active)
    ds_ = calc.apply_filters(dry, unit=unit, d0=r0, d1=r1, styles=styles_active)
    SS = calc.style_summary(ws_, ds_)
    if SS.empty:
        st.info('No style data in this range.')
    else:
        c = st.columns(4)
        kpi(c[0], 'Styles in range', fi(len(SS)), f"{r0:%d %b} - {r1:%d %b}")
        kpi(c[1], 'Wash output', fi(SS['Output'].sum()), 'pcs')
        top_rw = SS.dropna(subset=['Rewash_Pct']).sort_values('Rewash_Pct', ascending=False)
        kpi(c[2], 'Highest rewash %', top_rw.iloc[0]['Style'] if len(top_rw) else '–', fp(top_rw.iloc[0]['Rewash_Pct']) if len(top_rw) else '', 'bad' if len(top_rw) and top_rw.iloc[0]['Rewash_Pct'] > S['Max_Rewash_Pct'] else '')
        top_df = SS.dropna(subset=['Defect_Pct']).sort_values('Defect_Pct', ascending=False)
        kpi(c[3], 'Highest defect %', top_df.iloc[0]['Style'] if len(top_df) else '–', fp(top_df.iloc[0]['Defect_Pct']) if len(top_df) else '', 'bad' if len(top_df) and top_df.iloc[0]['Defect_Pct'] > S['Max_Defect_Pct'] else '')
        sec('Style summary')
        SSd = SS.assign(**{'Defect %': SS['Defect_Pct'] * 100, 'Rewash %': SS['Rewash_Pct'] * 100,
                           'Dry Defect %': SS['Dry_Defect_Pct'] * 100, 'Dry Rework %': SS['Dry_Rework_Pct'] * 100})
        cols = ['Style', 'Output', 'Input', 'Defect %', 'Rewash %', 'Machines', 'Days', 'Downtime_Min', 'Dry_Output', 'Dry Defect %', 'Dry Rework %']
        table(SSd[cols], {'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f'), 'Dry Defect %': num_cfg('Dry Defect %', '%.1f'),
                          'Dry Rework %': num_cfg('Dry Rework %', '%.1f'), 'Dry_Output': num_cfg('Dry output (process-pcs)'), 'Downtime_Min': num_cfg('Downtime (min)')}, height=300)
        st.download_button('Download style summary (CSV)', SSd[cols].to_csv(index=False).encode(), file_name='style_summary.csv', mime='text/csv')
        pick = st.selectbox('Drill into a style', list(SS['Style']), key='style_pick')
        wsel, dsel = ws_[ws_['Style'] == pick], ds_[ds_['Style'] == pick]
        sec(f'Style detail: {pick}')
        a, b = st.columns(2)
        with a:
            gd = wsel.groupby('Date').agg(Output=('Output', 'sum'), Q=('QC_Inspected', 'sum'), D=('Defect', 'sum'), R=('Rewash', 'sum')).reset_index()
            fig = make_subplots(specs=[[{'secondary_y': True}]])
            fig.add_trace(go.Bar(x=gd['Date'], y=gd['Output'], name='Output', marker_color=TEAL), secondary_y=False)
            fig.add_trace(go.Scatter(x=gd['Date'], y=calc.safe_div(gd['D'], gd['Q']) * 100, name='Defect %', mode='lines+markers', line=dict(color=RED)), secondary_y=True)
            fig.add_trace(go.Scatter(x=gd['Date'], y=calc.safe_div(gd['R'], gd['Output']) * 100, name='Rewash %', mode='lines+markers', line=dict(color=ORANGE)), secondary_y=True)
            fig.update_yaxes(ticksuffix='%', showgrid=False, rangemode='tozero', secondary_y=True)
            show(style_fig(fig, 'Daily wash output with defect % and rewash %'))
        with b:
            gh = wsel.groupby('Hour_Idx')['Output'].sum().reindex(calc.HOURS).fillna(0)
            fig = go.Figure(go.Bar(x=[l[:5] for l in LABELS], y=gh.values, marker_color=NAVY, name='Output'))
            show(style_fig(fig, 'Output by hour of day', legend=False))
        a, b = st.columns(2)
        with a:
            gm = wsel.groupby('Machine_ID').agg(Output=('Output', 'sum'), R=('Rewash', 'sum')).reset_index().sort_values('Output', ascending=False).head(12)
            fig = go.Figure(go.Bar(x=gm['Output'], y=gm['Machine_ID'], orientation='h', marker_color=TEAL, name='Output'))
            fig.update_yaxes(autorange='reversed')
            show(style_fig(fig, 'Top machines for this style (output)', legend=False))
        with b:
            gp = dsel.groupby('Process')['Output'].sum().sort_values(ascending=False).reset_index()
            fig = go.Figure(go.Bar(x=gp['Process'], y=gp['Output'], marker_color=AMBER, name='Output'))
            fig.update_xaxes(tickangle=-35)
            show(style_fig(fig, 'Dry process output for this style', legend=False))

# ================================================================== TRENDS
with tabs[5]:
    st.caption('Unit-level trend across dates (style and wash-type filters are not applied here).')
    rng = st.date_input('Trend range', value=(first, last), min_value=first, max_value=last, key='trend_range')
    t0, t1 = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (first, last)
    DY = calc.wash_daily(wash, mm, unit, t0, t1, BASIS)
    if DY.empty:
        st.info('No data in this range.')
    else:
        c = st.columns(5)
        tot_o, tot_p = DY['Output'].sum(), DY['Plan'].sum()
        kpi(c[0], 'Days with data', fi(len(DY)), f"{t0:%d %b} - {t1:%d %b}")
        kpi(c[1], 'Total output', fi(tot_o))
        kpi(c[2], 'Achievement %', fp(tot_o / tot_p if tot_p else np.nan), '', tone_achv(tot_o / tot_p if tot_p else np.nan, S))
        kpi(c[3], 'Defect %', fp(DY['Defect'].sum() / DY['QC_Inspected'].sum() if DY['QC_Inspected'].sum() else np.nan))
        kpi(c[4], 'Rewash %', fp(DY['Rewash'].sum() / tot_o if tot_o else np.nan))
        fig = make_subplots(specs=[[{'secondary_y': True}]])
        fig.add_trace(go.Bar(x=DY['Date'], y=DY['Output'], name='Output', marker_color=TEAL), secondary_y=False)
        fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Plan'], name='Plan', mode='lines', line=dict(color=NAVY, width=2)), secondary_y=False)
        fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Achv'] * 100, name='Achv %', mode='lines+markers', line=dict(color=ORANGE)), secondary_y=True)
        fig.update_yaxes(ticksuffix='%', showgrid=False, rangemode='tozero', secondary_y=True)
        show(style_fig(fig, 'Daily wash output vs plan', h=360))
        a, b = st.columns(2)
        with a:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Defect_Pct'] * 100, name='Defect %', mode='lines+markers', line=dict(color=RED)))
            fig.add_trace(go.Scatter(x=DY['Date'], y=DY['Rewash_Pct'] * 100, name='Rewash %', mode='lines+markers', line=dict(color=ORANGE)))
            fig.update_yaxes(ticksuffix='%', rangemode='tozero')
            show(style_fig(fig, 'Daily defect % and rewash %'))
        with b:
            dwip = []
            for dte in DY['Date']:
                dwip.append(calc.opening_wip(wip, unit, dte, 'WASH') + DY.loc[DY['Date'] == dte, 'Input'].iloc[0] - DY.loc[DY['Date'] == dte, 'Output'].iloc[0])
            fig = go.Figure(go.Scatter(x=DY['Date'], y=dwip, mode='lines+markers', line=dict(color=NAVY), name='Closing WIP'))
            show(style_fig(fig, 'Day-end WASH WIP (opening + input - output)', legend=False))
        sec('Monthly summary')
        MO = calc.monthly(DY)
        MOd = MO.assign(**{'Achv %': MO['Achv'] * 100, 'Defect %': MO['Defect_Pct'] * 100, 'Rewash %': MO['Rewash_Pct'] * 100})
        table(MOd[['Month', 'Days', 'Plan', 'Output', 'Achv %', 'Input', 'Defect %', 'Rewash %', 'Downtime_Min']],
              {'Achv %': pct_cfg('Achv %'), 'Defect %': num_cfg('Defect %', '%.1f'), 'Rewash %': num_cfg('Rewash %', '%.1f'),
               'Plan': num_cfg('Plan'), 'Output': num_cfg('Output'), 'Input': num_cfg('Input'), 'Downtime_Min': num_cfg('Downtime (min)')})
        sec('Dry process achievement by day')
        DD = calc.dry_daily(dry, mp, unit, t0, t1, RUN_H, BASIS)
        if len(DD):
            z = DD.pivot_table(index='Process', columns='Date', values='Achv', aggfunc='mean')
            fig = go.Figure(go.Heatmap(z=z.values, x=[d.strftime('%d %b') for d in z.columns], y=list(z.index), colorscale=HEAT, zmin=0, zmax=1.2, xgap=1, ygap=1,
                                       colorbar=dict(tickformat='.0%', thickness=12)))
            fig.update_yaxes(autorange='reversed')
            show(style_fig(fig, 'Process x Day achievement %', h=max(340, 22 * len(z) + 100), legend=False))
        st.download_button('Download daily trend (CSV)', DY.to_csv(index=False).encode(), file_name=f'daily_trend_{unit}.csv', mime='text/csv')

# ================================================================== DATA HEALTH
with tabs[6]:
    HC = calc.health_checks(w_day if not filters_on else calc.apply_filters(wash, unit=unit, date=day),
                            d_day if not style_on else calc.apply_filters(dry, unit=unit, date=day),
                            mm, mp, unit, until, BASIS, D['rej_w'], D['rej_d'], RUN_H)
    c = st.columns(5)
    kpi(c[0], 'Wash coverage', fp(HC['wash_coverage'], 0), 'machine-hours logged / expected', 'ok' if (HC['wash_coverage'] or 0) >= 0.95 else 'warn')
    kpi(c[1], 'Dry coverage', fp(HC['dry_coverage'], 0), 'process-hours logged / expected', 'ok' if (HC['dry_coverage'] or 0) >= 0.95 else 'warn')
    kpi(c[2], 'Duplicate rows', fi(len(HC['dup_wash']) + len(HC['dup_dry'])), '', 'bad' if len(HC['dup_wash']) + len(HC['dup_dry']) else 'ok')
    kpi(c[3], 'Suspicious rows', fi(len(HC['suspicious_wash']) + len(HC['suspicious_dry'])), 'output > 150% plan, defect > inspected ...', 'warn' if len(HC['suspicious_wash']) + len(HC['suspicious_dry']) else 'ok')
    kpi(c[4], 'Rejected rows (all dates)', fi(len(HC['rejected_wash']) + len(HC['rejected_dry'])), 'bad date / hour / ID', 'bad' if len(HC['rejected_wash']) + len(HC['rejected_dry']) else 'ok')
    if HC['missing_hours']:
        st.warning('Hours with NO wash entries (up to the selected hour): ' + ', '.join(LABELS[h - 1][:5] for h in HC['missing_hours']))
    for title, df in [('Duplicate wash rows (same date, hour, machine)', HC['dup_wash']), ('Duplicate dry rows', HC['dup_dry']),
                      ('Suspicious wash rows', HC['suspicious_wash']), ('Suspicious dry rows', HC['suspicious_dry']),
                      ('Rejected wash rows', HC['rejected_wash']), ('Rejected dry rows', HC['rejected_dry'])]:
        if len(df):
            sec(title)
            table(df.drop(columns=[c_ for c_ in ('Hour_Idx', 'Shift') if c_ in df.columns]).head(300), height=240)
    sec('Export (selected date and unit)')
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button('Hourly table (CSV)', H.to_csv(index=False).encode(), file_name=f'hourly_{unit}_{day:%Y%m%d}.csv', mime='text/csv')
    e2.download_button('Machine table (CSV)', MT.to_csv(index=False).encode(), file_name=f'machines_{unit}_{day:%Y%m%d}.csv', mime='text/csv')
    e3.download_button('Dry process table (CSV)', DT.to_csv(index=False).encode(), file_name=f'dry_{unit}_{day:%Y%m%d}.csv', mime='text/csv')
    e4.download_button('Raw wash rows (CSV)', w_day.to_csv(index=False).encode(), file_name=f'wash_rows_{unit}_{day:%Y%m%d}.csv', mime='text/csv')
