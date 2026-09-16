import unittest


class TestCampaignEventModeSwitch(unittest.TestCase):
    """2024.07+ event maps share A/C (B/D) nodes; difficulty is inside LevelInfoSPView."""

    def test_mode_name_twins(self):
        from module.campaign.campaign_ui import CampaignUI

        ui = CampaignUI.__new__(CampaignUI)
        self.assertEqual(ui.campaign_get_mode_names('a1'), ['a1', 'c1'])
        self.assertEqual(ui.campaign_get_mode_names('c1'), ['a1', 'c1'])
        self.assertEqual(ui.campaign_get_mode_names('b2'), ['b2', 'd2'])
        self.assertEqual(ui.campaign_get_mode_names('d2'), ['b2', 'd2'])
        self.assertEqual(ui.campaign_get_mode_names('t3'), ['t3', 'ht3'])
        self.assertEqual(ui.campaign_get_mode_names('ht3'), ['t3', 'ht3'])

    def test_entrance_uses_visible_twin_when_mode_switch(self):
        from module.campaign.campaign_ui import CampaignUI

        ui = CampaignUI.__new__(CampaignUI)
        ui.config = type('Cfg', (), {'MAP_HAS_MODE_SWITCH': True})()
        a1 = type('Btn', (), {'name': 'a1'})()
        ui.stage_entrance = {'a1': a1, 'a2': type('Btn', (), {'name': 'a2'})()}
        entrance = ui.campaign_get_entrance('c1')
        self.assertIs(entrance, a1)
        self.assertEqual(entrance.name, 'c1')

    def test_entrance_refuses_missing_stage_without_twin(self):
        from module.campaign.campaign_ui import CampaignUI
        from module.exception import CampaignNameError

        ui = CampaignUI.__new__(CampaignUI)
        ui.config = type('Cfg', (), {'MAP_HAS_MODE_SWITCH': True})()
        ui.stage_entrance = {'sp1': type('Btn', (), {'name': 'sp1'})()}
        with self.assertRaises(CampaignNameError):
            ui.campaign_get_entrance('c1')

    def test_ensure_mode_skips_when_switches_missing(self):
        from module.campaign import campaign_ui as campaign_ui_mod
        from module.campaign.campaign_ui import CampaignUI

        class DummySwitch:
            def get(self, main):
                return 'unknown'

            def set(self, state, main):
                raise AssertionError(f'should not click {state}')

            def wait(self, main, skip_first_screenshot=True):
                return False

        ui = CampaignUI.__new__(CampaignUI)
        orig_1 = campaign_ui_mod.MODE_SWITCH_1
        orig_2 = campaign_ui_mod.MODE_SWITCH_2
        campaign_ui_mod.MODE_SWITCH_1 = DummySwitch()
        campaign_ui_mod.MODE_SWITCH_2 = DummySwitch()
        try:
            ui.campaign_ensure_mode('normal')
        finally:
            campaign_ui_mod.MODE_SWITCH_1 = orig_1
            campaign_ui_mod.MODE_SWITCH_2 = orig_2

    def test_mainline_stages_not_ready_on_event_chrome(self):
        from module.campaign.campaign_ui import CampaignUI
        from module.ui.assets import EVENT_CHECK

        ui = CampaignUI.__new__(CampaignUI)

        def appear(button, **kwargs):
            return button is EVENT_CHECK

        ui.appear = appear
        self.assertFalse(ui._campaign_mainline_stages_ready())

    def test_set_chapter_main_raises_before_mode_switch(self):
        from module.campaign.campaign_ui import CampaignUI
        from module.exception import CampaignNameError

        ui = CampaignUI.__new__(CampaignUI)
        ui.ui_goto_campaign = lambda: None
        ui._campaign_mainline_stages_ready = lambda: False
        called = []
        ui.campaign_ensure_mode = lambda mode: called.append(mode)
        with self.assertRaises(CampaignNameError):
            ui.campaign_set_chapter_main('16', 'normal')
        self.assertEqual(called, [])


if __name__ == '__main__':
    unittest.main()
