import threading
import unittest
from unittest.mock import Mock

from upload_engine import ADB
from tap_flow import TouchFlow, FlowStopped
from test_tap_flow import item


ALBUM = 'AU_20261111_abcd'
REMOTE = f'/sdcard/Movies/AutoUpload/{ALBUM}/au_video.mp4'
ROW = f'Row: 0 _id=42, _display_name=au_video.mp4, _data=/storage/emulated/0/Movies/AutoUpload/{ALBUM}/au_video.mp4'


class IsolatedAlbumTest(unittest.TestCase):
    def flow(self):
        adb = Mock()
        adb.cancelled = threading.Event()
        adb.run.return_value = ROW
        f = TouchFlow(adb, 'TikTok', REMOTE, 'content://media/external/video/media/42', '', False, True, lambda _: None)
        f.sleep = Mock()
        f.snapshot = Mock(return_value='failure.png')
        return f

    def test_album_identity_checks_path_id_and_name(self):
        f = self.flow()
        self.assertTrue(f.album_is_exact(ALBUM))
        for wrong in (ROW.replace('_id=42', '_id=99'),
                      ROW.replace('_display_name=au_video', '_display_name=other'),
                      ROW.replace('/Movies/AutoUpload/', '/DCIM/Camera/')):
            f.adb.run.return_value = wrong
            self.assertFalse(f.album_is_exact(ALBUM))

    def test_multiple_files_never_guessed(self):
        f = self.flow()
        f.adb.run.return_value = ROW + '\n' + ROW.replace('_id=42', '_id=43')
        self.assertFalse(f.album_is_exact(ALBUM))

    def test_old_camera_upload_never_guesses_newest_thumbnail(self):
        f = self.flow()
        f.remote = '/sdcard/DCIM/Camera/au_video.mp4'
        tab = item('Video')
        tile = dict(item(cls='android.widget.ImageView'), grid_item=True)
        f.wait_nodes = Mock(return_value=[tab, tile])
        f.latest_in_mediastore = Mock(return_value=True)
        with self.assertRaises(FlowStopped):
            f.select_video()
        f.adb.tap.assert_called_once_with(tab)
        f.latest_in_mediastore.assert_not_called()

    def test_unique_album_picks_only_direct_media_grid_child(self):
        f = self.flow()
        title = item(ALBUM, resource='com.zhiliaoapp.musically:id/tv_title')
        tab = item('Video')
        tile = dict(item(x=120, y=330), grid_item=True)
        unrelated = item('Camera icon', cls='android.widget.ImageView', x=30, y=230)
        f.wait_nodes = Mock(return_value=[title, tab, unrelated, tile])
        f.select_video()
        self.assertTrue(f.selected_media)
        self.assertEqual(f.adb.tap.call_args.args[0], tile)

    def test_album_changed_by_video_filter_never_taps_tile(self):
        f = self.flow()
        title = item(ALBUM, resource='com.zhiliaoapp.musically:id/tv_title')
        tab = item('Video')
        tile = dict(item(), grid_item=True)
        recent = item('Gần đây', resource='com.zhiliaoapp.musically:id/tv_title')
        f.wait_nodes = Mock(side_effect=[[title, tab], [recent, tab, tile]])
        with self.assertRaises(FlowStopped):
            f.select_video()
        f.adb.tap.assert_called_once_with(tab)

    def test_two_tiles_in_album_never_auto_selected(self):
        f = self.flow()
        title = item(ALBUM, resource='com.zhiliaoapp.musically:id/tv_title')
        tab = item('Video')
        f.wait_nodes = Mock(return_value=[title, tab, dict(item(x=100), grid_item=True), dict(item(x=300), grid_item=True)])
        with self.assertRaises(FlowStopped):
            f.select_video()
        f.adb.tap.assert_called_once_with(tab)

    def test_opens_exact_album_instead_of_recents(self):
        f = self.flow()
        recent = item('Gần đây', resource='com.zhiliaoapp.musically:id/tv_title')
        album_row = item(ALBUM)
        title = item(ALBUM, resource='com.zhiliaoapp.musically:id/tv_title')
        f.wait_nodes = Mock(side_effect=[[album_row], [title]])
        self.assertEqual(f.open_isolated_album(ALBUM, [recent]), [title])
        self.assertEqual(f.adb.tap.call_args_list[-1].args[0], album_row)


if __name__ == '__main__':
    unittest.main()
