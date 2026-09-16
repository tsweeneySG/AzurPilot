import inspect
import unittest

from module.map.camera import Camera


class TestCameraFocusCap(unittest.TestCase):
    def test_focus_to_caps_opposite_swipes(self):
        src = inspect.getsource(Camera.focus_to)
        self.assertIn('opposite >= 2', src)
        self.assertIn('swipes >= 6', src)
        self.assertIn('_raise_focus_swipe_cap', src)

    def test_full_scan_caps_predict_fail(self):
        src = inspect.getsource(Camera.full_scan)
        self.assertIn('predict_fail >= 5', src)
        self.assertIn('full_scan predict failed', src)
