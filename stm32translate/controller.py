"""Request identity and restartable, lazy worker process management."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


class RequestState:
    def __init__(self):
        self.current_id = 0
        self.source = ''

    def begin(self, source: str) -> int:
        self.current_id += 1
        self.source = source
        return self.current_id

    def accept(self, request_id: int) -> bool:
        return request_id == self.current_id

    def invalidate(self):
        self.current_id += 1


class WorkerClient:
    """One active job, one replaceable pending job, restartable lazy engine."""
    def __init__(self, model_dir: Path, events: queue.Queue, idle_seconds: float = 300,
                 command: list[str] | None = None, response_timeout: float = 120):
        self.model_dir, self.events = Path(model_dir), events
        self.idle_seconds, self.timeout = idle_seconds, response_timeout
        self.process = None
        self._responses = self._reader = self._writer = None
        self._process_lock = threading.Lock()
        self._jobs = queue.Queue(maxsize=1)
        self._closed = threading.Event()
        self.last_used = time.monotonic()
        if command is not None:
            self.command = command
        elif getattr(sys, 'frozen', False):
            self.command = [str(Path(sys.executable).with_name('TranslateWorker.exe')), '--worker']
        else:
            self.command = [sys.executable, '-u', str(Path(__file__).resolve().parents[1] / 'run.py'), '--worker']
        self.thread = threading.Thread(target=self._loop, name='translation-supervisor', daemon=True)
        self.thread.start()

    @property
    def pid(self):
        p = self.process
        return p.pid if p is not None and p.poll() is None else None

    def submit(self, request_id: int, text: str):
        if self._closed.is_set():
            return
        try:
            self._jobs.get_nowait()
        except queue.Empty:
            pass
        self._jobs.put_nowait((request_id, text))

    def _start(self):
        if self._closed.is_set():
            return
        if self.process is not None and self.process.poll() is None:
            return
        self._stop()
        with self._process_lock:
            if self._closed.is_set():
                return
            self.process = subprocess.Popen(
                self.command + ['--model', str(self.model_dir)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf8',
                bufsize=1, env=dict(os.environ, PYTHONUTF8='1', PYTHONUNBUFFERED='1'),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
        responses = self._responses = queue.Queue()
        proc = self.process
        def read():
            try:
                for line in proc.stdout:
                    try:
                        responses.put(json.loads(line))
                    except ValueError:
                        responses.put({'_exit': '翻译引擎返回了无法识别的数据，请重试。'})
            except (ValueError, OSError):
                pass
            finally:
                responses.put({'_exit': '翻译引擎已退出，请重试；下一次查询会自动重新启动。'})
        self._reader = threading.Thread(target=read, name='translation-reader', daemon=True)
        self._reader.start()

    def _stop(self):
        with self._process_lock:
            p, self.process = self.process, None
        if p is None:
            return
        try:
            if p.poll() is None:
                p.terminate()
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=2)
        finally:
            if self._writer is not None:
                self._writer.join(timeout=.5)
            if self._reader is not None and self._reader is not threading.current_thread():
                self._reader.join(timeout=.5)
            for pipe in (p.stdin, p.stdout):
                if pipe:
                    try:
                        pipe.close()
                    except OSError:
                        pass

    def _loop(self):
        try:
            while not self._closed.is_set():
                try:
                    job = self._jobs.get(timeout=.1)
                except queue.Empty:
                    if self.process and time.monotonic() - self.last_used >= self.idle_seconds:
                        self._stop()
                        self.events.put({'kind': 'idle'})
                    continue
                if job is None or self._closed.is_set():
                    break
                request_id, text = job
                try:
                    deadline = time.monotonic() + self.timeout
                    self._start()
                    if self._closed.is_set():
                        break
                    proc, responses = self.process, self._responses
                    payload = json.dumps({'id': request_id, 'text': text}, ensure_ascii=False) + '\n'
                    def send(proc=proc, responses=responses, payload=payload):
                        try:
                            proc.stdin.write(payload)
                            proc.stdin.flush()
                        except (OSError, ValueError) as exc:
                            responses.put({'_exit': '无法向翻译引擎发送文本：' + str(exc)})
                    self._writer = threading.Thread(target=send, name='translation-writer', daemon=True)
                    self._writer.start()
                    response = responses.get(timeout=max(.001, deadline-time.monotonic()))
                    if '_exit' in response:
                        raise RuntimeError(response['_exit'])
                    if response.get('id') != request_id:
                        raise RuntimeError('翻译引擎请求序号不匹配，请重试。')
                    self.events.put(response)
                except queue.Empty:
                    self._stop()
                    self.events.put({'id': request_id, 'error': '翻译超时，已释放引擎。请减少单次输入后重试。'})
                except Exception as exc:
                    self._stop()
                    self.events.put({'id': request_id, 'error': str(exc)})
                finally:
                    self.last_used = time.monotonic()
        finally:
            self._stop()

    def close(self):
        self._closed.set()
        with self._process_lock:
            p = self.process
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        try:
            self._jobs.get_nowait()
        except queue.Empty:
            pass
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        self.thread.join(timeout=5)
