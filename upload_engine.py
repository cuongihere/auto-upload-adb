"""ADB video transfer and cautious in-app publishing workflow.

No social credentials, private APIs, or root permissions are used.
Final publishing is opt-in; a tap is never reported as verified publication.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

PACKAGES = {
    "TikTok": "com.zhiliaoapp.musically",
    "Facebook": "com.facebook.katana",
}
EXTENSIONS = {".mp4", ".mov", ".m4v", ".3gp"}
ANDROID_DIR = "/sdcard/DCIM/Camera"
HISTORY = Path(__file__).resolve().parent / "logs" / "auto_upload_history.jsonl"


class UploadError(Exception):
    pass


@dataclass(frozen=True)
class UploadRequest:
    serial: str
    video: Path
    platforms: tuple[str, ...]
    captions: dict[str, str]
    auto_publish: bool = False
    choose_latest: bool = True


def write_history(data: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(), **data}
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class ADB:
    def __init__(self, executable: str, serial: str, cancelled: threading.Event):
        self.executable = executable
        self.serial = serial
        self.cancelled = cancelled

    def run(self, args: list[str], timeout: int = 25, check: bool = True) -> str:
        if self.cancelled.is_set():
            raise UploadError("Đã hủy theo yêu cầu.")
        command = [self.executable, "-s", self.serial, *args]
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise UploadError(f"ADB không khởi chạy: {exc}") from exc
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if self.cancelled.is_set():
                    process.kill()
                    process.communicate()
                    raise UploadError("Đã hủy theo yêu cầu.")
                if time.monotonic() >= deadline:
                    process.kill()
                    process.communicate()
                    raise UploadError(f"ADB quá thời gian {timeout}s: {' '.join(args[:3])}")
                time.sleep(0.1)
            stdout, stderr = process.communicate()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        out = (stdout or "") + "\n" + (stderr or "")
        if check and process.returncode != 0:
            raise UploadError(f"ADB exit={process.returncode}: {out.strip()[-500:]}")
        return out.strip()

    def verify_online(self) -> None:
        state = self.run(["get-state"], timeout=10)
        if state.splitlines()[0].strip() != "device":
            raise UploadError(f"{self.serial}: thiết bị không ở trạng thái device.")

    def app_installed(self, package: str) -> bool:
        out = self.run(["shell", "pm", "path", package], timeout=15, check=False)
        return "package:" in out

    def launch(self, package: str) -> None:
        out = self.run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
        if "monkey aborted" in out.lower() or "no activities found" in out.lower():
            raise UploadError(f"Không thể mở ứng dụng {package}.")

    def transfer(self, video: Path, log: Callable[[str], None]) -> tuple[str, Optional[str]]:
        if not video.is_file():
            raise UploadError(f"Không tìm thấy video: {video}")
        if video.suffix.lower() not in EXTENSIONS:
            raise UploadError("Định dạng chưa hỗ trợ. Dùng MP4, MOV, M4V hoặc 3GP.")
        if video.stat().st_size == 0:
            raise UploadError("Tệp video rỗng.")
        ext = video.suffix.lower()
        remote_name = f"au_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}{ext}"
        remote = f"{ANDROID_DIR}/{remote_name}"
        self.run(["shell", "mkdir", "-p", ANDROID_DIR])
        log(f"{self.serial}: chuyển {video.name} sang {remote}")
        self.run(["push", str(video), remote], timeout=max(120, video.stat().st_size // (500 * 1024)))
        actual_size = self.run(["shell", "stat", "-c", "%s", remote], timeout=15)
        match = re.search(r"\b(\d+)\b", actual_size)
        if not match or int(match.group(1)) != video.stat().st_size:
            raise UploadError("Kích thước video trên điện thoại không khớp.")
        # Notify media provider. Some Android ROMs no longer honor this broadcast;
        # an absent MediaStore row is therefore a normal manual-fallback case.
        self.run(
            ["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
             "-d", f"file://{remote}"], timeout=15, check=False
        )
        media_uri: Optional[str] = None
        for attempt in range(5):
            if self.cancelled.is_set():
                raise UploadError("Đã hủy theo yêu cầu.")
            rows = self.run(
                ["shell", "content", "query", "--uri", "content://media/external/video/media",
                 "--projection", "_id:_display_name",
                 "--where", f"_display_name='{remote_name}'"],
                timeout=20, check=False
            )
            matched = re.search(r"(?:^|[\s,])_id=(\d+)", rows)
            if matched:
                media_uri = f"content://media/external/video/media/{matched.group(1)}"
                break
            time.sleep(1)
        log(f"{self.serial}: đã copy và kiểm tra video ({video.stat().st_size:,} bytes).")
        return remote, media_uri

    def share_video(self, package: str, media_uri: str) -> bool:
        # Grant the receiving app read access to the MediaStore URI.
        out = self.run(
            ["shell", "am", "start", "-a", "android.intent.action.SEND",
             "-t", "video/*", "-f", "0x1", "--eu",
             "android.intent.extra.STREAM", media_uri, "-p", package],
            timeout=25, check=False
        )
        bad = ("error:", "unable to resolve", "does not exist", "exception", "securityexception")
        return not any(token in out.lower() for token in bad)

    def ui_nodes(self) -> list[dict]:
        # Dump on the phone first, then read XML (avoids terminal encoding noise).
        out = self.run(["shell", "uiautomator", "dump", "/sdcard/window_auto_upload.xml"],
                       timeout=25, check=False)
        if "ERROR" in out.upper() or "exception" in out.lower():
            raise UploadError("Không đọc được giao diện Android (UIAutomator).")
        xml = self.run(["exec-out", "cat", "/sdcard/window_auto_upload.xml"], timeout=15)
        start = xml.find("<?xml")
        if start < 0:
            raise UploadError("UIAutomator không trả XML.")
        try:
            root = ET.fromstring(xml[start:])
        except ET.ParseError as exc:
            raise UploadError("XML giao diện không hợp lệ.") from exc
        nodes = []
        for el in root.iter("node"):
            a = el.attrib
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", a.get("bounds", ""))
            if not m:
                continue
            x1, y1, x2, y2 = map(int, m.groups())
            if x2 <= x1 or y2 <= y1:
                continue
            nodes.append({
                "text": a.get("text", "").strip(),
                "desc": a.get("content-desc", "").strip(),
                "resource": a.get("resource-id", "").strip(),
                "class": a.get("class", ""),
                "package": a.get("package", ""),
                "enabled": a.get("enabled", "") == "true",
                "clickable": a.get("clickable", "") == "true",
                "x": (x1 + x2) // 2,
                "y": (y1 + y2) // 2,
            })
        return nodes

    def tap(self, node: dict) -> None:
        self.run(["shell", "input", "tap", str(node["x"]), str(node["y"])], timeout=12)

    def input_ascii(self, text: str) -> bool:
        # 'adb shell input text' is not safe for arbitrary Vietnamese/emoji.
        if not text.isascii() or "\n" in text or "\r" in text:
            return False
        escaped = text.replace("%", "%25").replace(" ", "%s")
        self.run(["shell", "input", "text", escaped], timeout=25)
        return True


def find_button(nodes: list[dict], labels: tuple[str, ...], package: str) -> Optional[dict]:
    labels_fold = {t.casefold() for t in labels}
    # Exact match only. Never click partial matches such as "Đăng xuất".
    for node in nodes:
        if not node["enabled"] or node["package"] != package:
            continue
        for key in ("text", "desc"):
            if node[key].casefold() in labels_fold:
                return node
    return None


def find_edit(nodes: list[dict], package: str) -> Optional[dict]:
    for node in nodes:
        if node["package"] != package or not node["enabled"]:
            continue
        if node["class"].endswith("EditText"):
            return node
    return None


NEXT_BUTTONS = ("Tiếp", "Tiếp theo", "Next", "Continue", "Tiếp tục")
PUBLISH_BUTTONS = {
    "TikTok": ("Đăng", "Post"),
    "Facebook": ("Đăng", "Post", "Chia sẻ ngay", "Share now"),
}


def attempt_publish(
    adb: ADB, platform: str, caption: str, log: Callable[[str], None]
) -> str:
    """Best effort UI automation; no success assertion without platform verification."""
    package = PACKAGES[platform]
    caption_done = not bool(caption.strip())
    next_count = 0
    editor_seen = False
    for _ in range(9):
        if adb.cancelled.is_set():
            raise UploadError("Đã hủy theo yêu cầu.")
        time.sleep(2)
        nodes = adb.ui_nodes()
        count = sum(n["package"] == package for n in nodes)
        if count < 2:
            log(f"{platform}: màn hình khác ứng dụng đích (có thể có quyền/cảnh báo).")
            return "manual_required"
        editor = find_edit(nodes, package)
        if editor:
            editor_seen = True
        if editor and not caption_done:
            if not caption.isascii() or "\n" in caption:
                log(f"{platform}: caption có dấu/emoji; cần nhập thủ công để tránh sai nội dung.")
                return "manual_required"
            adb.tap(editor)
            time.sleep(0.4)
            if not adb.input_ascii(caption):
                return "manual_required"
            caption_done = True
            log(f"{platform}: đã nhập caption ASCII.")
            adb.run(["shell", "input", "keyevent", "KEYCODE_BACK"], timeout=10)
            continue
        if caption_done:
            publish = find_button(nodes, PUBLISH_BUTTONS[platform], package)
            if publish and (editor_seen or next_count > 0):
                adb.tap(publish)
                log(f"{platform}: đã nhấn Đăng, chưa xác minh video xuất bản.")
                return "submitted_unverified"
        next_btn = find_button(nodes, NEXT_BUTTONS, package)
        if next_btn and next_count < 4:
            adb.tap(next_btn)
            next_count += 1
            log(f"{platform}: chuyển sang bước biên tập tiếp theo ({next_count}).")
            continue
        log(f"{platform}: không xác định được bước tiếp theo một cách an toàn.")
        return "manual_required"
    return "manual_required"


def run_request(
    request: UploadRequest, adb_executable: str,
    log: Callable[[str], None], cancelled: threading.Event,
    on_manual_wait: Optional[Callable[[dict], None]] = None
) -> list[dict]:
    """Transfer once, then navigate each social app by tapping its real UI."""
    from tap_flow import TouchFlow, FlowStopped

    adb = ADB(adb_executable, request.serial, cancelled)
    adb.verify_online()
    log(f"{request.serial}: sao chép video từ PC vào điện thoại...")
    remote, media_uri = adb.transfer(request.video, log)
    outcomes: list[dict] = []

    for platform in request.platforms:
        if cancelled.is_set():
            raise UploadError("Đã hủy theo yêu cầu.")
        package = PACKAGES[platform]
        result = {
            "serial": request.serial, "video": str(request.video),
            "remote": remote, "platform": platform,
            "status": "manual_required", "detail": "",
        }
        try:
            if not adb.app_installed(package):
                raise UploadError(f"Chưa cài {platform} ({package}) trên điện thoại.")
            flow = TouchFlow(
                adb, platform, remote, media_uri, request.captions.get(platform, ""),
                request.auto_publish, request.choose_latest, log
            )
            result["status"] = flow.execute()
            if result["status"] == "prepared":
                result["detail"] = (
                    "Đã vào màn hình đăng; hãy xác nhận video và nhấn Đăng trên điện thoại."
                )
            elif result["status"] == "submitted_unverified":
                result["detail"] = (
                    "Đã chạm nút Đăng; chưa xác minh TikTok/Facebook xuất bản thành công."
                )
        except FlowStopped as exc:
            result["status"] = "manual_required"
            result["detail"] = str(exc)
            log(f"{request.serial} | {platform}: DỪNG AN TOÀN: {exc}")
        except UploadError as exc:
            if cancelled.is_set():
                raise
            result["status"] = "error"
            result["detail"] = str(exc)
            log(f"{request.serial} | {platform}: LỖI - {exc}")
        except Exception as exc:
            result["status"] = "error"
            result["detail"] = str(exc)
            log(f"{request.serial} | {platform}: LỖI KHÔNG DỰ KIẾN - {exc}")
        write_history(result)
        outcomes.append(result)
        if on_manual_wait and result["status"] in {"prepared", "manual_required"}:
            on_manual_wait(result)
    return outcomes
