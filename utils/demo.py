"""Demo data in the same shape as the real sheets (switch on 'Use demo data' in the sidebar)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

BUYERS = ["Primark", "Next", "Zara", "Marks & Spencer", "Gap", "Tesco", "C&A", "H&M"]
HOURS = [f"{h:02d}:00-{(h + 1) % 24:02d}:00" for h in list(range(8, 24)) + list(range(0, 8))]


def make_demo():
    from .data import Bundle
    rng = np.random.default_rng(7)
    today = pd.Timestamp.today().normalize()
    ms = today.replace(day=1)
    ndays = (today + pd.offsets.MonthEnd(0)).day
    orders, daily, hourly, units, fin, fout = [], [], [], [], [], []
    for pi, plant in enumerate(C.PLANTS):
        cap = int(rng.integers(26000, 70000))
        units.append(pd.DataFrame({"Wash_Plant": [plant], "Wet_Capacity_Day": [cap], "Dry_Capacity_Day": [int(cap * 0.55)]}))
        n = int(rng.integers(6, 11))
        rows = []
        for k in range(n):
            qty = int(rng.integers(8, 40)) * 500
            style = f"ST-{4400 + pi * 20 + k}"
            buyer = BUYERS[int(rng.integers(0, len(BUYERS)))]
            wt = C.WASH_TYPES[int(rng.integers(0, 4))]
            crd = today + pd.Timedelta(days=int(rng.integers(-3, 28)))
            prog = float(rng.uniform(0.25, 1.0))
            inp = int(qty * min(1.0, prog + rng.uniform(0.02, 0.12)))
            out = int(qty * prog * rng.uniform(0.7, 1.0))
            wip = max(0, inp - out)
            rew = int(wip * rng.uniform(0, 0.08))
            plan_out = int(qty * min(1.0, prog + rng.uniform(-0.05, 0.12)))
            plan_in = int(qty * min(1.0, prog + rng.uniform(0.0, 0.15)))
            last_out = today - pd.Timedelta(days=int(rng.integers(0, 5)))
            rows.append({
                "Order": f"U{k % 3 + 1} | {buyer} | {style} | PO-{1000 + k} | Blue | Pant | {wt}", "Wash_Plant": plant,
                "Sewing_Unit": f"{plant[:2]}SU-{k % 3 + 1}", "Buyer": buyer, "Style": style, "PO": f"PO-{1000 + k}", "Color": "Blue",
                "Item": "Pant", "Wash_Type": wt, "CRD": crd, "Order_Qty": qty, "Plan_Start": ms, "Plan_End": crd,
                "Total_Sewing_Input": inp, "Total_Wash_Output": out, "Wash_WIP": wip, "Rewash_WIP": rew, "Total_WIP": wip + rew,
                "Total_Dry_Output": int(out * rng.uniform(0.9, 1.3)), "Wash_Balance": max(0, qty - out), "Sewing_Balance": max(0, qty - inp),
                "Input_Plan_Till_Today": plan_in, "Output_Plan_Till_Today": plan_out, "Dry_Plan_Till_Today": plan_out,
                "Month_Input_Plan": qty, "Month_Output_Plan": qty, "Month_Dry_Plan": qty,
                "Last_Input_Date": today - pd.Timedelta(days=int(rng.integers(0, 3))), "Last_Output_Date": last_out,
                "First_Input_Date": ms + pd.Timedelta(days=int(rng.integers(0, 6))), "Risk": "No", "Rewash_Input": rew + int(out * 0.01),
                "Defect_Pcs": int(out * 0.012), "Today_Input": int(qty * 0.04), "Today_Output": int(qty * 0.035),
                "Today_Output_Plan": int(qty * 0.045), "Today_Input_Plan": int(qty * 0.045),
                "Holding_Days": int((today - last_out).days) if wip > 0 else 0, "Report_Date": today,
            })
        o = pd.DataFrame(rows)
        o["Risk"] = np.where((o["Wash_Balance"] > 0) & ((o["CRD"] - today).dt.days <= 7), "Yes", "No")
        orders.append(o)
        # daily
        dts = pd.date_range(ms, periods=ndays)
        d = pd.DataFrame({"Date": dts})
        base = cap * 0.9
        past = d["Date"] <= today
        for col, f in (("Sew_Plan", 1.0), ("Dry_Plan", 0.55), ("Wash_Plan", 1.0)):
            d[col] = (base * f * rng.uniform(0.9, 1.05, ndays)).round()
        d["Sew_Actual"] = np.where(past, (d["Sew_Plan"] * rng.uniform(0.85, 1.05, ndays)).round(), 0)
        d["Dry_Actual"] = np.where(past, (d["Dry_Plan"] * rng.uniform(0.85, 1.05, ndays)).round(), 0)
        d["Wash_Actual"] = np.where(past, (d["Wash_Plan"] * rng.uniform(0.85, 1.05, ndays)).round(), 0)
        d["WashLog_Input"] = d["Sew_Actual"]; d["WashLog_Output"] = d["Wash_Actual"]
        d["Rewash_Input"] = (d["Wash_Actual"] * 0.012).round(); d["Rewash_Output"] = (d["Wash_Actual"] * 0.01).round()
        d["Defect"] = (d["Wash_Actual"] * 0.01).round(); d["Wash_Plant"] = plant
        daily.append(d)
        # hourly (today)
        hr = []
        for dt in dts:
            if dt > today:
                continue
            for i, hname in enumerate(HOURS):
                full = dt < today
                upto = full or i < 12
                dt_t = d.loc[d["Date"] == dt, "Dry_Plan"].iloc[0] / 24
                wt_t = d.loc[d["Date"] == dt, "Wash_Plan"].iloc[0] / 24
                dry = float(dt_t * rng.uniform(0.6, 1.2)) if upto else 0.0
                wet = float(wt_t * rng.uniform(0.6, 1.2)) if upto else 0.0
                hr.append([dt, hname, dt_t, round(dry), dry / dt_t if dt_t else np.nan, wt_t, round(wet), wet / wt_t if wt_t else np.nan, False])
        h = pd.DataFrame(hr, columns=["Date", "Time", "Dry_Target", "Dry_Output", "Dry_Ach", "Wet_Target", "Wet_Output", "Wet_Ach", "Is_Total"])
        h["Wash_Plant"] = plant
        hourly.append(h)
        # flows (day wise per order)
        fi_rows, fo_rows = [], []
        for _, r in o.iterrows():
            for dt in pd.date_range(ms, today):
                if rng.random() < 0.55:
                    fi_rows.append([r["Order"], dt, float(int(r["Order_Qty"] * rng.uniform(0.02, 0.08)))])
                if rng.random() < 0.5:
                    fo_rows.append([r["Order"], dt, float(int(r["Order_Qty"] * rng.uniform(0.02, 0.07)))])
        fi = pd.DataFrame(fi_rows, columns=["Order", "Date", "Qty"]); fi["Wash_Plant"] = plant
        fo = pd.DataFrame(fo_rows, columns=["Order", "Date", "Qty"]); fo["Wash_Plant"] = plant
        fin.append(fi); fout.append(fo)
    cat = lambda xs: pd.concat(xs, ignore_index=True)
    return Bundle(cat(orders), cat(daily), cat(hourly), cat(units), cat(fin), cat(fout), today, ms, plants=list(C.PLANTS), demo=True)
