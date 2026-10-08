import json, pathlib
HERE = pathlib.Path(__file__).parent
CFG = json.load(open(HERE / 'units_config.json'))
WASH_TYPES = ['Denim', 'Acid', 'Twill', 'Dyeing']
WASH_REASONS = ['Machine breakdown', 'Power / utility', 'Water / steam shortage', 'Waiting for input', 'Waiting for chemical',
                'Waiting for dryer / unload', 'Shade / quality hold', 'Changeover / cleaning', 'Other']
DRY_REASONS = ['Machine breakdown', 'Power / utility', 'Waiting for input', 'Waiting for material', 'Operator shortage',
               'Changeover / setup', 'Quality hold', 'Other']
TYPE_CODE = {'F/L': 'FL', 'Acid B/L': 'AB', 'B/L': 'BL'}

def hour_labels(day_start=8):
    return [f"{(day_start+i)%24:02d}:00-{(day_start+i+1)%24:02d}:00" for i in range(24)]

def machines_for(unit, run_hours=24):
    u = CFG['units'][unit]
    n = u['fl'] + u['ab'] + u['bl']
    plan = round(u['wash_cap_day'] / n / run_hours, 4)
    rows = []
    for typ, key in [('F/L', 'fl'), ('Acid B/L', 'ab'), ('B/L', 'bl')]:
        for k in range(1, u[key] + 1):
            rows.append(dict(Unit=unit, Machine_ID=f"{unit}-{TYPE_CODE[typ]}-{k:02d}", Type=typ, Plan_per_hr=plan, Active='Y'))
    return rows

def processes_for(unit):
    u = CFG['units'][unit]
    return [dict(Unit=unit, Process=p, Machines=v['machines'], Capacity_per_day=v['capacity_day'], Active='Y')
            for p, v in u['dry_processes'].items()]

DEFAULT_SETTINGS = [('Run_Hours', 24), ('Day_Start_Hour', 8), ('Plan_Basis', 1.0), ('Target_Pct', 0.95), ('Alert_Pct', 0.80),
                    ('Max_Defect_Pct', 0.03), ('Max_Rewash_Pct', 0.02)]
