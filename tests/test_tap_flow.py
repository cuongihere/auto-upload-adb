"""Touch-flow tests with mocked ADB, no Android device required."""
from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock

from tap_flow import TouchFlow, FlowStopped
from upload_engine import UploadRequest, run_request


PKG = "com.zhiliaoapp.musically"
LAUNCHER = "com.sec.android.app.launcher"


def item(text="", *, package=PKG, desc="", cls="android.widget.TextView",
         clickable=True, enabled=True, x=250, y=400, resource=""):
    return {
        "text": text, "desc": desc, "resource": resource,
        "package": package, "class": cls, "enabled": enabled,
        "clickable": clickable, "x": x, "y": y
    }


def flow(*, publish=False, choose_latest=True, media_uri="content://media/external/video/media/42",
         caption="Test caption"):
    adb = Mock()
    adb.serial = "TEST_SERIAL"
    adb.executable = "adb"
    adb.cancelled = threading.Event()
    adb.run.return_value = ""
    return TouchFlow(
        adb, "TikTok", "/sdcard/DCIM/Camera/au_unique.mp4", media_uri,
        caption, publish, choose_latest, lambda _: None
    )


class TouchFlowTest(unittest.TestCase):
    def test_home_uses_android_home_and_taps_launcher_icon(self):
        f = flow()
        f.sleep = lambda _: None
        f.wait_nodes = Mock(side_effect=[
            [item("TikTok", package=LAUNCHER)],
            [item("Home"), item("Profile")]
        ])
        f.home_to_icon()
        f.adb.run.assert_any_call(["shell", "input", "keyevent", "KEYCODE_HOME"], timeout=12)
        f.adb.tap.assert_called_once_with(item("TikTok", package=LAUNCHER))

    def test_create_taps_accessible_add_post(self):
        f = flow()
        f.sleep = lambda _: None
        add = item("Add post")
        f.wait_nodes = Mock(return_value=[item("Home"), add])
        f.open_create()
        f.adb.tap.assert_called_once_with(add)

    def test_create_unknown_screen_never_taps_random_coordinate(self):
        f = flow()
        f.snapshot = Mock(return_value="failure.png")
        f.wait_nodes = Mock(return_value=[item("Account"), item("Settings")])
        with self.assertRaises(FlowStopped):
            f.open_create()
        f.adb.tap.assert_not_called()
        f.adb.run.assert_not_called()

    def test_video_selection_by_unique_filename(self):
        f = flow()
        f.sleep = lambda _: None
        video = item("au_unique.mp4")
        f.wait_nodes = Mock(return_value=[video])
        f.select_video()
        self.assertTrue(f.selected_media)
        f.adb.tap.assert_called_once_with(video)

    def test_wrong_or_ambiguous_gallery_stops(self):
        f = flow(media_uri=None)
        f.snapshot = Mock(return_value="failure.png")
        f.wait_nodes = Mock(return_value=[item("Yesterday"), item("Other clip")])
        with self.assertRaises(FlowStopped):
            f.select_video()
        f.adb.tap.assert_not_called()

    def test_latest_media_requires_exact_id_and_filename(self):
        f = flow()
        f.adb.run.return_value = "Row: 0 _id=42, _display_name=au_unique.mp4"
        self.assertTrue(f.latest_in_mediastore())
        f.adb.run.return_value = "Row: 0 _id=43, _display_name=other.mp4\nRow: 1 _id=42, _display_name=au_unique.mp4"
        self.assertFalse(f.latest_in_mediastore())

    def test_no_publish_without_confirmed_media(self):
        f = flow(publish=True)
        f.snapshot = Mock(return_value="failure.png")
        f.wait_nodes = Mock(return_value=[item("Post")])
        with self.assertRaises(FlowStopped):
            f.publish()
        f.adb.tap.assert_not_called()

    def test_publish_button_only_after_confirmation(self):
        f = flow(publish=True)
        f.selected_media = True
        f.caption_set = True
        post = item("Post")
        f.wait_nodes = Mock(return_value=[post])
        self.assertEqual("submitted_unverified", f.publish())
        f.adb.tap.assert_called_once_with(post)

    def test_caption_unicode_is_manual_not_corrupted(self):
        f = flow(caption="Bài mới 😍")
        f.selected_media = True
        f.snapshot = Mock(return_value="failure.png")
        f.wait_nodes = Mock(return_value=[item("description", cls="android.widget.EditText")])
        with self.assertRaises(FlowStopped):
            f.enter_caption()
        f.adb.input_ascii.assert_not_called()

    def test_caption_safe_ascii_enters_via_input_text(self):
        f = flow(caption="My video #test")
        f.sleep = lambda _: None
        f.wait_nodes = Mock(side_effect=[
            [item('Add a description', cls='android.widget.EditText')],
            [item('My video #test', cls='android.widget.EditText')],
        ])
        f.adb.input_ascii.return_value = True
        f.enter_caption()
        f.adb.input_ascii.assert_called_once_with("My video #test")
        self.assertTrue(f.caption_set)


if __name__ == "__main__":
    unittest.main()
