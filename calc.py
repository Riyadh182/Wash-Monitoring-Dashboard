"""Pure-pandas calculation layer (no Streamlit imports) so it can be unit-tested."""
import re
import numpy as np
import pandas as pd

WASH_NUM = ['Input', 'Output', 'QC_Inspected', 'Defect', 'Rewash', 'Rewash_Output', 'Reject', 'Downtime_Min']
DRY_NUM = ['Input', 'Output', 'Defect', 'Rework', 'Downtime_Min']
WASH_COLS = ['Date', 'Hour', 'Unit', 'Machine_ID', 'Wash_Type', 'Style', 'PO', 'Color', 'Input', 'Output', 'QC_Inspected',
             'Defect', 'Rewash', 'Rewash_Output', 'Reject', 'Downtime_Min', 'Downtime_Reason', 'Remarks']
DRY_COLS = ['Date', 'Hour', 'Unit', 'Process', 'Style', 'PO', 'Color', 'Input', 'Output', 'Defect', 'Rework',
            'Downtime_Min', 'Downtime_Reason', 'Remarks']
ORDER_COLS = ['Wash_Plant', 'Buyer', 'Style', 'PO', 'Color', 'Wash_Type', 'CRD', 'CRD_Revisions', 'Updated_CRD', 'Sewing_Unit',
              'Order_Qty', 'Plan_Start', 'Plan_End', 'Shade_Submit_Date', 'Shade_Approval_Date', 'Merchant', 'Remarks']
PLAN_COLS = ['Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'Plan_Input', 'Plan_Output']
KEYS = ['Style', 'PO', 'Color']
NO_PO, NO_COLOR = '(no PO)', '(no color)'
WIP_COLS = ['Date', 'Unit', 'Stage', 'Opening_WIP', 'Remarks']
MACHINE_COLS = ['Unit', 'Machine_ID', 'Type', 'Plan_per_hr', 'Active']
PROCESS_COLS = ['Unit', 'Process', 'Machines', 'Capacity_per_day', 'Active']
HOURS = list(range(1, 25))
NO_STYLE = '(no style)'

DEFAULT_SETTINGS = dict(Run_Hours=24.0, Day_Start_Hour=8.0, Plan_Basis=1.0, Target_Pct=0.95,
                        Alert_Pct=0.80, Max_Defect_Pct=0.03, Max_Rewash_Pct=0.02, Output_Lag_Days=2.0)
_PCT_KEYS = {'Plan_Basis', 'Target_Pct', 'Alert_Pct', 'Max_Defect_Pct', 'Max_Rewash_Pct'}


# ---------------------------------------------------------------- helpers
def parse_settings(df):
    s = dict(DEFAULT_SETTINGS)
    if df is not None and len(df) and {'Key', 'Value'} <= set(df.columns):
        for k, v in zip(df['Key'], df['Value']):
            k = str(k).strip()
            if k not in s:
                continue
            try:
                x = float(str(v).replace('%', '').replace(',', '').strip())
            except ValueError:
                continue
            if k in _PCT_KEYS and x > 1.5:
                x = x / 100.0
            s[k] = x
    return s


def hour_labels(day_start=8):
    day_start = int(day_start)
    return [f"{(day_start + i) % 24:02d}:00-{(day_start + i + 1) % 24:02d}:00" for i in range(24)]


def shift_of(idx):
    if pd.isna(idx):
        return np.nan
    return 'A' if idx <= 8 else ('B' if idx <= 16 else 'C')


def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(',', '', regex=False).str.strip(), errors='coerce')


def parse_date(s):
    num = pd.to_numeric(s, errors='coerce')
    out = pd.to_datetime(num, unit='D', origin='1899-12-30', errors='coerce')
    mask = out.isna()
    if mask.any():
        out = out.copy()
        out[mask] = pd.to_datetime(s[mask].astype(str).str.strip(), errors='coerce', format='mixed')
    return out.dt.normalize()


def hour_idx(series, day_start):
    start = pd.to_numeric(series.astype(str).str.extract(r'^\s*(\d{1,2})')[0], errors='coerce')
    start = start.where(start <= 23)
    return ((start - int(day_start)) % 24) + 1


def _ensure(df, cols):
    d = df.copy()
    for c in cols:
        if c not in d.columns:
            d[c] = np.nan
    return d


def _prep_log(df, cols, nums, key_col, day_start):
    """Returns (clean, rejected). Rows with no numbers entered yet (blank skeleton rows) are ignored."""
    d = _ensure(df, cols)
    d = d[~d['Remarks'].astype(str).str.upper().str.startswith('EXAMPLE')].copy()
    d['Date'] = parse_date(d['Date'])
    d['Hour_Idx'] = hour_idx(d['Hour'], day_start)
    for c in nums:
        d[c] = to_num(d[c])
    d = d[d[nums].notna().any(axis=1)].copy()
    for c in ('Unit', key_col, 'Style', 'PO', 'Color', 'Downtime_Reason'):
        d[c] = d[c].fillna('').astype(str).str.strip().replace({'nan': '', 'None': ''})
    if 'Machine_ID' == key_col:
        blank = d['Unit'] == ''
        d.loc[blank, 'Unit'] = d.loc[blank, 'Machine_ID'].str.rsplit('-', n=2).str[0]
    d.loc[d['Style'] == '', 'Style'] = NO_STYLE
    d.loc[d['PO'] == '', 'PO'] = NO_PO
    d.loc[d['Color'] == '', 'Color'] = NO_COLOR
    d[nums] = d[nums].fillna(0)
    bad = d['Date'].isna() | d['Hour_Idx'].isna() | (d[key_col] == '')
    rejected = d[bad].copy()
    rejected['Reason'] = np.where(rejected['Date'].isna(), 'Bad/missing date',
                          np.where(rejected['Hour_Idx'].isna(), 'Bad/missing hour slot', 'Missing ID'))
    d = d[~bad].copy()
    d['Hour_Idx'] = d['Hour_Idx'].astype(int)
    d['Shift'] = d['Hour_Idx'].map(shift_of)
    return d, rejected


