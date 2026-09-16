"""Operation Siren daily handshake via the Sweeney bridge.

Pick / accept / submit / goto use WorldProxy GAME verbs instead of
MISSION_CHECKOUT and ZONE_* template scans. Screenshot path stays the caller
fallback when this returns None.
"""
from __future__ import annotations

import time
from typing import Optional

from module.alas_bridge.actions import (
    bridge_enabled,
    get_os_missions,
    msgbox_from_heartbeat,
    msgbox_yes,
    os_accept_daily,
    os_from_heartbeat,
    os_goto_task,
    os_goto_zone,
    os_submit_tasks,
)

TASK_SIREN = 5
TASK_MONTHLY = 7
STATE_ONGOING = 1
STATE_FINISHED = 2
OS_MAP_TYPES = ('task_chapter', 'complete_chapter', 'base_chapter')
# ALAS DIC_OS_MAP ports are 0-7; world_chapter_colormask / GetEntrance ports are 1-8.
_ALAS_PORT_MAX = 7
_GAME_PORT_MAX = 8


def alas_zone_to_game_entrance(zone_id) -> int:
    """ALAS 港口 ID (NY=0) 转为游戏 atlas entrance ID (NY=1)。战斗海域不变。"""
    zid = int(zone_id)
    if 0 <= zid <= _ALAS_PORT_MAX:
        return zid + 1
    return zid


def game_entrance_to_alas_zone(zone_id) -> int:
    """游戏 atlas entrance ID (NY=1) 转为 ALAS 港口 ID (NY=0)。战斗海域不变。"""
    zid = int(zone_id)
    if 1 <= zid <= _GAME_PORT_MAX:
        return zid - 1
    return zid


def is_siren(task: dict) -> bool:
    return bool(task.get('siren') or task.get('type') == TASK_SIREN)


def is_monthly(task: dict) -> bool:
    return bool(task.get('monthly') or task.get('type') == TASK_MONTHLY)


def is_archive(task: dict) -> bool:
    if task.get('archive') or task.get('collection'):
        return True
    kind = str(task.get('map_kind') or task.get('map_type') or '').lower()
    return 'archive' in kind


def pick_submit_ids(doing, skip_monthly: bool = True) -> list:
    ids = []
    for task in doing or []:
        if not isinstance(task, dict):
            continue
        if int(task.get('state') or 0) != STATE_FINISHED:
            continue
        if skip_monthly and is_monthly(task):
            continue
        tid = task.get('id')
        if tid is not None:
            ids.append(int(tid))
    return ids


def _entrance_set(skip_entrances) -> set:
    out = set()
    for item in skip_entrances or ():
        try:
            out.add(int(item))
        except (TypeError, ValueError):
            continue
    return out


def pick_next_goto(doing, skip_siren: bool = False, skip_monthly: bool = True,
                   skip_entrances=None):
    skip = _entrance_set(skip_entrances)
    ranked = []
    for task in doing or []:
        if not isinstance(task, dict):
            continue
        if int(task.get('state') or 0) != STATE_ONGOING:
            continue
        if skip_monthly and is_monthly(task):
            continue
        if skip_siren and is_siren(task):
            continue
        if not (task.get('following_entrance') or task.get('following_area')):
            continue
        entrance = task.get('following_entrance')
        if entrance is not None:
            try:
                if int(entrance) in skip:
                    continue
            except (TypeError, ValueError):
                pass
        ranked.append(task)
    if not ranked:
        return None
    ranked.sort(key=lambda t: (
        int(t.get('type') or 0),
        -int(t.get('priority') or 0),
        int(t.get('id') or 0),
    ))
    return ranked[0]


def _confirm_os_msgbox(config) -> bool:
    snap = msgbox_from_heartbeat(config, max_age=3.0)
    if not isinstance(snap, dict) or not snap.get('showing') or not snap.get('has_yes'):
        return False
    return msgbox_yes(config)


def wait_os_arrival(config, zone_id=None, timeout: float = 25.0,
                    require_in_map: bool = False) -> Optional[dict]:
    """Poll heartbeat until in-zone map, globe pin, or timeout."""
    deadline = time.time() + max(1.0, float(timeout))
    last = None
    while time.time() < deadline:
        _confirm_os_msgbox(config)
        last = os_from_heartbeat(config, max_age=3.0)
        if isinstance(last, dict):
            if last.get('in_map'):
                if zone_id is None:
                    return last
                got = last.get('zone_id')
                if got is None or int(got) == int(zone_id):
                    return last
            if (not require_in_map
                    and last.get('ui') in ('globe', 'overview')
                    and last.get('pinned')):
                return last
        time.sleep(0.4)
    return last if isinstance(last, dict) else None


ALAS_TYPE_TO_MAP = {
    'SAFE': 'complete_chapter',
    'DANGEROUS': 'base_chapter',
    'OBSCURE': 'teasure_chapter',
    'ABYSSAL': 'teasure_chapter',
    'STRONGHOLD': 'sairen_chapter',
    'ARCHIVE': 'task_chapter',
}


def map_types_for_alas(types) -> list:
    """Map ALAS globe types (SAFE/DANGEROUS/...) to World.ReplacementMapType."""
    if types is None:
        seq = ()
    elif isinstance(types, str):
        seq = (types,)
    else:
        seq = tuple(types)
    out = []
    seen = set()
    for item in seq:
        kind = ALAS_TYPE_TO_MAP.get(str(item).upper())
        if kind and kind not in seen:
            seen.add(kind)
            out.append(kind)
    if 'base_chapter' not in seen:
        out.append('base_chapter')
    return out


