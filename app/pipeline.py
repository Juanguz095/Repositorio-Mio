"""Deterministic tools: no LLM is needed to clean or train."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score

FEATURES = ['asistencia', 'promedio', 'creditos_aprobados']

def synthetic(seed=42):
    rng = np.random.default_rng(seed)
    n = 600
    df = pd.DataFrame({'alumno_id': [f'SYN-{i:04}' for i in range(n)],
        'periodo': np.repeat([20231, 20232, 20241], n // 3),
        'asistencia': rng.uniform(.3, 1, n), 'promedio': rng.uniform(3, 20, n),
        'creditos_aprobados': rng.integers(0, 23, n)})
    p = 1 / (1 + np.exp(- (3 - 3*df.asistencia - .15*df.promedio - .04*df.creditos_aprobados)))
    df['deserto'] = rng.binomial(1, p)
    df.loc[rng.choice(n, 20, replace=False), 'promedio'] = np.nan
    return df

def clean(df):
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    if df.columns.duplicated().any():
        raise ValueError('Columnas duplicadas tras normalización')
    required = {'alumno_id', 'periodo', *FEATURES}
    if not required.issubset(df.columns):
        raise ValueError(f'Faltan columnas: {sorted(required - set(df.columns))}')
    before = len(df)
    df = df.drop_duplicates()
    if df[['alumno_id', 'periodo']].isna().any().any():
        raise ValueError('Identificador o periodo nulo')
    df['alumno_id'] = df.alumno_id.astype(str).str.strip()
    if (df.alumno_id == '').any() or df.duplicated(['alumno_id', 'periodo']).any():
        raise ValueError('Identificador vacío o registros contradictorios')
    for name in ['periodo', *FEATURES]:
        df[name] = pd.to_numeric(df[name], errors='raise')
    for name, low, high in [('asistencia', 0, 1), ('promedio', 0, 20), ('creditos_aprobados', 0, 40)]:
        if ((df[name].notna()) & ~df[name].between(low, high)).any():
            raise ValueError(f'Fuera de rango: {name}')
    return df, {'filas': len(df), 'duplicados_eliminados': before-len(df),
                'nulos': {k: int(v) for k,v in df[FEATURES].isna().sum().items()}}

def train(df):
    if 'deserto' not in df or not df.deserto.isin([0,1]).all():
        raise ValueError('Etiqueta binaria deserto requerida')
    cutoff = df.periodo.max()
    past, future = df[df.periodo < cutoff], df[df.periodo == cutoff]
    if past.deserto.nunique() != 2 or future.deserto.nunique() != 2:
        raise ValueError('Se requieren cohortes temporales con ambas clases')
    if past[FEATURES].isna().all().any():
        raise ValueError('Columna de entrenamiento completamente nula')
    model = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), LogisticRegression(random_state=42))
    model.fit(past[FEATURES], past.deserto)
    p = model.predict_proba(future[FEATURES])[:,1]
    metrics = {'test_periodo': int(cutoff), 'train_rows': len(past), 'test_rows': len(future),
        'average_precision': float(average_precision_score(future.deserto,p)),
        'brier': float(brier_score_loss(future.deserto,p)),
        'precision_05': float(precision_score(future.deserto,p >= .5, zero_division=0)),
        'recall_05': float(recall_score(future.deserto,p >= .5))}
    return model, metrics

class Harness:
    """Only named tools, confined file access and a per-execution budget."""
    def __init__(self, root, max_steps=10):
        self.root = Path(root).resolve()
        self.max_steps = max_steps
        self.steps = 0
        self.trace = []

    def call(self, tool, **args):
        if self.steps >= self.max_steps:
            raise RuntimeError('Presupuesto de pasos agotado')
        if tool not in {'read_excel', 'clean', 'train', 'write_report'}:
            raise PermissionError('Herramienta no permitida')
        self.steps += 1
        self.trace.append({'step': self.steps, 'tool': tool})
        if tool in {'read_excel', 'write_report'}:
            folder = self.root / ('raw' if tool == 'read_excel' else 'processed')
            path = (folder / args['path']).resolve()
            if not path.is_relative_to(folder) or not folder.resolve().is_relative_to(self.root):
                raise PermissionError('Ruta fuera del directorio autorizado')
            if tool == 'read_excel':
                return pd.read_excel(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(args['report'], indent=2), encoding='utf-8')
            return str(path)
        return {'clean': clean, 'train': train}[tool](args['df'])
