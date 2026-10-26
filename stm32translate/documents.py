"""Translate comment prose while keeping source structure and code intact."""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import re
from typing import Callable


@dataclass
class Translation:
    text: str
    warnings: list[str]


# Only high-confidence technical tokens; ordinary English remains translatable.
_NUMBER = re.compile(r'(?<![A-Za-z0-9_])[-+]?(?:0[xX][\da-fA-F]+|\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?:[uUlLfF]+)?(?![A-Za-z0-9_])')
# Capitalization alone is not evidence of code (e.g. PRESENT or ENABLE).
# Preserve known technical abbreviations, numbered names, and explicit code.
_ACRONYMS = r'GPIO|DMA|ADC|DAC|PWM|NVIC|RCC|EXTI|UART|USART|SPI|I2C|I2S|CAN|USB|CPU|MCU|RAM|ROM|SRAM|DRAM|FLASH|EEPROM|RTC|CRC|RNG|FPU|MPU|MMU|HAL|LL|CMSIS|RTOS|SWD|JTAG|IRQ|ISR|APB|AHB|PLL|HSE|HSI|LSE|LSI|SYSCLK|HCLK|PCLK|FIFO|MSB|LSB|LED|LCD|VDD|VSS'
_TOKEN = re.compile(
    r'`[^`\n]+`'
    r'|\b(?:[A-Za-z_]\w*_\w+|' + _ACRONYMS + r'|[A-Z][A-Z0-9]*\d[A-Z0-9]*|[a-z]+[A-Z]\w*|'
    r'[A-Za-z_]\w*(?=\s*\())\b(?:\([^()\n]*\))?'
    r'|' + _NUMBER.pattern
)
_COMMENT = re.compile(r'^(\s*(?:(?://[/!]?|/\*+[!]?)\s*|\*\s*))')
_PARAM = re.compile(r'^([@\\](?:param|tparam|defgroup|addtogroup|weakgroup)(?:\[[^\]]*\])?\s+(?:\[[^\]]+\]\s*)?\S+\s*)')
_TAG = re.compile(r'^([@\\][A-Za-z_]\w*(?:\[[^\]]*\])?\s*)')
_STRUCTURAL = re.compile(r'^[@\\](?:ingroup|fn|var|typedef|enum|struct|class|union|namespace|include|snippet|copydoc|copybrief|copydetails|anchor|link|endlink)\b')


def split_for_model(text: str, max_chars: int = 400) -> list[str]:
    """Keep every character; prefer sentence and word boundaries."""
    if max_chars < 32:
        raise ValueError('分段长度过小')
    chunks = []
    while len(text) > max_chars:
        prefix = text[:max_chars]
        ends = [m.end() for m in re.finditer(r'[.!?;]\s+', prefix)]
        cut = ends[-1] if ends else prefix.rfind(' ') + 1
        if cut < max_chars // 3:
            cut = max_chars
        chunks.append(text[:cut])
        text = text[cut:]
    if text:
        chunks.append(text)
    return chunks


def _code(line: str) -> bool:
    s = line.strip()
    return bool(s and (
        s.startswith(('#', '{', '}', 'typedef ', 'struct ', 'enum ', '```'))
        or s.endswith(';')
        or re.match(r'^(?:static\s+|const\s+|volatile\s+)*(?:void|int|char|float|double|bool|long|short|unsigned|signed|extern|if|else|while|for|do|switch|case|default|return|break|continue|goto|u?int\d+_t|[A-Za-z_]\w*(?:TypeDef|_t))\b', s)
        or re.match(r'^\w+(?:\.\w+|->\w+)*\s*(?:[|&+\-]?=)', s)
        or re.match(r'^[A-Za-z_]\w*\s*\([^\n]*\)\s*\{?$', s)
    ))


def _line_parts(line: str) -> tuple[str, str, str]:
    """Return immutable prefix, prose and immutable suffix."""
    if not line.strip() or line.strip() in ('/*', '/**', '*/', '*'):
        return line, '', ''
    m = _COMMENT.match(line)
    if m:
        prefix, prose = m.group(), line[m.end():]
    elif _code(line.split('//', 1)[0]) and '//' in line:
        before, prose = line.split('//', 1)
        prefix = before + '//'
        spaces = re.match(r'\s*', prose).group()
        prefix, prose = prefix + spaces, prose[len(spaces):]
    elif _code(line):
        return line, '', ''
    else:
        spaces = re.match(r'\s*', line).group()
        prefix, prose = spaces, line[len(spaces):]
    suffix = ''
    if prose.rstrip().endswith('*/'):
        cut = prose.rfind('*/')
        suffix, prose = prose[cut:], prose[:cut]
    if _STRUCTURAL.match(prose):
        return prefix + prose + suffix, '', ''
    m = _PARAM.match(prose) or _TAG.match(prose)
    if m:
        prefix, prose = prefix + m.group(), prose[m.end():]
    if _code(prose):
        return prefix + prose + suffix, '', ''
    return prefix, prose, suffix


