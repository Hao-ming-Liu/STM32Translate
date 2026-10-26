"""Small Win32 boundary: hotkey, single instance, focus, working areas."""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import os
import queue
import re
import threading


u32 = C.WinDLL('user32', use_last_error=True)
k32 = C.WinDLL('kernel32', use_last_error=True)
u32.RegisterHotKey.argtypes = (W.HWND, C.c_int, W.UINT, W.UINT)
u32.RegisterHotKey.restype = W.BOOL
u32.UnregisterHotKey.argtypes = (W.HWND, C.c_int)
u32.GetMessageW.argtypes = (C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
u32.GetMessageW.restype = C.c_int
u32.PostThreadMessageW.argtypes = (W.DWORD, W.UINT, W.WPARAM, W.LPARAM)
u32.GetForegroundWindow.restype = W.HWND
u32.GetWindowThreadProcessId.argtypes = (W.HWND, C.POINTER(W.DWORD))
u32.GetAncestor.argtypes = (W.HWND, W.UINT)
u32.GetAncestor.restype = W.HWND
u32.SetForegroundWindow.argtypes = (W.HWND,)
u32.SetWindowPos.argtypes = (W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT)
k32.CreateMutexW.argtypes = (C.c_void_p, W.BOOL, W.LPCWSTR)
k32.CreateMutexW.restype = W.HANDLE
k32.CreateEventW.argtypes = (C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR)
k32.CreateEventW.restype = W.HANDLE
k32.SetEvent.argtypes = (W.HANDLE,)
k32.WaitForSingleObject.argtypes = (W.HANDLE, W.DWORD)
k32.CloseHandle.argtypes = (W.HANDLE,)
k32.GetCurrentThreadId.restype = W.DWORD


def parse_hotkey(value: str) -> tuple[int, int, str]:
    parts = [p.strip().upper() for p in value.split('+')]
    modifiers = {'CTRL': (2, 'Ctrl'), 'ALT': (1, 'Alt'), 'SHIFT': (4, 'Shift')}
    if len(parts) < 2 or len(parts) != len(set(parts)):
        raise ValueError('请使用 Ctrl、Alt、Shift 搭配一个字母、数字或 F1–F11，例如 Ctrl+Alt+T。')
    keys = [p for p in parts if p not in modifiers]
    if len(keys) != 1:
        raise ValueError('快捷键需要一个字母、数字或 F1–F11，不支持 Win 键。')
    key = keys[0]
    if re.fullmatch(r'[A-Z0-9]', key):
        vk = ord(key)
    elif re.fullmatch(r'F(?:[1-9]|1[01])', key):
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError('快捷键仅支持字母、数字或 F1–F11；F12 由调试器保留。')
    used = [m for m in modifiers if m in parts]
    if not used:
        raise ValueError('请至少使用一个 Ctrl、Alt 或 Shift 修饰键。')
    return 0x4000 | sum(modifiers[m][0] for m in used), vk, '+'.join([modifiers[m][1] for m in used] + [key])


class Hotkey:
    def __init__(self, shortcut: str, events: queue.Queue):
        self.mods, self.key, self.shortcut = parse_hotkey(shortcut)
        self.events = events
        self.error = ''
        self._ready = threading.Event()
        self._thread_id = 0
        self.thread = None

    def start(self) -> bool:
        self.thread = threading.Thread(target=self._run, name='global-hotkey', daemon=True)
        self.thread.start()
        if not self._ready.wait(3):
            self.error = '注册快捷键超时，请重试。'
        return not self.error

    def _run(self):
        self._thread_id = k32.GetCurrentThreadId()
        if not u32.RegisterHotKey(None, 1, self.mods, self.key):
            self.error = f'{self.shortcut} 已被占用或无法注册，请在设置中更换快捷键。'
            self._ready.set()
            return
        self._ready.set()
        msg = W.MSG()
        try:
            while u32.GetMessageW(C.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.events.put({'kind': 'hotkey'})
        finally:
            u32.UnregisterHotKey(None, 1)

    def close(self):
        if self.thread and self.thread.is_alive():
            u32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            self.thread.join(timeout=3)


class InstanceGuard:
    def __init__(self, name: str = 'Local\\STM32Translate.v1'):
        self.mutex = k32.CreateMutexW(None, False, name)
        error = C.get_last_error()
        if not self.mutex:
            raise C.WinError(error)
        self.already_running = error == 183
        self.event = k32.CreateEventW(None, False, False, name + '.show')
        if not self.event:
            self.close()
            raise C.WinError(C.get_last_error())

    def notify(self):
        k32.SetEvent(self.event)

    def requested(self) -> bool:
        return k32.WaitForSingleObject(self.event, 0) == 0

    def close(self):
        for name in ('event', 'mutex'):
            handle = getattr(self, name, None)
            if handle:
                k32.CloseHandle(handle)
                setattr(self, name, None)


class MonitorInfo(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('dwFlags', W.DWORD)]


def working_areas() -> list[tuple[int, int, int, int]]:
    result = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
    u32.GetMonitorInfoW.argtypes = (W.HANDLE, C.POINTER(MonitorInfo))
    @callback_type
    def callback(handle, hdc, rect, data):
        info = MonitorInfo()
        info.cbSize = C.sizeof(info)
        if u32.GetMonitorInfoW(handle, C.byref(info)):
            r = info.rcWork
            result.append((r.left, r.top, r.right, r.bottom))
        return True
    u32.EnumDisplayMonitors(None, None, callback, 0)
    return result or [(0, 0, u32.GetSystemMetrics(0), u32.GetSystemMetrics(1))]


def clamp_geometry(x: int, y: int, width: int, height: int, areas: list[tuple]) -> tuple[int, int, int, int]:
    cx, cy = x + width / 2, y + height / 2
    def distance(r):
        return max(r[0]-cx, 0, cx-r[2])**2 + max(r[1]-cy, 0, cy-r[3])**2
    left, top, right, bottom = min(areas, key=distance)
    width, height = min(width, right-left), min(height, bottom-top)
    return min(max(x, left), right-width), min(max(y, top), bottom-height), width, height


def enable_dpi_awareness():
    try:
        u32.SetProcessDpiAwarenessContext.argtypes = (C.c_void_p,)
        u32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except AttributeError:
        try:
            C.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


def own_foreground() -> bool:
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return True  # Windows is transitioning between windows.
    pid = W.DWORD()
    u32.GetWindowThreadProcessId(hwnd, C.byref(pid))
    return pid.value == os.getpid()


def window_handle(root) -> int:
    return u32.GetAncestor(root.winfo_id(), 2) or root.winfo_id()


def place_window(root, x: int, y: int):
    # Native absolute coordinates also handle monitors left of the primary one.
    u32.SetWindowPos(window_handle(root), None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)


def foreground(root):
    u32.SetForegroundWindow(window_handle(root))
