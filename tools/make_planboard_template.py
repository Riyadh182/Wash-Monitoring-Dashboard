"""Plan Board workbook for one wash plant and one month (28/29/30/31 day blocks).
   python tools/make_planboard_template.py CWL-1 2026-11 out.xlsx
   python tools/make_planboard_template.py --all 2026-11 ../templates   (10 plants)"""
import sys, calendar, datetime, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule, CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter as CL
import board
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import CFG

ROWS = 700
R0 = board.FIRST_DATA_ROW            # 8
R1 = R0 + ROWS - 1
NS, NF = len(board.STATIC), len(board.FORMULA)
D0 = NS + NF + 1                     # first day column (1-based) = 32 (AF)
D1 = D0 + 7 * 31 - 1
IDX = {c: i + 1 for i, (c, _) in enumerate(board.STATIC + board.FORMULA)}
L = lambda code: CL(IDX[code])

NAVY, TEAL, GREY, INP, SEW, WSH = '1E293B', '0D9488', 'E2E8F0', 'FFF9DB', 'DBEAFE', 'DCFCE7'
fill = lambda c: PatternFill('solid', start_color=c, end_color=c)
F = lambda b=False, c='1E293B', s=10: Font(name='Arial', size=s, bold=b, color=c)
thin = Side(style='thin', color='CBD5E1')
box = Border(left=thin, right=thin, top=thin, bottom=thin)


