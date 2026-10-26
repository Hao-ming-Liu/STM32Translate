"""JSON-lines stdin/stdout-only worker. No network clients or downloads."""
import json
from pathlib import Path
import os
import sys
import time
from stm32translate.documents import translate_document


def main(model_dir: Path):
    blocked = os.environ.get('STM32_TRANSLATE_OFFLINE_TEST') == '1'
    if blocked:
        import socket
        def deny(*args, **kwargs):
            raise OSError('Network disabled for offline verification')
        socket.socket.connect = deny
        socket.socket.connect_ex = deny
        socket.create_connection = deny
        socket.getaddrinfo = deny
    translator = None
    def translate_batch(parts):
        nonlocal translator
        if translator is None:
            from vendor.argos_core import OfflineTranslator
            translator = OfflineTranslator(model_dir)
        return translator.translate_batch(parts)
    for line in sys.stdin:
        request_id = None
        started = time.perf_counter()
        try:
            request = json.loads(line)
            request_id = request.get('id')
            text = request['text']
            if not isinstance(text, str):
                raise ValueError('只支持文本内容')
            if len(text) > 30000:
                raise ValueError('单次输入最多 30000 字符，请拆分后翻译；原文未被截断。')
            result = translate_document(text, translate_batch)
            response = {'id': request_id, 'text': result.text, 'warnings': result.warnings,
                        'highlights': result.highlights,
                        'elapsed': time.perf_counter() - started, 'pid': os.getpid(), 'network_blocked': blocked}
        except Exception as exc:
            response = {'id': request_id, 'error': str(exc), 'elapsed': time.perf_counter() - started}
        print(json.dumps(response, ensure_ascii=False), flush=True)
