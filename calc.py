"""Pure-pandas calculation layer (no Streamlit imports) so it can be unit-tested."""
import re
import numpy as np
import pandas as pd

WASH_NUM = ['Input', 'Output', 'QC_Inspected', 'Defect', 'Rewash', 'Downtime_Min']
DRY_NUM = ['Input', 'Output', 'Defect', 'Rework', 'Downtime_Min']
WASH_COLS = ['Date', 'Hour', 'Unit', 'Machine_ID', 'Wash_Type', 'Style', 'Input', 'Output', 'QC_Inspected',
             'Defect', 'Rewash', 'Downtime_Min', 'Downtime_Reason', 'Remarks']
DRY_COLS = ['Date', 'Hour', 'Unit', 'Process', 'Style', 'Input', 'Output', 'Defect', 'Rework',
            'Downtime_Min', 'Downtime_Reason', 'Remarks']
WIP_COLS = ['Date', 'Unit', 'Stage', 'Opening_WIP', 'Remarks']
MACHINE_COLS = ['Unit', 'Machine_ID', 'Type', 'Plan_per_hr', 'Active']
PROCESS_COLS = ['Unit', 'Process', 'Machines', 'Capacity_per_day', 'Active']
HOURS = list(range(1, 25))
NO_STYLE = '(no style)'

DEFAULT_SETTINGS = dict(Run_Hours=24.0, Day_Start_Hour=8.0, Plan_Basis=1.0, Target_Pct=0.95,
                        Alert_Pct=0.80, Max_Defect_Pct=0.03, Max_Rewash_Pct=0.02)
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
    for c in ('Unit', key_col, 'Style', 'Downtime_Reason'):
        d[c] = d[c].fillna('').astype(str).str.strip()
    if 'Machine_ID' == key_col:
        blank = d['Unit'] == ''
        d.loc[blank, 'Unit'] = d.loc[blank, 'Machine_ID'].str.rsplit('-', n=2).str[0]
    d.loc[d['Style'].isin(['', 'nan', 'None']), 'Style'] = NO_STYLE
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
