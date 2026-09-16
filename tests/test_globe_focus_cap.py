import inspect
import unittest

from module.os.globe_camera import GlobeCamera


class TestGlobeFocusCap(unittest.TestCase):
    def test_globe_focus_to_caps_clicks_and_delays(self):
        src = inspect.getsource(GlobeCamera.globe_focus_to)
        self.assertIn('click_count >= 5', src)
        self.assertIn('attempts >= 8', src)
        self.assertIn("task_stop('Cannot pin globe zone')", src)
        self.assertIn('task_delay(minute=30)', src)