def prep_wash(df, day_start=8):
    d, rej = _prep_log(df, WASH_COLS, WASH_NUM, 'Machine_ID', day_start)
    d['Wash_Type'] = d['Wash_Type'].fillna('').astype(str).str.strip()
    return d, rej


def prep_dry(df, day_start=8):
    return _prep_log(df, DRY_COLS, DRY_NUM, 'Process', day_start)


def prep_wip(df):
    d = _ensure(df, WIP_COLS)
    d['Date'] = parse_date(d['Date'])
    d['Opening_WIP'] = to_num(d['Opening_WIP']).fillna(0)
    d['Unit'] = d['Unit'].astype(str).str.strip()
    d['Stage'] = d['Stage'].astype(str).str.strip()
    return d[d['Date'].notna() & ~d['Remarks'].astype(str).str.upper().str.startswith('EXAMPLE')].copy()


def prep_machine(df):
    d = _ensure(df, MACHINE_COLS)
    d['Plan_per_hr'] = to_num(d['Plan_per_hr']).fillna(0)
    d['Active'] = d['Active'].astype(str).str.strip().str.upper().replace({'': 'Y', 'NAN': 'Y'})
    for c in ('Unit', 'Machine_ID', 'Type'):
        d[c] = d[c].astype(str).str.strip()
    return d[d['Machine_ID'] != ''].drop_duplicates('Machine_ID').copy()


def prep_process(df):
    d = _ensure(df, PROCESS_COLS)
    d['Capacity_per_day'] = to_num(d['Capacity_per_day']).fillna(0)
    d['Machines'] = to_num(d['Machines']).fillna(0)
    d['Active'] = d['Active'].astype(str).str.strip().str.upper().replace({'': 'Y', 'NAN': 'Y'})
    for c in ('Unit', 'Process'):
        d[c] = d[c].astype(str).str.strip()
    return d[d['Process'] != ''].copy()


def safe_div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        out = np.where(b > 0, a / b, np.nan)
    return out


# ---------------------------------------------------------------- filters
def apply_filters(df, unit=None, date=None, d0=None, d1=None, styles=None, wash_types=None):
    d = df
    if unit is not None:
        d = d[d['Unit'] == unit]
    if date is not None:
        d = d[d['Date'] == pd.Timestamp(date)]
    if d0 is not None:
        d = d[d['Date'] >= pd.Timestamp(d0)]
    if d1 is not None:
        d = d[d['Date'] <= pd.Timestamp(d1)]
    if styles:
        d = d[d['Style'].isin(styles)]
    if wash_types and 'Wash_Type' in d.columns:
        d = d[d['Wash_Type'].isin(wash_types)]
    return d


def opening_wip(wip, unit, date, stage):
    w = wip[(wip['Unit'] == unit) & (wip['Date'] == pd.Timestamp(date)) & (wip['Stage'].str.upper() == stage.upper())]
    return float(w['Opening_WIP'].sum())


def unit_plan_per_hr(mm, unit, basis=1.0):
    m = mm[(mm['Unit'] == unit) & (mm['Active'] != 'N')]
    return float(m['Plan_per_hr'].sum() * basis)


# ---------------------------------------------------------------- wash hourly
def hourly_table(day_df, num_cols, plan_hr, until, opening, day_start=8, with_plan=True):
    """24-row hourly table. Hours after `until` get NaN actuals so charts show gaps, not zeros."""
    idx = pd.Index(HOURS, name='Hour_Idx')
    g = day_df.groupby('Hour_Idx')[num_cols].sum().reindex(idx).fillna(0.0)
    h = g.copy()
    h['Hour'] = hour_labels(day_start)
    h['Shift'] = [shift_of(i) for i in HOURS]
    active = np.asarray(h.index <= until)
    for c in num_cols:
        h.loc[~active, c] = np.nan
    plan = float(plan_hr) if with_plan else np.nan
    h['Plan'] = plan
    h['Cum_Plan'] = h['Plan'].cumsum()
    h['Cum_Output'] = h['Output'].cumsum()
    h['Closing_WIP'] = opening + h['Input'].cumsum() - h['Output'].cumsum()
    h['Var'] = h['Output'] - h['Plan'].where(active)
    h['Achv'] = np.where(active, safe_div(h['Output'], h['Plan']), np.nan)
    if 'QC_Inspected' in h:
        h['Defect_Pct'] = np.where(active, safe_div(h['Defect'], h['QC_Inspected']), np.nan)
        h['Rewash_Pct'] = np.where(active, safe_div(h['Rewash'], h['Output']), np.nan)
    else:
        h['Defect_Pct'] = np.where(active, safe_div(h['Defect'], h['Output']), np.nan)
        h['Rework_Pct'] = np.where(active, safe_div(h['Rework'], h['Output']), np.nan)
    return h.reset_index()


