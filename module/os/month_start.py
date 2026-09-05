"""大世界月初任务轮换。

大世界月在服务器时间 1 日 00:00 切换（日服 UTC+9，国际服 UTC-7）。此时：
- 保持数据记录仪已购买（SpecialRadar）。模组已提供全图视野，
  但原版每月开荒结束会关掉该开关，下月又要每区等 27 分钟。
- 关闭隐秘 / 深渊 / 要塞 / 短猫，避免月初抢开荒和每日的行动力。
  月中再手动打开。

按 `Alas.Emulator.PackageName` 判断服务器，使日服与国际服在正确墙钟翻转。
"""
from module.config.utils import get_os_month_id, os_server_now
from module.logger import logger

OPSI_MONTH_START_DISABLE_TASKS = (
    'OpsiObscure',
    'OpsiAbyssal',
    'OpsiStronghold',
    'OpsiMeowfficerFarming',
)
# First-run on an existing profile: stamp the month without flipping tasks if
# we are already past the opening days (deploying mid-cycle should not yank
# Abyssal/Stronghold that were turned on on purpose).
OPSI_MONTH_START_FIRST_RUN_DAY = 5
LAST_OS_MONTH_KEY = 'OpsiGeneral.Storage.Storage.LastOsMonth'
MONTH_START_ROTATION_KEY = 'OpsiGeneral.OpsiGeneral.MonthStartRotation'
SPECIAL_RADAR_KEY = 'OpsiExplore.OpsiExplore.SpecialRadar'
PACKAGE_KEY = 'Alas.Emulator.PackageName'


def _package_or_server(config):
    return config.cross_get(PACKAGE_KEY, default=None)


def apply_opsi_month_start(config, now=None):
    """
    Apply start-of-month OpSi toggles once per server month.

    Args:
        config (AzurLaneConfig):
        now (datetime): Naive local datetime for tests.

    Returns:
        bool: True if config was modified.
    """
    if getattr(config, 'is_template_config', False):
        return False
    if not config.cross_get(MONTH_START_ROTATION_KEY, default=True):
        return False

    server = _package_or_server(config)
    month_id = get_os_month_id(server=server, now=now)
    last = config.cross_get(LAST_OS_MONTH_KEY, default='') or ''
    if last == month_id:
        return False

    server_now = os_server_now(server=server, now=now)
    first_run = not last
    if first_run and server_now.day > OPSI_MONTH_START_FIRST_RUN_DAY:
        logger.info(
            f'OpSi month-start rotation: first run mid-month ({month_id} day {server_now.day}), '
            f'stamp only so current Obscure/Abyssal/Stronghold/Meowfficer enables stay'
        )
        config.cross_set(LAST_OS_MONTH_KEY, month_id)
        return True

    logger.hr('OpSi month start rotation', level=1)
    logger.attr('OpsiMonth', month_id)
    logger.attr('OpsiServer', server or 'cn')
    logger.attr('OpsiServerNow', server_now.replace(microsecond=0))

    changed = []
    setter = getattr(config, 'multi_set', None)
    ctx = setter() if setter else _NullCtx()
    with ctx:
        if not config.cross_get(SPECIAL_RADAR_KEY, default=False):
            changed.append('OpsiExplore.SpecialRadar=True')
        config.cross_set(SPECIAL_RADAR_KEY, True)
        for task in OPSI_MONTH_START_DISABLE_TASKS:
            key = f'{task}.Scheduler.Enable'
            if config.cross_get(key, default=False):
                changed.append(f'{task} off')
            config.cross_set(key, False)
        config.cross_set(LAST_OS_MONTH_KEY, month_id)

    if changed:
        logger.info(f'OpSi month-start rotation applied: {", ".join(changed)}')
    else:
        logger.info('OpSi month-start rotation: Data Logger on, AP-heavy tasks already off')
    return True


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
