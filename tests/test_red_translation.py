import sqlite3

from stm32translate.documents import translate_document
from stm32translate.store import Store


def test_protected_words_are_translated_and_only_their_results_are_red():
    seen = []
    def batch(parts):
        seen.extend(parts)
        return [{'GPIO': '通用输入输出'}.get(p, p.replace('Enable ', '使能 ')) for p in parts]
    result = translate_document('// Enable GPIO.\nGPIO_Init();', batch)
    assert result.text == '// 使能 通用输入输出.\nGPIO_Init();'
    assert 'GPIO' in seen
    assert [result.text[a:b] for a, b in result.highlights] == ['通用输入输出']


def test_repeated_tokens_and_unicode_offsets_are_correct():
    def batch(parts):
        return ['引脚' if p == 'GPIO_PIN_5' else p for p in parts]
    result = translate_document('😀 GPIO_PIN_5 and GPIO_PIN_5', batch)
    assert result.text == '😀 引脚 and 引脚'
    assert [result.text[a:b] for a,b in result.highlights] == ['引脚', '引脚']


def test_term_translation_survives_sentence_marker_failure():
    def batch(parts):
        return ['通用输入输出' if p == 'GPIO' else '无法定位' for p in parts]
    result = translate_document('Enable GPIO.', batch)
    assert '通用输入输出' in result.text
    assert result.highlights and result.warnings


def test_numbers_stay_literal_without_being_marked_as_translated_words():
    result = translate_document('Set GPIO to 10.', lambda parts: parts)
    assert [result.text[a:b] for a,b in result.highlights] == ['GPIO']


def test_cache_upgrades_old_schema_and_keeps_red_ranges(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE cache (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, result TEXT NOT NULL, warnings TEXT NOT NULL)')
    with Store(path) as store:
        store.save_term('GPIO', '已有术语')
        store.cache_put('source', 'v5', '使能 通用输入输出', [], [[3,9]])
    with Store(path) as store:
        assert store.exact_term('GPIO')['meaning'] == '已有术语'
        assert store.cache_get('source', 'v5')['highlights'] == [[3,9]]
