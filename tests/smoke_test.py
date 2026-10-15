"""Smoke test without Streamlit installed: stubs streamlit/plotly, then runs every page with demo data or a local xlsx.
Usage:  python tests/smoke_test.py            (demo data)
        LOCAL_XLSX=/path/recalculated.xlsx python tests/smoke_test.py   (real sheet file)"""
import os, sys, types, runpy
from contextlib import contextmanager
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, n): return getattr(st, n)


class ST:
    def __init__(self): self.session_state = {}; self.sidebar = Ctx(); self.secrets = {}; self.calls = []; self.radio_pick = {}
    def cache_data(self, *a, **k):
        if a and callable(a[0]): a[0].clear = lambda: None; return a[0]
        def deco(f): f.clear = lambda: None; return f
        return deco
    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec); return [Ctx() for _ in range(n)]
    def tabs(self, labels): return [Ctx() for _ in labels]
    def expander(self, *a, **k): return Ctx()
    def spinner(self, *a, **k): return Ctx()
    def radio(self, label, options, **k):
        return self.radio_pick.get(k.get("key") or label, options[0])
    def selectbox(self, label, options, **k): return options[0]
    def multiselect(self, *a, **k): return []
    def checkbox(self, label, value=False, **k): return value
    def slider(self, label, mn=0, mx=0, value=None, **k): return value if value is not None else mn
    def number_input(self, label, mn=0, mx=0, value=0, **k): return value
    def date_input(self, label, value=None, **k): return value
    def text_input(self, *a, **k): return ""
    def button(self, *a, **k): return False
    def stop(self): raise SystemExit
    def __getattr__(self, n):
        def f(*a, **k):
            self.calls.append(n); return None
        return f


st = ST()
sys.modules["streamlit"] = st
sys.modules["requests"] = MagicMock()
pl = MagicMock(); sys.modules["plotly"] = pl; sys.modules["plotly.graph_objects"] = pl.graph_objects

import pandas as pd
from utils import data, metrics as M
from views import overview, hourly, reports, crisis

demo = not os.environ.get("LOCAL_XLSX")
b = data.load_all(demo)
print("loaded", "demo" if demo else "xlsx", "orders", len(b.orders), "daily", len(b.daily), "hourly", len(b.hourly), "in", len(b.flow_in), "out", len(b.flow_out), "errors", b.errors)
o = M.add_calc(b.orders, b.today)
overview.render(b, o)
for pick in ("Wash plant", "Sewing unit", "Buyer", "CRD", "Orders"):
    st.radio_pick["ov_view"] = pick; overview.render(b, o)
d = pd.Timestamp(b.today)
hourly.render(b, None, d, 24); hourly.render(b, [b.plants[0]], d, 12)
for which in ("Plan execution", "Daily input / output", "WIP"):
    st.radio_pick["rp_which"] = which
    for g in ("Wash plant", "Sewing unit", "Wash plant x Sewing unit", "Buyer", "Orders (detail)"):
        st.radio_pick["rp_pe_g"] = g
        for w in ("All wash plants", "Wash plant wise", "Sewing unit wise", "Buyer wise", "Sewing unit x Buyer", "CRD wise"):
            st.radio_pick["rp_wip_g"] = w; reports.render(b, o)
crisis.render(b, o)
t = M.daily_wash_type(b.flow_in, b.flow_out, o, b.month_start, 30)
print(t.iloc[:, :6].to_string())
c = M.crisis_table(o, b.today); print("crisis rows", len(c))
k = M.kpis(o, b.units); print({x: (round(v, 2) if isinstance(v, float) else v) for x, v in k.items() if x != "max_hold"}, k["max_hold"])
from utils.export import to_excel_bytes, to_csv_bytes
assert len(to_excel_bytes({"a": M.overview_table(o, "Wash_Plant")})) > 1000
print("SMOKE TEST OK")
