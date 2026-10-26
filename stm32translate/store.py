"""Local-only terminology, settings and bounded translation cache."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3


DEFAULT_TERMS = {
    'GPIO': '通用输入/输出', 'DMA': '直接存储器访问', 'ADC': '模数转换器',
    'PWM': '脉冲宽度调制', 'NVIC': '嵌套向量中断控制器', 'RCC': '复位和时钟控制',
    'EXTI': '外部中断/事件控制器', 'UART': '通用异步收发器', 'USART': '通用同步/异步收发器',
    'SPI': '串行外设接口', 'I2C': '两线串行总线（集成电路互连总线）',
    'peripheral': '外设', 'pin': '引脚', 'pull-up': '上拉', 'pull-down': '下拉',
    'pull-up resistor': '上拉电阻', 'prescaler': '预分频器', 'timer': '定时器',
    'counter': '计数器', 'interrupt': '中断', 'interrupt priority': '中断优先级',
    'pending flag': '挂起标志位（待处理标志位）', 'update interrupt': '更新中断',
    'duty cycle': '占空比', 'square wave': '方波', 'reset': '复位', 'handle': '句柄',
    'transfer': '传输', 'buffer': '缓冲区', 'conversion': '转换', 'flag': '标志位',
    'input': '输入', 'output': '输出', 'clock': '时钟', 'timeout': '超时',
    'register': '寄存器', 'bit': '位', 'circular mode': '循环模式', 'memory': '存储器',
    'polling': '轮询', 'callback': '回调', 'baud rate': '波特率',
}


class Store:
    def __init__(self, path: Path, cache_limit: int = 2000):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.limit = cache_limit
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS terms (
                key TEXT PRIMARY KEY, term TEXT NOT NULL, meaning TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL, result TEXT NOT NULL, warnings TEXT NOT NULL
            );
        ''')
        if 'highlights' not in {row[1] for row in self.db.execute('PRAGMA table_info(cache)')}:
            self.db.execute("ALTER TABLE cache ADD COLUMN highlights TEXT NOT NULL DEFAULT '[]'")
            self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.db.close()

    def seed_defaults(self):
        if self.get_setting('default_terms_seeded', False):
            return
        with self.db:
            self.db.executemany('INSERT OR IGNORE INTO terms VALUES (?,?,?)',
                                [(self._term_key(k), k, v) for k, v in DEFAULT_TERMS.items()])
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('default_terms_seeded', 'true'))

    @staticmethod
    def _term_key(term: str) -> str:
        return ' '.join(term.strip().split()).casefold()

    def save_term(self, term: str, meaning: str):
        term, meaning = ' '.join(term.strip().split()), meaning.strip()
        if not term or not meaning:
            raise ValueError('英文术语和中文释义都不能为空')
        if len(term) > 120 or len(meaning) > 2000:
            raise ValueError('术语最多 120 字符，释义最多 2000 字符')
        with self.db:
            self.db.execute('INSERT INTO terms VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET term=excluded.term, meaning=excluded.meaning',
                            (self._term_key(term), term, meaning))

    def delete_term(self, term: str):
        with self.db:
            self.db.execute('DELETE FROM terms WHERE key=?', (self._term_key(term),))

    def exact_term(self, term: str) -> dict | None:
        row = self.db.execute('SELECT term, meaning FROM terms WHERE key=?', (self._term_key(term),)).fetchone()
        return dict(row) if row else None

    def all_terms(self) -> list[dict]:
        return [dict(r) for r in self.db.execute('SELECT term, meaning FROM terms ORDER BY term COLLATE NOCASE')]

    def match_terms(self, text: str) -> list[dict]:
        return [term for term in self.all_terms() if re.search(r'(?<![\w])' + re.escape(term['term']) + r'(?![\w])', text, re.IGNORECASE)]

    def get_setting(self, key: str, default=None):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except (ValueError, TypeError):
                pass
        return default

    def set_setting(self, key: str, value):
        with self.db:
            self.db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value, ensure_ascii=False)))

    @staticmethod
    def _cache_key(source: str, model: str) -> str:
        return hashlib.sha256((model + '\0' + source).encode('utf8')).hexdigest()

    def cache_get(self, source: str, model: str) -> dict | None:
        row = self.db.execute('SELECT result, warnings, highlights FROM cache WHERE key=?', (self._cache_key(source, model),)).fetchone()
        if not row:
            return None
        return {'text': row[0], 'warnings': json.loads(row[1]), 'highlights': json.loads(row[2])}

    def cache_put(self, source: str, model: str, result: str, warnings: list[str], highlights=None):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO cache(key,result,warnings,highlights) VALUES (?,?,?,?)',
                            (self._cache_key(source, model), result, json.dumps(warnings, ensure_ascii=False), json.dumps(highlights or [])))
            self.db.execute('DELETE FROM cache WHERE id NOT IN (SELECT id FROM cache ORDER BY id DESC LIMIT ?)', (self.limit,))