def wash_kpis(h, until):
    a = h[h['Hour_Idx'] <= until]
    plan = a['Plan'].sum(min_count=1)
    out = a['Output'].sum()
    insp = a['QC_Inspected'].sum()
    k = dict(plan=plan, output=out, input=a['Input'].sum(), inspected=insp, defect=a['Defect'].sum(),
             rewash=a['Rewash'].sum(), downtime_min=a['Downtime_Min'].sum(),
             wip=a['Closing_WIP'].iloc[-1] if len(a) else np.nan)
    k['achv'] = out / plan if plan and plan > 0 else np.nan
    k['defect_pct'] = k['defect'] / insp if insp > 0 else np.nan
    k['rewash_pct'] = k['rewash'] / out if out > 0 else np.nan
    k['var'] = out - plan if plan and plan > 0 else np.nan
    return k


# ---------------------------------------------------------------- machine-wise
def machine_table(day_df, mm, unit, until, basis=1.0, with_plan=True):
    m = mm[mm['Unit'] == unit].copy()
    m['Plan_hr'] = np.where(m['Active'] == 'N', 0.0, m['Plan_per_hr'] * basis)
    d = day_df[day_df['Hour_Idx'] <= until]
    g = d.groupby('Machine_ID').agg(Output=('Output', 'sum'), Input=('Input', 'sum'), QC_Inspected=('QC_Inspected', 'sum'),
                                    Defect=('Defect', 'sum'), Rewash=('Rewash', 'sum'), Downtime_Min=('Downtime_Min', 'sum'),
                                    Hours_Logged=('Hour_Idx', 'nunique')).reset_index()
    t = m.merge(g, on='Machine_ID', how='left')
    for c in ['Output', 'Input', 'QC_Inspected', 'Defect', 'Rewash', 'Downtime_Min', 'Hours_Logged']:
        t[c] = t[c].fillna(0)
    t['Plan'] = t['Plan_hr'] * until if with_plan else np.nan
    t['Var'] = t['Output'] - t['Plan']
    t['Achv'] = safe_div(t['Output'], t['Plan'])
    t['Defect_Pct'] = safe_div(t['Defect'], t['QC_Inspected'])
    t['Rewash_Pct'] = safe_div(t['Rewash'], t['Output'])
    t['Status'] = status_series(t['Achv'], t['Hours_Logged'], None)
    return t


def status_series(achv, logged, st):
    tgt, alr = (st or {}).get('Target_Pct', 0.95), (st or {}).get('Alert_Pct', 0.80)
    out = np.where(np.asarray(logged) == 0, 'No data',
          np.where(pd.isna(achv), '-',
          np.where(achv >= tgt, 'On target', np.where(achv >= alr, 'Watch', 'Behind'))))
    return out


def machine_heatmap(day_df, mm, unit, until, basis=1.0):
    m = mm[(mm['Unit'] == unit) & (mm['Active'] != 'N')].set_index('Machine_ID')['Plan_per_hr'] * basis
    d = day_df[day_df['Hour_Idx'] <= until]
    p = d.pivot_table(index='Machine_ID', columns='Hour_Idx', values='Output', aggfunc='sum')
    p = p.reindex(index=m.index, columns=[h for h in HOURS if h <= until])
    return p.div(m.replace(0, np.nan), axis=0)


# ---------------------------------------------------------------- dry
def dry_table(day_df, mp, wip, unit, date, until, run_hours=24.0, basis=1.0, with_plan=True):
    p = mp[(mp['Unit'] == unit) & (mp['Active'] != 'N')].copy()
    p['Plan_hr'] = p['Capacity_per_day'] / run_hours * basis
    d = day_df[day_df['Hour_Idx'] <= until]
    g = d.groupby('Process').agg(Output=('Output', 'sum'), Input=('Input', 'sum'), Defect=('Defect', 'sum'),
                                 Rework=('Rework', 'sum'), Downtime_Min=('Downtime_Min', 'sum'),
                                 Hours_Logged=('Hour_Idx', 'nunique')).reset_index()
    t = p.merge(g, on='Process', how='left')
    for c in ['Output', 'Input', 'Defect', 'Rework', 'Downtime_Min', 'Hours_Logged']:
        t[c] = t[c].fillna(0)
    t['Plan'] = t['Plan_hr'] * until if with_plan else np.nan
    t['Var'] = t['Output'] - t['Plan']
    t['Achv'] = safe_div(t['Output'], t['Plan'])
    t['Defect_Pct'] = safe_div(t['Defect'], t['Output'])
    t['Rework_Pct'] = safe_div(t['Rework'], t['Output'])
    t['Opening_WIP'] = [opening_wip(wip, unit, date, s) for s in t['Process']]
    t['WIP'] = t['Opening_WIP'] + t['Input'] - t['Output']
    t['Loss_Pcs'] = (t['Plan'] - t['Output']).clip(lower=0)
    t['Status'] = status_series(t['Achv'], t['Hours_Logged'], None)
    return t


