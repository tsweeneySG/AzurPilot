import inspect
import unittest

from module.combat.assets import GET_SHIP
from module.combat.combat import Combat
from module.handler.enemy_searching import EnemySearchingHandler


class TestHandleExpInfo(unittest.TestCase):
    def test_skips_exp_when_get_ship_visible(self):
        combat = Combat.__new__(Combat)
        combat.is_combat_executing = lambda: False
        combat.appear = lambda btn, **kw: btn is GET_SHIP

        def boom(*args, **kwargs):
            raise AssertionError('should not click EXP while GET_SHIP is visible')

        combat.appear_then_click = boom
        self.assertFalse(combat.handle_exp_info())

    def test_exp_info_uses_interval(self):
        src = inspect.getsource(Combat.handle_exp_info)
        self.assertIn('interval=2', src)
        self.assertIn('_get_ship_blocks_settlement', src)
        src = inspect.getsource(Combat.handle_get_ship)
        self.assertIn('interval=2', src)
        src = inspect.getsource(Combat.handle_battle_status)
        self.assertIn('_get_ship_blocks_settlement', src)

    def test_get_ship_holds_overlay_without_click(self):
        combat = Combat.__new__(Combat)
        combat.appear = lambda btn, **kw: btn is GET_SHIP
        combat.handle_popup_confirm = lambda *args, **kwargs: False
        combat.appear_then_click = lambda *args, **kwargs: False
        self.assertTrue(combat.handle_get_ship())

    def test_exp_clicks_when_get_ship_not_visible(self):
        combat = Combat.__new__(Combat)
        combat.is_combat_executing = lambda: False
        combat.appear = lambda btn, **kw: False
        combat.appear_then_click = lambda *args, **kwargs: True
        combat.device = type('D', (), {'sleep': lambda *a, **k: None})()
        self.assertTrue(combat.handle_exp_info())

    def test_no_wall_clock_get_ship_hold(self):
        src = inspect.getsource(Combat)
        self.assertNotIn('Timer(90, count=0)', src)
        self.assertNotIn('_hold_exp_for_get_ship', src)
        self.assertNotIn('_get_ship_exp_hold', src)

    def test_skips_battle_status_when_get_ship_visible(self):
        combat = Combat.__new__(Combat)
        combat.is_combat_executing = lambda: False
        combat.appear = lambda btn, **kw: btn is GET_SHIP
        combat._bridge_battle_is_report = lambda: True

        def boom(*args, **kwargs):
            raise AssertionError('should not click BATTLE_STATUS while GET_SHIP is visible')

        combat._click_bridge_battle_report = boom
        self.assertFalse(combat.handle_battle_status())

    def test_combat_status_handles_overlay_before_in_map(self):
        src = inspect.getsource(Combat.combat_status)
        get_ship = src.find('handle_get_ship')
        searching = src.find("expected_end == 'with_searching'")
        self.assertGreater(get_ship, 0)
        self.assertGreater(searching, get_ship)
        self.assertIn('overlayed', src)

    def test_combat_status_latches_exp_and_get_ship(self):
        src = inspect.getsource(Combat.combat_status)
        self.assertIn('not exp_info or self.appear(GET_SHIP)', src)
        self.assertGreaterEqual(src.count('if not exp_info and self.handle_exp_info()'), 2)
        self.assertIn('_bridge_try_result_advance', src)

    def test_enemy_searching_aborts_on_settlement_overlay(self):
        src = inspect.getsource(EnemySearchingHandler.handle_in_map_with_enemy_searching)
        self.assertIn('_settlement_overlay_during_map_search', src)
        self.assertIn('return False', src)

        handler = EnemySearchingHandler.__new__(EnemySearchingHandler)
        handler.appear = lambda btn, **kw: btn is GET_SHIP
        handler.retirement_appear = lambda: False
        self.assertTrue(handler._settlement_overlay_during_map_search())
        handler.appear = lambda btn, **kw: False
        self.assertFalse(handler._settlement_overlay_during_map_search())
