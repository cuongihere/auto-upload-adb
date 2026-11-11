"""Embed an existing scrcpy SDL window inside a PySide6 QWidget on Windows.

The video and input remain native scrcpy, so mouse, keyboard and clipboard
behave as they do in a standalone scrcpy window. This module never captures
frames or simulates taps. It uses SetParent on a *known* scrcpy process only.
"""
from __future__ import annotations

import ctypes
import platform
import time
from ctypes import wintypes
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget, QPushButton

WINDOWS = platform.system().lower() == "windows"

# Win32 flags: https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setparent
GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_OVERLAPPEDWINDOW = (WS_CAPTION | WS_THICKFRAME | WS_SYSMENU |
                       WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

if WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = (_callback_type, wintypes.LPARAM)
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.IsWindow.argtypes = (wintypes.HWND,)
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetParent.argtypes = (wintypes.HWND,)
    _user32.GetParent.restype = wintypes.HWND
    _user32.SetParent.argtypes = (wintypes.HWND, wintypes.HWND)
    _user32.SetParent.restype = wintypes.HWND
    _user32.SetWindowPos.argtypes = (
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT
    )
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.SetFocus.argtypes = (wintypes.HWND,)
    _user32.SetFocus.restype = wintypes.HWND
    # Use pointer-sized entry points on 64-bit Python.
    _get_style = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _set_style = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _get_style.argtypes = (wintypes.HWND, ctypes.c_int)
    _get_style.restype = ctypes.c_ssize_t
    _set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    _set_style.restype = ctypes.c_ssize_t


def find_scrcpy_window(process_id: int, title: str) -> Optional[int]:
    """Only match the scrcpy process AND its expected title, never another app."""
    if not WINDOWS or not process_id or not title:
        return None
    matches: list[int] = []

    @_callback_type
    def visitor(hwnd, _):
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != process_id or not _user32.IsWindowVisible(hwnd):
            return True
        count = _user32.GetWindowTextLengthW(hwnd)
        if count <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(count + 1)
        _user32.GetWindowTextW(hwnd, buffer, count + 1)
        if buffer.value == title:
            matches.append(int(hwnd))
            return False
        return True

    _user32.EnumWindows(visitor, 0)
    return matches[0] if matches else None


def attach_window(hwnd: int, parent: int, width: int, height: int) -> int:
    """Reparent a scrcpy top-level window as a child, return its original style."""
    if not WINDOWS:
        raise OSError("Nhúng cửa sổ chỉ hỗ trợ Windows.")
    if not _user32.IsWindow(hwnd) or not _user32.IsWindow(parent):
        raise OSError("Không tìm thấy cửa sổ scrcpy hoặc khung hiển thị.")
    old_style = int(_get_style(hwnd, GWL_STYLE))
    child_style = (old_style & ~(WS_POPUP | WS_OVERLAPPEDWINDOW)) | WS_CHILD | WS_VISIBLE
    ctypes.set_last_error(0)
    _set_style(hwnd, GWL_STYLE, child_style)
    if ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    ctypes.set_last_error(0)
    previous_parent = _user32.SetParent(hwnd, parent)
    if not previous_parent and ctypes.get_last_error():
        # Recover the style if the window parent operation was rejected.
        _set_style(hwnd, GWL_STYLE, old_style)
        raise ctypes.WinError(ctypes.get_last_error())
    if not _user32.SetWindowPos(
        hwnd, None, 0, 0, max(1, width), max(1, height),
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW
    ):
        error = ctypes.get_last_error()
        detach_window(hwnd, old_style)
        raise ctypes.WinError(error)
    return old_style


def detach_window(hwnd: int, original_style: Optional[int] = None) -> None:
    """Restore scrcpy to a movable external window without killing its process."""
    if not WINDOWS or not hwnd or not _user32.IsWindow(hwnd):
        return
    # A reparented SDL window may not have had a desktop parent previously.
    # Restoring the top-level style makes it accessible after detaching.
    style = (
        ((original_style | WS_VISIBLE) & ~WS_CHILD)
        if original_style is not None
        else ((int(_get_style(hwnd, GWL_STYLE)) | WS_OVERLAPPEDWINDOW | WS_VISIBLE) & ~WS_CHILD)
    )
    _set_style(hwnd, GWL_STYLE, style)
    _user32.SetParent(hwnd, None)
    _user32.SetWindowPos(
        hwnd, None, 80, 80, 420, 780,
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW
    )


class EmbeddedScrcpyViewport(QWidget):
    """A native QWidget owning the Win32 child scrcpy HWND."""

    message = Signal(str)
    attached = Signal(str)
    detached = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background: #0c0f14;")
        self.serial = ""
        self.title = ""
        self.process = None
        self.hwnd: Optional[int] = None
        self.old_style: Optional[int] = None
        self._deadline = 0.0
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._try_attach)
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(1000)
        self._health_timer.timeout.connect(self._check_alive)

        self.placeholder = QLabel(
            "📱\n\nChọn điện thoại ở bảng bên trái\nvà nhấn «Nhúng scrcpy».\n\n"
            "Màn hình sẽ hiển thị tại đây.\nDùng chuột và bàn phím để điều khiển."
        )
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.placeholder.setStyleSheet("color: #b5bdc7; font-size: 13px; background: transparent;")
        label_layout = QVBoxLayout(self)
        label_layout.setContentsMargins(8, 8, 8, 8)
        label_layout.addWidget(self.placeholder)
        # Force creation of the HWND before scrcpy is reparented.
        self.winId()

    def begin(self, serial: str, process, title: str) -> None:
        if not WINDOWS:
            self.message.emit("Chức năng nhúng scrcpy hiện chỉ hỗ trợ Windows.")
            return
        if self.serial == serial and self.hwnd and _user32.IsWindow(self.hwnd):
            self.message.emit(f"{serial}: scrcpy đã hiển thị trong ứng dụng.")
            return
        if self.serial:
            self.release(restore=True)
        self.serial = serial
        self.process = process
        self.title = title
        self.hwnd = None
        self.old_style = None
        self._deadline = time.monotonic() + 20
        self.placeholder.setText(f"Đang mở màn hình {serial}…")
        self.placeholder.show()
        self._search_timer.start()
        self._try_attach()

    def _try_attach(self) -> None:
        if not self.process or not self.serial:
            self._search_timer.stop()
            return
        if self.process.poll() is not None:
            self._search_timer.stop()
            self.message.emit(f"{self.serial}: scrcpy đã thoát trước khi nhúng.")
            self.release(restore=False)
            return
        hwnd = find_scrcpy_window(self.process.pid, self.title)
        if hwnd:
            try:
                self.old_style = attach_window(
                    hwnd, int(self.winId()), self.width(), self.height()
                )
            except Exception as exc:
                self._search_timer.stop()
                self.message.emit(f"Không nhúng được scrcpy: {exc}. Cửa sổ vẫn mở ngoài.")
                self.release(restore=False)
                return
            self.hwnd = hwnd
            self._search_timer.stop()
            self._health_timer.start()
            self.placeholder.hide()
            self.attached.emit(self.serial)
            self.message.emit(f"Đã nhúng màn hình {self.serial} vào ứng dụng.")
            return
        if time.monotonic() > self._deadline:
            serial = self.serial
            self._search_timer.stop()
            self.release(restore=False)
            self.message.emit(
                f"{serial}: quá 20 giây không tìm thấy cửa sổ scrcpy. "
                "Kiểm tra log và phiên bản scrcpy."
            )

    def _check_alive(self) -> None:
        if not self.process or self.process.poll() is not None:
            self.release(restore=False)
        elif WINDOWS and self.hwnd and not _user32.IsWindow(self.hwnd):
            self.release(restore=False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if WINDOWS and self.hwnd and _user32.IsWindow(self.hwnd):
            _user32.SetWindowPos(
                self.hwnd, None, 0, 0, max(1, self.width()), max(1, self.height()),
                SWP_NOZORDER | SWP_NOACTIVATE
            )

    def release(self, restore: bool = True) -> None:
        self._search_timer.stop()
        self._health_timer.stop()
        if self.hwnd and restore:
            detach_window(self.hwnd, self.old_style)
        self.serial = ""
        self.process = None
        self.title = ""
        self.hwnd = None
        self.old_style = None
        self.placeholder.setText(
            "📱\n\nChọn điện thoại ở bảng bên trái\nvà nhấn «Nhúng scrcpy»."
        )
        self.placeholder.show()
        self.detached.emit()

    def shutdown(self) -> None:
        # Stop QTimer callbacks, restore child before Qt destroys its native HWND.
        self.release(restore=True)


class PhonePreviewPanel(QWidget):
    """Permanent dock panel with phone video and basic device controls."""

    request_embed = Signal()
    request_external = Signal()
    request_stop = Signal()
    request_home = Signal()
    request_back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(800)
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(6)

        self.label = QLabel("Chưa chọn điện thoại.")
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.label)

        self.viewport = EmbeddedScrcpyViewport(self)
        self.viewport.setMinimumSize(220, 270)
        root.addWidget(self.viewport, 1)

        controls = QHBoxLayout()
        self.btn_embed = QPushButton("📱 Nhúng scrcpy")
        self.btn_external = QPushButton("Tách ra")
        self.btn_stop = QPushButton("Dừng scrcpy")
        controls.addWidget(self.btn_embed, 1)
        controls.addWidget(self.btn_external)
        controls.addWidget(self.btn_stop)
        root.addLayout(controls)

        navigation = QHBoxLayout()
        self.btn_home = QPushButton("⌂ Home")
        self.btn_back = QPushButton("← Back")
        navigation.addWidget(self.btn_home)
        navigation.addWidget(self.btn_back)
        root.addLayout(navigation)

        self.btn_embed.clicked.connect(self.request_embed.emit)
        self.btn_external.clicked.connect(self.request_external.emit)
        self.btn_stop.clicked.connect(self.request_stop.emit)
        self.btn_home.clicked.connect(self.request_home.emit)
        self.btn_back.clicked.connect(self.request_back.emit)
        self.viewport.attached.connect(self._on_attached)
        self.viewport.detached.connect(self._on_detached)
        self._on_detached()

    def _on_attached(self, serial: str):
        self.label.setText(f"📱 Đang điều khiển: {serial}")
        self.btn_external.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def _on_detached(self):
        self.label.setText("Chọn điện thoại và nhấn «Nhúng scrcpy».")
        self.btn_external.setEnabled(False)
        self.btn_stop.setEnabled(False)

    def externalize(self):
        self.viewport.release(restore=True)

    def stop_preview(self):
        self.viewport.release(restore=True)
