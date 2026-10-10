"""Generates realistic DEMO data (unit CWL-1, 21 days, with orders/PO/colour) into ../demo_data."""
import random, datetime, pathlib
import pandas as pd
from common import *

OUT = pathlib.Path(__file__).parent.parent / 'demo_data'
UNIT = 'CWL-1'
rnd = random.Random(2026)
D0 = datetime.date(2026, 9, 16); NDAYS = 21; TODAY_IDX = NDAYS - 1
STYLE_Q = {  # style -> (wash type, defect-multiplier, rewash-multiplier)
    'ST-4412 Dark Stone': ('Denim', 1.0, 1.0), 'ST-4430 Mid Blue': ('Denim', 0.9, 0.9), 'ST-4475 Vintage Wash': ('Denim', 1.6, 1.1),
    'ST-5120 Acid Blast': ('Acid', 1.0, 1.2), 'ST-5133 Snow Acid': ('Acid', 1.2, 2.6), 'ST-3307 Twill Rinse': ('Twill', 0.8, 0.8),
    'ST-3350 Twill Garment Dye': ('Twill', 1.0, 1.0), 'ST-2285 Dye Black': ('Dyeing', 1.1, 1.3)}
# (style, PO, colour, buyer, sewing unit, merchant, plan start day idx, plan end day idx)  - demo names only
ORDERS = [
 ('ST-4412 Dark Stone', 'PO-77101', 'Dark Blue', 'H&M', 'TISWL-01', 'Rahim Uddin', 0, 12),
 ('ST-4412 Dark Stone', 'PO-77102', 'Black Stone', 'Zara', 'TISWL-02', 'Sumaiya Akter', 8, 24),
 ('ST-4412 Dark Stone', 'PO-77103', 'Dark Blue', 'H&M', 'TISWL-01', 'Rahim Uddin', 15, 28),
 ('ST-4430 Mid Blue', 'PO-77210', 'Mid Blue', 'Next', 'TISWL-03', 'Tanvir Hasan', 0, 20),
 ('ST-4430 Mid Blue', 'PO-77211', 'Light Blue', 'Next', 'TISWL-03', 'Tanvir Hasan', 10, 30),
 ('ST-4475 Vintage Wash', 'PO-77305', 'Vintage Indigo', 'C&A', 'TISWL-04', 'Nusrat Jahan', 2, 18),
 ('ST-4475 Vintage Wash', 'PO-77306', 'Vintage Grey', 'C&A', 'TISWL-04', 'Nusrat Jahan', 14, 35),
 ('ST-5120 Acid Blast', 'PO-88010', 'Acid Black', 'Zara', 'RGL', 'Sumaiya Akter', 0, 16),
 ('ST-5133 Snow Acid', 'PO-88055', 'Snow White', 'H&M', 'TISWL-02', 'Rahim Uddin', 6, 22),
 ('ST-5133 Snow Acid', 'PO-88056', 'Snow Grey', 'H&M', 'TISWL-02', 'Rahim Uddin', 18, 40),
 ('ST-3307 Twill Rinse', 'PO-66120', 'Khaki', 'Tesco', 'TISWL-03', 'Tanvir Hasan', 0, 14),
 ('ST-3350 Twill Garment Dye', 'PO-66180', 'Olive', 'Tesco', 'RGL', 'Nusrat Jahan', 5, 26),
 ('ST-2285 Dye Black', 'PO-99040', 'Jet Black', 'Next', 'TISWL-01', 'Sumaiya Akter', 3, 21),
 ('ST-2285 Dye Black', 'PO-99041', 'Charcoal', 'Next', 'TISWL-01', 'Sumaiya Akter', 25, 45)]
mix = CFG['units'][UNIT]['wash_mix']
machines = machines_for(UNIT); procs = processes_for(UNIT)
labels = hour_labels(8)
days = [D0 + datetime.timedelta(days=i) for i in range(NDAYS)]
mach_eff = {m['Machine_ID']: min(1.05, max(0.5, rnd.gauss(0.88, 0.11))) for m in machines}
weak = set(rnd.sample(list(mach_eff), 5))
proc_eff = {p['Process']: rnd.uniform(0.78, 1.02) for p in procs}
proc_eff['Hand Sand (Front & Back)'] = 0.62; proc_eff['Grinding'] = 0.7; proc_eff['Laser Whisker'] = 1.0
def rr(x): return int(x) + (1 if rnd.random() < x - int(x) else 0)
def active_orders(di, wtype=None):
    a = [o for o in ORDERS if o[6] <= di <= o[7] and (wtype is None or STYLE_Q[o[0]][0] == wtype)]
    return a or [o for o in ORDERS if wtype is None or STYLE_Q[o[0]][0] == wtype]

