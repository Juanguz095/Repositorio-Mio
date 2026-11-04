"""Portable local demo entrypoint. Preserve existing files and cases on restart."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import synthetic
from scripts.make_source_demo import create


def initialize(root):
    root = Path(root)
    raw = root / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    history = synthetic()
    students = synthetic(seed=43).iloc[:30].drop(columns='deserto').copy()
    students['periodo'] = 20242
    for name, frame in [('history.xlsx', history), ('students.xlsx', students)]:
        path = raw/name
        try:
            with path.open('xb') as handle:
                frame.to_excel(handle, index=False, engine='openpyxl')
        except FileExistsError:
            pass
    source = raw/'source-demo.db'
    if not source.exists():
        create(source)
    samples = {
        'records.json': {'import_id': 'local-records-v1', 'history': json.loads(history.to_json(orient='records')),
                         'students': json.loads(students.to_json(orient='records'))},
        'excel.json': {'import_id': 'local-excel-v1', 'history_path': 'history.xlsx', 'students_path': 'students.xlsx'},
    }
    for name, payload in samples.items():
        try:
            with (root/name).open('x', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False)
        except FileExistsError:
            pass


def main():
    names = ('OPERATOR_TOKEN', 'REVIEWER_TOKEN', 'MOBILE_TOKEN')
    values = [os.environ.get(name) for name in names]
    if not all(values) or len(set(values)) != 3:
        raise SystemExit('Configure three distinct nonempty role tokens in the private environment file')
    if os.getenv('TUTORIA_INIT_DEMO') == '1':
        initialize(os.getenv('TUTORIA_DATA', 'data'))
    import uvicorn
    uvicorn.run('app.api:app', host='0.0.0.0', port=8000)


if __name__ == '__main__':
    main()
