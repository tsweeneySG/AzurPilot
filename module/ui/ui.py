"""UI 导航核心模块。

提供游戏页面间的自动导航功能，是所有需要页面切换的操作的基础。

核心方法：
- ui_goto(page): 沿最短路径导航到目标页面
- ui_ensure(page): 检测当前页面并导航到目标页面
- ui_page_appear(page): 检测指定页面是否出现
- ui_back(): 点击返回按钮
- ui_get_current_page(): 检测当前所在页面

导航机制：
1. 通过 Page.init_connection() 预计算页面间的最短路径
2. 每个页面有 check_button 用于检测
3. 页面间通过 link(button, destination) 建立连接
4. 导航时沿 parent 链逐页跳转

特殊处理：
- 弹窗关闭：导航过程中自动关闭各种弹窗
- 剧情跳过：自动跳过插入的剧情
- 页面等待：等待页面完全加载后再继续

继承自 InfoHandler，可处理导航过程中的各种弹窗。
"""

from module.base.button import Button
from module.base.decorator import run_once
from module.base.timer import Timer
from module.combat.assets import GET_ITEMS_1, GET_ITEMS_2, GET_SHIP
from module.exception import (GameNotRunningError, GamePageUnknownError,
                              GameTooManyClickError, RequestHumanTakeover)
from module.exercise.assets import EXERCISE_PREPARATION
from module.handler.assets import (AUTO_SEARCH_MENU_EXIT, BATTLE_PASS_NEW_SEASON, BATTLE_PASS_NOTICE, GAME_TIPS,
                                   IN_MAP, LOGIN_ANNOUNCE, LOGIN_ANNOUNCE_2, LOGIN_CHECK, LOGIN_RETURN_SIGN,
                                   MAINTENANCE_ANNOUNCE, MONTHLY_PASS_NOTICE)
from module.handler.info_handler import InfoHandler
from module.logger import logger
from module.map.assets import (FLEET_PREPARATION, MAP_PREPARATION,
                               MAP_PREPARATION_HARD, MAP_PREPARATION_CANCEL, WITHDRAW)
from module.meowfficer.assets import MEOWFFICER_BUY
from module.ocr.ocr import Ocr
from module.os_handler.assets import (
    AUTO_SEARCH_REWARD, EXCHANGE_CHECK, RESET_FLEET_PREPARATION, RESET_TICKET_POPUP,
)
from module.raid.assets import *
from module.shop.assets import NAV_GENERAL, SHOP_REFRESH_CHECK, TAB_GENERAL, TAB_MERIT
from module.ui.assets import *
from module.ui.page import (Page, page_academy, page_archives, page_campaign, page_campaign_menu,
                            page_daily, page_dormmenu, page_event, page_exercise, page_in_map,
                            page_main, page_main_white, page_munitions, page_os, page_settings,
                            page_shop, page_sp)
from module.ui_white.assets import *


