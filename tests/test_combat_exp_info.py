import unittest

from module.combat.assets import GET_SHIP
from module.combat.combat import Combat


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
        import inspect

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

    def test_skips_exp_while_get_ship_hold_active(self):
        from module.base.timer import Timer

        combat = Combat.__new__(Combat)
        combat.is_combat_executing = lambda: False
        combat.appear = lambda btn, **kw: False
        combat._get_ship_exp_hold = Timer(20, count=30).reset()

        def boom(*args, **kwargs):
            raise AssertionError('should not click EXP during GET_SHIP hold')

        combat.appear_then_click = boom
        self.assertFalse(combat.handle_exp_info())

    def test_skips_battle_status_when_get_ship_visible(self):
        combat = Combat.__new__(Combat)
        combat.is_combat_executing = lambda: False
        combat.appear = lambda btn, **kw: btn is GET_SHIP
        combat._bridge_battle_is_report = lambda: True

        def boom(*args, **kwargs):
            raise AssertionError('should not click BATTLE_STATUS while GET_SHIP is visible')

        combat._click_bridge_battle_report = boom
        self.assertFalse(combat.handle_battle_status())

    def test_skips_battle_status_while_get_ship_hold_active(self):
        from module.base.timer import Timer

        combat = Combat.__new__(Combat)
        combat.is_combat_executing = lambda: False
        combat.appear = lambda btn, **kw: False
        combat._get_ship_exp_hold = Timer(20, count=30).reset()
        combat._bridge_battle_is_report = lambda: True

        def boom(*args, **kwargs):
            raise AssertionError('should not click BATTLE_STATUS during GET_SHIP hold')

        combat._click_bridge_battle_report = boom
        self.assertFalse(combat.handle_battle_status())

    def test_combat_status_handles_overlay_before_in_map(self):
        import inspect

        src = inspect.getsource(Combat.combat_status)
        get_ship = src.find('handle_get_ship')
        searching = src.find("expected_end == 'with_searching'")
        self.assertGreater(get_ship, 0)
        self.assertGreater(searching, get_ship)
        self.assertIn('overlayed', src)

    def test_hold_starts_when_get_ship_visible(self):
        combat = Combat.__new__(Combat)
        combat.is_combat_executing = lambda: False
        combat.appear = lambda btn, **kw: btn is GET_SHIP
        combat.appear_then_click = lambda *args, **kwargs: False
        self.assertFalse(combat.handle_exp_info())
        self.assertIsNotNone(getattr(combat, '_get_ship_exp_hold', None))
        self.assertTrue(combat._get_ship_exp_hold.started())
