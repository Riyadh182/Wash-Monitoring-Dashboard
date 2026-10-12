"""Data loading. Live: one or many Google Sheets (public link, or optional service account). Demo: bundled gz/CSV files.

Secrets (Streamlit):
[sheets]
current = ["ID_PLANT_1", "ID_PLANT_2", ...]          # one Sheet per wash plant for the current month (or one Sheet for all)
archive = ["2026-09:ID", "2026-09:ID2", ...]         # past months; "YYYY-MM:ID" entries are only read when History is switched on
refresh_seconds = 180                                # optional cache time
Plan_Board / Plan_History / Audit_Log / Stage_Log / Master_Stage are the plan-execution tabs (see README).
"""
import concurrent.futures as cf
import pathlib
import pandas as pd
import streamlit as st
import calc
import board

DEMO_DIR = pathlib.Path(__file__).parent / 'demo_data'
LOGS = {'wash': 'Wash_Log', 'dry': 'Dry_Log', 'wip': 'WIP_Log'}
MASTERS = {'machine': 'Master_Machine', 'process': 'Master_Process', 'settings': 'Settings'}
OPTIONAL = {'cycle': 'Cycle_Log', 'order': 'Order_Master', 'plan': 'Daily_Plan', 'unit': 'Unit_Master', 'alloc': 'Allotment', 'mstage': 'Master_Stage'}
BOARD = {'board': 'Plan_Board', 'hist': 'Plan_History', 'audit': 'Audit_Log', 'stage': 'Stage_Log'}
HOURLY_ARCHIVE = {**LOGS, 'alloc': 'Allotment', 'cycle': 'Cycle_Log'}
BOARD_HEADER_ROWS = 6          # rows 1-6 of Plan_Board are header rows (title, month, dates, codes, day label, column label)
RAW_KEYS = list(LOGS) + list(MASTERS) + list(OPTIONAL) + list(BOARD)


def _secret(key, default=None):
    try:
        return st.secrets['sheets'].get(key, default)
    except Exception:
        return default


def secrets_ready():
    try:
        return 'sheets' in st.secrets and len(_ids('current')) > 0
    except Exception:
        return False


def _ids(key):
    v = _secret(key, [])
    return [v] if isinstance(v, str) else list(v)


def refresh_seconds():
    try:
        return int(_secret('refresh_seconds', 180))
    except Exception:
        return 180


def _use_service_account():
    try:
        return 'gcp_service_account' in st.secrets
    except Exception:
        return False


def _read_public(sid, title, raw=False):
    from urllib.parse import quote
    url = f'https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&sheet={quote(title)}'
    if raw:
        url += f'&headers={BOARD_HEADER_ROWS}'
    df = pd.read_csv(url, dtype=str, keep_default_na=False)
    if not raw:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def _make_reader():
    if _use_service_account():
        import gspread
        gc = gspread.service_account_from_dict(dict(st.secrets['gcp_service_account']))
        cache = {}

        def rd(sid, title, raw=False):
            sh = cache.setdefault(sid, gc.open_by_key(sid))
            vals = sh.worksheet(title).get_all_values(value_render_option='UNFORMATTED_VALUE', date_time_render_option='SERIAL_NUMBER')
            if not vals:
                return pd.DataFrame()
            if raw:
                return pd.DataFrame(vals)
            return pd.DataFrame(vals[1:], columns=[str(h).strip() for h in vals[0]])
        return rd
    return _read_public


def _split_archive(entries):
    out = []
    for e in entries:
        if ':' in str(e):
            m, sid = str(e).split(':', 1)
            out.append((m.strip(), sid.strip()))
        else:
            out.append(('', str(e).strip()))
    return out


def archive_months():
    """Months that have archive sheets listed in Secrets (sorted, newest last)."""
    return sorted({m for m, _ in _split_archive(_ids('archive')) if m})


def _read_jobs(jobs):
    rd = _make_reader()

    def run(j):
        k, sid, t, optional = j
        try:
            return k, rd(sid, t, raw=(k == 'board'))
        except Exception:
            if optional:
                return k, None
            raise
    raw = {k: [] for k in RAW_KEYS}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for k, df in ex.map(run, jobs):
            if df is not None and len(df.columns):
                raw[k].append(df)
    return raw


@st.cache_data(ttl=86400, show_spinner='Loading history...', max_entries=6)
def _read_archive(sids, hourly):
    """Closed months never change, so they are cached for a day. Only the plan-board tabs unless hourly history is asked for."""
    jobs = []
    for sid in sids:
        for k, t in BOARD.items():
            jobs.append((k, sid, t, True))
        if hourly:
            for k, t in HOURLY_ARCHIVE.items():
                jobs.append((k, sid, t, k == 'alloc'))
    return _read_jobs(jobs)