def dry_heatmap(day_df, mp, unit, until, run_hours=24.0, basis=1.0):
    p = mp[(mp['Unit'] == unit) & (mp['Active'] != 'N')].set_index('Process')['Capacity_per_day'] / run_hours * basis
    d = day_df[day_df['Hour_Idx'] <= until]
    pv = d.pivot_table(index='Process', columns='Hour_Idx', values='Output', aggfunc='sum')
    pv = pv.reindex(index=p.index, columns=[h for h in HOURS if h <= until])
    return pv.div(p.replace(0, np.nan), axis=0)


def critical_process(dt):
    c = dt[(dt['Hours_Logged'] > 0) & dt['Achv'].notna()]
    return None if c.empty else c.sort_values('Achv').iloc[0]


# ---------------------------------------------------------------- trends / styles / quality
def wash_daily(w, mm, unit, d0, d1, basis=1.0):
    d = apply_filters(w, unit=unit, d0=d0, d1=d1)
    if d.empty:
        return pd.DataFrame(columns=['Date', 'Output', 'Input', 'QC_Inspected', 'Defect', 'Rewash', 'Downtime_Min', 'Max_Hour',
                                     'Plan', 'Achv', 'Defect_Pct', 'Rewash_Pct'])
    g = d.groupby('Date').agg(Output=('Output', 'sum'), Input=('Input', 'sum'), QC_Inspected=('QC_Inspected', 'sum'),
                              Defect=('Defect', 'sum'), Rewash=('Rewash', 'sum'), Downtime_Min=('Downtime_Min', 'sum'),
                              Max_Hour=('Hour_Idx', 'max')).reset_index()
    g['Plan'] = unit_plan_per_hr(mm, unit, basis) * g['Max_Hour']
    g['Achv'] = safe_div(g['Output'], g['Plan'])
    g['Defect_Pct'] = safe_div(g['Defect'], g['QC_Inspected'])
    g['Rewash_Pct'] = safe_div(g['Rewash'], g['Output'])
    return g


def dry_daily(dd, mp, unit, d0, d1, run_hours=24.0, basis=1.0):
    d = apply_filters(dd, unit=unit, d0=d0, d1=d1)
    if d.empty:
        return pd.DataFrame(columns=['Date', 'Process', 'Output', 'Plan', 'Achv'])
    p = mp[(mp['Unit'] == unit) & (mp['Active'] != 'N')].set_index('Process')['Capacity_per_day'] / run_hours * basis
    mh = d.groupby('Date')['Hour_Idx'].max().rename('Max_Hour')
    g = d.groupby(['Date', 'Process']).agg(Output=('Output', 'sum'), Defect=('Defect', 'sum'), Rework=('Rework', 'sum')).reset_index()
    g = g.merge(mh, on='Date')
    g['Plan'] = g['Process'].map(p).fillna(0) * g['Max_Hour']
    g['Achv'] = safe_div(g['Output'], g['Plan'])
    return g


def monthly(daily):
    if daily.empty:
        return daily
    d = daily.copy()
    d['Month'] = d['Date'].dt.to_period('M').astype(str)
    g = d.groupby('Month').agg(Days=('Date', 'nunique'), Output=('Output', 'sum'), Plan=('Plan', 'sum'), Input=('Input', 'sum'),
                               QC_Inspected=('QC_Inspected', 'sum'), Defect=('Defect', 'sum'), Rewash=('Rewash', 'sum'),
                               Downtime_Min=('Downtime_Min', 'sum')).reset_index()
    g['Achv'] = safe_div(g['Output'], g['Plan'])
    g['Defect_Pct'] = safe_div(g['Defect'], g['QC_Inspected'])
    g['Rewash_Pct'] = safe_div(g['Rewash'], g['Output'])
    return g


def style_summary(w, dd):
    if w.empty:
        ws = pd.DataFrame(columns=['Style', 'Output', 'Input', 'Defect_Pct', 'Rewash_Pct', 'Machines', 'Days', 'Downtime_Min'])
    else:
        ws = w.groupby('Style').agg(Output=('Output', 'sum'), Input=('Input', 'sum'), QC_Inspected=('QC_Inspected', 'sum'),
                                    Defect=('Defect', 'sum'), Rewash=('Rewash', 'sum'), Downtime_Min=('Downtime_Min', 'sum'),
                                    Machines=('Machine_ID', 'nunique'), Days=('Date', 'nunique')).reset_index()
        ws['Defect_Pct'] = safe_div(ws['Defect'], ws['QC_Inspected'])
        ws['Rewash_Pct'] = safe_div(ws['Rewash'], ws['Output'])
    if dd.empty:
        ds = pd.DataFrame(columns=['Style', 'Dry_Output', 'Dry_Defect_Pct', 'Dry_Rework_Pct'])
    else:
        ds = dd.groupby('Style').agg(Dry_Output=('Output', 'sum'), Dry_Defect=('Defect', 'sum'), Dry_Rework=('Rework', 'sum')).reset_index()
        ds['Dry_Defect_Pct'] = safe_div(ds['Dry_Defect'], ds['Dry_Output'])
        ds['Dry_Rework_Pct'] = safe_div(ds['Dry_Rework'], ds['Dry_Output'])
    out = ws.merge(ds, on='Style', how='outer')
    return out.sort_values('Output', ascending=False, na_position='last').reset_index(drop=True)


