"""演习刷新未到账时短延迟重试，而不是半周期放弃。"""
import unittest
from datetime import datetime

from module.exercise.exercise import should_retry_missing_exercise_recover


class TestExerciseMissingRecoverRetry(unittest.TestCase):
    def test_retries_within_grace_after_refresh(self):
        last = datetime(2026, 9, 27, 15, 0, 0)
        now = datetime(2026, 9, 27, 15, 0, 1)
        self.assertTrue(should_retry_missing_exercise_recover(0, 5, now, last))
        self.assertTrue(should_retry_missing_exercise_recover(5, 5, now, last))

    def test_does_not_retry_after_grace(self):
        last = datetime(2026, 9, 27, 15, 0, 0)
        now = datetime(2026, 9, 27, 15, 31, 0)
        self.assertFalse(should_retry_missing_exercise_recover(0, 5, now, last))

    def test_overdue_reset_retries_past_scheduler_grace(self):
        last = datetime(2026, 9, 28, 3, 0, 0)
        now = datetime(2026, 9, 28, 3, 36, 0)
        reset_at = datetime(2026, 9, 28, 3, 0, 0)
        self.assertTrue(
            should_retry_missing_exercise_recover(
                5, 5, now, last, reset_at=reset_at)
        )

    def test_future_reset_does_not_retry(self):
        last = datetime(2026, 9, 28, 3, 0, 0)
        now = datetime(2026, 9, 28, 3, 36, 0)
        reset_at = datetime(2026, 9, 28, 15, 0, 0)
        self.assertFalse(
            should_retry_missing_exercise_recover(
                5, 5, now, last, reset_at=reset_at)
        )

    def test_does_not_retry_when_remain_above_preserve(self):
        last = datetime(2026, 9, 27, 15, 0, 0)
        now = datetime(2026, 9, 27, 15, 0, 1)
        self.assertFalse(should_retry_missing_exercise_recover(10, 5, now, last))

    def test_does_not_retry_before_last_update(self):
        last = datetime(2026, 9, 27, 15, 0, 0)
        now = datetime(2026, 9, 27, 14, 59, 0)
        self.assertFalse(should_retry_missing_exercise_recover(0, 5, now, last))


if __name__ == '__main__':
    unittest.main()
