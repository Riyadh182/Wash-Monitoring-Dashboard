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
RISK_COL = {'Overdue': '#E11D48', 'Critical': '#F97316', 'Watch': '#FACC15', 'Overrun': '#A855F7'}
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
.hbw{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px 0}
.hb{flex:1 1 92px;min-width:86px;max-width:130px;border-radius:10px;padding:6px 8px;text-align:center;border:1px solid rgba(148,163,184,.35);background:rgba(148,163,184,.10)}
.hb .h{font-size:.66rem;opacity:.8;font-weight:700;letter-spacing:.04em}
.hb .a{font-size:1.25rem;font-weight:800;line-height:1.25}
.hb .s{font-size:.62rem;opacity:.8}
.hb.ok{background:rgba(34,197,94,.20);border-color:#22C55E}.hb.ok .a{color:#22C55E}
.hb.warn{background:rgba(250,204,21,.22);border-color:#FACC15}.hb.warn .a{color:#EAB308}
.hb.bad{background:rgba(244,63,94,.18);border-color:#F43F5E}.hb.bad .a{color:#F43F5E}
.sbw{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:6px 0 10px 0}
.sb{border-radius:12px;padding:9px 12px;border:1px solid rgba(148,163,184,.35);background:rgba(148,163,184,.10);border-top:4px solid #6366F1}
.sb .l{font-size:.62rem;letter-spacing:.08em;opacity:.75;font-weight:700;text-transform:uppercase}
.sb .v{font-size:1.35rem;font-weight:800;line-height:1.25}
.sb .s{font-size:.7rem;opacity:.75}
.sb.ok{border-top-color:#22C55E}.sb.warn{border-top-color:#F59E0B}.sb.bad{border-top-color:#F43F5E}
.hl{border-radius:14px;padding:12px 18px;margin:6px 0 12px 0;border:1px solid #F43F5E;background:linear-gradient(120deg,rgba(244,63,94,.20),rgba(249,115,22,.12))}
.hl .l{font-size:.68rem;letter-spacing:.09em;font-weight:800;text-transform:uppercase;color:#F43F5E}
.hl .v{font-size:1.6rem;font-weight:800;line-height:1.25}
.hl .s{font-size:.82rem;opacity:.85}
.cc{border-radius:14px;padding:12px 16px;margin:8px 0;border:1px solid rgba(148,163,184,.4);border-left:8px solid #94A3B8;background:rgba(148,163,184,.08)}
.cc.Overdue{border-left-color:#E11D48;background:rgba(225,29,72,.12)}.cc.Critical{border-left-color:#F97316;background:rgba(249,115,22,.12)}.cc.Watch{border-left-color:#FACC15;background:rgba(250,204,21,.12)}
.cc .t{font-weight:800;font-size:1rem}.cc .t span{font-size:.7rem;border-radius:12px;padding:1px 9px;margin-left:8px;color:#fff;background:#94A3B8}
.cc.Overdue .t span{background:#E11D48}.cc.Critical .t span{background:#F97316}.cc.Watch .t span{background:#CA8A04}
.cc .g{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:6px 14px;margin-top:8px}
.cc .g div{font-size:.72rem;opacity:.95}.cc .g b{display:block;font-size:.95rem}
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


ACHV_GREEN, ACHV_YELLOW = 0.80, 0.60      # >= 80% green, 60-80% yellow, < 60% red (everywhere)


def achv_tone(a):
    if a is None or pd.isna(a):
        return ''
    return 'ok' if a >= ACHV_GREEN else ('warn' if a >= ACHV_YELLOW else 'bad')


def hour_boxes(H, until):
    """One small box per hour: hourly output achievement against hourly plan (target), colour by the 3-band rule."""
    out = []
    for r in H[H['Hour_Idx'] <= until].itertuples():
        a = r.Achv if pd.notna(r.Achv) else np.nan
        tone = achv_tone(a)
        txt = '–' if pd.isna(a) else f'{a * 100:.0f}%'
        sub = f'{r.Output:,.0f} / {r.Plan:,.0f}' if pd.notna(r.Plan) else f'{r.Output:,.0f} (no plan)'
        out.append(f'<div class="hb {tone}"><div class="h">{r.Hour}</div><div class="a">{txt}</div><div class="s">{sub}</div></div>')
    st.markdown('<div class="hbw">' + ''.join(out) + '</div>', unsafe_allow_html=True)


def tone_achv(a, S=None):
    if a is None or pd.isna(a):
        return ''
    return achv_tone(a)


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


def rag_colors(vals, hi=80, lo=60):
    return [GREEN if (v is not None and not pd.isna(v) and v >= hi) else (AMBER if (v is not None and not pd.isna(v) and v >= lo) else CORAL) for v in vals]


def hbar(df, x, y, title, color=TEAL, h=340, colors=None, fmt=None):
    fig = go.Figure(go.Bar(x=df[x], y=df[y], orientation='h', marker_color=colors or color, name=x,
                           text=df[x].map(fmt) if fmt else None, textposition='outside', cliponaxis=False))
    fig.update_yaxes(autorange='reversed')
    return style_fig(fig, title, h, legend=False)


# ---------------------------------------------------------------- sidebar order filters (CRD / Buyer / Sewing unit)
CRD_CHOICES = ['All CRDs', 'Overdue (not delivered)', 'Next 7 days', 'Next 14 days', 'Next 30 days', 'Custom range']


def apply_side(F, sf, asof=None):
    """Apply the sidebar CRD / Buyer / Sewing-unit selection to any frame that has Buyer, Sewing_Unit, Eff_CRD, Days_to_CRD, Balance."""
    if not sf or F is None or len(F) == 0:
        return F
    if sf.get('sw'):
        F = F[F['Sewing_Unit'].isin(sf['sw'])]
    if sf.get('by'):
        F = F[F['Buyer'].isin(sf['by'])]
    ch = sf.get('crd', 'All CRDs')
    if ch == 'Overdue (not delivered)':
        F = F[(F['Days_to_CRD'] < 0) & (F['Balance'] > 0)]
    elif ch.startswith('Next'):
        n = int(ch.split()[1])
        F = F[(F['Days_to_CRD'] >= 0) & (F['Days_to_CRD'] <= n)]
    elif ch == 'Custom range' and sf.get('rng') and len(sf['rng']) == 2:
        F = F[(F['Eff_CRD'] >= pd.Timestamp(sf['rng'][0])) & (F['Eff_CRD'] <= pd.Timestamp(sf['rng'][1]))]
    return F


def sbox_row(items):
    """items: list of (label, value, sub, tone). Compact box strip used above style graphs."""
    h = ''.join(f'<div class="sb {t}"><div class="l">{l}</div><div class="v">{v}</div><div class="s">{s}</div></div>' for l, v, s, t in items)
    st.markdown(f'<div class="sbw">{h}</div>', unsafe_allow_html=True)
