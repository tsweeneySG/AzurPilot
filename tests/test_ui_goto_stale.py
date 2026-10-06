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

    def test_unknown_prefer_back_stops_after_three(self):
        ui = self._ui()
        ui._ui_back_arrow_clicks = 3
        ui.appear_then_click = lambda button, **kwargs: True
        self.assertFalse(ui._ui_unknown_prefer_back())

    def test_click_toward_parent_stops_back_arrow_after_three(self):
        from module.ui.page import page_settings

        ui = self._ui()
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
        for _ in range(3):
            self.assertTrue(ui._ui_click_toward_parent(page_settings))
        self.assertFalse(ui._ui_click_toward_parent(page_settings))
        self.assertEqual(len(clicks), 3)

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

    def test_click_toward_parent_rate_limits_goto_main(self):
        from module.ui.assets import GOTO_MAIN
        from module.ui.page import Page, page_event, page_sp

        ui = self._ui()
        Page.init_connection(page_main)
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        class Timer:
            def __init__(self):
                self.calls = 0

            def reached(self):
                self.calls += 1
                return self.calls == 1

            def reset(self):
                return None

        ui.device = Device()
        ui.appear = lambda *args, **kwargs: False
        timer = Timer()
        ui.get_interval_timer = lambda *args, **kwargs: timer
        ui.ui_button_interval_reset = lambda *args, **kwargs: None
        self.assertTrue(ui._ui_click_toward_parent(page_event))
        self.assertFalse(ui._ui_click_toward_parent(page_sp))
        self.assertEqual(clicks, [GOTO_MAIN])

    def test_bridge_arrival_at_main_requires_home_chrome(self):
        ui = self._ui()
        ui.is_in_main = lambda: False
        self.assertFalse(ui._ui_bridge_confirms_arrival(page_main, page_main))

    def test_bridge_arrival_at_main_when_chrome_visible(self):
        ui = self._ui()
        ui.is_in_main = lambda: True
        self.assertTrue(ui._ui_bridge_confirms_arrival(page_main, page_main))

    def test_bridge_arrival_at_os_rejects_home_chrome(self):
        from module.ui.page import page_os

        ui = self._ui()
        ui._ui_home_chrome_visible = lambda *args, **kwargs: True
        self.assertFalse(ui._ui_bridge_confirms_arrival(page_os, page_os))

    def test_bridge_arrival_exercise_requires_check(self):
        from module.ui.page import page_exercise

        ui = self._ui()
        ui.is_in_main = lambda: False
        ui.appear = lambda *args, **kwargs: False
        self.assertFalse(ui._ui_bridge_confirms_arrival(page_exercise, page_exercise))
        ui.appear = lambda *args, **kwargs: True
        self.assertTrue(ui._ui_bridge_confirms_arrival(page_exercise, page_exercise))

    def test_bridge_arrival_non_main_does_not_need_chrome(self):
        from module.ui.page import page_guild

        ui = self._ui()
        ui.is_in_main = lambda: False
        self.assertTrue(ui._ui_bridge_confirms_arrival(page_guild, page_guild))

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

    def test_reject_stale_bridge_main_campaign_menu(self):
        from module.ui.assets import CAMPAIGN_MENU_CHECK

        ui = self._ui()

        def appear(button, **kwargs):
            return button is CAMPAIGN_MENU_CHECK

        ui.appear = appear
        self.assertEqual(ui._reject_stale_bridge_main(page_main), page_campaign_menu)

    def test_reject_stale_bridge_main_when_home_chrome(self):
        from module.ui.assets import MAIN_GOTO_CAMPAIGN

        ui = self._ui()

        def appear(button, **kwargs):
            return button is MAIN_GOTO_CAMPAIGN

        ui.appear = appear
        self.assertEqual(ui._reject_stale_bridge_main(page_main), page_main)

    def test_reject_stale_bridge_main_without_chrome(self):
        ui = self._ui()
        ui.appear = lambda *args, **kwargs: False
        self.assertIsNone(ui._reject_stale_bridge_main(page_main))

    def test_skip_main_goto_campaign_without_home_chrome(self):
        from module.ui.page import Page

        ui = self._ui()
        Page.init_connection(page_campaign_menu)
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        ui.device = Device()
        ui.appear = lambda *args, **kwargs: False
        self.assertFalse(ui._ui_click_toward_parent(page_main, via_bridge=True))
        self.assertEqual(clicks, [])

    def test_overshot_campaign_menu_on_event(self):
        from module.ui.assets import EVENT_CHECK

        ui = self._ui()

        def appear(button, **kwargs):
            return button is EVENT_CHECK

        ui.appear = appear
        self.assertTrue(ui._ui_overshot_campaign_menu())

    def test_main_goto_campaign_caps_at_two_clicks(self):
        from module.ui.assets import MAIN_GOTO_CAMPAIGN
        from module.ui.page import Page

        ui = self._ui()
        Page.init_connection(page_campaign_menu)
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
        ui.appear = lambda button, **kwargs: button is MAIN_GOTO_CAMPAIGN
        ui.get_interval_timer = lambda *args, **kwargs: Timer()
        ui.ui_button_interval_reset = lambda *args, **kwargs: None
        ui._ui_main_goto_campaign_clicks = 0
        self.assertTrue(ui._ui_click_toward_parent(page_main, via_bridge=True))
        self.assertTrue(ui._ui_click_toward_parent(page_main, via_bridge=True))
        self.assertFalse(ui._ui_click_toward_parent(page_main, via_bridge=True))
        self.assertEqual(clicks, [MAIN_GOTO_CAMPAIGN, MAIN_GOTO_CAMPAIGN])
        self.assertTrue(ui._ui_main_goto_capped)
        # 达上限后 MAIN_GOTO 仍停；BACK 另测。
        self.assertFalse(ui._ui_click_toward_parent(page_main, via_bridge=True))
        self.assertEqual(clicks, [MAIN_GOTO_CAMPAIGN, MAIN_GOTO_CAMPAIGN])

    def test_abort_main_goto_capped_event_is_arrival_only_for_campaign(self):
        from module.ui.assets import EVENT_CHECK
        from module.ui.page import page_daily, page_event, page_exercise

        ui = self._ui()
        ui.appear = lambda button, **kwargs: button is EVENT_CHECK
        self.assertEqual(ui._ui_abort_main_goto_capped(page_campaign_menu), 'arrived')
        self.assertEqual(ui.ui_current, page_event)
        # Daily/Exercise are not Combat arrival. Keep waiting (log once) so a
        # still-opening sortie hub can show CAMPAIGN_MENU_GOTO_DAILY.
        self.assertEqual(ui._ui_abort_main_goto_capped(page_daily), 'continue')
        self.assertEqual(ui._ui_abort_main_goto_capped(page_exercise), 'continue')

    def test_abort_main_goto_capped_daily_continues_on_campaign_menu(self):
        from module.ui.assets import CAMPAIGN_MENU_CHECK
        from module.ui.page import page_daily, page_exercise

        ui = self._ui()
        ui.appear = lambda button, **kwargs: button is CAMPAIGN_MENU_CHECK
        self.assertEqual(ui._ui_abort_main_goto_capped(page_daily), 'continue')
        self.assertEqual(ui._ui_abort_main_goto_capped(page_exercise), 'continue')

    def test_abort_main_goto_capped_archives_gives_up(self):
        from module.ui.page import page_archives

        ui = self._ui()
        ui.appear = lambda *args, **kwargs: False
        self.assertEqual(ui._ui_abort_main_goto_capped(page_archives), 'abort')

    def test_archives_heartbeat_waits_for_pixels(self):
        from module.ui.page import page_archives

        ui = self._ui()
        ui.appear = lambda *args, **kwargs: False
        self.assertFalse(ui._ui_bridge_confirms_arrival(page_archives, page_archives))
        ui.appear = lambda button, **kwargs: button is page_archives.check_button
        self.assertTrue(ui._ui_bridge_confirms_arrival(page_archives, page_archives))

    def test_abort_main_goto_capped_home_continues_for_os(self):
        from module.ui.assets import MAIN_GOTO_CAMPAIGN
        from module.ui.page import page_os

        ui = self._ui()
        ui.appear = lambda button, **kwargs: button is MAIN_GOTO_CAMPAIGN
        self.assertEqual(ui._ui_abort_main_goto_capped(page_os), 'continue')
        self.assertEqual(ui._ui_abort_main_goto_capped(page_campaign_menu), 'continue')

    def test_ui_goto_event_checks_event_pixels(self):
        import inspect

        from module.campaign.campaign_event import CampaignEvent

        src = inspect.getsource(CampaignEvent.ui_goto_event)
        self.assertIn('EVENT_CHECK', src)
        self.assertIn('出击菜单跳过', src)
        self.assertIn('_bridge_goto_event', src)
        src = inspect.getsource(CampaignEvent._bridge_goto_event)
        self.assertIn('goto_level', src)

    def test_ui_goto_tries_goto_level(self):
        import inspect

        from module.ui.ui import UI

        src = inspect.getsource(UI.ui_goto)
        self.assertIn('_bridge_try_goto_level', src)
        self.assertIn('_bridge_try_goto_scene', src)
        self.assertIn('_ui_abort_main_goto_capped', src)
        self.assertIn("action == 'abort'", src)
        self.assertIn('_ui_home_chrome_visible()', src)
        src = inspect.getsource(UI._ui_click_toward_parent)
        self.assertIn('_ui_bridge_nav_pending', src)
        self.assertIn('GOTO_MAIN_WHITE', src)
        self.assertIn('MAIN_GOTO_DORMMENU_WHITE', src)
        self.assertIn('DORMMENU_GOTO_ACADEMY', src)
        src = inspect.getsource(UI._bridge_try_goto_scene)
        self.assertIn("'type': 'supply'", src)
        src = inspect.getsource(UI.ui_additional)
        self.assertIn('appear_then_click(MAP_PREPARATION_CANCEL', src)
        self.assertNotIn('BRIDGE_MAP_PREP_CANCEL', src)
        self.assertIn('_ui_map_prep_visible', src)
        self.assertIn('_ui_map_prep_cancel_capped', src)
        src = inspect.getsource(UI._ui_click_toward_parent)
        self.assertIn('_ui_map_prep_visible', src)
        self.assertIn('_ui_map_prep_cancel_capped', src)

    def test_skip_goto_main_while_map_prep_visible(self):
        from module.map.assets import MAP_PREPARATION
        from module.ui.page import Page, page_event, page_main

        ui = self._ui()
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        Page.init_connection(page_main)
        page_event.parent = page_main
        ui.device = Device()
        ui.appear = lambda button, **kwargs: button is MAP_PREPARATION
        ui._ui_skip_home_click = lambda *args, **kwargs: False
        ui._ui_goto_scene_pending = False
        ui._ui_main_goto_capped = False
        self.assertFalse(ui._ui_click_toward_parent(page_event, via_bridge=True))
        self.assertEqual(clicks, [])

    def test_main_goto_capped_still_clicks_back(self):
        from module.ui.assets import BACK_ARROW
        from module.ui.page import Page, page_campaign, page_event, page_exercise

        ui = self._ui()
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        class Timer:
            def reached(self):
                return True

            def reset(self):
                return None

        Page.init_connection(page_exercise)
        # A* 可能把 event.parent 设成 page_main（与 campaign 同深）；上限后应改点 BACK。
        page_event.parent = page_campaign
        ui.device = Device()
        ui.appear = lambda *args, **kwargs: False
        ui._ui_home_chrome_visible = lambda *args, **kwargs: False
        ui._ui_skip_home_click = lambda *args, **kwargs: False
        ui.get_interval_timer = lambda *args, **kwargs: Timer()
        ui.ui_button_interval_reset = lambda *args, **kwargs: None
        ui._ui_goto_scene_pending = False
        ui._ui_main_goto_capped = True
        self.assertTrue(ui._ui_click_toward_parent(page_event, via_bridge=True))
        self.assertEqual(clicks, [BACK_ARROW])

    def test_main_goto_capped_prefers_back_over_home(self):
        from module.ui.assets import BACK_ARROW, GOTO_MAIN
        from module.ui.page import Page, page_event, page_exercise, page_main

        ui = self._ui()
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        class Timer:
            def reached(self):
                return True

            def reset(self):
                return None

        Page.init_connection(page_exercise)
        page_event.parent = page_main
        self.assertIs(page_event.links[page_event.parent], GOTO_MAIN)
        ui.device = Device()
        ui.appear = lambda *args, **kwargs: False
        ui._ui_home_chrome_visible = lambda *args, **kwargs: False
        ui._ui_skip_home_click = lambda *args, **kwargs: False
        ui.get_interval_timer = lambda *args, **kwargs: Timer()
        ui.ui_button_interval_reset = lambda *args, **kwargs: None
        ui._ui_goto_scene_pending = False
        ui._ui_main_goto_capped = True
        self.assertTrue(ui._ui_click_toward_parent(page_event, via_bridge=True))
        self.assertEqual(clicks, [BACK_ARROW])

    def test_ensure_campaign_ui_tries_chapter_enter(self):
        import inspect

        from module.campaign.campaign_ui import CampaignUI

        src = inspect.getsource(CampaignUI.ensure_campaign_ui)
        self.assertIn('_bridge_open_chapter_prep', src)
        src = inspect.getsource(CampaignUI._bridge_open_chapter_prep)
        self.assertIn('no_tries', src)
        self.assertIn("No remaining chapter tries", src)
        self.assertIn('panel_error', src)
        self.assertIn('archive_title', src)

    def test_campaign_sp_uses_bridge_tries(self):
        import inspect

        from module.event.campaign_sp import CampaignSP
        from module.map.map_operation import MapOperation

        src = inspect.getsource(CampaignSP.run)
        self.assertIn('event_sp', src)
        self.assertIn('get_task_remains', src)
        src = inspect.getsource(MapOperation._bridge_try_chapter_track)
        self.assertIn('no_tries', src)
        self.assertIn("No remaining chapter tries", src)
        self.assertIn('not_in_prep', src)
        self.assertIn('skip MAP_PREPARATION click', src)
        self.assertIn("ScriptEnd('chapter_track not_in_prep')", src)
        from module.handler.enemy_searching import EnemySearchingHandler
        from module.handler.info_handler import InfoHandler
        src = inspect.getsource(EnemySearchingHandler.handle_in_stage)
        self.assertIn('_in_stage_prep_cancel_clicks', src)
        src = inspect.getsource(InfoHandler.handle_game_tips)
        self.assertIn('MAP_PREPARATION', src)

    def test_enter_map_keeps_prep_after_auto_search_continue(self):
        from module.base.timer import Timer
        from module.map.map_operation import MapOperation

        op = MapOperation.__new__(MapOperation)
        op._auto_search_continue_timer = None
        op._level_prep_from_bridge = lambda: None
        self.assertFalse(op._auto_search_continue_blocks_prep())

        op._auto_search_continue_timer = Timer(20).start()
        op._level_prep_from_bridge = lambda: None
        self.assertTrue(op._auto_search_continue_blocks_prep())

        op._level_prep_from_bridge = lambda: 'info'
        self.assertFalse(op._auto_search_continue_blocks_prep())

    def test_enter_map_daily_check_respects_bridge_prep(self):
        from module.map.map_operation import MapOperation

        op = MapOperation.__new__(MapOperation)
        op.appear = lambda *args, **kwargs: False
        op._level_prep_from_bridge = lambda: 'info'
        self.assertTrue(op._enter_map_level_info_open())
        op._level_prep_from_bridge = lambda: None
        self.assertFalse(op._enter_map_level_info_open())
        op.appear = lambda button, *args, **kwargs: getattr(button, 'name', '') == 'MAP_PREPARATION'
        self.assertTrue(op._enter_map_level_info_open())

    def test_bridge_goto_scene_keys(self):
        from module.ui.page import (
            page_academy, page_campaign_menu, page_daily, page_exercise,
            page_munitions, page_os, page_shop,
        )

        ui = self._ui()
        self.assertEqual(ui._bridge_goto_scene_key(page_academy), 'NAVALACADEMYSCENE')
        self.assertEqual(ui._bridge_goto_scene_key(page_munitions), 'SHOP')
        self.assertEqual(ui._bridge_goto_scene_key(page_shop), 'SHOP')
        self.assertEqual(ui._bridge_goto_scene_key(page_os), 'WORLD')
        self.assertEqual(ui._bridge_goto_scene_key(page_daily), 'DAILYLEVEL')
        self.assertEqual(ui._bridge_goto_scene_key(page_exercise), 'MILITARYEXERCISE')
        self.assertIsNone(ui._bridge_goto_scene_key(page_main))
        self.assertIsNone(ui._bridge_goto_level_want(page_daily))
        self.assertIsNone(ui._bridge_goto_level_want(page_exercise))
        self.assertEqual(ui._bridge_goto_level_want(page_campaign_menu), 'campaign_menu')
        from module.ui.page import page_archives
        self.assertEqual(ui._bridge_goto_level_want(page_archives), 'archives')

    def test_os_init_bails_if_still_on_main(self):
        import inspect

        from module.os.map import OSMap

        src = inspect.getsource(OSMap.os_init)
        self.assertIn('未能进入大世界', src)
        self.assertIn('task_delay', src)
        self.assertIn('TaskEnd', src)

    def test_shop_munitions_pages_equivalent(self):
        from module.ui.page import page_munitions, page_shop

        ui = self._ui()
        self.assertTrue(ui._ui_pages_equivalent(page_munitions, page_shop))
        self.assertFalse(ui._ui_goto_blocked_by_bridge(page_munitions, page_shop))
        self.assertTrue(ui._ui_bridge_confirms_arrival(page_munitions, page_shop))
        ui.ui_current = page_shop
        self.assertFalse(ui._ui_goto_needs_fresh_frame(page_munitions))
        self.assertFalse(ui._ui_goto_blocked_by_source(page_munitions))

    def test_hub_tile_skipped_when_home_chrome_visible(self):
        from module.ui.page import Page, page_academy, page_dormmenu, page_main

        ui = self._ui()
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        Page.init_connection(page_academy)
        ui.device = Device()
        ui.ui_current = page_dormmenu
        ui.appear = lambda *args, **kwargs: False
        ui._ui_home_chrome_visible = lambda *args, **kwargs: True
        ui._ui_page_from_home_chrome = lambda *args, **kwargs: page_main
        ui._ui_skip_home_click = lambda *args, **kwargs: False
        ui._ui_goto_scene_pending = False
        self.assertFalse(ui._ui_click_toward_parent(page_dormmenu, via_bridge=True))
        self.assertEqual(clicks, [])
        self.assertEqual(ui.ui_current, page_main)

    def test_dormmenu_dock_shares_interval(self):
        from module.ui.page import Page, page_dormmenu, page_main, page_main_white

        ui = self._ui()
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        class Timer:
            def __init__(self):
                self.used = False

            def reached(self):
                if self.used:
                    return False
                self.used = True
                return True

            def reset(self):
                return None

        Page.init_connection(page_dormmenu)
        shared = Timer()
        ui.device = Device()
        ui.appear = lambda *args, **kwargs: False
        ui._ui_home_chrome_visible = lambda *args, **kwargs: True
        ui._ui_skip_home_click = lambda *args, **kwargs: False
        ui.get_interval_timer = lambda *args, **kwargs: shared
        ui.ui_button_interval_reset = lambda *args, **kwargs: None
        ui._ui_goto_scene_pending = False
        self.assertTrue(ui._ui_click_toward_parent(page_main, via_bridge=True))
        self.assertFalse(ui._ui_click_toward_parent(page_main_white, via_bridge=True))
        self.assertEqual(len(clicks), 1)

    def test_goto_level_pending_skips_all_clicks(self):
        from module.ui.page import Page, page_campaign_menu, page_daily, page_os

        ui = self._ui()
        clicks = []

        class Device:
            def click(self, button):
                clicks.append(button)

        Page.init_connection(page_daily)
        ui.device = Device()
        ui.appear = lambda *args, **kwargs: False
        ui._ui_home_chrome_visible = lambda *args, **kwargs: False
        ui._ui_skip_home_click = lambda *args, **kwargs: False
        ui._ui_map_prep_visible = lambda *args, **kwargs: False
        ui._ui_goto_level_pending = True
        ui._ui_goto_scene_pending = False
        self.assertFalse(ui._ui_click_toward_parent(page_os))
        self.assertFalse(ui._ui_click_toward_parent(page_campaign_menu))
        self.assertEqual(clicks, [])

    def test_ui_goto_shop_prefers_munitions_scene(self):
        import inspect

        from module.shop.ui import ShopUI

        src = inspect.getsource(ShopUI.ui_goto_shop)
        self.assertIn('page_munitions', src)
        self.assertIn('ui_ensure(page_munitions)', src)
        self.assertIn('ui_ensure(page_academy)', src)

    def test_world_scene_pending_survives_twelve_frames(self):
        ui = self._ui()
        ui._ui_goto_level_pending = False
        ui._ui_goto_scene_pending = True
        ui._ui_goto_scene_key = 'WORLD'
        ui._ui_goto_scene_pending_frames = 0
        ui._ui_goto_scene_os_gave_up = False

        class Hold:
            def reached(self):
                return False

        ui._ui_goto_scene_world_timer = Hold()
        for _ in range(20):
            ui._ui_tick_bridge_nav_pending()
        self.assertTrue(ui._ui_goto_scene_pending)
        self.assertFalse(ui._ui_goto_scene_os_gave_up)

    def test_world_scene_pending_gives_up_when_timer_ends(self):
        ui = self._ui()
        ui._ui_goto_level_pending = False
        ui._ui_goto_scene_pending = True
        ui._ui_goto_scene_key = 'WORLD'
        ui._ui_goto_scene_os_gave_up = False

        class Done:
            def reached(self):
                return True

        ui._ui_goto_scene_world_timer = Done()
        ui._ui_tick_bridge_nav_pending()
        self.assertFalse(ui._ui_goto_scene_pending)
        self.assertTrue(ui._ui_goto_scene_os_gave_up)

    def test_other_scene_pending_expires_at_twelve_frames(self):
        ui = self._ui()
        ui._ui_goto_level_pending = False
        ui._ui_goto_scene_pending = True
        ui._ui_goto_scene_key = 'SHOP'
        ui._ui_goto_scene_pending_frames = 0
        for _ in range(11):
            ui._ui_tick_bridge_nav_pending()
        self.assertTrue(ui._ui_goto_scene_pending)
        ui._ui_tick_bridge_nav_pending()
        self.assertFalse(ui._ui_goto_scene_pending)