def _from_sheets(include_archive, months, hourly):
    cur = _ids('current')
    jobs = []
    for sid in cur:
        for k, t in {**LOGS, 'alloc': 'Allotment'}.items():
            jobs.append((k, sid, t, True))
        for k, t in MASTERS.items():
            jobs.append((k, sid, t, True))
        for k, t in {**{o: n for o, n in OPTIONAL.items() if o != 'alloc'}, **BOARD}.items():
            jobs.append((k, sid, t, True))
    raw = _read_jobs(jobs)
    if include_archive:
        arc = [sid for m, sid in _split_archive(_ids('archive')) if (not months) or m in months or not m]
        if arc:
            extra = _read_archive(tuple(arc), bool(hourly))
            for k, v in extra.items():
                raw[k] = raw[k] + v
    return raw


def _from_demo():
    out = {}
    for k, t in {**LOGS, **MASTERS, **OPTIONAL, **BOARD}.items():
        p = DEMO_DIR / f'{t}.csv.gz'
        if not p.exists():
            p = DEMO_DIR / f'{t}.csv'
        if not p.exists():
            out[k] = [] if k == 'board' else pd.DataFrame()
        elif k == 'board':
            out[k] = [pd.read_csv(p, dtype=str, keep_default_na=False, header=None)]
        else:
            out[k] = pd.read_csv(p, dtype=str, keep_default_na=False)
    return out


def _cat(v):
    if isinstance(v, list):
        return pd.concat(v, ignore_index=True) if v else pd.DataFrame()
    return v


BUILD = 'planboard-2026-10-12'


@st.cache_data(ttl=refresh_seconds(), show_spinner='Loading data...', max_entries=3)
def load_all(use_demo=False, include_archive=False, months=(), hourly_history=False):
    error, demo = None, True
    if use_demo or not secrets_ready():
        raw = _from_demo()
    else:
        try:
            raw, demo = _from_sheets(include_archive, tuple(months), hourly_history), False
            if not any(len(_cat(raw[k])) for k in ('wash', 'machine', 'board', 'cycle')):
                raise ValueError('no tab could be read (check Sheet IDs, sharing = Anyone with the link, tab names)')
        except Exception as e:
            raw, error = _from_demo(), f'{type(e).__name__}: {str(e)[:200]}'
    board_parts = [board.parse_board(g) for g in (raw.get('board') or [])]
    bo, bd = board.merge_boards(board_parts)
    cat = {k: _cat(v) for k, v in raw.items() if k != 'board'}
    settings = calc.parse_settings(cat['settings'])
    ds = settings['Day_Start_Hour']
    machine = calc.prep_machine(cat['machine'])
    cyc_rows = calc.cycles_to_wash(cat.get('cycle'), cat.get('order'), machine, ds)       # one row per load -> hourly input / output / recipe time
    wash, rej_w = calc.prep_wash(pd.concat([cat['wash'], cyc_rows], ignore_index=True) if len(cyc_rows) else cat['wash'], ds)
    dry, rej_d = calc.prep_dry(cat['dry'], ds)
    process = calc.prep_process(cat['process'])
    unit_m = calc.prep_unit_master(cat.get('unit', pd.DataFrame()))
    units = sorted(set(machine['Unit']) | set(wash['Unit']) | set(process['Unit']) | set(unit_m['Wash_Plant']) | set(bo['Wash_Plant']), key=lambda x: (len(x) > 0, x))
    units = [u for u in units if u and u != 'nan']
    order_units = list(unit_m['Wash_Plant']) if len(unit_m) else units
    return dict(settings=settings, wash=wash, dry=dry, wip=calc.prep_wip(cat['wip']), machine=machine, process=process,
                order=calc.prep_order(cat.get('order', pd.DataFrame())), plan=calc.prep_plan(cat.get('plan', pd.DataFrame())),
                unit_master=unit_m, alloc=calc.prep_alloc(cat.get('alloc', pd.DataFrame())), units=_order_units(units, order_units),
                board_orders=bo, board_daily=bd, hist=board.prep_hist(cat.get('hist')), audit=board.prep_audit(cat.get('audit')),
                stage=board.prep_stage_log(cat.get('stage')), mstage=board.prep_master_stage(cat.get('mstage')),
                rej_w=rej_w, rej_d=rej_d, demo=demo, error=error,
                version=f'{len(wash)}-{len(dry)}-{wash["Date"].max()}-{wash["Output"].sum():.0f}-{wash["Input"].sum():.0f}-{len(bo)}-{bd["SEW_ACT"].sum():.0f}-{bd["WASH_ACT"].sum():.0f}-{len(cat.get("audit", []))}-{len(cyc_rows)}')


def _order_units(units, preferred):
    first = [u for u in preferred if u in units]
    return first + [u for u in units if u not in first]
