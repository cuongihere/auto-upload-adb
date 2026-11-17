import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication, QEvent

from auto_upload_tab import AutoUploadTab
from upload_history import UploadHistory, fingerprint


class UploadQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name).resolve()
        self.video = self.folder / 'fish.mp4'
        self.video.write_bytes(b'fish')
        self.other = self.folder / 'waiting.mp4'
        self.other.write_bytes(b'waiting')
        self.history = UploadHistory(self.folder / 'history.db')
        self.queue = self.folder / 'queue.json'
        self.queue.write_text(json.dumps({'videos': [str(self.video), str(self.other)]}))
        for p in (patch('auto_upload_tab.QUEUE_FILE', self.queue),
                  patch('auto_upload_tab.UploadHistory', return_value=self.history),
                  patch.object(self.history, 'import_legacy'),
                  patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes)):
            p.start()
            self.addCleanup(p.stop)
        self.tab = self.make_tab()

    def make_tab(self):
        tab = AutoUploadTab(lambda: 'adb', lambda: ['phone'], lambda _: True)

        def cleanup():
            tab.close()
            tab.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.app.processEvents()

        self.addCleanup(cleanup)
        return tab

    def reserve(self):
        return self.history.reserve(fingerprint(self.video), 'TikTok', 'phone', self.video)[0]

    def queued(self, tab=None):
        videos = (tab or self.tab).videos
        return [videos.item(i).text() for i in range(videos.count())]

    def test_started_video_moves_to_history_but_waiting_video_stays(self):
        self.reserve()
        self.tab.on_reserved({'video': str(self.video)})
        self.assertEqual(self.queued(), [str(self.other)])
        self.assertEqual(self.tab.history_table.rowCount(), 1)
        self.assertEqual(json.loads(self.queue.read_text())['videos'], [str(self.other)])
        self.assertEqual(self.queued(self.make_tab()), [str(self.other)])

    def test_retry_moves_group_back_to_queue_and_survives_restart(self):
        first = self.reserve()
        self.history.update(first, 'not_published')
        self.reserve()
        self.tab.on_reserved({'video': str(self.video)})
        self.tab.history_table.selectRow(0)
        self.tab.resolve_history(False)
        self.assertEqual(self.tab.history_table.rowCount(), 0)
        self.assertEqual(self.queued().count(str(self.video)), 1)
        restarted = self.make_tab()
        self.assertIn(str(self.video), self.queued(restarted))
        self.assertEqual(restarted.history_table.rowCount(), 0)
        self.assertIsNotNone(self.reserve())

    def test_history_distinguishes_confirmed_review_and_errors(self):
        ident = self.reserve()
        for status, color in [('in_progress', '#fef3c7'), ('needs_review', '#fef3c7'),
                              ('error', '#fee2e2'), ('published', '#dcfce7'),
                              ('published_manual', '#dcfce7')]:
            self.history.update(ident, status)
            self.tab.refresh_history()
            for col in range(5):
                self.assertEqual(self.tab.history_table.item(0, col).background().color().name(), color)

    def test_compact_dashboard_counters_and_safe_actions(self):
        self.assertIn('1/1 online', self.tab.summary_devices.text())
        self.assertIn('Video chờ: 2', self.tab.summary_videos.text())
        self.assertIn('TikTok', self.tab.summary_platforms.text())
        self.assertTrue(self.tab.advanced_options.isHidden())
        self.assertFalse(self.tab.auto_publish.isChecked())
        self.assertFalse(self.tab.posted_btn.isEnabled())
        self.tab.advanced_btn.setChecked(True)
        self.assertFalse(self.tab.advanced_options.isHidden())

    def test_progress_names_device_and_current_video(self):
        self.tab.on_request_started(2, 3, 'phone', 'fish.mp4')
        self.assertEqual(self.tab.progress_bar.maximum(), 3)
        self.assertEqual(self.tab.progress_bar.value(), 1)
        self.assertIn('fish.mp4', self.tab.progress_label.text())
        self.assertIn('phone', self.tab.progress_label.text())

    def test_startup_removes_previously_attempted_video_from_old_queue(self):
        self.reserve()
        self.assertEqual(self.queued(self.make_tab()), [str(self.other)])

    def test_missing_retry_file_keeps_history(self):
        self.reserve()
        self.tab.on_reserved({'video': str(self.video)})
        self.video.unlink()
        self.tab.history_table.selectRow(0)
        with patch.object(QMessageBox, 'warning') as warning:
            self.tab.resolve_history(False)
        warning.assert_called_once()
        self.assertEqual(self.tab.history_table.rowCount(), 1)
        self.assertNotIn(str(self.video), self.queued())

    def test_history_confirmation_resumes_current_manual_wait(self):
        ident = self.reserve()
        self.history.update(ident, 'manual_required')
        worker = Mock()
        worker.isRunning.return_value = True
        self.tab.worker = worker
        self.tab.on_reserved({'video': str(self.video), 'history_id': ident})
        self.tab.on_manual_step('Kiểm tra bài đã đăng')
        self.assertTrue(self.tab.mark_posted_btn.isEnabled())
        self.assertEqual(self.tab.history_table.currentRow(), 0)
        self.tab.resolve_history(True)
        worker.proceed.assert_called_once_with('published')
        self.assertFalse(self.tab.mark_posted_btn.isEnabled())

    def test_idle_top_confirmation_updates_selected_history(self):
        ident = self.reserve()
        self.history.update(ident, 'needs_review')
        self.tab.refresh_history()
        self.tab.history_table.selectRow(0)
        self.tab.confirm_posted()
        self.assertEqual(self.history.video_rows()[0]['status'], 'published_manual')


if __name__ == '__main__':
    unittest.main()
