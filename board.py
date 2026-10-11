"""Plan Board (sewing delivery -> wash production, one row per PO, one 7-column block per day): parsing, status, EDD+FIFO sequence,
capacity-based forecast, plant WIP, stage tracker and audit helpers. Pure pandas, no Streamlit."""
import re
import numpy as np
import pandas as pd
import calc
from calc import KEYS, NO_PO, NO_COLOR, safe_div, to_num, parse_date

# (code, label) - the code sits in the hidden code row of the sheet and is what the parser reads
STATIC = [('Wash_Plant', 'Wash Plant'), ('Sewing_Unit', 'Sewing Unit'), ('Buyer', 'Buyer'), ('Style', 'Style'), ('PO', 'PO'), ('Item', 'Item'),
          ('Color', 'Color'), ('Season', 'Season'), ('CRD', 'CRD Date'), ('Revised_CRD', 'Revised CRD'), ('Order_Qty', 'Order Quantity'),
          ('Plan_Start', 'Wash Plan Start'), ('Plan_End', 'Wash Plan End'), ('Merchant', 'Merchant'),
          ('Open_Received', 'Opening Received (before this month)'), ('Open_Washed', 'Opening Washed (before this month)'),
          ('Open_Sew_Var', 'Sewing Plan Variation (Opening)'), ('Open_Wash_Var', 'Wash Plan Variation (Opening)'),
          ('First_Received_On', 'First Received On (carry forward)'), ('Wash_Reject', 'Wash Reject Qty'), ('Missing_Body', 'Missing Body')]
FORMULA = [('Eff_CRD', 'Effective CRD'), ('Received', 'Received from Sewing'), ('Washed', 'Wash Throughput'), ('WIP', 'Wash WIP'), ('Balance', 'Balance to Wash'),
           ('First_Receive', 'First Receive Date'), ('Priority', 'Wash Priority (EDD then FIFO)'), ('Forecast', 'Forecasted Completion'),
           ('Sew_Delay', 'Sewing Delay Days'), ('Risk', 'Risk (Yes/No)')]
DAY = [('SEW_PLAN', 'Sewing Planned Delivery'), ('SEW_ACT', 'Sewing Actual Delivery'), ('SEW_VAR', 'Variation'), ('WASH_PLAN', 'Wash Planned Production'),
       ('WASH_ACT', 'Wash Actual Production'), ('WASH_VAR', 'Variation'), ('REMARK', 'Remarks')]
STATIC_CODES = [c for c, _ in STATIC]
ALL_STATIC = STATIC_CODES + [c for c, _ in FORMULA]
DAY_CODES = [c for c, _ in DAY]
NUM_STATIC = ['Order_Qty', 'Open_Received', 'Open_Washed', 'Open_Sew_Var', 'Open_Wash_Var', 'Wash_Reject', 'Missing_Body']
DATE_STATIC = ['CRD', 'Revised_CRD', 'Plan_Start', 'Plan_End', 'First_Received_On']
TXT_STATIC = ['Wash_Plant', 'Sewing_Unit', 'Buyer', 'Style', 'PO', 'Item', 'Color', 'Season', 'Merchant']
HEADER_ROW = 4          # row with codes in the sheet (1-based); the date row is HEADER_ROW - 1
FIRST_DATA_ROW = 8
BALANCE_TOL = calc.BALANCE_TOL
PLAN_FIELDS = ['Plan_Start', 'Plan_End', 'CRD', 'Revised_CRD', 'Order_Qty']
_TOKEN = re.compile(r'[A-Za-z_]+')


# ================================================================ parsing
_ISO = re.compile(r'\d{4}-\d{2}-\d{2}')


def _date_in(txt):
    m = _ISO.search(txt)
    if m:
        return m.group(0)
    for tok in txt.split():
        if any(ch.isdigit() for ch in tok):
            return tok
    return txt.strip()


def _codes_from_labels(labs):
    out = {}
    for j, lab in enumerate(labs):
        toks = _TOKEN.findall(str(lab))
        dc = [t for t in toks if t in DAY_CODES]
        sc = [t for t in toks if t in ALL_STATIC]
        if dc:
            txt = str(lab)
            for t in dc:
                txt = txt.replace(t, ' ')
            out[j] = ('day', dc[-1], _date_in(txt))
        elif sc:
            out[j] = ('static', sc[-1], None)
    return out


