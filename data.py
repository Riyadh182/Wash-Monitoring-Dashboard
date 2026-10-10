"""Data loading: Google Sheets (via service account in st.secrets) or bundled demo CSVs."""
import pathlib
import pandas as pd
import streamlit as st
import calc

DEMO_DIR = pathlib.Path(__file__).parent / 'demo_data'
LOGS = {'wash': 'Wash_Log', 'dry': 'Dry_Log', 'wip': 'WIP_Log'}
MASTERS = {'machine': 'Master_Machine', 'process': 'Master_Process', 'settings': 'Settings'}
OPTIONAL = {'order': 'Order_Master', 'plan': 'Daily_Plan'}   # older Sheets may not have this tab yet


def secrets_ready():
    try:
        return 'sheets' in st.secrets and len(_ids('current')) > 0
    except Exception:
        return False


def _ids(key):
    v = st.secrets['sheets'].get(key, [])
    return [v] if isinstance(v, str) else list(v)


def _read_ws(sh, title):
    ws = sh.worksheet(title)
    try:   # raw numbers + serial dates -> no locale/format ambiguity
        vals = ws.get_all_values(value_render_option='UNFORMATTED_VALUE', date_time_render_option='SERIAL_NUMBER')
    except Exception:
        vals = ws.get_all_values()
    if not vals:
        return pd.DataFrame()
    head = [str(h).strip() for h in vals[0]]
    return pd.DataFrame(vals[1:], columns=head)


def _read_public(sid, title):
    """Reads a tab from a Google Sheet shared as 'Anyone with the link' - no Google Cloud account needed."""
    from urllib.parse import quote
    url = f'https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&sheet={quote(title)}'
    df = pd.read_csv(url, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _use_service_account():
    try:
        return 'gcp_service_account' in st.secrets
    except Exception:
        return False


def _from_sheets():
    cur, arc = _ids('current'), _ids('archive')
    raw = {k: [] for k in list(LOGS) + list(MASTERS)}
    if _use_service_account():             # optional private mode
        import gspread
        gc = gspread.service_account_from_dict(dict(st.secrets['gcp_service_account']))
        reader = lambda sid, t, _c={}: _read_ws(_c.setdefault(sid, gc.open_by_key(sid)), t)
    else:                                  # public link mode (default)
        reader = _read_public
    for sid in cur + arc:
        for k, t in LOGS.items():
            raw[k].append(reader(sid, t))
    for sid in cur:                        # masters/settings only from the CURRENT files
        for k, t in MASTERS.items():
            raw[k].append(reader(sid, t))
        for k, t in OPTIONAL.items():
            try:
                raw.setdefault(k, []).append(reader(sid, t))
            except Exception:
                pass
    return {k: (pd.concat(v, ignore_index=True) if v else pd.DataFrame()) for k, v in raw.items()}


def _from_demo():
    return {k: pd.read_csv(DEMO_DIR / f'{t}.csv', dtype=str, keep_default_na=False)
            for k, t in {**LOGS, **MASTERS, **OPTIONAL}.items()}


@st.cache_data(ttl=60, show_spinner='Loading data...')
def load_all(use_demo=False):
    error, demo = None, True
    if use_demo or not secrets_ready():
        raw = _from_demo()
    else:
        try:
            raw, demo = _from_sheets(), False
        except Exception as e:             # wrong sheet id / not shared / tab name mismatch -> show demo + a clear message
            raw, error = _from_demo(), f'{type(e).__name__}: {str(e)[:200]}'
    settings = calc.parse_settings(raw['settings'])
    ds = settings['Day_Start_Hour']
    wash, rej_w = calc.prep_wash(raw['wash'], ds)
    dry, rej_d = calc.prep_dry(raw['dry'], ds)
    return dict(settings=settings, wash=wash, dry=dry, wip=calc.prep_wip(raw['wip']), order=calc.prep_order(raw.get('order', pd.DataFrame())),
                plan=calc.prep_plan(raw.get('plan', pd.DataFrame())),
                machine=calc.prep_machine(raw['machine']), process=calc.prep_process(raw['process']),
                rej_w=rej_w, rej_d=rej_d, demo=demo, error=error)
