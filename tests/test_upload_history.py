import concurrent.futures
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from upload_history import UploadHistory, fingerprint
from upload_engine import ADB, UploadRequest, run_request
from tap_flow import TouchFlow, FlowStopped


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.video = self.folder / 'video.mp4'
        self.video.write_bytes(b'video-content')
        self.path = self.folder / 'history.sqlite3'
        self.history = UploadHistory(self.path)

    def reserve(self, serial='phone'):
        return self.history.reserve(fingerprint(self.video), 'TikTok', serial, self.video)

    def test_renaming_and_restart_cannot_bypass_duplicate(self):
        ident, _ = self.reserve()
        self.history.update(ident, 'published_manual')
        renamed = self.folder / 'renamed.mp4'
        renamed.write_bytes(self.video.read_bytes())
        ident2, dup = UploadHistory(self.path).reserve(fingerprint(renamed), 'TikTok', 'other-phone', renamed)
        self.assertIsNone(ident2)
        self.assertEqual(dup['id'], ident)

    def test_uncertain_submission_and_crashed_reservation_block(self):
        ident, _ = self.reserve()
        for status in ('in_progress', 'prepared', 'submitting', 'submitted_unverified', 'needs_review'):
            self.history.update(ident, status)
            self.assertIsNone(self.reserve()[0], status)

    def test_only_explicit_not_published_allows_retry(self):
        ident, _ = self.reserve()
        self.history.update(ident, 'not_published')
        new, _ = self.reserve()
        self.assertNotEqual(ident, new)
        self.assertEqual(len(self.history.rows()), 2)

    def test_parallel_reservation_has_one_winner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self.reserve, ['a', 'b', 'c', 'd']))
        self.assertEqual(sum(ident is not None for ident, _ in results), 1)

    def test_same_video_can_use_different_platform(self):
        self.reserve()
        ident, _ = self.history.reserve(fingerprint(self.video), 'Facebook', 'phone', self.video)
        self.assertIsNotNone(ident)

    @patch('upload_engine.write_history')
    @patch('upload_engine.ADB')
    def test_duplicate_is_skipped_before_any_adb_or_transfer(self, adb_class, journal):
        self.reserve()
        req = UploadRequest('phone', self.video, ('TikTok',), {})
        result = run_request(req, 'adb', lambda _: None, threading.Event(), history=self.history)
        self.assertEqual(result[0]['status'], 'duplicate_skipped')
        adb_class.return_value.verify_online.assert_not_called()
        adb_class.return_value.transfer.assert_not_called()

    @patch('upload_engine.write_history')
    @patch('tap_flow.TouchFlow')
    @patch('upload_engine.ADB')
    def test_disconnect_after_tap_intent_stays_blocked(self, adb_class, flow_class, journal):
        adb_class.return_value.transfer.return_value = ('/sdcard/video.mp4', 'content://media/1')
        flow = flow_class.return_value
        def execute():
            flow.before_submit()
            raise RuntimeError('device disconnected')
        flow.execute.side_effect = execute
        req = UploadRequest('phone', self.video, ('TikTok',), {}, auto_publish=True)
        result = run_request(req, 'adb', lambda _: None, threading.Event(), history=self.history)
        self.assertEqual(result[0]['status'], 'submitted_unverified')
        self.assertIsNone(self.reserve()[0])

    @patch('upload_engine.write_history')
    @patch('tap_flow.TouchFlow')
    @patch('upload_engine.ADB')
    def test_manual_confirmation_persists_published(self, adb_class, flow_class, journal):
        adb_class.return_value.transfer.return_value = ('/sdcard/video.mp4', None)
        flow_class.return_value.execute.return_value = 'prepared'
        req = UploadRequest('phone', self.video, ('TikTok',), {})
        result = run_request(req, 'adb', lambda _: None, threading.Event(),
                             on_manual_wait=lambda _: 'published', history=self.history)
        self.assertEqual(result[0]['status'], 'published_manual')
        self.assertEqual(self.history.rows()[0]['status'], 'published_manual')

    def test_legacy_handoff_requires_review_once(self):
        import json
        legacy = self.folder / 'old.jsonl'
        legacy.write_text(json.dumps(dict(video=str(self.video), serial='phone', platform='TikTok',
                                         status='manual_required')) + '\ninvalid', encoding='utf-8')
        self.history.import_legacy(legacy)
        self.history.import_legacy(legacy)
        self.assertEqual(len(self.history.rows()), 1)
        self.assertEqual(self.history.rows()[0]['status'], 'needs_review')


class FlowRecoveryTest(unittest.TestCase):
    def flow(self):
        adb = Mock()
        adb.cancelled = threading.Event()
        return TouchFlow(adb, 'TikTok', '/a.mp4', None, '', False, False, lambda _: None)

    def test_continue_retries_failed_stage_not_whole_video(self):
        f = self.flow()
        f.home_to_icon = Mock()
        f.open_create = Mock()
        f.open_gallery = Mock(side_effect=[FlowStopped('picker'), None])
        f.select_video = Mock()
        f.navigate_edit = Mock()
        f.enter_caption = Mock()
        f.publish = Mock(return_value='prepared')
        f.manual_handler = Mock(return_value='retry')
        self.assertEqual(f.execute(), 'prepared')
        self.assertEqual(f.open_gallery.call_count, 2)
        f.home_to_icon.assert_called_once()

    def test_return_to_feed_is_not_publish_evidence(self):
        f = self.flow()
        f.wait_nodes = Mock(return_value=[dict(text='Trang chủ', desc='', package=f.package, enabled=True)])
        f.sleep = Mock()
        with patch('tap_flow.time.monotonic', side_effect=[0, 0, 100]):
            self.assertFalse(f.verify_publication(seconds=10))


class AdbRegressionTest(unittest.TestCase):
    def test_large_stdout_does_not_fill_pipe_and_deadlock(self):
        # Exercise the real subprocess communication loop without an Android phone.
        original = subprocess.Popen
        def spawn(*args, **kwargs):
            return original([sys.executable, '-c', "print('x'*200000)"], **kwargs)
        adb = ADB('unused', 'phone', threading.Event())
        with patch('upload_engine.subprocess.Popen', side_effect=spawn):
            self.assertEqual(len(adb.run(['exec-out', 'cat'], timeout=5)), 200000)

    def test_remote_shell_preserves_sql_and_caption_literals(self):
        proc = Mock()
        proc.communicate.return_value = ('ok', '')
        proc.returncode = 0
        proc.poll.return_value = 0
        adb = ADB('adb', 'phone', threading.Event())
        with patch('upload_engine.subprocess.Popen', return_value=proc) as spawn:
            adb.run(['shell', 'content', 'query', '--where', "_display_name='a.mp4'"])
            import shlex
            command = spawn.call_args.args[0]
            self.assertEqual(shlex.split(command[-1])[-1], "_display_name='a.mp4'")


if __name__ == '__main__':
    unittest.main()
