"""Builds demo Plan Board (October 2026, 31 day blocks, all 10 plants), Plan_History, Audit_Log, Stage_Log and Master_Stage from the existing demo orders / wash log.
Run after make_demo_data.py:  python tools/make_demo_board.py"""
import sys, pathlib, calendar
import numpy as np, pandas as pd
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import calc, board

D = ROOT / 'demo_data'
MONTH = '2026-10'
rng = np.random.default_rng(11)
om = calc.prep_order(pd.read_csv(D / 'Order_Master.csv', dtype=str, keep_default_na=False))
plan = calc.prep_plan(pd.read_csv(D / 'Daily_Plan.csv', dtype=str, keep_default_na=False))
w = pd.read_csv(D / 'Wash_Log.csv.gz', dtype=str, keep_default_na=False, usecols=['Date', 'Unit', 'Style', 'PO', 'Color', 'Input', 'Output', 'Reject'])
for c in ['Input', 'Output', 'Reject']:
    w[c] = pd.to_numeric(w[c], errors='coerce').fillna(0)
w['Date'] = pd.to_datetime(w['Date'])
dl = w.groupby(['Unit', 'Style', 'PO', 'Color', 'Date'])[['Input', 'Output', 'Reject']].sum().reset_index()
m0 = pd.Timestamp(MONTH + '-01')
ndays = calendar.monthrange(m0.year, m0.month)[1]
days = pd.date_range(m0, periods=ndays, freq='D')
last_actual = dl['Date'].max()
ITEMS = ['Denim Pant', 'Jogger', 'Jacket', 'Shorts', 'Twill Pant']
rows, hist, audit = [], [], []
cum = {}
for i, o in om.iterrows():
    u, k = o['Wash_Plant'], (o['Style'], o['PO'], o['Color'])
    x = dl[(dl['Unit'] == u) & (dl['Style'] == k[0]) & (dl['PO'] == k[1]) & (dl['Color'] == k[2])].set_index('Date')
    pr = calc.order_daily_plan(om[om['Wash_Plant'] == u], plan, u, 2.0)
    pr = pr[(pr['Style'] == k[0]) & (pr['PO'] == k[1]) & (pr['Color'] == k[2])].set_index('Date') if len(pr) else pr
    before = x[x.index < m0]
    open_in, open_out = o['Prior_Input'] + before['Input'].sum(), o['Prior_Output'] + before['Output'].sum()
    pin_b = pr[pr.index < m0]['Plan_Input'].sum() if len(pr) else 0.0
    pout_b = pr[pr.index < m0]['Plan_Output'].sum() if len(pr) else 0.0
    in_oct = x[(x.index >= m0)]
    pl_oct = pr[pr.index >= m0] if len(pr) else pr
    done_before = o['Order_Qty'] - open_out <= 0.02 * o['Order_Qty']
    if done_before and not len(in_oct) and not len(pl_oct):
        continue
    if not len(in_oct) and not len(pl_oct) and open_in - open_out <= 0 and open_out >= o['Order_Qty'] * .98:
        continue
    fro = x.index.min() if len(x) and before['Input'].sum() + o['Prior_Input'] > 0 else (m0 - pd.Timedelta(days=12) if o['Prior_Input'] > 0 else pd.NaT)
    rej = float(x['Reject'].sum())
    miss = float(rng.choice([0, 0, 0, 0, 0, 40, 120, 260])) if (open_in + in_oct['Input'].sum() - open_out - in_oct['Output'].sum() - rej) > 600 else 0.0
    rows.append(dict(o=o, key=k, u=u, open_in=open_in, open_out=open_out, sv=pin_b - open_in, wv=pout_b - open_out, fro=fro, rej=rej, miss=miss, x=x, pr=pr, item=ITEMS[i % len(ITEMS)]))

