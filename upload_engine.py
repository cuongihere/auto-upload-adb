"""ADB video transfer and cautious in-app publishing workflow.

No social credentials, private APIs, or root permissions are used.
Final publishing is opt-in; a tap is never reported as verified publication.
"""
from __future__ import annotations

import json
import re
import shlex
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
ANDROID_DIR = "/sdcard/Movies/AutoUpload"
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
        # adb shell joins argv into a remote shell command. Preserve SQL quotes,
        # spaces, hashtags and shell metacharacters as literal arguments.
        remote_args = ['shell', shlex.join(args[1:])] if args and args[0] == 'shell' else args
        command = [self.executable, "-s", self.serial, *remote_args]
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
            while True:
                if self.cancelled.is_set():
                    process.kill()
                    process.communicate()
                    raise UploadError("Đã hủy theo yêu cầu.")
                if time.monotonic() >= deadline:
                    process.kill()
                    process.communicate()
                    raise UploadError(f"ADB quá thời gian {timeout}s: {' '.join(args[:3])}")
                try:
                    # Drain pipes while waiting. Large UI XML otherwise fills the
                    # stdout pipe and deadlocks while poll() waits for ADB exit.
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
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
        token = f'{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}'
        remote_name = f'au_{token}{ext}'
        # A unique album contains exactly this video. Gallery order is not an
        # identity check: adb push preserves source mtime on some versions.
        remote_dir = f'{ANDROID_DIR}/AU_{token}'
        remote = f"{remote_dir}/{remote_name}"
        self.run(["shell", "mkdir", "-p", remote_dir])
        log(f"{self.serial}: chuyển {video.name} sang {remote}")
        self.run(["push", str(video), remote], timeout=max(120, video.stat().st_size // (500 * 1024)))
        self.run(['shell', 'touch', remote], timeout=15)
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
        parents = {child: parent for parent in root.iter() for child in parent}
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
                "selected": a.get("selected", "") == "true",
                "bounds": (x1, y1, x2, y2),
                "grid_item": parents.get(el) is not None and
                    parents[el].get('class', '').endswith('GridView'),
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
    on_manual_wait: Optional[Callable[[dict], str]] = None,
    history=None,
) -> list[dict]:
    """Reserve content before transfer; persist intent before any final Post tap."""
    from tap_flow import TouchFlow, FlowStopped
    from upload_history import UploadHistory, fingerprint

    history = history or UploadHistory()
    try:
        sha = fingerprint(request.video, cancelled)
    except (OSError, InterruptedError) as exc:
        raise UploadError(str(exc)) from exc
    adb = ADB(adb_executable, request.serial, cancelled)
    remote, media_uri = None, None
    outcomes = []
    for platform in request.platforms:
        if cancelled.is_set():
            break
        ident, duplicate = history.reserve(sha, platform, request.serial, request.video)
        result = dict(serial=request.serial, video=str(request.video), platform=platform,
                      sha256=sha, history_id=ident, status='in_progress', detail='')
        if duplicate:
            result.update(status='duplicate_skipped', detail=(
                f"Đã chặn trùng nội dung: {duplicate['status']} trên {duplicate['serial']}. "
                "Xem Lịch sử để xác nhận kết quả cũ nếu cần."))
            log(result['detail'])
            outcomes.append(result)
            continue
        flow = None
        submitted = False
        try:
            adb.verify_online()
            if platform not in PACKAGES or not adb.app_installed(PACKAGES[platform]):
                raise UploadError(f'Chưa cài ứng dụng {platform} trên điện thoại.')
            if remote is None:
                remote, media_uri = adb.transfer(request.video, log)
                # Detect a source file changed while it was being copied.
                if fingerprint(request.video, cancelled) != sha:
                    raise UploadError('Video đã thay đổi trong khi copy. Hãy chọn lại file ổn định.')
            result['remote'] = remote
            history.update(ident, 'in_progress', remote=remote)
            flow = TouchFlow(adb, platform, remote, media_uri,
                             request.captions.get(platform, ''), request.auto_publish,
                             request.choose_latest, log)

            def manual(stage, detail):
                result.update(status='manual_required', detail=f'{stage}: {detail}')
                history.update(ident, result['status'], result['detail'])
                if not on_manual_wait:
                    return 'pause'
                action = on_manual_wait(dict(result))
                if action == 'retry':
                    history.update(ident, 'in_progress', 'Tiếp tục bước đang dở.')
                return action

            flow.manual_handler = manual if on_manual_wait else None

            def before_submit():
                nonlocal submitted
                history.update(ident, 'submitting', 'Chuẩn bị bấm Đăng; không tự thử đăng lại.')
                submitted = True

            flow.before_submit = before_submit
            result['status'] = flow.execute()
            if result['status'] == 'prepared':
                result['detail'] = 'Video sẵn sàng. Bấm Đăng trên điện thoại rồi xác nhận Đã đăng thành công.'
                history.update(ident, 'prepared', result['detail'])
                if on_manual_wait:
                    action = on_manual_wait(dict(result))
                    while action == 'retry' and not cancelled.is_set():
                        if flow.verify_publication(seconds=8):
                            action = 'published'
                            break
                        result['detail'] = 'Chưa xác minh đăng. Nếu đã kiểm tra bài, chọn Đã đăng thành công.'
                        action = on_manual_wait(dict(result))
                    result['status'] = 'published_manual' if action == 'published' else 'needs_review'
            elif result['status'] == 'submitted_unverified':
                history.update(ident, 'submitted_unverified', 'Đã bấm Đăng, đang kiểm tra kết quả.')
                if flow.verify_publication():
                    result['status'] = 'published'
                elif on_manual_wait:
                    result['detail'] = 'Chưa đọc được xác nhận của TikTok. Kiểm tra bài trên điện thoại; không tự đăng lại.'
                    action = on_manual_wait(dict(result))
                    while action == 'retry' and not cancelled.is_set():
                        if flow.verify_publication(seconds=8):
                            action = 'published'
                            break
                        action = on_manual_wait(dict(result))
                    if action == 'published':
                        result['status'] = 'published_manual'
            if result['status'] in ('published', 'published_manual'):
                result['detail'] = ('Ứng dụng báo đăng thành công.' if result['status'] == 'published'
                                    else 'Người dùng xác nhận đã đăng thành công.')
        except Exception as exc:
            result['status'] = ('submitted_unverified' if submitted else
                                'needs_review' if flow is not None else 'error')
            result['detail'] = str(exc)
            log(f'{request.serial} | {platform}: {exc}')
        finally:
            # Cancellation/crash around a post must never make the file retryable.
            history.update(ident, result['status'], result['detail'], remote)
            write_history(result)
            outcomes.append(result)
        if cancelled.is_set():
            break
    return outcomes
