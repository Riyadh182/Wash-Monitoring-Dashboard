"""One-time helper: extracts unit/machine/capacity config from Capacity_August_2026.xlsx into units_config.json."""
import json, sys, openpyxl
src = sys.argv[1] if len(sys.argv) > 1 else 'Capacity_August_2026.xlsx'
ws = openpyxl.load_workbook(src, data_only=True).worksheets[0]
PROC = {4:'Laser Whisker',5:'Laser Mark Destroy',6:'Pattern Whisker',7:'Hand Sand (Front & Back)',8:'Allover Hand Sand',9:'Tagging',
        10:'Grinding',11:'Destruction',12:'Cutting / Destroy',13:'Air Blowing',14:'PP Spray (Front & Back)',15:'Allover PP Spray',16:'PP Rubbing',17:'Machine 3D',18:'Iron 3D'}
wash_rows = {'CWL-1':9,'CWL-2':10,'CWL-3':11,'CWL-4':12,'SWDL':13,'BWL-1':15,'BWL-2':16,'EWDL':17,'SZWDL':18,'NWL':19}
dry_rows  = {'CWL-1':26,'CWL-2':28,'CWL-3':30,'CWL-4':32,'SWDL':34,'BWL-1':38,'BWL-2':40,'EWDL':42,'SZWDL':44}
units = {}
for u, r in wash_rows.items():
    units[u] = dict(fl=ws.cell(r,3).value, ab=ws.cell(r,4).value, bl=ws.cell(r,5).value,
                    wash_cap_day=ws.cell(r,12).value, dry_cap_day=ws.cell(r,25).value,
                    wash_mix={'Denim':ws.cell(r,18).value,'Acid':ws.cell(r,19).value,'Dyeing':ws.cell(r,20).value,'Twill':ws.cell(r,21).value},
                    dry_processes={}, dry_verified=False)
for u, r in dry_rows.items():
    for c, name in PROC.items():
        units[u]['dry_processes'][name] = dict(machines=ws.cell(r,c).value, capacity_day=ws.cell(r+1,c).value)
# data-quality flag: BWL-1/BWL-2/EWDL/SZWDL dry rows are identical to CWL-1..CWL-4 rows in the source file
def sig(u): return tuple(v['capacity_day'] for v in units[u]['dry_processes'].values())
order = list(dry_rows)
for i, u in enumerate(order):   # a unit is suspect if it duplicates an EARLIER unit's row (copy-paste)
    units[u]['dry_verified'] = all(sig(u) != sig(o) for o in order[:i])
json.dump(dict(units=units, dry_process_names=list(PROC.values())), open('tools/units_config.json','w'), indent=1)
print({u: v['dry_verified'] for u, v in units.items() if v['dry_processes']})
