import unittest
from datetime import datetime

from module.config.deep import deep_get, deep_set
from module.os.ap_preserve import (
    ABYSSAL_COORD_KEY,
    OBSCURE_COORD_KEY,
    STRONGHOLD_KEY,
    mark_coordinate_from_item_name,
    month_end_stepped_preserve,
    should_hold_ap_for_loggers,
)

NEXT_RESET = datetime(2026, 10, 1, 3, 0, 0)
STILL_THIS_MONTH = datetime(2026, 9, 30, 10, 0, 0)
AFTER_RESET = datetime(2026, 10, 1, 3, 0, 0)


class FakeConfig:
    def __init__(self, data=None):
        self.data = data if data is not None else {}
        self.modified = {}

    def cross_get(self, keys, default=None):
        return deep_get(self.data, keys=keys, default=default)

    def cross_set(self, keys, value):
        self.modified[keys] = value
        deep_set(self.data, keys=keys, value=value)


def _config(obscure=None, abyssal=None, stronghold=None,
            obscure_enable=True, abyssal_enable=True, stronghold_enable=True,
            obscure_next=STILL_THIS_MONTH, abyssal_next=STILL_THIS_MONTH,
            stronghold_next=STILL_THIS_MONTH):
    data = {
        'OpsiObscure': {
            'Scheduler': {'Enable': obscure_enable, 'NextRun': obscure_next},
            'Storage': {'Storage': {}},
        },
        'OpsiAbyssal': {
            'Scheduler': {'Enable': abyssal_enable, 'NextRun': abyssal_next},
            'Storage': {'Storage': {}},
        },
        'OpsiStronghold': {
            'Scheduler': {'Enable': stronghold_enable, 'NextRun': stronghold_next},
            'Storage': {'Storage': {}},
        },
    }
    if obscure is not None:
        deep_set(data, OBSCURE_COORD_KEY, obscure)
    if abyssal is not None:
        deep_set(data, ABYSSAL_COORD_KEY, abyssal)
    if stronghold is not None:
        deep_set(data, STRONGHOLD_KEY, stronghold)
    return FakeConfig(data)


class TestMonthEndSteppedPreserve(unittest.TestCase):
    def test_not_near_reset(self):
        self.assertEqual(month_end_stepped_preserve(10), 2000)

    def test_three_days_normal(self):
        self.assertEqual(month_end_stepped_preserve(2), 300)
        self.assertEqual(month_end_stepped_preserve(1), 300)

    def test_three_days_cl1(self):
        self.assertEqual(month_end_stepped_preserve(2, is_cl1=True), 1000)

    def test_last_day(self):
        self.assertEqual(month_end_stepped_preserve(0), 0)
        self.assertEqual(month_end_stepped_preserve(0, cross_month=True), 300)


class TestHoldApForLoggers(unittest.TestCase):
    def test_empty_known_does_not_hold(self):
        cfg = _config(obscure=False, abyssal=False, stronghold=False)
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertFalse(hold)
        self.assertEqual(reason, '')

    def test_obscure_logger_holds(self):
        cfg = _config(obscure=True, abyssal=False, stronghold=False)
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertTrue(hold)
        self.assertIn('Obscure', reason)

    def test_abyssal_logger_holds(self):
        cfg = _config(obscure=False, abyssal=True, stronghold=False)
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertTrue(hold)
        self.assertIn('Abyssal', reason)

    def test_stronghold_holds(self):
        cfg = _config(obscure=False, abyssal=False, stronghold=True)
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertTrue(hold)
        self.assertIn('Stronghold', reason)

    def test_unknown_flag_holds_if_task_enabled(self):
        cfg = _config()
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertTrue(hold)

    def test_disabled_task_does_not_hold(self):
        cfg = _config(obscure=True, obscure_enable=False, abyssal=False, stronghold=False,
                      abyssal_enable=False, stronghold_enable=False)
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertFalse(hold)

    def test_next_run_after_reset_does_not_hold(self):
        cfg = _config(obscure=True, abyssal=False, stronghold=False,
                      obscure_next=AFTER_RESET, abyssal_enable=False, stronghold_enable=False)
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertFalse(hold)

    def test_shop_purchase_marks_coordinate(self):
        cfg = _config(obscure=False, abyssal=False, stronghold=False)
        mark_coordinate_from_item_name(cfg, 'LoggerAbyssalT6')
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertTrue(hold)
        self.assertIn('Abyssal', reason)
        mark_coordinate_from_item_name(cfg, 'LoggerObscureT5')
        hold, reason = should_hold_ap_for_loggers(cfg, next_reset=NEXT_RESET)
        self.assertIn('Obscure', reason)


if __name__ == '__main__':
    unittest.main()