def _raw_header(df):
    """Find the code row inside the first rows (raw / gspread / headers=0 reads). Returns (labels, data_df) or None."""
    head = df.head(14).astype(str)
    for i in range(len(head)):
        row = head.iloc[i].tolist()
        hits = sum(1 for v in row if v.strip() in STATIC_CODES)
        if hits >= 5:
            dates = head.iloc[i - 1].tolist() if i > 0 else [''] * len(row)
            labs = [f'{d} {c}'.strip() for d, c in zip(dates, row)]
            return labs, df.iloc[i + 1:].reset_index(drop=True)
    return None


def parse_board(df):
    """Wide sheet -> (orders, daily). Accepts a read with labelled columns (gviz headers=N) or a raw grid. Tolerant of Grand Total / header rows."""
    empty = (pd.DataFrame(columns=['Sheet_Month'] + STATIC_CODES), pd.DataFrame(columns=['Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT', 'REMARK']))
    if df is None or df.empty:
        return empty
    labs = [str(c) for c in df.columns]
    codes = _codes_from_labels(labs)
    data = df
    if sum(1 for v in codes.values() if v[0] == 'static') < 4:
        r = _raw_header(df)
        if r is None:
            return empty
        labs, data = r
        codes = _codes_from_labels(labs)
    data = data.reset_index(drop=True)
    stat_idx = {v[1]: j for j, v in codes.items() if v[0] == 'static'}
    O = pd.DataFrame({c: (data.iloc[:, stat_idx[c]] if c in stat_idx else '') for c in STATIC_CODES})
    for c in TXT_STATIC:
        O[c] = O[c].fillna('').astype(str).str.strip().replace({'nan': '', 'None': ''})
    keep = (O['Style'] != '') & ~O['Wash_Plant'].str.lower().isin(['wash plant', 'grand total']) & ~O['Style'].str.lower().isin(['style'])
    O.loc[O['PO'] == '', 'PO'] = NO_PO
    O.loc[O['Color'] == '', 'Color'] = NO_COLOR
    ex = O['Merchant'].str.upper().str.startswith('EXAMPLE') | O['Style'].str.upper().str.startswith('EXAMPLE')
    keep &= ~ex
    for c in DATE_STATIC:
        O[c] = parse_date(O[c])
    for c in NUM_STATIC:
        O[c] = to_num(O[c].astype(str)).fillna(0 if c != 'Order_Qty' else np.nan)
    rows = np.flatnonzero(keep.values)
    day_cols = [(j, v[1], v[2]) for j, v in codes.items() if v[0] == 'day']
    # dates of the day columns
    dts = parse_date(pd.Series([t for _, _, t in day_cols])) if day_cols else pd.Series([], dtype='datetime64[ns]')
    parts = []
    for (j, code, _), d in zip(day_cols, dts):
        if pd.isna(d) or code in ('SEW_VAR', 'WASH_VAR'):
            continue
        col = data.iloc[rows, j]
        if code == 'REMARK':
            v = col.fillna('').astype(str).str.strip().replace({'nan': ''})
        else:
            v = to_num(col.astype(str))
        parts.append(pd.DataFrame({'ri': rows, 'Date': d, 'code': code, 'v': v.values}))
    O = O.loc[keep].reset_index(drop=True)
    if not parts:
        O.insert(0, 'Sheet_Month', '')
        return O, empty[1]
    L = pd.concat(parts, ignore_index=True)
    ri_map = {r: i for i, r in enumerate(rows)}
    L['oi'] = L['ri'].map(ri_map)
    txt = L[L['code'] == 'REMARK'].copy()
    num = L[L['code'] != 'REMARK']
    num = num[num['v'].notna()]
    W = num.pivot_table(index=['oi', 'Date'], columns='code', values='v', aggfunc='sum').reset_index()
    for c in ('SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT'):
        if c not in W:
            W[c] = 0.0
        W[c] = W[c].fillna(0.0)
    tx = txt[txt['v'] != ''][['oi', 'Date', 'v']].rename(columns={'v': 'REMARK'})
    W = W.merge(tx, on=['oi', 'Date'], how='outer') if len(tx) else W.assign(REMARK='')
    W['REMARK'] = W['REMARK'].fillna('')
    for c in ('SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT'):
        W[c] = W[c].fillna(0.0)
    W = W[(W[['SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT']].abs().sum(axis=1) > 0) | (W['REMARK'] != '')]
    for c in ['Wash_Plant', 'Style', 'PO', 'Color']:
        W[c] = W['oi'].map(O[c])
    W = W.drop(columns=['oi'])
    month = W['Date'].dt.strftime('%Y-%m').mode().iat[0] if len(W) else ''
    O.insert(0, 'Sheet_Month', month)
    W.insert(0, 'Sheet_Month', month)
    cols = ['Sheet_Month', 'Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT', 'REMARK']
    return O, W[cols].reset_index(drop=True)


