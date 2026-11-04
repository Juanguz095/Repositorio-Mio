"""Real n8n -> API -> human approval -> mobile smoke test in disposable Docker containers.
Run from the repository root with .venv/bin/python scripts/smoke_n8n.py.
Requires images tutoria-demo:local and n8nio/n8n:1.123.0 already available.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import synthetic
from scripts.make_source_demo import create as create_source

DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
REDACT = []


def docker(*args, stdin=None):
    result = subprocess.run([*DOCKER, *args], input=stdin, text=True, capture_output=True)
    if result.returncode:
        # Docker error messages never include our generated credential file.
        output = result.stderr + result.stdout
        for token in REDACT:
            output = output.replace(token, '[redacted]')
        raise RuntimeError(output[-3000:])
    return result.stdout.strip()


def port(container, target):
    return docker('port', container, target).rsplit(':', 1)[1]


def wait(client, path):
    for _ in range(180):
        try:
            if client.get(path).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(1)
    raise RuntimeError('Service did not become healthy')


def main():
    suffix = secrets.token_hex(5)
    network, api, n8n = ['tutoria-smoke-'+suffix+x for x in ('-net', '-api', '-n8n')]
    operator, reviewer, mobile, webhook, form_password = [secrets.token_urlsafe(32) for _ in range(5)]
    REDACT.extend([operator, reviewer, mobile, webhook, form_password])
    auth = lambda token: {'Authorization': 'Bearer '+token}
    containers = []
    network_created = False
    try:
        docker('network', 'create', network)
        network_created = True
        env = os.environ.copy()
        env.update(OPERATOR_TOKEN=operator, REVIEWER_TOKEN=reviewer, MOBILE_TOKEN=mobile)
        # --env NAME reads the subprocess environment and keeps token values out of argv.
        subprocess.run([*DOCKER, 'run', '-d', '--name', api, '--network', network,
            '--network-alias', 'api', '-p', '127.0.0.1::8000',
            '-e', 'OPERATOR_TOKEN', '-e', 'REVIEWER_TOKEN', '-e', 'MOBILE_TOKEN',
            'tutoria-demo:local'], env=env, check=True, capture_output=True)
        containers.append(api)
        docker('run', '-d', '--name', n8n, '--network', network, '-p', '127.0.0.1::5678',
            '-e', 'NO_PROXY=localhost,127.0.0.1,api', '-e', 'no_proxy=localhost,127.0.0.1,api', '-e', 'N8N_DIAGNOSTICS_ENABLED=false',
            '-e', 'N8N_VERSION_NOTIFICATIONS_ENABLED=false', '-e', 'N8N_TEMPLATES_ENABLED=false',
            '-e', 'N8N_SECURE_COOKIE=false', '--entrypoint', '/bin/sh', 'n8nio/n8n:1.123.0', '-c', 'sleep 1800')
        containers.append(n8n)
        credentials = [
            {'id': 'smoke-operator', 'name': 'Smoke operator', 'type': 'httpHeaderAuth',
             'data': {'name': 'Authorization', 'value': 'Bearer '+operator}},
            {'id': 'smoke-form', 'name': 'Smoke form', 'type': 'httpBasicAuth',
             'data': {'user': 'demo-form', 'password': form_password}},
            {'id': 'smoke-hook', 'name': 'Smoke webhook', 'type': 'httpHeaderAuth',
             'data': {'name': 'Authorization', 'value': 'Bearer '+webhook}},
        ]
        docker('exec', '-i', n8n, 'sh', '-c',
               'umask 077; cat > /tmp/credentials.json; n8n import:credentials --input=/tmp/credentials.json; status=$?; rm -f /tmp/credentials.json; exit "$status"',
               stdin=json.dumps(credentials))
        workflows = []
        for source in ['records', 'excel', 'sqlite', 'forms-run', 'form']:
            workflow = json.loads(Path('n8n', source+'.json').read_text())
            workflow['settings']['saveDataErrorExecution'] = 'all'
            for node in workflow['nodes']:
                if node['type'] == 'n8n-nodes-base.webhook':
                    if node['parameters']['authentication'] == 'basicAuth':
                        node['credentials'] = {'httpBasicAuth': {'id': 'smoke-form', 'name': 'Smoke form'}}
                    else:
                        node['credentials'] = {'httpHeaderAuth': {'id': 'smoke-hook', 'name': 'Smoke webhook'}}
                elif node['type'] == 'n8n-nodes-base.httpRequest':
                    node['credentials'] = {'httpHeaderAuth': {'id': 'smoke-operator', 'name': 'Smoke operator'}}
            workflows.append(workflow)
        docker('exec', '-d', n8n, 'n8n', 'start')
        with httpx.Client(base_url='http://127.0.0.1:'+port(api, '8000'), trust_env=False, timeout=120) as backend, \
             httpx.Client(base_url='http://127.0.0.1:'+port(n8n, '5678'), trust_env=False, timeout=120) as workflow:
            wait(backend, '/health')
            wait(workflow, '/rest/settings')
            # Use n8n's normal editor API to create version history and publish.
            # Its legacy import/update CLI omits the history required for activation.
            password = 'Smoke-Aa1!'+secrets.token_urlsafe(24)
            REDACT.append(password)
            setup = workflow.post('/rest/owner/setup', json={
                'email': 'smoke@example.invalid', 'firstName': 'Local', 'lastName': 'Smoke', 'password': password})
            assert setup.status_code == 200, 'n8n owner setup failed: '+str(setup.status_code)
            for definition in workflows:
                created = workflow.post('/rest/workflows', json=definition)
                assert created.status_code == 200, created.text
                saved = created.json()['data']
                activated = workflow.post('/rest/workflows/'+saved['id']+'/activate', json={'versionId': saved['versionId']})
                assert activated.status_code == 200, activated.text
            history = synthetic()
            students = history.iloc[:5].drop(columns='deserto').copy()
            students['periodo'] = 20242
            payload = {'import_id': 'n8n-records-smoke', 'history': json.loads(history.to_json(orient='records')),
                       'students': json.loads(students.to_json(orient='records'))}
            denied = workflow.post('/webhook/tutoria-records', json=payload)
            assert denied.status_code in (401, 403), denied.text
            result = workflow.post('/webhook/tutoria-records', json=payload, headers=auth(webhook))
            assert result.status_code == 200, result.text
            if not result.content:
                listing = workflow.get('/rest/executions', params={'limit': 5}).json()
                evidence = []
                for execution in listing.get('data', {}).get('results', []):
                    details = workflow.get('/rest/executions/'+str(execution['id'])).json()['data']
                    encoded = details.get('data')
                    if isinstance(encoded, str):
                        table = json.loads(encoded)
                        cache = {}
                        def resolve(index):
                            if index in cache: return cache[index]
                            value = table[index]
                            if isinstance(value, str): return value
                            target = {} if isinstance(value, dict) else []
                            cache[index] = target
                            def item(v): return resolve(int(v)) if isinstance(v, str) else v
                            if isinstance(value, dict): target.update({k: item(v) for k,v in value.items()})
                            else: target.extend(item(v) for v in value)
                            return target
                        state = resolve(0)
                    else:
                        state = encoded or {}
                    error = state.get('resultData', {}).get('error', {})
                    evidence.append({key: error.get(key) for key in ['name', 'message', 'messages', 'httpCode']})
                output = json.dumps(evidence)
                for token in REDACT:
                    output = output.replace(token, '[redacted]')
                raise RuntimeError('Empty webhook response; execution errors: '+output[-5000:])
            report = result.json()
            assert report['cases'] == 5 and report['status'] == 'pending', report
            assert workflow.post('/webhook/tutoria-records', json=payload, headers=auth(webhook)).json() == report
            assert backend.get('/cases', headers=auth(mobile)).json() == []
            pending = backend.get('/review', headers=auth(reviewer)).json()
            assert len(pending) == 5
            case_id = pending[0]['id']
            assert backend.post(f'/review/{case_id}', json={'approve': True, 'note': 'Validación de integración'}, headers=auth(reviewer)).status_code == 200
            assert len(backend.get('/cases', headers=auth(mobile)).json()) == 1
            assert backend.get(f'/cases/{case_id}', headers=auth(mobile)).json()['academic']['periodo'] == 20242
            assert len(backend.get(f'/cases/{case_id}/history', headers=auth(mobile)).json()) == 1
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp, 'raw'); raw.mkdir(); raw.chmod(0o755)
                history.to_excel(raw/'history.xlsx', index=False)
                students.to_excel(raw/'students.xlsx', index=False)
                create_source(raw/'source-demo.db')
                for example in raw.iterdir(): example.chmod(0o644)
                docker('cp', str(raw), api+':/app/data/raw')
            excel = workflow.post('/webhook/tutoria-excel', headers=auth(webhook), json={
                'import_id': 'n8n-excel-smoke', 'history_path': 'history.xlsx', 'students_path': 'students.xlsx'})
            assert excel.status_code == 200, excel.text
            assert excel.json()['cases'] == 5, excel.text
            sql = workflow.post('/webhook/tutoria-sqlite', headers=auth(webhook), json={'import_id': 'sqlite-smoke'})
            assert sql.status_code == 200, sql.text
            assert sql.json()['cases'] == 30, sql.text
            basic = ('demo-form', form_password)
            assert workflow.get('/webhook/tutoria-form').status_code in (401, 403)
            page = workflow.get('/webhook/tutoria-form', auth=basic)
            assert page.status_code == 200 and 'pagos_al_dia' in page.text, page.text
            data = {'event_id': 'form-smoke-1', 'alumno_id': 'SYN-FORM-900', 'periodo': '20242',
                    'asistencia': '0.8', 'promedio': '14', 'creditos_aprobados': '18', 'matriculado': '1', 'pagos_al_dia': '0'}
            capture = workflow.post('/webhook/tutoria-form', auth=basic, data=data)
            assert capture.status_code == 200, capture.text
            assert capture.json()['status'] == 'captured', capture.text
            assert workflow.post('/webhook/tutoria-form', auth=basic, data=data).json() == capture.json()
            invalid = dict(data, event_id='form-invalid', pagos_al_dia='2')
            assert workflow.post('/webhook/tutoria-form', auth=basic, data=invalid).status_code == 422
            forms = workflow.post('/webhook/tutoria-forms-run', headers=auth(webhook), json={'import_id': 'form-cohort-smoke', 'periodo': 20242})
            assert forms.status_code == 200, forms.text
            assert forms.json()['cases'] == 1, forms.text
            invalid_import = workflow.post('/webhook/tutoria-records', headers=auth(webhook), json={'import_id':'bad', 'history':[], 'students':[]})
            assert invalid_import.status_code == 422, invalid_import.text
            print('PASS: n8n JSON + Excel + SQLite + authenticated HTML form, error propagation, idempotency, approval, mobile detail/history')
    finally:
        for container in reversed(containers):
            docker('rm', '-f', '-v', container)
        if network_created:
            docker('network', 'rm', network)


if __name__ == '__main__':
    main()
