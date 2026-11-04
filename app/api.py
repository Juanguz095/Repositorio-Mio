"""Local demonstration. Separate operator, reviewer and mobile bearer tokens."""
import os
from pathlib import Path
from contextlib import contextmanager
import secrets
import sqlite3
import json
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from app.pipeline import Harness, synthetic, FEATURES

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
