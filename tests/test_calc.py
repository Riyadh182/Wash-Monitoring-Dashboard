import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import pandas as pd, numpy as np
import calc

D = pathlib.Path(__file__).parent.parent / 'demo_data'
def load():
    r = lambda n: pd.read_csv(D / f'{n}.csv', dtype=str, keep_default_na=False)
    st = calc.parse_settings(r('Settings'))
    w, rw = calc.prep_wash(r('Wash_Log'), st['Day_Start_Hour']); d, rd = calc.prep_dry(r('Dry_Log'), st['Day_Start_Hour'])
    return st, w, d, calc.prep_wip(r('WIP_Log')), calc.prep_machine(r('Master_Machine')), calc.prep_process(r('Master_Process')), rw, rd

def test_all():
    st, w, d, wip, mm, mp, rw, rd = load()
    assert len(w) == 26712 and len(d) == 7560 and rw.empty and rd.empty
    assert st['Run_Hours'] == 24 and st['Target_Pct'] == 0.95
    day = pd.Timestamp('2026-10-06'); unit = 'CWL-1'
    plan_hr = calc.unit_plan_per_hr(mm, unit)
    assert abs(plan_hr * 24 - 40864) < 1, plan_hr * 24          # ties to capacity file
    wd = calc.apply_filters(w, unit=unit, date=day)
    h = calc.hourly_table(wd, calc.WASH_NUM, plan_hr, 16, calc.opening_wip(wip, unit, day, 'WASH'))
    assert h['Output'].iloc[:16].notna().all() and h['Output'].iloc[16:].isna().all()
    k = calc.wash_kpis(h, 16)
    assert abs(k['output'] - wd[wd.Hour_Idx <= 16]['Output'].sum()) < 1e-6
    assert abs(k['plan'] - plan_hr * 16) < 1e-6
    print('KPIs', {a: round(b, 3) for a, b in k.items()})
    mt = calc.machine_table(wd, mm, unit, 16)
    assert len(mt) == 53 and abs(mt['Output'].sum() - k['output']) < 1e-6
    hm = calc.machine_heatmap(wd, mm, unit, 16); assert hm.shape == (53, 16)
    dd = calc.apply_filters(d, unit=unit, date=day)
    dt = calc.dry_table(dd, mp, wip, unit, day, 16)
    assert len(dt) == 15; print(dt[['Process', 'Plan', 'Output', 'Achv', 'WIP']].round(2).sort_values('Achv').head(3).to_string())
    cp = calc.critical_process(dt); print('critical', cp['Process'], round(cp['Achv'], 3))
    assert calc.dry_heatmap(dd, mp, unit, 16).shape == (15, 16)
    dly = calc.wash_daily(w, mm, unit, '2026-09-16', '2026-10-06'); assert len(dly) == 21
    mo = calc.monthly(dly); assert list(mo['Month']) == ['2026-09', '2026-10']; print(mo[['Month', 'Days', 'Output', 'Achv', 'Defect_Pct', 'Rewash_Pct']].round(3).to_string())
    ss = calc.style_summary(w, d); print(ss[['Style', 'Output', 'Defect_Pct', 'Rewash_Pct']].round(3).to_string())
    assert not calc.pareto(wd).empty
    hc = calc.health_checks(wd, dd, mm, mp, unit, 16)
    print('coverage', round(hc['wash_coverage'], 3), round(hc['dry_coverage'], 3), len(hc['dup_wash']), len(hc['suspicious_wash']))
    # robustness: sheet-style raw inputs (serial dates, blank skeleton rows, EXAMPLE row, bad hour)
    raw = pd.DataFrame([
        [46301, '08:00-09:00', 'CWL-1', 'CWL-1-FL-01', 'Denim', 'S1', '100', '90', '80', '2', '1', '', '', ''],
        ['2026-10-06', '9:00-10:00', '', 'CWL-1-FL-02', 'Denim', '', '10', '12', '', '', '', '', '', ''],
        ['2026-10-06', '10:00-11:00', 'CWL-1', 'CWL-1-FL-03', '', '', '', '', '', '', '', '', '', ''],
        ['2026-10-06', 'xx', 'CWL-1', 'CWL-1-FL-04', '', '', '5', '5', '', '', '', '', '', ''],
        ['2026-10-06', '08:00-09:00', 'CWL-1', 'CWL-1-FL-05', '', '', '5', '5', '', '', '', '', '', 'EXAMPLE row']],
        columns=['Date', 'Hour', 'Unit', 'Machine_ID', 'Wash_Type', 'Style', 'Input', 'Output', 'QC_Inspected', 'Defect', 'Rewash', 'Downtime_Min', 'Downtime_Reason', 'Remarks'])  # old 14-column sheet still works
    c, rj = calc.prep_wash(raw, 8)
    assert len(c) == 2 and len(rj) == 1, (len(c), len(rj))
    assert c['Unit'].tolist() == ['CWL-1', 'CWL-1'] and c['Hour_Idx'].tolist() == [1, 2] and c['Style'].tolist() == ['S1', '(no style)']
    assert c['Date'].iloc[0] == pd.Timestamp('2026-10-06'), c['Date'].iloc[0]   # serial 46301
    # ---- style details
    st_o = calc.prep_order(pd.read_csv(D / 'Order_Master.csv', dtype=str, keep_default_na=False))
    asof = pd.Timestamp('2026-10-06')
    T = calc.style_details(w, st_o, unit, asof, 24, st['Day_Start_Hour'], st['Output_Lag_Days'])
    assert [c for c, _ in calc.DETAIL_COLS] == list(T.columns[:-2]) and len(calc.DETAIL_COLS) == 37
    assert abs(T['Input'].sum() - w[(w.Unit == unit) & (w.Date <= asof)]['Input'].sum()) < 1e-6      # nothing lost / double counted
    assert abs(T['Output'].sum() - w[(w.Unit == unit) & (w.Date <= asof)]['Output'].sum()) < 1e-6
    r0 = T[T['PO'] == 'PO-77101'].iloc[0]
    assert abs(r0['WIP'] - (r0['Input'] - r0['Output'])) < 1e-9 and abs(r0['Total_WIP'] - (r0['WIP'] + r0['Rewash_WIP'])) < 1e-9
    assert abs(r0['Input_Var'] - (r0['Input'] - r0['Input_Plan'])) < 1e-9
    assert 0.5 < r0['Hold_First'] < 4 and r0['Last_Out_Date'] >= r0['Last_In_Date']
    # as-of earlier day: less input; plan fraction lower
    T2 = calc.style_details(w, st_o, unit, pd.Timestamp('2026-09-25'), 12, st['Day_Start_Hour'], 2)
    assert T2['Input'].sum() < T['Input'].sum() and T2.loc[T2.PO == 'PO-77101', 'Input_Plan'].iloc[0] < r0['Input_Plan']
    # no Order_Master at all -> still works, master columns blank
    T3 = calc.style_details(w, calc.prep_order(pd.DataFrame()), unit, asof, 24)
    assert len(T3) == 14 and T3['Input_Plan'].isna().all() and T3['Buyer'].eq('').all()
    # before anything was logged
    T4 = calc.style_details(w, st_o, unit, pd.Timestamp('2026-09-01'), 24)
    assert (T4['Input'] == 0).all()
    print(T[['Style', 'PO', 'Input_Plan', 'Input', 'Achv_Pct', 'Total_WIP', 'Hold_First', 'Hold_Last']].head(3).round(1).to_string())
    # ---- daily plan / ledger
    pl = calc.prep_plan(pd.read_csv(D / 'Daily_Plan.csv', dtype=str, keep_default_na=False))
    T5 = calc.style_details(w, st_o, unit, asof, 24, st['Day_Start_Hour'], 2, pl)
    assert set(T5['Plan_Source']) >= {'Daily_Plan tab', 'Straight-line from Order_Qty'}
    dp = calc.order_daily_plan(st_o, pl, unit, 2)
    key = ('ST-4412 Dark Stone', 'PO-77101', 'Dark Blue')
    Lg = calc.style_ledger(w, dp, unit, [key], asof, 24)
    assert abs(Lg['Closing_WIP'].iloc[-1] - (Lg['Input'].sum() - Lg['Output'].sum())) < 1e-6
    assert (Lg['Opening_WIP'].iloc[1:].values == Lg['Closing_WIP'].iloc[:-1].values).all()       # carry-forward
    assert (Lg['Available_Input'] == Lg['Opening_WIP'] + Lg['Input']).all()
    r5 = T5[T5.PO == 'PO-77101'].iloc[0]
    assert abs(Lg['Cum_Input_Plan'].iloc[-1] - r5['Input_Plan']) < 1e-6 and abs(Lg['Cum_Output'].iloc[-1] - r5['Output']) < 1e-6
    assert set(calc.ledger_months(Lg)['Month']) == {'2026-09', '2026-10'}
    assert calc.style_ledger(w, dp, unit, [key], pd.Timestamp('2026-09-01'), 24).empty
    print('ALL OK')

if __name__ == '__main__':
    test_all()
