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

    def test_five_pixel_gap_cannot_be_dragged(self):
        scroll = Scroll((1176, 210, 1180, 720), color=(255, 255, 255), name='OS_SHOP_SCROLL')
        # Booty 15:24: length 505 / total 510，位置被夹成 1.00，空滑直到重启
        scroll.length = 505
        self.assertTrue(scroll.thumb_fills_track())

    def test_eleven_pixel_gap_can_still_drag(self):
        scroll = Scroll((1176, 210, 1180, 720), color=(255, 255, 255), name='OS_SHOP_SCROLL')
        scroll.length = 499
        self.assertFalse(scroll.thumb_fills_track())
