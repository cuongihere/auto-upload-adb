# Trình quản lý Android Scrcpy v1.2
# Quản lý nhiều điện thoại Android bằng ADB + scrcpy.
# Tác giả: generated for local use.
#
# Chạy:
#   setup_and_run.bat
#
# Yêu cầu:
#   - Windows 10/11
#   - Python 3.10+
#   - Đã bật USB debugging trên Android
#   - scrcpy portable nằm trong tools/scrcpy hoặc có sẵn trong PATH

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if platform.system().lower().startswith("win"):
    import ctypes
    from ctypes import wintypes

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from auto_upload_tab import AutoUploadTab
from embedded_scrcpy import PhonePreviewPanel

APP_NAME = "Trình quản lý Android Scrcpy"
PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_DIR / "config"
TOOLS_DIR = PROJECT_DIR / "tools"
SCREENSHOT_DIR = PROJECT_DIR / "screenshots"
LOG_DIR = PROJECT_DIR / "logs"
PROFILES_FILE = CONFIG_DIR / "device_profiles.json"
SETTINGS_FILE = CONFIG_DIR / "app_settings.json"

IS_WINDOWS = platform.system().lower().startswith("win")
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
CREATE_NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
# ===== Windows taskbar identity / per-app icon =====
# Đổi 2 dòng dưới đây cho từng app Python khác nhau để Windows không gom chung taskbar.
_THIS_MAIN_FILE = os.path.abspath(globals().get("__file__", "main.py"))
_THIS_MAIN_DIR = os.path.dirname(_THIS_MAIN_FILE)
APP_USER_MODEL_ID = "AndroidScrcpyManager.Cuong.Local"
APP_WINDOW_ICON_CANDIDATES = (
    os.path.join(_THIS_MAIN_DIR, "assets", "app_icon.ico"),
    os.path.join(_THIS_MAIN_DIR, "assets", "android_scrcpy.ico"),
    os.path.join(_THIS_MAIN_DIR, "assets", "unified_manager.ico"),
    os.path.join(_THIS_MAIN_DIR, "assets", "app.ico"),
    os.path.join(_THIS_MAIN_DIR, "assets", "icon.ico"),
    os.path.join(_THIS_MAIN_DIR, "app_icon.ico"),
    os.path.join(_THIS_MAIN_DIR, "android_scrcpy.ico"),
    os.path.join(_THIS_MAIN_DIR, "unified_manager.ico"),
    os.path.join(_THIS_MAIN_DIR, "app.ico"),
    os.path.join(_THIS_MAIN_DIR, "icon.ico"),
)


def get_app_icon_path() -> Optional[str]:
    """Return the first existing .ico file for the app window/taskbar icon."""
    for icon_path in APP_WINDOW_ICON_CANDIDATES:
        try:
            if icon_path and os.path.isfile(icon_path):
                return icon_path
        except Exception:
            pass
    return None


