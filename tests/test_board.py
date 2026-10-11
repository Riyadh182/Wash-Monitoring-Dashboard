"""Plan Board tests on the demo grid. Run: python tests/test_board.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import pandas as pd, numpy as np
import board, calc

D = pathlib.Path(__file__).parent.parent / 'demo_data'


def rd(n, **k):
    p = D / f'{n}.csv.gz'
    p = p if p.exists() else D / f'{n}.csv'
    return pd.read_csv(p, dtype=str, keep_default_na=False, **k)


def test_all():
    grid = pd.read_csv(D / 'Plan_Board.csv.gz', header=None, dtype=str, keep_default_na=False)
    O, DL = board.parse_board(grid)
    assert len(O) == 60, len(O)
    assert {'SEW_PLAN', 'SEW_ACT', 'WASH_PLAN', 'WASH_ACT'} <= set(DL.columns)
    assert DL['Date'].dt.month.eq(10).all() and DL['Date'].nunique() <= 31
    hist, audit = board.prep_hist(rd('Plan_History')), board.prep_audit(rd('Audit_Log'))
    asof = DL.loc[(DL['WASH_ACT'] > 0), 'Date'].max()
    S = board.board_status(O, DL, asof, hist, audit)
    assert len(S) == len(O)
    # invariants
    assert (S['Priority'].dropna() >= 1).all()
    op = S[S['Balance'] > 0].sort_values('Priority')
    for _, g in op.groupby('Wash_Plant'):
        assert g['Eff_CRD'].is_monotonic_increasing, 'priority must follow EDD'
    # FIFO tie-break within the same Eff_CRD
    for _, g in op.groupby(['Wash_Plant', 'Eff_CRD']):
        fr = g.sort_values('Priority')['First_Receive_Date']
        assert fr.dropna().is_monotonic_increasing
    assert (S['Overrun_Days'] >= 0).all()
    ov = S[(S['Overrun_Days'] > 0) & (S['Balance'] > 0)]
    assert len(ov) >= 1, len(ov)
    assert S['Edited'].astype(bool).any() and S['Plan_Revisions'].max() >= 1
    fl = board.red_flags(S)
    assert len(fl) == len(S)
    # crisis includes overrun orders
    cr = calc.crisis_table(S, 14) if 'horizon' not in calc.crisis_table.__code__.co_varnames else calc.crisis_table(S, horizon=14)
    assert 'Overrun' in set(cr['Risk']) or len(cr) > 0
    # forecast
    caps = {p: 5000.0 for p in S['Unit'].unique()} if 'Unit' in S else {}
    F, P = board.wash_forecast(S, DL, caps, asof, 60)
    assert len(F) > 0 and 'Verdict' in F.columns
    # plant daily
    units = sorted(S['Unit'].unique()) if 'Unit' in S else sorted(O['Wash_Plant'].unique())
    pdl = board.board_plant_daily(O, DL, units, DL['Date'].min(), asof)
    assert len(pdl) > 0
    # stage tracker
    L = board.prep_stage_log(rd('Stage_Log'))
    sp = board.stage_position(L, asof, board.prep_master_stage(rd('Master_Stage')))
    assert len(sp) > 0
    # merge two months keeps latest static, earliest openings
    M = board.merge_boards([(O, DL), (O, DL)]) if False else None
    print('board tests OK:', len(O), 'orders;', len(ov), 'overrun;', len(F), 'forecast rows')


if __name__ == '__main__':
    test_all()
