"""Wash & Dry Process - Monitoring Dashboard (Streamlit). Run: streamlit run app.py"""
import datetime as dt
import types
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Wash & Dry Monitoring', page_icon='🧺', layout='wide', initial_sidebar_state='expanded')

import calc
import data
import views_plant as VP
import views_portfolio as VF
import views_board as VB
import board
from ui import inject_css, kpi, sec, show

inject_css()

NAV = ['🌐 Overview', '📋 Plan Execution', '🗓 Daily Board', '📍 PO Tracker', '🚨 CRD Crisis', '📑 Reports', '🛡 Audit & History',
       '⏱ Hourly Monitor', '🏭 Machines', '🔥 Dry Process', '⚖️ Capacity', '🧪 Quality & Downtime', '👗 Style Explorer', '📈 Trends', '🩺 Data Health']
PLANT_PAGES = ('⏱ Hourly Monitor', '🏭 Machines', '🔥 Dry Process', '⚖️ Capacity', '🧪 Quality & Downtime', '👗 Style Explorer', '📈 Trends', '🩺 Data Health')
PORTFOLIO_PAGES = ('🌐 Overview', '📋 Plan Execution', '📍 PO Tracker', '🚨 CRD Crisis', '📑 Reports')


@st.cache_data(show_spinner='Calculating all plants...', max_entries=4, ttl=data.refresh_seconds())
def cached_status(_D, version, day, until):
    return calc.all_status(_D['wash'], _D['order'], _D['plan'], _D['units'], day, until, _D['settings']['Day_Start_Hour'], _D['settings']['Output_Lag_Days'])


@st.cache_data(show_spinner='Calculating plan board...', max_entries=4, ttl=data.refresh_seconds())
def cached_board_status(_D, version, day):
    return board.board_status(_D['board_orders'], _D['board_daily'], day, _D['hist'], _D['audit'])


@st.cache_data(show_spinner=False, max_entries=4, ttl=data.refresh_seconds())
def cached_board_pdaily(_D, version, d0, d1):
    return board.board_plant_daily(_D['board_orders'], _D['board_daily'], _D['units'], d0, d1)


@st.cache_data(show_spinner=False, max_entries=4, ttl=data.refresh_seconds())
def cached_pdaily(_D, version, d0, d1):
    return calc.all_plant_daily(_D['wash'], _D['wip'], _D['units'], d0, d1)


# ------------------------------------------------------------------ data + sidebar
with st.sidebar:
    st.markdown('### 🧺 Wash & Dry Monitor')
    secrets_ok = data.secrets_ready()
    use_demo = st.checkbox('Use demo data', value=not secrets_ok, disabled=not secrets_ok, help='Bundled demo data (10 plants x 1 month). Connect Google Sheets in Secrets for live data.')
    history = st.checkbox('Include history (archive sheets)', value=False, help='Loads the archive sheets listed in Secrets (YYYY-MM:SheetID) for the months you pick. Closed months are cached for a day.')
    hist_months, hist_hourly = (), False
    if history:
        am = data.archive_months()
        hist_months = tuple(st.multiselect('History months', am, default=am[-2:], help='Pick only the months you need: 5 years = 60 months x 10 sheets.'))
        hist_hourly = st.checkbox('Also load hourly logs of those months', value=False)

D = data.load_all(use_demo, history, hist_months, hist_hourly)
S = D['settings']
if D.get('error'):
    st.warning('Could not read your Google Sheet, showing DEMO data instead. Check: Sheet shared as "Anyone with the link", Sheet ID correct, tab names exact. Details: ' + D['error'])
wash, dry, wip, mm, mp = D['wash'], D['dry'], D['wip'], D['machine'], D['process']
RUN_H, BASIS, DAY_START = S['Run_Hours'], S['Plan_Basis'], S['Day_Start_Hour']
LABELS = calc.hour_labels(DAY_START)
units = D['units']
if not units:
    st.error('No units found. Check Master_Machine / Wash_Log tabs.')
    st.stop()

