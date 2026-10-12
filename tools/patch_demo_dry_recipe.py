"""One-off demo patch: (1) Recipe_Min in Wash_Log + Std_Recipe_Min in Master_Machine, (2) a Dry_Log where every order goes through
only SOME dry processes (finished dry output = the minimum of those process totals). Run after make_demo_data.py."""
import pathlib, zlib
import numpy as np, pandas as pd
from common import DRY_REASONS

D = pathlib.Path(__file__).parent.parent / 'demo_data'
rng = np.random.default_rng(2026)
w = pd.read_csv(D / 'Wash_Log.csv.gz', dtype=str, keep_default_na=False)
mm = pd.read_csv(D / 'Master_Machine.csv', dtype=str, keep_default_na=False)
mp = pd.read_csv(D / 'Master_Process.csv', dtype=str, keep_default_na=False)

# ---- recipe time (minutes per cycle)
base = {'Denim': 95, 'Acid': 120, 'Twill': 70, 'Dyeing': 85}
tf = {'F/L': 1.0, 'Acid B/L': 1.12, 'B/L': 0.94}
mtype = dict(zip(mm['Machine_ID'], mm['Type']))
mm['Std_Recipe_Min'] = [round(np.mean(list(base.values())) * tf[t]) for t in mm['Type']]
slow = set(rng.choice(mm['Machine_ID'], size=max(3, len(mm) // 25), replace=False))        # a few machines drift above standard
out = pd.to_numeric(w['Output'], errors='coerce').fillna(0)
mu = np.array([base.get(t, 90) * tf[mtype.get(m, 'F/L')] * (1.18 if m in slow else 1.0) for t, m in zip(w['Wash_Type'], w['Machine_ID'])])
rec = np.rint(rng.normal(mu, 7))
w['Recipe_Min'] = np.where(out > 0, rec, '')
cols = list(w.columns); cols.remove('Recipe_Min'); cols.insert(cols.index('Remarks') + 1, 'Recipe_Min')
w[cols].to_csv(D / 'Wash_Log.csv.gz', index=False)
mm.to_csv(D / 'Master_Machine.csv', index=False)

# ---- consistent dry log
w['Output_n'] = out
g = w[w['Output_n'] > 0].groupby(['Date', 'Hour', 'Unit', 'Style', 'PO', 'Color'], as_index=False)['Output_n'].sum()
rows = []
for unit, pr in mp.groupby('Unit'):
    names = list(pr['Process']); caps = dict(zip(pr['Process'], pd.to_numeric(pr['Capacity_per_day']) / 24.0))
    gu = g[g['Unit'] == unit].copy()
    if gu.empty:
        continue
    # each order goes through 2-3 processes (deterministic per PO)
    use = {}
    for po in gu['PO'].unique():
        r = np.random.default_rng(zlib.crc32((unit + po).encode()))
        k = int(r.integers(2, min(3, len(names)) + 1))
        use[po] = list(r.choice(names, size=k, replace=False))
    for p in names:
        sub = gu[gu['PO'].map(lambda x: p in use[x])].copy()
        if sub.empty:
            continue
        sub['raw'] = sub['Output_n'] * rng.uniform(.82, 1.0, len(sub))
        tot = sub.groupby(['Date', 'Hour'])['raw'].transform('sum')
        sub['Output'] = np.rint(sub['raw'] * np.minimum(1.0, caps[p] * rng.uniform(.85, 1.0, len(sub)) / tot))
        sub = sub[sub['Output'] > 0]
        sub['Process'] = p
        sub['Input'] = np.rint(sub['Output'] * rng.normal(1.0, .03, len(sub))).clip(lower=0)
        sub['Defect'] = rng.binomial(sub['Output'].astype(int), rng.uniform(.008, .03, len(sub)))
        sub['Rework'] = rng.binomial(sub['Output'].astype(int), rng.uniform(.005, .02, len(sub)))
        b = rng.random(len(sub)) < .03
        sub['Downtime_Min'] = np.where(b, rng.choice([15, 30, 45], len(sub)), '')
        sub['Downtime_Reason'] = np.where(b, rng.choice(DRY_REASONS[:6], len(sub)), '')
        rows.append(sub)
dl = pd.concat(rows)
dl['Remarks'] = ''
dl = dl[['Date', 'Hour', 'Unit', 'Process', 'Style', 'PO', 'Color', 'Input', 'Output', 'Defect', 'Rework', 'Downtime_Min', 'Downtime_Reason', 'Remarks']]
dl = dl.sort_values(['Date', 'Hour', 'Unit', 'Process'])
for c in ('Input', 'Output', 'Defect', 'Rework'):
    dl[c] = dl[c].astype(int)
dl.to_csv(D / 'Dry_Log.csv.gz', index=False)
print('recipe rows', int((w['Recipe_Min'] != '').sum()), 'dry rows', len(dl))
