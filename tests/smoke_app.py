"""Smoke-runs app.py with stubbed streamlit/plotly (neither is installable offline). Catches NameErrors, pandas bugs, empty-data crashes.
Real rendering must be checked in a real Streamlit run."""
import sys, types, runpy, pathlib, datetime as dt
import pandas as pd
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

class Dummy:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return Dummy()
    def __call__(self, *a, **k): return Dummy()
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter([])

class Stop(Exception): pass

def build(cfg):
    st = types.ModuleType('streamlit'); log = {'errors': [], 'markdown': 0, 'tables': []}
    def widget_default(*a, **k): return k.get('value')
    st.set_page_config = lambda **k: None
    st.markdown = lambda *a, **k: log.__setitem__('markdown', log['markdown'] + 1)
    st.caption = st.write = st.info = st.warning = lambda *a, **k: None
    st.error = lambda *a, **k: log['errors'].append(a)
    st.stop = lambda: (_ for _ in ()).throw(Stop())
    st.rerun = lambda: None
    st.sidebar = Dummy()
    st.checkbox = lambda label, value=False, **k: value
    st.selectbox = lambda label, options, **k: cfg.get(label, list(options)[0] if len(list(options)) else None)
    st.date_input = lambda label, value=None, **k: cfg.get(label, value)
    st.select_slider = lambda label, options=None, value=None, **k: cfg.get('until', value)
    st.text_input = lambda label, **k: cfg.get('style', '')
    st.multiselect = lambda label, options, default=None, **k: cfg.get(label, list(default or []))
    st.button = lambda *a, **k: False
    st.radio = lambda label, options, **k: cfg.get('view', options[0])
    st.expander = lambda *a, **k: Dummy()
    st.download_button = lambda *a, **k: False
    st.columns = lambda n, **k: [Dummy() for _ in range(n if isinstance(n, int) else len(n))]
    st.tabs = lambda labels: [Dummy() for _ in labels]
    st.plotly_chart = lambda *a, **k: None
    st.dataframe = lambda df, **k: log['tables'].append(len(df))
    st.cache_data = types.SimpleNamespace(clear=lambda: None)
    def cache_data(*a, **k):
        if a and callable(a[0]): return a[0]
        return lambda f: f
    cache_data.clear = lambda: None
    st.cache_data = cache_data
    st.column_config = types.SimpleNamespace(ProgressColumn=lambda *a, **k: None, NumberColumn=lambda *a, **k: None)
    st.secrets = {}
    return st, log

def run(cfg):
    st, log = build(cfg)
    go = types.ModuleType('plotly.graph_objects')
    for n in ['Figure', 'Bar', 'Scatter', 'Heatmap', 'Pie']: setattr(go, n, Dummy)
    sub = types.ModuleType('plotly.subplots'); sub.make_subplots = lambda *a, **k: Dummy()
    pl = types.ModuleType('plotly'); pl.graph_objects = go; pl.subplots = sub
    for k in list(sys.modules):
        if k in ('app', 'data', 'calc'): del sys.modules[k]
    sys.modules.update({'streamlit': st, 'plotly': pl, 'plotly.graph_objects': go, 'plotly.subplots': sub})
    try:
        runpy.run_path(str(ROOT / 'app.py'), run_name='__main__')
    except Stop:
        pass
    return log

cases = {
 'default': {},
 'early hour': {'until': 6},
 'style search': {'style': 'ST-4412'},
 'style no match': {'style': 'zzz'},
 'wash type': {'Wash type': ['Acid']},
 'empty date (no data)': {'Date': dt.date(2026, 10, 20)},
 'style details': {'view': 'Style details'},
 'style details + search': {'view': 'Style details', 'style': 'ST-4412'},
 'style details no match': {'view': 'Style details', 'style': 'zzz'},
 'style details empty date': {'view': 'Style details', 'Date': dt.date(2026, 9, 1)},
 'ledger default': {'view': 'Style details'},
 'range single day': {'Date range': (dt.date(2026, 10, 6), dt.date(2026, 10, 6)), 'Trend range': (dt.date(2026, 9, 16), dt.date(2026, 9, 20))},
}
for name, cfg in cases.items():
    log = run(cfg)
    assert not log['errors'], log['errors']
    print(f"OK  {name:24s} tables={len(log['tables'])}")
print('SMOKE OK')
