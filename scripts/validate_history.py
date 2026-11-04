"""Evaluate an explicitly selected local historical dataset and write a new report."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation import EvaluationProtocol, evaluate_history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', required=True)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    protocol = EvaluationProtocol.model_validate_json(Path(args.protocol).read_text())
    path = Path(args.history)
    if path.suffix.lower() == '.xlsx':
        frame = pd.read_excel(path, nrows=10001, dtype={'alumno_id': str})
    elif path.suffix.lower() == '.csv':
        frame = pd.read_csv(path, nrows=10001, dtype={'alumno_id': str})
    else:
        parser.error('Use un histórico .xlsx o .csv')
    report = evaluate_history(frame, protocol)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
    print('Informe guardado; tipo de datos:', report['dataset_kind'])
    print('Cohortes evaluadas:', sum(fold['status']=='evaluated' for fold in report['folds']))


if __name__ == '__main__':
    main()
