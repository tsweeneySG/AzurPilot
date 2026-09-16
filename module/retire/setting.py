"""退役设置管理模块。

管理快速退役的设置界面操作，包括进入/退出设置页面、
切换退役选项（如退役稀有度范围、保留规则等）。

QuickRetireSetting 扩展 Setting 类，适配退役设置的 UI 样式。
QuickRetireSettingHandler 提供设置页面的导航操作。

继承自 UI，利用页面导航能力。
"""

import cv2

from module.base.button import Button
from module.base.decorator import cached_property
from module.base.timer import Timer
from module.base.utils import color_similarity_2d
from module.config.utils import dict_to_kv
from module.logger import logger
from module.retire.assets import *
from module.ui.setting import Setting
from module.ui.ui import UI

# 稀有度三行是互斥单选。每行只登记目标列时，白像素误判会把 R 当成 E。
RARITY_FILTERS = ('filter_1', 'filter_2', 'filter_3')
# 选中圆点大约 200+ 白像素；50 太松，未选中的描边也能过。
RARITY_WHITE_MIN = 80


def _radio_at_row(template, x, name):
    """把某一列的 X 套到同一行的 Y 上，得到可点可检的单选按钮。"""
    area = template.area
    width = area[2] - area[0]
    box = (int(x), int(area[1]), int(x + width), int(area[3]))
    return Button(area=box, color=template.color, button=box, name=name)


def rarity_columns_collapsed():
    """JP 旧资源三列仍叠在 None 上，不能当网格用。"""
    xs = (
        RETIRE_SETTING_2.area[0],
        RETIRE_SETTING_1.area[0],
        RETIRE_SETTING_3.area[0],
    )
    return max(xs) - min(xs) < 40


class QuickRetireSetting(Setting):
    """快速退役设置项。

    稀有度三行按该行白像素最多的单选判定当前值，避免只登记 E
    时把旁边的 R 亮点误判成 Elite 已开。
    """

    def _option_white_count(self, option):
        image = self.main.image_crop(option, copy=False)
        mask = color_similarity_2d(image, color=(255, 255, 255))
        cv2.inRange(mask, 221, 255, dst=mask)
        return int(cv2.countNonZero(mask))

    def _rarity_row_winner(self, setting):
        best_button = None
        best_count = RARITY_WHITE_MIN
        for key, button in self.settings.items():
            if key[0] != setting:
                continue
            count = self._option_white_count(button)
            if count > best_count:
                best_count = count
                best_button = button
        return best_button

    def is_option_active(self, option: Button) -> bool:
        for key, button in self.settings.items():
            if button is not option:
                continue
            if key[0] in RARITY_FILTERS:
                return self._rarity_row_winner(key[0]) is option
            return self.main.image_color_count(
                option, color=(255, 255, 255), threshold=221, count=100)
        return False

    def _set_execute(self, **kwargs):
        """一次只点一个单选，等下一帧再判。连点会把 E 打成同行的 R。"""
        status = self._product_setting_status(**kwargs)

        logger.info(f'[UI-设置] 设置选项 {self.name}, {dict_to_kv(kwargs)}')
        skip_first_screenshot = True
        retry = Timer(2, count=4)
        timeout = Timer(20, count=30).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.main.device.screenshot()

            if timeout.reached():
                logger.warning(f'[UI] 设置 {self.name} 选项超时，假定当前选项已正确。')
                return False

            self.show_active_buttons()
            clicks = self.get_buttons_to_click(status)
            if not clicks:
                return True
            if retry.reached():
                self.main.device.click(clicks[0])
                retry.reset()


class QuickRetireSettingHandler(UI):
    """退役设置页面导航处理器。

    提供退役设置页面的进入和退出操作。
    """
    def _retire_setting_enter(self):
        """
        Pages:
            in: IN_RETIREMENT_CHECK, RETIRE_SETTING_ENTER
            out: RETIRE_SETTING_QUIT
        """
        self.ui_click(RETIRE_SETTING_ENTER, check_button=RETIRE_SETTING_QUIT,
                      offset=(30, 100), retry_wait=3, skip_first_screenshot=True)
        # 面板弹出动画未结束时白像素会误判，先吃一张稳定截图。
        self.device.screenshot()

    def _retire_setting_closed(self):
        """退役设置面板是否已关闭。

        1080p 下调后，面板打开时左侧齿轮仍可能以 0.75 相似度匹配
        RETIRE_SETTING_ENTER，不能用它判断已退出。
        """
        return not self.appear(RETIRE_SETTING_QUIT, offset=(30, 100))

    def _retire_setting_quit(self):
        """
        Pages:
            in: RETIRE_SETTING_QUIT
            out: IN_RETIREMENT_CHECK, RETIRE_SETTING_ENTER
        """
        self.ui_click(RETIRE_SETTING_QUIT, check_button=self._retire_setting_closed,
                      offset=(30, 100), retry_wait=3, skip_first_screenshot=True)

    @cached_property
    def retire_setting(self) -> QuickRetireSetting:
        setting = QuickRetireSetting(name='RETIRE', main=self)
        setting.reset_first = False
        collapsed = rarity_columns_collapsed()

        def add_rarity_row(name, template, default):
            if collapsed:
                setting.add_setting(
                    setting=name,
                    option_buttons=[template],
                    option_names=[default],
                    option_default=default,
                )
                return
            setting.add_setting(
                setting=name,
                option_buttons=[
                    _radio_at_row(template, RETIRE_SETTING_2.area[0], f'{name}_E'),
                    _radio_at_row(template, RETIRE_SETTING_1.area[0], f'{name}_R'),
                    _radio_at_row(template, RETIRE_SETTING_3.area[0], f'{name}_N'),
                ],
                option_names=['E', 'R', 'N'],
                option_default=default,
            )

        add_rarity_row('filter_1', RETIRE_SETTING_1, 'R')
        add_rarity_row('filter_2', RETIRE_SETTING_2, 'E')
        add_rarity_row('filter_3', RETIRE_SETTING_3, 'N')
        setting.add_setting(
            setting='filter_4',
            option_buttons=[RETIRE_SETTING_4],
            option_names=['all'],
            option_default='all'
        )
        setting.add_setting(
            setting='filter_5',
            option_buttons=[RETIRE_SETTING_5_PRESERVE, RETIRE_SETTING_5_ALL],
            option_names=['keep_limit_break', 'all'],
            option_default='all'
        )
        return setting

    def quick_retire_setting_set(self, filter_5='all'):
        """
        Set options of quick retire options.
        The first 4 options are forced to set to:
        - Prioritize Rarity 1: R (Rare)
        - Prioritize Rarity 2: E (Elite)
        - Prioritize Rarity 3: N (Normal)
        - If you own a ship that has been fully Limit Broken, this option
          determines what you want to do with the corresponding duplicate ships.
              Don't Keep

        Args:
            filter_5 (str, None): The fifth option in quick retire options.
                "If you own multiple copies of a ship that has not been fully Limit
                Broken, this option determines what you want to do with those copies."
                'keep_limit_break' for "Keep Enough to Max LB",
                'all' for "Don't Keep"
                None for don't change

        Pages:
            in: IN_RETIREMENT_CHECK, RETIRE_SETTING_ENTER
            out: IN_RETIREMENT_CHECK, RETIRE_SETTING_ENTER
        """
        self._retire_setting_enter()
        self.retire_setting.set(filter_5=filter_5)
        self._retire_setting_quit()

    def server_support_quick_retire_setting_fallback(self):
        """
        Fallback to the correct quick retire settings if user has wrong set.
        """
        return self.config.SERVER in ['cn', 'en', 'jp']
