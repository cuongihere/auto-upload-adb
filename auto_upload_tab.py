"""Auto Upload tab for the existing Android Scrcpy Manager."""
from __future__ import annotations

import threading
import json
from pathlib import Path
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget,
    QProgressBar,
)

from upload_engine import ADB, PACKAGES, UploadRequest, UploadError, run_request
from upload_history import UploadHistory

QUEUE_FILE = Path(__file__).resolve().parent / 'config' / 'upload_queue.json'
STATUS_LABELS = {
    'in_progress': 'Đang thao tác',
    'prepared': 'Chờ đăng / xác nhận',
    'manual_required': 'Cần thao tác thủ công',
    'submitting': 'Đang bấm Đăng',
    'submitted_unverified': 'Đã bấm Đăng — chưa xác nhận',
    'published': 'Đã đăng thành công',
    'published_manual': 'Đã xác nhận đăng thành công',
    'needs_review': 'Cần kiểm tra kết quả',
    'error': 'Có lỗi — cần kiểm tra',
}


class VideoList(QListWidget):
    """Accept video files dragged directly from Explorer."""
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setToolTip("Kéo video từ Windows Explorer vào đây.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    self.add_video(url.toLocalFile())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def add_video(self, name: str) -> bool:
        path = Path(name)
        if not path.is_file() or path.suffix.lower() not in {".mp4", ".mov", ".m4v", ".3gp"}:
            return False
        normalized = str(path.resolve())
        if any(self.item(i).text() == normalized for i in range(self.count())):
            return False
        self.addItem(normalized)
        return True


class UploadWorker(QThread):
    message = Signal(str)
    request_started = Signal(int, int, str, str)
    outcome = Signal(dict)
    manual_step = Signal(str)
    reserved = Signal(dict)

    def __init__(self, requests: list[UploadRequest], adb_executable: str):
        super().__init__()
        self.requests = requests
        self.adb_executable = adb_executable
        self.cancel_event = threading.Event()
        self.continue_event = threading.Event()
        self.manual_action = 'pause'

    def cancel(self):
        self.cancel_event.set()
        self.continue_event.set()

    def proceed(self, action='retry'):
        self.manual_action = action
        self.continue_event.set()

    def run(self):
        for index, req in enumerate(self.requests, 1):
            if self.cancel_event.is_set():
                break
            self.request_started.emit(index, len(self.requests), req.serial, req.video.name)
            self.message.emit(
                f"[{index}/{len(self.requests)}] {req.serial}: {req.video.name}"
            )
            try:
                def manual_wait(result: dict):
                    if result.get("status") in {"prepared", "manual_required", "submitted_unverified"}:
                        self.manual_action = 'pause'
                        self.continue_event.clear()
                        self.manual_step.emit(
                            f"{req.serial} | {result['platform']}: {result.get('detail') or 'Kiểm tra và hoàn tất thao tác trên điện thoại.'} "
                            "Nhấn Tiếp tục bước đang dở, hoặc Đã đăng thành công sau khi kiểm tra bài."
                        )
                        while not self.cancel_event.is_set():
                            if self.continue_event.wait(0.3):
                                break
                        return 'pause' if self.cancel_event.is_set() else self.manual_action
                    return 'pause'

                results = run_request(
                    req, self.adb_executable, self.message.emit,
                    self.cancel_event, on_manual_wait=manual_wait,
                    on_reserved=self.reserved.emit
                )
                for result in results:
                    self.outcome.emit(result)
            except UploadError as exc:
                self.message.emit(f"{req.serial}: {exc}")
                self.outcome.emit({
                    "serial": req.serial, "video": str(req.video),
                    "platform": "-", "status": "error", "detail": str(exc)
                })
            except Exception as exc:
                self.message.emit(f"{req.serial}: lỗi không dự kiến: {exc}")
                self.outcome.emit({
                    "serial": req.serial, "video": str(req.video),
                    "platform": "-", "status": "error", "detail": str(exc)
                })


class OpenAppWorker(QThread):
    message = Signal(str)

    def __init__(self, adb_executable, serials, platform):
        super().__init__()
        self.adb_executable, self.serials, self.platform = adb_executable, serials, platform
        self.cancel_event = threading.Event()

    def run(self):
        from tap_flow import TouchFlow
        for serial in self.serials:
            if self.cancel_event.is_set():
                break
            try:
                adb = ADB(self.adb_executable, serial, self.cancel_event)
                adb.verify_online()
                if not adb.app_installed(PACKAGES[self.platform]):
                    raise UploadError(f'Chưa cài {self.platform}.')
                flow = TouchFlow(adb, self.platform, '', None, '', False, False, self.message.emit)
                flow.home_to_icon()
                self.message.emit(f'{serial}: đã mở {self.platform}. Bạn có thể kiểm tra tài khoản trên điện thoại.')
            except Exception as exc:
                self.message.emit(f'{serial}: {exc}')


class AutoUploadTab(QWidget):
    def __init__(
        self, adb_locator: Callable[[], str | None],
        selected_serials: Callable[[], list[str]],
        is_online: Callable[[str], bool],
        parent=None
    ):
        super().__init__(parent)
        self.adb_locator = adb_locator
        self.selected_serials = selected_serials
        self.is_online = is_online
        self.worker: UploadWorker | None = None
        self.open_worker = None
        self.active_history_id = None
        self.history = UploadHistory()
        self.history.import_legacy(Path(__file__).resolve().parent / 'logs' / 'auto_upload_history.jsonl')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 8, 9, 9)
        layout.setSpacing(7)

        # Các chỉ số luôn nhìn thấy, thay vì phải đọc log để biết trạng thái.
        metrics = QHBoxLayout()
        metrics.setSpacing(7)
        self.summary_devices = QLabel()
        self.summary_videos = QLabel()
        self.summary_platforms = QLabel()
        self.summary_results = QLabel()
        for widget in (self.summary_devices, self.summary_videos,
                       self.summary_platforms, self.summary_results):
            widget.setProperty('role', 'metric')
            metrics.addWidget(widget, 1)
        layout.addLayout(metrics)

        panels = QHBoxLayout()
        panels.setSpacing(8)
        video_box = QGroupBox("01  /  Video chờ đăng")
        vl = QVBoxLayout(video_box)
        vl.setContentsMargins(8, 11, 8, 8)
        vl.setSpacing(6)
        self.videos = VideoList()
        self.videos.setMinimumHeight(115)
        self.videos.setTextElideMode(Qt.ElideLeft)
        self.videos.setToolTip("Kéo thả video vào đây. Đường dẫn đầy đủ lưu trong hàng đợi.")
        vl.addWidget(self.videos)
        video_actions = QHBoxLayout()
        btn_add = QPushButton("Thêm video")
        btn_add.setProperty('role', 'primary')
        btn_remove = QPushButton("Bỏ đã chọn")
        btn_clear = QPushButton("Xóa danh sách")
        video_actions.addWidget(btn_add)
        video_actions.addWidget(btn_remove)
        video_actions.addWidget(btn_clear)
        video_actions.addStretch()
        vl.addLayout(video_actions)
        btn_add.clicked.connect(self.add_files)
        btn_remove.clicked.connect(
            lambda: [self.videos.takeItem(self.videos.row(i)) for i in self.videos.selectedItems()]
        )
        btn_clear.clicked.connect(self.videos.clear)
        panels.addWidget(video_box, 5)

        config_box = QGroupBox("02  /  Nền tảng & caption")
        cl = QVBoxLayout(config_box)
        cl.setContentsMargins(8, 11, 8, 8)
        cl.setSpacing(6)
        platforms = QHBoxLayout()
        self.tiktok = QCheckBox("TikTok")
        self.facebook = QCheckBox("Facebook")
        self.tiktok.setChecked(True)
        platforms.addWidget(self.tiktok)
        platforms.addWidget(self.facebook)
        platforms.addStretch()
        cl.addLayout(platforms)

        caption_tabs = QTabWidget()
        self.tiktok_caption = QPlainTextEdit()
        self.tiktok_caption.setPlaceholderText(
            "Caption TikTok. Để trống sẽ lấy tên từng file video."
        )
        self.tiktok_caption.setMinimumHeight(70)
        caption_tabs.addTab(self.tiktok_caption, "Caption TikTok")
        self.facebook_caption = QPlainTextEdit()
        self.facebook_caption.setPlaceholderText(
            "Caption Facebook. Để trống sẽ lấy tên từng file video."
        )
        self.facebook_caption.setMinimumHeight(70)
        caption_tabs.addTab(self.facebook_caption, "Caption Facebook")
        cl.addWidget(caption_tabs)

        self.advanced_btn = QPushButton("Tùy chọn nâng cao  ▾")
        self.advanced_btn.setCheckable(True)
        self.advanced_btn.setToolTip(
            "Mở/tắt tùy chọn khởi chạy ứng dụng, album và đăng tự động."
        )
        cl.addWidget(self.advanced_btn)
        self.advanced_options = QWidget()
        advanced = QVBoxLayout(self.advanced_options)
        advanced.setContentsMargins(2, 2, 2, 1)
        advanced.setSpacing(6)
        self.open_mode = QComboBox()
        self.open_mode.addItems(['Tự mở ứng dụng', 'Tôi mở sẵn ứng dụng'])
        preview = QHBoxLayout()
        preview.addWidget(self.open_mode, 2)
        self.preview_platform = QComboBox()
        self.preview_platform.addItems(['TikTok', 'Facebook'])
        self.open_test_btn = QPushButton('Mở thử app')
        self.open_test_btn.setToolTip(
            'Chỉ mở ứng dụng trên máy đang chọn, không bắt đầu đăng video.'
        )
        self.open_test_btn.clicked.connect(self.test_open_app)
        preview.addWidget(self.preview_platform, 1)
        preview.addWidget(self.open_test_btn)
        advanced.addLayout(preview)
        self.choose_latest = QCheckBox("Dùng album riêng để chọn đúng video")
        self.choose_latest.setChecked(True)
        self.choose_latest.setToolTip(
            "Mỗi lượt dùng album AU_ riêng; chỉ chọn khi đúng ID, tên và đường dẫn."
        )
        advanced.addWidget(self.choose_latest)
        self.auto_publish = QCheckBox("Tự bấm Đăng cuối cùng (thử nghiệm)")
        self.auto_publish.setToolTip(
            "Có thể đăng bài thật. Mặc định tắt; cần kiểm tra video và tài khoản trước khi bật."
        )
        advanced.addWidget(self.auto_publish)
        cl.addWidget(self.advanced_options)
        self.advanced_options.setVisible(False)
        self.advanced_btn.toggled.connect(self.advanced_options.setVisible)
        self.advanced_btn.toggled.connect(lambda opened: self.advanced_btn.setText(
            "Thu gọn tùy chọn  ▴" if opened else "Tùy chọn nâng cao  ▾"
        ))
        panels.addWidget(config_box, 6)
        layout.addLayout(panels)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.start_btn = QPushButton("Bắt đầu xử lý")
        self.start_btn.setProperty('role', 'primary')
        self.next_btn = QPushButton("Tiếp tục bước đang dở")
        self.posted_btn = QPushButton("Đã kiểm tra: đăng thành công")
        self.posted_btn.setProperty('role', 'success')
        self.cancel_btn = QPushButton("Dừng lượt chạy")
        self.cancel_btn.setProperty('role', 'danger')
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.posted_btn.setToolTip(
            "Chỉ xác nhận khi đã kiểm tra video thực sự xuất hiện trong tài khoản."
        )
        for button in (self.start_btn, self.next_btn, self.posted_btn, self.cancel_btn):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QLabel("Sẵn sàng. Chọn máy ở bảng phía trên và thêm video để bắt đầu.")
        self.status.setProperty('role', 'status')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        progress_line = QHBoxLayout()
        self.progress_label = QLabel('Chưa có lượt chạy.')
        self.progress_label.setProperty('role', 'muted')
        self.progress_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('Chưa bắt đầu')
        progress_line.addWidget(self.progress_label, 3)
        progress_line.addWidget(self.progress_bar, 2)
        layout.addLayout(progress_line)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setPlaceholderText("Các bước thao tác trên điện thoại và lỗi sẽ hiển thị ở đây.")

        result_tabs = QTabWidget()
        result_tabs.setMinimumHeight(245)
        history_box = QWidget()
        hl = QVBoxLayout(history_box)
        hl.setContentsMargins(7, 7, 7, 7)
        hl.setSpacing(5)
        legend = QLabel('Xanh: đã đăng   •   Vàng: cần xác nhận   •   Đỏ: lỗi')
        legend.setProperty('role', 'muted')
        hl.addWidget(legend)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ['Thời gian (máy tính)', 'Thiết bị', 'Nền tảng', 'Video', 'Trạng thái']
        )
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setTextElideMode(Qt.ElideMiddle)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.history_table.setMinimumHeight(145)
        self.history_table.verticalHeader().hide()
        self.history_table.verticalHeader().setDefaultSectionSize(32)
        hl.addWidget(self.history_table)
        history_actions = QHBoxLayout()
        refresh = QPushButton('Làm mới lịch sử')
        self.mark_posted_btn = QPushButton('Xác nhận đã đăng')
        self.mark_posted_btn.setProperty('role', 'success')
        self.release_btn = QPushButton('Chưa đăng / Cho thử lại')
        history_actions.addWidget(refresh)
        history_actions.addWidget(self.mark_posted_btn)
        history_actions.addWidget(self.release_btn)
        history_actions.addStretch()
        hl.addLayout(history_actions)
        result_tabs.addTab(history_box, 'Lịch sử & chống trùng')
        result_tabs.addTab(self.log, 'Nhật ký thao tác')
        layout.addWidget(result_tabs, 1)

        refresh.clicked.connect(self.refresh_history)
        self.mark_posted_btn.clicked.connect(lambda: self.resolve_history(True))
        self.release_btn.clicked.connect(lambda: self.resolve_history(False))
        self.posted_btn.clicked.connect(self.confirm_posted)
        self.load_queue()
        self.videos.model().rowsInserted.connect(self.save_queue)
        self.videos.model().rowsRemoved.connect(self.save_queue)
        self.videos.model().modelReset.connect(self.save_queue)
        self.videos.model().rowsInserted.connect(self.update_summary)
        self.videos.model().rowsRemoved.connect(self.update_summary)
        self.videos.model().modelReset.connect(self.update_summary)
        self.tiktok_caption.textChanged.connect(self.save_queue)
        self.facebook_caption.textChanged.connect(self.save_queue)
        self.tiktok.toggled.connect(self.update_summary)
        self.facebook.toggled.connect(self.update_summary)
        self.start_btn.clicked.connect(self.start_upload)
        self.next_btn.clicked.connect(self.resume_upload)
        self.cancel_btn.clicked.connect(self.stop_upload)
        self.refresh_history()
        self.update_summary()

    def update_summary(self, *args):
        """Compact live counters; no database access or modification."""
        selected = list(dict.fromkeys(self.selected_serials()))
        ready = sum(bool(self.is_online(serial)) for serial in selected)
        platforms = [name for name, control in (
            ('TikTok', self.tiktok), ('Facebook', self.facebook)
        ) if control.isChecked()]
        history = getattr(self, 'history_rows', [])
        confirmed = sum(row['status'] in ('published', 'published_manual') for row in history)
        needs_review = sum(row['status'] not in ('published', 'published_manual') for row in history)
        self.summary_devices.setText(f"Máy được chọn: {ready}/{len(selected)} online")
        self.summary_videos.setText(f"Video chờ: {self.videos.count()}")
        self.summary_platforms.setText(
            "Nền tảng: " + (', '.join(platforms) if platforms else 'chưa chọn')
        )
        self.summary_results.setText(f"Lịch sử: {confirmed} đã đăng / {needs_review} cần xem")

    def on_request_started(self, index: int, total: int, serial: str, video: str):
        """Show which phone and file the worker is processing, not just raw log text."""
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(index - 1)
        self.progress_bar.setFormat(f"Lượt {index}/{total}")
        self.progress_label.setText(f"Đang xử lý {index}/{total}  •  {serial}  •  {video}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Chọn video", "", "Video (*.mp4 *.mov *.m4v *.3gp)"
        )
        for file in files:
            self.videos.add_video(file)

    def save_queue(self, *args):
        path = QUEUE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {'videos': [self.videos.item(i).text() for i in range(self.videos.count())],
                'captions': {'TikTok': self.tiktok_caption.toPlainText(),
                             'Facebook': self.facebook_caption.toPlainText()}}
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temp.replace(path)

    def load_queue(self):
        path = QUEUE_FILE
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            for video in data.get('videos', []):
                self.videos.add_video(video)
            self.tiktok_caption.setPlainText(data.get('captions', {}).get('TikTok', ''))
            self.facebook_caption.setPlainText(data.get('captions', {}).get('Facebook', ''))
        except (OSError, ValueError, TypeError):
            pass

    def start_upload(self):
        if self.open_worker and self.open_worker.isRunning():
            return
        if self.worker and self.worker.isRunning():
            return
        adb = self.adb_locator()
        if not adb:
            QMessageBox.warning(self, "Thiếu ADB", "Không tìm thấy adb.exe.")
            return
        serials = list(dict.fromkeys(self.selected_serials()))
        offline = [s for s in serials if not self.is_online(s)]
        if not serials or offline:
            QMessageBox.warning(
                self, "Chọn điện thoại",
                "Chọn ít nhất một thiết bị online (device). "
                + (f"Thiết bị không sẵn sàng: {', '.join(offline)}" if offline else "")
            )
            return
        videos = [Path(self.videos.item(i).text()) for i in range(self.videos.count())]
        if not videos:
            QMessageBox.information(self, "Thiếu video", "Thêm ít nhất một video.")
            return
        platforms = tuple(
            name for name, checkbox in (
                ("TikTok", self.tiktok), ("Facebook", self.facebook)
            ) if checkbox.isChecked()
        )
        if not platforms:
            QMessageBox.information(self, "Chọn nền tảng", "Chọn TikTok hoặc Facebook.")
            return
        if self.auto_publish.isChecked():
            answer = QMessageBox.question(
                self, "Xác nhận tự đăng (thử nghiệm)",
                "Ứng dụng sẽ THAO TÁC TRỰC TIẾP và có thể ĐĂNG THẬT trên TikTok/Facebook. "
                "Hãy theo dõi màn hình điện thoại, xác nhận đúng tài khoản/video. Tiếp tục?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                return
        captions = {
            "TikTok": self.tiktok_caption.toPlainText(),
            "Facebook": self.facebook_caption.toPlainText(),
        }
        requests = [
            UploadRequest(
                serial=s, video=v, platforms=platforms,
                captions=dict(captions), auto_publish=self.auto_publish.isChecked(),
                choose_latest=self.choose_latest.isChecked(),
                open_app=self.open_mode.currentIndex() == 0
            )
            for s in serials for v in videos
        ]
        self.worker = UploadWorker(requests, adb)
        self.worker.message.connect(self.append)
        self.worker.message.connect(self.on_progress)
        self.worker.request_started.connect(self.on_request_started)
        self.worker.outcome.connect(self.show_outcome)
        self.worker.reserved.connect(self.on_reserved)
        self.worker.manual_step.connect(self.on_manual_step)
        self.worker.finished.connect(self.on_finished)
        self.start_btn.setEnabled(False)
        self.open_test_btn.setEnabled(False)
        self.mark_posted_btn.setEnabled(False)
        self.release_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.posted_btn.setEnabled(False)
        self.progress_bar.setRange(0, max(1, len(requests)))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0/{len(requests)} lượt")
        self.progress_label.setText(
            f"Đã tạo {len(requests)} lượt video × thiết bị; {len(platforms)} nền tảng."
        )
        self.status.setText("Đang chuẩn bị gửi video và kiểm tra lịch sử chống trùng.")
        self.worker.start()

    def append(self, msg: str):
        self.log.appendPlainText(msg)

    def test_open_app(self):
        if ((self.worker and self.worker.isRunning()) or
                (self.open_worker and self.open_worker.isRunning())):
            return
        adb = self.adb_locator()
        serials = list(dict.fromkeys(self.selected_serials()))
        if not adb or not serials or any(not self.is_online(s) for s in serials):
            QMessageBox.warning(self, 'Mở thử ứng dụng', 'Cần ADB và chọn thiết bị đang online.')
            return
        self.open_worker = OpenAppWorker(adb, serials, self.preview_platform.currentText())
        self.open_worker.message.connect(self.append)
        self.open_worker.message.connect(self.status.setText)
        self.open_worker.finished.connect(self.on_open_finished)
        self.start_btn.setEnabled(False)
        self.open_test_btn.setEnabled(False)
        self.open_worker.start()

    def on_open_finished(self):
        self.start_btn.setEnabled(True)
        self.open_test_btn.setEnabled(True)

    def on_progress(self, msg: str):
        # Status tracks each visible phone action. The full trace stays in log.
        if self.worker and self.worker.isRunning() and not self.next_btn.isEnabled():
            self.status.setText("Đang thao tác: " + msg)

    def show_outcome(self, result: dict):
        self.refresh_history()
        self.append(
            f"{result.get('serial')} | {result.get('platform')} | "
            f"{result.get('status')}: {result.get('detail', '')}"
        )

    def on_reserved(self, result: dict):
        self.active_history_id = result.get('history_id')
        # The database reservation exists before the first phone action.
        for index in range(self.videos.count() - 1, -1, -1):
            if Path(self.videos.item(index).text()).resolve() == Path(result['video']).resolve():
                self.videos.takeItem(index)
        self.refresh_history()

    def on_manual_step(self, msg: str):
        self.status.setText(msg)
        self.progress_label.setText("Đang chờ bạn xử lý bước hiện tại trên điện thoại.")
        self.next_btn.setEnabled(True)
        self.posted_btn.setEnabled(True)
        self.mark_posted_btn.setEnabled(True)
        self.refresh_history()
        for row, item in enumerate(self.history_rows):
            if item['id'] == self.active_history_id:
                self.history_table.selectRow(row)
                break
        self.append("CẦN THAO TÁC: " + msg)

    def resume_upload(self):
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        self.mark_posted_btn.setEnabled(False)
        self.status.setText("Đang tiếp tục bước hiện tại...")
        self.progress_label.setText("Tiếp tục sau khi bạn đã thao tác trên điện thoại.")
        if self.worker:
            self.worker.proceed()

    def confirm_posted(self):
        if not self.worker or not self.worker.isRunning():
            self.resolve_history(True)
            return
        if QMessageBox.question(self, 'Xác nhận kết quả',
                'Bạn đã kiểm tra đúng video xuất hiện trong tài khoản TikTok/Facebook? '
                'Xác nhận sẽ lưu lịch sử và chặn đăng lại nội dung này.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        self.mark_posted_btn.setEnabled(False)
        if self.worker:
            self.worker.proceed('published')

    def refresh_history(self):
        selected = self.history_table.currentRow()
        previous = getattr(self, 'history_rows', [])
        selected_id = previous[selected]['id'] if 0 <= selected < len(previous) else None
        all_rows = self.history.video_rows()
        self.history_rows = [item for item in all_rows
                             if item['status'] != 'not_published']
        retry_paths = {Path(item['video']).resolve() for item in all_rows if item['status'] == 'not_published'}
        attempted_paths = {Path(item['video']).resolve() for item in self.history_rows} - retry_paths
        for index in range(self.videos.count() - 1, -1, -1):
            if Path(self.videos.item(index).text()).resolve() in attempted_paths:
                self.videos.takeItem(index)
        self.history_table.setRowCount(len(self.history_rows))
        for row, item in enumerate(self.history_rows):
            try:
                local_timestamp = datetime.fromisoformat(
                    item['updated_at'].replace('Z', '+00:00')
                ).astimezone().strftime('%d/%m %H:%M')
            except ValueError:
                local_timestamp = item['updated_at'][:16].replace('T', ' ')
            values = (local_timestamp, item['serial'], item['platform'],
                      Path(item['video']).name,
                      STATUS_LABELS.get(item['status'], 'Chưa xác nhận'))
            confirmed = item['status'] in ('published', 'published_manual')
            failed = item['status'] == 'error'
            background = '#DCFCE7' if confirmed else ('#FEE2E2' if failed else '#FEF3C7')
            foreground = '#14532D' if confirmed else ('#991B1B' if failed else '#78350F')
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setBackground(QBrush(QColor(background)))
                cell.setForeground(QBrush(QColor(foreground)))
                cell.setToolTip(item['detail'] + '\nSố lần thử: ' + str(item['attempt_count'])
                                + '\nSHA-256: ' + item['sha256'])
                self.history_table.setItem(row, col, cell)
            if item['id'] == selected_id:
                self.history_table.selectRow(row)
        self.update_summary()

    def resolve_history(self, published: bool):
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, 'Chọn video', 'Chọn dòng video trong bảng lịch sử để xác nhận kết quả.')
            return
        item = self.history_rows[row]
        if self.worker and self.worker.isRunning():
            if published and item['id'] == self.active_history_id and self.next_btn.isEnabled():
                self.confirm_posted()
            else:
                QMessageBox.information(self, 'Đang thao tác',
                                        'Chỉ xác nhận video hiện tại khi app đang chờ bạn. Với video khác, hãy dừng lượt chạy trước.')
            return
        text = ('Xác nhận video đã đăng thành công?' if published else
                'Bạn đã kiểm tra và chắc chắn video CHƯA đăng? Cho phép thử lại có thể tạo bài trùng nếu kiểm tra sai.')
        if QMessageBox.question(self, 'Đối chiếu lịch sử', text + '\n' + item['video'],
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if published:
            self.history.update(item['id'], 'published_manual',
                                'Người dùng đối chiếu kết quả trên điện thoại.')
        else:
            if not Path(item['video']).is_file():
                QMessageBox.warning(self, 'Không tìm thấy video',
                                    'File video đã bị di chuyển hoặc xóa. Hãy khôi phục file trước khi cho thử lại.')
                return
            # Persist the queue first so a failed save cannot lose the video.
            self.videos.add_video(item['video'])
            self.save_queue()
            self.history.release(item['sha256'], item['platform'])
        self.refresh_history()

    def stop_upload(self):
        if self.worker:
            self.worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        self.status.setText("Đang dừng sau thao tác hiện tại...")
        self.progress_label.setText("Đang dừng — kiểm tra lịch sử trước khi thử lại.")

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.open_test_btn.setEnabled(True)
        self.mark_posted_btn.setEnabled(True)
        self.release_btn.setEnabled(True)
        self.posted_btn.setEnabled(False)
        self.refresh_history()
        self.cancel_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        if self.worker and self.worker.cancel_event.is_set():
            self.status.setText("Đã dừng lượt xử lý. Các trạng thái chưa rõ vẫn cần đối chiếu.")
            self.progress_label.setText("Đã dừng. Xem Lịch sử & chống trùng để xử lý bài đang dở.")
        else:
            self.progress_bar.setValue(self.progress_bar.maximum())
            self.progress_bar.setFormat("Đã kết thúc lượt xử lý")
            self.progress_label.setText("Đã kết thúc lượt chạy. Kiểm tra kết quả từng bài ở lịch sử.")
            self.status.setText(
                "Đã xử lý hết lượt trong hàng đợi. Bài 'đã bấm Đăng — chưa xác nhận' "
                "không được tính là đăng thành công."
            )

    def shutdown(self) -> bool:
        if self.open_worker and self.open_worker.isRunning():
            self.open_worker.cancel_event.set()
            if not self.open_worker.wait(4000):
                return False
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(4000):
                self.append("ADB đang hoàn tất tác vụ. Hãy đóng lại khi tiến trình dừng.")
                return False
        return True
