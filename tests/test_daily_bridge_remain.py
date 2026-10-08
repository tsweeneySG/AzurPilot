"""每日桥接剩余次数：按 template id 匹配，避免取任意正数行。"""
import unittest

from module.daily.remain import bridge_daily_remain_for_id, daily_template_id


class TestDailyBridgeRemain(unittest.TestCase):
    def test_template_id_normal_order(self):
        self.assertEqual(daily_template_id(1, False), 601)
        self.assertEqual(daily_template_id(2, False), 501)
        self.assertEqual(daily_template_id(5, False), 201)
        self.assertEqual(daily_template_id(6, False), 301)
        self.assertEqual(daily_template_id(7, False), 401)

    def test_template_id_emergency_order(self):
        self.assertEqual(daily_template_id(1, True), 801)
        self.assertEqual(daily_template_id(2, True), 201)
        self.assertEqual(daily_template_id(6, True), 501)
        self.assertEqual(daily_template_id(7, True), 701)

    def test_match_current_slot_not_first_positive(self):
        # Asami 11:21: OCR 0 on Escort (201) while Advance (301) still had remain 3.
        rows = [
            {'id': 601, 'remain': 0, 'used': 1, 'limit': 1},
            {'id': 501, 'remain': 0, 'used': 2, 'limit': 2},
            {'id': 701, 'remain': 0, 'used': 2, 'limit': 2},
            {'id': 201, 'remain': 0, 'used': 2, 'limit': 2},
            {'id': 301, 'remain': 3, 'used': 0, 'limit': 3},
            {'id': 401, 'remain': 0, 'used': 3, 'limit': 3},
        ]
        escort_id = daily_template_id(5, False)
        self.assertEqual(escort_id, 201)
        self.assertEqual(bridge_daily_remain_for_id(rows, escort_id), 0)
        advance_id = daily_template_id(6, False)
        self.assertEqual(bridge_daily_remain_for_id(rows, advance_id), 3)

    def test_missing_row_returns_none(self):
        self.assertIsNone(bridge_daily_remain_for_id([{'id': 301, 'remain': 3}], 201))
        self.assertIsNone(bridge_daily_remain_for_id(None, 201))
        self.assertIsNone(bridge_daily_remain_for_id([], None))


if __name__ == '__main__':
    unittest.main()
