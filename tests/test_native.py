import os
import queue
import uuid

import pytest

from stm32translate.native import parse_hotkey, clamp_geometry, Hotkey, InstanceGuard


def test_hotkey_validation_and_modifier_order():
    assert parse_hotkey('alt+ctrl+t') == (0x4003, ord('T'), 'Ctrl+Alt+T')
    assert parse_hotkey('Ctrl+Shift+F9') == (0x4006, 0x78, 'Ctrl+Shift+F9')
    for invalid in ['T', 'Ctrl+F12', 'Win+T', 'Ctrl+Alt', 'Ctrl+Ctrl+T', 'Ctrl+Alt+Space+T']:
        with pytest.raises(ValueError):
            parse_hotkey(invalid)


def test_negative_monitor_positions_and_removed_monitor():
    monitors = [(-1920, 0, 0, 1080), (0, 0, 1920, 1040)]
    assert clamp_geometry(-1800, 50, 420, 320, monitors) == (-1800, 50, 420, 320)
    assert clamp_geometry(4000, 4000, 420, 320, monitors) == (1500, 720, 420, 320)
    assert clamp_geometry(0, 0, 3000, 2000, [(0, 0, 800, 600)]) == (0, 0, 800, 600)


@pytest.mark.skipif(os.name != 'nt', reason='Win32 integration')
def test_hotkey_conflict_and_release():
    events = queue.Queue()
    a = Hotkey('Ctrl+Alt+Shift+F11', events)
    b = Hotkey('Ctrl+Alt+Shift+F11', events)
    try:
        assert a.start(), a.error
        assert not b.start()
        assert '占用' in b.error
    finally:
        b.close()
        a.close()
    c = Hotkey('Ctrl+Alt+Shift+F11', events)
    try:
        assert c.start(), c.error
    finally:
        c.close()


@pytest.mark.skipif(os.name != 'nt', reason='Win32 integration')
def test_second_instance_notifies_first():
    name = 'Local\\STM32Translate.test.' + uuid.uuid4().hex
    first = InstanceGuard(name)
    second = InstanceGuard(name)
    try:
        assert not first.already_running
        assert second.already_running
        second.notify()
        assert first.requested()
        assert not first.requested()
    finally:
        second.close()
        first.close()
