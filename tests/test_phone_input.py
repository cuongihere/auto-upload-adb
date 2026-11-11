import ctypes
import unittest
from unittest.mock import Mock, patch

import phone_input


@unittest.skipUnless(phone_input.WINDOWS, 'Win32 native focus')
class NativeInputTest(unittest.TestCase):
    def api(self):
        api = Mock()
        api.IsWindow.return_value = True
        api.GetParent.return_value = 20
        def thread(hwnd, pid):
            if pid is not None:
                pid._obj.value = 123
            return 2
        api.GetWindowThreadProcessId.side_effect = thread
        api.AttachThreadInput.return_value = True
        api.GetAncestor.return_value = 30
        api.GetForegroundWindow.return_value = 30
        api.GetFocus.return_value = 10
        api.GetAsyncKeyState.return_value = 0
        api.SendInput.side_effect = lambda count, *_: count
        return api

    def test_wrong_process_never_receives_input(self):
        api = self.api()
        with patch.object(phone_input, 'user32', api):
            with self.assertRaises(OSError):
                phone_input.send_shortcut(10, 20, 999, 'V')
        api.SendInput.assert_not_called()

    def test_detached_child_never_receives_input(self):
        api = self.api()
        api.GetParent.return_value = 999
        with patch.object(phone_input, 'user32', api):
            with self.assertRaises(OSError):
                phone_input.send_shortcut(10, 20, 123, 'V')
        api.SendInput.assert_not_called()

    def test_focus_failure_never_types_into_another_app(self):
        api = self.api()
        api.GetFocus.return_value = 999
        with patch.object(phone_input, 'user32', api):
            with self.assertRaises(OSError):
                phone_input.send_shortcut(10, 20, 123, 'V')
        api.SendInput.assert_not_called()
        self.assertFalse(api.AttachThreadInput.call_args.args[-1])

    def test_success_sends_balanced_ctrl_v_to_focused_child(self):
        api = self.api()
        events = []
        def send(count, inputs, size):
            events.extend((inputs[i].ki.wVk, inputs[i].ki.dwFlags) for i in range(count))
            return count
        api.SendInput.side_effect = send
        with patch.object(phone_input, 'user32', api):
            phone_input.send_shortcut(10, 20, 123, 'V')
        self.assertEqual(events, [(0x11, 0), (ord('V'), 0), (ord('V'), 2), (0x11, 2)])
        self.assertFalse(api.AttachThreadInput.call_args.args[-1])

    def test_held_shift_does_not_trigger_legacy_paste(self):
        api = self.api()
        api.GetAsyncKeyState.return_value = 0x8000
        with patch.object(phone_input, 'user32', api):
            with self.assertRaises(OSError):
                phone_input.send_shortcut(10, 20, 123, 'V')
        api.SendInput.assert_not_called()

    def test_native_input_structure_has_correct_windows_size(self):
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(phone_input.INPUT), expected)


try:
    from PySide6.QtWidgets import QApplication
    from embedded_scrcpy import PhonePreviewPanel
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, 'PySide6 not installed')
class ClipboardPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = PhonePreviewPanel()
        self.panel.viewport.shortcut = Mock(return_value=True)
        self.panel.viewport.keyboard_focus = Mock(return_value=True)
        self.previous_clipboard = self.app.clipboard().text()

    def tearDown(self):
        self.app.clipboard().setText(self.previous_clipboard)
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()

    def test_unicode_multiline_uses_clipboard_not_adb_text(self):
        text = 'Chim gõ kiến 🐦\n#khámphá & ký tự % \' "'
        self.panel.composer.setPlainText(text)
        self.panel.insert_composed()
        self.assertEqual(self.app.clipboard().text(), text)
        self.panel.viewport.shortcut.assert_called_once_with('V')

    def test_empty_clipboard_does_not_paste_stale_phone_text(self):
        self.app.clipboard().clear()
        self.panel.paste_clipboard()
        self.panel.viewport.shortcut.assert_not_called()

    def test_failed_focus_preserves_composer_and_clipboard(self):
        self.app.clipboard().setText('existing')
        self.panel.composer.setPlainText('tiếng Việt')
        self.panel.viewport.keyboard_focus.return_value = False
        self.panel.insert_composed()
        self.assertEqual(self.app.clipboard().text(), 'existing')
        self.assertEqual(self.panel.composer.toPlainText(), 'tiếng Việt')
        self.panel.viewport.shortcut.assert_not_called()

    def test_detach_disables_paste_and_keyboard(self):
        self.panel._on_attached('phone')
        self.assertTrue(self.panel.btn_paste.isEnabled())
        self.panel._on_detached()
        self.assertFalse(self.panel.btn_paste.isEnabled())
        self.assertFalse(self.panel.btn_keyboard.isEnabled())


if __name__ == '__main__':
    unittest.main()
