"""Cycle_Log (one row per load) -> hourly rows -> machine recipe time. Run: python tests/test_cycles.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pandas as pd, numpy as np
import calc


def test_all():
    cyc = pd.DataFrame({'Date': ['2026-10-11'] * 4, 'Machine_ID': ['CWL-1-FL-01'] * 3 + ['CWL-1-FL-02'],
                        'Order': ['ST-4412 Dark Stone | PO-1001 | Light Blue'] * 3 + ['ST-3350 Twill | PO-1002 | Khaki'],
                        'Pcs': [400, 420, 410, 300], 'In_Time': ['08:00', '10:30', '23:00', '0.375'], 'Out_Time': ['09:40', '12:05', '01:10', ''],
                        'Defect': ['2', '', '', ''], 'Rewash': ['', '1', '', ''], 'Downtime_Min': [''] * 4, 'Remarks': [''] * 4})
    r = calc.cycles_to_wash(cyc)
    w, rej = calc.prep_wash(r, 8)
    assert len(rej) == 0
    assert w['Input'].sum() == 1530 and w['Output'].sum() == 1230       # open load (300) is input only -> WIP 300
    assert (w.loc[w['Output'] > 0, 'Recipe_Min'].sort_values().tolist() == [95, 100, 130])
    assert set(w['PO']) == {'PO-1001', 'PO-1002'} and set(w['Color']) == {'Light Blue', 'Khaki'}
    # midnight crossing stays on the same production date (day starts 08:00)
    assert w.loc[(w['Machine_ID'] == 'CWL-1-FL-01') & (w['Output'] == 410), 'Date'].iloc[0] == pd.Timestamp('2026-10-11')
    # recipe time per machine
    mm = pd.DataFrame({'Unit': ['CWL-1'] * 2, 'Machine_ID': ['CWL-1-FL-01', 'CWL-1-FL-02'], 'Type': ['F/L'] * 2, 'Plan_per_hr': [30, 30], 'Active': ['Y'] * 2, 'Std_Recipe_Min': [90, 90]})
    mm = calc.prep_machine(mm)
    MT = calc.machine_table(w[w['Date'] == pd.Timestamp('2026-10-11')], mm, 'CWL-1', 24)
    a = MT.set_index('Machine_ID')
    assert abs(a.loc['CWL-1-FL-01', 'Avg_Recipe_Min'] - 108.33) < 0.1 and abs(a.loc['CWL-1-FL-01', 'Recipe_Var_Min'] - 18.33) < 0.1
    assert pd.isna(a.loc['CWL-1-FL-02', 'Avg_Recipe_Min'])
    # empty / junk input never crashes
    assert calc.cycles_to_wash(pd.DataFrame()).empty and calc.cycles_to_wash(None).empty
    junk = pd.DataFrame({'Date': ['x', ''], 'Machine_ID': ['', 'M1'], 'Order': ['', ''], 'Pcs': ['a', '5'], 'In_Time': ['', 'zz'], 'Out_Time': ['', '']})
    calc.prep_wash(calc.cycles_to_wash(junk), 8)
    print('cycle tests OK')


if __name__ == '__main__':
    test_all()


def test_load_all_with_cycles():
    import smoke_app as sa
    st, log = sa.build({})
    sys.modules['streamlit'] = st
    import data
    base = data._from_demo()
    cyc = pd.DataFrame({'Date': ['2026-10-09'] * 2, 'Machine_ID': ['CWL-1-FL-01'] * 2,
                        'Order': ['ST-4501 Light Fade | PO-1013 | Light Blue'] * 2, 'Pcs': [500, 600], 'In_Time': ['08:10', '12:00'], 'Out_Time': ['09:50', ''],
                        'Defect': [''] * 2, 'Rewash': [''] * 2, 'Downtime_Min': [''] * 2, 'Remarks': [''] * 2})
    orig = data._from_demo
    data._from_demo = lambda: {**orig(), 'cycle': cyc}
    D = data.load_all.__wrapped__(True) if hasattr(data.load_all, '__wrapped__') else data.load_all(True)
    data._from_demo = orig
    w0, _ = __import__('calc').prep_wash(base['wash'] if not isinstance(base['wash'], list) else pd.concat(base['wash']), 8)
    assert len(D['wash']) == len(w0) + 3, (len(D['wash']), len(w0))
    assert D['wash'].loc[D['wash']['Recipe_Min'] == 100, 'Output'].sum() >= 500
    print('load_all + Cycle_Log OK')


if __name__ == '__main__':
    test_load_all_with_cycles()
