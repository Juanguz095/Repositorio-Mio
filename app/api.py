"""Local demonstration. Separate operator, reviewer and mobile bearer tokens."""
import os
from pathlib import Path
from contextlib import contextmanager
import secrets
import hashlib
from zipfile import BadZipFile
import pandas as pd
import sqlite3
import json
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict
from app.pipeline import Harness, synthetic, FEATURES
from app.agent import DataAgent
from app.llm import configured_planner, AgentUnavailable
from app.sources import read_sqlite, SourceUnavailable

app = FastAPI(title='TutorIA — demo sintética')
bearer = HTTPBearer()

def role(name):
    def check(auth: HTTPAuthorizationCredentials = Depends(bearer)):
        expected = os.getenv(name)
        if not expected or not secrets.compare_digest(auth.credentials, expected):
            raise HTTPException(403, 'Acceso denegado')
    return check

@contextmanager
def db():
    Path(os.getenv('TUTORIA_DB', 'data/tutoria.db')).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(os.getenv('TUTORIA_DB', 'data/tutoria.db'))
    connection.row_factory = sqlite3.Row
    connection.executescript('''CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, metrics TEXT);
    CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY, batch INTEGER, student TEXT, risk REAL, status TEXT DEFAULT 'pending');
    CREATE TABLE IF NOT EXISTS observations(event_id TEXT PRIMARY KEY, student TEXT NOT NULL, periodo INTEGER NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(student,periodo));
    CREATE TABLE IF NOT EXISTS imports(import_id TEXT PRIMARY KEY, digest TEXT NOT NULL, response TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS case_details(case_id INTEGER PRIMARY KEY, detail TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS batch_reports(batch INTEGER PRIMARY KEY, report TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, case_id INTEGER, action TEXT, note TEXT, created TEXT);''')
    try:
        with connection:
            yield connection
    finally:
        connection.close()

@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'synthetic-demo'}

@app.post('/demo/run', dependencies=[Depends(role('OPERATOR_TOKEN'))])
def run_demo():
    harness = Harness('data')
    frame, report = harness.call('clean', df=synthetic())
    model, metrics = harness.call('train', df=frame)
    harness.call('write_report', path='quality.json', report=report)
    cohort = frame[frame.periodo == frame.periodo.max()]
    probabilities = model.predict_proba(cohort[FEATURES])[:,1]
    with db() as c:
        batch = c.execute('INSERT INTO batches(metrics) VALUES (?)', (json.dumps(metrics),)).lastrowid
        c.executemany('INSERT INTO cases(batch,student,risk) VALUES (?,?,?)',
                      [(batch, sid, float(p)) for sid,p in zip(cohort.alumno_id, probabilities)])
    return {'batch': batch, 'cases': len(cohort), 'metrics': metrics, 'trace': harness.trace}

class ImportBase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    import_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')


class RecordsImport(ImportBase):
    history: list[dict] = Field(min_length=1, max_length=10000)
    students: list[dict] = Field(min_length=1, max_length=10000)


class ExcelImport(ImportBase):
    history_path: str = Field(min_length=1, max_length=200)
    students_path: str = Field(min_length=1, max_length=200)


def imported_response(connection, import_id, digest):
    previous = connection.execute('SELECT digest,response FROM imports WHERE import_id=?', (import_id,)).fetchone()
    if previous:
        if previous['digest'] != digest:
            raise HTTPException(409, 'import_id ya utilizado con datos distintos')
        return json.loads(previous['response'])


