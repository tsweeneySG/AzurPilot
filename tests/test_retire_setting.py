import inspect
import unittest
from unittest.mock import Mock

from module.base.button import Button
from module.retire.setting import QuickRetireSetting, QuickRetireSettingHandler, _radio_at_row
from module.ui.setting import Setting


def _radio(name, x):
    return Button(
        area=(x, 317, x + 28, 346),
        color=(64, 71, 91),
        button=(x, 317, x + 28, 346),
        name=name,
    )


class TestQuickRetireSettingClicks(unittest.TestCase):
    def test_set_execute_clicks_one_button_per_retry(self):
        src = inspect.getsource(QuickRetireSetting._set_execute)
        self.assertIn('clicks[0]', src)
        self.assertNotIn('for button in clicks:', src)

    def test_handler_registers_e_r_n_on_each_rarity_row(self):
        src = inspect.getsource(QuickRetireSettingHandler)
        self.assertIn("option_names=['E', 'R', 'N']", src)
        self.assertIn("add_rarity_row('filter_2'", src)

    def test_clicks_elite_when_row_is_rare(self):
        setting = QuickRetireSetting(name='RETIRE', main=Mock())
        elite = _radio('filter_2_E', 746)
        rare = _radio('filter_2_R', 818)
        normal = _radio('filter_2_N', 894)
        setting.add_setting(
            'filter_2', [elite, rare, normal], ['E', 'R', 'N'], 'E')
        counts = {elite: 10, rare: 220, normal: 12}
        setting._option_white_count = lambda button: counts[button]

        clicks = setting.get_buttons_to_click(setting._product_setting_status())

        self.assertEqual(clicks, [elite])
        self.assertFalse(setting.is_option_active(elite))
        self.assertTrue(setting.is_option_active(rare))

    def test_radio_at_row_keeps_template_y(self):
        template = Button(
            area=(818, 260, 846, 289),
            color=(64, 72, 92),
            button=(818, 260, 846, 289),
            name='row1',
        )
        elite = _radio_at_row(template, 746, 'row1_E')
        self.assertEqual(elite.area[1], 260)
        self.assertEqual(elite.area[0], 746)


class TestEnRetireSettingAssets(unittest.TestCase):
    def test_en_boxes_match_png_and_are_not_the_none_column(self):
        from module.base.utils import get_bbox, load_image
        from module.retire.assets import (
            RETIRE_SETTING_1,
            RETIRE_SETTING_2,
            RETIRE_SETTING_3,
            RETIRE_SETTING_QUIT,
        )

        for button in (
                RETIRE_SETTING_1, RETIRE_SETTING_2, RETIRE_SETTING_3, RETIRE_SETTING_QUIT):
            path = button.raw_file['en']
            if path.startswith('./'):
                path = path[2:]
            bbox = tuple(get_bbox(load_image(path)))
            self.assertEqual(tuple(button.raw_area['en']), bbox)
            self.assertEqual(tuple(button.raw_button['en']), bbox)

        xs = (
            RETIRE_SETTING_2.raw_area['en'][0],
            RETIRE_SETTING_1.raw_area['en'][0],
            RETIRE_SETTING_3.raw_area['en'][0],
        )
        self.assertGreaterEqual(max(xs) - min(xs), 40)
        self.assertLess(max(xs), 950)
        quit_box = RETIRE_SETTING_QUIT.raw_button['en']
        self.assertLess(quit_box[1], 100)
        self.assertGreater(quit_box[3], 109)


class TestQuickRetireBridgeSkipsRadios(unittest.TestCase):
    def _handler(self, bridge_ok, ships=0, keep_mode='keep_limit_break'):
        from unittest.mock import Mock

        from module.retire.retirement import Retirement

        obj = Retirement.__new__(Retirement)
        obj.config = Mock()
        obj.config.Retirement_RetireMode = 'one_click_retire'
        obj.config.OneClickRetire_KeepLimitBreak = keep_mode
        obj.server_support_quick_retire_setting_fallback = lambda: True
        obj._apply_quick_retire_via_bridge = lambda keep: bridge_ok and keep
        obj.one_clicks = 0

        def one_click():
            obj.one_clicks += 1
            return ships

        obj.retire_ships_one_click = one_click
        obj.dock_favourite_set = lambda *a, **k: None
        obj.dock_filter_set = lambda *a, **k: None
        obj.ui_calls = []
        obj.quick_retire_setting_set = lambda *a, **k: obj.ui_calls.append((a, k))
        obj.retire_gems_farming_flagships = lambda **k: 0
        obj._retirement_quit = lambda: None
        obj._retire_leave_no_ships = lambda: 0
        obj._retire_exhausted = False
        return obj

    def test_bridge_zero_ships_does_not_open_the_panel(self):
        obj = self._handler(bridge_ok=True, ships=0)
        self.assertEqual(obj._retire_handler(), 0)
        self.assertEqual(obj.ui_calls, [])

    def test_bridge_write_does_not_open_the_radio_panel(self):
        obj = self._handler(bridge_ok=True, ships=10)
        self.assertEqual(obj._retire_handler(), 10)
        self.assertEqual(obj.ui_calls, [])
        self.assertEqual(obj.one_clicks, 1)

    def test_bridge_miss_still_opens_the_panel(self):
        obj = self._handler(bridge_ok=False, ships=0)
        self.assertEqual(obj._retire_handler(), 0)
        self.assertGreaterEqual(len(obj.ui_calls), 1)

    def test_do_not_keep_asks_the_bridge_for_all(self):
        seen = []
        obj = self._handler(bridge_ok=True, ships=10, keep_mode='do_not_keep')
        obj._apply_quick_retire_via_bridge = lambda keep: seen.append(keep) or True
        obj._retire_handler()
        self.assertEqual(seen, ['all'])


class TestSettingBaseStillClicksAll(unittest.TestCase):
    def test_generic_setting_still_loops_clicks(self):
        src = inspect.getsource(Setting._set_execute)
        self.assertIn('for button in clicks:', src)