with st.sidebar:
    unit = st.selectbox('Wash plant (for plant views)', units)
    uw, ud = wash[wash['Unit'] == unit], dry[dry['Unit'] == unit]
    bd = D['board_daily']
    bdates = set(bd.loc[(bd['SEW_ACT'] > 0) | (bd['WASH_ACT'] > 0), 'Date']) if len(bd) else set()
    all_dates = sorted(set(wash['Date'].dropna()) | set(dry['Date'].dropna()) | bdates)
    last = all_dates[-1].date() if all_dates else dt.date.today()
    first = all_dates[0].date() if all_dates else last
    date = st.date_input('Date', value=last, min_value=first, max_value=max(last, dt.date.today()))
    day = pd.Timestamp(date)
    w_all = calc.apply_filters(wash, unit=unit, date=day)
    d_all = calc.apply_filters(dry, unit=unit, date=day)
    max_h = int(max(w_all['Hour_Idx'].max() if len(w_all) else 0, d_all['Hour_Idx'].max() if len(d_all) else 0)) or 24
    until = st.select_slider('Till hour', options=calc.HOURS, value=max_h, key=f'until_{unit}_{date}', format_func=lambda i: f"{i}  ({LABELS[i - 1][-5:]})")
    st.markdown('---')
    q = st.text_input('Style search', placeholder='e.g. ST-4412 or Snow').strip()
    styles_all = sorted((set(uw['Style']) | set(ud['Style'])) - {calc.NO_STYLE})
    matches = [s for s in styles_all if q.lower() in s.lower()] if q else []
    sel = st.multiselect('Matching styles', matches, default=matches, key=f'sty_{unit}_{q.lower()}') if q else []
    if q and not matches:
        st.warning('No style matches this search.')
    styles_active = (sel or ['__none__']) if q else None
    wtypes = st.multiselect('Wash type', sorted(t for t in uw['Wash_Type'].unique() if t and t != 'nan'), default=[]) or None
    st.markdown('---')
    if st.checkbox('Auto-refresh every 60 s', value=False):
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=60000, key='autorefresh')
        except Exception:
            st.caption('Install streamlit-autorefresh to enable.')
    if st.button('Refresh data now'):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Rows loaded: wash {len(wash):,} | dry {len(dry):,}")
    st.caption('Source: ' + ('DEMO data' if D['demo'] else 'Google Sheets (cached)'))

# ------------------------------------------------------------------ context
filters_on = bool(styles_active) or bool(wtypes)
style_on = bool(styles_active)
X = types.SimpleNamespace(D=D, S=S, wash=wash, dry=dry, wip=wip, mm=mm, mp=mp, unit=unit, units=units, day=day, until=until, first=first, last=last,
                          LABELS=LABELS, DAY_START=DAY_START, RUN_H=RUN_H, BASIS=BASIS, styles_active=styles_active, wtypes=wtypes,
                          filters_on=filters_on, style_on=style_on, cache={})
X.w_day = calc.apply_filters(wash, unit=unit, date=day, styles=styles_active, wash_types=wtypes)
X.d_day = calc.apply_filters(dry, unit=unit, date=day, styles=styles_active)
X.plan_hr = calc.unit_plan_per_hr(mm, unit, BASIS)
X.std_hr = calc.unit_plan_per_hr(mm, unit, 1.0)
X.open_w = calc.opening_wip(wip, unit, day, 'WASH')
X.caps = calc.unit_capacity(D['unit_master'], mm, mp, units, RUN_H, BASIS)
X.dp = calc.order_daily_plan(D['order'], D['plan'], unit, S['Output_Lag_Days'])
X.H = None

view = st.radio('Section', NAV, horizontal=True, label_visibility='collapsed', key='nav')

