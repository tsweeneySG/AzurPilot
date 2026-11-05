"""离岛维护总任务。

进入岛屿场景（管理按钮现在打开的是规划器，维护不依赖那一页），
通过 Sweeney 桥启动一键维护，等心跳里的 island.mega 结束，
再按岛屿回家离开，并预约到最早一名工人岗位做完的时刻。
"""
from datetime import datetime, timedelta

from module.base.timer import Timer
from module.config.time_source import now as current_time
from module.logger import logger

IDLE_FLOOR = timedelta(minutes=2)
IDLE_FALLBACK = timedelta(minutes=30)
MEGA_WAIT_SECONDS = 12 * 60
ISLAND_LOAD_SECONDS = 60
ISLAND_EXIT_SECONDS = 45


def next_run_from_idle(next_idle_at, now):
    """把岗位结束的 unix 时间换成调度用的本地时间。

    Args:
        next_idle_at: 服务器 unix 秒。None、非数字或 <=0 时用 30 分钟兜底。
        now (datetime): 当前本地时间。

    Returns:
        datetime: 不早于 now+2 分钟。没有有效结束时间时为 now+30 分钟。
    """
    floor = now + IDLE_FLOOR
    fallback = now + IDLE_FALLBACK
    if next_idle_at is None:
        return fallback
    try:
        stamp = float(next_idle_at)
    except (TypeError, ValueError):
        return fallback
    if stamp <= 0:
        return fallback
    target = datetime.fromtimestamp(stamp)
    if target < floor:
        return floor
    return target


def heartbeat_island(config, max_age=8.0):
    """心跳里的 island 表。读不到时返回 None。"""
    try:
        from module.alas_bridge.game_state import GameState

        state = GameState.from_config(config).read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    island = state.get('island')
    return island if isinstance(island, dict) else None


def heartbeat_island_scene_ready(island):
    """岛屿 3D 场景是否已经初始化完。

    island.loaded 只表示代理里有岛数据，场景可能还在加载。
    sceneReady 对应 IslandCore.STATE_INIT_FINISH。
    """
    return isinstance(island, dict) and island.get('sceneReady') is True


def mega_is_done(mega, seq):
    """心跳 island.mega 是否是这一轮已经结束的结果。"""
    if not isinstance(mega, dict) or mega.get('running'):
        return False
    if mega.get('phase') != 'done':
        return False
    if seq is None:
        return True
    try:
        return int(mega.get('seq')) == int(seq)
    except (TypeError, ValueError):
        return False


class IslandManagement:
    """进入岛屿场景，跑 Sweeney 一键维护，离开后按岗位结束时间预约。"""

    def __init__(self, config, device):
        self.config = config
        self.device = device

    def _wait_island_scene(self, island):
        """等到岛屿场景初始化完成，并且主界面 HUD 已经画出来。

        桥的场景名会在过场一开始就变成岛屿。这段时间不点任何按钮。
        """
        # 岛屿 HUD 标记在 ui.assets（page_island 用它）。island.assets 里没有这个名字。
        from module.ui.assets import ISLAND_CHECK

        for _ in island.loop(timeout=ISLAND_LOAD_SECONDS, skip_first=False):
            ready = heartbeat_island_scene_ready(heartbeat_island(self.config))
            if ready and island.appear(ISLAND_CHECK, offset=(20, 20)):
                return True
        return False

    def _wait_main_chrome(self, island):
        """主界面出击/编队按钮稳定出现。场景名提前变成主界面时不能算到了。"""
        confirm = Timer(1, count=2).start()
        for _ in island.loop(timeout=ISLAND_EXIT_SECONDS, skip_first=False):
            if island.is_in_main():
                if confirm.reached():
                    return True
            else:
                confirm.reset()
        return False

    def _leave_island(self, island):
        """等场景加载完，再按岛屿自己的回家离开。

        不调用 goto_scene(MAINUI)，也不在过场里点主界面按钮。
        那两步会把主界面和未卸掉的出击层叠在一起。
        """
        from module.alas_bridge.actions import island_exit

        if not heartbeat_island_scene_ready(heartbeat_island(self.config)):
            logger.info('[离岛维护] 等岛屿场景加载完再离开')
            if not self._wait_island_scene(island):
                logger.warning('[离岛维护] 岛屿场景未加载完，不强制切主界面')
                return
        exited = island_exit(self.config)
        if not isinstance(exited, dict):
            logger.warning('[离岛维护] island_exit 未执行，不强制切主界面')
            return
        if self._wait_main_chrome(island):
            return
        if heartbeat_island_scene_ready(heartbeat_island(self.config)):
            logger.info('[离岛维护] 主界面按钮未出现，再按一次回家')
            island_exit(self.config)
            if self._wait_main_chrome(island):
                return
        logger.warning('[离岛维护] 主界面按钮仍未出现')

    def run(self):
        """
        Pages:
            in: 任意页面
            out: page_main
        """
        from module.alas_bridge.actions import (
            bridge_enabled,
            island_manage,
            island_mega_from_heartbeat,
        )
        from module.island.island import Island
        from module.ui.page import page_island

        logger.hr('离岛维护', level=1)
        if not bridge_enabled(self.config):
            logger.warning('[离岛维护] Sweeney 桥未开启，30 分钟后重试')
            self.config.task_delay(minute=30)
            return

        island = Island(config=self.config, device=self.device)
        island.ui_goto(page_island, get_ship=False)
        if not self._wait_island_scene(island):
            logger.warning('[离岛维护] 岛屿场景未加载完，30 分钟后重试')
            self._leave_island(island)
            self.config.task_delay(minute=30)
            return
        result = island_manage(self.config)
        if not isinstance(result, dict):
            logger.warning('[离岛维护] island_manage 未启动，30 分钟后重试')
            self._leave_island(island)
            self.config.task_delay(minute=30)
            return

        seq = result.get('seq')
        logger.attr('Started', result.get('started'))
        logger.attr('AlreadyRunning', result.get('already_running'))
        logger.attr('Seq', seq)

        finished = None
        last_phase = None
        for _ in island.loop(timeout=MEGA_WAIT_SECONDS, skip_first=False):
            mega = island_mega_from_heartbeat(self.config)
            if isinstance(mega, dict):
                phase = mega.get('phase')
                if phase != last_phase:
                    last_phase = phase
                    logger.attr('Phase', phase)
                    if mega.get('error'):
                        logger.attr('MegaError', mega.get('error'))
            if mega_is_done(mega, seq):
                finished = mega
                break
            if island.ui_additional(get_ship=False):
                continue

        if finished is None:
            logger.warning('[离岛维护] 等待维护结束超时，按 30 分钟兜底预约')
        else:
            logger.attr('NextIdleAt', finished.get('nextIdleAt'))
            if finished.get('error'):
                logger.attr('MegaError', finished.get('error'))
            logger.info('[离岛维护] 一键维护结束')

        self._leave_island(island)
        idle_at = finished.get('nextIdleAt') if isinstance(finished, dict) else None
        when = next_run_from_idle(idle_at, current_time())
        logger.attr('NextRun', when.strftime('%Y-%m-%d %H:%M:%S'))
        self.config.task_delay(target=when)