def ingest(payload, excel=False, frames=None):
    try:
        agent = DataAgent(os.getenv('TUTORIA_DATA', 'data'), planner=configured_planner())
        if frames is not None:
            history, students = frames
        elif excel:
            # Read before checking idempotency: changing a file with the same ID
            # must be detected, rather than silently returning an older result.
            history = agent.harness.call('read_excel', path=payload.history_path)
            students = agent.harness.call('read_excel', path=payload.students_path)
        else:
            history = pd.DataFrame(payload.history)
            students = pd.DataFrame(payload.students)
        digest = hashlib.sha256((history.to_json(orient='split') + '\n' + students.to_json(orient='split')).encode()).hexdigest()
        with db() as c:
            previous = imported_response(c, payload.import_id, digest)
            if previous is not None:
                return previous
        frame, probabilities, metrics, quality = agent.run(history, students)
    except AgentUnavailable:
        raise HTTPException(503, 'Planificador LLM local no disponible; comprueba Ollama y su modelo') from None
    except PermissionError:
        raise HTTPException(403, 'Ruta fuera del directorio autorizado') from None
    except (FileNotFoundError, IsADirectoryError):
        raise HTTPException(422, 'Archivo Excel no disponible en data/raw') from None
    except (ValueError, TypeError, KeyError, RuntimeError):
        # Column/range validation details contain no raw student records.
        raise HTTPException(422, 'Datos inválidos: comprueba columnas, rangos, periodos y etiquetas del histórico') from None
    except (OSError, BadZipFile):
        raise HTTPException(422, 'No se pudo leer el Excel') from None
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        previous = imported_response(c, payload.import_id, digest)
        if previous is not None:
            return previous
        batch = c.execute('INSERT INTO batches(metrics) VALUES (?)', (json.dumps(metrics),)).lastrowid
        for (_, row), probability in zip(frame.iterrows(), probabilities):
            case_id = c.execute('INSERT INTO cases(batch,student,risk) VALUES (?,?,?)',
                                (batch, row.alumno_id, float(probability))).lastrowid
            detail = {name: None if pd.isna(row[name]) else float(row[name]) for name in ['periodo', *FEATURES]}
            c.execute('INSERT INTO case_details(case_id,detail) VALUES (?,?)', (case_id, json.dumps(detail)))
        response = {'batch': batch, 'cases': len(frame), 'status': 'pending', 'metrics': metrics,
                    'quality': quality, 'trace': agent.harness.trace, 'agent': agent.metadata}
        c.execute('INSERT INTO batch_reports(batch,report) VALUES (?,?)', (batch, json.dumps(response)))
        c.execute('INSERT INTO imports(import_id,digest,response) VALUES (?,?,?)',
                  (payload.import_id, digest, json.dumps(response)))
    return response


@app.post('/ingest/records', dependencies=[Depends(role('OPERATOR_TOKEN'))])
def ingest_records(payload: RecordsImport):
    return ingest(payload)


@app.post('/ingest/excel', dependencies=[Depends(role('OPERATOR_TOKEN'))])
def ingest_excel(payload: ExcelImport):
    return ingest(payload, excel=True)


@app.get('/batches/{batch_id}', dependencies=[Depends(role('OPERATOR_TOKEN'))])
def batch_report(batch_id: int):
    with db() as c:
        result = c.execute('SELECT report FROM batch_reports WHERE batch=?', (batch_id,)).fetchone()
        if not result:
            raise HTTPException(404, 'Informe no disponible')
        return json.loads(result['report'])


@app.get('/review', dependencies=[Depends(role('REVIEWER_TOKEN'))])
def review():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM cases WHERE status='pending' ORDER BY risk DESC")]

class Decision(BaseModel):
    approve: bool
    note: str = Field(min_length=3, max_length=1000)

@app.post('/review/{case_id}', dependencies=[Depends(role('REVIEWER_TOKEN'))])
def decide(case_id: int, decision: Decision):
    status = 'approved' if decision.approve else 'rejected'
    with db() as c:
        changed = c.execute("UPDATE cases SET status=? WHERE id=? AND status='pending'", (status, case_id)).rowcount
        if not changed:
            raise HTTPException(409, 'Caso inexistente o ya revisado')
        c.execute('INSERT INTO history(case_id,action,note,created) VALUES (?,?,?,?)',
                  (case_id,status,decision.note,datetime.now(timezone.utc).isoformat()))
    return {'status': status}

@app.get('/cases', dependencies=[Depends(role('MOBILE_TOKEN'))])
def cases():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM cases WHERE status='approved' ORDER BY risk DESC")]

@app.get('/cases/{case_id}/history', dependencies=[Depends(role('MOBILE_TOKEN'))])
def history(case_id: int):
    with db() as c:
        if not c.execute("SELECT id FROM cases WHERE id=? AND status='approved'", (case_id,)).fetchone():
            raise HTTPException(404, 'Caso no disponible')
        return [dict(r) for r in c.execute('SELECT * FROM history WHERE case_id=? ORDER BY id', (case_id,))]


