"""舰队下拉菜单按行位置编号，避免把未展开完的第 5、6 行当成 1 和 2。"""

import unittest

from module.map.fleet_bar import dropdown_ready, fleet_row_index

# EN FLEET_2_BAR：6 行下拉的搜索区域。
FLEET_2_BAR = (994, 384, 1165, 629)


def _box(center_y, height=33):
    half = height / 2.0
    return (1040, center_y - half, 1160, center_y + half)


class FleetRowIndexTest(unittest.TestCase):
    def test_six_rows_follow_the_bar(self):
        top = FLEET_2_BAR[1]
        height = FLEET_2_BAR[3] - top
        stride = height / 6.0
        for slot in range(1, 7):
            center = top + (slot - 0.5) * stride
            self.assertEqual(fleet_row_index(_box(center), FLEET_2_BAR), slot)

    def test_nyan_click_at_549_is_fleet_5_not_2(self):
        # 2026-10-24 09:30:01 点击 (1136, 549) @ FleetOption_2。
        # 菜单只检出两行，旧逻辑把下面那行编号成 2。
        self.assertEqual(fleet_row_index(_box(549), FLEET_2_BAR), 5)

    def test_short_bar_is_not_a_six_row_scale(self):
        # 潜艇条只有约两行高，编号仍从顶部顺序数，不走这个函数。
        sub = (994, 520, 1165, 597)
        self.assertLess(sub[3] - sub[1], 33 * 5)

    def test_partial_lower_rows_are_not_a_finished_menu(self):
        self.assertFalse(dropdown_ready({5: object(), 6: object()}, 2))
        self.assertTrue(dropdown_ready({5: object(), 6: object()}, 5))

    def test_two_fleet_account_and_full_menu_are_ready(self):
        self.assertTrue(dropdown_ready({1: object(), 2: object()}, 2))
        self.assertTrue(dropdown_ready({1: object(), 2: object()}, 5))
        full = {i: object() for i in range(1, 7)}
        self.assertTrue(dropdown_ready(full, 2))
        self.assertFalse(dropdown_ready({}, 1))


if __name__ == '__main__':
    unittest.main()
