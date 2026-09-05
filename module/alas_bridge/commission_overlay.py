"""Bridge-first commission run. Imported by RewardCommission.run when present."""
from module.alas_bridge.actions import (
    bridge_enabled,
    finish_commission,
    get_commissions,
    start_commission,
)
from module.commission.project import Commission
from module.logger import logger
from module.map.map_grids import SelectedGrids


def commission_from_bridge(task):
    """
    Args:
        task: RewardCommission instance.

    Returns:
        bool: True if live EventProxy list was applied (skip OCR).
    """
    if not bridge_enabled(task.config):
        return False
    finish_commission(task.config, all_done=True)
    payload = get_commissions(task.config)
    if not payload:
        return False
    rows = payload.get('commissions') or []
    daily = []
    urgent = []
    max_fleets = int(payload.get('max_fleets') or 4)
    if max_fleets > 0:
        task.max_commission = max_fleets
    for row in rows:
        if not isinstance(row, dict):
            continue
        comm = Commission.from_bridge_row(row, task.config)
        if comm.status == 'expired':
            continue
        logger.attr('Commission', comm)
        if comm.available_time:
            urgent.append(comm)
        else:
            daily.append(comm)
    task.daily = SelectedGrids(daily)
    task.urgent = SelectedGrids(urgent)
    task.daily_choose, task.urgent_choose = task._commission_choose(task.daily, task.urgent)
    for comm in list(task.daily_choose) + list(task.urgent_choose):
        eid = int(getattr(comm, 'event_id', 0) or 0)
        if eid <= 0 or comm.status != 'pending':
            continue
        started = start_commission(task.config, eid)
        if started:
            comm.convert_to_running()
            logger.info(f'Started commission {comm.name} id={eid}')
        else:
            logger.warning(f'Failed to start commission {comm.name} id={eid}')
    logger.info('Sweeney commissions from bridge')
    return True
