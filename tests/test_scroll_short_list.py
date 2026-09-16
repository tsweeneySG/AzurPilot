import unittest

from module.ui.scroll import Scroll


class TestScrollShortList(unittest.TestCase):
    def test_oversize_thumb_fills(self):
        scroll = Scroll((1176, 210, 1180, 720), color=(255, 255, 255), name='OS_SHOP_SCROLL')
        # total = 720 - 210 = 510; Asami JP Gibraltar reported length 513
        scroll.length = 513
        self.assertTrue(scroll.thumb_fills_track())

    def test_equal_length_fills(self):
        scroll = Scroll((1176, 210, 1180, 720), color=(255, 255, 255), name='OS_SHOP_SCROLL')
        # Same shop, next restart: length == total → cal_position used to report 1.00
        scroll.length = 510
        self.assertTrue(scroll.thumb_fills_track())

    def test_normal_thumb_does_not_fill(self):
        scroll = Scroll((1176, 210, 1180, 720), color=(255, 255, 255), name='OS_SHOP_SCROLL')
        scroll.length = 136
        self.assertFalse(scroll.thumb_fills_track())