@app.get('/cases/{case_id}', dependencies=[Depends(role('MOBILE_TOKEN'))])
def case_detail(case_id: int):
    with db() as c:
        case = c.execute("SELECT * FROM cases WHERE id=? AND status='approved'", (case_id,)).fetchone()
        if not case:
            raise HTTPException(404, 'Caso no disponible')
        detail = c.execute('SELECT detail FROM case_details WHERE case_id=?', (case_id,)).fetchone()
        return {**dict(case), 'academic': json.loads(detail['detail']) if detail else None}


class SourceImport(ImportBase):
    pass


class FormObservation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')
    alumno_id: str = Field(min_length=1, max_length=80)
    periodo: int = Field(gt=0, strict=True)
    asistencia: float | None = Field(default=None, ge=0, le=1)
    promedio: float | None = Field(default=None, ge=0, le=20)
    creditos_aprobados: float | None = Field(default=None, ge=0, le=40)
    matriculado: int | None = Field(default=None, ge=0, le=1, strict=True)
    pagos_al_dia: int | None = Field(default=None, ge=0, le=1, strict=True)


class FormImport(ImportBase):
    periodo: int = Field(gt=0, strict=True)


def source_frame(dataset):
    try:
        return read_sqlite(os.getenv('TUTORIA_SOURCE_DB', 'data/raw/source-demo.db'), dataset)
    except SourceUnavailable:
        raise HTTPException(503, 'Origen SQLite no disponible; comprueba TUTORIA_SOURCE_DB y sus vistas') from None


@app.post('/sources/sqlite/run', dependencies=[Depends(role('OPERATOR_TOKEN'))])
def source_run(payload: SourceImport):
    return ingest(payload, frames=(source_frame('history'), source_frame('students')))


@app.post('/forms/observations', dependencies=[Depends(role('OPERATOR_TOKEN'))])
def capture_form(payload: FormObservation):
    record = payload.model_dump(exclude={'event_id'})
    record['alumno_id'] = record['alumno_id'].strip()
    if not record['alumno_id']:
        raise HTTPException(422, 'Identificador vacío')
    serialized = json.dumps(record, sort_keys=True)
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        previous = c.execute('SELECT digest FROM observations WHERE event_id=?', (payload.event_id,)).fetchone()
        if previous:
            if previous['digest'] != digest:
                raise HTTPException(409, 'event_id ya utilizado con datos distintos')
            return {'event_id': payload.event_id, 'status': 'captured'}
        if c.execute('SELECT 1 FROM observations WHERE student=? AND periodo=?', (record['alumno_id'], payload.periodo)).fetchone():
            raise HTTPException(409, 'Ya existe una observación para el alumno y periodo')
        c.execute('INSERT INTO observations(event_id,student,periodo,digest,payload) VALUES (?,?,?,?,?)',
                  (payload.event_id, record['alumno_id'], payload.periodo, digest, serialized))
    return {'event_id': payload.event_id, 'status': 'captured'}


@app.post('/sources/forms/run', dependencies=[Depends(role('OPERATOR_TOKEN'))])
def forms_run(payload: FormImport):
    history = source_frame('history')
    with db() as c:
        rows = c.execute('SELECT payload FROM observations WHERE periodo=? ORDER BY student LIMIT 10001', (payload.periodo,)).fetchall()
    if not rows:
        raise HTTPException(422, 'No hay observaciones capturadas para ese periodo')
    return ingest(payload, frames=(history, pd.DataFrame([json.loads(row['payload']) for row in rows])))


@app.get('/review/{case_id}', dependencies=[Depends(role('REVIEWER_TOKEN'))])
def review_detail(case_id: int):
    with db() as c:
        case = c.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
        if not case:
            raise HTTPException(404, 'Caso no disponible')
        detail = c.execute('SELECT detail FROM case_details WHERE case_id=?', (case_id,)).fetchone()
        history = c.execute('SELECT * FROM history WHERE case_id=? ORDER BY id', (case_id,)).fetchall()
        return {**dict(case), 'academic': json.loads(detail['detail']) if detail else None,
                'history': [dict(row) for row in history]}
