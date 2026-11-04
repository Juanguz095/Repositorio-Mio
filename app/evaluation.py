"""Temporal validation reports. Dataset provenance is declared, never fabricated."""
from typing import Literal
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score, roc_auc_score
from app.pipeline import FEATURES, clean, train


class EvaluationProtocol(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_kind: Literal['synthetic', 'authorized_historical']
    target_definition: str = Field(min_length=10)
    prediction_horizon_periods: int = Field(ge=1, le=10)
    feature_timing: str = Field(min_length=10)
    enrollment_definition: str = Field(min_length=10)
    payment_definition: str = Field(min_length=10)
    authorization_confirmed: bool = False
    min_train_rows: int = Field(default=100, ge=10)
    min_test_rows: int = Field(default=50, ge=10)
    min_group_rows: int = Field(default=20, ge=5)
    threshold: float = Field(default=.5, gt=0, lt=1)

    @model_validator(mode='after')
    def require_authorization(self):
        if self.dataset_kind == 'authorized_historical' and not self.authorization_confirmed:
            raise ValueError('Debe confirmarse la autorización del histórico antes de procesarlo')
        if self.dataset_kind == 'authorized_historical' and any('REEMPLAZAR' in text for text in [self.target_definition, self.feature_timing, self.enrollment_definition, self.payment_definition]):
            raise ValueError('Completa las definiciones del protocolo antes de evaluar el histórico')
        return self


def metrics(y, probabilities, threshold):
    return {'rows': len(y), 'prevalence': float(np.mean(y)),
            'average_precision': float(average_precision_score(y, probabilities)) if np.sum(y) else None,
            'roc_auc': float(roc_auc_score(y, probabilities)) if len(np.unique(y)) == 2 else None,
            'brier': float(brier_score_loss(y, probabilities)),
            'precision': float(precision_score(y, probabilities >= threshold, zero_division=0)),
            'recall': float(recall_score(y, probabilities >= threshold, zero_division=0))}


def calibration(y, p):
    result = []
    for i, (low, high) in enumerate(zip(np.linspace(0, 1, 6)[:-1], np.linspace(0, 1, 6)[1:])):
        mask = (p >= low) & ((p <= high) if i == 4 else (p < high))
        if mask.any():
            result.append({'lower': float(low), 'upper': float(high), 'rows': int(mask.sum()),
                'predicted_mean': float(p[mask].mean()), 'observed_rate': float(np.asarray(y)[mask].mean())})
    return result


def evaluate_history(frame, protocol):
    # Keep an optional analyst-defined group outside the operational feature set.
    group_source = None
    if 'grupo' in frame.columns:
        group_source = frame[['alumno_id', 'periodo', 'grupo']].copy()
        group_source['alumno_id'] = group_source.alumno_id.astype(str).str.strip()
        group_source['periodo'] = pd.to_numeric(group_source.periodo)
        if group_source.duplicated(['alumno_id', 'periodo']).any():
            raise ValueError('Grupos ambiguos para alumno y periodo')
    cleaned, quality = clean(frame)
    if 'deserto' not in cleaned or not cleaned.deserto.isin([0, 1]).all():
        raise ValueError('El histórico requiere la etiqueta deserto binaria sin nulos')
    periods = sorted(cleaned.periodo.unique())
    if len(periods) < 2:
        raise ValueError('Se requieren al menos dos periodos históricos')
    folds = []
    for period in periods[1:]:
        past = cleaned[cleaned.periodo < period]
        heldout = cleaned[cleaned.periodo == period]
        if len(past) < protocol.min_train_rows or len(heldout) < protocol.min_test_rows or past.deserto.nunique() < 2 or heldout.deserto.nunique() < 2:
            folds.append({'period': int(period), 'status': 'skipped', 'reason': 'Filas o clases insuficientes'})
            continue
        model, fit_metrics = train(cleaned[cleaned.periodo <= period])
        p = model.predict_proba(heldout[FEATURES])[:, 1]
        groups = []
        if group_source is not None:
            cohort = heldout.merge(group_source, on=['alumno_id', 'periodo'], validate='one_to_one')
            # Merge order follows the left frame; probabilities stay aligned.
            for group, indices in cohort.groupby('grupo', dropna=False, sort=False).indices.items():
                if len(indices) < protocol.min_group_rows:
                    groups.append({'group': str(group), 'rows': len(indices), 'status': 'insufficient_rows'})
                else:
                    groups.append({'group': str(group), 'status': 'evaluated',
                        'metrics': metrics(cohort.iloc[indices].deserto.to_numpy(), p[indices], protocol.threshold)})
        folds.append({'period': int(period), 'status': 'evaluated', 'train_rows': len(past),
            'metrics': metrics(heldout.deserto.to_numpy(), p, protocol.threshold),
            'calibration': calibration(heldout.deserto.to_numpy(), p), 'groups': groups,
            'unavailable_features': fit_metrics['unavailable_features']})
    if folds[-1]['status'] != 'evaluated':
        raise ValueError('La última cohorte no permite una evaluación válida; revisa filas y clases')
    return {'dataset_kind': protocol.dataset_kind,
            'real_data_evaluated': protocol.dataset_kind == 'authorized_historical',
            'authorization_asserted_by_operator': protocol.authorization_confirmed,
            'institutional_effectiveness_demonstrated': False,
            'feature_timing_independently_verified': False,
            'protocol': protocol.model_dump(), 'quality': quality, 'folds': folds,
            'limitations': ['La división temporal no verifica cómo se construyeron las etiquetas ni las variables.',
                           'Las métricas no autorizan intervenciones ni sustituyen la revisión institucional.']}
