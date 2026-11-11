"""Unit tests that do not require an attached Android phone."""
import threading
import unittest
from unittest.mock import Mock

from upload_engine import ADB, UploadError, attempt_publish, find_button, find_edit


PKG = "com.zhiliaoapp.musically"


def node(text="", package=PKG, cls="android.widget.Button", desc="", enabled=True):
    return {
        "text": text, "desc": desc, "resource": "",
        "package": package, "class": cls, "enabled": enabled,
        "clickable": True, "x": 90, "y": 200
    }


class SelectorsTest(unittest.TestCase):
    def test_exact_button_never_hits_logout(self):
        ns = [node("Đăng xuất"), node("Đăng", package="com.facebook.katana")]
        self.assertIsNone(find_button(ns, ("Đăng",), PKG))
        self.assertEqual(find_button(ns, ("Đăng",), "com.facebook.katana"), ns[1])

    def test_disabled_and_wrong_package_are_skipped(self):
        ns = [node("Post", enabled=False), node("Post", package="com.example")]
        self.assertIsNone(find_button(ns, ("Post",), PKG))

    def test_find_edit_only_target_application(self):
        ns = [
            node(cls="android.widget.EditText", package="com.android.settings"),
            node(cls="android.widget.EditText"),
        ]
        self.assertEqual(find_edit(ns, PKG), ns[1])


class WorkflowTest(unittest.TestCase):
    def test_unicode_caption_is_not_corrupted(self):
        adb = Mock()
        adb.cancelled = threading.Event()
        adb.ui_nodes.return_value = [
            node("Caption", cls="android.widget.EditText"),
            node("Đăng"),
        ]
        status = attempt_publish(adb, "TikTok", "Video tiếng Việt ❤️", lambda _: None)
        self.assertEqual(status, "manual_required")
        adb.tap.assert_not_called()

    def test_empty_caption_publish_is_unverified(self):
        adb = Mock()
        adb.cancelled = threading.Event()
        post = node("Post")
        adb.ui_nodes.return_value = [node("Details"), post]
        status = attempt_publish(adb, "TikTok", "", lambda _: None)
        self.assertEqual(status, "submitted_unverified")
        adb.tap.assert_called_once_with(post)

    def test_ascii_input_escapes_spaces(self):
        adb = ADB("adb", "serial", threading.Event())
        adb.run = Mock()
        self.assertTrue(adb.input_ascii("Hello world #hello"))
        adb.run.assert_called_once_with(
            ["shell", "input", "text", "Hello%sworld%s#hello"],
            timeout=25,
        )

    def test_unicode_input_is_rejected(self):
        adb = ADB("adb", "serial", threading.Event())
        adb.run = Mock()
        self.assertFalse(adb.input_ascii("Xin chào"))
        adb.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