def pareto(df, reason_col='Downtime_Reason', val='Downtime_Min'):
    d = df[(df[val] > 0)]
    if d.empty:
        return pd.DataFrame(columns=['Reason', 'Minutes', 'Share', 'Cum_Share'])
    g = d.assign(Reason=d[reason_col].replace('', '(no reason)')).groupby('Reason')[val].sum().sort_values(ascending=False).reset_index()
    g.columns = ['Reason', 'Minutes']
    g['Share'] = g['Minutes'] / g['Minutes'].sum()
    g['Cum_Share'] = g['Share'].cumsum()
    return g


# ---------------------------------------------------------------- data health
def health_checks(w_day, dd_day, mm, mp, unit, until, basis=1.0, rejected_w=None, rejected_d=None, run_hours=24.0):
    out = {}
    m = mm[(mm['Unit'] == unit) & (mm['Active'] != 'N')]
    exp_w = len(m) * until
    out['wash_coverage'] = (w_day[w_day['Hour_Idx'] <= until][['Machine_ID', 'Hour_Idx']].drop_duplicates().shape[0] / exp_w) if exp_w else np.nan
    p = mp[(mp['Unit'] == unit) & (mp['Active'] != 'N')]
    exp_d = len(p) * until
    out['dry_coverage'] = (dd_day[dd_day['Hour_Idx'] <= until][['Process', 'Hour_Idx']].drop_duplicates().shape[0] / exp_d) if exp_d else np.nan
    out['dup_wash'] = w_day[w_day.duplicated(['Date', 'Hour_Idx', 'Machine_ID'], keep=False)].sort_values(['Machine_ID', 'Hour_Idx'])
    out['dup_dry'] = dd_day[dd_day.duplicated(['Date', 'Hour_Idx', 'Process'], keep=False)].sort_values(['Process', 'Hour_Idx'])
    ph = m.set_index('Machine_ID')['Plan_per_hr'] * basis
    sus = w_day.copy()
    sus['Plan_hr'] = sus['Machine_ID'].map(ph)
    flag = (sus['Output'] > 1.5 * sus['Plan_hr'].fillna(np.inf)) | (sus['Defect'] > sus['QC_Inspected']) | (sus['Rewash'] > sus['Output'])
    flag |= sus['Plan_hr'].isna()
    sus['Why'] = np.where(sus['Plan_hr'].isna(), 'Machine not in master / inactive',
                  np.where(sus['Output'] > 1.5 * sus['Plan_hr'].fillna(np.inf), 'Output > 150% of plan',
                  np.where(sus['Defect'] > sus['QC_Inspected'], 'Defect > inspected', 'Rewash > output')))
    out['suspicious_wash'] = sus[flag][['Hour', 'Machine_ID', 'Style', 'Input', 'Output', 'QC_Inspected', 'Defect', 'Rewash', 'Why']]
    pp = p.set_index('Process')['Capacity_per_day'] / run_hours
    sd = dd_day.copy()
    sd['Plan_hr'] = sd['Process'].map(pp)
    fd = sd['Plan_hr'].isna() | (sd['Output'] > 1.5 * sd['Plan_hr'].fillna(np.inf)) | (sd['Defect'] > sd['Output'])
    sd['Why'] = np.where(sd['Plan_hr'].isna(), 'Process not in master', np.where(sd['Defect'] > sd['Output'], 'Defect > output', 'Output > 150% of plan'))
    out['suspicious_dry'] = sd[fd][['Hour', 'Process', 'Style', 'Input', 'Output', 'Defect', 'Rework', 'Why']]
    hrs = set(w_day['Hour_Idx'])
    out['missing_hours'] = [h for h in range(1, until + 1) if h not in hrs]
    out['rejected_wash'] = rejected_w if rejected_w is not None else pd.DataFrame()
    out['rejected_dry'] = rejected_d if rejected_d is not None else pd.DataFrame()
    return out


# ---------------------------------------------------------------- order master and style details
def prep_order(df):
    d = _ensure(df, ORDER_COLS)
    d = d[~d['Remarks'].astype(str).str.upper().str.startswith('EXAMPLE')].copy()
    for c in ['Wash_Plant', 'Buyer', 'Style', 'PO', 'Color', 'Wash_Type', 'Sewing_Unit', 'Merchant']:
        d[c] = d[c].fillna('').astype(str).str.strip().replace({'nan': '', 'None': ''})
    d = d[d['Style'] != ''].copy()
    d.loc[d['PO'] == '', 'PO'] = NO_PO
    d.loc[d['Color'] == '', 'Color'] = NO_COLOR
    for c in ['CRD', 'Updated_CRD', 'Plan_Start', 'Plan_End', 'Shade_Submit_Date', 'Shade_Approval_Date']:
        d[c] = parse_date(d[c])
    d['Order_Qty'] = to_num(d['Order_Qty'])
    d['CRD_Revisions'] = to_num(d['CRD_Revisions'])
    return d.drop_duplicates(['Wash_Plant'] + KEYS).reset_index(drop=True)


def _mach_text(s, unit, maxn=6):
    ids = sorted({str(x).replace(unit + '-', '', 1) for x in s if str(x)})
    return ', '.join(ids) if len(ids) <= maxn else ', '.join(ids[:maxn]) + f' ... ({len(ids)} machines)'


