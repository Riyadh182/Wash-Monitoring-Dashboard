"""Builds one template workbook per wash plant (10 files) into an output folder: python make_all_templates.py ../templates"""
import subprocess, sys, pathlib
from common import CFG
out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '../templates'); out.mkdir(exist_ok=True, parents=True)
for u in CFG['units']:
    subprocess.run([sys.executable, str(pathlib.Path(__file__).parent / 'make_template.py'), u, str(out / f'Wash_Template_{u}.xlsx')], check=True)
