"""DEMO data: all 10 wash plants x 30 days (2026-09-10 .. 2026-10-09), machine-hour level, with orders, priors, daily plan,
allotment, unit master. Writes gz CSVs into ../demo_data. Run: python make_demo_data.py"""
import datetime, pathlib
import numpy as np, pandas as pd
from common import *

OUT = pathlib.Path(__file__).parent.parent / 'demo_data'
for f in OUT.glob('*'):
    f.unlink()
D0 = datetime.date(2026, 9, 10); D = 30; ASOF = D - 1
rng = np.random.default_rng(2026)
LABELS = np.array(hour_labels(8))
DATES = np.array([str(D0 + datetime.timedelta(days=i)) for i in range(D)])
BUYERS = {'H&M': 'Rahim Uddin', 'Zara': 'Sumaiya Akter', 'Next': 'Tanvir Hasan', 'C&A': 'Nusrat Jahan', 'Tesco': 'Imran Hossain',
          'Marks & Spencer': 'Farhana Yasmin', 'Primark': 'Kamal Hossain', 'Gap': 'Shirin Sultana'}
SEW = ['TISWL-01', 'TISWL-02', 'TISWL-03', 'TISWL-04', 'TISWL-04(B)', 'RGL']
STYLES = {  # wash type -> [(style, defect mult, rewash mult)]
    'Denim': [('ST-4412 Dark Stone', 1.0, 1.0), ('ST-4430 Mid Blue', .9, .9), ('ST-4475 Vintage Wash', 1.6, 1.1), ('ST-4501 Light Fade', 1.1, 1.0)],
    'Acid': [('ST-5120 Acid Blast', 1.0, 1.2), ('ST-5133 Snow Acid', 1.2, 2.6)],
    'Twill': [('ST-3307 Twill Rinse', .8, .8), ('ST-3350 Twill Garment Dye', 1.0, 1.0)],
    'Dyeing': [('ST-2285 Dye Black', 1.1, 1.3), ('ST-2290 Dye Navy', 1.0, 1.1)]}
COLORS = {'Denim': ['Dark Blue', 'Mid Blue', 'Light Blue', 'Indigo', 'Black Stone'], 'Acid': ['Acid Black', 'Snow White', 'Snow Grey'],
          'Twill': ['Khaki', 'Olive', 'Stone'], 'Dyeing': ['Jet Black', 'Charcoal', 'Navy']}
W_REASONS = np.array(WASH_REASONS[:6]); D_REASONS = np.array(DRY_REASONS[:6])
PROC_DAYMULT = {}

wash_parts, dry_parts, wip_rows, order_rows, plan_rows, al_rows, mm_rows, mp_rows, um_rows = [], [], [], [], [], [], [], [], []