def merge_boards(parts):
    """parts: list of (orders, daily) from several monthly sheets. Static fields from the latest month, opening balances from the earliest."""
    parts = [(o, d) for o, d in parts if o is not None and len(o)]
    if not parts:
        return parse_board(None)
    O = pd.concat([o for o, _ in parts], ignore_index=True)
    D = pd.concat([d for _, d in parts if len(d)], ignore_index=True) if any(len(d) for _, d in parts) else parse_board(None)[1]
    K = ['Wash_Plant'] + KEYS
    O = O.sort_values('Sheet_Month', kind='stable')
    first = O.drop_duplicates(K, keep='first')[K + ['Open_Received', 'Open_Washed', 'Open_Sew_Var', 'Open_Wash_Var']]
    last = O.drop_duplicates(K, keep='last').drop(columns=['Open_Received', 'Open_Washed', 'Open_Sew_Var', 'Open_Wash_Var'])
    O2 = last.merge(first, on=K, how='left')
    fro = O.groupby(K)['First_Received_On'].min().rename('FRO').reset_index()
    O2 = O2.merge(fro, on=K, how='left')
    O2['First_Received_On'] = O2['FRO'].where(O2['FRO'].notna(), O2['First_Received_On'])
    O2 = O2.drop(columns='FRO')
    if len(D):
        D = D.sort_values('Sheet_Month', kind='stable').drop_duplicates(['Date'] + K, keep='last')
    return O2[O.columns].reset_index(drop=True), D.reset_index(drop=True)


