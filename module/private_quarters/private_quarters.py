"""私人休息室任务模块。

自动化私人休息室的日常任务，包括商店购买和舰娘互动。

主要功能：
    - 购买每周商店物品（玫瑰需要金币，蛋糕需要钻石）
    - 与指定舰娘执行每日亲密互动
    - OCR 读取每日互动剩余次数
    - 导航至舰娘房间并执行互动序列

舰娘互动机制：
    - 每日有固定的亲密互动次数上限
    - 需要进入对应舰娘的房间执行互动
    - 互动包括对话选项和触摸互动
    - 可用舰娘：安克雷奇、能代、天狼星、新泽西、大凤、埃吉尔、纳希莫夫

商店机制：
    - 玫瑰（Roses）：每周限购物品，消耗金币（约 24000+）
    - 蛋糕（Cake）：每周限购物品，消耗钻石（约 210+）
    - TW 服务器暂不支持商店功能

继承关系：
    - PQInteract: 舰娘互动逻辑（房间导航、对话、触摸互动）
    - PQShop: 商店购买逻辑（商品过滤、购买确认）

服务器限制：
    - 部分舰娘在特定服务器不可用（通过 not_supported_filter 配置）
    - TW 服务器不支持商店功能

Pages:
    私人宿舍页面：page_private_quarters
    宿舍菜单页面：page_dormmenu
"""

import module.config.server as server
from module.base.timer import Timer
from module.logger import logger
from module.private_quarters.assets import *
from module.private_quarters.interact import PQInteract
from module.private_quarters.shop import PQShop
from module.ui.page import page_private_quarters, page_dormmenu