# (internal name, display label) in the exact order requested
DETAIL_COLS = [
    ('Wash_Plant', 'Wash plant'), ('Buyer', 'Buyer'), ('Style', 'Style'), ('PO', 'PO'), ('Color', 'Color'), ('Wash_Type', 'Wash Type'),
    ('CRD', 'CRD'), ('CRD_Revisions', 'CRD Revision count'), ('Updated_CRD', 'Updated CRD'), ('Machines', 'Machine IDs (Used for that style)'),
    ('Sewing_Unit', 'Sewing Unit'), ('Input_Plan', 'Wash Input Plan till today'), ('Input', 'Actual Input'), ('Input_Var', 'Variation'),
    ('Output_Plan', 'Wash Output Plan till today'), ('Output', 'Actual Output'), ('Output_Var', 'Variation'), ('Achv_Pct', 'Achievement (%)'),
    ('WIP', 'WIP'), ('Rewash', 'Rewash Input'), ('Rewash_Output', 'Rewash Output'), ('Rewash_WIP', 'Rewash WIP'), ('Total_WIP', 'Total WIP'),
    ('Rewash_Pct', 'Rewash (%) till today'), ('Defect', 'Quality Issue (Pcs)'), ('DHU', 'DHU (%)'), ('Reject', 'Rejection (Pcs)'),
    ('Reject_Pct', 'Rejection (%)'), ('Hold_First', '1st cycle Holding time (days)'), ('First_In_Date', '1st input date'),
    ('First_Out_Date', '1st Output date'), ('Hold_Last', 'last cycle holding time'), ('Last_In_Date', 'last input date'),
    ('Last_Out_Date', 'last output date'), ('Shade_Approval_Date', 'Shade Approval date'), ('Approval_Days', 'Approval time (days)'),
    ('Merchant', 'Responsible Merchant Name')]
DETAIL_DATES = ['CRD', 'Updated_CRD', 'First_In_Date', 'First_Out_Date', 'Last_In_Date', 'Last_Out_Date', 'Shade_Approval_Date']


def style_details(w, order, unit, asof, until, day_start=8.0, lag_days=2.0, plan=None):
    """One row per Style/PO/Color for a wash unit, cumulative till (asof date, until hour)."""
    asof = pd.Timestamp(asof).normalize()
    d = w[(w['Unit'] == unit) & ((w['Date'] < asof) | ((w['Date'] == asof) & (w['Hour_Idx'] <= until)))].copy()
    sums = ['Input', 'Output', 'QC_Inspected', 'Defect', 'Rewash', 'Rewash_Output', 'Reject']
    if len(d):
        d['DT'] = d['Date'] + pd.to_timedelta(float(day_start) + d['Hour_Idx'] - 1, unit='h')
        gb = d.groupby(KEYS)
        lg = gb[sums].sum()
        lg['Log_Wash_Type'] = gb['Wash_Type'].agg(lambda s: s[s != ''].mode().iat[0] if (s != '').any() else '')
        lg['Machines'] = gb['Machine_ID'].agg(lambda s: _mach_text(s, unit))
        lg['Machines_Full'] = gb['Machine_ID'].agg(lambda s: ', '.join(sorted({str(x) for x in s if str(x)})))
        fi = d[d['Input'] > 0].groupby(KEYS).agg(First_In=('DT', 'min'), Last_In=('DT', 'max'), First_In_Date=('Date', 'min'), Last_In_Date=('Date', 'max'))
        fo = d[d['Output'] > 0].groupby(KEYS).agg(First_Out=('DT', 'min'), Last_Out=('DT', 'max'), First_Out_Date=('Date', 'min'), Last_Out_Date=('Date', 'max'))
        logged = lg.join(fi).join(fo).reset_index()
    else:
        logged = pd.DataFrame(columns=KEYS + sums + ['Log_Wash_Type', 'Machines', 'Machines_Full', 'First_In', 'Last_In', 'First_Out', 'Last_Out',
                                                    'First_In_Date', 'Last_In_Date', 'First_Out_Date', 'Last_Out_Date'])
    om = order[(order['Wash_Plant'] == unit) | (order['Wash_Plant'] == '')] if len(order) else pd.DataFrame(columns=ORDER_COLS)
    t = om.merge(logged, on=KEYS, how='outer')
    t['Wash_Plant'] = unit
    for c in ['CRD', 'Updated_CRD', 'Plan_Start', 'Plan_End', 'Shade_Submit_Date', 'Shade_Approval_Date']:
        t[c] = pd.to_datetime(t[c], errors='coerce')
    for c in ['Order_Qty', 'CRD_Revisions']:
        t[c] = pd.to_numeric(t[c], errors='coerce')
    for c in sums:
        t[c] = pd.to_numeric(t[c], errors='coerce').fillna(0)
    for c in ['Buyer', 'Sewing_Unit', 'Merchant', 'Machines', 'Machines_Full', 'Wash_Type', 'Log_Wash_Type']:
        t[c] = t[c].fillna('').astype(str).replace({'nan': ''})
    t['Wash_Type'] = t['Wash_Type'].where(t['Wash_Type'] != '', t['Log_Wash_Type'])
    for c in ['First_In', 'Last_In', 'First_Out', 'Last_Out', 'First_In_Date', 'Last_In_Date', 'First_Out_Date', 'Last_Out_Date']:
        t[c] = pd.to_datetime(t[c], errors='coerce')
    dp = order_daily_plan(order, plan, unit, lag_days)
    cp = cum_plan_at(dp, asof, until)
    t = t.merge(cp, on=KEYS, how='left')
    t['Plan_Source'] = t['Plan_Source'].fillna('')
    t['Input_Var'] = t['Input'] - t['Input_Plan']
    t['Output_Var'] = t['Output'] - t['Output_Plan']
    t['Achv_Pct'] = safe_div(t['Output'], t['Output_Plan']) * 100
    t['WIP'] = t['Input'] - t['Output']
    t['Rewash_WIP'] = t['Rewash'] - t['Rewash_Output']
    t['Total_WIP'] = t['WIP'] + t['Rewash_WIP']
    t['Rewash_Pct'] = safe_div(t['Rewash'], t['Output']) * 100
    t['DHU'] = safe_div(t['Defect'], t['QC_Inspected']) * 100
    t['Reject_Pct'] = safe_div(t['Reject'], t['Input']) * 100
    day = pd.Timedelta(days=1)
    t['Hold_First'] = (t['First_Out'] - t['First_In']) / day
    t['Hold_Last'] = (t['Last_Out'] - t['Last_In']) / day
    start = t['Shade_Submit_Date'].where(t['Shade_Submit_Date'].notna(), t['First_Out_Date'])
    t['Approval_Days'] = (t['Shade_Approval_Date'] - start) / day
    t = t.sort_values(['Output', 'Input'], ascending=False).reset_index(drop=True)
    return t[[c for c, _ in DETAIL_COLS] + ['Machines_Full', 'Plan_Source']]