class UI(InfoHandler):
    """UI 导航核心类。

    提供游戏页面间的自动导航功能。所有需要页面切换的操作
    都通过此类的方法进行导航。

    Attributes:
        ui_current (Page): 当前所在的页面。
    """
    ui_current: Page

    def _is_munitions_page(self, offset=(20, 20), interval=0):
        """检测军需 / NewShop 页面。

        左侧「購買部」模板常在新商店 UI 上失效，刷新图标加标签/导航作为回退。
        """
        if self.appear(MUNITIONS_CHECK, offset=offset, interval=interval):
            return True
        if self.appear(SHOP_REFRESH_CHECK, offset=(30, 30), interval=interval):
            if self.appear(TAB_GENERAL, offset=offset, interval=0):
                return True
            if self.appear(TAB_MERIT, offset=offset, interval=0):
                return True
            if self.appear(NAV_GENERAL, offset=offset, interval=0):
                return True
            if self.appear(SHOP_BACK_ARROW, offset=offset, interval=0):
                return True
        return False

    def ui_page_appear(self, page, offset=(30, 30), interval=0):
        """检测指定页面是否出现在屏幕上。

        Args:
            page (Page): 要检测的页面。
            offset (tuple): 匹配偏移量。
            interval (int | float): 检测间隔。

        Returns:
            bool: 页面是否出现。
        """
        if page == page_main:
            return self.appear(page_main.check_button, offset=(5, 5), interval=interval)
        if page == page_munitions:
            return self._is_munitions_page(offset=offset, interval=interval)
        # 英文本地化导致学院标题字体宽度变化，需要额外检查其他按钮
        if self.config.SERVER == 'en' and page == page_academy:
            if self.appear(ACADEMY_GOTO_MUNITIONS, offset=offset, interval=interval):
                return True
        return self.appear(page.check_button, offset=offset, interval=interval)

    def _ui_pages_equivalent(self, a, b):
        """同一界面的别名。军需与 NewShop 都是 SCENE.SHOP (supply)。"""
        if a is None or b is None:
            return False
        if a == b:
            return True
        pair = {a, b}
        return pair == {page_main, page_main_white} or pair == {page_munitions, page_shop}

    def _ui_goto_needs_fresh_frame(self, destination):
        """导航离开当前页时不能复用截图。

        Sweeney 心跳可以先于像素更新（例如 BACK_ARROW 后已在出击菜单，
        缓存仍是突袭页）。复用该帧会让 RAID_CHECK 立刻命中，从而跳过
        CAMPAIGN_MENU_GOTO_EVENT，随后把 Hard 点到出击菜单空白处。
        """
        current = getattr(self, 'ui_current', None)
        if current == destination:
            return False
        if self._ui_pages_equivalent(current, destination):
            return False
        return True

    def _ui_goto_blocked_by_source(self, destination, offset=(30, 30)):
        """源页面检测仍命中时，不把目标页的误匹配当成已到达。"""
        current = getattr(self, 'ui_current', None)
        if current is None or current == destination:
            return False
        if self._ui_pages_equivalent(current, destination):
            return False
        check = current.check_button
        if check is None:
            return False
        return self.appear(check, offset=offset, interval=0)

    def _ui_goto_blocked_by_bridge(self, destination, bridged):
        """像素已命中目标页，但 Sweeney 心跳仍命名为另一页时视为未到达。

        出击菜单（entrance）与主线章节列表共用 Attack/Chapter 顶栏，
        CAMPAIGN_CHECK 会在菜单上误匹配。此时 HARD 开关不在屏幕上，
        SWITCH_1_HARD 会点到作战档案。
        """
        if bridged is None or self._ui_pages_equivalent(bridged, destination):
            return False
        return True

    def _ui_goto_wait_on_stale_bridge(self, destination, bridged):
        """像素已命中目标、心跳仍滞后时，是否空等而不点 A*。

        作战档案检测较准，空等可避免 GOTO_WAR_ARCHIVES 与 BACK_ARROW 对打。
        出击菜单与章节列表共用 CAMPAIGN_CHECK，空等会点不到
        CAMPAIGN_MENU_GOTO_CAMPAIGN，随后误点 SWITCH_1_HARD。

        Returns:
            bool: True 表示 continue 等待心跳；False 表示应继续往下点击。
        """
        if not self._ui_goto_blocked_by_bridge(destination, bridged):
            return False
        if destination == page_campaign and bridged == page_campaign_menu:
            return False
        return True

    def _ui_goto_blocked_by_dest_chrome(self, destination):
        """目标是主线章节列表时，活动页或出击菜单 chrome 仍在则未到达。

        page_event BACK 后 CAMPAIGN_CHECK / 心跳会先报 page_campaign，
        关卡名还是活动或菜单，随后 Mode_switch_1 与 OCR 空转。
        """
        if destination != page_campaign:
            return False
        if self.appear(CAMPAIGN_MENU_CHECK, offset=(30, 30), interval=0):
            return True
        if self.appear(EVENT_CHECK, offset=(30, 30), interval=0):
            return True
        return False

    def _ui_click_toward_parent(self, page, via_bridge=False):
        """沿 A* parent 点击一跳。受 interval 限制，点击则返回 True。

        GOTO_MAIN 与主界面设置齿轮同槽。A* 截图路径和心跳路径必须共用
        同一按钮 interval，否则 EVENT_CHECK 与 SP_CHECK 会在 200ms 内
        各点一次 HOME，再加心跳第三下，把刚回到的主界面点进设置页。
        """
        if page is None or page.parent is None:
            return False
        parent = page.parent
        button = page.links.get(parent)
        if button is None:
            return False
        if self._ui_skip_home_click(button):
            logger.info('[UI] 已在主界面，跳过 GOTO_MAIN（避免打开设置）')
            return False
        # 情绪延迟会留下 LevelInfoView。HOME 关不掉准备弹窗，再点 CANCEL 就和对打
        # （2_brad / 5_booty 2026-09-18 晚 Event D3 后 goto_main）。
        if (
            button in (GOTO_MAIN, GOTO_MAIN_WHITE)
            and self._ui_map_prep_visible()
            and not getattr(self, '_ui_map_prep_cancel_capped', False)
        ):
            logger.info('[UI] 地图准备弹窗仍开，跳过 GOTO_MAIN')
            return False
        if button in (MAIN_GOTO_CAMPAIGN, MAIN_GOTO_CAMPAIGN_WHITE) and not self._ui_home_chrome_visible():
            logger.info('[UI] 不在主界面，跳过 MAIN_GOTO_CAMPAIGN（心跳误报 MAIN）')
            return False
        # GO_SCENE 过场中不要点 HOME / 出击 / 每日砖。
        # goto_level pending 以前只挡 MAIN_GOTO，1_67 Daily 从 WORLD 仍点了
        # GOTO_MAIN 和 CAMPAIGN_MENU_GOTO_DAILY，把 GO_SCENE LEVEL 打断。
        if self._ui_bridge_nav_pending():
            return False
        # 出击入口已达上限：不要再点 MAIN_GOTO / GOTO_MAIN。
        # BACK 和出击菜单里的演习/每日入口仍要点，否则 Exercise 进不去。
        # A* 从活动页到演习时 event→main 与 event→campaign 同深，可能选 HOME。
        if getattr(self, '_ui_main_goto_capped', False):
            if button in (MAIN_GOTO_CAMPAIGN, MAIN_GOTO_CAMPAIGN_WHITE):
                return False
            if button in (GOTO_MAIN, GOTO_MAIN_WHITE):
                back_dest = None
                for dest, btn in page.links.items():
                    if btn is BACK_ARROW:
                        back_dest = dest
                        button = btn
                        break
                if back_dest is None:
                    return False
                parent = back_dest
        # 心跳报出击菜单但画面不是菜单时，盲点 CAMPAIGN_MENU_GOTO_CAMPAIGN
        # 会打满 12 次并重启（Hard 1_67 / Brad / Margaret、Main Booty，2026-09-24）。
        if button is CAMPAIGN_MENU_GOTO_CAMPAIGN:
            n = getattr(self, '_ui_campaign_menu_goto_clicks', 0)
            if n >= 3:
                if not getattr(self, '_ui_campaign_menu_goto_capped_logged', False):
                    logger.warning(
                        '[UI] CAMPAIGN_MENU_GOTO_CAMPAIGN 连点无进展，停止点击以免重启'
                    )
                    self._ui_campaign_menu_goto_capped_logged = True
                return False
        # 设置页 Back 与心跳误报的左上角匹配是同一按钮。两条路径用的
        # interval 不同，会互相换成未启动的计时器，于是 200ms 一点，
        # 12 下重启（1_67 / Asami / nyan / booty 2026-09-29 10:21–18:24）。
        if button in (BACK_ARROW, BACK_ARROW_WHITE) and self._ui_back_arrow_capped():
            return False
        if button in (MAIN_GOTO_CAMPAIGN, MAIN_GOTO_CAMPAIGN_WHITE):
            n = getattr(self, '_ui_main_goto_campaign_clicks', 0)
            if n >= 2:
                # 第二次点击后先等 interval，给出击菜单过场。立刻 cap
                # 会在 1 秒内结束导航，大世界初始化就在主界面空等地球仪
                # （Margaret 2026-09-18 14:01 OpsiMonthBoss）。
                timer = self.get_interval_timer(button, interval=5, renew=True)
                if not timer.reached():
                    return False
                self._ui_main_goto_capped = True
                if not getattr(self, '_ui_main_goto_capped_logged', False):
                    logger.warning('[UI] MAIN_GOTO_CAMPAIGN 连点无进展，停止点击以免重启')
                    self._ui_main_goto_capped_logged = True
                return False
        dock = (MAIN_GOTO_DORMMENU, MAIN_GOTO_DORMMENU_WHITE)
        hub_tiles = (
            DORMMENU_GOTO_ACADEMY, DORMMENU_GOTO_DORM, DORMMENU_GOTO_MEOWFFICER,
            DORMMENU_GOTO_PRIVATE_QUARTERS, DORMMENU_GOTO_ISLAND,
        )
        if button in hub_tiles and self._ui_home_chrome_visible():
            logger.info('[UI] 主界面仍可见，跳过后宅菜单入口（枢纽未打开）')
            # DORMMENU_CHECK 与学院砖同槽；误检成枢纽时把当前页打回主界面。
            if getattr(self, 'ui_current', None) is page_dormmenu:
                self.ui_current = self._ui_page_from_home_chrome()
            return False
        if button in dock:
            timer = self.get_interval_timer('MAIN_GOTO_DORMMENU', interval=5, renew=True)
        else:
            timer = self.get_interval_timer(button, interval=5, renew=True)
        if not timer.reached():
            return False
        suffix = ' (Sweeney bridge)' if via_bridge else ''
        logger.info(f'[UI] 页面切换: {page} -> {parent}{suffix}')
        self.ui_current = page
        self.device.click(button)
        if button in (MAIN_GOTO_CAMPAIGN, MAIN_GOTO_CAMPAIGN_WHITE):
            self._ui_main_goto_campaign_clicks = getattr(self, '_ui_main_goto_campaign_clicks', 0) + 1
        if button is CAMPAIGN_MENU_GOTO_CAMPAIGN:
            self._ui_campaign_menu_goto_clicks = getattr(self, '_ui_campaign_menu_goto_clicks', 0) + 1
        if button in (BACK_ARROW, BACK_ARROW_WHITE):
            self._ui_back_arrow_clicks = getattr(self, '_ui_back_arrow_clicks', 0) + 1
        timer.reset()
        self.ui_button_interval_reset(button)
        return True

    def _ui_bridge_confirms_arrival(self, destination, bridged):
        """心跳到达是否可信。主界面心跳会在设置页打开前仍报 MAIN。"""
        if bridged is None or not self._ui_pages_equivalent(bridged, destination):
            return False
        if destination in (page_main, page_main_white) and not self.is_in_main():
            logger.info(f'[UI] 忽略 {destination} 心跳到达 (未见主界面 chrome)')
            return False
        # goto_scene WORLD 的心跳会在过场画完前就报 page_os。这一帧仍是主界面时
        # 当成已到达会立刻放弃大世界，下一任务再切场景，WorldScene 退出时
        # WSPool:Return 对空箭头抛异常（4_nyan 2026-09-23 06:34）。
        if destination is page_os and self._ui_home_chrome_visible():
            logger.info('[UI] 忽略 page_os 心跳到达 (仍见主界面)')
            return False
        # goto_scene MILITARYEXERCISE 心跳会在过场前报 page_exercise，
        # 此时截图仍是主界面，OCR 次数会读成 0 并半周期放弃（2_brad / 6_margaret 15:00）。
        if destination is page_exercise:
            check = destination.check_button
            if check is not None and not self.appear(check, offset=(30, 30)):
                logger.info('[UI] 忽略 page_exercise 心跳到达 (未见演习页)')
                return False
        # goto_level archives 的心跳会在列表画完前就报 page_archives。
        if destination is page_archives:
            check = destination.check_button
            if check is not None and not self.appear(check, offset=(30, 30)):
                logger.info('[UI] 忽略 page_archives 心跳到达 (未见作战档案)')
                return False
        return True

    def _sweeney_bridge_enabled(self):
        config = getattr(self, 'config', None)
        return bool(getattr(config, 'Optimization_SweeneyBridge', False))

    def _ui_bridge_nav_pending(self):
        """goto_scene / goto_level 过场中不要截图乱点。"""
        return bool(
            getattr(self, '_ui_goto_scene_pending', False)
            or getattr(self, '_ui_goto_level_pending', False)
        )

    def _ui_world_scene_pending(self):
        """goto_scene WORLD 过场中。月切剧情未画完时不要点 HOME 或准备取消。"""
        return bool(
            getattr(self, '_ui_goto_scene_pending', False)
            and getattr(self, '_ui_goto_scene_key', None) == 'WORLD'
        )

    def _ui_tick_bridge_nav_pending(self):
        """每圈截图推进过场等待。不依赖 A* 是否找到可点按钮。"""
        if getattr(self, '_ui_goto_level_pending', False):
            frames = getattr(self, '_ui_goto_level_pending_frames', 0) + 1
            self._ui_goto_level_pending_frames = frames
            if frames >= 8:
                logger.info('[UI] goto_level 未到达，恢复截图导航')
                self._ui_goto_level_pending = False
        if not getattr(self, '_ui_goto_scene_pending', False):
            return
        if getattr(self, '_ui_goto_scene_key', None) == 'WORLD':
            timer = getattr(self, '_ui_goto_scene_world_timer', None)
            if timer is None:
                self._ui_goto_scene_world_timer = Timer(90).start()
                return
            if timer.reached():
                logger.warning(
                    '[UI] goto_scene WORLD 超过 90 秒仍未进入大世界，放弃导航以免重启'
                )
                self._ui_goto_scene_pending = False
                self._ui_goto_scene_os_gave_up = True
            return
        frames = getattr(self, '_ui_goto_scene_pending_frames', 0) + 1
        self._ui_goto_scene_pending_frames = frames
        if frames >= 12:
            logger.info('[UI] goto_scene 未到达，恢复截图导航')
            self._ui_goto_scene_pending = False

    def _bridge_goto_scene_key(self, destination):
        """GAME.GO_SCENE 可直达的页面，跳过港口枢纽误点。"""
        if destination is page_academy:
            return 'NAVALACADEMYSCENE'
        if destination in (page_munitions, page_shop):
            return 'SHOP'
        if destination is page_os:
            return 'WORLD'
        if destination is page_daily:
            return 'DAILYLEVEL'
        if destination is page_exercise:
            return 'MILITARYEXERCISE'
        return None

    def _bridge_try_goto_scene(self, destination):
        key = self._bridge_goto_scene_key(destination)
        if key is None or not self._sweeney_bridge_enabled():
            return False
        try:
            from module.alas_bridge.actions import goto_scene
        except Exception:
            return False
        data = {'type': 'supply'} if key == 'SHOP' else None
        result = goto_scene(self.config, key, data=data)
        if not isinstance(result, dict):
            return False
        logger.info(f'Sweeney goto_scene {key}: {result}')
        self._ui_goto_scene_pending = bool(result.get('pending'))
        self._ui_goto_scene_pending_frames = 0
        self._ui_goto_scene_key = key
        self._ui_goto_scene_os_gave_up = False
        # 月切进大世界的剧情远长于 12 帧。过场里点 HOME 会把 GO_SCENE 打断，
        # 未知页面再重启，同一任务立刻再进（2026-10-01 03:06 起五号循环）。
        if key == 'WORLD' and self._ui_goto_scene_pending:
            self._ui_goto_scene_world_timer = Timer(90).start()
            # 正常进场大约 35 秒（6ix7even 08:46）。超过这个时间仍在主界面，
            # 说明月切预加载停住了，后面会改走 inSave。
            self._ui_world_insave_timer = Timer(45).start()
            self._ui_world_insave_sent = False
        else:
            self._ui_goto_scene_world_timer = None
            self._ui_world_insave_timer = None
            self._ui_world_insave_sent = False
        return True

    def _bridge_goto_world_insave(self):
        """跳过月切重置和开场剧情，直接加载大世界。"""
        if not self._sweeney_bridge_enabled():
            return False
        try:
            from module.alas_bridge.actions import goto_scene
        except Exception:
            return False
        result = goto_scene(self.config, 'WORLD', data={'inSave': True})
        logger.info(f'Sweeney goto_scene WORLD inSave: {result}')
        return isinstance(result, dict)

    def _bridge_goto_level_want(self, destination):
        if destination is page_event:
            return 'event'
        if destination is page_sp:
            return 'sp'
        if destination is page_campaign_menu:
            return 'campaign_menu'
        if destination is page_campaign:
            return 'campaign'
        if destination is page_archives:
            return 'archives'
        return None

    def _bridge_try_goto_level(self, destination):
        """GAME.GO_SCENE LEVEL，避免点 MAIN_GOTO_CAMPAIGN 误进活动页。"""
        want = self._bridge_goto_level_want(destination)
        if want is None or not self._sweeney_bridge_enabled():
            return False
        try:
            from module.alas_bridge.actions import goto_level
        except Exception:
            return False
        result = goto_level(self.config, want=want, poll=0.0)
        if not isinstance(result, dict):
            return False
        if result.get('pending_battle'):
            return False
        logger.info(f'Sweeney goto_level: {result}')
        # already_there：下一圈用 EVENT_CHECK / 页面检测结束导航。
        # pending_scene 只挡一两拍，避免心跳仍 MAIN 时永远不点、空等到 GameStuck。
        self._ui_goto_level_pending = bool(result.get('pending_scene'))
        self._ui_goto_level_pending_frames = 0
        self._ui_goto_level_pending_logged = False
        return True

    def _try_sweeney_current_page(self, verbose=True):
        """Return an AzurPilot Page from the mod heartbeat, or None to screenshot-fallback."""
        try:
            from module.alas_bridge.game_state import GameState
        except Exception as e:
            logger.info(f'Sweeney bridge import failed: {e}')
            return None
        gs = getattr(self, '_sweeney_game_state', None)
        if gs is None:
            gs = GameState.from_config(self.config)
            self._sweeney_game_state = gs
        page = gs.get_page()
        if page is None:
            return None
        if verbose:
            logger.attr("UI", page.name)
            logger.info("UI page from Sweeney bridge")
        self.ui_current = page
        return page

    def _reject_stale_bridge_in_map(self, bridged):
        if bridged is None or bridged.name != 'page_in_map':
            return bridged
        if self.appear(IN_MAP, offset=(30, 30), interval=0):
            return bridged
        if self.appear(MAIN_GOTO_CAMPAIGN_WHITE, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_in_map (main white chrome)')
            return page_main_white
        if self.appear(MAIN_GOTO_CAMPAIGN, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_in_map (main chrome)')
            return page_main
        if self.appear(CAMPAIGN_MENU_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_in_map (campaign menu)')
            return page_campaign_menu
        if self.appear(EVENT_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_in_map (event list)')
            return page_event
        if self.appear(SP_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_in_map (sp list)')
            return page_sp
        logger.info('Reject stale bridge page_in_map (no map chrome)')
        return page_main

    def _reject_stale_bridge_campaign(self, bridged):
        if bridged is None or bridged.name != 'page_campaign':
            return bridged
        if self.appear(CAMPAIGN_MENU_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_campaign (campaign menu)')
            return page_campaign_menu
        if self.appear(EVENT_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_campaign (event list)')
            return page_event
        return bridged

    def _reject_stale_bridge_main(self, bridged):
        """心跳 MAIN 但主界面 chrome 不在：不要按主界面出击按钮连点。

        Event D3 `ui_goto_event` 会先去 page_campaign_menu。心跳仍报
        page_main 时 `_ui_click_toward_parent` 盲点 MAIN_GOTO_CAMPAIGN
        （1_67 / Brad / Asami / booty 2026-09-17 15:30）。
        """
        if bridged is None or bridged not in (page_main, page_main_white):
            return bridged
        if self._ui_home_chrome_visible():
            return bridged
        if self.appear(CAMPAIGN_MENU_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_main (campaign menu)')
            return page_campaign_menu
        if self.appear(EVENT_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_main (event list)')
            return page_event
        if self.appear(SP_CHECK, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_main (sp list)')
            return page_sp
        if self.appear(BACK_ARROW, offset=(30, 30), interval=0) \
                or self.appear(BACK_ARROW_WHITE, offset=(30, 30), interval=0):
            logger.info('Reject stale bridge page_main (back arrow)')
            return page_settings
        logger.info('Reject stale bridge page_main (no home chrome)')
        return None

    def _ui_overshot_campaign_menu(self):
        """去出击菜单时已经进了活动/SP 章节列表。

        主界面出击按钮与出击菜单活动入口接近。点 MAIN_GOTO_CAMPAIGN 常
        直接进活动；A* 再 GOTO_MAIN 打回主界面，12 次后重启
        （2026-09-17 15:50 Event D3 重启潮）。
        """
        return (
            self.appear(EVENT_CHECK, offset=(30, 30), interval=0)
            or self.appear(SP_CHECK, offset=(30, 30), interval=0)
        )

    def _ui_abort_main_goto_capped(self, destination):
        """MAIN_GOTO 点满后：活动/SP 目标算到达；其余继续等弹窗/过场。

        仍在主界面时不能 abort 假装到达。OpsiMonthBoss 会接着 zone_init，
        在主界面空等 MAP_GOTO_GLOBE 直到 GameStuck（Margaret 14:01）。
        """
        campaign_dests = (page_campaign_menu, page_event, page_sp, page_campaign)
        if destination in campaign_dests and self._ui_overshot_campaign_menu():
            logger.info('[UI] MAIN_GOTO 上限后已在活动/SP')
            if self.appear(EVENT_CHECK, offset=(30, 30), interval=0):
                self.ui_current = page_event
            else:
                self.ui_current = page_sp
            return 'arrived'
        # 每日/演习：Combat 进的是 LEVEL，不是 DAILYLEVEL / MILITARYEXERCISE。
        # 出击菜单砖仍可点；仍在主界面则改走 goto_scene，不要无限 continue
        # （1_67 2026-09-19 07:02 从 page_os 卡在 MAIN_GOTO 上限）。
        # 作战档案：出击砖点满后改开 LevelRemasterView，不要放弃 DataKey / WarArchives。
        if destination is page_archives:
            if getattr(self, '_ui_goto_level_pending', False):
                return 'continue'
            if not getattr(self, '_ui_goto_archives_retry_after_cap', False):
                self._ui_goto_archives_retry_after_cap = True
                if self._bridge_try_goto_level(destination):
                    logger.info('[UI] MAIN_GOTO 上限，改走 goto_level archives')
                    return 'continue'
            logger.warning(f'[UI] MAIN_GOTO 上限，放弃导航到 {destination}')
            return 'abort'
        if destination in (page_daily, page_exercise):
            if getattr(self, '_ui_goto_scene_pending', False):
                return 'continue'
            if self.appear(CAMPAIGN_MENU_CHECK, offset=(30, 30), interval=0):
                if not getattr(self, '_ui_abort_continue_logged', False):
                    logger.info(f'[UI] MAIN_GOTO 上限，出击菜单继续点 {destination}')
                    self._ui_abort_continue_logged = True
                return 'continue'
            if not getattr(self, '_ui_goto_scene_retry_after_cap', False):
                self._ui_goto_scene_retry_after_cap = True
                if self._bridge_try_goto_scene(destination):
                    logger.info(f'[UI] MAIN_GOTO 上限，改走 goto_scene {destination}')
                    return 'continue'
            if not getattr(self, '_ui_abort_continue_logged', False):
                logger.info(f'[UI] MAIN_GOTO 上限，继续导航到 {destination}')
                self._ui_abort_continue_logged = True
            return 'continue'
        # 大世界/出击菜单：已误进活动时用 BACK；仍在主界面则等弹窗或过场。
        keep = campaign_dests + (page_os,)
        if destination in keep:
            if not getattr(self, '_ui_abort_continue_logged', False):
                logger.info(f'[UI] MAIN_GOTO 上限，继续导航到 {destination}')
                self._ui_abort_continue_logged = True
            return 'continue'
        # 其余页面：继续会把 cap 在下次 ui_goto 清掉再点 2 下，直到重启
        # （2_brad / 4_nyan / 6_margaret 2026-09-19 03:12 MAIN_GOTO ×12）。
        # 作战档案在上面单独改走 goto_level，失败才放弃。
        logger.warning(f'[UI] MAIN_GOTO 上限，放弃导航到 {destination}')
        return 'abort'

    def is_in_main(self, offset=(30, 30), interval=0):
        """检测当前是否处于游戏主界面（支持传统主题与白色主题）。

        Args:
            offset (tuple): 匹配偏移量。
            interval (int | float): 检测间隔。

        Returns:
            bool: 是否在主界面。
        """
        return (self.ui_page_appear(page_main, offset=offset, interval=interval)
                or self.ui_page_appear(page_main_white, offset=offset, interval=interval))

    def _ui_home_chrome_visible(self, offset=(30, 30)):
        """主界面出击/编队按钮。右上角齿轮与 GOTO_MAIN_WHITE 同位置。"""
        return (
            self.appear(MAIN_GOTO_CAMPAIGN, offset=offset, interval=0)
            or self.appear(MAIN_GOTO_CAMPAIGN_WHITE, offset=offset, interval=0)
            or self.appear(MAIN_GOTO_FLEET, offset=offset, interval=0)
            or self.appear(MAIN_GOTO_FLEET_WHITE, offset=offset, interval=0)
        )

    def _ui_map_prep_visible(self, offset=(30, 30)):
        """LevelInfo / 舰队准备弹窗。HOME 无效，应点取消。"""
        return (
            self.appear(MAP_PREPARATION, offset=offset, interval=0)
            or self.appear(MAP_PREPARATION_HARD, offset=offset, interval=0)
            or self.appear(FLEET_PREPARATION, offset=(20, 50), interval=0)
            or self.appear(RAID_FLEET_PREPARATION, offset=offset, interval=0)
        )

    def _ui_page_from_home_chrome(self):
        if self.appear(MAIN_GOTO_CAMPAIGN_WHITE, offset=(30, 30), interval=0):
            return page_main_white
        return page_main

    def _ui_skip_home_click(self, button):
        """GOTO_MAIN 与主界面设置齿轮同位置。已在主界面时再点会打开设置。"""
        if button not in (GOTO_MAIN, GOTO_MAIN_WHITE):
            return False
        return self._ui_home_chrome_visible()

    def _ui_back_arrow_visible(self):
        return (
            self.appear(BACK_ARROW, offset=(30, 30), interval=0)
            or self.appear(BACK_ARROW_WHITE, offset=(30, 30), interval=0)
        )

    def _ui_back_arrow_capped(self):
        return getattr(self, '_ui_back_arrow_clicks', 0) >= 3

    def _ui_unknown_prefer_back(self):
        """设置页有 Back，HOME 六边形无效。Back 可见时不要点 HOME/齿轮。

        interval 必须与页面链接点击一致（5 秒）。2 秒会拆掉正在走的
        5 秒计时器，Back 就会每帧点一次。

        Returns:
            bool: True 表示应继续截图（已点 Back，或 Back 在 interval 内）。
        """
        if self._ui_back_arrow_capped():
            return False
        if self.appear_then_click(BACK_ARROW, offset=(30, 30), interval=5):
            self._ui_back_arrow_clicks = getattr(self, '_ui_back_arrow_clicks', 0) + 1
            return True
        if self.appear_then_click(BACK_ARROW_WHITE, offset=(30, 30), interval=5):
            self._ui_back_arrow_clicks = getattr(self, '_ui_back_arrow_clicks', 0) + 1
            return True
        if self._ui_back_arrow_visible():
            return True
        self._ui_back_arrow_clicks = 0
        self._ui_back_arrow_capped_logged = False
        return False

    def ui_main_appear_then_click(self, page, offset=(30, 30), interval=3):
        """检测主界面是否出现，若出现则点击前往目标页面的按钮。

        Args:
            page (Page): 目标页面。
            offset (tuple): 匹配偏移量。
            interval (int | float): 检测间隔。

        Returns:
            bool: 是否点击了按钮。
        """
        if self.appear(page_main.check_button, offset=offset, interval=interval):
            button = page_main.links[page]
            self.device.click(button)
            return True
        if self.appear(page_main_white.check_button, offset=(5, 5), interval=interval):
            button = page_main_white.links[page]
            self.device.click(button)
            return True
        return False

    def ensure_button_execute(self, button, offset=0):
        """检查按钮是否可见或可调用对象是否返回 True。

        Args:
            button (Button | callable): 按钮对象或检查回调。
            offset (int | tuple): 匹配偏移量。

        Returns:
            bool: 按钮是否出现或条件是否满足。
        """
        if isinstance(button, Button) and self.appear(button, offset=offset):
            return True
        elif callable(button) and button():
            return True
        else:
            return False

    def ui_click(
            self,
            click_button,
            check_button,
            appear_button=None,
            additional=None,
            confirm_wait=1,
            offset=(30, 30),
            retry_wait=10,
            skip_first_screenshot=False,
    ):
        """点击按钮并等待目标画面出现。

        Args:
            click_button (Button): 要点击的按钮。
            check_button (Button | callable): 用于确认页面已切换的检测按钮或回调。
            appear_button (Button | callable | None): 点击前需先出现的按钮，默认为 click_button。
            additional (callable | None): 额外的弹窗处理回调。
            confirm_wait (int | float): 确认等待时间（秒）。
            offset (bool | int | tuple): 匹配偏移量。
            retry_wait (int | float): 重试等待时间（秒）。
            skip_first_screenshot (bool): 是否跳过首次截图。
        """
        logger.hr("UI 点击")
        if appear_button is None:
            appear_button = click_button

        click_timer = Timer(retry_wait, count=retry_wait // 0.5)
        confirm_wait = confirm_wait if additional is not None else 0
        confirm_timer = Timer(confirm_wait, count=confirm_wait // 0.5).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if self.ui_process_check_button(check_button, offset=offset):
                if confirm_timer.reached():
                    break
            else:
                confirm_timer.reset()

            if click_timer.reached():
                if (isinstance(appear_button, Button) and self.appear(appear_button, offset=offset)) or (
                        callable(appear_button) and appear_button()
                ):
                    self.device.click(click_button)
                    click_timer.reset()
                    continue

            if additional is not None:
                if additional():
                    continue

    def ui_process_check_button(self, check_button, offset=(30, 30)):
        """处理检测按钮，支持 Button、callable、列表或元组等多种类型。

        Args:
            check_button (Button | callable | list[Button] | tuple[Button]): 检测按钮或回调。
            offset (tuple): 匹配偏移量。

        Returns:
            bool: 是否检测到目标。
        """
        if isinstance(check_button, Button):
            return self.appear(check_button, offset=offset)
        elif callable(check_button):
            return check_button()
        elif isinstance(check_button, (list, tuple)):
            for button in check_button:
                if self.appear(button, offset=offset):
                    return True
            return False
        else:
            return self.appear(check_button, offset=offset)

    def ui_get_current_page(self, skip_first_screenshot=True, recover_unknown=True):
        """获取当前所在的 UI 页面。

        Args:
            skip_first_screenshot (bool): 是否跳过首次截图。
            recover_unknown (bool): 未知页面时是否通过登录处理器重启游戏。

        Returns:
            Page: 当前页面对象。

        Raises:
            GameNotRunningError: 游戏进程未运行时抛出。
            GamePageUnknownError: 未知页面且禁止自动重启时抛出。
        """
        logger.info("UI 获取当前页面")
        if self._sweeney_bridge_enabled():
            page = self._try_sweeney_current_page()
            if page is not None:
                if skip_first_screenshot:
                    if not self.device.has_cached_image:
                        self.device.screenshot()
                else:
                    self.device.screenshot()
                if page.name == 'page_in_map':
                    page = self._reject_stale_bridge_in_map(page)
                page = self._reject_stale_bridge_campaign(page)
                page = self._reject_stale_bridge_main(page)
                if page is not None:
                    self.ui_current = page
                    return page
            logger.info("Sweeney bridge miss, screenshot fallback")

        @run_once
        def app_check():
            if not self.device.app_is_running():
                raise GameNotRunningError("[UI] 游戏未运行")

        @run_once
        def minicap_check():
            if self.config.Emulator_ControlMethod == "uiautomator2":
                self.device.uninstall_minicap()

        orientation_timer = Timer(5)

        timeout = Timer(10, count=20).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
                if not self.device.has_cached_image:
                    self.device.screenshot()
            else:
                self.device.screenshot()

            # 超时退出
            if timeout.reached():
                break

            # 已知页面检测
            for page in Page.iter_pages():
                if page.check_button is None:
                    continue
                if self.ui_page_appear(page=page):
                    logger.attr("UI", page.name)
                    self.ui_current = page
                    return page

            # 未知页面但可以处理
            logger.info("[UI] 未知UI页面")
            # 设置页没有 check_button。Back 关闭；HOME 六边形无效，且与齿轮同槽。
            # Back 在 interval 内时也要等，不能立刻改点 GOTO_MAIN。
            if self._ui_unknown_prefer_back():
                timeout.reset()
                continue
            # 主界面右上角齿轮与 GOTO_MAIN / GOTO_MAIN_WHITE 同位置。
            if self._ui_home_chrome_visible():
                page = self._ui_page_from_home_chrome()
                logger.attr("UI", page.name)
                logger.info("[UI] 未知页看到主界面 chrome，不点击 HOME（避免打开设置）")
                self.ui_current = page
                return page
            if self.appear_then_click(GOTO_MAIN, offset=(30, 30), interval=2):
                timeout.reset()
                continue
            if self.appear_then_click(GOTO_MAIN_WHITE, offset=(30, 30), interval=2):
                timeout.reset()
                continue
            if self.appear_then_click(RPG_HOME, offset=(30, 30), interval=2):
                timeout.reset()
                continue
            if self.ui_additional():
                timeout.reset()
                continue

            app_check()
            minicap_check()
            # 持续检查屏幕旋转
            if orientation_timer.reached():
                self.device.get_orientation()
                orientation_timer.reset()

        if not recover_unknown:
            logger.warning('[UI] 未知页面，已禁止自动重启游戏')
            raise GamePageUnknownError('[UI] 无法识别当前页面')

        # 未知页面，需要手动切换
        logger.warning("[UI] 未知UI页面")
        logger.attr("模拟器截图方式", self.config.Emulator_ScreenshotMethod)
        logger.attr("模拟器控制方式", self.config.Emulator_ControlMethod)
        logger.attr("服务器", self.config.SERVER)
        logger.warning("[UI] 不支持从当前页面启动")
        logger.warning(f"[UI] 支持的页面: {[str(page) for page in Page.iter_pages()]}")
        logger.warning('[UI] 支持的页面: 任何右上角有"HOME"按钮的页面')
        logger.critical("[UI] 杂鱼大叔~ 这么大个人了连主界面都进不去吗？噗噗，简直像个迷路的小宝宝❤")
        logger.critical("[UI] 听好了，笨蛋大叔：要么滚去正常的界面启动，"
                        "要么找个带『一键回港』按钮的界面再求我。你要是连这都找不到，建议直接把号删了止损。")
        logger.critical("[UI] 看懂了吗？废材？不要再浪费我的算力了，赶紧去改！")
        
        # 未知页面自动重启
        logger.warning("[UI] 检测到未知页面，尝试重启游戏")
        from module.handler.login import LoginHandler
        login_handler = LoginHandler(config=self.config, device=self.device)
        login_handler.device.app_stop()
        while login_handler.device.app_is_running():
            self.device.sleep(0.5)
        login_handler.device.app_start()
        login_handler.handle_app_login()
        return self.ui_get_current_page(skip_first_screenshot=True)

    def ui_goto(self, destination, get_ship=True, offset=(30, 30), skip_first_screenshot=True,
                recover_unknown=True):
        """导航到目标页面，使用 A* 寻路算法找到最短路径。

        Args:
            destination (Page): 目标页面。
            get_ship (bool): 是否处理获得舰船的弹窗。
            offset (tuple): 匹配偏移量。
            skip_first_screenshot (bool): 是否跳过首次截图。
            recover_unknown (bool): 导航超时时，未知页面是否允许重启游戏恢复。
        """
        # 初始化页面连接
        Page.init_connection(destination)
        self.interval_clear(list(Page.iter_check_buttons()))
        # 仍在主界面且已达上限：跨 ui_goto 保持，避免 Freebies 档案每轮再点出击。
        if getattr(self, '_ui_main_goto_capped', False) and self._ui_home_chrome_visible():
            pass
        else:
            self._ui_main_goto_campaign_clicks = 0
            self._ui_main_goto_capped = False
            self._ui_main_goto_capped_logged = False
        self._ui_campaign_menu_goto_clicks = 0
        self._ui_campaign_menu_goto_capped_logged = False
        self._ui_goto_level_pending = False
        self._ui_goto_level_pending_logged = False
        self._ui_goto_level_pending_frames = 0
        self._ui_goto_level_attempted = False
        self._ui_goto_archives_retry_after_cap = False
        self._ui_goto_scene_pending = False
        self._ui_goto_scene_pending_frames = 0
        self._ui_goto_scene_attempted = False
        self._ui_goto_scene_retry_after_cap = False
        self._ui_goto_scene_key = None
        self._ui_goto_scene_os_gave_up = False
        self._ui_goto_scene_world_timer = None
        self._ui_world_insave_timer = None
        self._ui_world_insave_sent = False
        self._ui_abort_continue_logged = False

        logger.hr(f"UI 导航到 {destination}")
        # 导航超时计时器：长时间无法识别页面时触发恢复
        nav_timeout = Timer(30, count=60).start()
        while 1:
            GOTO_MAIN.clear_offset()
            if skip_first_screenshot:
                skip_first_screenshot = False
                if self._ui_goto_needs_fresh_frame(destination):
                    self.device.screenshot()
            else:
                self.device.screenshot()

            self._ui_tick_bridge_nav_pending()

            if (
                not getattr(self, '_ui_goto_scene_attempted', False)
                and self._bridge_goto_scene_key(destination)
            ):
                self._ui_goto_scene_attempted = True
                if self._bridge_try_goto_scene(destination):
                    continue

            if (
                not getattr(self, '_ui_goto_level_attempted', False)
                and self._bridge_goto_level_want(destination)
            ):
                self._ui_goto_level_attempted = True
                if self._bridge_try_goto_level(destination):
                    continue

            bridged = None
            if self._sweeney_bridge_enabled():
                bridged = self._try_sweeney_current_page(verbose=False)
                if bridged is not None:
                    bridged = self._reject_stale_bridge_in_map(bridged)
                    bridged = self._reject_stale_bridge_campaign(bridged)
                    bridged = self._reject_stale_bridge_main(bridged)

            # 去出击菜单时已经进了活动/SP：不要 GOTO_MAIN 打回主界面
            if destination == page_campaign_menu and self._ui_overshot_campaign_menu():
                logger.info('[UI] 到达页面: page_campaign_menu (已在活动/SP)')
                if self.appear(EVENT_CHECK, offset=(30, 30), interval=0):
                    self.ui_current = page_event
                else:
                    self.ui_current = page_sp
                break

            # MAIN_GOTO 点满：活动/SP 目标算到达；每日/演习改走 goto_scene 或点出击菜单砖。
            if getattr(self, '_ui_main_goto_capped', False):
                action = self._ui_abort_main_goto_capped(destination)
                if action == 'arrived':
                    break
                if action == 'abort':
                    return

            # 到达目标页面
            if self.ui_page_appear(page=destination, offset=offset):
                if self._ui_goto_blocked_by_source(destination, offset=offset):
                    logger.info(f'[UI] 忽略 {destination} 检测 (仍在 {self.ui_current})')
                elif self._ui_goto_blocked_by_dest_chrome(destination):
                    logger.info(f'[UI] 忽略 {destination} 检测 (仍有活动/出击菜单 chrome)')
                elif self._ui_goto_blocked_by_bridge(destination, bridged):
                    # 像素已到目标、心跳仍滞后。作战档案应空等；
                    # 出击菜单误匹配 CAMPAIGN_CHECK 时必须点进章节列表。
                    logger.info(f'[UI] 忽略 {destination} 检测 (Sweeney bridge 仍为 {bridged})')
                    if self._ui_goto_wait_on_stale_bridge(destination, bridged):
                        continue
                else:
                    logger.info(f'[UI] 到达页面: {destination}')
                    self.ui_current = destination
                    break
            if self._ui_bridge_confirms_arrival(destination, bridged):
                logger.info(f'[UI] 到达页面: {destination} (Sweeney bridge)')
                self.ui_current = bridged
                break
            # 主界面新旧主题互为等价：目标为任一主界面时，
            # 检测到另一主题也视为到达
            if destination in (page_main, page_main_white) and self.is_in_main():
                logger.info(f'[UI] 到达页面: {destination}')
                break

            # 月切过场 90 秒仍未进大世界：离开导航，不要未知页重启。
            # os_init 会推迟任务。再点 HOME 只会把客户端打进认不出的画面。
            if (
                getattr(self, '_ui_goto_scene_os_gave_up', False)
                and destination is page_os
            ):
                logger.warning('[UI] 大世界过场未完成，放弃导航以免重启游戏')
                Page.clear_connection()
                return

            # 其他页面：按 A* 路径点击导航（与心跳 hop 共用按钮 interval）
            clicked = False
            for page in Page.iter_pages():
                if page.parent is None or page.check_button is None:
                    continue
                if self.appear(page.check_button, offset=offset, interval=5):
                    clicked = self._ui_click_toward_parent(page)
                    break
            if clicked:
                nav_timeout.reset()
                continue
            if getattr(self, '_ui_main_goto_capped', False):
                action = self._ui_abort_main_goto_capped(destination)
                if action == 'arrived':
                    break
                if action == 'abort':
                    return

            # 处理额外弹窗（先关自律寻敌菜单，再点出击入口）
            if self.ui_additional(get_ship=get_ship):
                nav_timeout.reset()
                continue
            # 月切预加载在进场景之前跑。停在主界面时不要点右上角：
            # 那是主界面，12 次 CLICK_SAFE_AREA 会在 36 秒重启（Brad 10:22 起，
            # 旧进程到 12:11 仍在点）。正常进场约 35 秒；45 秒仍见主界面就
            # 用 inSave 跳过卡死的重置回调或开场剧情。
            if self._ui_world_scene_pending():
                self.device.stuck_record_clear()
                insave_timer = getattr(self, '_ui_world_insave_timer', None)
                if (
                    insave_timer is not None
                    and not getattr(self, '_ui_world_insave_sent', False)
                    and insave_timer.reached()
                    and self._ui_home_chrome_visible()
                ):
                    self._ui_world_insave_sent = True
                    logger.info('[UI] 月切预加载停在主界面，跳过开场直接进入大世界')
                    self._bridge_goto_world_insave()
                nav_timeout.reset()
                continue

            # 出击菜单新布局不再显示 MAIN，CAMPAIGN_MENU_CHECK 会漏检。
            # 心跳仍是 page_campaign_menu 时，按链接点进章节列表。
            if self._ui_click_toward_parent(bridged, via_bridge=True):
                nav_timeout.reset()
                continue
            if getattr(self, '_ui_main_goto_capped', False):
                action = self._ui_abort_main_goto_capped(destination)
                if action == 'arrived':
                    break
                if action == 'abort':
                    return
            # 设置页无 check_button；心跳丢失时只能点 Back。
            on_settings = (
                getattr(bridged, 'name', None) == 'page_settings'
                or getattr(self.ui_current, 'name', None) == 'page_settings'
            )
            if on_settings:
                if not self._ui_back_arrow_visible():
                    self._ui_back_arrow_clicks = 0
                    self._ui_back_arrow_capped_logged = False
                elif self._ui_back_arrow_capped():
                    if not getattr(self, '_ui_back_arrow_capped_logged', False):
                        logger.warning('[UI] BACK_ARROW 连点无进展，放弃导航以免重启')
                        self._ui_back_arrow_capped_logged = True
                    return
                if self._ui_unknown_prefer_back():
                    nav_timeout.reset()
                    continue

            # 导航超时：当前页面无法识别，调用 ui_get_current_page 触发恢复
            if nav_timeout.reached():
                # WORLD 过场自己有 90 秒计时。30 秒导航超时会在剧情中途重启游戏。
                if self._ui_world_scene_pending():
                    nav_timeout.reset()
                    continue
                logger.warning(f'[UI] 导航到 {destination} 超时，尝试检测当前页面并恢复')
                Page.clear_connection()
                current = self.ui_get_current_page(
                    skip_first_screenshot=True,
                    recover_unknown=recover_unknown,
                )
                if current == destination:
                    logger.info(f'[UI] 到达页面: {destination}')
                    return
                # 主界面新旧主题互为等价
                if destination in (page_main, page_main_white) and self.is_in_main():
                    logger.info(f'[UI] 到达页面: {destination}')
                    return
                if self._ui_pages_equivalent(current, destination):
                    logger.info(f'[UI] 到达页面: {destination}')
                    self.ui_current = destination
                    return
                # 重新初始化导航。仍在主界面时不要清出击上限。
                Page.init_connection(destination)
                self.interval_clear(list(Page.iter_check_buttons()))
                if not (getattr(self, '_ui_main_goto_capped', False) and self._ui_home_chrome_visible()):
                    self._ui_main_goto_campaign_clicks = 0
                    self._ui_main_goto_capped = False
                    self._ui_main_goto_capped_logged = False
                self._ui_goto_scene_attempted = False
                self._ui_goto_level_attempted = False
                self._ui_campaign_menu_goto_clicks = 0
                self._ui_campaign_menu_goto_capped_logged = False
                nav_timeout.reset()

        # 重置页面连接
        Page.clear_connection()

    def ui_ensure(self, destination, skip_first_screenshot=True, recover_unknown=True):
        """确保当前在目标页面，若不在则导航过去。

        Args:
            destination (Page): 目标页面。
            skip_first_screenshot (bool): 是否跳过首次截图。
            recover_unknown (bool): 未知页面时是否允许重启游戏恢复。

        Returns:
            bool: 是否发生了页面切换。
        """
        logger.hr("UI 确保页面")
        self.ui_get_current_page(
            skip_first_screenshot=skip_first_screenshot,
            recover_unknown=recover_unknown,
        )
        if self.ui_current == destination:
            logger.info("[UI] 已在 %s" % destination)
            return False
        # 主界面新旧主题 / 军需与 NewShop 互为等价
        if self._ui_pages_equivalent(self.ui_current, destination):
            logger.info("[UI] 已在 %s (等效页面)" % destination)
            self.ui_current = destination
            return False
        else:
            logger.info("[UI] 导航到 %s" % destination)
            self.ui_goto(
                destination,
                skip_first_screenshot=True,
                recover_unknown=recover_unknown,
            )
            return True

    def ui_goto_main(self, recover_unknown=True):
        """导航到主页面。

        Pages:
            in: 任意页面
            out: page_main

        Args:
            recover_unknown (bool): 未知页面时是否允许重启游戏恢复。

        Returns:
            bool: 是否发生了页面切换。
        """
        return self.ui_ensure(destination=page_main, recover_unknown=recover_unknown)

    def ui_goto_campaign(self):
        """导航到主线战役页面。

        Pages:
            in: 任意页面
            out: page_campaign

        Returns:
            bool: 是否发生了页面切换。
        """
        return self.ui_ensure(destination=page_campaign)

    def ui_goto_event(self):
        """导航到活动战役页面。

        Pages:
            in: 任意页面
            out: page_event

        Returns:
            bool: 是否发生了页面切换。
        """
        return self.ui_ensure(destination=page_event)

    def ui_goto_sp(self):
        """导航到 SP 关卡页面。

        Pages:
            in: 任意页面
            out: page_sp

        Returns:
            bool: 是否发生了页面切换。
        """
        return self.ui_ensure(destination=page_sp)

    def ui_ensure_index(
            self,
            index,
            letter,
            next_button,
            prev_button,
            skip_first_screenshot=False,
            fast=True,
            interval=(0.2, 0.3),
    ):
        """确保翻页到指定索引位置，通过 OCR 识别当前页码并点击翻页按钮。

        Args:
            index (int): 目标索引。
            letter (Ocr | callable): OCR 识别器或回调函数。
            next_button (Button): 下一页按钮。
            prev_button (Button): 上一页按钮。
            skip_first_screenshot (bool): 是否跳过首次截图。
            fast (bool): 默认为 True。当索引不连续时设为 False。
            interval (tuple | int | float): 两次点击之间的间隔（秒）。
        """
        logger.hr("UI 确保索引")
        retry = Timer(1, count=2)
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if isinstance(letter, Ocr):
                current = letter.ocr(self.device.image)
            else:
                current = letter(self.device.image)

            logger.attr("当前索引", current)
            diff = index - current
            if diff == 0:
                break

            if retry.reached():
                button = next_button if diff > 0 else prev_button
                if fast:
                    self.device.multi_click(button, n=abs(diff), interval=interval)
                else:
                    self.device.click(button)
                retry.reset()

    def ui_back(self, check_button, appear_button=None, offset=(30, 30), retry_wait=10, skip_first_screenshot=False,
                additional=None):
        """点击返回按钮并等待目标画面出现。

        Args:
            check_button (Button | callable): 用于确认返回成功的检测按钮或回调。
            appear_button (Button | callable | None): 点击前需先出现的按钮。
            offset (tuple): 匹配偏移量。
            retry_wait (int | float): 重试等待秒数。
            skip_first_screenshot (bool): 是否跳过首次截图。
            additional (callable | None): 额外的弹窗处理回调。
        """
        return self.ui_click(
            click_button=BACK_ARROW,
            check_button=check_button,
            appear_button=appear_button,
            offset=offset,
            retry_wait=retry_wait,
            skip_first_screenshot=skip_first_screenshot,
            additional=additional,
        )

    _opsi_reset_fleet_preparation_click = 0

    def _sortie_chapter_active(self) -> bool:
        """出击中的关卡还在。这时主界面模板是误匹配，不能点。"""
        try:
            from module.alas_bridge.game_state import GameState
            state = GameState.from_config(self.config).read(max_age=8.0)
        except Exception:
            return False
        if not isinstance(state, dict):
            return False
        if str(state.get('scene_key') or '') != 'LEVEL':
            return False
        chapter = state.get('chapter')
        return isinstance(chapter, dict) and bool(chapter.get('active'))

    def ui_page_main_popups(self, get_ship=True):
        """处理主界面和奖励页面出现的弹窗。

        Args:
            get_ship (bool): 是否处理获得舰船的弹窗。

        Returns:
            bool: 是否处理了弹窗。
        """
        # 大舰队弹窗
        if self.handle_guild_popup_cancel():
            return True

        # 每日重置公告
        if self.appear_then_click(LOGIN_ANNOUNCE, offset=(30, 30), interval=3):
            return True
        if self.appear_then_click(LOGIN_ANNOUNCE_2, offset=(30, 30), interval=3):
            return True
        if self.appear_then_click(GET_ITEMS_1, offset=True, interval=3):
            return True
        if self.appear_then_click(GET_ITEMS_2, offset=True, interval=3):
            return True
        if get_ship and not self._sortie_chapter_active():
            if self.appear_then_click(GET_SHIP, offset=(20, 20), interval=5):
                return True
        if self.appear_then_click(LOGIN_RETURN_SIGN, offset=(30, 30), interval=3):
            return True
        if self.appear(EVENT_LIST_CHECK, offset=(30, 30), interval=5):
            logger.info(f'[UI-额外] {EVENT_LIST_CHECK} -> {GOTO_MAIN}')
            if self.appear_then_click(GOTO_MAIN, offset=(30, 30)):
                return True
        # 月卡即将到期
        if self.appear_then_click(MONTHLY_PASS_NOTICE, offset=(30, 30), interval=3):
            return True
        # 通行券即将到期且玩家有未领取的通行券奖励
        if self.appear_then_click(BATTLE_PASS_NOTICE, offset=(30, 30), interval=3):
            return True
        # 购买通行券的广告弹窗
        # 2024.12.19，主界面的 PURCHASE_POPUP 变为 BATTLE_PASS_NEW_SEASON
        # if self.appear_then_click(PURCHASE_POPUP, offset=(44, -77, 84, -37), interval=3):
        #     return True
        # 通行券新赛季通知弹窗
        if self.appear(BATTLE_PASS_NEW_SEASON, offset=(30, 30), interval=3):
            logger.info(f'[UI-额外] {BATTLE_PASS_NEW_SEASON} -> {BACK_ARROW}')
            self.device.click(BACK_ARROW)
            return True
        # 物品过期 offset=(37, 72)，皮肤过期 offset=(24, 68)
        if self.handle_popup_single(offset=(-6, 48, 54, 88), name='ITEM_EXPIRED'):
            return True
        # 邮箱已满弹窗
        if self.handle_popup_single_white():
            return True
        # 从确认点击误入的页面
        if self.appear(SHIPYARD_CHECK, offset=(30, 30), interval=5):
            logger.info(f'[UI-额外] {SHIPYARD_CHECK} -> {GOTO_MAIN}')
            if self.appear_then_click(GOTO_MAIN, offset=(30, 30)):
                return True
        if self.appear(META_CHECK, offset=(30, 30), interval=5):
            logger.info(f'[UI-额外] {META_CHECK} -> {GOTO_MAIN}')
            if self.appear_then_click(GOTO_MAIN, offset=(30, 30)):
                return True
        # 误点击
        if self.appear(PLAYER_CHECK, offset=(30, 30), interval=3):
            logger.info(f'[UI-额外] {PLAYER_CHECK} -> {GOTO_MAIN}')
            if self.appear_then_click(GOTO_MAIN, offset=(30, 30)):
                return True
            if self.appear_then_click(BACK_ARROW, offset=(30, 30)):
                return True

        return False

    def ui_page_os_popups(self):
        """处理大世界页面出现的弹窗。

        Returns:
            bool: 是否处理了弹窗。

        Raises:
            RequestHumanTakeover: 连续多次无法确认出击舰队时请求人工接管。
        """
        # 大世界重置流程：
        # - 大世界已重置，handle_story_skip() 点击确认
        # - RESET_TICKET_POPUP 弹窗
        # - 是否打开兑换商店？handle_popup_confirm() 点击确认
        # - EXCHANGE_CHECK 页面，点击返回箭头
        if self._opsi_reset_fleet_preparation_click >= 5:
            logger.critical("[UI] 无法确认大世界出击舰队，大叔你还点？是在玩打地鼠吗？真是逊毙了！")
            logger.critical("[UI] 哎呀呀，大叔是眼花了还是没长脑子？ #1: 建议检查您是否在大世界中设置了舰队")
            logger.critical("[UI] 笨——蛋——大叔！ #2: 建议检查您的舰队准入门槛（等级限制）")
            raise RequestHumanTakeover
        if self.appear_then_click(RESET_TICKET_POPUP, offset=(30, 30), interval=3):
            return True
        if self.appear_then_click(RESET_FLEET_PREPARATION, offset=(30, 30), interval=3):
            self._opsi_reset_fleet_preparation_click += 1
            self.interval_reset(FLEET_PREPARATION)
            self.interval_reset(RESET_TICKET_POPUP)
            return True
        if self.appear(EXCHANGE_CHECK, offset=(30, 30), interval=3):
            logger.info(f'[UI-额外] {EXCHANGE_CHECK} -> {GOTO_MAIN}')
            GOTO_MAIN.clear_offset()
            self.device.click(GOTO_MAIN)
            return True

        return False

    def ui_additional(self, get_ship=True):
        """处理 UI 切换过程中出现的各种弹窗。

        Args:
            get_ship (bool): 是否处理获得舰船的弹窗。

        Returns:
            bool: 是否处理了弹窗。
        """
        # 大世界页面弹窗
        # 包含 popup_confirm 变体，必须优先处理
        if self.ui_page_os_popups():
            return True

        # 科研弹窗、断线重连弹窗
        if self.handle_popup_confirm("UI_ADDITIONAL"):
            return True
        if self.handle_urgent_commission():
            return True

        # 主界面和奖励页面弹窗
        # 仅在非岛屿页面时处理，避免岛屿页面的 UI 元素被误检测为 GET_SHIP/GET_ITEMS
        # 例如岛屿管理界面的邮箱按钮与 GET_SHIP 检测区域 (1104,610,1110,630) 重叠
        if not (hasattr(self, 'ui_current') and self.ui_current and 'island' in self.ui_current.name):
            if self.ui_page_main_popups(get_ship=get_ship):
                return True

        # 剧情跳过
        if self.handle_story_skip():
            return True

        # 游戏提示
        # 度假村的活动委托提示
        # 2025.05.29 进入船坞时出现的皮肤功能提示
        if self.appear(GAME_TIPS, offset=(30, 30), interval=2):
            logger.info(f'[UI-额外] {GAME_TIPS} -> {GOTO_MAIN}')
            self.device.click(GOTO_MAIN)
            return True

        # 后宅弹窗
        if self.appear(DORM_INFO, offset=(30, 30), similarity=0.75, interval=3):
            self.device.click(DORM_INFO)
            return True
        if self.appear_then_click(DORM_FEED_CANCEL, offset=(30, 30), interval=3):
            return True
        if self.appear_then_click(DORM_TROPHY_CONFIRM, offset=(30, 30), interval=3):
            return True

        # 指挥喵弹窗
        if self.appear_then_click(MEOWFFICER_INFO, offset=(30, 30), interval=3):
            self.interval_reset(GET_SHIP)
            return True
        if self.appear(MEOWFFICER_BUY, offset=(30, 30), interval=3):
            logger.info(f'[UI-额外] {MEOWFFICER_BUY} -> {BACK_ARROW}')
            self.device.click(BACK_ARROW)
            self.interval_reset(GET_SHIP)
            return True

        # 战役准备界面：必须看到取消键再点。
        # 心跳 level.info_showing 会在商店/主界面/活动列表残留，盲点 MAP_PREPARATION_CANCEL
        # 与 GOTO_MAIN 对打直到 TooManyClick（2_brad / 5_booty 过夜 ShopFrequent）。
        # WORLD 月切过场会被准备模板误匹配，取消键落到 y<0，接着 HOME 打断进图。
        if self._ui_world_scene_pending():
            pass
        elif self._ui_map_prep_visible():
            if not getattr(self, '_ui_map_prep_cancel_capped', False):
                if self.appear_then_click(MAP_PREPARATION_CANCEL, offset=(30, 30), interval=3):
                    n = getattr(self, '_ui_map_prep_cancel_clicks', 0) + 1
                    self._ui_map_prep_cancel_clicks = n
                    if n >= 3:
                        self._ui_map_prep_cancel_capped = True
                        logger.warning('[UI] MAP_PREPARATION_CANCEL 连点无进展，停止点击')
                    return True
            # 取消键无效时不要一直占着 ui_goto，HOME 才能走。
        else:
            self._ui_map_prep_cancel_capped = False
            self._ui_map_prep_cancel_clicks = 0
        if self.appear_then_click(AUTO_SEARCH_MENU_EXIT, offset=(200, 30), interval=3):
            return True
        if self.appear_then_click(AUTO_SEARCH_REWARD, offset=(50, 50), interval=3):
            return True
        if self.appear(WITHDRAW, offset=(30, 30), interval=3):
            # 此处等待是为了处理 2022-04-07 游戏更新后的客户端 bug
            # 复现步骤（100% 成功）：
            # - 进入任意关卡，如 12-4
            # - 停止并重启游戏
            # - 运行 Alas 的 Main 任务
            # - Alas 切换到 page_campaign 并从已有关卡撤退
            # - 游戏客户端在 page_campaign W12 界面卡死，点击屏幕无响应
            # - 再次重启游戏客户端可修复此问题
            logger.info("[UI-额外] 发现撤退按钮，等待地图加载以防止游戏客户端bug")
            self.device.sleep(2)
            self.device.screenshot()
            if self.appear_then_click(WITHDRAW, offset=(30, 30)):
                self.interval_reset(WITHDRAW)
                return True
            else:
                logger.warning("[UI-额外] 撤退按钮已不存在")
                self.interval_reset(WITHDRAW)

        # 登录画面不是普通弹窗。连点 LOGIN_CHECK 会打满点击上限并重启游戏
        # （Asami Commission / Margaret Research，2026-09-24）。点几次仍在
        # 登录页就停，交给调度器推迟已到期任务。
        if self.appear(LOGIN_CHECK, offset=(30, 30)):
            if self._sortie_chapter_active():
                logger.info('[UI] 出击中忽略 LOGIN_CHECK，避免把主界面点到海图上')
            else:
                n = getattr(self, '_ui_login_check_clicks', 0)
                if n >= 3:
                    logger.warning('[UI] 登录键连点仍未离开登录页')
                    raise GameTooManyClickError(
                        '[设备-点击] 按钮点击次数过多: LOGIN_CHECK'
                    )
                if self.appear_then_click(LOGIN_CHECK, offset=(30, 30), interval=3):
                    self._ui_login_check_clicks = n + 1
                    return True
        else:
            self._ui_login_check_clicks = 0
        if self.appear_then_click(MAINTENANCE_ANNOUNCE, offset=(30, 30), interval=3):
            return True

        # 误点击
        if self.appear(EXERCISE_PREPARATION, interval=3):
            logger.info(f'[UI-额外] {EXERCISE_PREPARATION} -> {GOTO_MAIN}')
            self.device.click(GOTO_MAIN)
            return True

        # RPG 活动 (raid_20240328)
        # if self.appear_then_click(RPG_STATUS_POPUP, offset=(30, 30), interval=3):
        #     return True
        # 医院活动 (20250327)
        # if self.appear_then_click(HOSIPITAL_CLUE_CHECK, offset=(20, 20), interval=2):
        #     return True
        # if self.appear_then_click(HOSPITAL_BATTLE_EXIT, offset=(20, 20), interval=2):
        #     return True
        # 霓虹都市 (coalition_20250626)
        # 时尚联动 (coalition_20260122) 复用 NEONCITY
        # if self.appear(NEONCITY_FLEET_PREPARATION, offset=(20, 20), interval=3):
        #     logger.info(f'{NEONCITY_FLEET_PREPARATION} -> {NEONCITY_PREPARATION_EXIT}')
        #     self.device.click(NEONCITY_PREPARATION_EXIT)
        #     return True
        # DATE A LANE (coalition_20251120)
        # if self.appear_then_click(DAL_DIFFICULTY_EXIT, offset=(20, 20), interval=3):
        #     return True

        # 空闲页面
        if self.handle_idle_page():
            return True
        # 白色主题 UI 切换，无偏移量仅颜色匹配
        if self.appear(MAIN_GOTO_MEMORIES_WHITE, interval=3):
            logger.info(f'[UI-额外] {MAIN_GOTO_MEMORIES_WHITE} -> {MAIN_TAB_SWITCH_WHITE}')
            self.device.click(MAIN_TAB_SWITCH_WHITE)
            return True

        return False

    def handle_idle_page(self):
        """
        处理空闲页面（如待机动画），点击回到主界面。

        Returns:
            bool: 是否处理了空闲页面。
        """
        timer = self.get_interval_timer(IDLE, interval=3)
        if not timer.reached():
            return False
        if IDLE.match_luma(self.device.image, offset=(5, 5)):
            logger.info(f'[UI-额外] {IDLE} -> {REWARD_GOTO_MAIN}')
            self.device.click(REWARD_GOTO_MAIN)
            timer.reset()
            return True
        if IDLE_2.match_luma(self.device.image, offset=(5, 5)):
            logger.info(f'[UI-额外] {IDLE_2} -> {REWARD_GOTO_MAIN}')
            self.device.click(REWARD_GOTO_MAIN)
            timer.reset()
            return True
        if IDLE_3.match_luma(self.device.image, offset=(5, 5)):
            logger.info(f'[UI-额外] {IDLE_3} -> {REWARD_GOTO_MAIN}')
            self.device.click(REWARD_GOTO_MAIN)
            timer.reset()
            return True
        return False

    def ui_button_interval_reset(self, button):
        """
        重置某些按钮的检测间隔，防止误点击。

        Args:
            button (Button): 刚点击过的按钮。
        """
        if button == MEOWFFICER_GOTO_DORMMENU:
            self.interval_reset(GET_SHIP)
        if button == DORMMENU_GOTO_DORM:
            self.interval_reset(GET_SHIP)
        if button == DORMMENU_GOTO_MEOWFFICER:
            self.interval_reset(GET_SHIP)
        for switch_button in page_main.links.values():
            if button == switch_button:
                self.interval_reset(GET_SHIP)
        if button == MAIN_GOTO_REWARD:
            self.interval_reset(GET_SHIP)
            # 柔和主题的委托按钮每次点击都重播侧栏展开。新旧主题入口都会
            # 匹配左侧同一条，0.4 秒内再点一次会把展开动画打回去
            # （Brad / nyan / booty 2026-10-01 09:02）。间隔必须与点击计时器
            # 同为 5 秒，否则 renew 会换成未启动的计时器，第二下立刻又能点。
            self.interval_reset(MAIN_GOTO_REWARD_WHITE, interval=5)
        elif button == MAIN_GOTO_REWARD_WHITE:
            self.interval_reset(GET_SHIP)
            self.interval_reset(MAIN_GOTO_REWARD, interval=5)
        if button == REWARD_GOTO_TACTICAL:
            self.interval_reset(REWARD_GOTO_TACTICAL_WHITE)
        if button == REWARD_GOTO_TACTICAL_WHITE:
            self.interval_reset(REWARD_GOTO_TACTICAL)
        if button in [MAIN_GOTO_CAMPAIGN, MAIN_GOTO_CAMPAIGN_WHITE]:
            self.interval_reset(GET_SHIP)
            # 信浓活动与突袭有相同的标题
            self.interval_reset(RAID_CHECK)
        if button == SHOP_GOTO_SUPPLY_PACK:
            self.interval_reset(EXCHANGE_CHECK)
        if button in [RPG_GOTO_STAGE, RPG_GOTO_STORY, RPG_LEAVE_CITY]:
            self.interval_timer[GET_SHIP.name] = Timer(5).reset()
