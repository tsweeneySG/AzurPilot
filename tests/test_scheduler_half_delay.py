"""定额任务半延迟补跑：前半段只等剩余时间的一半，后半段等到下次刷新。"""
import unittest
from datetime import datetime

from module.config.utils import resolve_half_server_update


class TestResolveHalfServerUpdate(unittest.TestCase):
    def test_first_half_of_daily_period_uses_half_remaining(self):
        last_update = datetime(2026, 9, 7, 0, 0, 0)
        next_update = datetime(2026, 9, 8, 0, 0, 0)
        now = datetime(2026, 9, 7, 8, 0, 0)

        result = resolve_half_server_update(now, last_update, next_update)

        self.assertEqual(result, datetime(2026, 9, 7, 16, 0, 0))

    def test_second_half_of_daily_period_waits_for_server_update(self):
        last_update = datetime(2026, 9, 7, 0, 0, 0)
        next_update = datetime(2026, 9, 8, 0, 0, 0)
        now = datetime(2026, 9, 7, 16, 0, 0)

        result = resolve_half_server_update(now, last_update, next_update)

        self.assertEqual(result, next_update)

    def test_exercise_window_retries_once_then_waits(self):
        last_update = datetime(2026, 9, 7, 0, 0, 0)
        next_update = datetime(2026, 9, 7, 12, 0, 0)

        first = resolve_half_server_update(
            datetime(2026, 9, 7, 0, 30, 0), last_update, next_update
        )
        second = resolve_half_server_update(first, last_update, next_update)

        self.assertEqual(first, datetime(2026, 9, 7, 6, 15, 0))
        self.assertEqual(second, next_update)

    def test_short_remaining_waits_for_server_update(self):
        last_update = datetime(2026, 9, 7, 0, 0, 0)
        next_update = datetime(2026, 9, 7, 12, 0, 0)
        now = datetime(2026, 9, 7, 11, 20, 0)

        result = resolve_half_server_update(now, last_update, next_update)

        self.assertEqual(result, next_update)


if __name__ == '__main__':
    unittest.main()