# ---------------------------------------------------------------- daily plan and daily ledger
def prep_plan(df):
    d = _ensure(df, PLAN_COLS)
    for c in ['Wash_Plant', 'Style', 'PO', 'Color']:
        d[c] = d[c].fillna('').astype(str).str.strip().replace({'nan': '', 'None': ''})
    d = d[d['Style'] != ''].copy()
    d.loc[d['PO'] == '', 'PO'] = NO_PO
    d.loc[d['Color'] == '', 'Color'] = NO_COLOR
    d['Date'] = parse_date(d['Date'])
    d['Plan_Input'] = to_num(d['Plan_Input']).fillna(0)
    d['Plan_Output'] = to_num(d['Plan_Output']).fillna(0)
    return d[d['Date'].notna()].reset_index(drop=True)


def order_daily_plan(order, plan, unit, lag_days=2.0):
    """Daily plan per Style/PO/Color. Real Daily_Plan rows win; otherwise Order_Qty is spread evenly over
    Plan_Start..Plan_End (input) and the same window shifted by lag_days (output)."""
    rows = []
    om = order[(order['Wash_Plant'] == unit) | (order['Wash_Plant'] == '')] if order is not None and len(order) else pd.DataFrame(columns=ORDER_COLS)
    pl = plan[(plan['Wash_Plant'] == unit) | (plan['Wash_Plant'] == '')] if plan is not None and len(plan) else pd.DataFrame(columns=PLAN_COLS)
    have = set(map(tuple, pl[KEYS].drop_duplicates().values)) if len(pl) else set()
    for r in om.itertuples():
        key = (r.Style, r.PO, r.Color)
        if key in have:
            continue
        if pd.isna(r.Order_Qty) or pd.isna(r.Plan_Start) or pd.isna(r.Plan_End) or r.Plan_End < r.Plan_Start:
            continue
        days = pd.date_range(r.Plan_Start, r.Plan_End, freq='D')
        per = r.Order_Qty / len(days)
        rows.append(pd.DataFrame({'Style': key[0], 'PO': key[1], 'Color': key[2], 'Date': days, 'Plan_Input': per, 'Plan_Output': 0.0}))
        rows.append(pd.DataFrame({'Style': key[0], 'PO': key[1], 'Color': key[2], 'Date': days + pd.Timedelta(days=int(round(lag_days))),
                                  'Plan_Input': 0.0, 'Plan_Output': per}))
    cols = KEYS + ['Date', 'Plan_Input', 'Plan_Output']
    sl = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)
    sl['Plan_Source'] = 'Straight-line from Order_Qty'
    dr = pl[cols].copy() if len(pl) else pd.DataFrame(columns=cols)
    dr['Plan_Source'] = 'Daily_Plan tab'
    out = pd.concat([sl, dr], ignore_index=True)
    if out.empty:
        return out
    out['Date'] = pd.to_datetime(out['Date'])
    return out.groupby(KEYS + ['Date', 'Plan_Source'], as_index=False)[['Plan_Input', 'Plan_Output']].sum()


