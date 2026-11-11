"""Visible touch-based posting on a real Android device through ADB.

No Android ACTION_SEND or direct posting API is used. All screen changes are
HOME / swipe / tap / text on the actual TikTok/Facebook UI. Selectors are
accessibility nodes rather than hard-coded coordinates whenever possible.

This is a best-effort, version-sensitive workflow. It intentionally pauses
instead of guessing on unexpected screens and never reports publication success
from a button click alone.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from upload_engine import ADB, UploadError, find_button, find_edit, PACKAGES

DIAGNOSTICS = Path(__file__).resolve().parent / "logs" / "upload_screens"
NEXT = ("Tiếp", "Tiếp theo", "Next", "Continue", "Tiếp tục", "Done", "Xong")
POST = {
    "TikTok": ("Đăng", "Post", "Đăng bài"),
    "Facebook": ("Đăng", "Post", "Chia sẻ", "Share now"),
}
HOME_LABELS = {
    "TikTok": ("TikTok",),
    "Facebook": ("Facebook",),
}
CREATE = {
    "TikTok": ("Add post", "Create", "Create video", "New post", "Tạo", "Tạo video", "+"),
    "Facebook": ("Create reel", "Create a reel", "Tạo thước phim", "Tạo Reel", "Tạo bài viết"),
}
GALLERY = ("Upload", "Upload video", "Tải lên", "Tải video lên", "Album", "Gallery", "Thư viện")
GALLERY_MARKERS = (
    "Recents", "Recent", "Gần đây", "Videos", "Video", "All", "Tất cả", "Albums", "Album"
)
CAPTION_HINTS = (
    "Describe your video", "Add a description", "Viết chú thích",
    "Caption", "Mô tả", "Viết gì đó", "Describe", "Add caption"
)
PICKER_PACKAGES = {
    "com.google.android.providers.media.module",
    "com.android.providers.media.module",
    "com.android.documentsui",
    "com.google.android.documentsui",
    "com.sec.android.gallery3d",
    "com.google.android.apps.photos",
}


class FlowStopped(UploadError):
    """A screen is ambiguous, so the user needs to complete it manually."""


class TouchFlow:
    def __init__(self, adb: ADB, platform: str, remote: str, media_uri: Optional[str],
                 caption: str, auto_publish: bool, choose_latest: bool,
                 log: Callable[[str], None]):
        self.adb = adb
        self.platform = platform
        self.package = PACKAGES[platform]
        self.remote = remote
        self.media_uri = media_uri
        self.caption = caption.strip()
        self.auto_publish = auto_publish
        self.choose_latest = choose_latest
        self.log = log
        self.stage = "init"
        self.selected_media = False
        self.caption_set = False

    def step(self, name: str):
        if self.adb.cancelled.is_set():
            raise UploadError("Đã hủy theo yêu cầu.")
        self.stage = name
        self.log(f"{self.platform}: {name}")

    def wait_nodes(self, seconds: float = 7.0) -> list[dict]:
        """Wait until UI hierarchy is non-empty; do not rely on fixed sleep alone."""
        deadline = time.monotonic() + seconds
        last: list[dict] = []
        while time.monotonic() < deadline:
            if self.adb.cancelled.is_set():
                raise UploadError("Đã hủy theo yêu cầu.")
            try:
                last = self.adb.ui_nodes()
            except UploadError:
                time.sleep(0.4)
                continue
            if last:
                return last
            time.sleep(0.6)
        return last

    def sleep(self, delay: float = 1.1):
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            if self.adb.cancelled.is_set():
                raise UploadError("Đã hủy theo yêu cầu.")
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))

    def size(self) -> tuple[int, int]:
        result = self.adb.run(["shell", "wm", "size"], timeout=10)
        matches = re.findall(r"(\d+)\s*x\s*(\d+)", result)
        if not matches:
            raise FlowStopped("Không đọc được kích thước màn hình Android.")
        w, h = matches[-1]
        return int(w), int(h)

    def tap_ratio(self, x: float, y: float):
        w, h = self.size()
        self.adb.run(["shell", "input", "tap", str(round(x*w)), str(round(y*h))], timeout=12)

    def swipe_up(self):
        w, h = self.size()
        self.adb.run(
            ["shell", "input", "swipe", str(w//2), str(h*0.83),
             str(w//2), str(h*0.26), "400"], timeout=12
        )

    def key(self, code: str):
        self.adb.run(["shell", "input", "keyevent", code], timeout=12)

    def visible_app(self, nodes: list[dict]) -> bool:
        return any(n.get("package") == self.package and n.get("enabled") for n in nodes)

    def exact(self, nodes: list[dict], labels: tuple[str, ...],
              inside_app: bool = True) -> Optional[dict]:
        packages = (self.package,) if inside_app else tuple({
            n.get("package", "") for n in nodes if n.get("package") != self.package
        })
        for pkg in packages:
            hit = find_button(nodes, labels, pkg)
            if hit:
                return hit
        return None

    def hint(self, nodes: list[dict], hints: tuple[str, ...]) -> bool:
        return any(
            n.get("package") == self.package and any(
                h.casefold() in (n.get("text", "") + " " + n.get("desc", "")).casefold()
                for h in hints
            ) for n in nodes
        )

    def snapshot(self, reason: str) -> str:
        """Create a PNG and sanitized UI node summary for troubleshooting."""
        DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^A-Za-z0-9_-]", "_", self.adb.serial)
        base = DIAGNOSTICS / f"{slug}_{self.platform}_{stamp}"
        try:
            p = subprocess.run(
                [self.adb.executable, "-s", self.adb.serial, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if p.returncode == 0 and p.stdout.startswith(b"\x89PNG"):
                base.with_suffix(".png").write_bytes(p.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            nodes = self.adb.ui_nodes()
            # Avoid saving private text fields/captions in diagnostics.
            with base.with_suffix(".txt").open("w", encoding="utf-8") as f:
                f.write(f"{reason}\nstep={self.stage}\n")
                for n in nodes:
                    f.write(f"package={n.get('package','')} class={n.get('class','')} "
                            f"resource={n.get('resource','')} "
                            f"pos={n.get('x')},{n.get('y')}\n")
        except (OSError, UploadError):
            pass
        return str(base.with_suffix(".png"))

    def stop(self, reason: str):
        screenshot = self.snapshot(reason)
        raise FlowStopped(f"{reason} Ảnh kiểm tra: {screenshot}")

    def home_to_icon(self):
        self.step("Bấm Home → tìm icon ứng dụng")
        self.key("KEYCODE_HOME")
        self.sleep(1)
        for attempt in range(5):
            nodes = self.wait_nodes()
            icon = self.exact(nodes, HOME_LABELS[self.platform], inside_app=False)
            if icon:
                self.adb.tap(icon)
                self.sleep(2.2)
                after = self.wait_nodes()
                if self.visible_app(after):
                    self.log(f"{self.platform}: đã bấm icon {self.platform} từ màn hình Android.")
                    return
                # Some apps render no accessible nodes at startup.
                self.sleep(2.0)
                if self.visible_app(self.wait_nodes()):
                    return
                self.stop("Đã bấm icon nhưng không xác nhận được ứng dụng đã mở.")
            if attempt == 0:
                # Samsung One UI: swipe up to open all-apps drawer.
                self.swipe_up()
                self.sleep(1)
            elif attempt < 4:
                self.swipe_up()
                self.sleep(0.5)
        self.stop(f"Không tìm thấy icon {self.platform} ở Home hoặc app drawer.")

    def open_create(self):
        self.step("Bấm nút + / Tạo nội dung")
        nodes = self.wait_nodes()
        if not self.visible_app(nodes):
            self.stop(f"Không thấy giao diện {self.platform}.")
        create = self.exact(nodes, CREATE[self.platform])
        if create:
            self.adb.tap(create)
        elif self.platform == "TikTok" and self.hint(
            nodes, ("Home", "For You", "Friends", "Inbox", "Profile", "Trang chủ", "Hồ sơ")
        ):
            # Guarded TikTok fallback: bottom-center + on a verified TikTok feed.
            self.log("TikTok: nút + không có nhãn; bấm vị trí giữa thanh điều hướng.")
            self.tap_ratio(0.50, 0.955)
        else:
            self.stop("Không xác định được nút Tạo nội dung trên giao diện.")
        self.sleep(1.4)

    def open_gallery(self):
        self.step("Bấm Tải lên / Upload để mở album video")
        nodes = self.wait_nodes()
        upload = self.exact(nodes, GALLERY)
        if not upload:
            self.stop("Không tìm thấy nút Tải lên / Upload trong giao diện tạo video.")
        self.adb.tap(upload)
        self.sleep(1.4)

    def latest_in_mediastore(self) -> bool:
        """Only infer the first gallery tile when this exact video is newest."""
        if not self.media_uri:
            return False
        expected_id = self.media_uri.rsplit("/", 1)[-1]
        if not expected_id.isdigit():
            return False
        listing = self.adb.run(
            ["shell", "content", "query", "--uri", "content://media/external/video/media",
             "--projection", "_id:_display_name", "--sort", "_id DESC"],
            timeout=20, check=False
        )
        first_row = next(
            (line for line in listing.splitlines() if line.strip().startswith("Row:")), ""
        )
        m = re.search(r"(?:^|[\s,])_id=(\d+)", first_row)
        return bool(m and m.group(1) == expected_id
                    and Path(self.remote).name in first_row)

    def select_video(self):
        self.step("Chọn đúng video mới copy trong thư viện")
        nodes = self.wait_nodes(8)
        name = Path(self.remote).name
        # Prefer the Videos-only tab. Never guess the first item of a
        # mixed Photos+Videos album, even if this is the latest *video*.
        video_tab = next((
            n for n in nodes if n.get("enabled") and
            n.get("text", "").casefold() in ("videos", "video", "video clip", "video clips")
            and n.get("package") in ({self.package} | PICKER_PACKAGES)
        ), None)
        if video_tab:
            self.adb.tap(video_tab)
            self.sleep(0.9)
            nodes = self.wait_nodes(5)
        # Safest path: visible file name or accessibility description.
        matches = [n for n in nodes if name.casefold() in
                   (n.get("text", "") + " " + n.get("desc", "")).casefold()
                   and n.get("enabled")]
        if len(matches) == 1:
            self.adb.tap(matches[0])
        elif (self.choose_latest and video_tab is not None
              and self.latest_in_mediastore()):
            # Picker must expose a Videos-only filter, not an arbitrary mixed album.
            # Android's media scanner has confirmed this video is the newest VIDEO.
            w, h = self.size()
            candidates = [
                n for n in nodes if n.get("enabled") and n.get("clickable")
                and n.get("package") in ({self.package} | PICKER_PACKAGES)
                and int(h * 0.14) < n.get("y", 0) < int(h * 0.86)
                and ("Image" in n.get("class", "") or any(
                    key in n.get("resource", "").lower()
                    for key in ("thumbnail", "media_item", "gallery_item", "photo_item", "video_item")
                ))
            ]
            candidates.sort(key=lambda n: (n["y"], n["x"]))
            if not candidates:
                self.stop("Video mới nhất có trong MediaStore, nhưng không tìm thấy thumbnail có thể bấm.")
            self.log("Chọn thumbnail đầu tiên của tab Videos (đã xác nhận file mới là video mới nhất).")
            self.adb.tap(candidates[0])
        else:
            self.stop(
                "Không thể xác định chính xác video trong album. "
                "Hãy chọn video vừa chuyển trên màn hình điện thoại."
            )
        self.selected_media = True
        self.sleep(1.0)

    def navigate_edit(self):
        self.step("Tiếp → mở màn hình biên tập và caption")
        for index in range(6):
            nodes = self.wait_nodes()
            if not self.visible_app(nodes):
                self.stop("Không tìm thấy giao diện ứng dụng ở bước chỉnh sửa.")
            editor = find_edit(nodes, self.package)
            if editor and (self.hint(nodes, CAPTION_HINTS) or self.exact(nodes, POST[self.platform])):
                return
            nxt = self.exact(nodes, NEXT)
            if not nxt:
                # Some apps use a checkmark symbol for confirmation, but do not
                # click an unknown symbol unless explicitly identified.
                self.stop("Không tìm thấy nút Tiếp/Next trên màn hình biên tập.")
            self.adb.tap(nxt)
            self.sleep(1.3)
        self.stop("Quá nhiều màn hình Tiếp/Next, tạm dừng để tránh thao tác nhầm.")

    def enter_caption(self):
        self.step("Nhập caption trên màn hình đăng")
        if not self.caption:
            self.caption_set = True
            return
        nodes = self.wait_nodes()
        editor = find_edit(nodes, self.package)
        if not editor:
            self.stop("Không tìm thấy ô nhập caption.")
        # Never paste ASCII if text contains Unicode: old Android input text
        # can corrupt Vietnamese, apostrophes, hashes or emoji.
        safe_ascii = (
            self.caption.isascii()
            and all(ch.isalnum() or ch in " .,_-#@!?" for ch in self.caption)
            and "\n" not in self.caption
        )
        if not safe_ascii:
            self.stop(
                "Caption có dấu/emoji hoặc ký tự đặc biệt. "
                "Hãy nhập caption qua scrcpy rồi nhấn Tiếp tục."
            )
        self.adb.tap(editor)
        self.sleep(0.4)
        if not self.adb.input_ascii(self.caption):
            self.stop("Không thể nhập caption bằng bàn phím Android.")
        self.caption_set = True
        self.key("KEYCODE_BACK")
        self.sleep(0.5)

    def publish(self) -> str:
        self.step("Kiểm tra nút Đăng")
        nodes = self.wait_nodes()
        if not self.selected_media or not self.caption_set:
            self.stop("Chưa xác nhận chọn đúng video và nội dung, không được tự Đăng.")
        post = self.exact(nodes, POST[self.platform])
        if not post:
            self.stop("Chưa tìm thấy nút Đăng cuối cùng.")
        if not self.auto_publish:
            self.log(f"{self.platform}: video và caption sẵn sàng, chờ người dùng bấm Đăng.")
            return "prepared"
        self.adb.tap(post)
        self.log(f"{self.platform}: đã chạm nút Đăng. Chưa xác minh video xuất bản.")
        return "submitted_unverified"

    def execute(self) -> str:
        self.home_to_icon()
        self.open_create()
        self.open_gallery()
        self.select_video()
        self.navigate_edit()
        self.enter_caption()
        return self.publish()