# ================================================================ status per order
def board_status(O, D, asof, plan_hist=None, audit=None):
    """One row per order in the same shape as calc.style_details (+ board extras), cumulative till `asof` (a date, daily resolution)."""
    asof = pd.Timestamp(asof).normalize()
    K = ['Wash_Plant'] + KEYS
    if O is None or O.empty:
        return pd.DataFrame()
    t = O.copy()
    d = D[D['Date'] <= asof] if D is not None and len(D) else pd.DataFrame(columns=['Date'] + K + ['SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT'])
    if len(d):
        g = d.groupby(K).agg(cSP=('SEW_PLAN', 'sum'), cSA=('SEW_ACT', 'sum'), cWP=('WASH_PLAN', 'sum'), cWA=('WASH_ACT', 'sum'))
        sa = d[d['SEW_ACT'] > 0].groupby(K)['Date'].agg(First_In_Date='min', Last_In_Date='max')
        wa = d[d['WASH_ACT'] > 0].groupby(K)['Date'].agg(First_Out_Date='min', Last_Out_Date='max')
        r3 = d[d['Date'] > asof - pd.Timedelta(days=3)].groupby(K)['WASH_ACT'].sum().rename('Rate3_sum')
        nsp = d[d['SEW_PLAN'] > 0].groupby(K)['SEW_PLAN'].agg(['sum', 'count'])
        avg_sp = (nsp['sum'] / nsp['count']).rename('Avg_SP')
        ex = g.join(sa).join(wa).join(r3).join(avg_sp).reset_index()
        t = t.merge(ex, on=K, how='left')
    for c in ['cSP', 'cSA', 'cWP', 'cWA', 'Rate3_sum', 'Avg_SP']:
        if c not in t:
            t[c] = 0.0
        t[c] = t[c].fillna(0.0)
    for c in ['First_In_Date', 'Last_In_Date', 'First_Out_Date', 'Last_Out_Date']:
        if c not in t:
            t[c] = pd.NaT
        t[c] = pd.to_datetime(t[c])
    t['Input'] = t['Open_Received'] + t['cSA']
    t['Output'] = t['Open_Washed'] + t['cWA']
    t['Input_Plan'] = t['Open_Received'] + t['Open_Sew_Var'] + t['cSP']
    t['Output_Plan'] = t['Open_Washed'] + t['Open_Wash_Var'] + t['cWP']
    t['Input_Var'] = t['Input'] - t['Input_Plan']
    t['Output_Var'] = t['Output'] - t['Output_Plan']
    t['Achv_Pct'] = safe_div(t['Output'], t['Output_Plan']) * 100
    t['Reject'] = t['Wash_Reject']
    t['WIP'] = t['Input'] - t['Output'] - t['Wash_Reject'] - t['Missing_Body']
    for c in ['Rewash', 'Rewash_Output', 'Rewash_WIP', 'Defect', 'QC_Inspected']:
        t[c] = 0.0
    t['Total_WIP'] = t['WIP']
    t['Rewash_Pct'] = np.nan
    t['DHU'] = np.nan
    t['Reject_Pct'] = safe_div(t['Reject'], t['Input']) * 100
    t['Balance'] = (t['Order_Qty'] - t['Output']).clip(lower=0)
    t['Balance'] = t['Balance'].where(t['Balance'] > BALANCE_TOL * t['Order_Qty'].fillna(0), 0.0)
    t['Pending_Input'] = (t['Order_Qty'] - t['Input']).clip(lower=0)
    t['Eff_CRD'] = t['Revised_CRD'].where(t['Revised_CRD'].notna(), t['CRD'])
    t['Updated_CRD'] = t['Revised_CRD']
    t['Days_to_CRD'] = (t['Eff_CRD'] - asof).dt.days
    t['Rate3'] = t['Rate3_sum'] / 3.0
    open_ = (t['Balance'] > 0) | (t['WIP'] > BALANCE_TOL * t['Order_Qty'].fillna(0))
    t['Overrun_Days'] = np.where(open_ & t['Plan_End'].notna() & (t['Plan_End'] < asof), (asof - t['Plan_End']).dt.days, 0)
    t['Sew_Delay_Days'] = np.where(t['Avg_SP'] > 0, (t['Input_Plan'] - t['Input']).clip(lower=0) / t['Avg_SP'].replace(0, np.nan), 0.0)
    fro = t['First_Received_On'].where(t['First_Received_On'].notna(), t['Plan_Start'].where(t['Open_Received'] > 0))
    t['First_Receive_Date'] = pd.concat([fro, t['First_In_Date']], axis=1).min(axis=1)
    # priority: earliest delivery date first, then first-in-first-out, then PO
    far = pd.Timestamp('2100-01-01')
    key = pd.DataFrame({'p': t['Wash_Plant'], 'e': t['Eff_CRD'].fillna(far), 'f': t['First_Receive_Date'].fillna(far), 'po': t['PO'], 'o': open_})
    od = key[key['o']].sort_values(['p', 'e', 'f', 'po'], kind='stable')
    t['Priority'] = np.nan
    t.loc[od.index, 'Priority'] = od.groupby('p').cumcount() + 1
    # history / audit
    t['Plan_Revisions'] = 0
    t['CRD_Revisions'] = 0
    t['Edited'] = 0
    if plan_hist is not None and len(plan_hist):
        h = plan_hist
        for col, fields in (('Plan_Revisions', ['Plan_Start', 'Plan_End']), ('CRD_Revisions', ['CRD', 'Revised_CRD'])):
            c = h[h['Field'].isin(fields)].groupby(K).size().rename(col).reset_index()
            t = t.drop(columns=col).merge(c, on=K, how='left')
            t[col] = t[col].fillna(0).astype(int)
    if audit is not None and len(audit):
        a = audit[audit['Type'].astype(str).str.upper().str.startswith('EDIT')].groupby(K).size().rename('Edited').reset_index()
        t = t.drop(columns='Edited').merge(a, on=K, how='left')
        t['Edited'] = t['Edited'].fillna(0).astype(int)
    t['Wash_Type'] = ''
    t['Machines'] = ''
    t['Machines_Full'] = ''
    t['Prior_Input'] = t['Open_Received']
    t['Prior_Output'] = t['Open_Washed']
    t['Plan_Source'] = 'Plan Board'
    for c in ['Hold_First', 'Hold_Last', 'Approval_Days']:
        t[c] = np.nan
    t['Shade_Approval_Date'] = pd.NaT
    t = t.sort_values(['Eff_CRD', 'Priority'], na_position='last').reset_index(drop=True)
    cols = [c for c, _ in calc.DETAIL_COLS] + ['Machines_Full', 'Plan_Source', 'Order_Qty', 'Prior_Input', 'Prior_Output', 'Balance', 'Pending_Input', 'Eff_CRD',
                                               'Days_to_CRD', 'Rate3', 'QC_Inspected', 'Item', 'Season', 'Plan_Start', 'Plan_End', 'Missing_Body', 'Overrun_Days',
                                               'Sew_Delay_Days', 'Priority', 'First_Receive_Date', 'Plan_Revisions', 'Edited']
    return t[cols]