def _protect(text: str, parameter_names: set[str]) -> tuple[str, list[tuple[str, str]]]:
    tokens: list[tuple[str, str]] = []
    # The nonce cannot collide with a literal marker in the user's input.
    nonce = 'ZXQ'
    while nonce.casefold() in text.casefold():
        nonce += 'Z'
    def replace(m):
        if _NUMBER.fullmatch(m.group()):
            tokens.append((f'NUM:{len(tokens)}', m.group()))
            return m.group()  # Numbers translate more reliably in their literal form.
        marker = f'{nonce}{len(tokens)}QXZ'
        tokens.append((marker, m.group()))
        return marker
    pattern = _TOKEN
    if parameter_names:
        pattern = re.compile(_TOKEN.pattern + r'|(?<!\w)(?:' + '|'.join(re.escape(n) for n in sorted(parameter_names, key=len, reverse=True)) + r')(?!\w)')
    protected = pattern.sub(replace, text)
    # The small translation model handles natural-language casing much better
    # than all-caps headings. Markers contain digits and are not matched here.
    protected = re.sub(r'\b[A-Z]{2,}\b', lambda m: m.group().lower(), protected)
    return protected, tokens


def _restore(text: str, tokens: list[tuple[str, str]]) -> str | None:
    numbers = Counter(original for marker, original in tokens if marker.startswith('NUM:'))
    if numbers and Counter(_NUMBER.findall(text)) != numbers:
        return None
    for marker, original in tokens:
        if marker.startswith('NUM:'):
            continue
        pattern = r'\s*'.join(re.escape(c) for c in marker)
        if len(re.findall(pattern, text, flags=re.IGNORECASE)) != 1:
            return None
        text = re.sub(pattern, lambda _: original, text, flags=re.IGNORECASE)
    return text


def _validate_literal(text: str, tokens: list[tuple[str, str]]) -> bool:
    if not text.strip():
        return False
    numeric = []
    identifiers = Counter()
    for marker, original in tokens:
        if marker.startswith('NUM:'):
            numeric.append(original)
        else:
            identifiers[original] += 1
            numeric.extend(_NUMBER.findall(original))
    if numeric and Counter(_NUMBER.findall(text)) != Counter(numeric):
        return False
    return all(len(re.findall(r'(?<![A-Za-z0-9_])' + re.escape(value) + r'(?![A-Za-z0-9_])', text)) == count
               for value, count in identifiers.items())


def translate_document(text: str, batch_translate: Callable[[list[str]], list[str]]) -> Translation:
    if not text.strip():
        return Translation('', [])
    # A segment is (literal, translatable, original, protected tokens).
    layout = []
    requests = []
    in_fence = False
    in_code = False
    brace_depth = 0
    parameter_names = set(re.findall(r'[@\\](?:param|tparam)(?:\[[^\]]*\])?\s+(?:\[[^\]]+\]\s*)?([A-Za-z_]\w*)', text))
    parameter_names.update(re.findall(r'^\s*#\s*define\s+([A-Za-z_]\w*)', text, re.MULTILINE))
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip('\r\n')
        ending = raw[len(line):]
        pfx, prose, suffix = _line_parts(line)
        if re.search(r'[@\\](?:code|verbatim|dot|msc|startuml)\b', line):
            in_code = not bool(re.search(r'[@\\](?:endcode|endverbatim|enddot|endmsc|enduml)\b', line))
            layout.append((raw, False, '', []))
            continue
        if re.search(r'[@\\](?:endcode|endverbatim|enddot|endmsc|enduml)\b', line):
            in_code = False
            layout.append((raw, False, '', []))
            continue
        if '```' in line:
            in_fence = not in_fence
            layout.append((raw, False, '', []))
            continue
        if in_code or in_fence:
            layout.append((raw, False, '', []))
            continue
        # A C body stays code even on unfamiliar continuation lines. Comments in
        # that body still go through the normal comment/prose path.
        comment = _COMMENT.match(line)
        if not comment and (brace_depth > 0 or _code(line.split('//', 1)[0])):
            code = re.sub(r'"(?:\\.|[^"\\])*"', '', line.split('//', 1)[0])
            brace_depth = max(0, brace_depth + code.count('{') - code.count('}'))
            if '//' not in line:
                layout.append((raw, False, '', []))
                continue
        if not re.search(r'[A-Za-z]', prose):
            layout.append((raw, False, '', []))
            continue
        layout.append((pfx, False, '', []))
        for chunk in split_for_model(prose):
            leading = re.match(r'\s*', chunk).group()
            trailing = re.search(r'\s*$', chunk).group()
            core = chunk.strip()
            if not core:
                layout.append((chunk, False, '', []))
                continue
            protected, tokens = _protect(core, parameter_names)
            layout.append((leading, False, '', []))
            layout.append((protected, True, core, tokens))
            layout.append((trailing, False, '', []))
            requests.append(protected)
        layout.append((suffix + ending, False, '', []))
    responses = iter(batch_translate(requests) if requests else [])
    output, warnings = [], []
    count = 0
    for value, translate, original, tokens in layout:
        if not translate:
            output.append(value)
            continue
        try:
            translated = next(responses)
        except StopIteration as exc:
            raise ValueError('翻译结果数量不匹配，未显示不完整译文') from exc
        count += 1
        restored = _restore(translated, tokens) if translated.strip() else None
        if restored is None:
            retry = batch_translate([original])
            if len(retry) != 1:
                raise ValueError('翻译结果数量不匹配')
            if _validate_literal(retry[0], tokens):
                restored = retry[0]
        if restored is None:
            output.append(original)
            warnings.append(f'第 {count} 个片段的代码标识符或数值未能安全恢复，已保留该片段原文。')
        else:
            output.append(restored)
    if next(responses, None) is not None:
        raise ValueError('翻译结果数量不匹配')
    return Translation(''.join(output), warnings)
