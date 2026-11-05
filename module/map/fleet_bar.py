import cv2

from module.base.base import ModuleBase
from module.base.decorator import cached_property
from module.base.utils import area_cross_area, area_in_area, color_mask, crop, point_in_area
from module.logger import logger
from module.map.assets import FLEET_PREPARATION


class FleetOption:
    def __init__(self, area, index=0, selected=False):
        self.area = area
        self.color = (0, 0, 0)
        self.button = area
        self.index = index
        self.selected = selected

    def __repr__(self):
        return f'{self.__class__.__name__}(area={self.area}, index={self.index}, selected={self.selected})'

    def __eq__(self, other):
        if not isinstance(other, FleetOption):
            return NotImplemented
        return self.area == other.area and self.index == other.index and self.selected == other.selected

    def __str__(self):
        return f'{self.__class__.__name__}_{self.index}'

    def pretty(self):
        if self.selected:
            return f'[{self.index}]'
        else:
            return f' {self.index} '


class FleetBarDetector:
    def __init__(self, main, bar, choose=None):
        """
        Args:
            main (ModuleBase):
            bar (Button):
            choose (Button): Optional choose button to check if first option is below recommend
        """
        self.area = bar.button
        self.main = main
        self.image = main.device.image
        self.choose = choose

        self.option_shape = (169, 33)
        # min size: size of letter 1
        # max size: size of option
        self.shape_range = (12, 25, 169 + 5, 55 + 5)

    def _find_option(self, image):
        """
        Find option button from image mask

        Returns:
            list[FleetOptionButton]:
        """
        contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        buttons = []
        for contour in contours:
            # x, y, w, h
            x, y, w, h = cv2.boundingRect(contour)
            if not point_in_area((w, h), self.shape_range, threshold=0):
                continue
            x += self.area[0]
            y += self.area[1]
            area = (x, y, x + w, y + h)
            if self.avoid_area is not None:
                if area_in_area(self.avoid_area, area, threshold=0):
                    continue
                if area_in_area(area, self.avoid_area, threshold=0):
                    continue
                if area_cross_area(self.avoid_area, area, threshold=0):
                    continue

            buttons.append(FleetOption(area))

        return buttons

    @staticmethod
    def _merge_options(options):
        """
        Merge option boxes that belong to the same option.

        A click animation can split one option into two boxes on the same row.
        Boxes whose center y coordinates are close enough are merged into one.

        Args:
            options (list[FleetOption]):

        Returns:
            list[FleetOption]:
        """
        merged = []
        for button in sorted(options, key=lambda x: x.area[1]):
            if not merged:
                merged.append(button)
                continue

            prev = merged[-1]
            prev_center_y = (prev.area[1] + prev.area[3]) / 2
            center_y = (button.area[1] + button.area[3]) / 2
            if abs(center_y - prev_center_y) < 10:
                area = (
                    min(prev.area[0], button.area[0]),
                    min(prev.area[1], button.area[1]),
                    max(prev.area[2], button.area[2]),
                    max(prev.area[3], button.area[3]),
                )
                option = FleetOption(area)
                option.selected = prev.selected or button.selected
                merged[-1] = option
            else:
                merged.append(button)

        return merged

    @cached_property
    def avoid_area(self):
        # delete options from FLEET_PREPARATION
        if self.main.appear(FLEET_PREPARATION, offset=(20, 50)):
            return FLEET_PREPARATION.button
        return None

    def get_options(self):
        """
        Get the detected fleet options.

        Returns:
            tuple[dict[int, FleetOption], str]:
                The options, and the validation error. The error is empty if no
                problem was found.
        """
        image = crop(self.image, self.area, copy=False)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

        # white letter on orange background
        orange = color_mask(image, (251, 231, 157), threshold=30)
        cv2.morphologyEx(orange, cv2.MORPH_OPEN, kernel, dst=orange)
        selected = self._find_option(orange)

        # white letter on light-gray background
        gray = color_mask(image, (203, 208, 222), threshold=30)
        cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel, dst=gray)
        non_selected = self._find_option(gray)

        for button in selected:
            button.selected = True
        options = self._assign_fleet_indexes(self._merge_options(selected + non_selected))

        logger.info('FleetOption: ' + ''.join([button.pretty() for button in options]))
        # validate
        error = []
        amount = len(options)
        if amount == 1:
            error.append(f'FleetOption amount == 1, options={options}')
        elif amount > 6:
            error.append(f'FleetOption amount > 6, options={options}')
        elif 2 <= amount <= 6:
            # check option gaps
            prev_h = 0
            for button in options:
                if prev_h:
                    # options should just next to each other with little gaps
                    gap = button.area[1] - prev_h
                    if gap < self.option_shape[1]:
                        error.append(f'FleetOption gap too small on index={button.index}, options={options}')
                    if gap > self.option_shape[1] * 2:
                        error.append(f'FleetOption gap too large on index={button.index}, options={options}')
                else:
                    # first option should just below recommend button
                    if not self.choose:
                        continue
                    gap = button.area[1] - self.choose.button[3]
                    if gap < 0:
                        error.append(f'FleetOption first option is on the top of choose button, options={options}')
                    if gap > self.option_shape[1]:
                        error.append(f'FleetOption gap too large on first button, options={options}')

                prev_h = button.area[1]
        else:
            # no logs on empty options
            pass
        options = {button.index: button for button in options}
        return options, '\n'.join(error)

    def _assign_fleet_indexes(self, options):
        """Number rows by where they sit in a 6-fleet dropdown.

        A menu that is still opening often shows only the lower rows. Counting
        those boxes from 1 made fleet 5/6 look like fleets 1 and 2 (nyan 16-4,
        2026-10-24 09:30, click y=549). A short bar (submarine) stays sequential
        from the top, because those rows really are the first slots.
        """
        height = self.area[3] - self.area[1]
        tall = height >= self.option_shape[1] * 5
        if not tall:
            for index, button in enumerate(options, start=1):
                button.index = index
            return options

        by_index = {}
        for button in options:
            index = fleet_row_index(button.area, self.area)
            if index is None:
                continue
            button.index = index
            prev = by_index.get(index)
            if prev is None or (button.selected and not prev.selected):
                by_index[index] = button
        return [by_index[key] for key in sorted(by_index)]


def fleet_row_index(area, bar_area, limit=6):
    """Dock-fleet slot from a dropdown row's vertical center.

    Args:
        area (tuple): Detected option box, (left, top, right, bottom).
        bar_area (tuple): Full dropdown search area, tall enough for `limit` rows.
        limit (int): Surface fleets in the menu.

    Returns:
        int | None: 1-based slot, or None when the box is outside the menu.
    """
    height = bar_area[3] - bar_area[1]
    if height <= 0 or limit <= 0:
        return None
    center = (area[1] + area[3]) / 2.0
    stride = height / float(limit)
    index = int(round((center - bar_area[1]) / stride + 0.5))
    if index < 1 or index > limit:
        return None
    return index


def dropdown_ready(options, target):
    """Whether the dropdown can be clicked without guessing a fleet number.

    Ready when the requested slot is visible, the menu has all 6 rows, or the
    only rows are fleets 1 and 2 (an account that has just those two). Two
    lower rows are not a finished menu.
    """
    if not options:
        return False
    if target in options:
        return True
    if len(options) >= 6:
        return True
    return set(options) == {1, 2}
