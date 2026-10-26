"""Extract the release ZIP and smoke-test its runtime without system Python paths."""
from pathlib import Path
import hashlib
import argparse
import json
import os
import subprocess
import tempfile
import time
import zipfile

import psutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist-dir', default='dist')
    parser.add_argument('--skip-gui', action='store_true', help='preserve an existing user instance; verify extracted worker only')
    args = parser.parse_args()
    archive = ROOT / args.dist_dir / 'STM32Translate-1.0.2-win64-full.zip'
    env = dict(os.environ, PATH=os.environ.get('SystemRoot', r'C:\Windows') + '\\System32',
               STM32_TRANSLATE_OFFLINE_TEST='1')
    for name in ('PYTHONPATH', 'PYTHONHOME', 'TCL_LIBRARY', 'TK_LIBRARY', 'VIRTUAL_ENV'):
        env.pop(name, None)
    with tempfile.TemporaryDirectory(prefix='portable-smoke-', dir=ROOT / 'build') as tmp:
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None, 'ZIP CRC failure'
            names = z.namelist()
            assert not any('/data/' in name or '/.venv/' in name for name in names)
            z.extractall(tmp)
        folder = Path(tmp) / 'STM32Translate'
        for name in ('STM32Translate.exe', 'TranslateWorker.exe', '_internal/python312.dll',
                     'README.md', 'THIRD_PARTY_NOTICES.md', 'MODEL_INFO.json', 'licenses'):
            assert (folder / name).exists(), name
        model = folder / 'models/en_zh'
        for name, expected in json.loads((model / 'SOURCE.json').read_text(encoding='utf8'))['files_sha256'].items():
            with (model / name).open('rb') as f:
                assert hashlib.file_digest(f, 'sha256').hexdigest() == expected, name
        sources = ['The prescaler value must be between 0 and 65535.', 'PRESENT', 'THE DEVICE IS PRESENT.', 'ENABLE THE TIMER', 'Set TIM_Prescaler to 50.']
        worker = subprocess.run([str(folder / 'TranslateWorker.exe'), '--worker'], cwd=folder, env=env,
                                input=''.join(json.dumps({'id':i, 'text':s})+'\n' for i,s in enumerate(sources)),
                                capture_output=True, text=True, encoding='utf8', timeout=45,
                                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        results = [json.loads(line) for line in worker.stdout.splitlines()]
        assert len(results) == len(sources)
        for i, result in enumerate(results):
            assert result['id'] == i and result['network_blocked'] and not result.get('error') and not result['warnings'], result
            assert any('\u4e00' <= c <= '\u9fff' for c in result['text']), result
        assert '0' in results[0]['text'] and '65535' in results[0]['text'], results[0]
        colored = results[-1]
        assert '50' in colored['text'] and colored['highlights'], colored
        for start, end in colored['highlights']:
            assert 0 <= start < end <= len(colored['text'])
            assert colored['text'][start:end] != '50'
        if args.skip_gui:
            report = {'version':'1.0.2', 'archive_crc':'pass', 'model_hashes':'pass',
                      'extracted_worker_results':results,
                      'gui_startup':'skipped explicitly to preserve the running user instance'}
            (ROOT / 'docs/archive-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        start = time.perf_counter()
        gui = subprocess.Popen([str(folder / 'STM32Translate.exe')], cwd=folder, env=env, startupinfo=startup)
        try:
            database = folder / 'data/translator.db'
            while not database.exists() and time.perf_counter()-start < 15:
                assert gui.poll() is None, 'GUI exited during startup'
                time.sleep(.05)
            assert database.exists(), 'GUI did not initialize its store'
            store_ready_seconds = time.perf_counter()-start
            time.sleep(2)
            assert gui.poll() is None
            process = psutil.Process(gui.pid)
            modules = [m.path for m in process.memory_maps() if any(n in m.path.lower() for n in ('python312', 'tcl86', 'tk86'))]
            assert any('tk86' in m.lower() for m in modules), modules
            assert all(str(folder).lower() in m.lower() for m in modules), modules
            assert not process.children(), 'Idle GUI unexpectedly loaded a worker'
            report = {'version':'1.0.2', 'archive_crc':'pass', 'model_hashes':'pass', 'extracted_worker_results':results,
                      'gui_store_ready_seconds':store_ready_seconds,
                      'gui_idle_rss_mib':process.memory_info().rss/1048576, 'gui_modules':[str(Path(m).relative_to(folder)) for m in modules],
                      'note':'Hidden GUI startup smoke test; store-ready time is not time to first paint.'}
        finally:
            if gui.poll() is None:
                gui.terminate()
            gui.wait(timeout=10)
        (ROOT / 'docs/archive-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