# ---- tidy: no negative WIP in the demo; planners re-plan most open orders (every 5th is left un-replanned => red flag demo)
for n_, r in enumerate(rows):
    o = r['o']
    in_oct = r['x'][r['x'].index >= m0]
    wip_now = r['open_in'] + in_oct['Input'].sum() - r['open_out'] - in_oct['Output'].sum() - r['rej'] - r['miss']
    if wip_now < 0:
        r['open_in'] += -wip_now + 25
        wip_now = 25
    rem_in = o['Order_Qty'] - r['open_in'] - in_oct['Input'].sum()
    r['xsp'], r['xwp'], r['new_end'] = {}, {}, None
    if rem_in > 0.02 * o['Order_Qty'] and n_ % 5 != 0:
        nd = int(min(6, max(2, rem_in // 6000 + 2)))
        fut = pd.date_range(last_actual + pd.Timedelta(days=1), periods=nd, freq='D')
        for d in fut:
            r['xsp'][d] = rem_in / nd
            r['xwp'][d + pd.Timedelta(days=2)] = r['xwp'].get(d + pd.Timedelta(days=2), 0) + rem_in / nd
        for d in fut[:3]:
            r['xwp'][d] = r['xwp'].get(d, 0) + max(wip_now, 0) / 3
        end = fut[-1]
        if pd.isna(o['Plan_End']) or end > o['Plan_End']:
            r['new_end'] = end
    elif (o['Order_Qty'] - r['open_out'] - in_oct['Output'].sum()) > 0.02 * o['Order_Qty'] and n_ % 5 == 0:
        r['demo_end'] = last_actual - pd.Timedelta(days=1 + n_ % 3)      # plan window already over but balance remains -> red flag
    elif (o['Order_Qty'] - r['open_out'] - in_oct['Output'].sum()) > 0.02 * o['Order_Qty'] and wip_now > 0 and n_ % 5 != 0:
        fut = pd.date_range(last_actual + pd.Timedelta(days=1), periods=2, freq='D')
        for d in fut:
            r['xwp'][d] = max(wip_now, 0) / 2

# ---- raw grid (exactly what a sheet read returns)
ncs = len(board.STATIC) + len(board.FORMULA)
width = ncs + 7 * 31
grid = [[''] * width for _ in range(7 + len(rows))]
grid[0][0] = 'HAMEEM GROUP - E2E Plan Execution (Sewing-Wash) | ' + MONTH
grid[1][0] = 'Month'; grid[1][1] = MONTH
for j, (c, lab) in enumerate(board.STATIC + board.FORMULA):
    grid[3][j] = c; grid[5][j] = lab
for n in range(31):
    for q, (c, lab) in enumerate(board.DAY):
        j = ncs + n * 7 + q
        grid[2][j] = (m0 + pd.Timedelta(days=n)).strftime('%Y-%m-%d') if n < ndays else ''
        grid[3][j] = c
        grid[4][j] = f'Day {n + 1}' if q == 0 else ''
        grid[5][j] = lab
grid[6][0] = 'Grand Total'
fmt = lambda v: '' if pd.isna(v) else (v.strftime('%Y-%m-%d') if isinstance(v, pd.Timestamp) else v)
today = last_actual
for r_i, r in enumerate(rows):
    o = r['o']
    row = grid[7 + r_i]
    vals = dict(Wash_Plant=r['u'], Sewing_Unit=o['Sewing_Unit'], Buyer=o['Buyer'], Style=r['key'][0], PO=r['key'][1], Item=r['item'], Color=r['key'][2], Season='SP27',
                CRD=fmt(o['CRD']), Revised_CRD=fmt(o['Updated_CRD']), Order_Qty=o['Order_Qty'], Plan_Start=fmt(o['Plan_Start']), Plan_End=fmt(r['new_end'] if r['new_end'] is not None else r.get('demo_end', o['Plan_End'])),
                Merchant=o['Merchant'], Open_Received=round(r['open_in']), Open_Washed=round(r['open_out']), Open_Sew_Var=round(r['sv']), Open_Wash_Var=round(r['wv']),
                First_Received_On=fmt(r['fro']), Wash_Reject=round(r['rej']), Missing_Body=r['miss'])
    for j, (c, _) in enumerate(board.STATIC):
        v = vals[c]
        row[j] = '' if (isinstance(v, float) and np.isnan(v)) else v
    sa_tot = wa_tot = 0
    for n, d in enumerate(days):
        base = ncs + n * 7
        sp = r['pr']['Plan_Input'].get(d, 0.0) if len(r['pr']) else 0.0
        wp = r['pr']['Plan_Output'].get(d, 0.0) if len(r['pr']) else 0.0
        if d > last_actual and r['xsp'] or d > last_actual and r['xwp']:
            sp, wp = r['xsp'].get(d, 0.0), r['xwp'].get(d, 0.0)
        if sp: row[base] = round(sp)
        if wp: row[base + 3] = round(wp)
        if d <= last_actual:
            sa = r['x']['Input'].get(d, 0.0); wa = r['x']['Output'].get(d, 0.0)
            if sa: row[base + 1] = round(sa)
            if wa: row[base + 4] = round(wa)
            if sp or sa: row[base + 2] = round(sa - sp)
            if wp or wa: row[base + 5] = round(wa - wp)
            sa_tot += round(sa); wa_tot += round(wa)
    row[len(board.STATIC) + 1] = round(r['open_in'] + sa_tot); row[len(board.STATIC) + 2] = round(r['open_out'] + wa_tot)
    row[len(board.STATIC) + 3] = round(r['open_in'] + sa_tot - r['open_out'] - wa_tot - r['rej'] - r['miss'])
pd.DataFrame(grid).to_csv(D / 'Plan_Board.csv.gz', index=False, header=False, compression='gzip')

# ---- plan history and audit (a few realistic entries)
ts = lambda d: (pd.Timestamp(d)).strftime('%Y-%m-%d %H:%M:%S')
pick = rng.choice(len(rows), size=min(12, len(rows)), replace=False)
for n, i in enumerate(pick):
    r, o = rows[i], rows[i]['o']
    base = dict(Wash_Plant=r['u'], Style=r['key'][0], PO=r['key'][1], Color=r['key'][2])
    if n < 6 and pd.notna(o['Plan_End']):
        hist.append(dict(Timestamp=ts(o['Plan_Start'] - pd.Timedelta(days=3, hours=-10)), User='planner@hameem.demo', Field='Plan_End', Old='', New=fmt(o['Plan_End'] - pd.Timedelta(days=3)), Version=1, **base))
        hist.append(dict(Timestamp=ts(o['Plan_End'] - pd.Timedelta(days=2, hours=-11)), User='planner@hameem.demo', Field='Plan_End', Old=fmt(o['Plan_End'] - pd.Timedelta(days=3)), New=fmt(o['Plan_End']), Version=2, **base))
    if pd.notna(o['Updated_CRD']) and pd.notna(o['CRD']) and o['Updated_CRD'] != o['CRD']:
        hist.append(dict(Timestamp=ts(o['CRD'] - pd.Timedelta(days=9, hours=-9)), User='merchant@hameem.demo', Field='Revised_CRD', Old=fmt(o['CRD']), New=fmt(o['Updated_CRD']), Version=1, **base))
for r in rows:
    if r['new_end'] is not None:
        o = r['o']
        hist.append(dict(Timestamp=ts(last_actual + pd.Timedelta(hours=10)), User='planner@hameem.demo', Wash_Plant=r['u'], Style=r['key'][0], PO=r['key'][1], Color=r['key'][2],
                         Field='Plan_End', Old=fmt(o['Plan_End']), New=fmt(r['new_end']), Version=3))
for n, i in enumerate(pick[:5]):
    r = rows[i]
    d = last_actual - pd.Timedelta(days=int(rng.integers(1, 6)))
    old = int(r['x']['Output'].get(d, 0) or 1200)
    audit.append(dict(Timestamp=ts(last_actual + pd.Timedelta(hours=9 + n)), User=['monitor1@hameem.demo', 'monitor2@hameem.demo', ''][n % 3], Wash_Plant=r['u'], Style=r['key'][0],
                      PO=r['key'][1], Color=r['key'][2], Field='WASH_ACT' if n % 2 == 0 else 'SEW_ACT', Date=fmt(d), Old=old, New=old + int(rng.integers(150, 900)), Type='EDIT', Ack=''))
pd.DataFrame(hist, columns=board.HIST_COLS).to_csv(D / 'Plan_History.csv', index=False)
pd.DataFrame(audit, columns=board.AUDIT_COLS).to_csv(D / 'Audit_Log.csv', index=False)

# ---- stage tracker: Receive Store -> Wash -> Dry process -> QC & Packing -> out
STAGES = ['Receive Store', 'Wash', 'Dry Process', 'QC & Packing']
FRAC = [0.80, 0.52, 0.25, 0.0]
pd.DataFrame({'Stage': STAGES, 'Seq': [1, 2, 3, 4]}).to_csv(D / 'Master_Stage.csv', index=False)
sl = []
rng_days = pd.date_range(dl['Date'].min() - pd.Timedelta(days=1), last_actual, freq='D')
for r in rows:
    x = r['x'].reindex(rng_days).fillna(0.0)
    A = r['open_in'] - x.loc[x.index >= m0, 'Input'].sum() - x.loc[x.index < m0, 'Input'].sum() + x['Input'].cumsum()   # cumulative received (opening adjusted)
    WA = r['o']['Prior_Output'] + x['Output'].cumsum() + x['Reject'].cumsum()
    WA.iloc[-1] += r['miss']
    passed = []
    for f in FRAC:
        p_ = (WA + f * (A - WA).clip(lower=0)).round()
        passed.append(p_)
    prev_in = A.round()
    for k, st_ in enumerate(STAGES):
        pin = prev_in if k == 0 else passed[k - 1]
        pout = passed[k]
        din = pin.diff().fillna(pin.iloc[0]); dout = pout.diff().fillna(pout.iloc[0])
        t = pd.DataFrame({'Date': rng_days, 'Wash_Plant': r['u'], 'Style': r['key'][0], 'PO': r['key'][1], 'Color': r['key'][2], 'Stage': st_, 'Pcs_In': din.values, 'Pcs_Out': dout.values, 'Remarks': ''})
        sl.append(t[(t['Pcs_In'] != 0) | (t['Pcs_Out'] != 0)])
SL = pd.concat(sl, ignore_index=True)
SL['Date'] = SL['Date'].dt.strftime('%Y-%m-%d')
SL.to_csv(D / 'Stage_Log.csv.gz', index=False, compression='gzip')
print('orders', len(rows), 'grid', len(grid), 'x', width, '| stage rows', len(SL), '| hist', len(hist), '| audit', len(audit))
