"""Exercise the real bundled worker, with Python socket access disabled in it."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import queue
import statistics
import subprocess
import sys
import threading
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--idle-seconds', type=float, default=300)
    args = parser.parse_args()
    folder = ROOT / 'dist/STM32Translate'
    worker = folder / 'TranslateWorker.exe'
    cases = json.loads((ROOT / 'tests/fixtures/stm32_comments.json').read_text(encoding='utf8'))
    env = dict(os.environ, STM32_TRANSLATE_OFFLINE_TEST='1', PYTHONUTF8='1', PATH=os.environ.get('SystemRoot', r'C:\Windows') + '\\System32')
    for key in ('PYTHONPATH', 'PYTHONHOME', 'TCL_LIBRARY', 'TK_LIBRARY', 'VIRTUAL_ENV'):
        env.pop(key, None)
    p = subprocess.Popen([str(worker), '--worker'], cwd=folder, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding='utf8', env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    rss = []
    stop = threading.Event()
    def sample():
        while not stop.wait(.02):
            try:
                rss.append(psutil.Process(p.pid).memory_info().rss)
            except psutil.NoSuchProcess:
                break
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    report = []
    try:
        for i, case in enumerate(cases):
            start = time.perf_counter()
            p.stdin.write(json.dumps({'id':i, 'text':case['source']}, ensure_ascii=False) + '\n')
            p.stdin.flush()
            line = p.stdout.readline()
            if not line:
                raise RuntimeError('Worker exited: ' + p.stderr.read())
            result = json.loads(line)
            assert not result.get('error'), result
            assert result['network_blocked']
            missing = [token for token in case['keep'] if token not in result['text']]
            assert not missing, (case, result, missing)
            assert any('\u4e00' <= c <= '\u9fff' for c in result['text']) or (result['warnings'] and result['text'] == case['source']), result
            report.append(dict(case, result=result['text'], warnings=result['warnings'], wall_seconds=time.perf_counter()-start))
        runtime_modules = [m.path for m in psutil.Process(p.pid).memory_maps() if any(name in m.path.lower() for name in ('python312', 'tcl86', 'tk86', 'ctranslate2'))]
        print('Completed', len(report), 'translation cases; protection fallbacks:', sum(bool(r['warnings']) for r in report), flush=True)
        p.stdin.close()
        assert p.wait(timeout=20) == 0
    finally:
        stop.set()
        if p.poll() is None:
            p.kill()
        sampler.join()
    from stm32translate.controller import WorkerClient
    events = queue.Queue()
    client = WorkerClient(folder / 'models/en_zh', events, idle_seconds=args.idle_seconds, command=[str(worker), '--worker'])
    try:
        client.submit(100, 'Enable the timer.')
        response = events.get(timeout=30)
        assert not response.get('error'), response
        engine_pid = client.pid
        started = time.monotonic()
        (ROOT / 'docs/translation-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print('Measuring idle release for', args.idle_seconds, 'seconds...', flush=True)
        event = events.get(timeout=args.idle_seconds+15)
        assert event.get('kind') == 'idle' and client.pid is None
        idle_elapsed = time.monotonic()-started
    finally:
        client.close()
    archive = ROOT / 'dist/STM32Translate-1.0.1-win64-full.zip'
    summary = {
        'os':sys.getwindowsversion().build,
        'network_test':'Python socket connection and DNS APIs disabled inside worker; PATH contains only Windows System32; no system network adapters changed.',
        'case_count':len(report), 'cold_seconds':report[0]['wall_seconds'],
        'warm_median_seconds':statistics.median(r['wall_seconds'] for r in report[1:]),
        'worker_peak_rss_mib':max(rss)/1048576,
        'idle_seconds_configured':args.idle_seconds, 'idle_release_measured_seconds':idle_elapsed,
        'released_engine_pid':engine_pid,
        'runtime_modules':runtime_modules,
        'zip_mib':archive.stat().st_size/1048576,
        'folder_mib':sum(f.stat().st_size for f in folder.rglob('*') if f.is_file() and 'data' not in f.relative_to(folder).parts)/1048576,
        'zip_sha256':hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest(),
        'cases':report,
    }
    (ROOT / 'docs/benchmark.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in summary.items() if k!='cases'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
