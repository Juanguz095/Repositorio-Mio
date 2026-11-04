"""Run one real Android instrumentation test against a disposable synthetic API.
Requires the debug APK, debug test APK and a dedicated running emulator.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import httpx
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.pipeline import synthetic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', default='emulator-5554')
    parser.add_argument('--sdk', default=os.getenv('ANDROID_HOME', '/workspace/toolchains/android-sdk'))
    parser.add_argument('--boot-timeout', type=int, default=900)
    parser.add_argument('--output')
    args = parser.parse_args()
    adb_command = [str(Path(args.sdk, 'platform-tools/adb')), '-s', args.serial]
    operator, reviewer, mobile = [secrets.token_urlsafe(24) for _ in range(3)]
    tokens = [operator, reviewer, mobile]

    def redact(text):
        for token in tokens: text = text.replace(token, '[redacted]')
        return text

    def adb(*arguments, timeout=120):
        try:
            result = subprocess.run([*adb_command, *arguments], capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError('ADB command timed out') from None
        if result.returncode:
            raise RuntimeError('ADB failed: '+redact(result.stderr.decode(errors='replace'))[-1000:])
        return result.stdout.decode(errors='replace').strip()

    deadline = time.monotonic()+args.boot_timeout
    last_progress = 0
    while time.monotonic() < deadline:
        try:
            if adb('shell', 'getprop', 'sys.boot_completed', timeout=10) == '1': break
        except RuntimeError: pass
        if time.monotonic()-last_progress > 30:
            print('Waiting for Android boot...', flush=True); last_progress = time.monotonic()
        time.sleep(2)
    else: raise RuntimeError('Android did not boot within the configured deadline')
    for path in ['android/app/build/outputs/apk/debug/app-debug.apk',
                 'android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk']:
        apk = ROOT/path
        if not apk.is_file(): raise RuntimeError('Build :app:assembleDebug and :app:assembleDebugAndroidTest first')
        adb('install', '-r', str(apk), timeout=180)
    for setting in ['window_animation_scale','transition_animation_scale','animator_duration_scale']:
        adb('shell','settings','put','global',setting,'0')
    adb('shell','input','keyevent','82')
    print('Android ready; test APK installed', flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update(OPERATOR_TOKEN=operator, REVIEWER_TOKEN=reviewer, MOBILE_TOKEN=mobile,
                   TUTORIA_DB=tmp+'/cases.db', TUTORIA_DATA=tmp, TUTORIA_AGENT_MODE='rules')
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.api:app', '--host','127.0.0.1','--port',str(port)],
                                  env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=30) as client:
                for _ in range(100):
                    try:
                        if client.get('/health').status_code == 200: break
                    except httpx.TransportError: pass
                    time.sleep(.1)
                else: raise RuntimeError('Disposable API did not start')
                history = synthetic()
                students = synthetic(seed=43).iloc[:3].drop(columns='deserto').copy()
                students['periodo'] = 20242
                students['alumno_id'] = ['SYN-UI-001','SYN-UI-002','SYN-UI-003']
                result = client.post('/ingest/records', headers={'Authorization':'Bearer '+operator}, json={
                    'import_id':'android-ui-smoke','history':json.loads(history.to_json(orient='records')),
                    'students':json.loads(students.to_json(orient='records'))})
                assert result.status_code == 200, 'Synthetic API import failed'
                adb('reverse',f'tcp:{port}',f'tcp:{port}')
                test = adb('shell','am','instrument','-w','-r',
                    '-e','class','pe.unmsm.tutoria.ApprovalFlowTest',
                    '-e','baseUrl',f'http://127.0.0.1:{port}',
                    '-e','mobileToken',mobile,'-e','reviewerToken',reviewer,
                    'pe.unmsm.tutoria.test/androidx.test.runner.AndroidJUnitRunner',timeout=600)
                test = redact(test)
                print(test, flush=True)
                assert 'OK (1 test)' in test and 'INSTRUMENTATION_CODE: -1' in test and 'FAILURES!!!' not in test, 'Android instrumentation did not pass one test'
                output=Path(args.output) if args.output else ROOT/'data/processed'/('android-ui-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
                output.mkdir(parents=True,exist_ok=False)
                remote='/sdcard/Android/data/pe.unmsm.tutoria/files/'
                adb('pull',remote+'tutoria-smoke.png',str(output/'screen.png'))
                adb('pull',remote+'tutoria-smoke.xml',str(output/'hierarchy.xml'))
                xml=redact((output/'hierarchy.xml').read_text())
                (output/'hierarchy.xml').write_text(xml)
                (output/'instrumentation.txt').write_text(test)
                (output/'report.json').write_text(json.dumps({'status':'passed','instrumented_tests':1,
                    'api_level':adb('shell','getprop','ro.build.version.sdk'),
                    'checks':['pending_hidden','approved_only','risk_ordering','rejected_hidden','academic_detail','enrollment','payments','review_history'],
                    'data_kind':'synthetic','transport':'adb_reverse'},indent=2))
                print('PASS: Android UI approval flow; evidence:',output,flush=True)
        finally:
            try: adb('reverse','--remove',f'tcp:{port}')
            except RuntimeError: pass
            server.terminate()
            try: server.wait(timeout=10)
            except subprocess.TimeoutExpired: server.kill(); server.wait()


if __name__=='__main__': main()
