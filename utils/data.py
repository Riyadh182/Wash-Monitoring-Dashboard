"""Data loading: Google Sheets (public link or service account), a local xlsx for testing, or demo data."""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

import pandas as pd
import requests
import streamlit as st

from . import config as C


# ----------------------------------------------------------------------------- raw readers
def _secrets_sheets() -> dict:
    try:
        return {k: str(v) for k, v in dict(st.secrets["sheets"]).items() if str(v).strip()}
    except Exception:
        return {}


def _service_account():
    try:
        return dict(st.secrets["gcp_service_account"])
    except Exception:
        return None


def _local_tab(path: str, tab: str) -> pd.DataFrame:
    """Developer mode: read a (recalculated) xlsx instead of Google Sheets. LOCAL_XLSX=/path/file.xlsx"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    if tab not in wb.sheetnames:
        raise ValueError(f"tab {tab} not in {path}")
    rows = []
    for row in wb[tab].iter_rows(values_only=True):
        out = []
        for v in row:
            if v is None:
                out.append("")
            elif hasattr(v, "strftime"):
                out.append(v.strftime("%Y-%m-%d"))
            else:
                out.append(str(v))
        rows.append(out)
    width = max((len(r) for r in rows), default=0)
    return pd.DataFrame([r + [""] * (width - len(r)) for r in rows], dtype=str)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_tab(sheet_id: str, tab: str) -> pd.DataFrame:
    """Returns the tab as a text table without header handling (header=None)."""
    local = os.environ.get("LOCAL_XLSX")
    if local:
        return _local_tab(local, tab)
    sa = _service_account()
    if sa:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(
            sa, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        ws = gspread.authorize(creds).open_by_key(sheet_id).worksheet(tab)
        vals = ws.get_all_values()
        width = max((len(r) for r in vals), default=0)
        return pd.DataFrame([r + [""] * (width - len(r)) for r in vals], dtype=str)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
    r = requests.get(url, params={"tqx": "out:csv", "sheet": tab, "headers": 0}, timeout=60)
    r.raise_for_status()
    if r.text.lstrip().startswith("<"):
        raise PermissionError("Sheet is not shared (set 'Anyone with the link: Viewer') or the tab name is wrong.")
    return pd.read_csv(io.StringIO(r.text), header=None, dtype=str, keep_default_na=False)


# ----------------------------------------------------------------------------- cleaning helpers
def to_num(s: pd.Series) -> pd.Series:
    t = s.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.strip()
    return pd.to_numeric(t.replace({"": None, "nan": None, "None": None}), errors="coerce")


def to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).replace({"": None, "nan": None, "None": None}), errors="coerce", format="mixed")


def table_with_header(raw: pd.DataFrame, header_row: int = 0) -> pd.DataFrame:
    hdr = [str(x).strip() for x in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 1:].copy()
    df.columns = hdr
    df = df.loc[:, [c for c in df.columns if c != ""]]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]
    return df.reset_index(drop=True)


# ----------------------------------------------------------------------------- parsers
def parse_orders(raw: pd.DataFrame, plant: str) -> pd.DataFrame:
    df = table_with_header(raw)
    if "Order" not in df.columns:
        raise ValueError("Dashboard_Data tab has no 'Order' column")
    df = df[df["Order"].astype(str).str.strip() != ""].copy()
    for c in C.NUM_COLS:
        df[c] = to_num(df[c]) if c in df.columns else 0.0
        df[c] = df[c].fillna(0.0)
    for c in C.DATE_COLS:
        df[c] = to_date(df[c]) if c in df.columns else pd.NaT
    for c in C.TEXT_COLS:
        df[c] = df[c].astype(str).str.strip() if c in df.columns else ""
    df["Wash_Plant"] = plant
    df["Style"] = df["Style"].replace({"": "-", "0": "-"})
    return df.reset_index(drop=True)


def parse_daily(raw: pd.DataFrame, plant: str) -> pd.DataFrame:
    df = table_with_header(raw)
    df["Date"] = to_date(df["Date"])
    df = df.dropna(subset=["Date"]).copy()
    for c in df.columns:
        if c != "Date":
            df[c] = to_num(df[c]).fillna(0.0)
    df["Wash_Plant"] = plant
    return df.reset_index(drop=True)


def parse_hourly(raw: pd.DataFrame, plant: str) -> pd.DataFrame:
    df = table_with_header(raw)
    cols = list(df.columns)
    # the sheet has two columns called "Achievement (%)": keep position based names
    names = ["Date", "Time", "Dry_Target", "Dry_Output", "Dry_Ach", "Wet_Target", "Wet_Output", "Wet_Ach"]
    df = df.iloc[:, :8].copy()
    df.columns = names
    df["Date"] = to_date(df["Date"])
    df = df.dropna(subset=["Date"]).copy()
    df["Is_Total"] = df["Time"].astype(str).str.strip().str.lower() == "total"
    for c in names[2:]:
        df[c] = to_num(df[c])
    for c in ("Dry_Target", "Dry_Output", "Wet_Target", "Wet_Output"):
        df[c] = df[c].fillna(0.0)
    df["Wash_Plant"] = plant
    return df.reset_index(drop=True)


def parse_units(raw: pd.DataFrame, plant: str) -> pd.DataFrame:
    df = table_with_header(raw)
    df = df[df.iloc[:, 0].astype(str).str.strip().ne("")]
    df = df[~df.iloc[:, 0].astype(str).str.upper().eq("TOTAL")]
    out = pd.DataFrame({
        "Wash_Plant": plant,
        "Wet_Capacity_Day": to_num(df.get("Wet_Capacity_Day", pd.Series(dtype=str))).fillna(0.0).head(1).sum(),
        "Dry_Capacity_Day": to_num(df.get("Dry_Capacity_Day", pd.Series(dtype=str))).fillna(0.0).head(1).sum(),
    }, index=[0])
    return out


def parse_board(raw: pd.DataFrame, plant: str, month_start: pd.Timestamp) -> pd.DataFrame:
    """Input_Board / Output_Board -> long table [Order, Date, Qty]. Day number is read from the 'Day n | ..' header."""
    if raw.empty:
        return pd.DataFrame(columns=["Order", "Date", "Qty", "Wash_Plant"])
    hdr_idx = None
    for i in range(min(12, len(raw))):
        if any(re.match(r"\s*Day\s+1\b", str(x)) for x in raw.iloc[i].tolist()):
            hdr_idx = i
            break
    if hdr_idx is None:
        raise ValueError("Board tab: header row with 'Day 1 | ...' not found")
    day_cols = {}
    for j in range(raw.shape[1]):
        m = re.match(r"\s*Day\s+(\d+)", str(raw.iat[hdr_idx, j]))
        if m:
            day_cols[j] = int(m.group(1))
    body = raw.iloc[hdr_idx + 1:]
    body = body[body.iloc[:, 0].astype(str).str.strip().ne("")]
    body = body[~body.iloc[:, 0].astype(str).str.lower().str.startswith("grand total")]
    rows = []
    for j, d in day_cols.items():
        q = to_num(body.iloc[:, j]).fillna(0.0)
        sel = q > 0
        if sel.any():
            rows.append(pd.DataFrame({
                "Order": body.iloc[:, 0][sel].astype(str).str.strip().values,
                "Date": month_start + pd.Timedelta(days=d - 1),
                "Qty": q[sel].values,
            }))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["Order", "Date", "Qty"])
    out["Wash_Plant"] = plant
    return out


# ----------------------------------------------------------------------------- bundle
@dataclass
class Bundle:
    orders: pd.DataFrame
    daily: pd.DataFrame
    hourly: pd.DataFrame
    units: pd.DataFrame
    flow_in: pd.DataFrame
    flow_out: pd.DataFrame
    today: pd.Timestamp
    month_start: pd.Timestamp
    plants: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    demo: bool = False


def configured_plants() -> dict:
    ids = _secrets_sheets()
    if os.environ.get("LOCAL_XLSX"):
        return {os.environ.get("LOCAL_PLANT", "BWL-1"): "local"}
    return ids


def load_all(demo: bool = False) -> Bundle:
    if demo:
        from .demo import make_demo
        return make_demo()
    ids = configured_plants()
    orders, daily, hourly, units, fin, fout = [], [], [], [], [], []
    errors = {}
    for plant, sid in ids.items():
        try:
            o = parse_orders(fetch_tab(sid, C.TAB_ORDERS), plant)
            d = parse_daily(fetch_tab(sid, C.TAB_DAILY), plant)
            h = parse_hourly(fetch_tab(sid, C.TAB_HOURLY), plant)
            try:
                u = parse_units(fetch_tab(sid, C.TAB_UNIT), plant)
            except Exception:
                u = pd.DataFrame({"Wash_Plant": [plant], "Wet_Capacity_Day": [0.0], "Dry_Capacity_Day": [0.0]})
            ms = d["Date"].min() if len(d) else pd.Timestamp.today().normalize().replace(day=1)
            fi = parse_board(fetch_tab(sid, C.TAB_INPUT), plant, ms)
            fo = parse_board(fetch_tab(sid, C.TAB_OUTPUT), plant, ms)
            orders.append(o); daily.append(d); hourly.append(h); units.append(u); fin.append(fi); fout.append(fo)
        except Exception as e:  # one broken plant must not stop the dashboard
            errors[plant] = str(e)[:300]
    cat = lambda xs: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()
    orders_df = cat(orders)
    daily_df = cat(daily)
    today = pd.Timestamp.today().normalize()
    if len(orders_df) and orders_df["Report_Date"].notna().any():
        today = orders_df["Report_Date"].dropna().max().normalize()
    month_start = daily_df["Date"].min() if len(daily_df) else today.replace(day=1)
    return Bundle(orders_df, daily_df, cat(hourly), cat(units), cat(fin), cat(fout), today, month_start,
                  plants=list(ids.keys()), errors=errors)
