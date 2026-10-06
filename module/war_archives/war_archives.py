"""作战档案模块。

自动执行碧蓝航线的作战档案战役。作战档案是过往活动的复刻入口，
需要消耗数据密钥（Data Key）才能进入。2026-07 后旧图每场 5 把，新特别图按关卡单独标价。

本模块的核心功能：
- 通过 OCR 识别剩余数据密钥数量，控制出击节奏
- 管理每日出击次数限制（可配置每日上限）
- 持有量不够进入当前这张图时停止任务（持有量大于 0 仍可能不够）
- 通关后实时扣减每日额度并持久化到配置

注意：作战档案中禁用自动搜索续战功能，因为自动搜索菜单的模糊背景
会遮挡数据密钥的 OCR 识别区域。

配置路径: WarArchives.DailyRunCount (每日出击上限),
         StopCondition.OilLimit (燃油限制)
"""

import re

from campaign.campaign_war_archives.campaign_base import CampaignBase
from module.campaign.run import CampaignRun
from module.config.utils import get_server_last_update
from module.logger import logger
from module.ocr.ocr import DigitCounter
from module.war_archives.assets import (OCR_DATA_KEY_CAMPAIGN,
                                        WAR_ARCHIVES_CAMPAIGN_CHECK)
from module.war_archives_catchup.policy import (
    LEGACY_REMASTER_TICKET_COST,
    data_keys_insufficient,
)


class OcrDataKey(DigitCounter):
    """作战档案数据密钥计数器 OCR。

    处理数据密钥数量的 OCR 识别，修正常见的识别错误。
    数据密钥格式为 "当前/60"，OCR 可能将 "/60" 误识别为 "60"。
    """

    def after_process(self, result):
        """OCR 后处理，修正数据密钥数量识别错误。

        将 OCR 误识别的 "X60" 格式修正为 "X/60"。
        例如：识别结果 "1560" 会被修正为 "15/60"。

        Args:
            result: OCR 原始识别结果字符串。

        Returns:
            修正后的数据密钥数量字符串。
        """
        result = super().after_process(result)
        result = re.sub(r'(\d{1,2})60$', r'\1/60', result)
        return result


DATA_KEY_CAMPAIGN = OcrDataKey(OCR_DATA_KEY_CAMPAIGN, letter=(255, 247, 247), threshold=64)


