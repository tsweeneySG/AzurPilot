import unittest

from module.map.camera import Camera
from module.map.map_operation import MapOperation


class TestEnterMapCombatLoading(unittest.TestCase):
    def _op(
        self, auto_search, loading, executing, bar=False, saw_bar=False,
        load_bar_finished=False, server='jp', heartbeat=False,
    ):
        op = MapOperation.__new__(MapOperation)
        op.map_is_auto_search = auto_search
        op._enter_map_saw_load_bar = saw_bar
        op._enter_map_bar_this_frame = False
        op._enter_map_load_bar_finished = load_bar_finished
        op._enter_map_combat_started = False
        op.config = type('Cfg', (), {'SERVER': server})()
        op.is_combat_loading_bar = lambda: bar
        op.is_combat_loading = lambda: loading
        op.is_combat_executing = lambda: executing
        op._enter_map_heartbeat_battle_busy = lambda: heartbeat
        return op

    def test_manual_map_loading_bar_does_not_finish_enter(self):
        op = self._op(auto_search=False, loading=True, executing=False, bar=True)
        self.assertFalse(op._enter_map_combat_loading_means_entered())
        self.assertTrue(op._enter_map_saw_load_bar)
        self.assertTrue(op._enter_map_bar_this_frame)

    def test_auto_search_combat_loading_finishes_enter(self):
        op = self._op(auto_search=True, loading=True, executing=False, bar=True)
        self.assertTrue(op._enter_map_combat_loading_means_entered())

    def test_manual_real_combat_finishes_enter(self):
        op = self._op(auto_search=False, loading=True, executing=True, bar=False)
        self.assertTrue(op._enter_map_combat_loading_means_entered())

    def test_manual_after_load_bar_ignores_pause_false_positive(self):
        op = self._op(
            auto_search=False, loading=True, executing=True, bar=False, saw_bar=True,
        )

        def boom():
            raise AssertionError('should not call is_combat_loading after load bar')

        op.is_combat_loading = boom
        self.assertFalse(op._enter_map_combat_loading_means_entered())
        self.assertTrue(op._enter_map_saw_load_bar)
        self.assertFalse(op._enter_map_bar_this_frame)

    def test_not_loading_does_not_finish_enter(self):
        op = self._op(auto_search=False, loading=False, executing=False, bar=False)
        self.assertFalse(op._enter_map_combat_loading_means_entered())

    def test_manual_second_load_bar_finishes_enter(self):
        op = self._op(
            auto_search=False, loading=True, executing=False, bar=True,
            saw_bar=True, load_bar_finished=True,
        )
        self.assertTrue(op._enter_map_combat_loading_means_entered())
        self.assertTrue(op._enter_map_combat_started)

    def test_manual_heartbeat_after_load_bar_finishes_enter(self):
        op = self._op(
            auto_search=False, loading=False, executing=False, bar=False,
            saw_bar=True, heartbeat=True,
        )
        self.assertTrue(op._enter_map_combat_loading_means_entered())
        self.assertTrue(op._enter_map_combat_started)

    def test_manual_en_pause_after_load_bar_finishes_enter(self):
        op = self._op(
            auto_search=False, loading=True, executing=True, bar=False,
            saw_bar=True, server='en',
        )
        self.assertTrue(op._enter_map_combat_loading_means_entered())
        self.assertTrue(op._enter_map_combat_started)

    def test_map_init_finishes_combat_on_loading_bar(self):
        op = self._op(auto_search=False, loading=False, executing=False, bar=True)
        op.combat_appear = lambda: False
        self.assertTrue(op._map_init_should_finish_combat())

    def test_map_init_skips_jp_pause_on_map(self):
        op = self._op(auto_search=False, loading=True, executing=True, bar=False)
        op.combat_appear = lambda: False
        self.assertFalse(op._map_init_should_finish_combat())


class TestEnterMapClickCap(unittest.TestCase):
    def test_campaign_click_cap_is_script_end_not_rht(self):
        import inspect

        from module.map import map_operation

        src = inspect.getsource(map_operation.MapOperation.enter_map)
        campaign_block = src.split('if campaign_click > 5')[1].split('if fleet_click')[0]
        self.assertIn("ScriptEnd('Cannot enter map')", campaign_block)
        self.assertNotIn('raise RequestHumanTakeover', campaign_block)


class TestCampaignNameErrorDelay(unittest.TestCase):
    def test_ensure_ui_script_end_is_caught_and_delayed(self):
        import inspect

        from module.campaign import run

        src = inspect.getsource(run.CampaignRun.run)
        self.assertIn('_handle_campaign_script_end', src)
        self.assertIn('except CampaignEnd as e', src)
        helper = inspect.getsource(run.CampaignRun._handle_campaign_script_end)
        self.assertIn("Campaign name error", helper)
        self.assertIn('task_delay(minute=30)', helper)

    def test_map_init_campaign_end_is_success(self):
        import inspect

        from module.campaign import campaign_base

        src = inspect.getsource(campaign_base.CampaignBase.run)
        self.assertIn('except CampaignEnd', src)
        self.assertIn('return True', src)

    def test_hard_ensure_ui_script_end_is_caught(self):
        import inspect

        from module.hard import hard

        src = inspect.getsource(hard.CampaignHard.run)
        self.assertIn('_handle_campaign_script_end', src)
        self.assertIn('except ScriptEnd', src)
        self.assertIn('except CampaignEnd', src)

    def test_alas_treats_campaign_end_as_success(self):
        import inspect

        import alas as alas_mod

        src = inspect.getsource(alas_mod.AzurLaneAutoScript.run)
        self.assertIn('except CampaignEnd', src)
        self.assertIn('return True', src)


class TestCameraWaitForMap(unittest.TestCase):
    def test_wait_while_combat_loading(self):
        cam = Camera.__new__(Camera)
        cam.is_combat_loading = lambda: True
        self.assertTrue(cam._camera_should_wait_for_map())

    def test_do_not_wait_when_not_loading(self):
        cam = Camera.__new__(Camera)
        cam.is_combat_loading = lambda: False
        self.assertFalse(cam._camera_should_wait_for_map())