def red_flags(S):
    """Plain-language flag text per order (empty string = no flag)."""
    f = []
    for r in S.itertuples():
        x = []
        if getattr(r, 'Overrun_Days', 0) and r.Overrun_Days > 0:
            x.append(f'Plan end passed {int(r.Overrun_Days)} d ago, balance {r.Balance:,.0f}')
        if r.Balance > 0 and r.Days_to_CRD < 0:
            x.append(f'CRD passed {int(-r.Days_to_CRD)} d ago')
        elif r.Balance > 0 and r.Days_to_CRD <= 7:
            x.append(f'CRD in {int(r.Days_to_CRD)} d')
        if getattr(r, 'Sew_Delay_Days', 0) and r.Sew_Delay_Days >= 1:
            x.append(f'Sewing {r.Sew_Delay_Days:.0f} d behind')
        if getattr(r, 'Edited', 0):
            x.append('Data edited after entry')
        f.append('; '.join(x))
    return pd.Series(f, index=S.index)


# ================================================================ forecast (EDD + FIFO capacity simulation)
def wash_forecast(S, D, cap_by_plant, asof, horizon=60):
    """Walk forward day by day. Each plant has a daily wash capacity; it is filled in priority order (earliest CRD, then FIFO, then PO)
    from pieces already in the plant plus sewing deliveries planned for later days. Returns (forecast per order, suggested daily plan)."""
    asof = pd.Timestamp(asof).normalize()
    K = ['Wash_Plant'] + KEYS
    open_ = S[(S['Balance'] > 0) & S['Priority'].notna()].copy()
    fut = D[D['Date'] > asof] if D is not None and len(D) else pd.DataFrame(columns=['Date'] + K + ['SEW_PLAN'])
    fut = fut[fut['SEW_PLAN'] > 0]
    arr = {}
    for r in fut.itertuples():
        arr.setdefault((r.Wash_Plant, r.Style, r.PO, r.Color), {})[r.Date] = r.SEW_PLAN
    res, plan_rows = [], []
    days = pd.date_range(asof + pd.Timedelta(days=1), periods=horizon, freq='D')
    for plant, g in open_.groupby('Wash_Plant'):
        g = g.sort_values('Priority')
        cap = float(cap_by_plant.get(plant, np.nan))
        st = {}
        for r in g.itertuples():
            k = (plant, r.Style, r.PO, r.Color)
            a = arr.get(k, {})
            sched = min(sum(a.values()), r.Pending_Input)
            st[k] = dict(r=r, wip=max(r.WIP, 0.0), need=r.Balance - 0.0, arr=a, left_arr=r.Pending_Input, done=None, sched_gap=max(r.Pending_Input - sched, 0.0))
        if not (cap > 0):
            for k, s in st.items():
                res.append((k, pd.NaT, 'No capacity set'))
            continue
        for d in days:
            left = cap
            for k, s in st.items():
                x = min(s['arr'].get(d, 0.0), s['left_arr'])
                s['wip'] += x
                s['left_arr'] -= x
            for k, s in st.items():
                if s['done'] is not None or left <= 0:
                    continue
                take = min(s['wip'], s['need'], left)
                if take > 0:
                    s['wip'] -= take
                    s['need'] -= take
                    left -= take
                    plan_rows.append((d, *k, take))
                if s['need'] <= BALANCE_TOL * s['r'].Order_Qty:
                    s['done'] = d
        for k, s in st.items():
            r = s['r']
            if s['done'] is not None:
                res.append((k, s['done'], 'ok'))
            elif s['sched_gap'] > BALANCE_TOL * (r.Order_Qty or 0):
                res.append((k, pd.NaT, 'No sewing plan for ' + f"{s['sched_gap']:,.0f} pcs"))
            elif s['wip'] <= 0 and s['left_arr'] <= 0:
                res.append((k, pd.NaT, f"Short {s['need']:,.0f} pcs (reject / missing body)"))
            else:
                res.append((k, pd.NaT, f'Beyond {horizon} days'))
    F = pd.DataFrame([dict(Wash_Plant=k[0], Style=k[1], PO=k[2], Color=k[3], Forecast_Date=fd, Note=n) for k, fd, n in res])
    P = pd.DataFrame(plan_rows, columns=['Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'Suggested_Wash'])
    out = S[K + ['Buyer', 'Sewing_Unit', 'Eff_CRD', 'Days_to_CRD', 'Order_Qty', 'Input', 'Output', 'WIP', 'Balance', 'Pending_Input', 'Priority', 'First_Receive_Date',
                 'Plan_End', 'Overrun_Days']].copy()
    out = out[out['Priority'].notna()].merge(F, on=K, how='left') if len(F) else out.assign(Forecast_Date=pd.NaT, Note='')
    out['Late_Days'] = (out['Forecast_Date'] - out['Eff_CRD']).dt.days
    out['Note'] = out['Note'].where(out['Note'].notna(), np.where(out['Balance'] <= 0, 'Delivered (WIP remains)', ''))
    out['Verdict'] = np.where(out['Forecast_Date'].isna(), out['Note'].fillna(''), np.where(out['Late_Days'] > 0, 'Will miss CRD', 'On time'))
    return out.sort_values(['Wash_Plant', 'Priority']).reset_index(drop=True), P


# ================================================================ plant-level daily WIP from the board
def board_plant_daily(O, D, units, d0, d1):
    d0, d1 = pd.Timestamp(d0).normalize(), pd.Timestamp(d1).normalize()
    idx = pd.date_range(d0, d1, freq='D')
    fr = []
    for u in units:
        o = O[O['Wash_Plant'] == u]
        d = D[D['Wash_Plant'] == u] if len(D) else D
        base = float((o['Open_Received'] - o['Open_Washed']).sum())
        before = d[d['Date'] < d0] if len(d) else d
        base += float((before['SEW_ACT'] - before['WASH_ACT']).sum()) if len(before) else 0.0
        g = d[(d['Date'] >= d0) & (d['Date'] <= d1)].groupby('Date')[['SEW_ACT', 'WASH_ACT']].sum() if len(d) else pd.DataFrame(columns=['SEW_ACT', 'WASH_ACT'])
        g = g.reindex(idx).fillna(0.0)
        cl = base + (g['SEW_ACT'] - g['WASH_ACT']).cumsum()
        x = pd.DataFrame({'Date': idx, 'Wash_Plant': u, 'Opening_WIP': (cl - (g['SEW_ACT'] - g['WASH_ACT'])).values, 'Input': g['SEW_ACT'].values,
                          'Output': g['WASH_ACT'].values, 'Closing_WIP': cl.values})
        x['Change'] = x['Closing_WIP'] - x['Opening_WIP']
        x['Rewash'] = 0.0
        x['Rewash_Output'] = 0.0
        fr.append(x)
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


def daily_matrix(O, D, plant, month, order_keys=None):
    """Wide view like the Excel: one row per order, per day Sewing plan/actual and Wash plan/actual, for one plant and 'YYYY-MM'."""
    p = pd.Period(month, 'M')
    ndays = p.days_in_month
    o = O[O['Wash_Plant'] == plant]
    d = D[(D['Wash_Plant'] == plant) & (D['Date'].dt.to_period('M') == p)] if len(D) else D
    return o, d, ndays


# ================================================================ stage tracker (where is each PO now)
def stage_position(L, asof, master_stage=None):
    """Stage_Log rows (Date, Wash_Plant, Style, PO, Color, Stage, Pcs_In, Pcs_Out) -> pcs currently in each stage per order."""
    if L is None or L.empty:
        return pd.DataFrame(), []
    d = L[L['Date'] <= pd.Timestamp(asof).normalize()]
    g = d.groupby(['Wash_Plant'] + KEYS + ['Stage']).agg(In=('Pcs_In', 'sum'), Out=('Pcs_Out', 'sum')).reset_index()
    g['Here'] = g['In'] - g['Out']
    order = stage_order(L, master_stage)
    w = g.pivot_table(index=['Wash_Plant'] + KEYS, columns='Stage', values='Here', aggfunc='sum').reindex(columns=order).fillna(0.0).reset_index()
    return w, order


def stage_order(L, master_stage=None):
    if master_stage is not None and len(master_stage):
        m = master_stage.sort_values('Seq')
        o = [s for s in m['Stage'] if s in set(L['Stage'])]
        return o + [s for s in L['Stage'].unique() if s not in o]
    if 'Seq' in L.columns and L['Seq'].notna().any():
        return list(L.dropna(subset=['Seq']).sort_values('Seq')['Stage'].drop_duplicates())
    return list(L['Stage'].drop_duplicates())


def prep_stage_log(df):
    cols = ['Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'Stage', 'Pcs_In', 'Pcs_Out', 'Remarks']
    d = calc._ensure(df if df is not None else pd.DataFrame(), cols)
    d['Date'] = parse_date(d['Date'])
    for c in ['Wash_Plant', 'Style', 'PO', 'Color', 'Stage']:
        d[c] = d[c].fillna('').astype(str).str.strip().replace({'nan': ''})
    d.loc[d['PO'] == '', 'PO'] = NO_PO
    d.loc[d['Color'] == '', 'Color'] = NO_COLOR
    d['Pcs_In'] = to_num(d['Pcs_In']).fillna(0)
    d['Pcs_Out'] = to_num(d['Pcs_Out']).fillna(0)
    return d[d['Date'].notna() & (d['Stage'] != '') & (d['Style'] != '')].reset_index(drop=True)


def prep_master_stage(df):
    d = calc._ensure(df if df is not None else pd.DataFrame(), ['Stage', 'Seq'])
    d['Stage'] = d['Stage'].fillna('').astype(str).str.strip()
    d['Seq'] = to_num(d['Seq'])
    return d[d['Stage'] != ''].reset_index(drop=True)


# ================================================================ audit / history tabs
AUDIT_COLS = ['Timestamp', 'User', 'Wash_Plant', 'Style', 'PO', 'Color', 'Field', 'Date', 'Old', 'New', 'Type', 'Ack']
HIST_COLS = ['Timestamp', 'User', 'Wash_Plant', 'Style', 'PO', 'Color', 'Field', 'Old', 'New', 'Version']


def _prep_text_log(df, cols):
    d = calc._ensure(df if df is not None else pd.DataFrame(), cols)
    for c in ['User', 'Wash_Plant', 'Style', 'PO', 'Color', 'Field', 'Old', 'New'] + (['Type', 'Ack'] if 'Type' in cols else []):
        d[c] = d[c].fillna('').astype(str).str.strip().replace({'nan': ''})
    d.loc[d['PO'] == '', 'PO'] = NO_PO
    d.loc[d['Color'] == '', 'Color'] = NO_COLOR
    d['Timestamp'] = pd.to_datetime(d['Timestamp'], errors='coerce', format='mixed')
    return d[d['Style'] != ''].reset_index(drop=True)


def prep_audit(df):
    d = _prep_text_log(df, AUDIT_COLS)
    d['Date'] = parse_date(d['Date'])
    return d.sort_values('Timestamp', ascending=False).reset_index(drop=True)


def prep_hist(df):
    return _prep_text_log(df, HIST_COLS).sort_values('Timestamp', ascending=False).reset_index(drop=True)