class PrivateQuarters(PQInteract, PQShop):
    """私人休息室任务处理器。

    管理私人休息室的日常任务流程，组合了舰娘互动（PQInteract）
    和商店购买（PQShop）两种能力。

    核心流程：
        1. 从任意页面导航至宿舍菜单，再进入私人休息室。
        2. 如配置了每周商品购买，进入商店购买玫瑰或蛋糕。
        3. 如配置了舰娘互动，检查每日剩余次数后进入目标房间互动。

    Attributes:
        not_supported_filter (dict): 各服务器不支持的舰娘列表。

    配置项:
        PrivateQuarters_BuyRoses: 是否购买每周玫瑰。
        PrivateQuarters_BuyCake: 是否购买每周蛋糕。
        PrivateQuarters_TargetInteract: 是否执行舰娘互动。
        PrivateQuarters_TargetShip: 目标舰娘名称（小写，如 'sirius'）。
    """
    # Key: str, server name
    # Value: list[str]
    not_supported_filter = {
        'cn': (),
        'en': (),
        'jp': ('nakhimov'),
        'tw': ('taihou', 'nakhimov'),
    }

    def _pq_get_daily_count(self, retry=3):
        """
        获取每日互动剩余次数，带重试缓冲。

        高性能 PC 上初始截图可能模糊或滞后，
        因此通过有限次数的重读来确保结果准确。

        Args:
            retry (int): 最大重试次数

        Returns:
            int: 剩余互动次数，0 表示已耗尽

        Pages:
            in: 私人宿舍主页
        """
        count = self.status_get_daily_count()
        get_timer = Timer(1.5, count=3).start()
        skip_first_screenshot = True
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            # 结束条件：成功获取非零次数，或重试耗尽确认为零
            if count != 0 or retry == 0:
                return count

            # 计时器到期，重新读取每日次数
            if get_timer.reached():
                count = self.status_get_daily_count()
                get_timer.reset()
                retry -= 1

    def _pq_shop_enter(self):
        """
        进入私人宿舍商店并导航到天狼星礼物标签页。

        Pages:
            in: 私人宿舍主页
            out: 私人宿舍商店 - 天狼星 - 礼物
        """
        # 进入商店
        self.ui_click(
            click_button=PRIVATE_QUARTERS_SHOP_ENTER,
            check_button=PRIVATE_QUARTERS_SHOP_CHECK,
            appear_button=page_private_quarters.check_button,
            offset=(20, 20),
            skip_first_screenshot=True
        )

        # 切换到天狼星分区
        self.shop_left_navbar_ensure(2)

        # 切换到礼物标签
        self.shop_bottom_navbar_ensure(2)

    def _pq_shop_exit(self):
        """
        退出私人宿舍商店，返回私人宿舍主页。

        Pages:
            in: 私人宿舍商店
            out: 私人宿舍主页
        """
        self.ui_click(
            click_button=PRIVATE_QUARTERS_SHOP_BACK,
            check_button=page_private_quarters.check_button,
            appear_button=PRIVATE_QUARTERS_SHOP_CHECK,
            offset=(20, 20),
            skip_first_screenshot=True
        )

    def pq_shop_weekly_items(self):
        """
        购买商店每周物品。

        玫瑰需要 24000+ 金币，蛋糕需要 210+ 钻石，
        余额不足时跳过等待次日。

        Pages:
            in: 私人宿舍主页
            out: 私人宿舍主页
        """
        logger.hr(f'[私人休息室] 获取每周物品', level=2)

        # 进入商店
        self._pq_shop_enter()

        # 执行购买
        self.shop_buy()

        # 退出商店
        self._pq_shop_exit()

    def pq_execute_interact(self, target_ship):
        """
        执行与目标舰娘的互动流程。

        校验目标合法性后，进入房间并执行互动序列。

        Args:
            target_ship (str): 目标舰娘名称（小写，如 'sirius'）

        Pages:
            in: 私人宿舍主页
            out: 私人宿舍主页
        """
        # 校验目标是否可选
        target_title = target_ship.title().replace('_', ' ')
        if target_ship not in self.available_targets:
            logger.error(f'Unsupported target ship: {target_title}, cannot continue subtask')
            return

        # 进入目标房间，最多重试 3 次
        if not self.pq_goto_room(target_ship, retry=3):
            return

        # 执行互动流程
        self.pq_interact()

    def pq_run(self, buy_roses, buy_cake, target_interact, target_ship,
               do_shop=True, do_interact=True):
        """
        执行私人宿舍日常流程。

        包括购买每周商品（玫瑰/蛋糕）和与目标舰娘互动。
        桥接已完成的子任务由 do_shop / do_interact 跳过。

        Args:
            buy_roses (bool): 是否购买每周玫瑰
            buy_cake (bool): 是否购买每周蛋糕
            target_interact (bool): 是否执行舰娘互动
            target_ship (str): 目标舰娘名称
            do_shop (bool): 是否走截图商店路径
            do_interact (bool): 是否走截图互动路径

        Pages:
            in: 私人宿舍主页
            out: 私人宿舍主页
        """
        logger.hr(f'私人休息室运行', level=1)
        target_title = target_ship.title().replace('_', ' ')
        logger.info(f'[私人休息室] 任务配置: 买玫瑰={buy_roses}, '
                    f'买蛋糕={buy_cake}, '
                    f'舰娘互动={target_interact}, '
                    f'目标舰娘={target_title}')

        # 进入商店购买每周物品
        if do_shop and self.shop_filter:
            if server.server not in ['tw']:
                self.pq_shop_weekly_items()
            else:
                logger.info(f'[私人休息室] {server.server} 服务器不支持商店功能')

        # 执行舰娘互动
        if do_interact and target_interact:
            # Ensure target is supported for server
            # Update `not_supported_filter` to enable a target
            if target_ship in self.not_supported_filter[server.server]:
                logger.info(f'[私人休息室] 目标舰娘 {target_ship} 在 {server.server} 服务器不可用')
                return

            # 获取每日剩余次数，为 0 则退出
            count = self._pq_get_daily_count(retry=3)
            if count == 0:
                logger.info('每日亲密度次数耗尽，退出子任务')
                return

            # 执行互动
            self.pq_execute_interact(target_ship)

    def _pq_bridge_try(self, buy_roses, buy_cake, target_interact, target_ship):
        """
        优先走 Sweeney 桥接买每周礼物、消耗每日体力，避免打开 Dorm3D。

        Returns:
            tuple[bool, bool]: (shop_done, interact_done)。任一为 False 时截图路径补做该子任务。
        """
        shop_needed = bool(self.shop_filter) and server.server not in ['tw']
        interact_needed = bool(target_interact)
        if target_interact and target_ship in self.not_supported_filter.get(server.server, ()):
            logger.info(f'[私人休息室] 目标舰娘 {target_ship} 在 {server.server} 服务器不可用')
            interact_needed = False

        shop_done = not shop_needed
        interact_done = not interact_needed
        if shop_done and interact_done:
            return True, True

        try:
            from module.alas_bridge.actions import (
                bridge_enabled,
                get_pq_status,
                pq_from_heartbeat,
                pq_shop_buy,
                pq_spend_stamina,
            )
        except Exception as e:
            logger.info(f'Sweeney PQ bridge import failed: {e}')
            return shop_done, interact_done

        if not bridge_enabled(self.config):
            return shop_done, interact_done

        status = pq_from_heartbeat(self.config) or get_pq_status(self.config)
        if isinstance(status, dict) and 'stamina' in status:
            stamina = int(status.get('stamina') or 0)
            logger.info(f'[私人休息室] 桥接体力={stamina}/{status.get("stamina_max")}')
            if interact_needed and stamina <= 0:
                logger.info('[私人休息室] 桥接：每日体力已用完')
                interact_done = True

        if shop_needed and not shop_done:
            try:
                result = pq_shop_buy(self.config, roses=bool(buy_roses), cake=bool(buy_cake))
            except Exception as e:
                logger.info(f'Sweeney pq_shop_buy failed: {e}')
                result = None
            # pq_shop_buy 返回 buys[]（limit / complete_or_limit / bought），没有 sent
            if isinstance(result, dict):
                logger.info(f'[私人休息室] 商店购买通过桥接完成: {result}')
                shop_done = True
            else:
                logger.info('[私人休息室] 商店桥接未完成，将使用截图路径')

        if interact_needed and not interact_done:
            try:
                result = pq_spend_stamina(self.config, ship=target_ship)
            except Exception as e:
                logger.info(f'Sweeney pq_spend_stamina failed: {e}')
                result = None
            if isinstance(result, dict):
                logger.info(
                    f'[私人休息室] 互动通过桥接完成: '
                    f'spent={result.get("spent")} '
                    f'{result.get("stamina_before")}->{result.get("stamina_after")} '
                    f'group={result.get("group_id")}'
                )
                interact_done = True
            else:
                logger.info('[私人休息室] 体力桥接未完成，将使用截图路径')

        return shop_done, interact_done

    def run(self):
        """
        私人宿舍任务入口。

        桥接可用时先 RPC 完成商店与体力，不进入宿舍 UI。
        仅当桥接缺子任务时才导航到私人宿舍走截图路径。

        Pages:
            in: 任意页面
            out: page_main，可能有 info_bar
        """
        buy_roses = self.config.PrivateQuarters_BuyRoses
        buy_cake = self.config.PrivateQuarters_BuyCake
        target_interact = self.config.PrivateQuarters_TargetInteract
        target_ship = self.config.PrivateQuarters_TargetShip

        shop_done, interact_done = self._pq_bridge_try(
            buy_roses, buy_cake, target_interact, target_ship
        )
        if shop_done and interact_done:
            logger.info('[私人休息室] 通过 Sweeney 桥接完成（未打开宿舍 UI）')
            self.config.task_delay(server_update=True)
            return

        self.ui_ensure(page_dormmenu)
        self.ui_goto(page_private_quarters, get_ship=False)
        self.handle_info_bar()
        self.pq_run(
            buy_roses=buy_roses,
            buy_cake=buy_cake,
            target_interact=target_interact,
            target_ship=target_ship,
            do_shop=not shop_done,
            do_interact=not interact_done,
        )

        self.config.task_delay(server_update=True)