wash, dry, wip = [], [], []
tot_in = {}
open_wash = 106939
for di, day in enumerate(days):
    day_eff = rnd.uniform(0.9, 1.05)
    for m in machines:
        base = m['Plan_per_hr']
        blocks = []
        for b in range(3):
            wt = rnd.choices(list(mix), [mix[k] for k in mix])[0]
            blocks.append((wt, rnd.choice(active_orders(di, wt))))
        for h in range(1, 25):
            wt, o = blocks[(h - 1) // 8]
            sty, po, col = o[0], o[1], o[2]
            _, dm, rm = STYLE_Q[sty]
            eff = mach_eff[m['Machine_ID']] * day_eff * rnd.uniform(0.82, 1.12) * (0.8 if h in (1, 9, 17) else 1)
            dt, why = 0, ''
            if rnd.random() < 0.045 or (m['Machine_ID'] in weak and rnd.random() < 0.18):
                eff *= rnd.uniform(0, 0.4); dt = rnd.choice([20, 30, 40, 60]); why = rnd.choice(WASH_REASONS[:6])
            out = round(base * eff); inp = round(out * rnd.uniform(0.97, 1.12)); insp = round(out * 0.8)
            dfr = rnd.uniform(0.012, 0.03) * dm; rwr = rnd.uniform(0.006, 0.016) * rm
            rw = rr(out * rwr); rwo = rr(rw * rnd.uniform(0.5, 1.0)); rej = rr(out * rnd.uniform(0.0005, 0.004))
            wash.append([day, labels[h-1], UNIT, m['Machine_ID'], wt, sty, po, col, inp, out, insp, rr(insp * dfr), rw, rwo, rej, dt or '', why, ''])
    for p in procs:
        base = p['Capacity_per_day'] / 24.0
        blocks = [rnd.choice(active_orders(di)) for _ in range(3)]
        wip.append([day, UNIT, p['Process'], round(base * rnd.uniform(0.5, 2.5)), 'DEMO'])
        for h in range(1, 25):
            o = blocks[(h-1)//8]
            eff = proc_eff[p['Process']] * rnd.uniform(0.85, 1.12) * (0.85 if h in (1, 9, 17) else 1)
            dt, why = 0, ''
            if rnd.random() < 0.05:
                eff *= rnd.uniform(0, 0.5); dt = rnd.choice([15, 30, 45]); why = rnd.choice(DRY_REASONS)
            out = round(base * eff); inp = round(out * rnd.uniform(0.98, 1.1))
            dry.append([day, labels[h-1], UNIT, p['Process'], o[0], o[1], o[2], inp, out, rr(out * rnd.uniform(0.008, 0.03)),
                        rr(out * rnd.uniform(0.005, 0.02)), dt or '', why, ''])

# ---- make wash cycles realistic: output starts ~1-2.5 days after first input; last input stops 1-2.5 days before last output
wdf = pd.DataFrame(wash, columns=['Date','Hour','Unit','Machine_ID','Wash_Type','Style','PO','Color','Input','Output','QC_Inspected','Defect','Rewash','Rewash_Output','Reject','Downtime_Min','Downtime_Reason','Remarks'])
hidx = wdf['Hour'].map({l: i for i, l in enumerate(labels)})
wdf['_dt'] = pd.to_datetime(wdf['Date']) + pd.to_timedelta(8 + hidx, unit='h')
for (po, col), idx in wdf.groupby(['PO', 'Color']).groups.items():
    g = wdf.loc[idx]
    first_in = g.loc[g['Input'] > 0, '_dt'].min(); last_out = g.loc[g['Output'] > 0, '_dt'].max()
    l1, l2 = rnd.uniform(30, 60), rnd.uniform(24, 60)
    early = g.index[g['_dt'] < first_in + pd.Timedelta(hours=l1)]
    wdf.loc[early, ['Output', 'QC_Inspected', 'Defect', 'Rewash', 'Rewash_Output', 'Reject']] = 0
    late = g.index[g['_dt'] > last_out - pd.Timedelta(hours=l2)]
    wdf.loc[late, 'Input'] = 0
tot_in = wdf.groupby(['PO', 'Color'])['Input'].sum().to_dict()
dd = wdf.groupby('Date')[['Input', 'Output']].sum()
for di, day in enumerate(days):
    wip.append([day, UNIT, 'WASH', open_wash, 'DEMO' if di == 0 else 'carry-forward'])
    open_wash = max(40000, open_wash + dd.loc[day, 'Input'] - dd.loc[day, 'Output'])
wash = wdf.drop(columns='_dt').values.tolist()

# Order_Master: quantity so that the straight-line plan is near (but not equal to) the actual so far
om = []
for k, o in enumerate(ORDERS):
    sty, po, col, buyer, sew, mer, s_i, e_i = o
    start, end = D0 + datetime.timedelta(days=s_i), D0 + datetime.timedelta(days=e_i)
    total = e_i - s_i + 1
    prog = min(max((TODAY_IDX - s_i + 1) / total, 0), 1)
    done = tot_in.get((po, col), 0)
    qty = round(done / prog * rnd.uniform(0.92, 1.12), -2) if prog > 0 and done else round(rnd.uniform(18000, 40000), -2)
    crd = end + datetime.timedelta(days=rnd.randint(9, 20))
    rev = rnd.choice([0, 0, 1, 2, 3]); upd = crd + datetime.timedelta(days=rnd.randint(3, 10)) if rev else ''
    submit = start - datetime.timedelta(days=rnd.randint(2, 4))
    appr = submit + datetime.timedelta(days=rnd.randint(2, 6)) if s_i <= TODAY_IDX and rnd.random() > 0.15 else ''
    om.append([UNIT, buyer, sty, po, col, STYLE_Q[sty][0], crd, rev, upd, sew, qty, start, end, submit, appr, mer, 'DEMO'])
# Daily_Plan demo: ramp-up / ramp-down for 3 orders (others use the straight-line fallback)
plan_rows = []
for o, om_row in zip(ORDERS, om):
    if o[1] not in ('PO-77101', 'PO-77210', 'PO-88010'):
        continue
    s_i, e_i, qty = o[6], o[7], om_row[10]
    n = e_i - s_i + 1
    wts = [0.5 + min(k, n - 1 - k, 3) * 0.35 for k in range(n)]
    tot = sum(wts); ins = [round(qty * x / tot) for x in wts]
    for k in range(n):
        d_in = D0 + datetime.timedelta(days=s_i + k)
        plan_rows.append([d_in, UNIT, o[0], o[1], o[2], ins[k], 0])
        plan_rows.append([d_in + datetime.timedelta(days=2), UNIT, o[0], o[1], o[2], 0, ins[k]])
pdf = pd.DataFrame(plan_rows, columns=['Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'Plan_Input', 'Plan_Output'])
pdf.groupby(['Date', 'Wash_Plant', 'Style', 'PO', 'Color'], as_index=False)[['Plan_Input', 'Plan_Output']].sum().to_csv(OUT / 'Daily_Plan.csv', index=False)
cols_w = ['Date','Hour','Unit','Machine_ID','Wash_Type','Style','PO','Color','Input','Output','QC_Inspected','Defect','Rewash','Rewash_Output','Reject','Downtime_Min','Downtime_Reason','Remarks']
cols_d = ['Date','Hour','Unit','Process','Style','PO','Color','Input','Output','Defect','Rework','Downtime_Min','Downtime_Reason','Remarks']
pd.DataFrame(wash, columns=cols_w).to_csv(OUT/'Wash_Log.csv', index=False)
pd.DataFrame(dry, columns=cols_d).to_csv(OUT/'Dry_Log.csv', index=False)
pd.DataFrame(wip, columns=['Date','Unit','Stage','Opening_WIP','Remarks']).to_csv(OUT/'WIP_Log.csv', index=False)
pd.DataFrame(om, columns=['Wash_Plant','Buyer','Style','PO','Color','Wash_Type','CRD','CRD_Revisions','Updated_CRD','Sewing_Unit','Order_Qty','Plan_Start','Plan_End','Shade_Submit_Date','Shade_Approval_Date','Merchant','Remarks']).to_csv(OUT/'Order_Master.csv', index=False)
pd.DataFrame(machines).to_csv(OUT/'Master_Machine.csv', index=False)
pd.DataFrame(procs).to_csv(OUT/'Master_Process.csv', index=False)
pd.DataFrame(DEFAULT_SETTINGS, columns=['Key','Value']).to_csv(OUT/'Settings.csv', index=False)
print(len(wash), len(dry), len(wip), len(om))
