import os
import tempfile
import unittest
from pathlib import Path
import httpx
import subprocess
import socket
import time
from app.api import app
from app.pipeline import Harness, clean, synthetic, train

class SystemTests(unittest.TestCase):
    def test_temporal_training(self):
        df, report = clean(synthetic())
        _, metrics = train(df)
        self.assertEqual(metrics['train_rows'], 400)
        self.assertEqual(metrics['test_rows'], 200)
        self.assertEqual(metrics['test_periodo'], 20241)
        self.assertEqual(report['nulos']['promedio'], 20)

    def test_cleaning(self):
        import pandas as pd
        df = synthetic()
        _, report = clean(pd.concat([df, df.iloc[:1]]))
        self.assertEqual(report['duplicados_eliminados'], 1)
        df.loc[0, 'asistencia'] = 2
        with self.assertRaises(ValueError): clean(df)

    def test_harness(self):
        with tempfile.TemporaryDirectory() as root:
            h = Harness(root, max_steps=1)
            with self.assertRaises(PermissionError): h.call('shell')
            with self.assertRaises(PermissionError): h.call('read_excel', path='../../secret.xlsx')
            with self.assertRaises(RuntimeError): h.call('clean', df=synthetic())

    def test_excel(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'raw').mkdir()
            synthetic().to_excel(Path(root, 'raw/input.xlsx'), index=False)
            h = Harness(root)
            df = h.call('read_excel', path='input.xlsx')
            self.assertEqual(len(h.call('clean', df=df)[0]), 600)

    def test_approval_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            from unittest.mock import patch
            with patch.dict(os.environ, {'TUTORIA_DB': root+'/test.db', 'OPERATOR_TOKEN': 'operator-test',
                                         'REVIEWER_TOKEN': 'review-test', 'MOBILE_TOKEN': 'mobile-test'}):
                sock = socket.socket()
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
                sock.close()
                server = subprocess.Popen(['python', '-m', 'uvicorn', 'app.api:app', '--port', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.addCleanup(server.wait)
                self.addCleanup(server.terminate)
                client = httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=10)
                self.addCleanup(client.close)
                for _ in range(100):
                    try:
                        if client.get('/health').status_code == 200: break
                    except httpx.ConnectError: pass
                    time.sleep(.1)
                else: self.fail('API failed to start')
                operator = {'Authorization': 'Bearer operator-test'}
                reviewer = {'Authorization': 'Bearer review-test'}
                mobile = {'Authorization': 'Bearer mobile-test'}
                self.assertEqual(client.post('/demo/run').status_code, 401)
                response = client.post('/demo/run', headers=operator)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['cases'], 200)
                self.assertEqual(client.get('/cases', headers=mobile).json(), [])
                pending = client.get('/review', headers=reviewer).json()
                case_id = pending[0]['id']
                decision = {'approve': True, 'note': 'Revisión humana de prueba'}
                self.assertEqual(client.post(f'/review/{case_id}', headers=mobile, json=decision).status_code, 403)
                self.assertEqual(client.post(f'/review/{case_id}', headers=reviewer, json=decision).status_code, 200)
                self.assertEqual(client.post(f'/review/{case_id}', headers=reviewer, json=decision).status_code, 409)
                self.assertEqual(len(client.get('/cases', headers=mobile).json()), 1)
                self.assertEqual(len(client.get(f'/cases/{case_id}/history', headers=mobile).json()), 1)
                self.assertEqual(client.get(f'/cases/{pending[1]["id"]}/history', headers=mobile).status_code, 404)

if __name__ == '__main__': unittest.main()
