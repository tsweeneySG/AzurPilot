import unittest

from module.ui.page import page_campaign, page_campaign_menu, page_main, page_main_white, page_raid
from module.ui.ui import UI


class TestUiGotoStaleFrame(unittest.TestCase):
    def _ui(self):
        return UI.__new__(UI)

    def test_needs_fresh_frame_when_navigating(self):
        ui = self._ui()
        ui.ui_current = page_campaign_menu
        self.assertTrue(ui._ui_goto_needs_fresh_frame(page_raid))

    def test_reuse_frame_when_already_on_destination(self):
        ui = self._ui()
        ui.ui_current = page_raid
        self.assertFalse(ui._ui_goto_needs_fresh_frame(page_raid))

    def test_main_theme_equivalence(self):
        ui = self._ui()
        ui.ui_current = page_main
        self.assertFalse(ui._ui_goto_needs_fresh_frame(page_main_white))

    def test_blocked_when_source_chrome_still_visible(self):
        ui = self._ui()
        ui.ui_current = page_campaign_menu
        ui.appear = lambda *args, **kwargs: True
        self.assertTrue(ui._ui_goto_blocked_by_source(page_raid))

    def test_not_blocked_when_source_chrome_gone(self):
        ui = self._ui()
        ui.ui_current = page_campaign_menu
        ui.appear = lambda *args, **kwargs: False
        self.assertFalse(ui._ui_goto_blocked_by_source(page_raid))

    def test_not_blocked_when_already_on_destination(self):
        ui = self._ui()
        ui.ui_current = page_raid
        ui.appear = lambda *args, **kwargs: True
        self.assertFalse(ui._ui_goto_blocked_by_source(page_raid))

    def test_blocked_by_bridge_when_still_on_campaign_menu(self):
        ui = self._ui()
        self.assertTrue(ui._ui_goto_blocked_by_bridge(page_campaign, page_campaign_menu))

    def test_not_blocked_by_bridge_when_bridge_agrees(self):
        ui = self._ui()
        self.assertFalse(ui._ui_goto_blocked_by_bridge(page_campaign, page_campaign))

    def test_not_blocked_by_bridge_when_missing(self):
        ui = self._ui()
        self.assertFalse(ui._ui_goto_blocked_by_bridge(page_campaign, None))

    def test_main_theme_not_blocked_by_bridge(self):
        ui = self._ui()
        self.assertFalse(ui._ui_goto_blocked_by_bridge(page_main, page_main_white))

    def test_bridge_block_is_wait_not_source_block(self):
        """源页 chrome 已消失、仅心跳滞后时应走 bridge 分支（ui_goto 会 continue 等待）。"""
        ui = self._ui()
        ui.ui_current = page_campaign_menu
        ui.appear = lambda *args, **kwargs: False
        self.assertFalse(ui._ui_goto_blocked_by_source(page_campaign))
        self.assertTrue(ui._ui_goto_blocked_by_bridge(page_campaign, page_campaign_menu))

    def test_campaign_menu_does_not_wait_on_stale_bridge(self):
        """CAMPAIGN_CHECK 会在出击菜单误匹配，空等会点不到章节列表。"""
        ui = self._ui()
        self.assertFalse(ui._ui_goto_wait_on_stale_bridge(page_campaign, page_campaign_menu))

    def test_archives_still_waits_on_stale_bridge(self):
        from module.ui.page import page_archives

        ui = self._ui()
        self.assertTrue(ui._ui_goto_wait_on_stale_bridge(page_archives, page_campaign_menu))

    def test_dest_chrome_blocks_campaign_when_event_visible(self):
        from module.ui.assets import EVENT_CHECK
        from module.ui.page import page_event

        ui = self._ui()

        def appear(button, **kwargs):
            return button is EVENT_CHECK

        ui.appear = appear
        self.assertTrue(ui._ui_goto_blocked_by_dest_chrome(page_campaign))
        self.assertFalse(ui._ui_goto_blocked_by_dest_chrome(page_event))

    def test_dest_chrome_blocks_campaign_when_menu_visible(self):
        from module.ui.assets import CAMPAIGN_MENU_CHECK

        ui = self._ui()

        def appear(button, **kwargs):
            return button is CAMPAIGN_MENU_CHECK

        ui.appear = appear
        self.assertTrue(ui._ui_goto_blocked_by_dest_chrome(page_campaign))

    def test_reject_stale_bridge_campaign_event(self):
        from module.ui.assets import EVENT_CHECK
        from module.ui.page import page_event

        ui = self._ui()

        def appear(button, **kwargs):
            return button is EVENT_CHECK

        ui.appear = appear
        self.assertEqual(ui._reject_stale_bridge_campaign(page_campaign), page_event)

    def test_reject_stale_bridge_campaign_menu(self):
        from module.ui.assets import CAMPAIGN_MENU_CHECK

        ui = self._ui()

        def appear(button, **kwargs):
            return button is CAMPAIGN_MENU_CHECK

        ui.appear = appear
        self.assertEqual(ui._reject_stale_bridge_campaign(page_campaign), page_campaign_menu)

    def test_reject_stale_bridge_campaign_when_clean(self):
        ui = self._ui()
        ui.appear = lambda *args, **kwargs: False
        self.assertEqual(ui._reject_stale_bridge_campaign(page_campaign), page_campaign)

    def test_home_chrome_visible_on_campaign_button(self):
        from module.ui.assets import MAIN_GOTO_CAMPAIGN

        ui = self._ui()

        def appear(button, **kwargs):
            return button is MAIN_GOTO_CAMPAIGN

        ui.appear = appear
        self.assertTrue(ui._ui_home_chrome_visible())
        self.assertEqual(ui._ui_page_from_home_chrome(), page_main)

    def test_home_chrome_white_theme(self):
        from module.ui_white.assets import MAIN_GOTO_CAMPAIGN_WHITE

        ui = self._ui()

        def appear(button, **kwargs):
            return button is MAIN_GOTO_CAMPAIGN_WHITE

        ui.appear = appear
        self.assertTrue(ui._ui_home_chrome_visible())
        self.assertEqual(ui._ui_page_from_home_chrome(), page_main_white)

    def test_settings_page_backs_to_main(self):
        from module.ui.assets import BACK_ARROW
        from module.ui.page import Page, page_settings

        self.assertIsNone(page_settings.check_button)
        self.assertIs(page_settings.links.get(page_main), BACK_ARROW)
        Page.init_connection(page_campaign_menu)
        self.assertIs(page_settings.parent, page_main)

    def test_skip_home_click_when_already_on_main(self):
        from module.ui.assets import BACK_ARROW, GOTO_MAIN, MAIN_GOTO_CAMPAIGN

        ui = self._ui()

        def appear(button, **kwargs):
            return button is MAIN_GOTO_CAMPAIGN

        ui.appear = appear
        self.assertTrue(ui._ui_skip_home_click(GOTO_MAIN))
        self.assertFalse(ui._ui_skip_home_click(BACK_ARROW))

    def test_skip_home_click_when_not_on_main(self):
        from module.ui.assets import GOTO_MAIN

        ui = self._ui()
        ui.appear = lambda *args, **kwargs: False
        self.assertFalse(ui._ui_skip_home_click(GOTO_MAIN))

    def test_unknown_prefer_back_clicks_back(self):
        from module.ui.assets import BACK_ARROW

        ui = self._ui()
        ui.appear_then_click = lambda button, **kwargs: button is BACK_ARROW
        ui.appear = lambda button, **kwargs: button is BACK_ARROW
        self.assertTrue(ui._ui_unknown_prefer_back())

    def test_unknown_prefer_back_waits_when_back_on_interval(self):
        """Back 刚点过、interval 未到时，仍要挡住 HOME/齿轮，不能改点 GOTO_MAIN。"""
        from module.ui.assets import BACK_ARROW

        ui = self._ui()
        ui.appear_then_click = lambda button, **kwargs: False
        ui.appear = lambda button, **kwargs: button is BACK_ARROW
        self.assertTrue(ui._ui_unknown_prefer_back())

    def test_unknown_prefer_back_false_when_only_home(self):
        from module.ui.assets import GOTO_MAIN

        ui = self._ui()
        ui.appear_then_click = lambda button, **kwargs: False
        ui.appear = lambda button, **kwargs: button is GOTO_MAIN
        self.assertFalse(ui._ui_unknown_prefer_back())

    def test_click_toward_parent_skips_goto_main_on_home(self):
        from module.ui.assets import MAIN_GOTO_CAMPAIGN
        from module.ui.page import Page, page_event

        ui = self._ui()
        Page.init_connection(page_main)
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        ui.device = Device()
        ui.appear = lambda button, **kwargs: button is MAIN_GOTO_CAMPAIGN
        self.assertFalse(ui._ui_click_toward_parent(page_event))
        self.assertEqual(clicks, [])

    def test_click_toward_parent_still_backs_from_settings(self):
        from module.ui.assets import BACK_ARROW
        from module.ui.page import Page, page_settings

        ui = self._ui()
        Page.init_connection(page_main)
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        class Timer:
            def reached(self):
                return True

            def reset(self):
                return None

        ui.device = Device()
        ui.appear = lambda *args, **kwargs: False
        ui.get_interval_timer = lambda *args, **kwargs: Timer()
        ui.ui_button_interval_reset = lambda *args, **kwargs: None
        ui.ui_current = page_settings
        self.assertTrue(ui._ui_click_toward_parent(page_settings))
        self.assertEqual(clicks, [BACK_ARROW])
