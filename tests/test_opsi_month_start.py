import unittest
from datetime import datetime, timedelta, timezone

from module.config.deep import deep_get, deep_set
from module.config.utils import get_os_month_id, get_os_next_reset, os_server_now
from module.os.month_start import (
    LAST_OS_MONTH_KEY,
    OPSI_MONTH_START_DISABLE_TASKS,
    SPECIAL_RADAR_KEY,
    apply_opsi_month_start,
)


class FakeConfig:
    def __init__(self, data=None):
        self.data = data if data is not None else _fresh_data()
        self.modified = {}
        self.auto_update = False
        self.is_template_config = False

    def cross_get(self, keys, default=None):
        return deep_get(self.data, keys=keys, default=default)

    def cross_set(self, keys, value):
        self.modified[keys] = value
        deep_set(self.data, keys=keys, value=value)

    def multi_set(self):
        return _NullCtx()


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _fresh_data(package='com.YoStarEN.AzurLane', enable_heavy=True, rotation=True):
    data = {
        'Alas': {'Emulator': {'PackageName': package}},
        'OpsiGeneral': {
            'OpsiGeneral': {'MonthStartRotation': rotation},
            'Storage': {'Storage': {}},
        },
        'OpsiExplore': {'OpsiExplore': {'SpecialRadar': False}},
    }
    for task in OPSI_MONTH_START_DISABLE_TASKS:
        data[task] = {'Scheduler': {'Enable': enable_heavy}}
    return data


# Aug 31 2026 20:00 UTC: JP (UTC+9) is already Sep 1 05:00; EN (UTC-7) is still Aug 31 13:00.
AUG31_20Z = datetime(2026, 8, 31, 20, 0, 0, tzinfo=timezone.utc)
# Sep 1 2026 08:00 UTC: both JP (17:00) and EN (01:00) are in September.
SEP1_08Z = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
# Sep 10 2026 12:00 UTC: well into the month for both servers.
SEP10_12Z = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


class TestOpSiTimezone(unittest.TestCase):
    def test_jp_server_now_ahead_of_en(self):
        jp = os_server_now('jp', now=AUG31_20Z)
        en = os_server_now('en', now=AUG31_20Z)
        self.assertEqual(jp, datetime(2026, 9, 1, 5, 0, 0))
        self.assertEqual(en, datetime(2026, 8, 31, 13, 0, 0))

    def test_jp_month_ticks_before_global(self):
        self.assertEqual(get_os_month_id('jp', now=AUG31_20Z), '2026-09')
        self.assertEqual(get_os_month_id('en', now=AUG31_20Z), '2026-08')
        self.assertEqual(get_os_month_id('com.YoStarJP.AzurLane', now=AUG31_20Z), '2026-09')
        self.assertEqual(get_os_month_id('com.YoStarEN.AzurLane', now=AUG31_20Z), '2026-08')

    def test_both_in_september_after_global_midnight(self):
        self.assertEqual(get_os_month_id('jp', now=SEP1_08Z), '2026-09')
        self.assertEqual(get_os_month_id('en', now=SEP1_08Z), '2026-09')

    def test_next_reset_jp_sixteen_hours_before_en(self):
        jp = get_os_next_reset(server='jp', now=SEP1_08Z)
        en = get_os_next_reset(server='en', now=SEP1_08Z)
        self.assertEqual(en - jp, timedelta(hours=16))


class TestOpSiMonthStart(unittest.TestCase):
    def test_applies_on_month_change(self):
        cfg = FakeConfig(_fresh_data())
        cfg.cross_set(LAST_OS_MONTH_KEY, '2026-08')
        self.assertTrue(apply_opsi_month_start(cfg, now=SEP1_08Z))
        self.assertTrue(cfg.cross_get(SPECIAL_RADAR_KEY))
        for task in OPSI_MONTH_START_DISABLE_TASKS:
            self.assertFalse(cfg.cross_get(f'{task}.Scheduler.Enable'))
        self.assertEqual(cfg.cross_get(LAST_OS_MONTH_KEY), '2026-09')

    def test_idempotent_same_month(self):
        cfg = FakeConfig(_fresh_data())
        cfg.cross_set(LAST_OS_MONTH_KEY, '2026-08')
        self.assertTrue(apply_opsi_month_start(cfg, now=SEP1_08Z))
        cfg.modified.clear()
        cfg.cross_set('OpsiAbyssal.Scheduler.Enable', True)
        self.assertFalse(apply_opsi_month_start(cfg, now=SEP1_08Z))
        self.assertTrue(cfg.cross_get('OpsiAbyssal.Scheduler.Enable'))

    def test_first_run_mid_month_stamps_without_disabling(self):
        cfg = FakeConfig(_fresh_data(enable_heavy=True))
        self.assertTrue(apply_opsi_month_start(cfg, now=SEP10_12Z))
        self.assertEqual(cfg.cross_get(LAST_OS_MONTH_KEY), '2026-09')
        self.assertTrue(cfg.cross_get('OpsiAbyssal.Scheduler.Enable'))
        self.assertFalse(cfg.cross_get(SPECIAL_RADAR_KEY))

    def test_first_run_early_month_applies(self):
        cfg = FakeConfig(_fresh_data())
        self.assertTrue(apply_opsi_month_start(cfg, now=SEP1_08Z))
        self.assertTrue(cfg.cross_get(SPECIAL_RADAR_KEY))
        self.assertFalse(cfg.cross_get('OpsiObscure.Scheduler.Enable'))

    def test_rotation_disabled_is_noop(self):
        cfg = FakeConfig(_fresh_data(rotation=False))
        cfg.cross_set(LAST_OS_MONTH_KEY, '2026-08')
        self.assertFalse(apply_opsi_month_start(cfg, now=SEP1_08Z))
        self.assertTrue(cfg.cross_get('OpsiStronghold.Scheduler.Enable'))
        self.assertFalse(cfg.cross_get(SPECIAL_RADAR_KEY))

    def test_jp_account_rotates_while_global_still_august(self):
        jp = FakeConfig(_fresh_data(package='com.YoStarJP.AzurLane'))
        jp.cross_set(LAST_OS_MONTH_KEY, '2026-08')
        en = FakeConfig(_fresh_data(package='com.YoStarEN.AzurLane'))
        en.cross_set(LAST_OS_MONTH_KEY, '2026-08')
        self.assertTrue(apply_opsi_month_start(jp, now=AUG31_20Z))
        self.assertFalse(apply_opsi_month_start(en, now=AUG31_20Z))
        self.assertFalse(jp.cross_get('OpsiMeowfficerFarming.Scheduler.Enable'))
        self.assertTrue(en.cross_get('OpsiMeowfficerFarming.Scheduler.Enable'))
        self.assertEqual(jp.cross_get(LAST_OS_MONTH_KEY), '2026-09')
        self.assertEqual(en.cross_get(LAST_OS_MONTH_KEY), '2026-08')

    def test_template_skipped(self):
        cfg = FakeConfig(_fresh_data())
        cfg.is_template_config = True
        self.assertFalse(apply_opsi_month_start(cfg, now=SEP1_08Z))


if __name__ == '__main__':
    unittest.main()
