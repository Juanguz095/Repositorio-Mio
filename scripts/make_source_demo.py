"""Create a local SQLite source with synthetic academic history and current observations."""
import argparse
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import synthetic


def create(path):
    path = Path(path)
    new_parent = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if new_parent: path.parent.chmod(0o755)
    # Exclusive creation protects existing sources, including files not created by us.
    with path.open('xb'):
        pass
    history = synthetic()
    students = synthetic(seed=43).iloc[:30].drop(columns='deserto').copy()
    students['periodo'] = 20242
    with sqlite3.connect(path) as db:
        history.to_sql('history_records', db, index=False)
        students.to_sql('current_records', db, index=False)
        db.executescript('CREATE VIEW academic_history AS SELECT * FROM history_records;\n'
                         'CREATE VIEW academic_current AS SELECT * FROM current_records;')
    path.chmod(0o644) # Only the synthetic database exclusively created above.
    print('Created synthetic SQLite source:', path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/raw/source-demo.db')
    args = parser.parse_args()
    try:
        create(args.output)
    except FileExistsError:
        parser.error('The source already exists; choose another output path')