def run_os_globe_goto(
        config, zone_id, types=None, timeout: float = 25.0, *,
        alas_ids: bool = True) -> Optional[bool]:
    """
    Transport to zone_id via OpTransport.

    Args:
        alas_ids: True if zone_id is an ALAS DIC_OS_MAP id (NY=0).
            Heartbeat / following_entrance ids are game atlas ids (NY=1).

    Returns:
        True: arrived in-map at zone_id.
        False: already there.
        None: bridge off/miss — caller keeps globe clicks.
    """
    if not bridge_enabled(config):
        return None
    zid = int(zone_id)
    game_id = alas_zone_to_game_entrance(zid) if alas_ids else zid
    prefer = map_types_for_alas(types)
    result = os_goto_zone(config, game_id, map_types=prefer)
    if result is None:
        return None
    if result.get('pending_scene'):
        time.sleep(2.0)
        result = os_goto_zone(config, game_id, map_types=prefer)
        if result is None:
            return None
    already = bool(result.get('already_active'))
    # GetInMap flips true at SetInMap start; still wait for map chrome.
    # Heartbeat zone_id is the game atlas id.
    state = wait_os_arrival(
        config, zone_id=game_id, timeout=timeout, require_in_map=True)
    if not isinstance(state, dict) or not state.get('in_map'):
        return None
    got = state.get('zone_id')
    if got is not None and int(got) != int(game_id):
        return None
    return False if already else True


def run_os_accept_daily(config, skip_siren: bool = False) -> Optional[bool]:
    """
    Accept daily OS missions without the overview UI.

    Returns:
        True: accepted or nothing left.
        False: task cap (same as screenshot 'cannot accept more').
        None: bridge off/miss — caller keeps screenshot path.
    """
    if not bridge_enabled(config):
        return None
    for _ in range(4):
        result = os_accept_daily(config, skip_siren=skip_siren)
        if result is None:
            return None
        if result.get('pending_refresh'):
            time.sleep(1.2)
            continue
        if result.get('reason') == 'limit':
            return False
        return True
    return True


def run_os_mission_handshake(config, skip_siren: bool = False, timeout: float = 10.0,
                             goto: bool = True, skip_entrances=None):
    """
    Submit finished missions and jump to the next daily zone.

    Arrival is in-zone map only. Globe + pinned is not enough for AutoSearch.

    Returns:
        'pinned_at_mission_zone' | 'already_at_mission_zone' |
        'pinned_at_archive_zone' | False (no more tasks).
        None if the bridge cannot complete the handshake.
    """
    if not bridge_enabled(config):
        return None
    snap = get_os_missions(config)
    if not isinstance(snap, dict) or snap.get('loaded') is False:
        return None
    submit_ids = pick_submit_ids(snap.get('doing'))
    if submit_ids:
        os_submit_tasks(config, ids=submit_ids)
        time.sleep(0.8)
        snap = get_os_missions(config) or snap
    if not goto:
        return False
    nxt = pick_next_goto(
        snap.get('doing'), skip_siren=skip_siren, skip_entrances=skip_entrances)
    if nxt is None:
        return False
    jumped = os_goto_task(config, task_id=int(nxt['id']), skip_siren=skip_siren)
    if jumped is None:
        return None
    if jumped.get('pending_scene'):
        time.sleep(2.0)
        jumped = os_goto_task(config, task_id=int(nxt['id']), skip_siren=skip_siren)
        if jumped is None:
            return None
    zone_id = nxt.get('following_entrance') or jumped.get('following_entrance')
    state = wait_os_arrival(
        config, zone_id=zone_id, timeout=timeout, require_in_map=True)
    if not isinstance(state, dict):
        state = {}
    need_transport = not state.get('in_map')
    if zone_id is not None and state.get('in_map'):
        got = state.get('zone_id')
        if got is None or int(got) != int(zone_id):
            need_transport = True
    if need_transport and zone_id is not None:
        transported = os_goto_zone(config, int(zone_id), map_types=list(OS_MAP_TYPES))
        if transported is None and not jumped.get('already_in_zone'):
            return None
        time.sleep(0.6)
        state = wait_os_arrival(
            config, zone_id=zone_id, timeout=timeout, require_in_map=True) or state
    if not state.get('in_map'):
        extra = list(skip_entrances or [])
        if zone_id is not None:
            try:
                zid = int(zone_id)
            except (TypeError, ValueError):
                return False
            if zid not in extra:
                extra.append(zid)
                return run_os_mission_handshake(
                    config, skip_siren=skip_siren, timeout=timeout, goto=True,
                    skip_entrances=extra)
        return False
    if zone_id is not None:
        got = state.get('zone_id')
        if got is not None and int(got) != int(zone_id):
            extra = list(skip_entrances or [])
            try:
                extra.append(int(zone_id))
            except (TypeError, ValueError):
                return False
            return run_os_mission_handshake(
                config, skip_siren=skip_siren, timeout=timeout, goto=True,
                skip_entrances=extra)
    if is_archive(nxt) or jumped.get('archive'):
        return 'pinned_at_archive_zone'
    if jumped.get('already_in_zone'):
        return 'already_at_mission_zone'
    return 'pinned_at_mission_zone'