chips = f'<span class="chip">{day:%A, %d %b %Y}</span><span class="chip">Till hour {until} ({LABELS[until - 1][-5:]})</span>'
if view in PLANT_PAGES:
    chips = f'<span class="chip">Plant {unit}</span>' + chips
else:
    chips = f'<span class="chip">All {len(units)} wash plants</span>' + chips
if q:
    chips += f'<span class="chip">Style: {q}</span>'
if wtypes:
    chips += f'<span class="chip">Wash: {", ".join(wtypes)}</span>'
if D['demo']:
    chips += '<span class="chip" style="background:#F43F5E">DEMO DATA</span>'
st.markdown(f'<div class="hero"><h1>WASH &amp; DRY PROCESS | MONITORING</h1><div class="sub">{chips}</div></div>', unsafe_allow_html=True)

# portfolio frames only when needed (plan-board mode when a Plan_Board exists, otherwise hourly-log mode)
X.board_mode = len(D['board_orders']) > 0
if view in PORTFOLIO_PAGES:
    if X.board_mode:
        X.S_all = cached_board_status(D, D['version'], day)
        X.pdaily = cached_board_pdaily(D, D['version'], pd.Timestamp(first), day) if view == '📑 Reports' else None
        if view == '🚨 CRD Crisis' or view == '🌐 Overview':
            st.caption('Source: Plan Board (daily). Hourly pages use the hourly logs.')
    else:
        X.S_all = cached_status(D, D['version'], day, until)
        X.pdaily = cached_pdaily(D, D['version'], pd.Timestamp(first), day) if view == '📑 Reports' else None
elif view in ('🗓 Daily Board', '🛡 Audit & History'):
    pass
if view in ('📋 Plan Execution', '📍 PO Tracker', '🗓 Daily Board', '🛡 Audit & History') and not X.board_mode:
    st.warning('These pages need the Plan_Board tab. Add it to the Google Sheet (template: Plan_Board_<PLANT>_<MONTH>.xlsx) or tick "Use demo data".')
    st.stop()

if view in ('⏱ Hourly Monitor', '🏭 Machines', '🧪 Quality & Downtime', '🩺 Data Health') and filters_on:
    st.info('Style / wash-type filter is ON: plan, achievement and WIP are hidden (plan is not defined per style). Actuals are filtered.')
if view in ('⏱ Hourly Monitor', '🏭 Machines', '🔥 Dry Process') and not len(w_all) and not len(d_all):
    st.warning('No numbers entered yet for this date and plant. Showing plan only.')

if view == '⏱ Hourly Monitor' or view == '🧪 Quality & Downtime' or view == '🩺 Data Health':
    H = VP.hourly_tbl(X)
    X.K = calc.wash_kpis(H, until)
    daily_all = calc.wash_daily(wash, mm, unit, first, last, BASIS)
    X.avg_out = daily_all['Output'].tail(7).mean() if len(daily_all) else np.nan

if view == '🌐 Overview':
    VF.overview(X)
elif view == '📋 Plan Execution':
    VB.plan_exec(X)
elif view == '🗓 Daily Board':
    VB.daily_board(X)
elif view == '📍 PO Tracker':
    VB.po_tracker(X)
elif view == '🛡 Audit & History':
    VB.audit_view(X)
elif view == '⏱ Hourly Monitor':
    VP.hourly(X)
elif view == '🏭 Machines':
    VP.machines(X)
elif view == '🔥 Dry Process':
    VP.dry(X)
elif view == '⚖️ Capacity':
    VF.capacity(X)
elif view == '🚨 CRD Crisis':
    VF.crisis(X)
elif view == '🧪 Quality & Downtime':
    VP.quality(X)
elif view == '👗 Style Explorer':
    VP.style_view(X)
elif view == '📈 Trends':
    VP.trends(X)
elif view == '📑 Reports':
    VF.reports_view(X)
else:
    VP.health(X)
