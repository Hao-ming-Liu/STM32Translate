from pathlib import Path
import tkinter as tk

import pytest

from stm32translate.app import App
from urllib.parse import urlparse, parse_qs


@pytest.fixture(scope='module')
def window_app(tmp_path_factory):
    root = tk.Tk()
    instance = App(root, tmp_path_factory.mktemp('ui-data'))
    yield instance
    instance.quit()


@pytest.fixture
def app(window_app):
    # Production creates exactly one Tcl/Tk interpreter per process. Reuse it
    # here rather than repeatedly initialize Tcl during interpreter GC.
    if window_app.pinned:
        window_app.toggle_pin()
    window_app.hide()
    window_app.set_source('')
    window_app.last_translation = ''
    window_app.state.invalidate()
    return window_app


def test_popup_pin_escape_and_local_term_translation(app):
    app.show()
    app.root.update()
    assert app.root.state() == 'normal'
    app.toggle_pin()
    assert app.pinned and app.root.attributes('-topmost')
    app.store.save_term('prescaler', '预分频器')
    app.set_source('prescaler')
    app.translate()
    assert app.last_translation == '预分频器'
    assert app.client.pid is None
    app.hide()
    app.root.update()
    assert app.root.state() == 'withdrawn'


def test_child_focus_does_not_hide_popup(app, monkeypatch):
    app.show()
    app.term_dialog()
    dialog = next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))
    dialog.update()
    # Win32 may briefly report the previously focused external process while
    # the modal dialog receives focus; the parent must remain visible.
    monkeypatch.setattr('stm32translate.native.own_foreground', lambda: False)
    app.check_focus()
    app.root.update()
    assert app.root.state() == 'normal'
    dialog.destroy()


def test_empty_clipboard_and_text_paste(app):
    # Clipboard text is restored on completion; this test uses only our own UI.
    try:
        original = app.root.clipboard_get()
    except tk.TclError:
        original = None
    try:
        app.root.clipboard_clear()
        app.from_clipboard()
        assert '剪贴板' in app.status.get()
        app.store.save_term('interrupt', '中断')
        app.root.clipboard_append('interrupt')
        app.from_clipboard()
        assert app.last_translation == '中断'
    finally:
        app.root.clipboard_clear()
        if original is not None:
            app.root.clipboard_append(original)
        app.root.update()


def test_stale_result_does_not_overwrite_cached_term(app):
    old = app.state.begin('old')
    app.store.save_term('DMA', '直接存储器访问')
    app.set_source('DMA')
    app.translate()
    app.handle_result({'id': old, 'text': '过期结果', 'warnings': []})
    assert app.last_translation == '直接存储器访问'


def test_editing_source_invalidates_inflight_output(app):
    app.set_source('first')
    old = app.state.begin('first')
    app.set_source('second')
    app.handle_result({'id': old, 'text': '第一段结果', 'warnings': []})
    assert app.last_translation != '第一段结果'


@pytest.mark.parametrize('source', ['PRESENT', 'Enable the timer.\n' * 12])
def test_online_lookup_uses_complete_source_and_requested_suffix(app, monkeypatch, source):
    opened = []
    app.set_source(source)
    app.output.configure(state='normal')
    app.output.delete('1.0', 'end')
    app.output.insert('1.0', 'GPIO 错误的译文查询内容')
    app.output.tag_add('sel', '1.0', 'end')
    app.output.configure(state='disabled')
    monkeypatch.setattr('stm32translate.app.webbrowser.open', opened.append)
    monkeypatch.setattr('stm32translate.app.simpledialog.askstring', lambda *a, **k: pytest.fail('已有原文时不应再次询问'))
    app.lookup()
    assert len(opened) == 1
    assert parse_qs(urlparse(opened[0]).query)['q'] == [source.strip() + ' 英译中（STM32）']
    app.output.tag_remove('sel', '1.0', 'end')
