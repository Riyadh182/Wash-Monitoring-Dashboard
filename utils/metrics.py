"""All calculations. Pure pandas, no Streamlit, so they can be tested alone."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

LABELS = {
    "Wash_Plant": "Wash plant", "Sewing_Unit": "Sewing unit", "Buyer": "Buyer", "Style": "Style", "PO": "PO", "Color": "Color",
    "Wash_Type": "Wash type", "CRD": "CRD", "Orders": "Orders", "Order_Qty": "Order qty",
    "Input_Plan_Till_Today": "Plan input (till today)", "Total_Sewing_Input": "Actual input", "Input_Var": "Input variation",
    "Input_Ach": "Input achv %", "Output_Plan_Till_Today": "Plan output (till today)", "Total_Wash_Output": "Actual output",
    "Output_Var": "Output variation", "Output_Ach": "Output achv %", "Dry_Plan_Till_Today": "Dry plan (till today)",
    "Total_Dry_Output": "Dry output", "Wash_WIP": "Wash WIP", "Rewash_WIP": "Rewash WIP", "Total_WIP": "Total WIP",
    "Wash_Balance": "Wash balance", "Sewing_Balance": "Sewing balance", "Month_Input_Plan": "Month input plan",
    "Month_Output_Plan": "Month output plan", "Month_Dry_Plan": "Month dry plan", "Holding_Days": "Holding days",
    "Days_To_CRD": "Days to CRD", "Order": "Order",
}


def safe_div(a, b):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    return np.where(b > 0, a / b, np.nan)


def add_calc(orders: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    df = orders.copy()
    if df.empty:
        for c in ("Days_To_CRD", "CRD_Bucket", "Input_Var", "Output_Var", "Input_Ach", "Output_Ach"):
            df[c] = []
        return df
    df["Days_To_CRD"] = (df["CRD"] - today).dt.days
    df["Input_Var"] = df["Total_Sewing_Input"] - df["Input_Plan_Till_Today"]
    df["Output_Var"] = df["Total_Wash_Output"] - df["Output_Plan_Till_Today"]
    df["Input_Ach"] = safe_div(df["Total_Sewing_Input"], df["Input_Plan_Till_Today"])
    df["Output_Ach"] = safe_div(df["Total_Wash_Output"], df["Output_Plan_Till_Today"])
    df["CRD_Bucket"] = np.select(
        [df["Days_To_CRD"] < 0, df["Days_To_CRD"] <= C.CRISIS_DAYS],
        ["Overdue", f"Next {C.CRISIS_DAYS} days"], default="Later")
    df["CRD_Bucket"] = np.where(df["CRD"].isna(), "No CRD", df["CRD_Bucket"])
    return df


def apply_filters(df: pd.DataFrame, plants=None, units=None, buyers=None, crds=None, open_only=False,
                  style_q: str = "", wash_types=None) -> pd.DataFrame:
    out = df
    if plants:
        out = out[out["Wash_Plant"].isin(plants)]
    if units:
        out = out[out["Sewing_Unit"].isin(units)]
    if buyers:
        out = out[out["Buyer"].isin(buyers)]
    if crds:
        out = out[out["CRD"].dt.strftime("%Y-%m-%d").isin(crds)]
    if open_only:
        out = out[(out["Wash_Balance"] > 0) | (out["Total_WIP"] > 0)]
    if style_q:
        q = style_q.strip().lower()
        out = out[out["Style"].str.lower().str.contains(q, regex=False) | out["Order"].str.lower().str.contains(q, regex=False)]
    if wash_types:
        out = out[out["Wash_Type"].isin(wash_types)]
    return out


def kpis(df: pd.DataFrame, units: pd.DataFrame, plants=None) -> dict:
    u = units if not plants else units[units["Wash_Plant"].isin(plants)]
    k = {
        "wet_cap": float(u["Wet_Capacity_Day"].sum()) if len(u) else 0.0,
        "dry_cap": float(u["Dry_Capacity_Day"].sum()) if len(u) else 0.0,
        "n_plants": int(df["Wash_Plant"].nunique()) if len(df) else 0,
        "orders": int(len(df)),
        "styles_unique": int(df["Style"].nunique()) if len(df) else 0,
        "qty": float(df["Order_Qty"].sum()),
        "plan_in": float(df["Input_Plan_Till_Today"].sum()),
        "act_in": float(df["Total_Sewing_Input"].sum()),
        "plan_out": float(df["Output_Plan_Till_Today"].sum()),
        "act_out": float(df["Total_Wash_Output"].sum()),
        "month_in": float(df["Month_Input_Plan"].sum()),
        "month_out": float(df["Month_Output_Plan"].sum()),
        "month_dry": float(df["Month_Dry_Plan"].sum()),
        "dry_plan": float(df["Dry_Plan_Till_Today"].sum()),
        "dry_out": float(df["Total_Dry_Output"].sum()),
        "wip": float(df["Total_WIP"].sum()),
        "rewash_wip": float(df["Rewash_WIP"].sum()),
        "balance": float(df["Wash_Balance"].sum()),
        "sew_balance": float(df["Sewing_Balance"].sum()),
    }
    k["in_var"] = k["act_in"] - k["plan_in"]
    k["out_var"] = k["act_out"] - k["plan_out"]
    k["in_ach"] = k["act_in"] / k["plan_in"] if k["plan_in"] > 0 else np.nan
    k["out_ach"] = k["act_out"] / k["plan_out"] if k["plan_out"] > 0 else np.nan
    k["dry_ach"] = k["dry_out"] / k["dry_plan"] if k["dry_plan"] > 0 else np.nan
    if len(df) and "Days_To_CRD" in df:
        crisis = df[(df["Wash_Balance"] > 0) & (df["Days_To_CRD"] <= C.CRISIS_DAYS)]
        nxt = df[(df["Days_To_CRD"] >= 0) & (df["Days_To_CRD"] <= C.CRISIS_DAYS)]
        k["crisis_orders"] = int(len(crisis)); k["crisis_pcs"] = float(crisis["Wash_Balance"].sum())
        k["next7_orders"] = int(len(nxt)); k["next7_wip"] = float(nxt["Total_WIP"].sum()); k["next7_balance"] = float(nxt["Wash_Balance"].sum())
        k["next7_styles"] = int(nxt["Style"].nunique())
        wipd = df[df["Total_WIP"] > 0]
        if len(wipd):
            r = wipd.sort_values("Holding_Days", ascending=False).iloc[0]
            k["max_hold"] = dict(days=int(r["Holding_Days"]), buyer=r["Buyer"], style=r["Style"], plant=r["Wash_Plant"], wip=float(r["Total_WIP"]))
        else:
            k["max_hold"] = None
    else:
        k.update(crisis_orders=0, crisis_pcs=0.0, next7_orders=0, next7_wip=0.0, next7_balance=0.0, next7_styles=0, max_hold=None)
    return k


SUM_COLS = ["Order_Qty", "Input_Plan_Till_Today", "Total_Sewing_Input", "Output_Plan_Till_Today", "Total_Wash_Output",
            "Dry_Plan_Till_Today", "Total_Dry_Output", "Wash_WIP", "Rewash_WIP", "Total_WIP", "Wash_Balance", "Sewing_Balance"]


def group_table(df: pd.DataFrame, by, cols=None) -> pd.DataFrame:
    """Overall / by plant / unit / buyer / CRD table with plan-vs-actual."""
    cols = cols or SUM_COLS
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    if by is None:
        d["_all"] = "All"
        keys = ["_all"]
    else:
        keys = [by] if isinstance(by, str) else list(by)
        if "CRD" in keys:
            d["CRD"] = d["CRD"].dt.strftime("%Y-%m-%d").fillna("No CRD")
    g = d.groupby(keys, dropna=False).agg(Orders=("Order", "count"), **{c: (c, "sum") for c in cols}).reset_index()
    g["Input_Var"] = g["Total_Sewing_Input"] - g["Input_Plan_Till_Today"]
    g["Input_Ach"] = safe_div(g["Total_Sewing_Input"], g["Input_Plan_Till_Today"]) * 100
    g["Output_Var"] = g["Total_Wash_Output"] - g["Output_Plan_Till_Today"]
    g["Output_Ach"] = safe_div(g["Total_Wash_Output"], g["Output_Plan_Till_Today"]) * 100
    if by is None:
        g = g.drop(columns=["_all"])
    return g.sort_values(keys[0] if by is not None else "Orders", ascending=by is not None).reset_index(drop=True)


OVERVIEW_ORDER = ["Orders", "Order_Qty", "Input_Plan_Till_Today", "Total_Sewing_Input", "Input_Var", "Input_Ach", "Output_Plan_Till_Today",
                  "Total_Wash_Output", "Output_Var", "Output_Ach", "Total_WIP", "Wash_Balance"]


def overview_table(df: pd.DataFrame, by) -> pd.DataFrame:
    g = group_table(df, by)
    if g.empty:
        return g
    keys = [] if by is None else ([by] if isinstance(by, str) else list(by))
    return g[keys + OVERVIEW_ORDER].round(1)


PLAN_EXEC_COLS = ["Orders", "Order_Qty", "Month_Input_Plan", "Input_Plan_Till_Today", "Total_Sewing_Input", "Input_Var", "Input_Ach",
                  "Month_Output_Plan", "Output_Plan_Till_Today", "Total_Wash_Output", "Output_Var", "Output_Ach",
                  "Dry_Plan_Till_Today", "Total_Dry_Output", "Total_WIP", "Wash_Balance", "Sewing_Balance"]


def plan_execution_table(df: pd.DataFrame, by) -> pd.DataFrame:
    g = group_table(df, by, SUM_COLS + ["Month_Input_Plan", "Month_Output_Plan"])
    if g.empty:
        return g
    keys = [by] if isinstance(by, str) else list(by)
    tot = {k: "TOTAL" if i == 0 else "" for i, k in enumerate(keys)}
    body = g[keys + PLAN_EXEC_COLS]
    t = body[PLAN_EXEC_COLS].sum(numeric_only=True)
    t["Input_Ach"] = t["Total_Sewing_Input"] / t["Input_Plan_Till_Today"] * 100 if t["Input_Plan_Till_Today"] > 0 else np.nan
    t["Output_Ach"] = t["Total_Wash_Output"] / t["Output_Plan_Till_Today"] * 100 if t["Output_Plan_Till_Today"] > 0 else np.nan
    t = pd.concat([pd.Series(tot), t])
    return pd.concat([body, t.to_frame().T], ignore_index=True).round(1)


ORDER_DETAIL_COLS = ["Wash_Plant", "Sewing_Unit", "Buyer", "Style", "PO", "Color", "Wash_Type", "CRD", "Order_Qty", "Month_Input_Plan",
                     "Input_Plan_Till_Today", "Total_Sewing_Input", "Input_Var", "Input_Ach", "Month_Output_Plan", "Output_Plan_Till_Today",
                     "Total_Wash_Output", "Output_Var", "Output_Ach", "Total_Dry_Output", "Total_WIP", "Wash_Balance", "Sewing_Balance", "Risk"]


def order_detail(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["Input_Ach"] = d["Input_Ach"] * 100
    d["Output_Ach"] = d["Output_Ach"] * 100
    d["CRD"] = d["CRD"].dt.strftime("%Y-%m-%d")
    return d[ORDER_DETAIL_COLS].sort_values(["Wash_Plant", "Sewing_Unit", "CRD"]).round(1).reset_index(drop=True)


WIP_COLS = ["Orders", "Order_Qty", "Total_Sewing_Input", "Total_Wash_Output", "Wash_WIP", "Rewash_WIP", "Total_WIP", "Wash_Balance", "Sewing_Balance"]


def wip_table(df: pd.DataFrame, by) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    if by is None:
        d["_all"] = "All wash plants"
        keys = ["_all"]
    else:
        keys = [by] if isinstance(by, str) else list(by)
        if "CRD" in keys:
            d["CRD"] = d["CRD"].dt.strftime("%Y-%m-%d").fillna("No CRD")
    g = d.groupby(keys, dropna=False).agg(Orders=("Order", "count"), **{c: (c, "sum") for c in WIP_COLS[1:]}).reset_index()
    g = g.sort_values("Total_WIP", ascending=False) if by not in ("CRD",) else g.sort_values(keys[0])
    tot = g[WIP_COLS].sum(numeric_only=True)
    trow = pd.concat([pd.Series({k: "TOTAL" if i == 0 else "" for i, k in enumerate(keys)}), tot]).to_frame().T
    out = pd.concat([g, trow], ignore_index=True)
    out = out.rename(columns={"_all": "Scope"})
    return out.round(1)


def crisis_table(df: pd.DataFrame, today: pd.Timestamp, days: int = C.CRISIS_DAYS, behind: float = C.BEHIND_PCT) -> pd.DataFrame:
    d = df[(df["Wash_Balance"] > 0) | (df["Total_WIP"] > 0)].copy()
    if d.empty:
        return d
    ratio = pd.Series(safe_div(d["Total_Wash_Output"], d["Output_Plan_Till_Today"]), index=d.index)
    d["Output_vs_Plan"] = ratio
    crd_hit = (d["Days_To_CRD"] <= days) & (d["Wash_Balance"] > 0)
    behind_hit = (d["Output_Plan_Till_Today"] > 0) & (ratio < behind)
    d = d[crd_hit | behind_hit].copy()
    if d.empty:
        return d
    reason = []
    for _, r in d.iterrows():
        rs = []
        if r["Days_To_CRD"] < 0 and r["Wash_Balance"] > 0:
            rs.append("CRD overdue")
        elif r["Days_To_CRD"] <= days and r["Wash_Balance"] > 0:
            rs.append(f"CRD in {int(r['Days_To_CRD'])}d")
        if r["Output_Plan_Till_Today"] > 0 and r["Output_vs_Plan"] < behind:
            rs.append("Behind output plan")
        if r["Sewing_Balance"] > 0:
            rs.append("Sewing pending")
        reason.append(", ".join(rs))
    d["Crisis_Reason"] = reason
    d["Gap_Pcs"] = d["Output_Plan_Till_Today"] - d["Total_Wash_Output"]
    d["Sewing_Pending"] = np.where(d["Sewing_Balance"] > 0, "Yes", "No")
    d["Level"] = np.select([d["Days_To_CRD"] < 0, d["Days_To_CRD"] <= 3], ["Overdue", "Critical"], default="Watch")
    return d.sort_values(["Days_To_CRD", "Gap_Pcs"], ascending=[True, False]).reset_index(drop=True)


CRISIS_COLS = ["Level", "Wash_Plant", "Style", "Buyer", "PO", "Color", "Wash_Type", "CRD", "Days_To_CRD", "Order_Qty",
               "Output_Plan_Till_Today", "Total_Dry_Output", "Total_Wash_Output", "Output_vs_Plan", "Gap_Pcs", "Sewing_Pending",
               "Sewing_Balance", "Total_WIP", "Wash_Balance", "Crisis_Reason"]
CRISIS_LABELS = {"Output_Plan_Till_Today": "Plan till now", "Total_Dry_Output": "Dry process output", "Total_Wash_Output": "Wash output",
                 "Output_vs_Plan": "Output vs plan %", "Gap_Pcs": "Gap vs plan (pcs)", "Sewing_Pending": "Sewing balance?",
                 "Sewing_Balance": "Sewing balance (pcs)", "Wash_Balance": "Wash balance (pcs)", "Crisis_Reason": "Reason"}


def crisis_display(c: pd.DataFrame) -> pd.DataFrame:
    if c.empty:
        return c
    x = c[CRISIS_COLS].copy()
    x["CRD"] = x["CRD"].dt.strftime("%Y-%m-%d")
    x["Output_vs_Plan"] = (x["Output_vs_Plan"] * 100).round(1)
    return x.rename(columns={**LABELS, **CRISIS_LABELS})


# ----------------------------------------------------------------------------- hourly
def hourly_view(hourly: pd.DataFrame, date: pd.Timestamp, plants=None, till_idx: int = 24):
    h = hourly[(hourly["Date"] == date) & (~hourly["Is_Total"])]
    if plants:
        h = h[h["Wash_Plant"].isin(plants)]
    if h.empty:
        return pd.DataFrame(columns=["Idx", "Time", "Dry_Target", "Dry_Output", "Wet_Target", "Wet_Output", "Dry_Ach", "Wet_Ach"])
    order = {t: i for i, t in enumerate(h.drop_duplicates("Time")["Time"].tolist())}
    g = h.groupby("Time", sort=False)[["Dry_Target", "Dry_Output", "Wet_Target", "Wet_Output"]].sum().reset_index()
    g["Idx"] = g["Time"].map(order) + 1
    g = g[g["Idx"] <= till_idx].sort_values("Idx").reset_index(drop=True)
    g["Dry_Ach"] = safe_div(g["Dry_Output"], g["Dry_Target"]) * 100
    g["Wet_Ach"] = safe_div(g["Wet_Output"], g["Wet_Target"]) * 100
    return g


def last_hour_with_output(hv: pd.DataFrame):
    x = hv[(hv["Dry_Output"] > 0) | (hv["Wet_Output"] > 0)]
    return None if x.empty else x.iloc[-1]


# ----------------------------------------------------------------------------- daily wash type report
def daily_wash_type(flow_in: pd.DataFrame, flow_out: pd.DataFrame, orders: pd.DataFrame, month_start: pd.Timestamp,
                    n_days: int, plants=None) -> pd.DataFrame:
    """Rows: wash type x (Input, Output). Columns: Total (left) then Day 1..Day n."""
    wt = orders[["Wash_Plant", "Order", "Wash_Type"]].drop_duplicates()

    def prep(f):
        if f.empty:
            return pd.DataFrame(columns=["Wash_Plant", "Order", "Date", "Qty", "Wash_Type"])
        x = f.merge(wt, on=["Wash_Plant", "Order"], how="left")
        x["Wash_Type"] = x["Wash_Type"].fillna("Unknown")
        return x[x["Wash_Plant"].isin(plants)] if plants else x

    fi, fo = prep(flow_in), prep(flow_out)
    types = list(C.WASH_TYPES)
    for t in sorted(set(fi["Wash_Type"]).union(fo["Wash_Type"]).union(set(wt["Wash_Type"]))):
        if t and t not in types and t != "":
            types.append(t)
    days = [month_start + pd.Timedelta(days=i) for i in range(n_days)]
    rows = []

    def row(label_t, label_m, f, t):
        x = f if t is None else f[f["Wash_Type"] == t]
        by_day = x.groupby("Date")["Qty"].sum() if len(x) else pd.Series(dtype=float)
        vals = [float(by_day.get(d, 0.0)) for d in days]
        return {"Wash type": label_t, "Metric": label_m, "Total": sum(vals), **{f"D{i + 1:02d}": v for i, v in enumerate(vals)}}

    for t in types:
        rows.append(row(t, "Input", fi, t))
        rows.append(row(t, "Output", fo, t))
    rows.append(row("ALL TYPES", "Input", fi, None))
    rows.append(row("ALL TYPES", "Output", fo, None))
    return pd.DataFrame(rows)
