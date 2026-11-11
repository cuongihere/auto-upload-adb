"""Auto Upload tab for the existing Android Scrcpy Manager."""
from __future__ import annotations

import threading
import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from upload_engine import UploadRequest, UploadError, run_request
from upload_history import UploadHistory


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
    outcome = Signal(dict)
    manual_step = Signal(str)

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
                    self.cancel_event, on_manual_wait=manual_wait
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
        self.history = UploadHistory()
        self.history.import_legacy(Path(__file__).resolve().parent / 'logs' / 'auto_upload_history.jsonl')

        layout = QVBoxLayout(self)
        help_label = QLabel(
            "Chọn/tick thiết bị ở bảng phía trên, thêm video PC, chọn nền tảng và nhấn Bắt đầu. "
            "App sẽ thao tác trực tiếp trên điện thoại: Home → icon → Tạo video → Album → Next → Caption. "
            "Mặc định dừng trước nút Đăng. Nếu một bước không nhận diện được, app dừng an toàn và lưu ảnh lỗi."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        first = QHBoxLayout()
        video_box = QGroupBox("1. Video trên máy tính")
        vl = QVBoxLayout(video_box)
        self.videos = VideoList()
        vl.addWidget(self.videos)
        video_actions = QHBoxLayout()
        btn_add = QPushButton("Thêm video")
        btn_remove = QPushButton("Xóa đã chọn")
        btn_clear = QPushButton("Xóa danh sách")
        video_actions.addWidget(btn_add)
        video_actions.addWidget(btn_remove)
        video_actions.addWidget(btn_clear)
        vl.addLayout(video_actions)
        btn_add.clicked.connect(self.add_files)
        btn_remove.clicked.connect(lambda: [self.videos.takeItem(self.videos.row(i)) for i in self.videos.selectedItems()])
        btn_clear.clicked.connect(self.videos.clear)
        first.addWidget(video_box, 2)

        config_box = QGroupBox("2. Nền tảng & nội dung")
        cl = QVBoxLayout(config_box)
        platforms = QHBoxLayout()
        self.tiktok = QCheckBox("TikTok")
        self.facebook = QCheckBox("Facebook")
        self.tiktok.setChecked(True)
        platforms.addWidget(self.tiktok)
        platforms.addWidget(self.facebook)
        platforms.addStretch()
        cl.addLayout(platforms)
        cl.addWidget(QLabel("Caption TikTok:"))
        self.tiktok_caption = QPlainTextEdit()
        self.tiktok_caption.setPlaceholderText("Caption và hashtag TikTok")
        self.tiktok_caption.setMaximumHeight(80)
        cl.addWidget(self.tiktok_caption)
        cl.addWidget(QLabel("Caption Facebook:"))
        self.facebook_caption = QPlainTextEdit()
        self.facebook_caption.setPlaceholderText("Caption và hashtag Facebook")
        self.facebook_caption.setMaximumHeight(80)
        cl.addWidget(self.facebook_caption)
        self.auto_publish = QCheckBox("Tự bấm Đăng cuối cùng sau khi đã chọn video/caption (thử nghiệm)")
        self.auto_publish.setToolTip(
            "Chỉ bật sau khi đã thử trên tài khoản và thiết bị riêng. "
            "Nếu giao diện thay đổi, app sẽ dừng để xử lý thủ công."
        )
        cl.addWidget(self.auto_publish)
        self.choose_latest = QCheckBox("Tự chọn đúng video trong album riêng của lượt upload")
        self.choose_latest.setChecked(True)
        self.choose_latest.setToolTip(
            "Mỗi lượt copy có một album AU_ riêng. Chỉ chọn khi album có duy nhất đúng ID, tên và đường dẫn video. "
            "Không chọn thumbnail đầu tiên trong Gần đây."
        )
        cl.addWidget(self.choose_latest)
        first.addWidget(config_box, 2)
        layout.addLayout(first)

        row = QHBoxLayout()
        self.start_btn = QPushButton("Bắt đầu thao tác trên điện thoại")
        self.next_btn = QPushButton("Tiếp tục bước đang dở")
        self.posted_btn = QPushButton("Đã đăng thành công")
        self.cancel_btn = QPushButton("Dừng")
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        row.addWidget(self.start_btn)
        row.addWidget(self.next_btn)
        row.addWidget(self.posted_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch()
        layout.addLayout(row)

        self.status = QLabel("Sẵn sàng.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setPlaceholderText("Tiến trình đăng và trạng thái từng video sẽ hiển thị ở đây.")
        layout.addWidget(self.log, 1)

        history_box = QGroupBox('Lịch sử chống đăng trùng (theo nội dung video và nền tảng, trên mọi máy)')
        hl = QVBoxLayout(history_box)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(['Thời gian', 'Máy', 'Nền tảng', 'Video', 'Kết quả'])
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.history_table.setMaximumHeight(170)
        hl.addWidget(self.history_table)
        hr = QHBoxLayout()
        refresh = QPushButton('Làm mới lịch sử')
        self.mark_posted_btn = QPushButton('Xác nhận bài đã đăng')
        self.release_btn = QPushButton('Xác nhận chưa đăng / Cho thử lại')
        hr.addWidget(refresh)
        hr.addWidget(self.mark_posted_btn)
        hr.addWidget(self.release_btn)
        hl.addLayout(hr)
        layout.addWidget(history_box)
        refresh.clicked.connect(self.refresh_history)
        self.mark_posted_btn.clicked.connect(lambda: self.resolve_history(True))
        self.release_btn.clicked.connect(lambda: self.resolve_history(False))
        self.posted_btn.clicked.connect(self.confirm_posted)
        self.refresh_history()
        self.load_queue()
        self.videos.model().rowsInserted.connect(self.save_queue)
        self.videos.model().rowsRemoved.connect(self.save_queue)
        self.tiktok_caption.textChanged.connect(self.save_queue)
        self.facebook_caption.textChanged.connect(self.save_queue)

        self.start_btn.clicked.connect(self.start_upload)
        self.next_btn.clicked.connect(self.resume_upload)
        self.cancel_btn.clicked.connect(self.stop_upload)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Chọn video", "", "Video (*.mp4 *.mov *.m4v *.3gp)"
        )
        for file in files:
            self.videos.add_video(file)

    def save_queue(self, *args):
        path = Path(__file__).resolve().parent / 'config' / 'upload_queue.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {'videos': [self.videos.item(i).text() for i in range(self.videos.count())],
                'captions': {'TikTok': self.tiktok_caption.toPlainText(),
                             'Facebook': self.facebook_caption.toPlainText()}}
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temp.replace(path)

    def load_queue(self):
        path = Path(__file__).resolve().parent / 'config' / 'upload_queue.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            for video in data.get('videos', []):
                self.videos.add_video(video)
            self.tiktok_caption.setPlainText(data.get('captions', {}).get('TikTok', ''))
            self.facebook_caption.setPlainText(data.get('captions', {}).get('Facebook', ''))
        except (OSError, ValueError, TypeError):
            pass

    def start_upload(self):
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
                choose_latest=self.choose_latest.isChecked()
            )
            for s in serials for v in videos
        ]
        self.worker = UploadWorker(requests, adb)
        self.worker.message.connect(self.append)
        self.worker.message.connect(self.on_progress)
        self.worker.outcome.connect(self.show_outcome)
        self.worker.manual_step.connect(self.on_manual_step)
        self.worker.finished.connect(self.on_finished)
        self.start_btn.setEnabled(False)
        self.mark_posted_btn.setEnabled(False)
        self.release_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status.setText(
            f"Đang xử lý {len(requests)} video × thiết bị; {len(platforms)} nền tảng."
        )
        self.worker.start()

    def append(self, msg: str):
        self.log.appendPlainText(msg)

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

    def on_manual_step(self, msg: str):
        self.status.setText(msg)
        self.next_btn.setEnabled(True)
        self.posted_btn.setEnabled(True)
        self.refresh_history()
        self.append("CẦN THAO TÁC: " + msg)

    def resume_upload(self):
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        self.status.setText("Đang tiếp tục hàng đợi...")
        if self.worker:
            self.worker.proceed()

    def confirm_posted(self):
        if QMessageBox.question(self, 'Xác nhận kết quả',
                'Bạn đã kiểm tra đúng video xuất hiện trong tài khoản TikTok/Facebook? '
                'Xác nhận sẽ lưu lịch sử và chặn đăng lại nội dung này.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        if self.worker:
            self.worker.proceed('published')

    def refresh_history(self):
        self.history_rows = self.history.rows()
        self.history_table.setRowCount(len(self.history_rows))
        for row, item in enumerate(self.history_rows):
            values = (item['updated_at'][:19].replace('T', ' ') + ' UTC', item['serial'],
                      item['platform'], Path(item['video']).name, item['status'])
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(item['detail'] + '\nSHA-256: ' + item['sha256'])
                self.history_table.setItem(row, col, cell)

    def resolve_history(self, published: bool):
        if self.worker and self.worker.isRunning():
            return
        row = self.history_table.currentRow()
        if row < 0:
            return
        item = self.history_rows[row]
        text = ('Xác nhận video đã đăng thành công?' if published else
                'Bạn đã kiểm tra và chắc chắn video CHƯA đăng? Cho phép thử lại có thể tạo bài trùng nếu kiểm tra sai.')
        if QMessageBox.question(self, 'Đối chiếu lịch sử', text + '\n' + item['video'],
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.history.update(item['id'], 'published_manual' if published else 'not_published',
                            'Người dùng đối chiếu kết quả trên điện thoại.')
        self.refresh_history()

    def stop_upload(self):
        if self.worker:
            self.worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.posted_btn.setEnabled(False)
        self.status.setText("Đang dừng sau thao tác hiện tại...")

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.mark_posted_btn.setEnabled(True)
        self.release_btn.setEnabled(True)
        self.posted_btn.setEnabled(False)
        self.refresh_history()
        self.cancel_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        if self.worker and self.worker.cancel_event.is_set():
            self.status.setText("Đã dừng.")
        else:
            self.status.setText(
                "Đã xử lý xong hàng đợi. Chú ý: trạng thái submitted_unverified "
                "KHÔNG có nghĩa video đã xuất bản thành công."
            )

    def shutdown(self) -> bool:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(4000):
                self.append("ADB đang hoàn tất tác vụ. Hãy đóng lại khi tiến trình dừng.")
                return False
        return True
