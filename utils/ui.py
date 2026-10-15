"""Theme and small UI components (same look as the design board)."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from . import config as C
from .export import to_csv_bytes, to_excel_bytes

CSS = """
<style>
.block-container {padding-top: 1.4rem; max-width: 1500px;}
div[role="radiogroup"] {gap: .25rem 1.2rem;}
.banner {background: linear-gradient(100deg,#4338CA 0%,#1D7FA8 42%,#0F9488 68%,#0EA5E9 100%); border-radius: 18px; padding: 26px 30px; color: #fff; margin: 6px 0 18px 0;}
.banner h1 {margin: 0 0 14px 0; font-size: 1.7rem; letter-spacing: .02em; color:#fff; padding:0;}
.chip {display:inline-block; background: rgba(255,255,255,.2); border-radius: 999px; padding: 4px 14px; font-size: .82rem; margin-right: 8px;}
.kpi {background:#F3F4F8; border:1px solid #E1E4EC; border-radius: 14px; padding: 14px 16px 12px 16px; border-top: 5px solid var(--c); min-height: 118px; margin-bottom: 14px;}
.kpi .l {font-size:.68rem; font-weight:700; letter-spacing:.07em; color:#4B5563; text-transform:uppercase;}
.kpi .v {font-size:1.85rem; font-weight:800; color: var(--c); line-height:1.25;}
.kpi .s {font-size:.76rem; color:#6B7280;}
.sec {border-left: 5px solid #6366F1; padding-left: 10px; font-weight: 700; font-size: 1.05rem; margin: 18px 0 10px 0;}
.note {font-size:.8rem; color:#6B7280;}
.pill-red {background:#FEE2E2;color:#B91C1C;border-radius:8px;padding:2px 8px;font-weight:600;}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def banner(title: str, chips: list[str]):
    c = "".join(f'<span class="chip">{html.escape(x)}</span>' for x in chips)
    st.markdown(f'<div class="banner"><h1>{html.escape(title)}</h1>{c}</div>', unsafe_allow_html=True)


def section(text: str):
    st.markdown(f'<div class="sec">{html.escape(text)}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", color: str = C.C_PURPLE):
    st.markdown(
        f'<div class="kpi" style="--c:{color}"><div class="l">{html.escape(label)}</div>'
        f'<div class="v">{html.escape(str(value))}</div><div class="s">{html.escape(sub)}</div></div>',
        unsafe_allow_html=True)


def n0(x) -> str:
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "-"


def pct(x, d: int = 1) -> str:
    try:
        return "-" if pd.isna(x) else f"{float(x) * 100:.{d}f}%"
    except Exception:
        return "-"


def ach_color(x, good: float = 0.95, warn: float = 0.80) -> str:
    if x is None or pd.isna(x):
        return C.C_PURPLE
    return C.C_GREEN if x >= good else (C.C_AMBER if x >= warn else C.C_ROSE)


def download_buttons(df: pd.DataFrame, name: str, key: str):
    """CSV + Excel buttons for one table."""
    c1, c2, _ = st.columns([1, 1, 6])
    c1.download_button("⬇ CSV", to_csv_bytes(df), f"{name}.csv", "text/csv", key=f"{key}_csv")
    c2.download_button("⬇ Excel", to_excel_bytes({name: df}), f"{name}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key}_xlsx")


def table(df: pd.DataFrame, height: int | None = None):
    st.dataframe(df, use_container_width=True, hide_index=True, height=height)


def fig_layout(fig, title: str = "", height: int = 380):
    fig.update_layout(template="plotly_white", title=dict(text=title, font=dict(size=15)), height=height,
                      margin=dict(l=10, r=10, t=50, b=10), legend=dict(orientation="h", y=-0.18, x=0))
    return fig
