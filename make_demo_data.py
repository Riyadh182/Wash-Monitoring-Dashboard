"""Generates realistic DEMO data (unit CWL-1, 21 days) into ../demo_data so the app runs without Google Sheets."""
import random, datetime, pathlib
import pandas as pd
from common import *

OUT = pathlib.Path(__file__).parent.parent / 'demo_data'
UNIT = 'CWL-1'
rnd = random.Random(2026)
STYLES = {  # style -> (wash type, defect-multiplier, rewash-multiplier)
    'ST-4412 Dark Stone': ('Denim', 1.0, 1.0), 'ST-4430 Mid Blue': ('Denim', 0.9, 0.9), 'ST-4475 Vintage Wash': ('Denim', 1.6, 1.1),
    'ST-5120 Acid Blast': ('Acid', 1.0, 1.2), 'ST-5133 Snow Acid': ('Acid', 1.2, 2.6), 'ST-3307 Twill Rinse': ('Twill', 0.8, 0.8),
    'ST-3350 Twill Garment Dye': ('Twill', 1.0, 1.0), 'ST-2285 Dye Black': ('Dyeing', 1.1, 1.3)}
by_type = {t: [s for s, v in STYLES.items() if v[0] == t] for t in WASH_TYPES}
mix = CFG['units'][UNIT]['wash_mix']
machines = machines_for(UNIT); procs = processes_for(UNIT)
labels = hour_labels(8)
def rr(x):  # probabilistic rounding so small defect/rewash counts are not rounded to zero
    return int(x) + (1 if rnd.random() < x - int(x) else 0)
days = [datetime.date(2026, 9, 16) + datetime.timedelta(days=i) for i in range(21)]
mach_eff = {m['Machine_ID']: min(1.05, max(0.5, rnd.gauss(0.88, 0.11))) for m in machines}
weak = set(rnd.sample(list(mach_eff), 5))
proc_eff = {p['Process']: rnd.uniform(0.78, 1.02) for p in procs}
proc_eff['Hand Sand (Front & Back)'] = 0.62; proc_eff['Grinding'] = 0.7; proc_eff['Laser Whisker'] = 1.0

wash, dry, wip = [], [], []
open_wash = 106939
for di, day in enumerate(days):
    day_in = day_out = 0
    day_eff = rnd.uniform(0.9, 1.05)
    for m in machines:
        base = m['Plan_per_hr']
        blocks = []
        for b in range(3):
            wt = rnd.choices(list(mix), [mix[k] for k in mix])[0]
            blocks.append((wt, rnd.choice(by_type[wt])))
        for h in range(1, 25):
            wt, sty = blocks[(h - 1) // 8]
            _, dm, rm = STYLES[sty]
            eff = mach_eff[m['Machine_ID']] * day_eff * rnd.uniform(0.82, 1.12) * (0.8 if h in (1, 9, 17) else 1)
            dt, why = 0, ''
            if rnd.random() < 0.045 or (m['Machine_ID'] in weak and rnd.random() < 0.18):
                eff *= rnd.uniform(0, 0.4); dt = rnd.choice([20, 30, 40, 60]); why = rnd.choice(WASH_REASONS[:6])
            out = round(base * eff); inp = round(out * rnd.uniform(0.97, 1.12)); insp = round(out * 0.8)
            dfr = rnd.uniform(0.012, 0.03) * dm; rwr = rnd.uniform(0.006, 0.016) * rm
            wash.append([day, labels[h-1], UNIT, m['Machine_ID'], wt, sty, inp, out, insp, rr(insp * dfr), rr(out * rwr), dt or '', why, ''])
            day_in += inp; day_out += out
    wip.append([day, UNIT, 'WASH', open_wash, 'DEMO' if di == 0 else 'carry-forward'])
    open_wash = max(40000, open_wash + day_in - day_out)
    for p in procs:
        base = p['Capacity_per_day'] / 24.0
        blocks = [rnd.choice(list(STYLES)) for _ in range(3)]
        wip.append([day, UNIT, p['Process'], round(base * rnd.uniform(0.5, 2.5)), 'DEMO'])
        for h in range(1, 25):
            eff = proc_eff[p['Process']] * rnd.uniform(0.85, 1.12) * (0.85 if h in (1, 9, 17) else 1)
            dt, why = 0, ''
            if rnd.random() < 0.05:
                eff *= rnd.uniform(0, 0.5); dt = rnd.choice([15, 30, 45]); why = rnd.choice(DRY_REASONS)
            out = round(base * eff); inp = round(out * rnd.uniform(0.98, 1.1))
            dry.append([day, labels[h-1], UNIT, p['Process'], blocks[(h-1)//8], inp, out, rr(out * rnd.uniform(0.008, 0.03)),
                        rr(out * rnd.uniform(0.005, 0.02)), dt or '', why, ''])
cols_w = ['Date','Hour','Unit','Machine_ID','Wash_Type','Style','Input','Output','QC_Inspected','Defect','Rewash','Downtime_Min','Downtime_Reason','Remarks']
cols_d = ['Date','Hour','Unit','Process','Style','Input','Output','Defect','Rework','Downtime_Min','Downtime_Reason','Remarks']
pd.DataFrame(wash, columns=cols_w).to_csv(OUT/'Wash_Log.csv', index=False)
pd.DataFrame(dry, columns=cols_d).to_csv(OUT/'Dry_Log.csv', index=False)
pd.DataFrame(wip, columns=['Date','Unit','Stage','Opening_WIP','Remarks']).to_csv(OUT/'WIP_Log.csv', index=False)
pd.DataFrame(machines).to_csv(OUT/'Master_Machine.csv', index=False)
pd.DataFrame(procs).to_csv(OUT/'Master_Process.csv', index=False)
pd.DataFrame(DEFAULT_SETTINGS, columns=['Key','Value']).to_csv(OUT/'Settings.csv', index=False)
print(len(wash), len(dry), len(wip))
