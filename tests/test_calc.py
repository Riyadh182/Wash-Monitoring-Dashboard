"""Calculation-layer tests on the 10-plant demo data. Run: python tests/test_calc.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import pandas as pd, numpy as np
import calc, reports

D = pathlib.Path(__file__).parent.parent / 'demo_data'


def rd(n):
    p = D / f'{n}.csv.gz'
    p = p if p.exists() else D / f'{n}.csv'
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def test_all():
    st = calc.parse_settings(rd('Settings'))
    w, rw = calc.prep_wash(rd('Wash_Log'), st['Day_Start_Hour']); d, rd_ = calc.prep_dry(rd('Dry_Log'), st['Day_Start_Hour'])
    wip, mm, mp = calc.prep_wip(rd('WIP_Log')), calc.prep_machine(rd('Master_Machine')), calc.prep_process(rd('Master_Process'))
    um, alloc = calc.prep_unit_master(rd('Unit_Master')), calc.prep_alloc(rd('Allotment'))
    order, plan = calc.prep_order(rd('Order_Master')), calc.prep_plan(rd('Daily_Plan'))
    units = list(um['Wash_Plant'])
    assert len(units) == 10 and rw.empty and rd_.empty and w['Unit'].nunique() == 10
    assert w['Date'].nunique() == 30 and len(mm) == 581, (w['Date'].nunique(), len(mm))
    # ---- plant hourly (CWL-1) ties to capacity file
    unit, day = 'CWL-1', w['Date'].max()
    plan_hr = calc.unit_plan_per_hr(mm, unit)
    assert abs(plan_hr * 24 - 40864) < 1
    wd = calc.apply_filters(w, unit=unit, date=day)
    h = calc.hourly_table(wd, calc.WASH_NUM, plan_hr, 16, calc.opening_wip(wip, unit, day, 'WASH'))
    k = calc.wash_kpis(h, 16)
    assert abs(k['output'] - wd[wd.Hour_Idx <= 16]['Output'].sum()) < 1e-6 and abs(k['plan'] - plan_hr * 16) < 1e-6
    mt = calc.machine_table(wd, mm, unit, 16)
    assert abs(mt['Output'].sum() - k['output']) < 1e-6
    dd = calc.apply_filters(d, unit=unit, date=day)
    dt = calc.dry_table(dd, mp, wip, unit, day, 16)
    assert len(dt) == 15
    # ---- capacity file ties
    caps = calc.unit_capacity(um, mm, mp, units)
    c1 = caps[caps.Wash_Plant == 'CWL-1'].iloc[0]
    assert abs(c1['Wet_Capacity_Day'] - 40864) < 1 and c1['Dry_Capacity_Day'] == 16000
    assert caps['Wet_Capacity_Day'].notna().all()
    # ---- order-level status for all plants
    S = calc.all_status(w, order, plan, units, day, 24, st['Day_Start_Hour'], st['Output_Lag_Days'])
    assert [c for c, _ in calc.DETAIL_COLS] == list(S.columns[:37]) and set(S['Wash_Plant']) == set(units)
    # no pcs lost or double counted between logs and order table (priors added on top)
    for u in ('CWL-1', 'NWL'):
        su = S[S.Wash_Plant == u]
        logged = w[(w.Unit == u) & (w.Date <= day)]
        assert abs(su['Input'].sum() - su['Prior_Input'].sum() - logged['Input'].sum()) < 1e-3
        assert abs(su['Output'].sum() - su['Prior_Output'].sum() - logged['Output'].sum()) < 1e-3
    assert abs(S['Total_WIP'] - (S['WIP'] + S['Rewash_WIP'])).max() < 1e-6
    assert (S['Balance'] >= 0).all() and S['Eff_CRD'].notna().all()
    # ---- group summaries
    for by in (['Wash_Plant'], ['Sewing_Unit'], ['Buyer'], ['Sewing_Unit', 'Wash_Plant']):
        g = calc.group_summary(S, by)
        assert abs(g['Output'].sum() - S['Output'].sum()) < 1e-6 and abs(g['Total_WIP'].sum() - S['Total_WIP'].sum()) < 1e-6 and g['Orders'].sum() == len(S)
    cs = calc.crd_summary(S, day, 'week'); assert abs(cs['Order_Qty'].sum() - S['Order_Qty'].sum()) < 1e-6
    # ---- crisis
    C = calc.crisis_table(S, 7)
    assert len(C) > 0 and (C['Balance'] > 0).all() and (C['Days_to_CRD'] <= 7).all() and set(C['Risk']) <= {'Overdue', 'Critical', 'Watch'}
    assert len(calc.crisis_table(S, 21)) >= len(C) and len(calc.crisis_table(S, 0)) <= len(C)
    assert S[(S.Balance > 0) & (S.Days_to_CRD <= 7)].shape[0] == len(C)
    # ---- plant daily / WIP comparison
    pdl = calc.all_plant_daily(w, wip, units, day - pd.Timedelta(days=5), day)
    assert len(pdl) == 60
    wc = calc.wip_compare(pdl, day)
    assert len(wc) == 10 and np.allclose(wc['WIP_Today'] - wc['WIP_Yesterday'], wc['Change'])
    pdc = pdl[pdl.Wash_Plant == 'CWL-1'].reset_index(drop=True)
    assert np.allclose(pdc['Closing_WIP'], pdc['Opening_WIP'] + pdc['Input'] - pdc['Output'])
    # ---- capacity justification
    cap_hr = mm[(mm.Unit == unit) & (mm.Active != 'N')].set_index('Machine_ID')['Plan_per_hr'].astype(float)
    t = calc.resource_daily(w, alloc, cap_hr, unit, 'Machine_ID', day - pd.Timedelta(days=6), day, day, 24)
    assert len(t) == 7 * len(cap_hr) and (t['Allotted'] <= t['Capacity'] + 1e-6).all()
    assert abs(t['Capacity'].sum() - cap_hr.sum() * 24 * 7) < 1e-3
    assert abs(t['Output'].sum() - w[(w.Unit == unit) & (w.Date > day - pd.Timedelta(days=7))]['Output'].sum()) < 1e-3
    r = calc.cap_rollup(t, ['Month', 'Machine_ID'])
    assert abs(r['Output'].sum() - t['Output'].sum()) < 1e-6 and r['Util_Pct'].between(0, 200).all()
    t2 = calc.resource_daily(w, alloc, cap_hr, unit, 'Machine_ID', day, day, day, 10)     # partial day: capacity counts only 10 h
    assert abs(t2['Capacity'].sum() - cap_hr.sum() * 10) < 1e-3
    pr = (mp[(mp.Unit == unit)].set_index('Process')['Capacity_per_day'] / 24).astype(float)
    tp = calc.resource_daily(d, alloc, pr, unit, 'Process', day - pd.Timedelta(days=2), day, day, 24)
    assert len(tp) == 3 * len(pr)
    assert isinstance(calc.top_reasons(w, unit, 'Machine_ID', day - pd.Timedelta(days=6), day, day, 24), pd.DataFrame)
    # ---- reports
    R = reports.report_set(S, pdl, day, 7, day - pd.Timedelta(days=5), day)
    assert len(R) >= 10 and all(isinstance(v, pd.DataFrame) for v in R.values())
    b = reports.excel_bytes(R)
    assert b[:2] == b'PK' and len(b) > 5000
    # ---- robustness
    raw = pd.DataFrame([
        [46301, '08:00-09:00', 'CWL-1', 'CWL-1-FL-01', 'Denim', 'S1', '100', '90', '80', '2', '1', '', '', ''],
        ['2026-10-06', '9:00-10:00', '', 'CWL-1-FL-02', 'Denim', '', '10', '12', '', '', '', '', '', ''],
        ['2026-10-06', '10:00-11:00', 'CWL-1', 'CWL-1-FL-03', '', '', '', '', '', '', '', '', '', ''],
        ['2026-10-06', 'xx', 'CWL-1', 'CWL-1-FL-04', '', '', '5', '5', '', '', '', '', '', ''],
        ['2026-10-06', '08:00-09:00', 'CWL-1', 'CWL-1-FL-05', '', '', '5', '5', '', '', '', '', '', 'EXAMPLE row']],
        columns=['Date', 'Hour', 'Unit', 'Machine_ID', 'Wash_Type', 'Style', 'Input', 'Output', 'QC_Inspected', 'Defect', 'Rewash', 'Downtime_Min', 'Downtime_Reason', 'Remarks'])
    c, rj = calc.prep_wash(raw, 8)
    assert len(c) == 2 and len(rj) == 1 and c['Hour_Idx'].tolist() == [1, 2] and c['Date'].iloc[0] == pd.Timestamp('2026-10-06')
    # empty frames everywhere
    e = calc.prep_order(pd.DataFrame())
    S0 = calc.all_status(w, e, calc.prep_plan(pd.DataFrame()), ['CWL-1'], day, 24)
    assert calc.group_summary(S0, ['Buyer']) is not None and calc.crisis_table(S0, 7) is not None
    print('ALL OK')


if __name__ == '__main__':
    test_all()
