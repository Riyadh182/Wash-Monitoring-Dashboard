"""Smoke-runs app.py with a stubbed streamlit (streamlit may not be installable offline). Catches NameErrors, pandas bugs, empty-data crashes.
Real rendering must still be checked in a real Streamlit run."""
import sys, types, runpy, pathlib, datetime as dt, traceback
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
try:
    import plotly  # noqa
    REAL_PLOTLY = True
except Exception:
    REAL_PLOTLY = False


class Dummy:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return Dummy()
    def __call__(self, *a, **k): return Dummy()
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter([])


class Stop(Exception): pass
MEMO = {}


def build(cfg):
    st = types.ModuleType('streamlit')
    log = {'errors': [], 'tables': [], 'downloads': 0, 'charts': 0}
    st.__getattr__ = lambda n: Dummy()
    st.session_state = {}
    pick = lambda label, key: cfg.get(key, cfg.get(label))
    st.set_page_config = lambda **k: None
    st.error = lambda *a, **k: log['errors'].append(a)
    st.stop = lambda: (_ for _ in ()).throw(Stop())
    st.rerun = lambda: None
    st.sidebar = Dummy()
    st.checkbox = lambda label, value=False, **k: cfg.get(label, value)
    st.selectbox = lambda label, options, **k: (lambda o: pick(label, k.get('key')) if pick(label, k.get('key')) in o else (o[0] if o else None))(list(options))
    st.date_input = lambda label, value=None, **k: pick(label, k.get('key')) or value
    st.select_slider = lambda label, options=None, value=None, **k: cfg.get('until', value)
    st.slider = lambda label, a=0, b=0, v=None, **k: cfg.get('horizon', (v if v is not None else k.get('value', a)))
    st.text_input = lambda label, **k: cfg.get('style', '')
    st.multiselect = lambda label, options=(), default=None, **k: (lambda o: [x for x in (pick(label, k.get('key')) if pick(label, k.get('key')) is not None else (default or [])) if x in o or True])(list(options))
    st.button = lambda *a, **k: cfg.get('button:' + str(k.get('key')), False)
    st.radio = lambda label, options, **k: (lambda v: v if v in options else options[0])(pick(label, k.get('key')))
    st.expander = lambda *a, **k: Dummy()
    st.spinner = lambda *a, **k: Dummy()
    st.download_button = lambda *a, **k: log.__setitem__('downloads', log['downloads'] + 1)
    class Col:
        def __getattr__(self, n): return getattr(st, n)
        def __enter__(self): return self
        def __exit__(self, *a): return False
    st.columns = lambda n, **k: [Col() for _ in range(n if isinstance(n, int) else len(n))]
    st.plotly_chart = lambda *a, **k: log.__setitem__('charts', log['charts'] + 1)
    st.dataframe = lambda df, **k: log['tables'].append(len(df))
    def cache_data(*a, **k):
        def deco(f):
            def w(*args, **kw):
                key = (f.__qualname__, tuple(repr(x) for i, x in enumerate(args) if not (f.__code__.co_varnames[i].startswith('_'))), tuple(sorted(kw.items(), key=str)).__repr__())
                if key not in MEMO: MEMO[key] = f(*args, **kw)
                return MEMO[key]
            return w
        return deco(a[0]) if a and callable(a[0]) else deco
    cache_data.clear = lambda: None
    st.cache_data = cache_data
    cc = Dummy()
    st.column_config = cc
    st.secrets = {}
    return st, log


def run(cfg):
    st, log = build(cfg)
    mods = {'streamlit': st}
    if not REAL_PLOTLY:
        go = types.ModuleType('plotly.graph_objects')
        for n in ['Figure', 'Bar', 'Scatter', 'Heatmap', 'Pie']: setattr(go, n, Dummy)
        sub = types.ModuleType('plotly.subplots'); sub.make_subplots = lambda *a, **k: Dummy()
        pl = types.ModuleType('plotly'); pl.graph_objects = go; pl.subplots = sub
        mods.update({'plotly': pl, 'plotly.graph_objects': go, 'plotly.subplots': sub})
    for k in list(sys.modules):
        if k in ('app', 'data', 'calc', 'ui', 'views_plant', 'views_portfolio', 'reports'): del sys.modules[k]
    sys.modules.update(mods)
    try:
        runpy.run_path(str(ROOT / 'app.py'), run_name='__main__')
    except Stop:
        pass
    return log


NAV = ['🌐 Overview', '⏱ Hourly Monitor', '🏭 Machines', '🔥 Dry Process', '⚖️ Capacity', '🚨 CRD Crisis', '🧪 Quality & Downtime', '👗 Style Explorer', '📈 Trends', '📑 Reports', '🩺 Data Health']
cases = {}
for v in NAV:
    cases[v] = {'nav': v}
    cases[v + ' | early hour/plant NWL'] = {'nav': v, 'until': 6, 'Wash plant (for plant views)': 'NWL'}
    cases[v + ' | empty date'] = {'nav': v, 'Date': dt.date(2026, 10, 20)}
cases.update({
    'style search': {'nav': '⏱ Hourly Monitor', 'style': 'ST-'},
    'style no match': {'nav': '⏱ Hourly Monitor', 'style': 'zzz'},
    'style details': {'nav': '👗 Style Explorer', 'style_view': 'Style details'},
    'style details SWDL': {'nav': '👗 Style Explorer', 'style_view': 'Style details', 'Wash plant (for plant views)': 'SWDL'},
    'capacity process': {'nav': '⚖️ Capacity', 'cap_kind': 'Process-wise'},
    'capacity month': {'nav': '⚖️ Capacity', 'cap_per': 'Month-wise'},
    'capacity process month': {'nav': '⚖️ Capacity', 'cap_kind': 'Process-wise', 'cap_per': 'Month-wise'},
    'overview plant': {'nav': '🌐 Overview', 'ov_view': 'Wash plant'},
    'overview sewing': {'nav': '🌐 Overview', 'ov_view': 'Sewing unit'},
    'overview buyer': {'nav': '🌐 Overview', 'ov_view': 'Buyer'},
    'overview crd': {'nav': '🌐 Overview', 'ov_view': 'CRD'},
    'overview orders': {'nav': '🌐 Overview', 'ov_view': 'Orders'},
    'overview crd next7': {'nav': '🌐 Overview', 'ov_crd': 'Next 7 days'},
    'overview plant filter': {'nav': '🌐 Overview', 'ov_pl': ['CWL-1', 'CWL-2']},
    'crisis horizon 3': {'nav': '🚨 CRD Crisis', 'horizon': 3},
    'reports pack': {'nav': '📑 Reports', 'button:rp_build': True},
})

if __name__ == '__main__':
    bad = 0
    for name, cfg in cases.items():
        try:
            log = run(cfg)
            flag = ''
            if log['errors']:
                flag = ' ERRORS ' + str(log['errors'])[:80]; bad += 1
            print(f"ok  {name:58s} tables={len(log['tables']):2d} charts={log['charts']:2d} dl={log['downloads']:2d}{flag}")
        except Exception:
            bad += 1
            print('FAIL', name); traceback.print_exc(limit=-4)
    print('FAILED' if bad else 'ALL OK', bad)
    sys.exit(1 if bad else 0)
