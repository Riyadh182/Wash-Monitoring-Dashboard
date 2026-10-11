"""UI helpers: theme-adaptive CSS, KPI cards, static Plotly styling, download buttons."""
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import reports

# vivid colours that read well on BOTH dark and light backgrounds
TEAL, AMBER, CORAL, INDIGO, SKY, VIOLET, GREEN, PINK, SLATE = '#14B8A6', '#F59E0B', '#F43F5E', '#6366F1', '#38BDF8', '#A855F7', '#22C55E', '#EC4899', '#94A3B8'
PALETTE = [TEAL, AMBER, INDIGO, CORAL, SKY, VIOLET, GREEN, PINK, '#F97316', '#84CC16']
RISK_COL = {'Overdue': '#E11D48', 'Critical': '#F97316', 'Watch': '#FACC15'}
HEAT = [[0, '#F43F5E'], [0.45, '#FBBF24'], [0.75, '#86EFAC'], [1, '#14B8A6']]
GRID = 'rgba(148,163,184,0.22)'

CSS = """
<style>
.block-container{padding-top:1.1rem;max-width:1550px}
.hero{background:linear-gradient(120deg,#4338CA,#0D9488 70%,#0EA5E9);color:#fff;border-radius:16px;padding:16px 24px;margin-bottom:12px}
.hero h1{font-size:1.5rem;margin:0;color:#fff;letter-spacing:.03em}
.hero .sub{opacity:.95;font-size:.86rem;margin-top:7px}
.chip{display:inline-block;background:rgba(255,255,255,.2);border-radius:20px;padding:2px 11px;margin:2px 6px 2px 0;font-size:.76rem}
.kpi{background:rgba(148,163,184,.10);border:1px solid rgba(148,163,184,.30);border-top:4px solid #14B8A6;border-radius:14px;padding:10px 16px;margin-bottom:10px}
.kpi .l{font-size:.64rem;letter-spacing:.09em;opacity:.7;font-weight:700;text-transform:uppercase}
.kpi .v{font-size:1.75rem;font-weight:700;line-height:1.2}
.kpi .s{font-size:.74rem;opacity:.7}
.kpi.ok{border-top-color:#22C55E}.kpi.ok .v{color:#22C55E}
.kpi.warn{border-top-color:#F59E0B}.kpi.warn .v{color:#F59E0B}
.kpi.bad{border-top-color:#F43F5E}.kpi.bad .v{color:#F43F5E}
.kpi.info{border-top-color:#6366F1}.kpi.info .v{color:#818CF8}
.sec{font-weight:700;font-size:1.02rem;margin:16px 0 4px 0;border-left:4px solid #6366F1;padding-left:10px}
.note{font-size:.78rem;opacity:.75}
.stPlotlyChart text{fill:currentColor !important}
</style>"""

PLOT_CONFIG = {'displayModeBar': False, 'scrollZoom': False, 'doubleClick': False, 'showAxisDragHandles': False,
               'showTips': False, 'displaylogo': False, 'responsive': True}


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def fi(x):
    return '–' if x is None or pd.isna(x) else f"{x:,.0f}"


def fp(x, d=1):
    return '–' if x is None or pd.isna(x) else f"{x * 100:.{d}f}%"


def ff(x, d=1):
    return '–' if x is None or pd.isna(x) else f"{x:,.{d}f}"


def kpi(col, label, value, sub='', tone=''):
    col.markdown(f'<div class="kpi {tone}"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>', unsafe_allow_html=True)


def sec(text):
    st.markdown(f'<div class="sec">{text}</div>', unsafe_allow_html=True)


def note(text):
    st.markdown(f'<div class="note">{text}</div>', unsafe_allow_html=True)


def _try(fn, *a, **kw):
    """Streamlit renamed width options across versions; try new API, then old, then plain."""
    for extra in ({'width': 'stretch'}, {'use_container_width': True}, {}):
        try:
            return fn(*a, **kw, **extra)
        except TypeError:
            continue
    return fn(*a, **kw)


