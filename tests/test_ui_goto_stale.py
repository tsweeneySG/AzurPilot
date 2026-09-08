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
