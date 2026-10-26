from pathlib import Path
import sqlite3

import pytest

from stm32translate.documents import translate_document, split_for_model
from stm32translate.store import Store
from stm32translate.controller import RequestState


def test_doxygen_parameter_and_code_are_preserved():
    source = '/**\n * @param[in] GPIOx Select the GPIO peripheral.\n * @retval None\n */\nvoid HAL_GPIO_Init(GPIO_TypeDef *GPIOx);'
    def batch(parts):
        return [p.replace('Select the ', '选择 ').replace(' peripheral.', ' 外设。').replace('None', '无') for p in parts]
    result = translate_document(source, batch)
    assert '@param[in] GPIOx 选择 GPIO 外设。' in result.text
    assert '@retval 无' in result.text
    assert 'void HAL_GPIO_Init(GPIO_TypeDef *GPIOx);' in result.text


def test_numeric_ranges_and_identifier_restore_exactly():
    def batch(parts):
        return [p.replace('Set', '设置').replace('between', '范围').replace('and', '与') for p in parts]
    result = translate_document('Set TIM_Prescaler between 0 and 65535.', batch)
    assert 'TIM_Prescaler' in result.text
    assert '65535' in result.text and '0' in result.text
    assert not result.warnings


def test_mutated_placeholder_falls_back_without_losing_source():
    source = 'Enable HAL_TIM_Base_Start_IT() before using GPIO_PIN_5.'
    result = translate_document(source, lambda parts: ['译文丢失标识符' for p in parts])
    assert result.text == source
    assert result.warnings


def test_long_input_is_fully_chunked_without_dropping_tail():
    source = ('Enable the timer before starting conversion. ' * 200) + 'Last sentence.'
    parts = split_for_model(source, max_chars=240)
    assert ''.join(parts) == source
    assert all(len(p) <= 240 for p in parts)
    result = translate_document(source, lambda parts: parts)
    assert result.text == source


def test_code_block_and_comments_on_code_lines():
    source = '#define DELAY 100\nGPIO_InitStruct.Pin = GPIO_PIN_5; // Enable output\n// Enable the timer.'
    result = translate_document(source, lambda parts: [p.replace('Enable', '使能') for p in parts])
    assert '#define DELAY 100' in result.text
    assert 'GPIO_InitStruct.Pin = GPIO_PIN_5; // 使能 output' in result.text
    assert '// 使能 the timer.' in result.text


def test_empty_input_does_not_invoke_model():
    result = translate_document('  ', lambda _: pytest.fail('empty input should not load model'))
    assert result.text == ''


def test_model_output_count_mismatch_is_explicit_error():
    with pytest.raises(ValueError, match='数量'):
        translate_document('Enable the timer.', lambda _: [])


def test_term_persistence_casefold_boundaries_and_edit(tmp_path):
    path = tmp_path / 'store.db'
    with Store(path) as store:
        store.save_term('interrupt', '中断')
        store.save_term('DMA', '直接存储器访问')
        assert store.exact_term(' INTERRUPT ')['meaning'] == '中断'
        assert [t['term'] for t in store.match_terms('An interrupt enables DMA; not interruptible.')] == ['DMA', 'interrupt']
        assert store.match_terms('interruptible') == []
        store.save_term('Interrupt', '中断请求')
    with Store(path) as store:
        assert store.exact_term('interrupt')['meaning'] == '中断请求'
        store.delete_term('interrupt')
        assert store.exact_term('interrupt') is None


def test_translation_cache_is_model_scoped_and_bounded(tmp_path):
    with Store(tmp_path / 'store.db', cache_limit=2) as store:
        store.cache_put('first', 'a', '一', [])
        store.cache_put('second', 'a', '二', ['保留原文'])
        assert store.cache_get('first', 'b') is None
        assert store.cache_get('second', 'a')['warnings'] == ['保留原文']
        store.cache_put('third', 'a', '三', [])
        assert store.cache_get('first', 'a') is None
        assert store.cache_get('third', 'a')['text'] == '三'


def test_stale_results_never_replace_newer_input():
    state = RequestState()
    old = state.begin('first')
    new = state.begin('second')
    assert not state.accept(old)
    assert state.accept(new)
    state.begin('third')
    assert not state.accept(new)


def test_discard_result_when_hidden_does_not_cancel_new_request():
    state = RequestState()
    old = state.begin('first')
    state.invalidate()
    assert not state.accept(old)
    new = state.begin('second')
    assert state.accept(new)


def test_c_control_flow_is_never_translated_but_comments_are():
    source = 'extern "C"\n{\n bool ready;\n while (!ready)\n {\n  if (ready)\n   ++count;\n  else\n   break;\n  // Enable the timer.\n }\n}'
    result = translate_document(source, lambda parts: ['使能定时器。' for _ in parts])
    assert result.text == source.replace('Enable the timer.', '使能定时器。')


@pytest.mark.parametrize('prefix', ['@', '\\'])
def test_doxygen_code_blocks_and_structural_commands(prefix):
    source = f'{prefix}defgroup GPIO GPIO peripheral\n{prefix}ingroup HAL Driver\n{prefix}code\nif (ready)\n run();\nelse\n stop();\n{prefix}endcode'
    result = translate_document(source, lambda parts: [p.replace('peripheral', '外设').replace('defgroup', '错误标签').replace('ingroup', '错误标签').replace('code', '错误标签').replace('if', '错误代码') for p in parts])
    assert result.text == source.replace('peripheral', '外设')


def test_parameter_names_are_protected_even_before_declaration():
    source = '@brief State specifies the operation.\n@param State State specifies the operation.\n@param GPIOx GPIOx specifies the peripheral.'
    def translate(parts):
        return [p.replace('State', '国家').replace('GPIOx', '错误').replace('specifies the operation.', '指定操作。').replace('specifies the peripheral.', '指定外设。') for p in parts]
    result = translate_document(source, translate)
    assert '@brief State 指定操作。' in result.text
    assert '@param State State 指定操作。' in result.text
    assert '@param GPIOx GPIOx 指定外设。' in result.text


def test_numeric_values_use_literal_numbers_and_are_validated():
    seen = []
    def translate(parts):
        seen.extend(parts)
        return [p.replace('The value is', '数值为') for p in parts]
    result = translate_document('The value is 50.', translate)
    assert seen == ['The value is 50.']
    assert result.text == '数值为 50.' and not result.warnings
    result = translate_document('The value is 50.', lambda _: ['数值为 5。'])
    assert result.text == 'The value is 50.' and result.warnings
    result = translate_document('The value is 50.', lambda _: ['数值为50。'])
    assert result.text == '数值为50。' and not result.warnings


def test_retry_without_markers_is_accepted_only_when_code_survives():
    def translate(parts):
        return [p.replace('ZXQ0QXZ', '损坏的标记').replace('Call ', '调用 ').replace(' to start the timer.', ' 启动定时器。') for p in parts]
    result = translate_document('Call HAL_TIM_Base_Start_IT() to start the timer.', translate)
    assert result.text == '调用 HAL_TIM_Base_Start_IT() 启动定时器。'
    assert not result.warnings


def test_seed_terms_do_not_overwrite_edits_or_restore_deleted_entries(tmp_path):
    with Store(tmp_path / 'terms.db') as store:
        store.save_term('pin', '自定义引脚解释')
        store.seed_defaults()
        assert store.exact_term('pull-up resistor')['meaning'] == '上拉电阻'
        assert store.exact_term('pin')['meaning'] == '自定义引脚解释'
        store.delete_term('prescaler')
        store.seed_defaults()
        assert store.exact_term('prescaler') is None
