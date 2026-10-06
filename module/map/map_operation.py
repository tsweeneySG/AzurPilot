"""地图操作与战斗准备。

本模块提供战役地图中的基础操作，包括：
- 舰队切换与准备（fleet_set、fleet_preparation）
- 进入战役关卡的完整流程（enter_map）
- 地图难度模式切换（handle_map_mode_switch）
- 地图准备阶段处理（handle_map_preparation）
- 撤退操作（withdraw）
- 猫猫攻击跳过（handle_map_cat_attack）
- 舰队顺序反转处理（handle_fleet_reverse）

``MapOperation`` 继承了 ``MysteryHandler``（神秘格子处理）、
``FleetPreparation``（舰队准备）、``Retirement``（退役处理）
和 ``FastForwardHandler``（快进处理），组合了进入地图所需的全部子流程。
"""

from datetime import datetime, timedelta

import cv2

from module.base.timer import Timer
from module.config.time_source import now as current_time
from module.exception import CampaignEnd, RequestHumanTakeover, ScriptEnd
from module.handler.fast_forward import FastForwardHandler
from module.handler.mystery import MysteryHandler
from module.logger import logger
from module.map.assets import *
from module.map.map_fleet_preparation import FleetPreparation
from module.notify import handle_notify
from module.retire.retirement import Retirement
from module.ui.assets import BACK_ARROW, DAILY_CHECK

# 读不到作战委托结束时间时的兜底重试间隔（分钟）
HANDOVER_CONFLICT_RETRY_MINUTES = 15


