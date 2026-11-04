import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.api import app
from app.agent import DataAgent
from app.pipeline import clean, synthetic


def records(frame):
    return json.loads(frame.to_json(orient='records'))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.patch = patch.dict(os.environ, {
            'TUTORIA_DB': self.root.name+'/cases.db', 'TUTORIA_DATA': self.root.name,
            'OPERATOR_TOKEN': 'operator-test', 'REVIEWER_TOKEN': 'review-test', 'MOBILE_TOKEN': 'mobile-test'})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.operator = {'Authorization': 'Bearer operator-test'}
        self.reviewer = {'Authorization': 'Bearer review-test'}
        self.mobile = {'Authorization': 'Bearer mobile-test'}
        self.history = synthetic()
        self.students = synthetic().iloc[:8].drop(columns='deserto').copy()
        self.students['periodo'] = 20242
        self.payload = {'import_id': 'form-001', 'history': records(self.history), 'students': records(self.students)}

    def ingest(self, payload=None):
        return self.client.post('/ingest/records', json=payload or self.payload, headers=self.operator)

    def test_import_review_mobile_and_idempotency(self):
        self.assertEqual(self.client.post('/ingest/records', json=self.payload).status_code, 401)
        self.assertEqual(self.client.post('/ingest/records', json=self.payload, headers=self.mobile).status_code, 403)
        result = self.ingest()
        self.assertEqual(result.status_code, 200, result.text)
        batch = result.json()
        self.assertEqual(batch['cases'], 8)
        self.assertEqual(batch['metrics']['train_rows'], 400)
        self.assertEqual(batch['metrics']['test_rows'], 200)
        self.assertEqual(len(batch['trace']), 4)
        self.assertTrue(all(step['status'] == 'ok' for step in batch['trace']))
        self.assertEqual(self.ingest().json(), batch)
        self.assertEqual(self.client.get(f"/batches/{batch['batch']}", headers=self.operator).json(), batch)
        pending = self.client.get('/review', headers=self.reviewer).json()
        self.assertEqual(len(pending), 8)
        self.assertEqual(self.client.get('/cases', headers=self.mobile).json(), [])
        case = pending[0]['id']
        self.assertEqual(self.client.get(f'/cases/{case}', headers=self.mobile).status_code, 404)
        self.assertEqual(self.client.post(f'/review/{case}', headers=self.reviewer,
            json={'approve': True, 'note': 'Tutor confirma seguimiento'}).status_code, 200)
        detail = self.client.get(f'/cases/{case}', headers=self.mobile).json()
        self.assertEqual(detail['academic']['periodo'], 20242)
        self.assertEqual(detail['status'], 'approved')
        self.assertEqual(len(self.client.get(f'/cases/{case}/history', headers=self.mobile).json()), 1)
        self.payload['students'][0]['promedio'] = 19
        self.assertEqual(self.ingest().status_code, 409)

    def test_excel_and_path_restrictions(self):
        raw = Path(self.root.name, 'raw')
        raw.mkdir()
        self.history.to_excel(raw/'history.xlsx', index=False)
        self.students.to_excel(raw/'students.xlsx', index=False)
        payload = {'import_id': 'excel-001', 'history_path': 'history.xlsx', 'students_path': 'students.xlsx'}
        response = self.client.post('/ingest/excel', json=payload, headers=self.operator)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['cases'], 8)
        self.assertEqual(self.client.post('/ingest/excel', json=payload, headers=self.operator).json(), response.json())
        self.students.loc[self.students.index[0], 'promedio'] = 20
        self.students.to_excel(raw/'students.xlsx', index=False)
        self.assertEqual(self.client.post('/ingest/excel', json=payload, headers=self.operator).status_code, 409)
        payload['history_path'] = '../../outside.xlsx'
        self.assertEqual(self.client.post('/ingest/excel', json=payload, headers=self.operator).status_code, 403)
        payload['history_path'] = 'missing.xlsx'
        self.assertEqual(self.client.post('/ingest/excel', json=payload, headers=self.operator).status_code, 422)
        (raw/'broken.xlsx').write_text('not an Excel')
        payload['history_path'] = 'broken.xlsx'
        self.assertEqual(self.client.post('/ingest/excel', json=payload, headers=self.operator).status_code, 422)

    def test_bad_inputs_create_no_cases(self):
        for change in ['past', 'label', 'range', 'empty']:
            payload = json.loads(json.dumps(self.payload))
            if change == 'past': payload['students'][0]['periodo'] = 20231
            if change == 'label': payload['history'][0]['deserto'] = None
            if change == 'range': payload['students'][0]['asistencia'] = 2
            if change == 'empty': payload['students'] = []
            with self.subTest(change=change):
                self.assertEqual(self.ingest(payload).status_code, 422)
        self.assertEqual(self.client.get('/review', headers=self.reviewer).json(), [])

    def test_normalization_and_nonfinite(self):
        frame = self.students.copy().astype(object)
        frame.loc[0, 'asistencia'] = ' 75% '
        frame.loc[0, 'promedio'] = '14,5'
        frame = frame.rename(columns={'alumno_id': ' Alumno ID ', 'creditos_aprobados': 'Créditos aprobados'})
        result, _ = clean(frame)
        self.assertEqual(result.loc[0, 'asistencia'], .75)
        self.assertEqual(result.loc[0, 'promedio'], 14.5)
        for column, value in [('periodo', 20242.5), ('asistencia', float('inf'))]:
            invalid = self.students.copy()
            invalid[column] = invalid[column].astype(float)
            invalid.loc[0, column] = value
            with self.assertRaises(ValueError): clean(invalid)

    def test_agent_budget_and_trace(self):
        agent = DataAgent(self.root.name, max_steps=2)
        with self.assertRaises(RuntimeError): agent.run(self.history, self.students)
        self.assertEqual(len(agent.harness.trace), 2)
        with self.assertRaises(PermissionError): DataAgent(self.root.name).harness.call('approve')
        agent = DataAgent(self.root.name)
        with self.assertRaises(PermissionError): agent.harness.call('read_excel', path='../outside.xlsx')
        self.assertEqual(agent.harness.trace[0]['status'], 'failed')

    def test_workflow_contracts(self):
        for source in ['records', 'excel']:
            workflow = json.loads(Path('n8n', source+'.json').read_text())
            nodes = {node['id']: node for node in workflow['nodes']}
            self.assertEqual(nodes['capture']['parameters']['authentication'], 'headerAuth')
            self.assertEqual(nodes['ingest']['parameters']['url'], 'http://api:8000/ingest/'+source)
            self.assertNotIn('credentials', nodes['ingest'])
            self.assertFalse(workflow['active'])