def cum_plan_at(dp, asof, until):
    """Cumulative plan per order till (asof date, until hour): full earlier days + until/24 of the as-of day."""
    if dp is None or dp.empty:
        return pd.DataFrame(columns=KEYS + ['Input_Plan', 'Output_Plan', 'Plan_Source'])
    asof = pd.Timestamp(asof).normalize()
    d = dp[dp['Date'] <= asof].copy()
    w = np.where(d['Date'] == asof, until / 24.0, 1.0)
    d['Input_Plan'] = d['Plan_Input'] * w
    d['Output_Plan'] = d['Plan_Output'] * w
    return d.groupby(KEYS).agg(Input_Plan=('Input_Plan', 'sum'), Output_Plan=('Output_Plan', 'sum'), Plan_Source=('Plan_Source', 'first')).reset_index()


LEDGER_NUM = ['Input', 'Output', 'QC_Inspected', 'Defect', 'Rewash', 'Rewash_Output', 'Reject']


def style_ledger(w, dp, unit, keys, asof, until):
    """Day-by-day tracking for Style/PO/Color keys up to (asof, until).
    Opening WIP of a day = previous day's closing WIP, so it carries across months."""
    asof = pd.Timestamp(asof).normalize()
    kdf = pd.DataFrame(list(keys), columns=KEYS)
    d = w[(w['Unit'] == unit) & ((w['Date'] < asof) | ((w['Date'] == asof) & (w['Hour_Idx'] <= until)))]
    d = d.merge(kdf, on=KEYS)
    act = d.groupby('Date')[LEDGER_NUM].sum() if len(d) else pd.DataFrame(columns=LEDGER_NUM, dtype=float)
    p = dp.merge(kdf, on=KEYS) if dp is not None and len(dp) else pd.DataFrame(columns=['Date', 'Plan_Input', 'Plan_Output'])
    p = p[p['Date'] <= asof]
    pl = p.groupby('Date')[['Plan_Input', 'Plan_Output']].sum() if len(p) else pd.DataFrame(columns=['Plan_Input', 'Plan_Output'], dtype=float)
    if len(pl) and asof in pl.index:
        pl.loc[asof] = pl.loc[asof] * (until / 24.0)
    if act.empty and pl.empty:
        return pd.DataFrame()
    start = min(x for x in [act.index.min() if len(act) else None, pl.index.min() if len(pl) else None] if x is not None)
    L = pd.DataFrame(index=pd.date_range(start, asof, freq='D')).join(act).join(pl)
    for c in LEDGER_NUM + ['Plan_Input', 'Plan_Output']:
        L[c] = pd.to_numeric(L[c], errors='coerce').fillna(0.0)
    L['Closing_WIP'] = (L['Input'] - L['Output']).cumsum()
    L['Opening_WIP'] = L['Closing_WIP'].shift(1).fillna(0.0)
    L['Available_Input'] = L['Opening_WIP'] + L['Input']
    L['Input_Var'] = L['Input'] - L['Plan_Input']
    L['Output_Var'] = L['Output'] - L['Plan_Output']
    L['Cum_Input_Plan'] = L['Plan_Input'].cumsum(); L['Cum_Input'] = L['Input'].cumsum()
    L['Cum_Output_Plan'] = L['Plan_Output'].cumsum(); L['Cum_Output'] = L['Output'].cumsum()
    L['Cum_Input_Var'] = L['Cum_Input'] - L['Cum_Input_Plan']
    L['Cum_Output_Var'] = L['Cum_Output'] - L['Cum_Output_Plan']
    L['Achv_Pct'] = safe_div(L['Output'], L['Plan_Output']) * 100
    L['Cum_Achv_Pct'] = safe_div(L['Cum_Output'], L['Cum_Output_Plan']) * 100
    L['Rewash_WIP'] = (L['Rewash'] - L['Rewash_Output']).cumsum()
    L['Total_WIP'] = L['Closing_WIP'] + L['Rewash_WIP']
    L['Month'] = L.index.strftime('%Y-%m')
    ev = pd.Series('', index=L.index, dtype=object)
    def mark(mask, text):
        if mask.any():
            i = mask.idxmax()
            ev.loc[i] = (ev.loc[i] + ', ' if ev.loc[i] else '') + text
    mark(L['Input'] > 0, '1st input'); mark(L['Output'] > 0, '1st output')
    mark((L['Input'] > 0)[::-1], 'last input'); mark((L['Output'] > 0)[::-1], 'last output')
    for i in L.index[L['Month'] != L['Month'].shift(1)]:
        if i != L.index[0]:
            ev.loc[i] = (ev.loc[i] + ', ' if ev.loc[i] else '') + f"month opening carry-forward {L.loc[i, 'Opening_WIP']:,.0f}"
    L['Event'] = ev
    L.index.name = 'Date'
    return L.reset_index()


def ledger_months(L):
    if L is None or L.empty:
        return pd.DataFrame()
    g = L.groupby('Month').agg(Days=('Date', 'nunique'), Opening_WIP=('Opening_WIP', 'first'), Plan_Input=('Plan_Input', 'sum'), Input=('Input', 'sum'),
                               Plan_Output=('Plan_Output', 'sum'), Output=('Output', 'sum'), Closing_WIP=('Closing_WIP', 'last'),
                               Rewash=('Rewash', 'sum'), Rewash_Output=('Rewash_Output', 'sum'), Reject=('Reject', 'sum')).reset_index()
    g['Input_Var'] = g['Input'] - g['Plan_Input']
    g['Output_Var'] = g['Output'] - g['Plan_Output']
    g['Achv_Pct'] = safe_div(g['Output'], g['Plan_Output']) * 100
    return g
