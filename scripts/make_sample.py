"""Generate synthetic inputs for both n8n capture workflows. Never contains real records."""
import json
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import synthetic

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--force', action='store_true', help='Replace the generated example files')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1] / 'data'
raw = root / 'raw'
targets = [raw/'history.xlsx', raw/'students.xlsx', root/'records.json', root/'excel.json']
if any(p.exists() for p in targets) and not args.force:
    parser.error('Example files already exist; use --force only to replace these examples')
new_raw = not raw.exists()
raw.mkdir(parents=True, exist_ok=True)
if new_raw: raw.chmod(0o755)
history = synthetic()
students = synthetic(seed=43).iloc[:30].drop(columns='deserto').copy()
students['periodo'] = 20242
history.to_excel(raw / 'history.xlsx', index=False)
students.to_excel(raw / 'students.xlsx', index=False)
# These two files contain generated synthetic examples only.
for example in [raw/'history.xlsx', raw/'students.xlsx']: example.chmod(0o644)
(root / 'records.json').write_text(json.dumps({
    'import_id': 'sample-records-v1', 'history': json.loads(history.to_json(orient='records')),
    'students': json.loads(students.to_json(orient='records'))}, indent=2), encoding='utf-8')
(root / 'excel.json').write_text(json.dumps({'import_id': 'sample-excel-v1',
    'history_path': 'history.xlsx', 'students_path': 'students.xlsx'}, indent=2), encoding='utf-8')
print('Generated synthetic Excel and JSON examples under data/')