def build(plant, month, out):
    y, m = map(int, month.split('-'))
    nd = calendar.monthrange(y, m)[1]
    wb = Workbook()
    # ------------------------------------------------------------------ README
    r = wb.active; r.title = 'README'; r.sheet_view.showGridLines = False
    r.column_dimensions['A'].width = 3; r.column_dimensions['B'].width = 130
    lines = [(f'PLAN BOARD | {plant} | {month} ({nd} days)', True), ('', False),
             ('1. One row per PO (Style + PO + Color). Fill the yellow cells once: buyer, CRD, order qty, wash plan start / end, opening balances. Rows 1-7 are headers, data starts at row 8.', False),
             ('2. Every day: Sewing planned delivery and Wash planned production come from the planner. Sewing ACTUAL delivery and Wash ACTUAL production are typed by the monitoring team. Variation and totals are formulas.', False),
             ('3. Do NOT change numbers that were already entered. The script logs every change (old value, new value, who, when), the cell turns red and the dashboard shows the order as "edited".', False),
             ('4. Wash plan start / end, CRD and order qty changes are saved as plan history (version 1, 2, 3 ...). Revising the plan is allowed: the history just keeps the proof.', False),
             ('5. Work sequence = earliest delivery date (CRD) first; same CRD -> first received first (FIFO); then PO. Column "Wash Priority" shows it. Filter / sort by that column.', False),
             ('6. After the wash plan end date, if balance or WIP is still open the row is red flagged (Risk = Yes) and the dashboard reports it as crisis / possible crisis.', False),
             ('7. Month length: change cell B2 (first day of the month). Day blocks beyond the month length go blank; run Plan Board > Setup month to hide them. 28, 29, 30 or 31 days work.', False),
             ('8. Next month: Plan Board > Create next month sheet. It copies this file, keeps only open orders, carries the opening balances and clears the days. Then add the old Sheet ID to Secrets "archive" as YYYY-MM:ID and the new ID to "current".', False),
             ('9. Stage_Log (optional): where the pieces are inside the plant (Receive Store, Wash, Dry Process, QC & Packing ...). Date, Wash_Plant, Style, PO, Color, Stage, Pcs_In, Pcs_Out. A scan system export fits this layout.', False),
             ('10. Share the Sheet as "Anyone with the link" if the dashboard reads it without a service account. Floor staff need Editor access.', False),
             ('Rows whose Style starts with EXAMPLE are ignored by the dashboard.', False)]
    for i, (t, b) in enumerate(lines, 2):
        c = r.cell(i, 2, t); c.font = F(b, NAVY, 14 if b else 10); c.alignment = Alignment(wrap_text=True, vertical='top')
    # ------------------------------------------------------------------ Plan_Board
    ws = wb.create_sheet('Plan_Board')
    ws.sheet_view.zoomScale = 90
    ws['A1'] = f'HAMEEM GROUP | E2E Plan Execution (Sewing - Wash) | {plant}'
    ws['A1'].font = F(True, 'FFFFFF', 14); ws['A1'].fill = fill(NAVY); ws['A1'].alignment = Alignment(vertical='center')
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=NS + NF + 14)
    ws.row_dimensions[1].height = 28
    ws['A2'] = 'Month (first day)'; ws['A2'].font = F(True)
    ws['B2'] = datetime.date(y, m, 1); ws['B2'].number_format = 'yyyy-mm-dd'; ws['B2'].fill = fill(INP); ws['B2'].font = F(True, '0000FF')
    ws['D2'] = 'Wash plant'; ws['D2'].font = F(True); ws['E2'] = plant; ws['E2'].font = F(True, '0000FF'); ws['E2'].fill = fill(INP)
    ws['G2'] = 'Days in month'; ws['G2'].font = F(True); ws['H2'] = '=DAY(EOMONTH($B$2,0))'
    ws['J2'] = 'Do not insert rows above row 8 - the dashboard reads rows 1-6 as headers.'; ws['J2'].font = F(False, 'B91C1C', 9)
    # header rows 3-6
    for j, (c, lab) in enumerate(board.STATIC + board.FORMULA, 1):
        ws.cell(4, j, c).font = F(False, '94A3B8', 7)
        h = ws.cell(6, j, lab); h.font = F(True, 'FFFFFF', 9); h.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        h.fill = fill(NAVY if c in ('Wash_Plant', 'Style', 'PO', 'Color') else (TEAL if c in dict(board.STATIC) else '475569'))
        ws.merge_cells(start_row=5, start_column=j, end_row=5, end_column=j) if False else None
        ws.column_dimensions[CL(j)].width = {'Style': 24, 'Buyer': 14, 'Merchant': 16, 'Sewing_Unit': 12}.get(c, 13)
    ws.row_dimensions[6].height = 54
    for n in range(31):
        c0 = D0 + n * 7
        ws.merge_cells(start_row=5, start_column=c0, end_row=5, end_column=c0 + 6)
        dcell = f'{CL(c0)}$3'
        ws.cell(5, c0, f'=IF({dcell}="","","Day {n + 1} | "&TEXT({dcell},"ddd dd-mmm"))')
        ws.cell(5, c0).font = F(True, 'FFFFFF', 10); ws.cell(5, c0).alignment = Alignment(horizontal='center')
        ws.cell(5, c0).fill = fill('0369A1' if n % 2 == 0 else '0F766E')
        for q, (code, lab) in enumerate(board.DAY):
            j = c0 + q
            ws.cell(3, j, f'=IF({n + 1}<=DAY(EOMONTH($B$2,0)),$B$2+{n},"")').number_format = 'yyyy-mm-dd'
            ws.cell(3, j).font = F(False, '94A3B8', 7)
            ws.cell(4, j, code).font = F(False, '94A3B8', 7)
            h = ws.cell(6, j, lab); h.font = F(True, 'FFFFFF', 9); h.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            h.fill = fill('3B82F6' if q < 3 else ('16A34A' if q < 6 else '64748B'))
            ws.column_dimensions[CL(j)].width = 22 if code == 'REMARK' else 11
            if n >= nd:
                ws.column_dimensions[CL(j)].hidden = True
    ws.row_dimensions[3].height = 10; ws.row_dimensions[4].height = 10
    # grand total row 7
    ws.cell(7, 1, 'Grand Total').font = F(True)
    for code in ['Order_Qty', 'Open_Received', 'Open_Washed', 'Open_Sew_Var', 'Open_Wash_Var', 'Wash_Reject', 'Missing_Body', 'Received', 'Washed', 'WIP', 'Balance']:
        c = ws.cell(7, IDX[code], f'=SUM({L(code)}{R0}:{L(code)}{R1})'); c.font = F(True); c.number_format = '#,##0'
    for n in range(31):
        for q, (code, _) in enumerate(board.DAY):
            if code != 'REMARK':
                j = D0 + n * 7 + q
                c = ws.cell(7, j, f'=SUM({CL(j)}{R0}:{CL(j)}{R1})'); c.font = F(True); c.number_format = '#,##0'
    for j in range(1, D1 + 1):
        ws.cell(7, j).fill = fill(GREY)
    # data rows: formulas
    VR = lambda r_: f'${CL(D0)}{r_}:${CL(D1)}{r_}'
    CR = f'${CL(D0)}$4:${CL(D1)}$4'
    DR = f'${CL(D0)}$3:${CL(D1)}$3'
    cL = {c: L(c) for c in IDX}
    for r_ in range(R0, R1 + 1):
        E = f'${cL["PO"]}{r_}'
        g = lambda c: f'{cL[c]}{r_}'
        f = {
            'Eff_CRD': f'=IF({g("Revised_CRD")}<>"",{g("Revised_CRD")},IF({g("CRD")}<>"",{g("CRD")},""))',
            'Received': f'=IF({E}="","",N({g("Open_Received")})+SUMIFS({VR(r_)},{CR},"SEW_ACT"))',
            'Washed': f'=IF({E}="","",N({g("Open_Washed")})+SUMIFS({VR(r_)},{CR},"WASH_ACT"))',
            'WIP': f'=IF({E}="","",{g("Received")}-{g("Washed")}-N({g("Wash_Reject")})-N({g("Missing_Body")}))',
            'Balance': f'=IF({E}="","",IF(N({g("Order_Qty")})-{g("Washed")}<=0.02*N({g("Order_Qty")}),0,N({g("Order_Qty")})-{g("Washed")}))',
            'First_Receive': f'=IF({E}="","",IF({g("First_Received_On")}<>"",{g("First_Received_On")},IF(N({g("Open_Received")})>0,IF({g("Plan_Start")}<>"",{g("Plan_Start")},99999),'
                             f'IFERROR(1/(1/_xlfn.MINIFS({DR},{CR},"SEW_ACT",{VR(r_)},">0")),99999))))',
            'Priority': f'=IF(OR({E}="",{g("Balance")}=0,{g("Eff_CRD")}=""),"",1+COUNTIFS({cL["Balance"]}${R0}:{cL["Balance"]}${R1},">0",{cL["Eff_CRD"]}${R0}:{cL["Eff_CRD"]}${R1},"<"&{g("Eff_CRD")})'
                        f'+COUNTIFS({cL["Balance"]}${R0}:{cL["Balance"]}${R1},">0",{cL["Eff_CRD"]}${R0}:{cL["Eff_CRD"]}${R1},{g("Eff_CRD")},{cL["First_Receive"]}${R0}:{cL["First_Receive"]}${R1},"<"&{g("First_Receive")})'
                        f'+COUNTIFS({cL["Balance"]}${R0}:{cL["Balance"]}${R1},">0",{cL["Eff_CRD"]}${R0}:{cL["Eff_CRD"]}${R1},{g("Eff_CRD")},{cL["First_Receive"]}${R0}:{cL["First_Receive"]}${R1},{g("First_Receive")},'
                        f'{cL["PO"]}${R0}:{cL["PO"]}${R1},"<"&{E}))',
            'Forecast': f'=IF(OR({E}="",{g("Balance")}=0),"",IFERROR(TODAY()+ROUNDUP({g("Balance")}/(SUMIFS({VR(r_)},{CR},"WASH_ACT")/COUNTIFS({CR},"WASH_ACT",{VR(r_)},">0")),0),"no output yet"))',
            'Sew_Delay': f'=IF({E}="","",IFERROR(ROUND(MAX(0,SUMIFS({VR(r_)},{CR},"SEW_PLAN",{DR},"<="&TODAY())-SUMIFS({VR(r_)},{CR},"SEW_ACT",{DR},"<="&TODAY())+N({g("Open_Sew_Var")}))'
                         f'/(SUMIFS({VR(r_)},{CR},"SEW_PLAN")/COUNTIFS({CR},"SEW_PLAN",{VR(r_)},">0")),1),0))',
            'Risk': f'=IF({E}="","",IF(AND({g("Balance")}>0,OR(AND({g("Plan_End")}<>"",TODAY()>{g("Plan_End")}),AND({g("Eff_CRD")}<>"",{g("Eff_CRD")}-TODAY()<=7))),"Yes","No"))',
        }
        for c, v in f.items():
            cell = ws[f'{cL[c]}{r_}']; cell.value = v
        for c in ('Eff_CRD', 'First_Receive', 'Forecast'):
            ws[f'{cL[c]}{r_}'].number_format = '[>=99999]"-";dd-mmm-yy'
        for c in ('Received', 'Washed', 'WIP', 'Balance'):
            ws[f'{cL[c]}{r_}'].number_format = '#,##0'
        for c in board.DATE_STATIC:
            ws[f'{cL[c]}{r_}'].number_format = 'yyyy-mm-dd'
        for c in board.NUM_STATIC:
            ws[f'{cL[c]}{r_}'].number_format = '#,##0'
        for n in range(31):
            c0 = D0 + n * 7
            for pc, ac, vc in ((0, 1, 2), (3, 4, 5)):
                p_, a_ = f'{CL(c0 + pc)}{r_}', f'{CL(c0 + ac)}{r_}'
                ws.cell(r_, c0 + vc, f'=IF(OR({CL(c0)}$3="",{CL(c0)}$3>TODAY()),"",IF(AND({p_}="",{a_}=""),"",N({a_})-N({p_})))')
    # fills: input = yellow, formulas grey, sew blue, wash green
    for r_ in range(R0, R1 + 1):
        for c, _ in board.STATIC:
            ws[f'{cL[c]}{r_}'].fill = fill(INP)
        for c, _ in board.FORMULA:
            ws[f'{cL[c]}{r_}'].fill = fill('F1F5F9'); ws[f'{cL[c]}{r_}'].font = F(False, '334155', 9)
    # conditional formats
    red = fill('FECACA'); redf = Font(color='B91C1C', bold=True)
    key_rng = f'{cL["Wash_Plant"]}{R0}:{cL["Color"]}{R1}'
    ws.conditional_formatting.add(f'{cL["Risk"]}{R0}:{cL["Risk"]}{R1}', CellIsRule(operator='equal', formula=['"Yes"'], fill=red, font=redf))
    ws.conditional_formatting.add(key_rng, FormulaRule(formula=[f'AND(${cL["Risk"]}{R0}="Yes",${cL["Plan_End"]}{R0}<>"",TODAY()>${cL["Plan_End"]}{R0})'], fill=red))
    ws.conditional_formatting.add(f'{cL["Overdue"] if False else cL["Eff_CRD"]}{R0}:{cL["Eff_CRD"]}{R1}', FormulaRule(formula=[f'AND(${cL["Balance"]}{R0}>0,{cL["Eff_CRD"]}{R0}<>"",{cL["Eff_CRD"]}{R0}<TODAY())'], fill=red, font=redf))
    ws.conditional_formatting.add(f'{CL(D0)}{R0}:{CL(D1)}{R1}', FormulaRule(formula=[f'AND({CL(D0)}$4="SEW_VAR",ISNUMBER({CL(D0)}{R0}),{CL(D0)}{R0}<0)'], font=Font(color='DC2626', bold=True)))
    ws.conditional_formatting.add(f'{CL(D0)}{R0}:{CL(D1)}{R1}', FormulaRule(formula=[f'AND({CL(D0)}$4="WASH_VAR",ISNUMBER({CL(D0)}{R0}),{CL(D0)}{R0}<0)'], font=Font(color='DC2626', bold=True)))
    ws.conditional_formatting.add(f'{CL(D0)}{R0}:{CL(D1)}{R1}', FormulaRule(formula=[f'AND(OR({CL(D0)}$4="SEW_VAR",{CL(D0)}$4="WASH_VAR"),ISNUMBER({CL(D0)}{R0}),{CL(D0)}{R0}>0)'], font=Font(color='16A34A', bold=True)))
    ws.conditional_formatting.add(f'{CL(D0)}3:{CL(D1)}{R1}', FormulaRule(formula=[f'{CL(D0)}$3=""'], fill=fill('E5E7EB')))
    ws.conditional_formatting.add(f'{CL(D0)}{R0}:{CL(D1)}{R1}', FormulaRule(formula=[f'AND({CL(D0)}$3<>"",WEEKDAY({CL(D0)}$3)=6)'], fill=fill('FFF1F2')))
    ws.conditional_formatting.add(f'{CL(D0)}{R0}:{CL(D1)}{R1}', FormulaRule(formula=[f'AND({CL(D0)}$3<>"",{CL(D0)}$3=TODAY())'], fill=fill('FEF9C3')))
    # validations
    dv = DataValidation(type='decimal', operator='greaterThanOrEqual', formula1='0', allow_blank=True, showErrorMessage=True, errorTitle='Check value', error='Enter a number >= 0')
    ws.add_data_validation(dv)
    for n in range(31):
        for q in (0, 1, 3, 4):
            dv.add(f'{CL(D0 + n * 7 + q)}{R0}:{CL(D0 + n * 7 + q)}{R1}')
    for c in board.NUM_STATIC:
        dv.add(f'{cL[c]}{R0}:{cL[c]}{R1}')
    dvd = DataValidation(type='date', operator='greaterThan', formula1='36526', allow_blank=True, showErrorMessage=True, errorTitle='Date', error='Write dates as yyyy-mm-dd')
    ws.add_data_validation(dvd)
    for c in board.DATE_STATIC:
        dvd.add(f'{cL[c]}{R0}:{cL[c]}{R1}')
    # example row
    ex = {'Wash_Plant': plant, 'Sewing_Unit': 'TISWL-01', 'Buyer': 'Buyer name', 'Style': 'EXAMPLE ST-4412', 'PO': 'PO-0001', 'Item': 'Denim Pant', 'Color': 'Dark Blue', 'Season': 'SP27',
          'CRD': datetime.date(y, m, min(28, nd)), 'Order_Qty': 20000, 'Plan_Start': datetime.date(y, m, 5), 'Plan_End': datetime.date(y, m, 15), 'Merchant': 'EXAMPLE - delete me'}
    for c, v in ex.items():
        ws[f'{cL[c]}{R0}'] = v
    ws.freeze_panes = ws.cell(R0, 6)
    for j in range(6, 22):
        ws.column_dimensions[CL(j)].outlineLevel = 1
    ws.sheet_properties.tabColor = '0D9488'
    # ------------------------------------------------------------------ other tabs
    def tab(name, cols, widths=None, rows=None):
        t = wb.create_sheet(name)
        for j, h in enumerate(cols, 1):
            c = t.cell(1, j, h); c.font = F(True, 'FFFFFF'); c.fill = fill(NAVY); c.alignment = Alignment(horizontal='center', wrap_text=True)
            t.column_dimensions[CL(j)].width = (widths or {}).get(h, 16)
        for i, row in enumerate(rows or [], 2):
            for j, v in enumerate(row, 1):
                t.cell(i, j, v)
        t.freeze_panes = 'A2'
        return t
    tab('Plan_History', board.HIST_COLS, {'Timestamp': 20, 'User': 26, 'Style': 24})
    tab('Audit_Log', board.AUDIT_COLS, {'Timestamp': 20, 'User': 26, 'Style': 24, 'Old': 12, 'New': 12})
    tab('Stage_Log', ['Date', 'Wash_Plant', 'Style', 'PO', 'Color', 'Stage', 'Pcs_In', 'Pcs_Out', 'Remarks'], {'Style': 24, 'Stage': 18})
    tab('Master_Stage', ['Stage', 'Seq'], {'Stage': 22}, [['Receive Store', 1], ['Wash', 2], ['Dry Process', 3], ['QC & Packing', 4]])
    u = CFG['units'].get(plant, {})
    t = tab('Unit_Master', ['Wash_Plant', 'Wet_Capacity_Day', 'Dry_Capacity_Day'], {'Wet_Capacity_Day': 20, 'Dry_Capacity_Day': 20}, [[plant, u.get('wash_cap_day', ''), u.get('dry_cap_day', '')]])
    t['E1'] = 'Plant capacity in pcs per day (wet = wash, dry = dry process total). Used for the dashboard forecast.'; t['E1'].font = F(False, '64748B', 9)
    wb.save(out)
    return out


if __name__ == '__main__':
    if sys.argv[1] == '--all':
        month, outdir = sys.argv[2], pathlib.Path(sys.argv[3]); outdir.mkdir(parents=True, exist_ok=True)
        for u in CFG['units']:
            print('saved', build(u, month, str(outdir / f'Plan_Board_{u}_{month}.xlsx')))
    else:
        print('saved', build(sys.argv[1], sys.argv[2], sys.argv[3]))
