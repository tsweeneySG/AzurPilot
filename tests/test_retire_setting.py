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


class TestSettingBaseStillClicksAll(unittest.TestCase):
    def test_generic_setting_still_loops_clicks(self):
        src = inspect.getsource(Setting._set_execute)
        self.assertIn('for button in clicks:', src)
