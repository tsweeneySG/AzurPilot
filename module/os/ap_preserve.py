"""月末短猫行动力保留：隐秘/深渊/要塞仍需行动力时不要把保留值踩下去。"""
from datetime import datetime

from module.config.utils import DEFAULT_TIME, get_os_next_reset
from module.logger import logger

OBSCURE_COORD_KEY = 'OpsiObscure.Storage.Storage.HasCoordinate'
ABYSSAL_COORD_KEY = 'OpsiAbyssal.Storage.Storage.HasCoordinate'
STRONGHOLD_KEY = 'OpsiStronghold.Storage.Storage.HasStronghold'

# (task name, storage flag, label for logs)
HIGH_AP_HOLD_TASKS = (
    ('OpsiObscure', OBSCURE_COORD_KEY, 'Obscure loggers'),
    ('OpsiAbyssal', ABYSSAL_COORD_KEY, 'Abyssal loggers'),
    ('OpsiStronghold', STRONGHOLD_KEY, 'Siren Strongholds'),
)


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return DEFAULT_TIME


def month_end_stepped_preserve(remain, is_cl1=False, cross_month=False):
    """
    Vanilla month-end preserve. 2000 means "do not override the user value".

    Args:
        remain (int): Days until OpSi reset (`get_os_reset_remain()`).
        is_cl1 (bool):
        cross_month (bool): OpsiCrossMonth enabled.

    Returns:
        int:
    """
    if remain <= 0:
        return 300 if cross_month else 0
    if remain <= 2:
        return 1000 if is_cl1 else 300
    return 2000


def mark_high_ap_content(config, kind, available):
    """
    Args:
        config:
        kind (str): 'OBSCURE', 'ABYSSAL', or 'STRONGHOLD'.
        available (bool):
    """
    kind = (kind or '').upper()
    if kind == 'OBSCURE':
        key = OBSCURE_COORD_KEY
    elif kind == 'ABYSSAL':
        key = ABYSSAL_COORD_KEY
    elif kind == 'STRONGHOLD':
        key = STRONGHOLD_KEY
    else:
        return
    config.cross_set(key, bool(available))
    logger.attr(f'OpsiHas{kind.title()}', bool(available))


def mark_coordinate_from_item_name(config, name):
    """Set HasCoordinate when a shop/voucher purchase is an Obscure/Abyssal logger."""
    n = (name or '').lower()
    if 'logger' not in n:
        return
    if 'abyssal' in n:
        mark_high_ap_content(config, 'ABYSSAL', True)
    elif 'obscure' in n:
        mark_high_ap_content(config, 'OBSCURE', True)


def should_hold_ap_for_loggers(config, now=None, next_reset=None):
    """
    True if Meowfficer Farming must keep its AP reserve because Strongholds
    or coordinate loggers are still in play this month.

    A task holds AP when it is enabled, still scheduled before the next OpSi
    reset, and not known-empty (storage flag False). Missing flag is treated
    as "might still have content" so a just-enabled task is not starved.

    Args:
        config:
        now (datetime):
        next_reset (datetime): Naive local OpSi reset. None computes from config.

    Returns:
        tuple[bool, str]: (hold, reason)
    """
    if next_reset is None:
        server = config.cross_get('Alas.Emulator.PackageName', default=None)
        next_reset = get_os_next_reset(server=server, now=now)

    reasons = []
    for task, flag_key, label in HIGH_AP_HOLD_TASKS:
        enabled = bool(config.cross_get(f'{task}.Scheduler.Enable', default=False))
        if not enabled:
            continue
        next_run = _as_datetime(config.cross_get(f'{task}.Scheduler.NextRun', default=DEFAULT_TIME))
        if next_run >= next_reset:
            continue
        has = config.cross_get(flag_key, default=None)
        if has is False:
            continue
        reasons.append(label)

    if reasons:
        return True, ', '.join(reasons)
    return False, ''
