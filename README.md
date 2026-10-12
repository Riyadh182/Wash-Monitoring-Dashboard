# Wash & Dry Monitoring — Plan Board edition

Sewing plan + wash plan in ONE sheet per plant per month. Nobody types Style/PO every day. The dashboard shows plan vs actual (sewing and wash), EDD+FIFO wash sequence, red flags after plan end, where every PO is (stage-wise), and every manipulated entry.

## 1. How it works
1. Each month, 10 Google Sheets (one per wash plant), made from `Plan_Board_<PLANT>_<YYYY-MM>.xlsx` (upload to Drive > Open with Google Sheets). Share "Anyone with the link: Editor".
2. **Planner** fills the yellow static columns once per order (Style, PO, Color, CRD, Order_Qty, Plan_Start, Plan_End) and the daily SEW_PLAN / WASH_PLAN.
3. **Floor** enters only numbers: SEW_ACT (pcs received from sewing) and WASH_ACT (pcs washed/finished) in that day's column. No style/PO typing, the row already is the PO.
4. Month has 28/29/30/31 day blocks (B2 = first of month; extra blocks hidden by menu "Plan Board > 2. Setup month").
5. Dashboard: Streamlit app (`app.py`) reads the sheets.

## 2. Rules
- **EDD + FIFO**: priority per plant = earliest Eff_CRD (Revised_CRD else CRD), then earliest first-received date, then PO. Same style + same CRD: the PO received first washes first (PO-wise).
- **Red flag**: Plan_End passed and balance (Order_Qty - Washed) > 2% => "Overrun" (possible crisis); if CRD is also inside the horizon or passed => Critical / Overdue. Also flagged: no sewing plan for the WIP, short pcs (reject / missing body), forecast beyond CRD.
- **History**: any change to Plan_Start, Plan_End, CRD, Revised_CRD, Order_Qty or a day plan cell is logged in `Plan_History` with a version number (first entry = v1).
- **Manipulation**: changing/deleting an already entered actual/opening/reject number is logged in `Audit_Log` (type EDIT), the cell turns red with a note, and the dashboard (Audit & History, Plan Execution "Edited") shows it. First entry for a day older than yesterday is logged as LATE.
- **Stage tracker**: `Stage_Log` (Date, Wash_Plant, Style, PO, Color, Stage, Pcs_In, Pcs_Out); pcs in stage = cumulative In - Out. Stage order from `Master_Stage`.
- **Forecast**: daily wash capacity (Unit_Master) filled in priority order from WIP + later-dated sewing plan => Forecast date, verdict, suggested wash plan.

## 2b. Hourly layer: easiest data entry (Cycle_Log)
Optional, feeds Hourly Monitor / Machines / Style Explorer. **One row per load**: Machine_ID (dropdown), Order (dropdown "Style | PO | Color"), Pcs, In_Time, Out_Time (type `x` = now), optional Defect / Rewash / Downtime_Min.
The dashboard derives hourly input (hour the load went in), hourly output (hour it came out), recipe time (Out - In), WIP (loaded but not out yet) and machine-wise average recipe time vs `Std_Recipe_Min` (Master_Machine). Apps Script (`apps_script/Code.gs`) auto-fills Date and In_Time.
`Wash_Log` (machine x hour rows) still works; do not enter the same day in both. Template: `Wash_Template_<PLANT>.xlsx`.

## 2c. Dashboard colours and finished dry output
- Achievement colours everywhere: green >= 80%, yellow 60-80%, red < 60%. Hourly Monitor shows one box per hour (output vs hourly plan).
- Sidebar: CRD Date, Sewing Unit, Select Buyer (cascading). They apply to Style Explorer, CRD Crisis, Plan Execution, PO Tracker and Reports.
- Finished dry output of a style = the MINIMUM of the process totals the style passed through (summing processes would count a piece once per process).
- Style Explorer: Style summary (most critical style = highest last-cycle holding time), Style details (box strip above the daily graph), Style crisis (colour-coded cards).

## 3. Setup
1. Make the 10 sheets from the templates; in each: Extensions > Apps Script > paste `apps_script/PlanBoard.gs` > save > reload > menu **Plan Board**: run *1. Enable audit* (authorise once) and *2. Setup month*.
2. Streamlit Cloud > Secrets: copy `.streamlit/secrets.toml.example`, put the 10 IDs in `current`.
3. Month end: Plan Board > *4. Create next month sheet* (copies open orders only, opening balances carried, days cleared). Add `"YYYY-MM:oldID"` to `archive`, replace the ID in `current`.
4. 5 years = 60 months x 10 sheets: only `current` is read normally; tick "Include history" and pick months to load archives (closed months cached 24 h).

## 4. Do / don't
- Never insert rows above row 8 or move header rows 1-6 (codes in row 4, dates in row 3 are read by the app). 700 order rows per sheet.
- Do not rename tabs: Plan_Board, Plan_History, Audit_Log, Stage_Log, Master_Stage, Unit_Master.
- Hourly logs (Wash_Log, Dry_Log, WIP_Log, masters) are optional; keep them only for machine/process/quality pages.

## 5. Limits (honest)
- Google Sheets cannot block edits: it detects and marks them. Anonymous editors show a blank user name; use Google accounts for names. Deleting the whole `Audit_Log` tab by hand is possible: restrict that tab (Data > Protect).
- Plant-level daily WIP ignores reject / missing body (they are not dated); order-level WIP includes them.
- Apps Script and Google "gviz" parsing and the Streamlit rendering were tested only with stubs / LibreOffice here, not on live Google. Test one sheet first.

## 6. Dev
`python tools/make_demo_board.py` (demo data), `python tools/make_planboard_template.py --all 2026-11 out/`, tests: `python tests/test_calc.py && python tests/test_board.py && python tests/smoke_app.py`.
