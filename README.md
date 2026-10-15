# Wash & Dry Monitor (Streamlit)

Dashboard for 10 wash plants. Every plant has its own Google Sheet (the Plan Board file, version 3). The app reads
four clean tabs from each sheet and builds four menus.

| Menu | What it shows |
|---|---|
| 📊 Overview | Capacity, running styles (orders + unique styles), crisis orders, WIP, plan vs actual input / output (month plan and till today), max holding time with buyer, next-7-days CRD WIP, graphs, downloadable tables (overall, wash plant, sewing unit, buyer, CRD, orders) |
| ⏱ Hourly Monitoring | Today hour by hour: dry target / output / achievement, wet target / output / achievement, final hourly output, last days input vs output, defect and rewash %, top orders today |
| 📑 Reports | Plan execution (wash plant / sewing unit / both / orders), daily input-output by wash type (Total + one column per day, per plant or all plants), WIP (all plants, plant, sewing unit, buyer, unit x buyer, CRD). Every table: CSV + Excel, plus Excel packs |
| 🚨 Crisis | Styles with CRD inside 7 days (or overdue) and balance open, or wash output below 80% of plan. Shows CRD, order qty, plan till now, dry output, wash output vs plan, sewing balance |

## Google Sheet tabs used (do not rename)
`Dashboard_Data`, `Dashboard_Daily`, `Hourly_Monitor`, `Input_Board`, `Output_Board`, `Unit_Master`.
They exist in `Plan_Board_BWL-01_2026-11_v3.xlsx`. For the other 9 plants use the same file (one copy per plant).

## Run on your PC
```
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml     (then fill the sheet ids)
streamlit run app.py
```
No sheet ids yet? Tick **Use demo data** in the sidebar to see the full design with fake data.

## Deploy (GitHub + Streamlit Community Cloud)
1. Create a GitHub repository and upload this folder (the `.gitignore` keeps `secrets.toml` out).
2. share.streamlit.io > New app > pick the repo, main file `app.py`.
3. App settings > Secrets: paste the content of `secrets.toml.example` with the real sheet ids.
4. Sheets must be readable: either **Share > Anyone with the link > Viewer** (easiest), or create a Google
   service account, share each sheet with its e-mail and add the `[gcp_service_account]` block in Secrets.

Data is cached for 5 minutes; the sidebar button **Refresh data now** clears it.

## Files
```
app.py                 menu + sidebar + header
views/overview.py      Overview menu
views/hourly.py        Hourly Monitoring menu
views/reports.py       Reports menu
views/crisis.py        Crisis menu
utils/data.py          Google Sheet / local xlsx readers and parsers
utils/metrics.py       every calculation (pure pandas)
utils/export.py        CSV and formatted Excel downloads
utils/ui.py            theme, KPI cards, download buttons
utils/demo.py          demo data
utils/config.py        plant names, colours, crisis rules
tests/smoke_test.py    runs every page with stubbed Streamlit (demo data or LOCAL_XLSX=recalculated sheet file)
```

## Rules used (change in `utils/config.py` or in the Crisis "rules" box)
* Crisis = wash balance > 0 and CRD within 7 days (overdue included), **or** wash output < 80% of plan till today.
* Holding time = days since last output (no output yet: since last input / first input) while WIP > 0.
* Wash output / actual output = Output_Board (final output) + opening output; input = Input_Board + opening.
* Daily wash-type report counts this month entries of Input_Board / Output_Board (opening WIP not included).