for ui, u in enumerate(CFG['units']):
    cfg = CFG['units'][u]
    mach = machines_for(u); M = len(mach); cap = np.array([m['Plan_per_hr'] for m in mach]); mids = np.array([m['Machine_ID'] for m in mach])
    mm_rows += mach
    procs = processes_for(u) if cfg['dry_processes'] else []
    mp_rows += procs
    um_rows.append(dict(Wash_Plant=u, Wet_Capacity_Day=cfg['wash_cap_day'], Dry_Capacity_Day=cfg['dry_cap_day'] or ''))
    mix = cfg['wash_mix']; types = ['Denim', 'Acid', 'Twill', 'Dyeing']
    pr = np.array([mix.get(t) or 0 for t in types], float); pr = pr / pr.sum() if pr.sum() > 0 else np.array([.64, .14, .13, .09])
    # ---------------- orders
    n = int(14 + min(6, cap.sum() * 24 / 20000))
    O = []
    for i in range(n):
        wt = rng.choice(types, p=pr); sty = STYLES[wt][rng.integers(len(STYLES[wt]))]
        start = int(rng.integers(-8, 14)); length = int(rng.integers(8, 21))
        O.append(dict(wt=wt, style=sty[0], dm=sty[1], rm=sty[2], color=COLORS[wt][rng.integers(len(COLORS[wt]))], po=f"PO-{ui + 1}{i + 1:03d}",
                      buyer=list(BUYERS)[rng.integers(len(BUYERS))], sew=SEW[rng.integers(len(SEW))], start=start, end=start + length - 1, w=rng.uniform(.5, 1.5)))
    for d in range(-2, D + 1):
        while sum(1 for o in O if o['start'] <= d <= o['end']) < 2:
            o = min([x for x in O if not (x['start'] <= d <= x['end'])], key=lambda x: min(abs(x['end'] - d), abs(x['start'] - d)))
            if o['end'] < d: o['end'] = d + int(rng.integers(0, 4))
            elif o['start'] > d: o['start'] = d
    st_a = np.array([o['start'] for o in O]); en_a = np.array([o['end'] for o in O]); w_a = np.array([o['w'] for o in O])
    dm_a = np.array([o['dm'] for o in O]); rm_a = np.array([o['rm'] for o in O])

    def pick(d, size, uniform=False):
        act = np.where((st_a <= d) & (en_a >= d))[0]
        if len(act) == 0:
            act = np.arange(n)
        p = np.ones(len(act)) if uniform else w_a[act]
        return rng.choice(act, size=size, p=p / p.sum())

    # ---------------- wash log
    assign = np.stack([np.stack([pick(d, M) for _ in range(3)], axis=1) for d in range(D)])          # (D, M, 3)
    ordrow = np.repeat(assign, 8, axis=2).reshape(-1); N = D * M * 24
    mach_eff = np.clip(rng.normal(.96, .08, M), .6, 1.08); weak = rng.choice(M, min(5, M), replace=False)
    pbd = np.full(M, .045); pbd[weak] = .18
    day_eff = rng.uniform(.9, 1.05, D)
    dip = np.ones(24); dip[[0, 8, 16]] = .85
    eff = mach_eff[None, :, None] * day_eff[:, None, None] * rng.uniform(.82, 1.12, (D, M, 24)) * dip[None, None, :]
    bd = rng.random((D, M, 24)) < pbd[None, :, None]
    eff = np.where(bd, eff * rng.uniform(0, .4, (D, M, 24)), eff)
    dtm = np.where(bd, rng.choice([20, 30, 40, 60], (D, M, 24)), 0).reshape(-1)
    rsn = np.where(bd, rng.integers(0, 6, (D, M, 24)), -1).reshape(-1)
    out = np.rint(cap[None, :, None] * eff).astype(int).reshape(-1)
    inp = np.clip(np.rint(out * rng.normal(1.0, .04, N)), 0, None).astype(int)
    insp = np.rint(out * .8).astype(int)
    dfr = np.clip(rng.uniform(.012, .03, N) * dm_a[ordrow], 0, .5); rwr = np.clip(rng.uniform(.006, .016, N) * rm_a[ordrow], 0, .5)
    defect = rng.binomial(insp, dfr); rewash = rng.binomial(out, rwr); rew_out = rng.binomial(rewash, .8); reject = rng.binomial(out, .002)
    th = np.repeat(np.arange(D), M * 24) * 24 + np.tile(np.arange(24), D * M)
    df = pd.DataFrame(dict(o=ordrow, th=th, Input=inp, Output=out, QC_Inspected=insp, Defect=defect, Rewash=rewash, Rewash_Output=rew_out, Reject=reject))
    first_in = df.groupby('o')['th'].transform('min')
    l1 = rng.uniform(30, 60, n)[df['o']]; started = (st_a >= 0)[df['o']]
    early = started & (df['th'] < first_in + l1)
    for c in ['Output', 'QC_Inspected', 'Defect', 'Rewash', 'Rewash_Output', 'Reject']:
        df.loc[early, c] = 0
    lastout = df[df['Output'] > 0].groupby('o')['th'].max().reindex(range(n)).fillna(10 ** 6).values
    late = (en_a < D - 3)[df['o']] & (df['th'] > lastout[df['o']] - rng.uniform(24, 60, n)[df['o']])
    df.loc[late, 'Input'] = 0
    out_sum = df.groupby('o')['Output'].sum().reindex(range(n)).fillna(0).values
    days_act = np.maximum(df.groupby('o')['th'].apply(lambda s_: s_.floordiv(24).nunique()).reindex(range(n)).fillna(1).values, 1)
    rate_out = out_sum / days_act
    pre = np.maximum(0, -st_a)
    P_IN = rate_out * pre * rng.uniform(.9, 1.0, n); P_OUT = rate_out * np.maximum(0, pre - 2) * rng.uniform(.9, 1.0, n)
    wip_end = np.where(en_a >= D - 2, rate_out * rng.uniform(1.2, 2.4, n), rate_out * rng.uniform(.05, .3, n))
    in_sum = df.groupby('o')['Input'].sum().reindex(range(n)).fillna(0).values
    fac = np.clip((out_sum + wip_end - (P_IN - P_OUT)) / np.maximum(in_sum, 1), .3, 3)
    df['Input'] = np.rint(df['Input'].values * fac[df['o'].values]).astype(int)
    sty_a = np.array([o['style'] for o in O]); po_a = np.array([o['po'] for o in O]); col_a = np.array([o['color'] for o in O]); wt_a = np.array([o['wt'] for o in O])
    wl = pd.DataFrame({'Date': np.repeat(DATES, M * 24), 'Hour': np.tile(LABELS, D * M), 'Unit': u, 'Machine_ID': np.tile(np.repeat(mids, 24), D),
                       'Wash_Type': wt_a[ordrow], 'Style': sty_a[ordrow], 'PO': po_a[ordrow], 'Color': col_a[ordrow],
                       'Input': df['Input'].values, 'Output': df['Output'].values, 'QC_Inspected': df['QC_Inspected'].values, 'Defect': df['Defect'].values,
                       'Rewash': df['Rewash'].values, 'Rewash_Output': df['Rewash_Output'].values, 'Reject': df['Reject'].values,
                       'Downtime_Min': np.where(dtm > 0, dtm, ''), 'Downtime_Reason': np.where(rsn >= 0, W_REASONS[np.clip(rsn, 0, 5)], ''), 'Remarks': ''})
    wash_parts.append(wl)
    # ---------------- orders master with priors, qty, CRD
    realised_in = df.groupby('o')['Input'].sum().reindex(range(n)).fillna(0).values
    ongoing_idx = [i for i, o_ in enumerate(O) if o_['end'] >= ASOF - 1]; rng.shuffle(ongoing_idx)
    crisis_set = set(ongoing_idx[:3]); overdue_set = set(ongoing_idx[3:4])
    for i, o in enumerate(O):
        p_in, p_out = P_IN[i], P_OUT[i]
        length = o['end'] - o['start'] + 1; prog = min(1.0, (ASOF - o['start'] + 1) / length)
        qty = round((p_in + realised_in[i]) / max(prog, .05) * rng.uniform(.93, 1.08), -2) if o['end'] >= ASOF - 1 else round((P_OUT[i] + out_sum[i]) * rng.uniform(1.0, 1.012), -2)
        o.update(qty=qty, p_in=round(p_in), p_out=round(p_out))
        pstart = D0 + datetime.timedelta(days=o['start']); pend = D0 + datetime.timedelta(days=o['end'])
        if i in crisis_set:
            crd = D0 + datetime.timedelta(days=ASOF + int(rng.integers(1, 8)))
        elif i in overdue_set:
            crd = D0 + datetime.timedelta(days=ASOF - int(rng.integers(1, 4)))      # a few already overdue
        else:
            crd = pend + datetime.timedelta(days=int(rng.integers(7, 19)))
        rev = int(rng.choice([0, 0, 1, 2, 3])); upd = crd + datetime.timedelta(days=int(rng.integers(2, 9))) if rev else ''
        submit = pstart - datetime.timedelta(days=int(rng.integers(2, 5)))
        appr = submit + datetime.timedelta(days=int(rng.integers(2, 7))) if rng.random() > .12 else ''
        order_rows.append([u, o['buyer'], o['style'], o['po'], o['color'], o['wt'], crd, rev, upd, o['sew'], qty, pstart, pend, submit, appr,
                           BUYERS[o['buyer']], o['p_in'], o['p_out'], 'DEMO'])
        if rng.random() < .25:     # real daily plan with ramp-up/down for some orders
            wts = np.array([.5 + min(k, length - 1 - k, 3) * .35 for k in range(length)]); ins = np.rint(qty * wts / wts.sum())
            for k in range(length):
                dd = pstart + datetime.timedelta(days=k)
                plan_rows.append([dd, u, o['style'], o['po'], o['color'], ins[k], 0]); plan_rows.append([dd + datetime.timedelta(days=2), u, o['style'], o['po'], o['color'], 0, ins[k]])
    # ---------------- wash WIP opening per day (orders priors + running net)
    dayio = df.assign(d=df['th'] // 24).groupby('d')[['Input', 'Output']].sum()
    opening = sum(o['p_in'] - o['p_out'] for o in O)
    for d in range(D):
        wip_rows.append([DATES[d], u, 'WASH', int(opening), 'DEMO' if d == 0 else 'carry-forward'])
        opening += dayio.loc[d, 'Input'] - dayio.loc[d, 'Output']
    # ---------------- allotment (machines)
    cap_row = np.tile(np.repeat(cap, 3), D)
    a = pd.DataFrame({'Date': np.repeat(DATES, M * 3), 'Resource': np.tile(np.repeat(mids, 3), D), 'o': assign.reshape(-1), 'q': 8 * cap_row * rng.uniform(.9, 1.0, D * M * 3)})
    a = a.groupby(['Date', 'Resource', 'o'], as_index=False)['q'].sum()
    a['Unit'] = u; a['Style'] = sty_a[a['o']]; a['PO'] = po_a[a['o']]; a['Color'] = col_a[a['o']]; a['Plan_Qty'] = a['q'].round(0).astype(int)
    al_rows.append(a[['Date', 'Unit', 'Resource', 'Style', 'PO', 'Color', 'Plan_Qty']])
    # ---------------- dry
    if procs:
        P = len(procs); pnames = np.array([p['Process'] for p in procs]); pcap = np.array([p['Capacity_per_day'] for p in procs]) / 24.0
        peff = rng.uniform(.78, 1.02, P)
        for nm, v in {'Hand Sand (Front & Back)': .62, 'Grinding': .7}.items():
            if nm in pnames: peff[list(pnames).index(nm)] = v
        da = np.stack([np.stack([pick(d, P, True) for _ in range(3)], axis=1) for d in range(D)]); drow = np.repeat(da, 8, axis=2).reshape(-1); ND_ = D * P * 24
        e = peff[None, :, None] * rng.uniform(.85, 1.12, (D, P, 24)) * np.where(dip < 1, .85, 1)[None, None, :]
        b2 = rng.random((D, P, 24)) < .05
        e = np.where(b2, e * rng.uniform(0, .5, (D, P, 24)), e)
        dt2 = np.where(b2, rng.choice([15, 30, 45], (D, P, 24)), 0).reshape(-1); r2 = np.where(b2, rng.integers(0, 6, (D, P, 24)), -1).reshape(-1)
        o2 = np.rint(pcap[None, :, None] * e).astype(int).reshape(-1); i2 = np.clip(np.rint(o2 * rng.normal(1.0, .04, ND_)), 0, None).astype(int)
        dl = pd.DataFrame({'Date': np.repeat(DATES, P * 24), 'Hour': np.tile(LABELS, D * P), 'Unit': u, 'Process': np.tile(np.repeat(pnames, 24), D),
                           'Style': sty_a[drow], 'PO': po_a[drow], 'Color': col_a[drow], 'Input': i2, 'Output': o2,
                           'Defect': rng.binomial(o2, rng.uniform(.008, .03, ND_)), 'Rework': rng.binomial(o2, rng.uniform(.005, .02, ND_)),
                           'Downtime_Min': np.where(dt2 > 0, dt2, ''), 'Downtime_Reason': np.where(r2 >= 0, D_REASONS[np.clip(r2, 0, 5)], ''), 'Remarks': ''})
        dry_parts.append(dl)
        for d in range(D):
            for k in range(P):
                wip_rows.append([DATES[d], u, pnames[k], int(pcap[k] * rng.uniform(.5, 2.5)), 'DEMO'])
        ca = np.tile(np.repeat(pcap, 3), D)
        b = pd.DataFrame({'Date': np.repeat(DATES, P * 3), 'Resource': np.tile(np.repeat(pnames, 3), D), 'o': da.reshape(-1), 'q': 8 * ca * rng.uniform(.9, 1.0, D * P * 3)})
        b = b.groupby(['Date', 'Resource', 'o'], as_index=False)['q'].sum()
        b['Unit'] = u; b['Style'] = sty_a[b['o']]; b['PO'] = po_a[b['o']]; b['Color'] = col_a[b['o']]; b['Plan_Qty'] = b['q'].round(0).astype(int)
        al_rows.append(b[['Date', 'Unit', 'Resource', 'Style', 'PO', 'Color', 'Plan_Qty']])
    print(u, 'machines', M, 'orders', n, 'wash rows', N)

def fmt(x):
    return x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else x
pd.concat(wash_parts).to_csv(OUT / 'Wash_Log.csv.gz', index=False)
pd.concat(dry_parts).to_csv(OUT / 'Dry_Log.csv.gz', index=False)
pd.concat(al_rows).to_csv(OUT / 'Allotment.csv.gz', index=False)
pd.DataFrame(wip_rows, columns=['Date', 'Unit', 'Stage', 'Opening_WIP', 'Remarks']).to_csv(OUT / 'WIP_Log.csv.gz', index=False)
oc = ['Wash_Plant', 'Buyer', 'Style', 'PO', 'Color', 'Wash_Type', 'CRD', 'CRD_Revisions', 'Updated_CRD', 'Sewing_Unit', 'Order_Qty', 'Plan_Start', 'Plan_End',
      'Shade_Submit_Date', 'Shade_Approval_Date', 'Merchant', 'Prior_Input', 'Prior_Output', 'Remarks']
om = pd.DataFrame(order_rows, columns=oc)
for c in ['CRD', 'Updated_CRD', 'Plan_Start', 'Plan_End', 'Shade_Submit_Date', 'Shade_Approval_Date']:
    om[c] = om[c].map(fmt)
om.to_csv(OUT / 'Order_Master.csv', index=False)
pdl = pd.DataFrame(plan_rows, columns=['Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'Plan_Input', 'Plan_Output'])
pdl['Date'] = pdl['Date'].map(fmt); pdl.groupby(['Date', 'Wash_Plant', 'Style', 'PO', 'Color'], as_index=False)[['Plan_Input', 'Plan_Output']].sum().to_csv(OUT / 'Daily_Plan.csv', index=False)
pd.DataFrame(mm_rows).to_csv(OUT / 'Master_Machine.csv', index=False)
pd.DataFrame(mp_rows).to_csv(OUT / 'Master_Process.csv', index=False)
pd.DataFrame(um_rows).to_csv(OUT / 'Unit_Master.csv', index=False)
pd.DataFrame(DEFAULT_SETTINGS, columns=['Key', 'Value']).to_csv(OUT / 'Settings.csv', index=False)
for f in sorted(OUT.glob('*')):
    print(f.name, round(f.stat().st_size / 1e6, 2), 'MB')