def apply_windows_app_user_model_id() -> None:
    """Make Windows taskbar use this app's own identity instead of Python's icon."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def apply_window_icon(target) -> Optional[str]:
    """Apply the app icon to QApplication/QMainWindow when an icon file exists."""
    icon_path = get_app_icon_path()
    if not icon_path:
        return None
    try:
        icon = QIcon(icon_path)
        if not icon.isNull() and hasattr(target, "setWindowIcon"):
            target.setWindowIcon(icon)
            return icon_path
    except Exception:
        pass
    return None

QUALITY_PRESETS = {
    "Thấp - nhiều máy": {
        "max_size": 800,
        "bitrate": "1M",
        "max_fps": 20,
        "no_audio": True,
    },
    "Cân bằng": {
        "max_size": 1024,
        "bitrate": "3M",
        "max_fps": 30,
        "no_audio": True,
    },
    "Cao": {
        "max_size": 1280,
        "bitrate": "6M",
        "max_fps": 60,
        "no_audio": False,
    },
    "Tùy chỉnh": {
        "max_size": 1024,
        "bitrate": "3M",
        "max_fps": 30,
        "no_audio": True,
    },
}

QUALITY_ALIASES = {
    "Low - nhieu may": "Thấp - nhiều máy",
    "Low - nhiều máy": "Thấp - nhiều máy",
    "Balanced": "Cân bằng",
    "High": "Cao",
    "Custom": "Tùy chỉnh",
}


def normalize_quality_name(value: str) -> str:
    value = (value or "").strip()
    return QUALITY_ALIASES.get(value, value if value in QUALITY_PRESETS else "Cân bằng")


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    TOOLS_DIR.mkdir(exist_ok=True)
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def win_startupinfo():
    if not IS_WINDOWS:
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def safe_run(args: List[str], timeout: int = 15, cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=win_startupinfo(),
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError as e:
        return 127, "", str(e)
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", f"Timeout after {timeout}s"


def find_first(patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        for p in PROJECT_DIR.glob(pattern):
            if p.is_file():
                return str(p)
    return None


def find_exe(name: str) -> Optional[str]:
    exe = f"{name}.exe" if IS_WINDOWS and not name.lower().endswith(".exe") else name

    # Local preferred paths
    local_patterns = [
        f"tools/{exe}",
        f"tools/scrcpy/{exe}",
        f"tools/scrcpy-win64/{exe}",
        f"tools/scrcpy-win64-*/{exe}",
        f"tools/scrcpy-win32/{exe}",
        f"tools/scrcpy-win32-*/{exe}",
        f"tools/platform-tools/{exe}",
    ]
    found = find_first(local_patterns)
    if found:
        return found

    # PATH fallback
    path_found = shutil.which(exe) or shutil.which(name)
    return path_found


def adb_path() -> Optional[str]:
    # Prefer adb beside scrcpy if present
    scr = find_exe("scrcpy")
    if scr:
        maybe = Path(scr).parent / ("adb.exe" if IS_WINDOWS else "adb")
        if maybe.exists():
            return str(maybe)
    return find_exe("adb")


def scrcpy_path() -> Optional[str]:
    return find_exe("scrcpy")


@dataclass
class AndroidDevice:
    serial: str
    state: str
    model: str = ""
    product: str = ""
    device: str = ""
    transport_id: str = ""

    @property
    def is_online(self) -> bool:
        return self.state == "device"

    @property
    def display_model(self) -> str:
        return (self.model or self.device or self.product or "Android").replace("_", " ")


@dataclass
class DeviceProfile:
    name: str = ""
    group: str = ""
    default_package: str = ""
    quality: str = "Cân bằng"
    max_size: int = 1024
    bitrate: str = "3M"
    max_fps: int = 30
    no_audio: bool = True
    stay_awake: bool = True
    turn_screen_off: bool = False
    power_off_on_close: bool = False
    window_width: int = 360
    window_height: int = 720

    def merged_with_quality(self) -> "DeviceProfile":
        data = asdict(self)
        preset = QUALITY_PRESETS.get(self.quality)
        if preset and self.quality != "Custom":
            data.update(preset)
        return DeviceProfile(**data)


class ConfigStore:
    def __init__(self):
        ensure_dirs()
        self.profiles: Dict[str, DeviceProfile] = {}
        self.settings = {
            "layout_columns": 4,
            "layout_margin_x": 0,
            "layout_margin_y": 0,
            "layout_gap_x": 8,
            "layout_gap_y": 32,
            "default_window_width": 360,
            "default_window_height": 720,
            "master_window_width": 540,
            "master_window_height": 960,
            "auto_scan_seconds": 5,
        }
        self.load()

    def load(self) -> None:
        if PROFILES_FILE.exists():
            try:
                raw = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
                for serial, data in raw.items():
                    clean = {k: v for k, v in data.items() if k in DeviceProfile.__dataclass_fields__}
                    if "quality" in clean:
                        clean["quality"] = normalize_quality_name(clean.get("quality", ""))
                    self.profiles[serial] = DeviceProfile(**clean)
            except Exception:
                self.profiles = {}
        if SETTINGS_FILE.exists():
            try:
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                self.settings.update(raw)
            except Exception:
                pass

    def save(self) -> None:
        ensure_dirs()
        raw = {serial: asdict(profile) for serial, profile in self.profiles.items()}
        PROFILES_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def profile_for(self, device: AndroidDevice) -> DeviceProfile:
        if device.serial not in self.profiles:
            short = device.display_model
            if short == "Android":
                short = device.serial
            self.profiles[device.serial] = DeviceProfile(
                name=short,
                window_width=int(self.settings["default_window_width"]),
                window_height=int(self.settings["default_window_height"]),
            )
        return self.profiles[device.serial]


def parse_adb_devices(output: str) -> List[AndroidDevice]:
    devices: List[AndroidDevice] = []
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in lines:
        if line.lower().startswith("list of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        kv = {}
        for token in parts[2:]:
            if ":" in token:
                k, v = token.split(":", 1)
                kv[k] = v
        devices.append(
            AndroidDevice(
                serial=serial,
                state=state,
                model=kv.get("model", ""),
                product=kv.get("product", ""),
                device=kv.get("device", ""),
                transport_id=kv.get("transport_id", ""),
            )
        )
    return devices


class DeviceScanner(QThread):
    done = Signal(list, str)
    fail = Signal(str)

    def run(self) -> None:
        adb = adb_path()
        if not adb:
            self.fail.emit("Không tìm thấy adb.exe. Đặt scrcpy portable vào tools/scrcpy hoặc cài ADB vào PATH.")
            return

        code, out, err = safe_run([adb, "devices", "-l"], timeout=20)
        if code != 0:
            self.fail.emit((err or out or "Lệnh adb devices lỗi").strip())
            return
        devices = parse_adb_devices(out)
        self.done.emit(devices, out)


class AdbWorker(QThread):
    done = Signal(str)
    fail = Signal(str)

    def __init__(self, args: List[str], timeout: int = 30, capture_binary_to: Optional[Path] = None):
        super().__init__()
        self.args = args
        self.timeout = timeout
        self.capture_binary_to = capture_binary_to

    def run(self) -> None:
        try:
            if self.capture_binary_to:
                with open(self.capture_binary_to, "wb") as f:
                    p = subprocess.run(
                        self.args,
                        stdout=f,
                        stderr=subprocess.PIPE,
                        timeout=self.timeout,
                        creationflags=CREATE_NO_WINDOW,
                        startupinfo=win_startupinfo(),
                    )
                if p.returncode != 0:
                    self.fail.emit((p.stderr or b"").decode("utf-8", errors="replace") or "Command failed")
                    return
                self.done.emit(str(self.capture_binary_to))
                return

            code, out, err = safe_run(self.args, timeout=self.timeout)
            if code != 0:
                self.fail.emit((err or out or f"Exit code {code}").strip())
                return
            self.done.emit((out or "Xong").strip())
        except Exception as e:
            self.fail.emit(str(e))


def adb_device_screen_size(serial: str) -> Optional[Tuple[int, int]]:
    adb = adb_path()
    if not adb:
        return None
    code, out, err = safe_run([adb, "-s", serial, "shell", "wm", "size"], timeout=8)
    if code != 0:
        return None
    matches = re.findall(r"(\d+)\s*x\s*(\d+)", out or err)
    if not matches:
        return None
    w, h = matches[-1]
    try:
        return max(1, int(w)), max(1, int(h))
    except ValueError:
        return None


class InputSyncController:
    """Relay basic input from one scrcpy window to checked child devices."""

    VK_LBUTTON = 0x01
    VK_RBUTTON = 0x02
    VK_BACK = 0x08
    VK_RETURN = 0x0D
    VK_ESCAPE = 0x1B
    VK_SPACE = 0x20
    VK_LEFT = 0x25
    VK_UP = 0x26
    VK_RIGHT = 0x27
    VK_DOWN = 0x28
    VK_HOME = 0x24
    VK_END = 0x23

    KEY_MAP = {
        VK_ESCAPE: "KEYCODE_BACK",
        VK_BACK: "KEYCODE_DEL",
        VK_RETURN: "KEYCODE_ENTER",
        VK_SPACE: "KEYCODE_SPACE",
        VK_LEFT: "KEYCODE_DPAD_LEFT",
        VK_UP: "KEYCODE_DPAD_UP",
        VK_RIGHT: "KEYCODE_DPAD_RIGHT",
        VK_DOWN: "KEYCODE_DPAD_DOWN",
        VK_HOME: "KEYCODE_HOME",
        VK_END: "KEYCODE_MOVE_END",
    }

    def __init__(self, log_callback, parent: QWidget):
        self.log = log_callback
        self.parent = parent
        self.enabled = False
        self.master_serial = ""
        self.master_title = ""
        self.child_serials: List[str] = []
        self.master_size: Optional[Tuple[int, int]] = None
        self.child_sizes: Dict[str, Tuple[int, int]] = {}
        self.hwnd = None
        self._left_down = False
        self._right_down = False
        self._drag_start: Optional[Tuple[int, int, int, float]] = None
        self._key_down: Dict[int, bool] = {}
        self.timer = QTimer(parent)
        self.timer.timeout.connect(self._poll)

    def start(self, master_serial: str, master_title: str, child_serials: List[str]) -> bool:
        if not IS_WINDOWS:
            self.log("Dong bo thao tac hien chi ho tro Windows.")
            return False
        self.master_serial = master_serial
        self.master_title = master_title
        self.child_serials = [s for s in child_serials if s and s != master_serial]
        self.master_size = adb_device_screen_size(master_serial)
        self.child_sizes = {}
        for serial in self.child_serials:
            size = adb_device_screen_size(serial)
            if size:
                self.child_sizes[serial] = size
        if not self.master_size:
            self.log(f"{master_serial}: khong doc duoc kich thuoc man hinh Android.")
            return False
        if not self.child_sizes:
            self.log("Chua co may con hop le de dong bo. Hay tick cac may con dang online.")
            return False
        self.hwnd = self._find_window()
        self.enabled = True
        self._left_down = False
        self._right_down = False
        self._drag_start = None
        self._key_down = {}
        self.timer.start(35)
        self.log(f"Dong bo BAT: may chinh {master_serial} -> {len(self.child_sizes)} may con.")
        return True

    def stop(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
        if self.enabled:
            self.log("Dong bo thao tac da tat.")
        self.enabled = False
        self.hwnd = None
        self._left_down = False
        self._right_down = False
        self._drag_start = None

    def update_children(self, child_serials: List[str]) -> None:
        if not self.enabled:
            return
        self.start(self.master_serial, self.master_title, child_serials)

    def _find_window(self):
        if not IS_WINDOWS:
            return None
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, self.master_title)
        if hwnd:
            return hwnd

        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(candidate, _):
            length = user32.GetWindowTextLengthW(candidate)
            if length <= 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(candidate, buff, length + 1)
            if self.master_title in buff.value:
                found.append(candidate)
                return False
            return True

        user32.EnumWindows(enum_proc, 0)
        return found[0] if found else None

    def _client_rect_on_screen(self):
        if not IS_WINDOWS:
            return None
        if not self.hwnd or not ctypes.windll.user32.IsWindow(self.hwnd):
            self.hwnd = self._find_window()
        if not self.hwnd:
            return None
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetClientRect(self.hwnd, ctypes.byref(rect)):
            return None
        point = wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(self.hwnd, ctypes.byref(point))
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)
        return point.x, point.y, width, height

    def _cursor_pos(self) -> Optional[Tuple[int, int]]:
        if not IS_WINDOWS:
            return None
        point = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
        return None

    def _map_cursor_to_master(self, screen_x: int, screen_y: int) -> Optional[Tuple[int, int]]:
        rect = self._client_rect_on_screen()
        if not rect or not self.master_size:
            return None
        left, top, client_w, client_h = rect
        local_x = screen_x - left
        local_y = screen_y - top
        if local_x < 0 or local_y < 0 or local_x > client_w or local_y > client_h:
            return None

        android_w, android_h = self.master_size
        scale = min(client_w / android_w, client_h / android_h)
        video_w = android_w * scale
        video_h = android_h * scale
        offset_x = (client_w - video_w) / 2
        offset_y = (client_h - video_h) / 2
        if local_x < offset_x or local_y < offset_y:
            return None
        if local_x > offset_x + video_w or local_y > offset_y + video_h:
            return None

        x = int(round((local_x - offset_x) / video_w * android_w))
        y = int(round((local_y - offset_y) / video_h * android_h))
        x = max(0, min(android_w - 1, x))
        y = max(0, min(android_h - 1, y))
        return x, y

    def _is_foreground_master(self) -> bool:
        if not IS_WINDOWS:
            return False
        if not self.hwnd or not ctypes.windll.user32.IsWindow(self.hwnd):
            self.hwnd = self._find_window()
        return bool(self.hwnd and ctypes.windll.user32.GetForegroundWindow() == self.hwnd)

    def _poll(self) -> None:
        if not self.enabled:
            return
        pos = self._cursor_pos()
        mapped = self._map_cursor_to_master(*pos) if pos else None
        left_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(self.VK_LBUTTON) & 0x8000)
        right_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(self.VK_RBUTTON) & 0x8000)

        if left_pressed and not self._left_down and mapped:
            self._drag_start = (mapped[0], mapped[1], int(time.time() * 1000), time.time())
        elif not left_pressed and self._left_down and self._drag_start and mapped:
            start_x, start_y, start_ms, _ = self._drag_start
            end_x, end_y = mapped
            duration = max(50, min(2000, int(time.time() * 1000) - start_ms))
            if abs(end_x - start_x) <= 8 and abs(end_y - start_y) <= 8 and duration < 350:
                self._send_touch("tap", start_x, start_y)
            else:
                self._send_touch("swipe", start_x, start_y, end_x, end_y, duration)
            self._drag_start = None
        elif not left_pressed:
            self._drag_start = None
        self._left_down = left_pressed

        if right_pressed and not self._right_down and mapped:
            self._send_key("KEYCODE_BACK")
        self._right_down = right_pressed

        if self._is_foreground_master():
            for vk, keycode in self.KEY_MAP.items():
                pressed = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
                if pressed and not self._key_down.get(vk, False):
                    self._send_key(keycode)
                self._key_down[vk] = pressed

    def _scale_point(self, serial: str, x: int, y: int) -> Tuple[int, int]:
        master_w, master_h = self.master_size or (1, 1)
        child_w, child_h = self.child_sizes.get(serial, (master_w, master_h))
        return (
            max(0, min(child_w - 1, int(round(x / master_w * child_w)))),
            max(0, min(child_h - 1, int(round(y / master_h * child_h)))),
        )

    def _send_touch(self, kind: str, *values: int) -> None:
        commands = []
        for serial in self.child_serials:
            if serial not in self.child_sizes:
                continue
            if kind == "tap":
                x, y = self._scale_point(serial, values[0], values[1])
                commands.append((serial, f"input tap {x} {y}"))
            elif kind == "swipe":
                x1, y1 = self._scale_point(serial, values[0], values[1])
                x2, y2 = self._scale_point(serial, values[2], values[3])
                duration = int(values[4])
                commands.append((serial, f"input swipe {x1} {y1} {x2} {y2} {duration}"))
        self._run_async(commands)

    def _send_key(self, keycode: str) -> None:
        self._run_async([(serial, f"input keyevent {keycode}") for serial in self.child_serials])

    def _run_async(self, commands: List[Tuple[str, str]]) -> None:
        adb = adb_path()
        if not adb or not commands:
            return

        def runner() -> None:
            for serial, shell_cmd in commands:
                try:
                    subprocess.Popen(
                        [adb, "-s", serial, "shell", shell_cmd],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=CREATE_NO_WINDOW,
                        startupinfo=win_startupinfo(),
                    )
                except Exception as e:
                    self.log(f"Loi dong bo {serial}: {e}")

        threading.Thread(target=runner, daemon=True).start()


class ScrcpyProcessManager:
    def __init__(self, log_callback):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.window_titles: Dict[str, str] = {}
        self.log = log_callback

    def is_running(self, serial: str) -> bool:
        p = self.processes.get(serial)
        return bool(p and p.poll() is None)

    def cleanup_dead(self) -> None:
        dead = [s for s, p in self.processes.items() if p.poll() is not None]
        for serial in dead:
            self.processes.pop(serial, None)
            self.window_titles.pop(serial, None)

    def start(
        self,
        serial: str,
        profile: DeviceProfile,
        window_title: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> bool:
        self.cleanup_dead()
        if self.is_running(serial):
            self.log(f"{serial}: scrcpy đang chạy, bỏ qua.")
            return True

        scr = scrcpy_path()
        if not scr:
            self.log("Không tìm thấy scrcpy.exe. Đặt vào tools/scrcpy hoặc cài vào PATH.")
            return False

        p = profile.merged_with_quality()
        args = [
            scr,
            "-s",
            serial,
            "--window-title",
            window_title,
            "--window-width",
            str(p.window_width),
            "--window-height",
            str(p.window_height),
            "--max-size",
            str(p.max_size),
            "--video-bit-rate",
            str(p.bitrate),
            "--max-fps",
            str(p.max_fps),
            '--keyboard=sdk',
            '--prefer-text',
        ]

        if p.no_audio:
            args.append("--no-audio")
        if p.turn_screen_off:
            args.append("--turn-screen-off")
        if p.power_off_on_close:
            args.append("--power-off-on-close")
        if p.stay_awake:
            args.append("--stay-awake")
        if x is not None:
            args += ["--window-x", str(x)]
        if y is not None:
            args += ["--window-y", str(y)]

        try:
            log_file = LOG_DIR / f"scrcpy_{serial.replace(':', '_')}_{now_stamp()}.log"
            lf = open(log_file, "w", encoding="utf-8", errors="replace")
            proc = subprocess.Popen(
                args,
                cwd=str(Path(scr).parent),
                stdout=lf,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                startupinfo=win_startupinfo(),
            )
            self.processes[serial] = proc
            self.window_titles[serial] = window_title
            self.log(f"Mở scrcpy: {window_title} | {serial}")
            return True
        except Exception as e:
            self.log(f"Lỗi mở scrcpy {serial}: {e}")
            return False

    def _send_sleep_key(self, serial: str) -> None:
        adb = adb_path()
        if not adb:
            self.log(f"{serial}: không tìm thấy adb để tắt màn hình.")
            return
        code, out, err = safe_run([adb, "-s", serial, "shell", "input", "keyevent", "KEYCODE_SLEEP"], timeout=6)
        if code != 0:
            self.log(f"{serial}: lỗi tắt màn hình bằng ADB: {(err or out).strip()}")

    def stop(self, serial: str, keep_screen_off: bool = False) -> None:
        p = self.processes.get(serial)
        if not p:
            if keep_screen_off:
                self._send_sleep_key(serial)
            else:
                self.log(f"{serial}: không có scrcpy đang quản lý.")
            return
        if keep_screen_off:
            self._send_sleep_key(serial)
        if p.poll() is None:
            try:
                p.terminate()
                time.sleep(0.5)
                if p.poll() is None:
                    p.kill()
            except Exception as e:
                self.log(f"Lỗi tắt scrcpy {serial}: {e}")
        self.processes.pop(serial, None)
        self.window_titles.pop(serial, None)
        if keep_screen_off:
            time.sleep(0.2)
            self._send_sleep_key(serial)
        self.log(f"Tắt scrcpy: {serial}")

    def stop_all(self, keep_screen_off_serials: Optional[set] = None) -> None:
        keep_screen_off_serials = keep_screen_off_serials or set()
        for serial in list(self.processes.keys()):
            self.stop(serial, keep_screen_off=serial in keep_screen_off_serials)

    def __del__(self):
        # Không bắt buộc tắt scrcpy khi app đóng, nhưng sẽ tắt các process do app quản lý.
        try:
            self.stop_all()
        except Exception:
            pass


class MainWindow(QMainWindow):
    COL_CHECK = 0
    COL_INDEX = 1
    COL_NAME = 2
    COL_SERIAL = 3
    COL_MODEL = 4
    COL_STATE = 5
    COL_GROUP = 6
    COL_PACKAGE = 7
    COL_SCRCPY = 8

    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.config = ConfigStore()
        self.devices: Dict[str, AndroidDevice] = {}
        self.scanner: Optional[DeviceScanner] = None
        self.workers: List[AdbWorker] = []
        self.scrcpy = ScrcpyProcessManager(self.append_log)
        self.input_sync = InputSyncController(self.append_log, self)
        self.master_serial = ""
        self.master_title = ""
        self.setWindowTitle(APP_NAME)
        self._icon_path = apply_window_icon(self)
        self.resize(1480, 860)
        self._build_ui()
        self._apply_settings_to_ui()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_running_state)
        self.refresh_timer.start(1000)

        self.auto_scan_timer = QTimer(self)
        self.auto_scan_timer.timeout.connect(self.scan_devices)
        self.auto_scan_toggle.stateChanged.connect(self._toggle_auto_scan)

        self.scan_devices()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.status_label = QLabel("")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        toolbar = QHBoxLayout()
        self.btn_scan = QPushButton("Quét thiết bị")
        self.btn_open_selected = QPushButton("Nhúng scrcpy đã chọn")
        self.btn_close_selected = QPushButton("Tắt scrcpy đã chọn")
        self.btn_open_all = QPushButton("Mở tất cả (cửa sổ riêng)")
        self.btn_close_all = QPushButton("Tắt tất cả")
        self.btn_save_profile = QPushButton("Lưu profile")
        self.auto_scan_toggle = QCheckBox("Tự quét")

        for b in [
            self.btn_scan,
            self.btn_open_selected,
            self.btn_close_selected,
            self.btn_open_all,
            self.btn_close_all,
            self.btn_save_profile,
        ]:
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        toolbar.addWidget(self.auto_scan_toggle)

        self.btn_scan.clicked.connect(self.scan_devices)
        self.btn_open_selected.clicked.connect(self.open_selected)
        self.btn_close_selected.clicked.connect(self.close_selected)
        self.btn_open_all.clicked.connect(self.open_all_online)
        self.btn_close_all.clicked.connect(self.close_all)
        self.btn_save_profile.clicked.connect(self.save_selected_profile)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["", "#", "Tên máy", "Serial", "Model", "Trạng thái", "Nhóm", "Package mặc định", "Scrcpy"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.load_selected_profile_to_form)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_INDEX, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_SERIAL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_MODEL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_GROUP, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_PACKAGE, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_SCRCPY, QHeaderView.ResizeToContents)

        splitter = QSplitter(Qt.Vertical)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.addLayout(toolbar)
        top_layout.addWidget(self.status_label)
        top_layout.addWidget(self.table)

        bottom_tabs = QTabWidget()
        bottom_tabs.addTab(self._build_profile_tab(), "Profile / Lệnh máy")
        bottom_tabs.addTab(self._build_layout_tab(), "Bố cục scrcpy")
        self.auto_upload_tab = AutoUploadTab(
            adb_locator=adb_path,
            selected_serials=self.selected_serials,
            is_online=lambda serial: bool(self.devices.get(serial) and self.devices[serial].is_online),
            parent=self,
        )
        bottom_tabs.addTab(self.auto_upload_tab, "Auto Upload")
        bottom_tabs.addTab(self._build_log_tab(), "Nhật ký")

        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([230, 650])
        layout.addWidget(splitter)

        # Màn hình điện thoại luôn nằm trong ứng dụng, kể cả khi mở tab Auto Upload.
        self.phone_panel = PhonePreviewPanel(self)
        self.phone_dock = QDockWidget("Màn hình điện thoại - scrcpy trực tiếp", self)
        self.phone_dock.setObjectName("embeddedPhoneDock")
        self.phone_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.phone_dock.setMinimumWidth(310)
        self.phone_dock.setWidget(self.phone_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.phone_dock)
        self.phone_panel.request_embed.connect(self.embed_selected_phone)
        self.phone_panel.request_external.connect(self.detach_preview_phone)
        self.phone_panel.request_stop.connect(self.stop_preview_phone)
        self.phone_panel.request_home.connect(lambda: self.phone_keyevent("KEYCODE_HOME"))
        self.phone_panel.request_back.connect(lambda: self.phone_keyevent("KEYCODE_BACK"))
        self.phone_panel.viewport.message.connect(self.append_log)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("Tệp")
        act_open_config = QAction("Mở thư mục cấu hình", self)
        act_open_tools = QAction("Mở thư mục tools", self)
        act_open_screens = QAction("Mở thư mục ảnh chụp màn hình", self)
        act_exit = QAction("Thoát", self)
        file_menu.addAction(act_open_config)
        file_menu.addAction(act_open_tools)
        file_menu.addAction(act_open_screens)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)
        act_open_config.triggered.connect(lambda: self.open_folder(CONFIG_DIR))
        act_open_tools.triggered.connect(lambda: self.open_folder(TOOLS_DIR))
        act_open_screens.triggered.connect(lambda: self.open_folder(SCREENSHOT_DIR))
        act_exit.triggered.connect(self.close)

    def _build_profile_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        grid = QGridLayout()

        profile_box = QGroupBox("Profile máy đang chọn")
        form = QFormLayout(profile_box)
        self.name_edit = QLineEdit()
        self.group_edit = QLineEdit()
        self.package_edit = QLineEdit()
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(list(QUALITY_PRESETS.keys()))
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(240, 4096)
        self.max_size_spin.setSingleStep(80)
        self.bitrate_edit = QLineEdit()
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 240)
        self.no_audio_check = QCheckBox("Tắt audio để nhẹ máy")
        self.stay_awake_check = QCheckBox("Giữ máy thức / không ngủ khi scrcpy chạy")
        self.turn_screen_off_check = QCheckBox("Tắt màn hình điện thoại khi điều khiển")
        self.power_off_on_close_check = QCheckBox("Giữ màn hình tắt sau khi thoát scrcpy")
        self.win_w_spin = QSpinBox()
        self.win_w_spin.setRange(160, 5000)
        self.win_h_spin = QSpinBox()
        self.win_h_spin.setRange(160, 5000)

        form.addRow("Tên hiển thị", self.name_edit)
        form.addRow("Nhóm / kèo", self.group_edit)
        form.addRow("Package mặc định", self.package_edit)
        form.addRow("Chất lượng", self.quality_combo)
        form.addRow("Max size", self.max_size_spin)
        form.addRow("Bitrate", self.bitrate_edit)
        form.addRow("FPS", self.fps_spin)
        form.addRow("", self.no_audio_check)
        form.addRow("", self.stay_awake_check)
        form.addRow("", self.turn_screen_off_check)
        form.addRow("", self.power_off_on_close_check)
        form.addRow("Rộng cửa sổ", self.win_w_spin)
        form.addRow("Cao cửa sổ", self.win_h_spin)

        command_box = QGroupBox("Lệnh nhanh")
        cmd_layout = QGridLayout(command_box)
        self.btn_launch_app = QPushButton("Mở app package")
        self.btn_force_stop = QPushButton("Tắt cưỡng bức app")
        self.btn_restart_app = QPushButton("Khởi động lại app")
        self.btn_reboot = QPushButton("Reboot máy")
        self.btn_screenshot = QPushButton("Chụp màn hình")
        self.btn_adb_shell = QPushButton("Chạy ADB shell")
        self.shell_edit = QLineEdit()
        self.shell_edit.setPlaceholderText("Ví dụ: input keyevent KEYCODE_HOME")
        self.btn_open_settings = QPushButton("Mở Cài đặt Android")
        self.btn_home = QPushButton("Nút Home")
        self.btn_back = QPushButton("Nút Back")
        self.btn_screen_off_now = QPushButton("Tắt màn hình ngay")
        self.btn_screen_on_now = QPushButton("Bật màn hình")

        cmd_layout.addWidget(self.btn_launch_app, 0, 0)
        cmd_layout.addWidget(self.btn_force_stop, 0, 1)
        cmd_layout.addWidget(self.btn_restart_app, 0, 2)
        cmd_layout.addWidget(self.btn_reboot, 1, 0)
        cmd_layout.addWidget(self.btn_screenshot, 1, 1)
        cmd_layout.addWidget(self.btn_open_settings, 1, 2)
        cmd_layout.addWidget(self.btn_home, 2, 0)
        cmd_layout.addWidget(self.btn_back, 2, 1)
        cmd_layout.addWidget(self.btn_screen_off_now, 2, 2)
        cmd_layout.addWidget(self.btn_screen_on_now, 3, 0)
        cmd_layout.addWidget(self.shell_edit, 4, 0, 1, 2)
        cmd_layout.addWidget(self.btn_adb_shell, 4, 2)

        self.btn_launch_app.clicked.connect(self.launch_app_selected)
        self.btn_force_stop.clicked.connect(self.force_stop_selected)
        self.btn_restart_app.clicked.connect(self.restart_app_selected)
        self.btn_reboot.clicked.connect(self.reboot_selected)
        self.btn_screenshot.clicked.connect(self.screenshot_selected)
        self.btn_open_settings.clicked.connect(lambda: self.adb_activity_selected("android.settings.SETTINGS"))
        self.btn_home.clicked.connect(lambda: self.adb_keyevent_selected("KEYCODE_HOME"))
        self.btn_back.clicked.connect(lambda: self.adb_keyevent_selected("KEYCODE_BACK"))
        self.btn_screen_off_now.clicked.connect(self.screen_off_selected)
        self.btn_screen_on_now.clicked.connect(self.screen_on_selected)
        self.btn_adb_shell.clicked.connect(self.run_shell_selected)

        grid.addWidget(profile_box, 0, 0)
        grid.addWidget(command_box, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)
        return w

    def _build_layout_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        box = QGroupBox("Tự động xếp cửa sổ scrcpy")
        form = QFormLayout(box)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.margin_x_spin = QSpinBox()
        self.margin_x_spin.setRange(-5000, 10000)
        self.margin_y_spin = QSpinBox()
        self.margin_y_spin.setRange(-5000, 10000)
        self.gap_x_spin = QSpinBox()
        self.gap_x_spin.setRange(0, 500)
        self.gap_y_spin = QSpinBox()
        self.gap_y_spin.setRange(0, 500)
        self.default_w_spin = QSpinBox()
        self.default_w_spin.setRange(160, 5000)
        self.default_h_spin = QSpinBox()
        self.default_h_spin.setRange(160, 5000)
        self.master_w_spin = QSpinBox()
        self.master_w_spin.setRange(240, 5000)
        self.master_h_spin = QSpinBox()
        self.master_h_spin.setRange(240, 5000)
        self.auto_scan_spin = QSpinBox()
        self.auto_scan_spin.setRange(2, 300)

        form.addRow("Số cột", self.cols_spin)
        form.addRow("Lề trái X", self.margin_x_spin)
        form.addRow("Lề trên Y", self.margin_y_spin)
        form.addRow("Khoảng cách ngang", self.gap_x_spin)
        form.addRow("Khoảng cách dọc", self.gap_y_spin)
        form.addRow("Rộng mặc định", self.default_w_spin)
        form.addRow("Cao mặc định", self.default_h_spin)
        form.addRow("Rong may chinh", self.master_w_spin)
        form.addRow("Cao may chinh", self.master_h_spin)
        form.addRow("Tự quét mỗi giây", self.auto_scan_spin)

        row = QHBoxLayout()
        self.btn_save_layout = QPushButton("Lưu cấu hình bố cục")
        self.btn_preview_layout = QPushButton("Mở tất cả theo bố cục")
        self.btn_save_layout.clicked.connect(self.save_layout_settings)
        self.btn_preview_layout.clicked.connect(self.open_all_online)
        row.addWidget(self.btn_save_layout)
        row.addWidget(self.btn_preview_layout)
        row.addStretch(1)

        help_text = QLabel(
            "Gợi ý: nếu chạy nhiều máy, dùng preset Thấp/Cân bằng, --no-audio, cửa sổ 300x600 hoặc 360x720."
        )
        help_text.setWordWrap(True)

        sync_box = QGroupBox("May chinh phong to va dong bo thao tac")
        sync_layout = QVBoxLayout(sync_box)
        sync_row = QHBoxLayout()
        self.btn_open_master = QPushButton("Mo may chinh giua man hinh")
        self.sync_toggle = QCheckBox("Dong bo thao tac sang may con")
        self.sync_status_label = QLabel("May chinh: chua mo. May con: tick cac dong can nhan thao tac.")
        self.sync_status_label.setWordWrap(True)
        self.btn_open_master.clicked.connect(self.open_master_centered)
        self.sync_toggle.stateChanged.connect(self.toggle_input_sync)
        sync_row.addWidget(self.btn_open_master)
        sync_row.addWidget(self.sync_toggle)
        sync_row.addStretch(1)
        sync_layout.addLayout(sync_row)
        sync_layout.addWidget(self.sync_status_label)

        layout.addWidget(box)
        layout.addLayout(row)
        layout.addWidget(sync_box)
        layout.addWidget(help_text)
        layout.addStretch(1)
        return w

    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(2000)
        layout.addWidget(self.log_box)
        return w

    def _apply_settings_to_ui(self) -> None:
        s = self.config.settings
        self.cols_spin.setValue(int(s["layout_columns"]))
        self.margin_x_spin.setValue(int(s["layout_margin_x"]))
        self.margin_y_spin.setValue(int(s["layout_margin_y"]))
        self.gap_x_spin.setValue(int(s["layout_gap_x"]))
        self.gap_y_spin.setValue(int(s["layout_gap_y"]))
        self.default_w_spin.setValue(int(s["default_window_width"]))
        self.default_h_spin.setValue(int(s["default_window_height"]))
        self.master_w_spin.setValue(int(s.get("master_window_width", 540)))
        self.master_h_spin.setValue(int(s.get("master_window_height", 960)))
        self.auto_scan_spin.setValue(int(s["auto_scan_seconds"]))
        self._update_paths_label()

    def _update_paths_label(self) -> None:
        adb = adb_path() or "KHÔNG TÌM THẤY"
        scr = scrcpy_path() or "KHÔNG TÌM THẤY"
        self.status_label.setText(f"ADB: {adb}   |   scrcpy: {scr}")

    def _toggle_auto_scan(self):
        if self.auto_scan_toggle.isChecked():
            self.auto_scan_timer.start(max(2, self.auto_scan_spin.value()) * 1000)
        else:
            self.auto_scan_timer.stop()

    def append_log(self, msg: str) -> None:
        self.log_box.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def open_folder(self, path: Path) -> None:
        path.mkdir(exist_ok=True)
        if IS_WINDOWS:
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def scan_devices(self) -> None:
        if self.scanner and self.scanner.isRunning():
            return
        self._update_paths_label()
        self.append_log("Đang quét ADB devices...")
        self.scanner = DeviceScanner()
        self.scanner.done.connect(self.on_scan_done)
        self.scanner.fail.connect(self.on_scan_fail)
        self.scanner.start()

    def on_scan_done(self, devices: List[AndroidDevice], raw: str) -> None:
        self.devices = {d.serial: d for d in devices}
        for d in devices:
            self.config.profile_for(d)
        self.config.save()
        self.populate_table()
        self.append_log(f"Tìm thấy {len(devices)} thiết bị.")
        if any(d.state == "unauthorized" for d in devices):
            self.append_log("Có máy unauthorized: mở điện thoại và bấm Allow USB debugging.")
        self._update_paths_label()

    def on_scan_fail(self, msg: str) -> None:
        self.append_log(f"Lỗi scan: {msg}")
        QMessageBox.warning(self, "Lỗi quét ADB", msg)

    def selected_serials(self, checked_only: bool = False) -> List[str]:
        serials = []
        if checked_only:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, self.COL_CHECK)
                if item and item.checkState() == Qt.Checked:
                    serial = self.table.item(row, self.COL_SERIAL).text()
                    serials.append(serial)
            return serials

        rows = sorted(set(i.row() for i in self.table.selectedItems()))
        for row in rows:
            item = self.table.item(row, self.COL_SERIAL)
            if item:
                serials.append(item.text())

        if not serials:
            return self.selected_serials(checked_only=True)
        return serials

    def current_serial(self) -> Optional[str]:
        serials = self.selected_serials()
        return serials[0] if serials else None

    def populate_table(self) -> None:
        self.scrcpy.cleanup_dead()
        checked_before = set(self.selected_serials(checked_only=True)) if hasattr(self, "table") else set()
        devices = list(self.devices.values())
        devices.sort(key=lambda d: (not d.is_online, d.display_model, d.serial))
        self.table.setRowCount(len(devices))

        for row, d in enumerate(devices):
            profile = self.config.profile_for(d)
            values = [
                "",
                str(row + 1),
                profile.name or d.display_model,
                d.serial,
                d.display_model,
                d.state,
                profile.group,
                profile.default_package,
                "Đang chạy" if self.scrcpy.is_running(d.serial) else "Đã tắt",
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == self.COL_CHECK:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                    item.setCheckState(Qt.Checked if d.serial in checked_before else Qt.Unchecked)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                if col == self.COL_STATE:
                    if d.state == "device":
                        item.setForeground(QColor("#007a2f"))
                    elif d.state == "unauthorized":
                        item.setForeground(QColor("#c77700"))
                    else:
                        item.setForeground(QColor("#b00020"))

                if col == self.COL_SCRCPY:
                    if self.scrcpy.is_running(d.serial):
                        item.setForeground(QColor("#007a2f"))
                    else:
                        item.setForeground(QColor("#666666"))

                self.table.setItem(row, col, item)

        self.table.resizeRowsToContents()

    def refresh_running_state(self) -> None:
        self.scrcpy.cleanup_dead()
        for row in range(self.table.rowCount()):
            serial_item = self.table.item(row, self.COL_SERIAL)
            state_item = self.table.item(row, self.COL_SCRCPY)
            if not serial_item or not state_item:
                continue
            serial = serial_item.text()
            running = self.scrcpy.is_running(serial)
            state_item.setText("Đang chạy" if running else "Đã tắt")
            state_item.setForeground(QColor("#007a2f") if running else QColor("#666666"))
        if self.master_serial and self.input_sync.enabled and not self.scrcpy.is_running(self.master_serial):
            self.input_sync.stop()
            self._set_sync_toggle_checked(False)
            self.sync_status_label.setText("Dong bo TAT. May chinh da tat.")

    def load_selected_profile_to_form(self) -> None:
        serial = self.current_serial()
        if not serial:
            return
        device = self.devices.get(serial)
        if not device:
            return
        p = self.config.profile_for(device)
        self.name_edit.setText(p.name)
        self.group_edit.setText(p.group)
        self.package_edit.setText(p.default_package)
        self.quality_combo.setCurrentText(normalize_quality_name(p.quality))
        self.max_size_spin.setValue(int(p.max_size))
        self.bitrate_edit.setText(p.bitrate)
        self.fps_spin.setValue(int(p.max_fps))
        self.no_audio_check.setChecked(bool(p.no_audio))
        self.stay_awake_check.setChecked(bool(p.stay_awake))
        self.turn_screen_off_check.setChecked(bool(p.turn_screen_off))
        self.power_off_on_close_check.setChecked(bool(p.power_off_on_close))
        self.win_w_spin.setValue(int(p.window_width))
        self.win_h_spin.setValue(int(p.window_height))

    def form_to_profile(self) -> DeviceProfile:
        return DeviceProfile(
            name=self.name_edit.text().strip(),
            group=self.group_edit.text().strip(),
            default_package=self.package_edit.text().strip(),
            quality=normalize_quality_name(self.quality_combo.currentText()),
            max_size=int(self.max_size_spin.value()),
            bitrate=self.bitrate_edit.text().strip() or "3M",
            max_fps=int(self.fps_spin.value()),
            no_audio=self.no_audio_check.isChecked(),
            stay_awake=self.stay_awake_check.isChecked(),
            turn_screen_off=self.turn_screen_off_check.isChecked(),
            power_off_on_close=self.power_off_on_close_check.isChecked(),
            window_width=int(self.win_w_spin.value()),
            window_height=int(self.win_h_spin.value()),
        )

    def save_selected_profile(self) -> None:
        serials = self.selected_serials()
        if not serials:
            QMessageBox.information(self, "Chưa chọn máy", "Chọn ít nhất 1 máy trong bảng.")
            return
        p = self.form_to_profile()
        for serial in serials:
            old = self.config.profiles.get(serial, DeviceProfile())
            merged = DeviceProfile(
                name=p.name or old.name,
                group=p.group,
                default_package=p.default_package,
                quality=p.quality,
                max_size=p.max_size,
                bitrate=p.bitrate,
                max_fps=p.max_fps,
                no_audio=p.no_audio,
                stay_awake=p.stay_awake,
                turn_screen_off=p.turn_screen_off,
                power_off_on_close=p.power_off_on_close,
                window_width=p.window_width,
                window_height=p.window_height,
            )
            # Nếu lưu cho nhiều máy, không ép tất cả cùng tên.
            if len(serials) > 1:
                merged.name = old.name or serial
            self.config.profiles[serial] = merged
        self.config.save()
        self.populate_table()
        self.append_log(f"Đã lưu profile cho {len(serials)} máy.")

    def save_current_profile_silent(self) -> bool:
        """Lưu riêng profile của máy đang chọn, không hiện popup và không reload bảng.

        Lý do: các tùy chọn scrcpy như --turn-screen-off / --power-off-on-close
        chỉ có hiệu lực lúc mở scrcpy. Nếu người dùng tick xong bấm Mở scrcpy
        mà chưa bấm Lưu profile, app phải tự lưu trước khi tạo process.
        """
        serial = self.current_serial()
        if not serial:
            return False
        old = self.config.profiles.get(serial, DeviceProfile())
        p = self.form_to_profile()
        if not p.name:
            p.name = old.name or serial
        self.config.profiles[serial] = p
        self.config.save()
        return True

    def save_layout_settings(self) -> None:
        self.config.settings.update(
            {
                "layout_columns": int(self.cols_spin.value()),
                "layout_margin_x": int(self.margin_x_spin.value()),
                "layout_margin_y": int(self.margin_y_spin.value()),
                "layout_gap_x": int(self.gap_x_spin.value()),
                "layout_gap_y": int(self.gap_y_spin.value()),
                "default_window_width": int(self.default_w_spin.value()),
                "default_window_height": int(self.default_h_spin.value()),
                "master_window_width": int(self.master_w_spin.value()),
                "master_window_height": int(self.master_h_spin.value()),
                "auto_scan_seconds": int(self.auto_scan_spin.value()),
            }
        )
        self.config.save()
        self._toggle_auto_scan()
        self.append_log("Đã lưu cấu hình bố cục.")

    def layout_position_for_index(self, index: int, profile: DeviceProfile) -> Tuple[int, int]:
        cols = max(1, self.cols_spin.value())
        mx = self.margin_x_spin.value()
        my = self.margin_y_spin.value()
        gx = self.gap_x_spin.value()
        gy = self.gap_y_spin.value()
        col = index % cols
        row = index // cols
        w = profile.window_width
        h = profile.window_height
        return mx + col * (w + gx), my + row * (h + gy)

    def center_position_for_window(self, width: int, height: int) -> Tuple[int, int]:
        screen = QApplication.primaryScreen()
        if not screen:
            return 0, 0
        geo = screen.availableGeometry()
        x = geo.x() + max(0, (geo.width() - width) // 2)
        y = geo.y() + max(0, (geo.height() - height) // 2)
        return x, y

    def checked_child_serials_for_master(self, master_serial: str) -> List[str]:
        children = []
        for serial in self.selected_serials(checked_only=True):
            device = self.devices.get(serial)
            if serial != master_serial and device and device.is_online:
                children.append(serial)
        return children

    def _set_sync_toggle_checked(self, checked: bool) -> None:
        self.sync_toggle.blockSignals(True)
        self.sync_toggle.setChecked(checked)
        self.sync_toggle.blockSignals(False)

    def open_master_centered(self) -> None:
        self.save_current_profile_silent()
        serial = self.current_serial()
        if not serial:
            QMessageBox.information(self, "Chua chon may", "Chon 1 dong lam may chinh.")
            return
        device = self.devices.get(serial)
        if not device or not device.is_online:
            QMessageBox.warning(self, "May chinh offline", "May chinh phai o trang thai device.")
            return

        profile = self.config.profile_for(device).merged_with_quality()
        width = int(self.master_w_spin.value())
        height = int(self.master_h_spin.value())
        profile.window_width = width
        profile.window_height = height
        profile.max_size = max(int(profile.max_size), min(4096, max(width, height)))
        x, y = self.center_position_for_window(width, height)
        title = f"MASTER - {profile.name or device.display_model} - {serial}"

        if self.scrcpy.is_running(serial):
            if self.phone_panel.viewport.serial == serial:
                self.phone_panel.viewport.release(restore=True)
            self.scrcpy.stop(serial, keep_screen_off=False)
            time.sleep(0.2)
        if not self.scrcpy.start(serial, profile, title, x=x, y=y):
            return

        self.master_serial = serial
        self.master_title = title
        children = self.checked_child_serials_for_master(serial)
        self.sync_status_label.setText(
            f"May chinh: {serial}. May con dang tick: {len(children)}. Co the keo/resize cua so scrcpy truc tiep tren Windows."
        )
        if self.sync_toggle.isChecked():
            self.start_input_sync_or_turn_off()
        self.refresh_running_state()

    def start_input_sync_or_turn_off(self) -> None:
        if not self.master_serial or not self.master_title:
            QMessageBox.information(self, "Chua mo may chinh", "Bam 'Mo may chinh giua man hinh' truoc.")
            self._set_sync_toggle_checked(False)
            return
        if not self.scrcpy.is_running(self.master_serial):
            QMessageBox.warning(self, "May chinh da tat", "Mo lai may chinh truoc khi bat dong bo.")
            self._set_sync_toggle_checked(False)
            return
        children = self.checked_child_serials_for_master(self.master_serial)
        if not children:
            QMessageBox.information(self, "Chua co may con", "Tick cac may con can nhan thao tac trong bang.")
            self._set_sync_toggle_checked(False)
            return
        if self.input_sync.start(self.master_serial, self.master_title, children):
            self.sync_status_label.setText(f"Dong bo BAT: {self.master_serial} -> {len(children)} may con.")
        else:
            self._set_sync_toggle_checked(False)
            self.sync_status_label.setText("Dong bo dang tat.")

    def toggle_input_sync(self) -> None:
        if self.sync_toggle.isChecked():
            self.start_input_sync_or_turn_off()
        else:
            self.input_sync.stop()
            if self.master_serial:
                self.sync_status_label.setText(f"Dong bo TAT. May chinh: {self.master_serial}.")
            else:
                self.sync_status_label.setText("Dong bo TAT. May chinh: chua mo.")

    def open_for_serials(self, serials: List[str]) -> None:
        if not serials:
            QMessageBox.information(self, "Chưa chọn máy", "Chọn máy hoặc tick máy cần mở.")
            return

        online_serials = [s for s in serials if self.devices.get(s) and self.devices[s].is_online]
        if not online_serials:
            QMessageBox.warning(self, "Không có máy online", "Không có thiết bị nào ở trạng thái device.")
            return

        for idx, serial in enumerate(online_serials):
            d = self.devices[serial]
            p = self.config.profile_for(d)
            x, y = self.layout_position_for_index(idx, p)
            title = f"{idx + 1:02d} - {p.name or d.display_model} - {serial}"
            self.scrcpy.start(serial, p, title, x=x, y=y)
        self.refresh_running_state()

    def embed_selected_phone(self) -> None:
        # Một màn hình trong dock tại một thời điểm. Các máy khác vẫn quản lý bình thường.
        serials = self.selected_serials()
        if not serials:
            QMessageBox.information(self, "Chưa chọn máy", "Chọn một điện thoại đang online trong bảng.")
            return
        serial = serials[0]
        device = self.devices.get(serial)
        if not device or not device.is_online:
            QMessageBox.warning(self, "Thiết bị offline", f"{serial} chưa sẵn sàng qua ADB.")
            return
        if self.input_sync.enabled and self.master_serial == serial:
            QMessageBox.warning(
                self, "Đang đồng bộ thao tác",
                "Tắt đồng bộ máy chính → máy con trước khi nhúng màn hình máy chính."
            )
            return
        if len(serials) > 1:
            self.append_log(f"Chỉ nhúng máy đầu tiên ({serial}); các máy khác không bị ảnh hưởng.")
        if self.phone_panel.viewport.serial == serial and self.phone_panel.viewport.hwnd:
            self.append_log(f"{serial}: màn hình đã nhúng trong ứng dụng.")
            return
        # Không ghi đè các profile đã lưu bằng form chưa được chọn hoặc chưa nhập.
        profile = self.config.profile_for(device)
        if self.scrcpy.is_running(serial):
            process = self.scrcpy.processes[serial]
            title = self.scrcpy.window_titles.get(serial, "")
            if not title:
                QMessageBox.warning(self, "Thiếu tiêu đề cửa sổ", "Không xác định được phiên scrcpy đang chạy.")
                return
        else:
            title = f"EMBED - {profile.name or device.display_model} - {serial}"
            if not self.scrcpy.start(serial, profile, title):
                return
            process = self.scrcpy.processes[serial]
        self.phone_panel.viewport.begin(serial, process, title)
        self.refresh_running_state()

    def open_selected(self) -> None:
        self.embed_selected_phone()

    def detach_preview_phone(self) -> None:
        serial = self.phone_panel.viewport.serial
        if not serial:
            return
        self.phone_panel.viewport.release(restore=True)
        self.append_log(f"{serial}: đã chuyển scrcpy thành cửa sổ riêng.")

    def stop_preview_phone(self) -> None:
        serial = self.phone_panel.viewport.serial
        if not serial:
            return
        self.phone_panel.viewport.release(restore=True)
        if self.master_serial == serial:
            self.input_sync.stop()
            self._set_sync_toggle_checked(False)
        self.scrcpy.stop(serial, keep_screen_off=self.profile_keep_screen_off(serial))
        self.refresh_running_state()

    def phone_keyevent(self, key: str) -> None:
        serial = self.phone_panel.viewport.serial or self.current_serial()
        if not serial:
            QMessageBox.information(self, "Chưa chọn máy", "Chọn một điện thoại trước.")
            return
        args = self.adb_args(serial, ["shell", "input", "keyevent", key])
        if not args:
            return
        worker = AdbWorker(args, timeout=10)
        worker.done.connect(lambda msg, s=serial: self.append_log(f"{s}: {key} - {msg}"))
        worker.fail.connect(lambda err, s=serial: self.append_log(f"{s}: {key} lỗi - {err}"))
        self.workers.append(worker)
        worker.finished.connect(lambda w=worker: self._worker_finished(w))
        worker.start()

    def open_all_online(self) -> None:
        # Người dùng yêu cầu tất cả ở chế độ cửa sổ ngoài.
        if self.phone_panel.viewport.serial:
            self.detach_preview_phone()
        # Nếu đang sửa profile của một máy, lưu ngay trước khi mở toàn bộ.
        self.save_current_profile_silent()
        serials = [d.serial for d in self.devices.values() if d.is_online]
        self.open_for_serials(serials)

    def profile_keep_screen_off(self, serial: str) -> bool:
        p = self.config.profiles.get(serial)
        return bool(p and p.power_off_on_close)

    def close_selected(self) -> None:
        self.save_current_profile_silent()
        serials = self.selected_serials()
        if self.phone_panel.viewport.serial in serials:
            self.phone_panel.viewport.release(restore=True)
        if self.master_serial in serials:
            self.input_sync.stop()
            self._set_sync_toggle_checked(False)
        for serial in serials:
            self.scrcpy.stop(serial, keep_screen_off=self.profile_keep_screen_off(serial))
        self.refresh_running_state()

    def close_all(self) -> None:
        self.save_current_profile_silent()
        self.phone_panel.viewport.release(restore=True)
        self.input_sync.stop()
        self._set_sync_toggle_checked(False)
        keep = {s for s in self.scrcpy.processes.keys() if self.profile_keep_screen_off(s)}
        self.scrcpy.stop_all(keep_screen_off_serials=keep)
        self.refresh_running_state()

    def adb_args(self, serial: str, extra: List[str]) -> Optional[List[str]]:
        adb = adb_path()
        if not adb:
            QMessageBox.warning(self, "Thiếu adb", "Không tìm thấy adb.exe.")
            return None
        return [adb, "-s", serial] + extra

    def run_adb_for_selected(self, builder, success_prefix: str, timeout: int = 30) -> None:
        serials = self.selected_serials()
        if not serials:
            QMessageBox.information(self, "Chưa chọn máy", "Chọn máy cần chạy lệnh.")
            return

        for serial in serials:
            args = builder(serial)
            if not args:
                continue
            worker = AdbWorker(args, timeout=timeout)
            worker.done.connect(lambda msg, s=serial: self.append_log(f"{success_prefix} {s}: {msg}"))
            worker.fail.connect(lambda err, s=serial: self.append_log(f"Lỗi {s}: {err}"))
            self.workers.append(worker)
            worker.finished.connect(lambda w=worker: self._worker_finished(w))
            worker.start()

    def _worker_finished(self, worker: AdbWorker):
        try:
            self.workers.remove(worker)
        except ValueError:
            pass

    def current_package(self) -> str:
        return self.package_edit.text().strip()

    def launch_app_selected(self) -> None:
        pkg = self.current_package()
        if not pkg:
            QMessageBox.information(self, "Thiếu package", "Nhập package app, ví dụ: com.example.app")
            return
        self.save_selected_profile()
        self.run_adb_for_selected(
            lambda s: self.adb_args(s, ["shell", "monkey", "-p", pkg, "1"]),
            "Mở app",
            timeout=20,
        )

    def force_stop_selected(self) -> None:
        pkg = self.current_package()
        if not pkg:
            QMessageBox.information(self, "Thiếu package", "Nhập package app cần force-stop.")
            return
        self.save_selected_profile()
        self.run_adb_for_selected(
            lambda s: self.adb_args(s, ["shell", "am", "force-stop", pkg]),
            "Tắt cưỡng bức",
            timeout=20,
        )

    def restart_app_selected(self) -> None:
        pkg = self.current_package()
        if not pkg:
            QMessageBox.information(self, "Thiếu package", "Nhập package app cần restart.")
            return
        self.save_selected_profile()
        serials = self.selected_serials()
        if not serials:
            QMessageBox.information(self, "Chưa chọn máy", "Chọn máy cần restart app.")
            return
        for serial in serials:
            args = self.adb_args(
                serial,
                [
                    "shell",
                    f"am force-stop {pkg}; sleep 1; monkey -p {pkg} 1",
                ],
            )
            if not args:
                continue
            worker = AdbWorker(args, timeout=30)
            worker.done.connect(lambda msg, s=serial: self.append_log(f"Khởi động lại app {s}: {msg}"))
            worker.fail.connect(lambda err, s=serial: self.append_log(f"Lỗi restart {s}: {err}"))
            self.workers.append(worker)
            worker.finished.connect(lambda w=worker: self._worker_finished(w))
            worker.start()

    def reboot_selected(self) -> None:
        answer = QMessageBox.question(
            self,
            "Xác nhận reboot",
            "Reboot các máy đang chọn?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.run_adb_for_selected(lambda s: self.adb_args(s, ["reboot"]), "Reboot", timeout=10)

    def screen_off_selected(self) -> None:
        # Lệnh này tắt màn hình ngay cho máy đang chọn; khác với --turn-screen-off chỉ áp dụng lúc mở scrcpy.
        # KEYCODE_SLEEP không phải toggle nên an toàn hơn KEYCODE_POWER.
        self.turn_screen_off_check.setChecked(True)
        self.save_current_profile_silent()
        self.run_adb_for_selected(
            lambda s: self.adb_args(s, ["shell", "input", "keyevent", "KEYCODE_SLEEP"]),
            "Tắt màn hình",
            timeout=10,
        )

    def screen_on_selected(self) -> None:
        self.run_adb_for_selected(
            lambda s: self.adb_args(s, ["shell", "input", "keyevent", "KEYCODE_WAKEUP"]),
            "Bật màn hình",
            timeout=10,
        )

    def screenshot_selected(self) -> None:
        serials = self.selected_serials()
        if not serials:
            QMessageBox.information(self, "Chưa chọn máy", "Chọn máy cần chụp màn hình.")
            return
        adb = adb_path()
        if not adb:
            QMessageBox.warning(self, "Thiếu adb", "Không tìm thấy adb.exe.")
            return
        for serial in serials:
            out_file = SCREENSHOT_DIR / f"{serial.replace(':', '_')}_{now_stamp()}.png"
            worker = AdbWorker([adb, "-s", serial, "exec-out", "screencap", "-p"], timeout=30, capture_binary_to=out_file)
            worker.done.connect(lambda msg, s=serial: self.append_log(f"Đã chụp màn hình {s}: {msg}"))
            worker.fail.connect(lambda err, s=serial: self.append_log(f"Lỗi screenshot {s}: {err}"))
            self.workers.append(worker)
            worker.finished.connect(lambda w=worker: self._worker_finished(w))
            worker.start()

    def adb_activity_selected(self, action: str) -> None:
        self.run_adb_for_selected(
            lambda s: self.adb_args(s, ["shell", "am", "start", "-a", action]),
            "Mở activity",
            timeout=20,
        )

    def adb_keyevent_selected(self, key: str) -> None:
        self.run_adb_for_selected(
            lambda s: self.adb_args(s, ["shell", "input", "keyevent", key]),
            "Keyevent",
            timeout=10,
        )

    def run_shell_selected(self) -> None:
        raw = self.shell_edit.text().strip()
        if not raw:
            QMessageBox.information(self, "Thiếu lệnh", "Nhập lệnh shell, ví dụ: input keyevent KEYCODE_HOME")
            return
        self.run_adb_for_selected(
            lambda s: self.adb_args(s, ["shell", raw]),
            "ADB shell",
            timeout=30,
        )

    def closeEvent(self, event):
        if not self.auto_upload_tab.shutdown():
            event.ignore()
            return
        self.config.save()
        self.phone_panel.viewport.shutdown()
        self.input_sync.stop()
        # Tắt scrcpy do app mở để tránh treo process. Nếu bật giữ màn hình tắt, app sẽ gửi lệnh sleep trước/sau khi tắt.
        keep = {s for s in self.scrcpy.processes.keys() if self.profile_keep_screen_off(s)}
        self.scrcpy.stop_all(keep_screen_off_serials=keep)
        event.accept()


def main() -> int:
    ensure_dirs()
    apply_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_window_icon(app)
    w = MainWindow()
    if w._icon_path:
        w.append_log(f"Icon app: {w._icon_path}")
    else:
        w.append_log("Chưa tìm thấy file icon. Đặt file .ico vào assets/app_icon.ico hoặc assets/app.ico")
    w.showMaximized()
    QTimer.singleShot(0, lambda: w.resizeDocks([w.phone_dock], [425], Qt.Horizontal))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
