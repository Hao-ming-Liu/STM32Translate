import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import time
import threading

import pytest

from stm32translate.controller import WorkerClient


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'models' / 'en_zh'


@pytest.mark.skipif(not (MODEL / 'model/model.bin').exists(), reason='download model first')
def test_real_worker_translates_uppercase_english_offline():
    sources = ['PRESENT', 'THE DEVICE IS PRESENT.', 'ENABLE THE TIMER']
    env = dict(os.environ, STM32_TRANSLATE_OFFLINE_TEST='1', PYTHONUTF8='1')
    p = subprocess.run([sys.executable, str(ROOT / 'run.py'), '--worker', '--model', str(MODEL)],
                       input=''.join(json.dumps({'id': i, 'text': s}) + '\n' for i, s in enumerate(sources)),
                       text=True, encoding='utf8', capture_output=True, env=env, timeout=40)
    assert p.returncode == 0, p.stderr
    results = [json.loads(line) for line in p.stdout.splitlines()]
    assert len(results) == len(sources)
    for i, result in enumerate(results):
        assert result['id'] == i and not result.get('error') and not result['warnings']
        assert any('\u4e00' <= c <= '\u9fff' for c in result['text'])
        assert result['network_blocked']


@pytest.mark.skipif(not (MODEL / 'model/model.bin').exists(), reason='download model first')
def test_real_worker_translates_with_network_blocked():
    env = dict(os.environ, STM32_TRANSLATE_OFFLINE_TEST='1', PYTHONUTF8='1')
    p = subprocess.run([sys.executable, str(ROOT / 'run.py'), '--worker', '--model', str(MODEL)],
                       input=json.dumps({'id': 7, 'text': '@param[in] GPIOx Select the GPIO peripheral.'}) + '\n',
                       text=True, encoding='utf8', capture_output=True, env=env, timeout=40)
    assert p.returncode == 0, p.stderr
    result = json.loads(p.stdout)
    assert result['id'] == 7 and not result.get('error')
    assert '@param[in] GPIOx ' in result['text']
    assert 'GPIO' in result['text']
    assert any('\u4e00' <= c <= '\u9fff' for c in result['text'])
    assert result['network_blocked'] is True


def test_worker_rejects_over_limit_instead_of_truncating():
    p = subprocess.run([sys.executable, str(ROOT / 'run.py'), '--worker', '--model', str(MODEL)],
                       input=json.dumps({'id': 9, 'text': 'x' * 30001}) + '\n',
                       text=True, encoding='utf8', capture_output=True, timeout=20)
    result = json.loads(p.stdout)
    assert result['id'] == 9
    assert '30000' in result['error']


def wait_for(events, request_id, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = events.get(timeout=max(.01, deadline-time.monotonic()))
        if event.get('id') == request_id:
            return event
    raise AssertionError('worker response timed out')


@pytest.mark.skipif(not (MODEL / 'model/model.bin').exists(), reason='download model first')
def test_idle_release_and_restart_after_crash():
    events = queue.Queue()
    client = WorkerClient(MODEL, events, idle_seconds=.3)
    try:
        client.submit(1, 'Enable the timer.')
        assert not wait_for(events, 1).get('error')
        first_pid = client.pid
        assert first_pid
        deadline = time.monotonic() + 5
        while client.pid and time.monotonic() < deadline:
            time.sleep(.05)
        assert client.pid is None
        client.submit(2, 'Disable the interrupt.')
        assert not wait_for(events, 2).get('error')
        assert client.pid != first_pid
        client.process.kill()
        client.process.wait(timeout=5)
        client.submit(3, 'Clear the flag.')
        assert not wait_for(events, 3).get('error')
    finally:
        client.close()
    assert client.pid is None


def test_missing_model_is_an_actionable_error_and_not_a_hang(tmp_path):
    events = queue.Queue()
    client = WorkerClient(tmp_path, events)
    try:
        client.submit(12, 'Enable the timer.')
        result = wait_for(events, 12, timeout=20)
        assert '模型' in result['error']
    finally:
        client.close()


def test_blocked_input_pipe_is_covered_by_timeout():
    events = queue.Queue()
    command = [sys.executable, '-u', '-c', 'import time; time.sleep(60)']
    client = WorkerClient(MODEL, events, command=command, response_timeout=.3)
    try:
        client.submit(80, 'A' * 30000)
        result = wait_for(events, 80, timeout=3)
        assert '超时' in result['error']
        assert client.pid is None
    finally:
        client.close()


def test_closing_during_startup_cannot_spawn_an_orphan():
    events = queue.Queue()
    client = WorkerClient(MODEL, events, command=[sys.executable, '-u', '-c', 'import time; time.sleep(60)'])
    entered, resume = threading.Event(), threading.Event()
    start = client._start
    def delayed():
        entered.set()
        resume.wait(10)
        start()
    client._start = delayed
    client.submit(81, 'Enable the timer.')
    assert entered.wait(2)
    closer = threading.Thread(target=client.close)
    closer.start()
    closer.join(6)
    resume.set()
    client.thread.join(2)
    try:
        assert not client.thread.is_alive()
        assert client.pid is None
    finally:
        client.close()