class CampaignWarArchives(CampaignRun, CampaignBase):
    """作战档案战役执行器。

    继承自 CampaignRun（战役运行）和 CampaignBase（作战档案战役基础），
    在标准战役运行逻辑上增加作战档案特有的限制：
    - 数据密钥消耗管理（强制启用 USE_DATA_KEY）
    - 每日出击次数限制（跨天自动重置、配置变更实时调整）
    - 数据密钥 OCR 检测（在档案战役界面识别剩余数量）
    - 禁用自动搜索续战（避免遮挡 OCR 区域）
    """
    def daily_run_limit_reset(self):
        """刷新作战档案每日出击额度。

        DailyRunCount 是用户设置的每日上限；DailyRunCountRemain 是脚本保存的当日剩余额度。
        记录时间早于上次服务器刷新时，说明已经进入新的一天，需要恢复完整额度。
        """
        limit = self.config.WarArchives_DailyRunCount
        if limit <= 0:
            if self.config.WarArchives_DailyRunCountLimit != 0:
                with self.config.multi_set():
                    self.config.WarArchives_DailyRunCountRemain = 0
                    self.config.WarArchives_DailyRunCountLimit = 0
            return

        last_update = get_server_last_update(self.config.Scheduler_ServerUpdate)
        record = self.config.WarArchives_DailyRunCountRecord
        remain = self.config.WarArchives_DailyRunCountRemain
        old_limit = self.config.WarArchives_DailyRunCountLimit
        if record < last_update or remain > limit:
            logger.info(f'[作战档案] 重置每日出击次数: {remain} -> {limit}')
            with self.config.multi_set():
                self.config.WarArchives_DailyRunCountRemain = limit
                self.config.WarArchives_DailyRunCountRecord = last_update
                self.config.WarArchives_DailyRunCountLimit = limit
        elif old_limit != limit:
            remain = max(remain + limit - old_limit, 0)
            remain = min(remain, limit)
            logger.info(f'[作战档案] 更新每日出击次数: {old_limit} -> {limit}，剩余: {remain}')
            with self.config.multi_set():
                self.config.WarArchives_DailyRunCountRemain = remain
                self.config.WarArchives_DailyRunCountLimit = limit

    def daily_run_limit_triggered(self):
        """检查作战档案每日出击额度是否用尽。"""
        limit = self.config.WarArchives_DailyRunCount
        if limit <= 0:
            return False

        remain = self.config.WarArchives_DailyRunCountRemain
        logger.info(f'[作战档案] 今日剩余出击次数: {remain} / {limit}')
        if remain > 0:
            return False

        logger.hr('触发停止条件：每日出击次数')
        self.config.task_delay(server_update=True)
        return True

    def daily_run_limit_consume(self):
        """通关后扣减并保存作战档案每日出击额度。"""
        limit = self.config.WarArchives_DailyRunCount
        if limit <= 0:
            return

        remain = max(self.config.WarArchives_DailyRunCountRemain - 1, 0)
        logger.info(f'[作战档案] 今日剩余出击次数: {remain} / {limit}')
        with self.config.multi_set():
            self.config.WarArchives_DailyRunCountRemain = remain
            self.config.WarArchives_DailyRunCountRecord = get_server_last_update(self.config.Scheduler_ServerUpdate)
            self.config.WarArchives_DailyRunCountLimit = limit

    def after_campaign_run(self):
        """作战档案单次通关后立即扣减每日出击额度。"""
        self.daily_run_limit_consume()

    def triggered_stop_condition(self, oil_check=True):
        """检查作战档案的停止条件。

        当处于档案战役界面时，用桥接回报的本图消耗（没有时报旧档 5 把）对比持有量。
        持有量大于 0 但不够进当前这张图时，延迟任务到下次服务器重置。

        Pages:
            in: WAR_ARCHIVES_CAMPAIGN_CHECK（档案战役界面）

        Args:
            oil_check: 是否检查燃油停止条件。

        Returns:
            True 表示触发了停止条件，False 表示未触发。
        """
        if self.daily_run_limit_triggered():
            return True

        # chapter_enter 已经带回本图消耗。进图后的截图往往还停在上一画面，
        # WAR_ARCHIVES_CAMPAIGN_CHECK 对不上，不能把钥匙判断绑在那张按钮上。
        if self._bridge_data_keys_block():
            return True

        if self.appear(WAR_ARCHIVES_CAMPAIGN_CHECK, offset=(20, 20)):
            current, _remain, total = DATA_KEY_CAMPAIGN.ocr(self.device.image)
            logger.info(
                f'[作战档案] 数据密钥: {current} / {total}, '
                f'本图消耗: {LEGACY_REMASTER_TICKET_COST}'
            )
            if data_keys_insufficient(current, LEGACY_REMASTER_TICKET_COST):
                logger.hr('[作战档案] 数据密钥不足以进入本图')
                self.config.task_delay(server_update=True)
                return True

        # 其他情况，检查通用停止条件
        return super().triggered_stop_condition(oil_check)

    def _wa_data_key_gate(self):
        """chapter_enter 写在战役实例上的钥匙持有量和本图消耗。"""
        gate = getattr(getattr(self, 'campaign', None), '_wa_data_key_gate', None)
        return gate if isinstance(gate, dict) else None

    def _bridge_data_keys_block(self):
        """
        桥接已给出本图消耗时，持有量不够就推迟到服务器刷新。

        Returns:
            bool: True 表示已推迟，调用方应结束本轮。
        """
        gate = self._wa_data_key_gate()
        if gate is None:
            return False
        if gate.get('tickets') is None or gate.get('ticket_cost') is None:
            return False
        try:
            owned = int(gate.get('tickets'))
            cost = int(gate.get('ticket_cost'))
        except (TypeError, ValueError):
            return False
        logger.info(f'[作战档案] 数据密钥: {owned}, 本图消耗: {cost}')
        if not data_keys_insufficient(owned, cost):
            return False
        logger.hr('[作战档案] 数据密钥不足以进入本图')
        self.config.task_delay(server_update=True)
        return True

    def _handle_campaign_script_end(self, e):
        """出击被拒且钥匙不够时，推迟到刷新，避免立刻重开同一张图。"""
        if str(e) == 'chapter_track not_in_prep' and self._bridge_data_keys_block():
            return
        super()._handle_campaign_script_end(e)

    def can_use_auto_search_continue(self):
        """判断是否可使用自动搜索续战。

        自动搜索菜单具有模糊背景，会遮挡 DATA_KEY_CAMPAIGN 的 OCR 区域，
        因此作战档案中禁用自动搜索续战功能。

        Returns:
            始终返回 False，不支持自动搜索续战。
        """
        return False

    def run(self, name=None, folder='campaign_main', mode='normal', total=0):
        """执行作战档案战役。

        强制启用数据密钥使用，然后调用父类战役运行逻辑。
        作战档案必须使用数据密钥才能进入。

        Pages:
            in: page_archives（作战档案选择界面）
            out: page_main（主界面，任务完成后）

        Args:
            name: 战役名称，如 'war_archives_20190321_en'。
            folder: 战役文件夹路径，默认 'campaign_main'。
            mode: 战役模式，'normal' 或 'hard'。
            total: 总运行次数，0 表示无限。
        """
        self.config.override(USE_DATA_KEY=True)
        self.daily_run_limit_reset()
        super().run(name, folder, mode, total)
