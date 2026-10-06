import inspect
import unittest

from module.map.camera import Camera


class TestCameraFocusCap(unittest.TestCase):
    def test_focus_to_caps_opposite_swipes(self):
        src = inspect.getsource(Camera.focus_to)
        self.assertIn('opposite >= 2', src)
        self.assertIn('swipes >= 6', src)
        self.assertIn('_raise_focus_swipe_cap', src)

    def test_swipe_cap_delays_task_instead_of_map_error(self):
        src = inspect.getsource(Camera._raise_focus_swipe_cap)
        self.assertIn('task_delay(minute=2)', src)
        self.assertIn('task_stop', src)

    def test_full_scan_caps_predict_fail(self):
        src = inspect.getsource(Camera.full_scan)
        self.assertIn('predict_fail >= 5', src)
        self.assertIn('full_scan predict failed', src)

    def test_edge_swipe_pinned_at_top_despite_column_jitter(self):
        cam = Camera.__new__(Camera)

        class View:
            center_offset = (0.53, 0.006)
            upper_edge = False
            lower_edge = False
            left_edge = False
            right_edge = True

        cam.view = View()
        self.assertTrue(cam._edge_swipe_pinned(0, -5))
        View.center_offset = (0.50, 0.50)
        self.assertFalse(cam._edge_swipe_pinned(0, -5))
        self.assertFalse(cam._edge_swipe_pinned(-6, 0))
