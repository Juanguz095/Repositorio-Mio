"""Deterministic tools: no LLM is needed to clean or train."""
from pathlib import Path
import json
import unicodedata
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score

BASE_FEATURES = ['asistencia', 'promedio', 'creditos_aprobados']
OPTIONAL_FEATURES = ['matriculado', 'pagos_al_dia']
FEATURES = [*BASE_FEATURES, *OPTIONAL_FEATURES]

def synthetic(seed=42):
    rng = np.random.default_rng(seed)
    n = 600
    df = pd.DataFrame({'alumno_id': [f'SYN-{i:04}' for i in range(n)],
        'periodo': np.repeat([20231, 20232, 20241], n // 3),
        'asistencia': rng.uniform(.3, 1, n), 'promedio': rng.uniform(3, 20, n),
        'creditos_aprobados': rng.integers(0, 23, n)})
    df['matriculado'] = rng.binomial(1, .9, n)
    df['pagos_al_dia'] = rng.binomial(1, .8, n)
    p = 1 / (1 + np.exp(- (3 - 3*df.asistencia - .15*df.promedio - .04*df.creditos_aprobados
                                   + .8*(1-df.matriculado) + .4*(1-df.pagos_al_dia))))
    df['deserto'] = rng.binomial(1, p)
    df.loc[rng.choice(n, 20, replace=False), 'promedio'] = np.nan
    return df

def clean(df):
    if df is None or not 1 <= len(df) <= 10000:
        raise ValueError('Se requieren entre 1 y 10000 filas por conjunto')
    df = df.copy()
    def column_name(value):
        text = str(value).strip().lower().replace(' ', '_')
        return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    df.columns = [column_name(c) for c in df.columns]
    if df.columns.duplicated().any():
        raise ValueError('Columnas duplicadas tras normalización')
    required = {'alumno_id', 'periodo', *BASE_FEATURES}
    if not required.issubset(df.columns):
        raise ValueError(f'Faltan columnas: {sorted(required - set(df.columns))}')
    missing_optional = [name for name in OPTIONAL_FEATURES if name not in df]
    for name in missing_optional:
        df[name] = np.nan
    # Unrecognized source fields are not retained in operational case details.
    df = df[[c for c in ['alumno_id', 'periodo', *FEATURES, 'deserto'] if c in df]]
    before = len(df)
    if df[['alumno_id', 'periodo']].isna().any().any():
        raise ValueError('Identificador o periodo nulo')
    df['alumno_id'] = df.alumno_id.astype(str).str.strip()
    for name in ['periodo', *FEATURES, *(['deserto'] if 'deserto' in df else [])]:
        values = df[name].astype('string').str.strip().replace('', pd.NA)
        percent = values.str.endswith('%', na=False)
        if percent.any() and name != 'asistencia':
            raise ValueError(f'Porcentaje no permitido: {name}')
        values = values.str.removesuffix('%').str.replace(',', '.', regex=False)
        try:
            df[name] = pd.to_numeric(values, errors='raise').astype(float)
        except (ValueError, TypeError):
            raise ValueError(f'Formato numérico inválido: {name}') from None
        df.loc[percent, name] /= 100
        if np.isinf(df[name]).any():
            raise ValueError(f'Valor no finito: {name}')
    if df.periodo.isna().any() or (df.periodo <= 0).any() or (df.periodo % 1 != 0).any():
        raise ValueError('Periodo debe ser un entero positivo')
    df = df.drop_duplicates()
    if (df.alumno_id == '').any() or df.duplicated(['alumno_id', 'periodo']).any():
        raise ValueError('Identificador vacío o registros contradictorios')
    for name, low, high in [('asistencia', 0, 1), ('promedio', 0, 20), ('creditos_aprobados', 0, 40)]:
        if ((df[name].notna()) & ~df[name].between(low, high)).any():
            raise ValueError(f'Fuera de rango: {name}')
    for name in OPTIONAL_FEATURES:
        if (~df[name].isna() & ~df[name].isin([0, 1])).any():
            raise ValueError(f'Se requiere 0, 1 o nulo: {name}')
    return df, {'missing_optional_columns': missing_optional, 'filas': len(df), 'duplicados_eliminados': before-len(df),
                'nulos': {k: int(v) for k,v in df[FEATURES].isna().sum().items()}}

def train(df):
    if 'deserto' not in df or not df.deserto.isin([0,1]).all():
        raise ValueError('Etiqueta binaria deserto requerida')
    cutoff = df.periodo.max()
    past, future = df[df.periodo < cutoff], df[df.periodo == cutoff]
    if past.deserto.nunique() != 2 or future.deserto.nunique() != 2:
        raise ValueError('Se requieren cohortes temporales con ambas clases')
    if past[BASE_FEATURES].isna().all().any():
        raise ValueError('Columna de entrenamiento completamente nula')
    model = make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True), StandardScaler(), LogisticRegression(random_state=42))
    model.fit(past[FEATURES], past.deserto)
    p = model.predict_proba(future[FEATURES])[:,1]
    metrics = {'schema_version': 2, 'features': FEATURES,
        'unavailable_features': [name for name in OPTIONAL_FEATURES if past[name].isna().all()],
        'test_periodo': int(cutoff), 'train_rows': len(past), 'test_rows': len(future),
        'average_precision': float(average_precision_score(future.deserto,p)),
        'brier': float(brier_score_loss(future.deserto,p)),
        'precision_05': float(precision_score(future.deserto,p >= .5, zero_division=0)),
        'recall_05': float(recall_score(future.deserto,p >= .5))}
    return model, metrics

class Harness:
    """Only named tools, confined file access and a per-execution budget."""
    def __init__(self, root, max_steps=10):
        if type(max_steps) is not int or not 1 <= max_steps <= 10:
            raise ValueError('El presupuesto debe estar entre 1 y 10 pasos')
        self.root = Path(root).resolve()
        self.max_steps = max_steps
        self.steps = 0
        self.trace = []

    def call(self, tool, **args):
        if self.steps >= self.max_steps:
            raise RuntimeError('Presupuesto de pasos agotado')
        if tool not in {'read_excel', 'clean', 'train', 'predict', 'write_report'}:
            raise PermissionError('Herramienta no permitida')
        self.steps += 1
        event = {'step': self.steps, 'tool': tool, 'status': 'started'}
        self.trace.append(event)
        try:
            result = self._execute(tool, args)
        except Exception:
            event['status'] = 'failed'
            raise
        event['status'] = 'ok'
        return result

    def _execute(self, tool, args):
        if tool in {'read_excel', 'write_report'}:
            folder = self.root / ('raw' if tool == 'read_excel' else 'processed')
            path = (folder / args['path']).resolve()
            if not path.is_relative_to(folder) or not folder.resolve().is_relative_to(self.root):
                raise PermissionError('Ruta fuera del directorio autorizado')
            if tool == 'read_excel':
                if path.suffix.lower() != '.xlsx':
                    raise ValueError('Solo se permiten archivos .xlsx')
                return pd.read_excel(path, nrows=10001)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(args['report'], indent=2), encoding='utf-8')
            return str(path)
        if tool == 'predict':
            return args['model'].predict_proba(args['df'][FEATURES])[:, 1]
        return {'clean': clean, 'train': train}[tool](args['df'])