class MapOperation(MysteryHandler, FleetPreparation, Retirement, FastForwardHandler):
    """地图操作处理器。

    封装战役地图中的所有基础操作，包括进入关卡、舰队切换、
    撤退、模式切换等。组合了神秘格子、舰队准备、退役和快进处理。

    Attributes:
        map_cat_attack_timer (Timer): 猫猫攻击检测的节流计时器。
        map_clear_percentage_prev (float): 上一次记录的地图通关百分比。
        map_clear_percentage_timer (Timer): 通关百分比变化检测计时器。
        fleet_show_index (int): 屏幕上显示的舰队编号（1 或 2）。
        fleet_current_index (int): 当前逻辑舰队编号（考虑舰队顺序反转）。
    """

    map_cat_attack_timer = Timer(2)
    map_clear_percentage_prev = -1
    map_clear_percentage_timer = Timer(0.3, count=1)

    # 屏幕上显示的舰队编号。
    fleet_show_index = 1
    # 注意：这与 get_fleet_current_index() 不同。
    # 在 fleet_current_index 中，1 表示道中队，2 表示 Boss 队。
    fleet_current_index = 1

    def get_fleet_show_index(self):
        """获取屏幕上当前显示的舰队编号。

        Returns:
            int: 屏幕显示的舰队编号（1 或 2）。

        Pages:
            in: in_map
        """
        if self.appear(FLEET_NUM_1, offset=(20, 20)):
            self.fleet_show_index = 1
            return 1
        elif self.appear(FLEET_NUM_2, offset=(20, 20)):
            self.fleet_show_index = 2
            return 2
        else:
            logger.warning('[地图-操作] 未知的舰队当前索引，默认使用1')
            self.fleet_show_index = 1
            return 1

    def get_fleet_current_index(self):
        """获取当前逻辑舰队编号（考虑舰队顺序反转）。

        Returns:
            int: 逻辑舰队编号（1 为道中队，2 为 Boss 队）。
        """
        if self.fleets_reversed:
            self.fleet_current_index = 3 - self.fleet_show_index
            return self.fleet_current_index
        else:
            self.fleet_current_index = self.fleet_show_index
            return self.fleet_current_index

    def fleet_set(self, index=None, skip_first_screenshot=True):
        """切换到目标逻辑舰队。

        Args:
            index (int, optional): 目标逻辑舰队编号（1 或 2）。默认为 None。
            skip_first_screenshot (bool, optional): 是否跳过首次截图。默认为 True。

        Returns:
            bool: 是否进行了舰队切换。
        """
        logger.info(f'[地图-操作] 舰队设置为 {index}')
        timeout = Timer(5, count=10).start()
        count = 0
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if timeout.reached():
                logger.warning('[地图-操作] 舰队设置超时，假设当前舰队正确')
                break

            if self.handle_story_skip():
                timeout.reset()
                continue
            if self.handle_in_stage():
                timeout.reset()
                continue

            self.get_fleet_show_index()
            self.get_fleet_current_index()
            logger.info(f'[地图-操作] 舰队: {self.fleet_show_index}, 当前舰队索引: {self.fleet_current_index}')
            if self.fleet_current_index == index:
                break
            elif self.appear_then_click(SWITCH_OVER):
                count += 1
                self.device.sleep((1, 1.5))
                timeout.reset()
                continue
            else:
                logger.warning('[地图-操作] 未找到切换按钮')
                continue

        return count > 0

    def handover_conflict_appear(self):
        """当前画面是不是作战委托的阻止弹窗。

        两种弹窗都算：
        - 委托的不是当前关卡：游戏通用的「信息 INFORMATION」弹窗，右侧是「查看委托」
        - 委托的正是当前关卡：直接弹出「作战委托 INFORM」弹窗，底部是「终止作战」
          或「领取奖励」

        Returns:
            bool: 屏幕上有作战委托阻止弹窗返回 True。
        """
        return (
            self.appear(HANDOVER_CONFLICT_CHECK, offset=(20, 20))
            or self.appear(HANDOVER_STOP_CHECK, offset=(20, 20))
            or self.appear(HANDOVER_PASS_CLICK, offset=(20, 20))
        )

    def handle_handover_conflict(self):
        """处理作战委托进行中的阻止弹窗。

        作战委托进行时，出击类任务点关卡节点会被上面 handover_conflict_appear()
        列的两种弹窗拦下。两个弹窗都不能用 handle_popup_cancel()：它要求画面上
        同时有通用弹窗的「确定」和「取消」，而「信息」弹窗右侧是「查看委托」
        （位置正好压在通用「确定」上），通用素材在这里一个都命中不了，只会让
        截图循环空转；「作战委托 INFORM」弹窗的按钮更是完全另一套。必须用弹窗
        各自的专用素材点击。

        关掉弹窗后把当前任务推迟到作战委托结束之后：委托期间出击类任务都无法
        进行，但委托是有明确结束时间的，不必整天不刷。委托是脚本自己开的
        （任务开关为开）时额外推送一次「功能冲突」提示。

        Pages:
            in: 关卡页（阻止弹窗）
            out: 关卡页

        Raises:
            TaskEnd: 作战委托进行中无法出击，当前任务到此为止。
        """
        if not self.handover_conflict_appear():
            return

        logger.hr('功能冲突: 作战委托进行中', level=2)

        # 无论委托是不是脚本自己开的都要先关掉弹窗，
        # 否则脚本会卡在这个页面上，之后所有页面识别都会失败。
        closed = self.handover_close_conflict()
        target = self.handover_conflict_delay()

        if self.config.is_task_enabled('OperationHandover'):
            handle_notify(
                self.config.Error_OnePushConfig,
                title=f'AzurPilot <{self.config.config_name}> 功能冲突',
                content=f'<{self.config.config_name}> 作战委托未结束，'
                        f'{self.config.task.command} 无法出击，已推迟到 {target}',
            )
        else:
            logger.warning('[功能冲突] 作战委托任务未启用，'
                           '当前委托可能是手动开启的，本次不推送通知')

        if not closed:
            logger.warning('[功能冲突] 阻止弹窗关闭失败，当前页面可能无法正常操作')

        self.config.task_stop('作战委托进行中，无法出击')

    def handover_conflict_delay(self):
        """把当前任务推迟到作战委托结束之后。

        作战委托开委托时会把结束时间记在 OperationHandover.CommissionEnd，
        优先用它——作战委托任务自己的 NextRun 不一定是委托结束时间（委托次数为 0
        时它只是下一次触发时刻，可能在一周以后）。两个都读不到或者都已经过期时，
        改为 HANDOVER_CONFLICT_RETRY_MINUTES 分钟后再试，避免把任务排到过去。

        Returns:
            datetime.datetime: 实际推迟到的时间点。
        """
        now = current_time()
        commission_end = self.config.cross_get(
            keys=['OperationHandover', 'OperationHandover', 'CommissionEnd'], default=None)
        next_run = self.config.cross_get(
            keys=['OperationHandover', 'Scheduler', 'NextRun'], default=None)
        candidates = [
            t for t in (commission_end, next_run)
            if isinstance(t, datetime) and t > now
        ]

        if candidates:
            end = min(candidates)
            target = (end + timedelta(minutes=1)).replace(microsecond=0)
            logger.info(f'[功能冲突] 作战委托预计 {end} 结束，推迟到 {target}')
        else:
            target = (now + timedelta(minutes=HANDOVER_CONFLICT_RETRY_MINUTES)).replace(microsecond=0)
            logger.warning(f'[功能冲突] 读不到作战委托的结束时间'
                           f'（{commission_end} / {next_run}），'
                           f'{HANDOVER_CONFLICT_RETRY_MINUTES} 分钟后再试')

        self.config.task_delay(target=target)
        return target

    def handover_close_conflict(self):
        """关闭作战委托阻止弹窗。

        两种弹窗都要关：
        - 「信息 INFORMATION」弹窗：点左下角「取消」
        - 「作战委托 INFORM」弹窗：点右上角红叉。底部那颗按钮不能点，
          「终止作战」会把委托停掉，「领取奖励」会提前领奖。

        Pages:
            in: 关卡页（阻止弹窗）
            out: 关卡页

        Returns:
            bool: 弹窗已关闭返回 True，超时仍未关闭返回 False。
        """
        # 30 秒的静态画面检测会抛 GameStuckError，这里的超时要更短，
        # 保证失败时还能继续走完推迟任务的流程。
        timeout = Timer(10).start()
        while 1:
            self.device.screenshot()

            if not self.handover_conflict_appear():
                logger.info('[功能冲突] 已关闭作战委托提示弹窗')
                return True

            if timeout.reached():
                return False

            if self.appear_then_click(HANDOVER_CONFLICT_CANCEL, offset=(20, 20), interval=1):
                continue
            if self.appear_then_click(HANDOVER_DIALOG_CLOSE, offset=(20, 20), interval=1):
                continue

    def enter_map(self, button, mode='normal', skip_first_screenshot=True):
        """进入战役关卡。

        包含关卡点击、准备页面检测、自律与通关模式配置、舰队切换、剧情跳过等。

        Args:
            button (Button): 要进入的战役按钮。
            mode (str, optional): 难度模式，'normal' 或 'hard'。默认为 'normal'。
            skip_first_screenshot (bool, optional): 是否跳过首次截图。默认为 True。

        Returns:
            bool: 成功进入地图返回 True，若已在地图中则返回 False。

        Raises:
            RequestHumanTakeover: 点击次数过多或未满足限制时抛出，请求人工接管。
            ScriptEnd: 达成关卡停止条件时抛出。
        """
        logger.hr('进入地图')
        campaign_timer = Timer(5)
        map_timer = Timer(5)
        fleet_timer = Timer(5)
        campaign_click = 0
        map_click = 0
        fleet_click = 0
        checked_in_map = False
        self._enter_map_saw_load_bar = False
        self._enter_map_bar_this_frame = False
        self._enter_map_load_bar_finished = False
        self._enter_map_combat_started = False
        self._auto_search_continue_timer = None
        # chapter_track 已发出但海图/自律一直不出现时，不要空等到 GameStuck 重启。
        self._track_enter_timer = None
        self.stage_entrance = button
        self.map_clear_percentage_prev = -1
        self.map_clear_percentage_timer.reset()

        with self.stat.new(
                genre=self.config.campaign_name, method=self.config.DropRecord_CombatRecord
        ) as drop:
            while 1:
                if skip_first_screenshot:
                    skip_first_screenshot = False
                else:
                    self.device.screenshot()

                # 检查错误
                if campaign_click > 5:
                    logger.warning(f"[Map] 无法进入 {button}，对 {button} 的点击次数过多")
                    logger.warning("[Map] 可能原因 #1: 关卡未解锁、章节页未切完、或仍有覆盖层。")
                    logger.warning("[Map] 推迟任务而非重启模拟器")
                    raise ScriptEnd('Cannot enter map')
                if fleet_click > 5:
                    logger.critical(f"[Map] 无法进入 {button}，对 FLEET_PREPARATION 的点击次数过多")
                    logger.critical("[Map] 可能原因 #1: "
                                    "您的舰队尚未满足该关卡的属性限制。")
                    logger.critical("[Map] 可能原因 #2: "
                                    "该关卡每天只能刷一次，"
                                    "但这是您第二次进入")
                    raise RequestHumanTakeover

                # 已在地图中
                if not checked_in_map and self.is_in_map():
                    logger.info('[地图-操作] 已在地图中，跳过进入地图')
                    return False
                else:
                    checked_in_map = True

                # 意外点击处理。准备页上 DAILY_CHECK 会误匹配，BACK 关掉 LevelInfo
                # 后 chapter_track 变 not_in_prep（3_asami Hard 14-4 2026-09-21 11:24）。
                # 进图第一帧模板可能还没跟上，心跳 info_showing 仍为真
                # （4_nyan / 6_margaret Hard 14-4 2026-10-05 03:15，BACK 后空等至 GameStuck）。
                if self.appear(DAILY_CHECK, offset=(20, 20), interval=3) \
                        and not self._enter_map_level_info_open():
                    logger.info(f'{DAILY_CHECK} -> {BACK_ARROW}')
                    self.device.click(BACK_ARROW)
                    continue

                # 作战委托进行中，出击会被游戏阻止
                self.handle_handover_conflict()

                # 地图准备
                if map_timer.reached() and self.handle_map_mode_switch(mode):
                    prep_button = self.handle_map_preparation()
                else:
                    prep_button = None
                # 刚点过自律继续：截图残留准备页。chapter_track 会 not_in_prep，
                # 推迟 Main 后空闲回港，未知页重启（5_booty / 6_margaret / 1_67，2026-10-04～05）。
                if prep_button and self._auto_search_continue_blocks_prep():
                    logger.info('[地图-操作] 自律继续后忽略残留准备页，等待进图')
                    prep_button = None
                if prep_button:
                    self.map_get_info()
                    self.handle_map_walk_speedup()
                    self.handle_fast_forward()
                    self.handle_auto_search()
                    if self.triggered_map_stop():
                        self.enter_map_cancel()
                        self.handle_map_stop()
                        raise ScriptEnd(f'Reach condition: {self.config.StopCondition_MapAchievement}')
                    if self._bridge_try_chapter_track():
                        map_click += 1
                        map_timer.reset()
                        campaign_timer.reset()
                        if self._track_enter_timer is None:
                            self._track_enter_timer = Timer(45).start()
                        continue
                    if self._level_prep_from_bridge() == 'fleet':
                        map_timer.reset()
                        continue
                    self.device.click(prep_button)
                    map_click += 1
                    map_timer.reset()
                    campaign_timer.reset()
                    continue

                # 舰队准备
                if fleet_timer.reached() and self.appear(FLEET_PREPARATION, offset=(20, 50)):
                    if mode == 'normal' or mode == 'hard':
                        self.handle_2x_book_setting(mode='prep')
                        self.fleet_preparation()
                        self.handle_auto_submarine_call_disable()
                        self.handle_auto_search_setting()
                        self.map_fleet_checked = True
                    self.device.click(FLEET_PREPARATION)
                    fleet_click += 1
                    fleet_timer.reset()
                    campaign_timer.reset()
                    continue

                # 自动搜索继续
                if self.handle_auto_search_continue(drop=drop):
                    campaign_timer.reset()
                    continue

                # 退役
                if self.handle_retirement():
                    continue

                # 使用数据密钥
                if self.handle_use_data_key():
                    continue

                # 16-1/16-2 潜艇支援弹窗
                if self.handle_submarine_support_popup():
                    continue

                # 情绪处理
                if self.handle_combat_low_emotion():
                    continue

                # 紧急委托
                if self.handle_urgent_commission(drop=drop):
                    continue

                # 2倍经验书弹窗
                if self.handle_2x_book_popup():
                    continue

                if self.handle_submarine_cost_popup():
                    continue

                # 剧情跳过
                if self.handle_story_skip():
                    campaign_timer.reset()
                    continue

                # 进入战役。加载条出现后不要再点关卡入口，否则 JP 暂停键误判
                # 时会连点 16-4 直到 RequestHumanTakeover。
                if not getattr(self, '_enter_map_saw_load_bar', False):
                    # 自律继续后的等待窗口里不要再点关卡入口。
                    if campaign_timer.reached() \
                            and not self._auto_search_continue_blocks_prep() \
                            and self.appear_then_click(button):
                        campaign_click += 1
                        campaign_timer.reset()
                        continue

                # 档案 T6：chapter_track 返回 sent 后画面停住，16-4 则 1 秒内
                # 出现自律。空等会 GameStuck 并重启客户端（6ix7even 74 次、
                # Brad 32 次，2026-09-27 02:38–09:47）。
                track_timer = self._track_enter_timer
                if track_timer is not None and track_timer.reached():
                    entered = (
                        self.is_in_map()
                        or self.is_auto_search_running()
                        or self._enter_map_saw_load_bar
                        or self._enter_map_combat_started
                    )
                    if not entered:
                        logger.warning('[地图-操作] chapter_track 已发出但未进入地图')
                        raise ScriptEnd('chapter_track did not enter map')
                    self._track_enter_timer = None

                # 结束判断
                if self.map_is_auto_search:
                    if self.is_auto_search_running():
                        logger.info('[地图-操作] 自动搜索运行中出现')
                        break
                    if self._enter_map_combat_loading_means_entered():
                        logger.warning('[地图-操作] 进入地图时战斗加载画面出现')
                        break
                else:
                    if self._enter_map_combat_loading_means_entered():
                        logger.warning('[地图-操作] 进入地图时战斗已开始')
                        break
                    if getattr(self, '_enter_map_bar_this_frame', False):
                        # 第一段进图加载条与战斗加载共用模板（常见 2%）。
                        # 此时不要结束 enter_map。第二段加载条由
                        # _enter_map_combat_loading_means_entered 判为战斗。
                        continue
                    if not getattr(self, '_enter_map_saw_load_bar', False):
                        if hasattr(self, 'is_combat_loading') and self.is_combat_loading():
                            continue
                    if self.handle_in_map_with_enemy_searching():
                        # self.handle_map_after_combat_story()
                        break

        return True

    def _enter_map_heartbeat_battle_busy(self):
        """Sweeney 心跳是否已在战斗中。比 JP 暂停键颜色可靠。"""
        config = getattr(self, 'config', None)
        if config is None:
            return False
        try:
            from module.alas_bridge.actions import battle_state_from_heartbeat
            state = battle_state_from_heartbeat(config, max_age=3.0)
        except Exception:
            return False
        return state in ('BATTLE_FIGHT', 'BATTLE_OPENING', 'BATTLE_REPORT')

    def _enter_map_pause_is_template_reliable(self):
        """CN/EN 暂停键走 luma 模板；JP/TW 颜色回退会把进图画面当成战斗。"""
        config = getattr(self, 'config', None)
        server = getattr(config, 'SERVER', None) if config is not None else None
        return server in ('cn', 'en')

    def _map_init_should_finish_combat(self):
        """map_init 扫描前：若已在战斗/战斗加载中，先 combat()。

        不用 JP 暂停键颜色。16-1 潜艇支援打完后已在地图上则返回 False。
        """
        if hasattr(self, 'combat_appear') and self.combat_appear():
            return True
        if hasattr(self, 'is_combat_loading_bar') and self.is_combat_loading_bar():
            return True
        return self._enter_map_heartbeat_battle_busy()

    def _enter_map_combat_loading_means_entered(self):
        """进图加载条会被当成战斗加载。自动搜索可直接开打。

        手动图：第一段加载条走完后 JP 暂停键颜色会误判“战斗已开始”。
        见过加载条后等到 in_map，不要用暂停键回退结束 enter_map。
        但加载走完后又出现加载条、心跳已在战斗、或 CN/EN 暂停键模板
        命中时，说明已经开打，应结束 enter_map 交给 combat()。

        Returns:
            bool: True 表示 enter_map 应结束，交给后续战斗或自动搜索。
        """
        bar = hasattr(self, 'is_combat_loading_bar') and self.is_combat_loading_bar()
        self._enter_map_bar_this_frame = bar
        if bar:
            if getattr(self, '_enter_map_load_bar_finished', False):
                self._enter_map_combat_started = True
                return True
            self._enter_map_saw_load_bar = True
            loading = True
        elif getattr(self, '_enter_map_saw_load_bar', False):
            # 加载条走完后 JP 暂停键颜色会每帧打 “未检测到加载条”。
            self._enter_map_load_bar_finished = True
            loading = False
        else:
            loading = hasattr(self, 'is_combat_loading') and self.is_combat_loading()
        if self.map_is_auto_search:
            return bool(loading)
        if loading:
            if getattr(self, '_enter_map_saw_load_bar', False):
                return False
            if hasattr(self, 'is_combat_executing') and self.is_combat_executing():
                self._enter_map_combat_started = True
                return True
            return False
        if getattr(self, '_enter_map_saw_load_bar', False):
            if self._enter_map_heartbeat_battle_busy():
                self._enter_map_combat_started = True
                return True
            if self._enter_map_pause_is_template_reliable():
                if hasattr(self, 'is_combat_executing') and self.is_combat_executing():
                    self._enter_map_combat_started = True
                    return True
        return False

    def enter_map_cancel(self, skip_first_screenshot=True):
        """取消进入地图，从地图准备界面退回关卡选择界面。

        Args:
            skip_first_screenshot (bool, optional): 是否跳过首次截图。默认为 True。

        Returns:
            bool: 始终返回 True。
        """
        logger.hr('取消进入地图')
        clicks = 0
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            # 结束判断
            if self.is_in_stage():
                break

            prep = self.appear(MAP_PREPARATION, offset=(20, 20), interval=2) \
                or self.appear(MAP_PREPARATION_HARD, offset=(20, 20), interval=2) \
                or self.appear(FLEET_PREPARATION, offset=(20, 50), interval=2)
            if prep:
                # offset 模板匹配会把取消键的点击区域留在 y<=0，点不中准备界面，
                # 直到 GameTooManyClick（3_asami Event2 2026-09-23 07:29）。
                if clicks >= 3:
                    logger.warning('[地图] MAP_PREPARATION_CANCEL 连点无进展，放弃进入')
                    self.device.click_record_clear()
                    raise CampaignEnd('MAP_PREPARATION_CANCEL gave up')
                MAP_PREPARATION_CANCEL.clear_offset()
                self.device.click(MAP_PREPARATION_CANCEL)
                clicks += 1
                continue

        return True

    def handle_map_mode_switch(self, mode):
        """处理地图难度模式切换（普通/困难）。

        Args:
            mode (str): 目标模式，'normal' 或 'hard'。

        Returns:
            bool: 地图模式是否满足要求。若地图无模式切换则始终返回 True。
        """
        if not self.config.MAP_HAS_MODE_SWITCH:
            return True

        if mode == 'normal':
            if self.match_template_color(MAP_MODE_SWITCH_NORMAL, offset=(20, 20)):
                logger.attr('地图模式', '普通')
                return True
            if self._is_mod_switch_hard_appear(active=False, interval=2):
                logger.attr('地图模式', '困难')
                MAP_MODE_SWITCH_NORMAL.clear_offset()
                self.device.click(MAP_MODE_SWITCH_NORMAL)
                self.interval_reset(MAP_MODE_SWITCH_HARD)
                return False
            return self._map_mode_switch_bypass_if_prep_showing()
        elif mode == 'hard':
            if self._is_mod_switch_hard_appear(active=True):
                logger.attr('地图模式', '困难')
                return True
            if self.match_template_color(MAP_MODE_SWITCH_NORMAL, offset=(20, 20), interval=2):
                logger.attr('地图模式', '普通')
                MAP_MODE_SWITCH_HARD.clear_offset()
                self.device.click(MAP_MODE_SWITCH_HARD)
                return False
            return self._map_mode_switch_bypass_if_prep_showing()
        else:
            logger.attr('地图模式', '未知')
            return False

    def _map_mode_switch_bypass_if_prep_showing(self):
        """2024.07+ 活动把 Normal/Hard 放进 LevelInfoSPView，旧 MAP_MODE_SWITCH_* 对不上。

        不要在活动列表上点主线 SWITCH_1_HARD。准备弹窗已由桥接确认时放行，
        由 chapter_track 按 chapter_name 切换 SP 孪生关卡后再 TRACKING。

        Returns:
            bool: 地图准备弹窗已出现则为 True，否则 False。
        """
        if self._level_prep_from_bridge():
            logger.info('[地图-操作] 关内难度模板未匹配，交给 chapter_track 切换 LevelInfoSPView')
            return True
        return False

    def _is_mod_switch_hard_appear(self, active=True, interval=0):
        """检测困难模式切换按钮是否出现。

        遍历多个可能的困难模式按钮模板进行匹配。

        Args:
            active (bool, optional): 是否需要检查按钮处于激活状态。默认为 True。
            interval (int | float, optional): 操作间隔时间（秒）。默认为 0。

        Returns:
            bool: 困难模式按钮是否出现（且若需要检查则是否处于激活状态）。
        """
        if interval:
            interval = self.get_interval_timer(MAP_MODE_SWITCH_HARD, interval=interval)
            if not interval.reached():
                return False

        for button in [
            MAP_MODE_SWITCH_HARD,
            MAP_MODE_SWITCH_HARD2,
            MAP_MODE_SWITCH_HARD3,
            MAP_MODE_SWITCH_HARD4,
            MAP_MODE_SWITCH_HARD5,
            MAP_MODE_SWITCH_HARD6,
        ]:
            if self.appear(button, offset=(20, 20), similarity=0.7):
                if active:
                    return self._is_mod_switch_hard_active(button)
                else:
                    return True
        return False

    def _is_mod_switch_hard_active(self, button):
        """通过颜色检测判断困难模式按钮是否处于激活状态。

        激活状态的按钮包含白色图标（RGB 最大值 > 235 的像素占比 > 50%）。

        Args:
            button (Button): 困难模式切换按钮。

        Returns:
            bool: 按钮是否处于激活状态。
        """
        image = self.image_crop(button.button)
        # 取 RGB 三通道最大值
        r, g, b = cv2.split(image)
        cv2.max(r, g, dst=r)
        cv2.max(r, b, dst=r)
        # 活跃按钮有白色图标，检查是否有颜色 > 235 的像素
        cv2.inRange(r, 235, 255, dst=r)
        sum_ = cv2.countNonZero(r)
        total = r.shape[0] * r.shape[1]
        return sum_ / total > 0.5


    def _enter_map_level_info_open(self):
        """准备页是否还在。截图或心跳任一命中即可。

        Returns:
            bool: LevelInfo / 舰队准备仍打开。
        """
        if self.appear(MAP_PREPARATION, offset=(20, 20)) \
                or self.appear(MAP_PREPARATION_HARD, offset=(20, 20)):
            return True
        return self._level_prep_from_bridge() in ('info', 'fleet')

    def _auto_search_continue_blocks_prep(self):
        """自律继续后的短窗口内，不要把残留准备页当成 LevelInfo。

        心跳仍报 info 时准备页还在，继续走 chapter_track。

        Returns:
            bool: True 表示本帧跳过准备页点击和 chapter_track。
        """
        timer = getattr(self, '_auto_search_continue_timer', None)
        if timer is None or timer.reached():
            return False
        if self._level_prep_from_bridge() == 'info':
            return False
        return True

    def _level_prep_from_bridge(self):
        """心跳中的 'info' / 'fleet'，否则 None。"""
        try:
            from module.alas_bridge.actions import map_prep_showing_from_heartbeat
            return map_prep_showing_from_heartbeat(self.config)
        except Exception:
            return None

    def _bridge_try_chapter_track(self):
        """
        通过 Sweeney 桥发送 GAME.TRACKING，替代点击出击。
        未开自动搜索时打开舰队选择，以便仍可处理职责。
        2x 教材由 chapter_track 的 use_2x_book 写入 TRACKING.operationItem。
        """
        try:
            from module.alas_bridge.actions import bridge_enabled, chapter_track
        except Exception:
            return False
        if not bridge_enabled(self.config):
            return False
        auto_fight = bool(getattr(self, 'map_is_auto_search', False)
                          or self.config.Campaign_UseAutoSearch)
        loop = bool(getattr(self, 'map_is_clear_mode', False)
                    or self.config.Campaign_UseClearMode)
        open_fleet = not auto_fight
        # 舰队准备页 info view 已关；再发 TRACKING 会 not_in_prep，然后误点 MAP_PREPARATION。
        if self._level_prep_from_bridge() == 'fleet':
            return False
        result = chapter_track(
            self.config,
            auto_fight=auto_fight,
            loop=loop,
            open_fleet=open_fleet,
        )
        if not isinstance(result, dict):
            return False
        logger.info(f'Sweeney chapter_track: {result}')
        if result.get('reason') == 'no_tries':
            logger.info('Sweeney chapter_track no remaining tries')
            raise ScriptEnd('No remaining chapter tries')
        if result.get('reason') == 'not_in_prep':
            # GAME.TRACKING 需要 LevelInfoView。再点 MAP_PREPARATION 会空等 GameStuck
            # （5_booty Event D3 2026-09-20 02:20，GAME_TIPS 关掉准备页后 15 次重启）。
            logger.warning('Sweeney chapter_track not_in_prep, skip MAP_PREPARATION click')
            raise ScriptEnd('chapter_track not_in_prep')
        if result.get('reason') == 'chapter_mismatch':
            logger.warning('Sweeney chapter_track mismatch, falling back to screenshot click')
            return False
        if not (result.get('sent') or result.get('already_active') or result.get('opened_fleet')):
            return False
        if auto_fight:
            self.map_is_auto_search = True
        return True

    def handle_map_preparation(self):
        """处理地图准备阶段，等待地图信息动画完成。

        Returns:
            Button | None: 地图准备页出现且信息动画结束时，返回普通或困难模式
                对应的准备按钮；否则返回 None。
        """
        bridge_prep = self._level_prep_from_bridge()
        if self.appear(MAP_PREPARATION, offset=(20, 20)):
            prep_button = MAP_PREPARATION
        elif self.appear(MAP_PREPARATION_HARD, offset=(20, 20)):
            prep_button = MAP_PREPARATION_HARD
        elif bridge_prep:
            logger.attr('地图准备', f'bridge_{bridge_prep}')
            return MAP_PREPARATION
        else:
            self.map_clear_percentage_prev = -1
            self.map_clear_percentage_timer.reset()
            return None
        if not self.config.MAP_HAS_CLEAR_PERCENTAGE:
            logger.attr('地图有通关百分比', self.config.MAP_HAS_CLEAR_PERCENTAGE)
            return prep_button
        if self.config.MAP_IS_ONE_TIME_STAGE:
            logger.attr('地图是一次性关卡', self.config.MAP_IS_ONE_TIME_STAGE)
            return prep_button
        # 信息栏会遮挡进度条和 MAP_GREEN
        if self.info_bar_count():
            return None

        percent = self.get_map_clear_percentage()
        logger.attr('地图通关百分比', f'{int(percent * 100)}%')
        # 注意：进度条从 100% 开始，然后从 0% 增加到实际值。
        # 2022.08.21 当 `percent` 从 0 上升时仍然启用此逻辑。
        if percent > 0.95 and 0 <= self.map_clear_percentage_prev < 0.95:
            # 地图通关进度达到 100%，直接退出
            return prep_button
        if abs(percent - self.map_clear_percentage_prev) < 0.02:
            self.map_clear_percentage_prev = percent
            if self.map_clear_percentage_timer.reached():
                return prep_button
            else:
                return None
        else:
            self.map_clear_percentage_prev = percent
            self.map_clear_percentage_timer.reset()
            return None

    def withdraw(self, skip_first_screenshot=True):
        """从当前战役地图撤退。

        Args:
            skip_first_screenshot (bool, optional): 是否跳过首次截图。默认为 True。

        Raises:
            CampaignEnd: 成功撤退并回到关卡选择界面时抛出。
        """
        logger.hr('地图撤退')
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if self.appear_then_click(FLEET_SWITCH_CONFIRM, offset=(30, 30)):
                continue
            if self.handle_popup_confirm('WITHDRAW'):
                continue
            if self.appear_then_click(WITHDRAW, interval=5):
                continue
            if self.handle_auto_search_exit():
                continue
            # 意外点击处理
            if self.appear(DAILY_CHECK, offset=(20, 20), interval=3):
                logger.info(f'{DAILY_CHECK} -> {BACK_ARROW}')
                self.device.click(BACK_ARROW)
                continue

            # 结束判断
            if self.handle_in_stage():
                raise CampaignEnd('Withdraw')

    def handle_map_cat_attack(self):
        """处理地图上的指挥喵伏击/攻击动画并点击跳过。

        Returns:
            bool: 是否检测到并点击跳过了动画。
        """
        if not self.map_cat_attack_timer.reached():
            return False
        if self.image_color_count(MAP_CAT_ATTACK, color=(255, 231, 123), threshold=30, count=100):
            logger.info('[地图-操作] 跳过地图猫攻击')
            self.device.click(MAP_CAT_ATTACK)
            self.map_cat_attack_timer.reset()
            return True
        if not self.map_is_clear_mode:
            # 威胁检测：Medium 模式有 106 像素计数，MAP_CAT_ATTACK_MIRROR 有 290。
            if self.image_color_count(MAP_CAT_ATTACK_MIRROR, color=(255, 231, 123), threshold=30, count=200):
                logger.info('[地图-操作] 跳过地图被攻击')
                self.device.click(MAP_CAT_ATTACK)
                self.map_cat_attack_timer.reset()
                return True

        return False

    @property
    def fleets_reversed(self):
        """是否反转了道中队与 Boss 队在游戏界面上的出击顺序。

        Returns:
            bool: 是否反转。
        """
        if not self.config.FLEET_2:
            return False
        return self.config.Fleet_FleetOrder in ['fleet1_boss_fleet2_mob', 'fleet1_standby_fleet2_all']

    def handle_fleet_reverse(self):
        """处理舰队出击顺序反转。

        游戏会选择编号较小的舰队作为第一舰队，无论我们在舰队准备中如何选择。
        自动搜索更新后，游戏不再忽略用户设置。

        Returns:
            bool: 舰队是否发生了变更。
        """
        if not self.map_is_hard_mode \
                and self.config.Fleet_FleetOrder in ['fleet1_boss_fleet2_mob', 'fleet1_standby_fleet2_all']:
            logger.warning(f"[Map] 普通模式不应使用反转的舰队顺序 ({self.config.Fleet_FleetOrder})。")
            logger.warning('[Map] 请交换舰队 1 和舰队 2 的配置，'
                           '使用 "fleet1_mob_fleet2_boss" 或 "fleet1_all_fleet2_standby"')
            # raise RequestHumanTakeover

        if not self.fleets_reversed:
            return False

        return self.fleet_set(index=2)
