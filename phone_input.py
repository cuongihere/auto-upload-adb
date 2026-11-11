"""Focus and keyboard shortcuts for the app-owned native scrcpy child window.

Text travels through scrcpy's Unicode clipboard protocol, never adb input text.
Every input checks the expected process, parent and foreground focus first.
"""
from __future__ import annotations

import ctypes
import platform
from ctypes import wintypes

WINDOWS = platform.system().lower() == 'windows'

if WINDOWS:
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    for name, args, result in (
        ('IsWindow', (wintypes.HWND,), wintypes.BOOL),
        ('GetParent', (wintypes.HWND,), wintypes.HWND),
        ('GetAncestor', (wintypes.HWND, wintypes.UINT), wintypes.HWND),
        ('GetForegroundWindow', (), wintypes.HWND),
        ('GetWindowThreadProcessId', (wintypes.HWND, ctypes.POINTER(wintypes.DWORD)), wintypes.DWORD),
        ('AttachThreadInput', (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL), wintypes.BOOL),
        ('SetForegroundWindow', (wintypes.HWND,), wintypes.BOOL),
        ('SetFocus', (wintypes.HWND,), wintypes.HWND),
        ('GetFocus', (), wintypes.HWND),
        ('GetAsyncKeyState', (ctypes.c_int,), ctypes.c_short),
    ):
        fn = getattr(user32, name)
        fn.argtypes, fn.restype = args, result
    kernel32.GetCurrentThreadId.argtypes = ()
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                    ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                    ('dwExtraInfo', ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                    ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

    class INPUTUNION(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ('value',)
        _fields_ = [('type', wintypes.DWORD), ('value', INPUTUNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT


def validate_target(hwnd: int, parent: int, process_id: int) -> None:
    if not WINDOWS:
        raise OSError('Điều khiển bàn phím nhúng chỉ hỗ trợ Windows.')
    if not hwnd or not parent or not process_id or not user32.IsWindow(hwnd):
        raise OSError('Chưa nhúng điện thoại hoặc scrcpy đã đóng.')
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value != process_id or user32.GetParent(hwnd) != parent:
        raise OSError('Cửa sổ scrcpy đã thay đổi. Hãy nhúng lại điện thoại.')


def _with_focus(hwnd: int, parent: int, process_id: int, action=None) -> None:
    validate_target(hwnd, parent, process_id)
    current = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(hwnd, None)
    linked = False
    if current != other:
        linked = bool(user32.AttachThreadInput(current, other, True))
        if not linked:
            raise OSError('Không chuyển được focus bàn phím sang scrcpy.')
    try:
        root = user32.GetAncestor(hwnd, 2)  # GA_ROOT: our main app window
        user32.SetForegroundWindow(root)
        user32.SetFocus(hwnd)
        if user32.GetFocus() != hwnd or user32.GetForegroundWindow() != root:
            raise OSError('Hãy kích hoạt app và bấm lại nút Bàn phím → điện thoại.')
        validate_target(hwnd, parent, process_id)
        if action:
            action()
    finally:
        if linked:
            user32.AttachThreadInput(current, other, False)


def focus_phone(hwnd: int, parent: int, process_id: int) -> None:
    _with_focus(hwnd, parent, process_id)


def send_shortcut(hwnd: int, parent: int, process_id: int, key: str) -> None:
    """Ctrl+A/C/X/V, explicitly requested by the user via a panel button."""
    if key not in ('A', 'C', 'X', 'V'):
        raise ValueError('Unsupported phone shortcut')

    def send():
        # A held modifier could redirect a shortcut (e.g. Ctrl+Shift+V = legacy
        # text injection). Let the user release it instead of changing its state.
        if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            raise OSError('Thả Ctrl/Alt/Shift trước khi bấm nút điều khiển.')
        keys = ((0x11, 0), (ord(key), 0), (ord(key), 2), (0x11, 2))
        events = (INPUT * len(keys))()
        for event, (vk, flags) in zip(events, keys):
            event.type = 1  # INPUT_KEYBOARD
            event.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
        count = user32.SendInput(len(events), events, ctypes.sizeof(INPUT))
        if count != len(events):
            # Best-effort release prevents a failed injection leaving Ctrl held.
            release = INPUT(type=1)
            release.ki = KEYBDINPUT(0x11, 0, 2, 0, 0)
            user32.SendInput(1, ctypes.byref(release), ctypes.sizeof(INPUT))
            raise OSError('Windows chưa chuyển đủ phím tới scrcpy; kiểm tra ô nhập trước khi thử lại.')

    _with_focus(hwnd, parent, process_id, send)