def style_fig(fig, title, h=330, legend=True, grouped=True):
    """Static (no zoom / pan / drag), transparent background so it follows light AND dark theme."""
    fig.update_layout(title=dict(text=title, x=0, font=dict(size=14)), height=h, margin=dict(l=10, r=10, t=46, b=10), showlegend=legend,
                      legend=dict(orientation='h', y=-0.2, x=0), font=dict(size=11, color='#94A3B8'), paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)', barmode='group' if grouped else 'relative', dragmode=False, hovermode='x unified',
                      bargap=0.22, colorway=PALETTE)
    fig.update_xaxes(fixedrange=True, showgrid=False, linecolor=GRID, zeroline=False)
    fig.update_yaxes(fixedrange=True, gridcolor=GRID, zeroline=False)
    return fig


def show(fig):
    _try(st.plotly_chart, fig, config=PLOT_CONFIG)


def table(df, cfg=None, height=None):
    kw = dict(hide_index=True, column_config=cfg or {})
    if height:
        kw['height'] = height
    _try(st.dataframe, df, **kw)


def pct_cfg(label, mx=120):
    return st.column_config.ProgressColumn(label, format='%.1f', min_value=0, max_value=mx)


def num_cfg(label, fmt='%d'):
    return st.column_config.NumberColumn(label, format=fmt)


def auto_cfg(df, labels=None):
    """Column config from the label map: ints as %d, percents/ratios with one decimal."""
    labels = labels or reports.LABELS
    cfg = {}
    for c in df.columns:
        lab = labels.get(c, c.replace('_', ' '))
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            cfg[c] = st.column_config.DateColumn(lab, format='DD-MMM-YY')
        elif pd.api.types.is_numeric_dtype(df[c]):
            dec = '%.1f' if ('Pct' in c or c in ('DHU', 'Required_Rate', 'Rate3', 'Cap_hr', 'Change_Pct')) else '%d'
            cfg[c] = st.column_config.NumberColumn(lab, format=dec)
        else:
            cfg[c] = st.column_config.TextColumn(lab)
    return cfg


def tone_achv(a, S):
    if a is None or pd.isna(a):
        return ''
    return 'ok' if a >= S['Target_Pct'] else ('warn' if a >= S['Alert_Pct'] else 'bad')


def tone_limit(x, lim):
    if x is None or pd.isna(x):
        return ''
    return 'bad' if x > lim else 'ok'


@st.cache_data(show_spinner=False, max_entries=60)
def _xlsx(sheets):
    return reports.excel_bytes(dict(sheets))


def xlsx_of(sheets: dict):
    # tuple-of-pairs keeps the cache key hashable
    return _xlsx(tuple(sheets.items()))


def downloads(df, name, key, sheet='Data', excel=True):
    """CSV + Excel buttons for one table."""
    e = reports.export_frame(df)
    c1, c2, _ = st.columns([1, 1, 4])
    c1.download_button('⬇ CSV', e.to_csv(index=False).encode('utf-8-sig'), file_name=f'{name}.csv', mime='text/csv', key=f'{key}_csv')
    if excel:
        c2.download_button('⬇ Excel', xlsx_of({sheet: df}), file_name=f'{name}.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=f'{key}_xls')


def bar_plan_actual(x, plan, actual, title, h=340, plan_name='Plan', act_name='Actual'):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=plan, name=plan_name, marker_color=SLATE, opacity=0.55))
    fig.add_trace(go.Bar(x=x, y=actual, name=act_name, marker_color=TEAL))
    return style_fig(fig, title, h)


def rag_colors(vals, hi=95, lo=80):
    return [GREEN if (v is not None and not pd.isna(v) and v >= hi) else (AMBER if (v is not None and not pd.isna(v) and v >= lo) else CORAL) for v in vals]


def hbar(df, x, y, title, color=TEAL, h=340, colors=None, fmt=None):
    fig = go.Figure(go.Bar(x=df[x], y=df[y], orientation='h', marker_color=colors or color, name=x,
                           text=df[x].map(fmt) if fmt else None, textposition='outside', cliponaxis=False))
    fig.update_yaxes(autorange='reversed')
    return style_fig(fig, title, h, legend=False)
