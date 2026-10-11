"""Data loading. Live: one or many Google Sheets (public link, or optional service account). Demo: bundled gz/CSV files.

Secrets (Streamlit):
[sheets]
current = ["ID_PLANT_1", "ID_PLANT_2", ...]          # one Sheet per wash plant for the current month (or one Sheet for all)
archive = ["2026-09:ID", "2026-09:ID2", ...]         # past months; "YYYY-MM:ID" entries are only read when History is switched on
refresh_seconds = 180                                # optional cache time
"""
import concurrent.futures as cf
import pathlib
import pandas as pd
import streamlit as st
import calc

DEMO_DIR = pathlib.Path(__file__).parent / 'demo_data'
LOGS = {'wash': 'Wash_Log', 'dry': 'Dry_Log', 'wip': 'WIP_Log'}
MASTERS = {'machine': 'Master_Machine', 'process': 'Master_Process', 'settings': 'Settings'}
OPTIONAL = {'order': 'Order_Master', 'plan': 'Daily_Plan', 'unit': 'Unit_Master', 'alloc': 'Allotment'}
ARCHIVE_TABS = {**LOGS, 'alloc': 'Allotment'}


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


def _read_public(sid, title):
    from urllib.parse import quote
    url = f'https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&sheet={quote(title)}'
    df = pd.read_csv(url, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _make_reader():
    if _use_service_account():
        import gspread
        gc = gspread.service_account_from_dict(dict(st.secrets['gcp_service_account']))
        cache = {}

        def rd(sid, title):
            sh = cache.setdefault(sid, gc.open_by_key(sid))
            vals = sh.worksheet(title).get_all_values(value_render_option='UNFORMATTED_VALUE', date_time_render_option='SERIAL_NUMBER')
            if not vals:
                return pd.DataFrame()
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


def _from_sheets(include_archive):
    rd = _make_reader()
    cur = _ids('current')
    arc = [sid for _, sid in _split_archive(_ids('archive'))] if include_archive else []
    jobs = []
    for sid in cur + arc:
        for k, t in {**LOGS, 'alloc': 'Allotment'}.items():
            jobs.append((k, sid, t, k == 'alloc'))
    for sid in cur:
        for k, t in {**MASTERS, **{o: n for o, n in OPTIONAL.items() if o != 'alloc'}}.items():
            jobs.append((k, sid, t, k in OPTIONAL))

    def run(j):
        k, sid, t, optional = j
        try:
            return k, rd(sid, t)
        except Exception:
            if optional:
                return k, None
            raise
    raw = {k: [] for k in list(LOGS) + list(MASTERS) + list(OPTIONAL)}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for k, df in ex.map(run, jobs):
            if df is not None and len(df.columns):
                raw[k].append(df)
    return {k: (pd.concat(v, ignore_index=True) if v else pd.DataFrame()) for k, v in raw.items()}


def _from_demo():
    out = {}
    for k, t in {**LOGS, **MASTERS, **OPTIONAL}.items():
        p = DEMO_DIR / f'{t}.csv.gz'
        if not p.exists():
            p = DEMO_DIR / f'{t}.csv'
        out[k] = pd.read_csv(p, dtype=str, keep_default_na=False) if p.exists() else pd.DataFrame()
    return out


@st.cache_data(ttl=refresh_seconds(), show_spinner='Loading data...', max_entries=2)
def load_all(use_demo=False, include_archive=False):
    error, demo = None, True
    if use_demo or not secrets_ready():
        raw = _from_demo()
    else:
        try:
            raw, demo = _from_sheets(include_archive), False
        except Exception as e:
            raw, error = _from_demo(), f'{type(e).__name__}: {str(e)[:200]}'
    settings = calc.parse_settings(raw['settings'])
    ds = settings['Day_Start_Hour']
    wash, rej_w = calc.prep_wash(raw['wash'], ds)
    dry, rej_d = calc.prep_dry(raw['dry'], ds)
    machine, process = calc.prep_machine(raw['machine']), calc.prep_process(raw['process'])
    unit_m = calc.prep_unit_master(raw.get('unit', pd.DataFrame()))
    units = sorted(set(machine['Unit']) | set(wash['Unit']) | set(process['Unit']) | set(unit_m['Wash_Plant']), key=lambda x: (len(x) > 0, x))
    units = [u for u in units if u and u != 'nan']
    order_units = list(unit_m['Wash_Plant']) if len(unit_m) else units
    return dict(settings=settings, wash=wash, dry=dry, wip=calc.prep_wip(raw['wip']), machine=machine, process=process,
                order=calc.prep_order(raw.get('order', pd.DataFrame())), plan=calc.prep_plan(raw.get('plan', pd.DataFrame())),
                unit_master=unit_m, alloc=calc.prep_alloc(raw.get('alloc', pd.DataFrame())), units=_order_units(units, order_units),
                rej_w=rej_w, rej_d=rej_d, demo=demo, error=error, version=f'{len(wash)}-{len(dry)}-{wash["Date"].max()}-{wash["Output"].sum():.0f}-{wash["Input"].sum():.0f}-{len(raw.get("order", []))}')


def _order_units(units, preferred):
    first = [u for u in preferred if u in units]
    return first + [u for u in units if u not in first]
