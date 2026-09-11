"""Named ALAS-bridge RPC verbs (rewards, island, resources). Screenshot fallback stays in callers."""
from __future__ import annotations

from typing import Optional

from module.alas_bridge.game_state import GameState
from module.alas_bridge.rpc import BridgeRpc


def bridge_enabled(config) -> bool:
    return bool(getattr(config, 'Optimization_SweeneyBridge', False))


def _log(msg: str, warning: bool = False):
    try:
        from module.logger import logger
        if warning:
            logger.warning(msg)
        else:
            logger.info(msg)
    except Exception:
        print(msg)


def send_verb(config, name: str, args: Optional[dict] = None, timeout: float = 12.0) -> Optional[dict]:
    """
    Returns:
        result dict on ok, else None.
    """
    try:
        gs = GameState.from_config(config)
        rpc = BridgeRpc(gs)
        ack = rpc.send(name, args or {}, timeout=timeout)
    except Exception as e:
        _log(f'Sweeney RPC {name} failed: {e}', warning=True)
        return None
    if not isinstance(ack, dict) or not ack.get('ok'):
        err = ack.get('error') if isinstance(ack, dict) else ack
        _log(f'Sweeney RPC {name} error: {err}', warning=True)
        return None
    result = ack.get('result')
    return result if isinstance(result, dict) else {}


def player_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    player = state.get('player')
    return player if isinstance(player, dict) else None


def dock_full_from_heartbeat(config, max_age: float = 3.0) -> Optional[bool]:
    """
    True/False from heartbeat player.dock_full when present; None if unknown/stale.
    """
    player = player_from_heartbeat(config, max_age=max_age)
    if not isinstance(player, dict) or 'dock_full' not in player:
        return None
    return bool(player.get('dock_full'))


def battle_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    battle = state.get('battle')
    return battle if isinstance(battle, dict) else None


def battle_state_from_heartbeat(config, max_age: float = 3.0) -> Optional[str]:
    battle = battle_from_heartbeat(config, max_age=max_age)
    if not battle:
        return None
    state = str(battle.get('state') or '')
    return state or None


BATTLE_SCENE_KEYS = ('BATTLE', 'COMBATLOAD')


def battle_report_overlay_from_state(state: Optional[dict]) -> bool:
    """
    True only while Lua is in BATTLE_REPORT *and* the context is still a battle
    scene. META WorldBoss leaves BattleState at REPORT after the overlay is gone;
    clicking Confirm there hits Collect Reward instead.
    """
    if not isinstance(state, dict):
        return False
    battle = state.get('battle')
    if not isinstance(battle, dict):
        return False
    if str(battle.get('state') or '') != 'BATTLE_REPORT':
        return False
    scene = str(state.get('scene_key') or '')
    # Missing scene_key is not "still in battle" — leftover REPORT on WorldBoss
    # used to blind-click Start Battle / Collect Reward.
    if scene not in BATTLE_SCENE_KEYS:
        return False
    return True


def battle_report_overlay_active(config, max_age: float = 3.0) -> bool:
    if not bridge_enabled(config):
        return False
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return False
    return battle_report_overlay_from_state(state)


def battle_is_fighting(config, max_age: float = 3.0) -> Optional[bool]:
    """
    True while BATTLE_FIGHT/OPENING, False on REPORT/IDLE.
    None when bridge off, stale, or unknown state.
    """
    if not bridge_enabled(config):
        return None
    state = battle_state_from_heartbeat(config, max_age=max_age)
    if state is None:
        return None
    if state in ('BATTLE_FIGHT', 'BATTLE_OPENING'):
        return True
    if state in ('BATTLE_REPORT', 'BATTLE_IDLE'):
        return False
    return None


def combat_idle_skip_allowed(
    config,
    auto: str = 'combat_auto',
    submarine: str = 'do_not_use',
    drop=None,
) -> bool:
    """
    True when combat can poll heartbeat instead of screenshot+PAUSE CV.
    Manual weapons, submarine call UI, and drop recording still need frames.
    """
    if not bridge_enabled(config):
        return False
    if auto != 'combat_auto':
        return False
    if submarine not in ('do_not_use', None, ''):
        return False
    if drop is not None:
        return False
    method = getattr(config, 'DropRecord_CombatRecord', 'do_not')
    if method not in (None, '', 'do_not'):
        return False
    return True


def combat_idle_should_skip(fighting: Optional[bool], latched: bool) -> tuple:
    """
    Decide whether to skip a combat screenshot.

    Heartbeat often goes stale in the battle scene (shared-folder mtime >3s)
    even while PAUSE is on screen. Once latched, keep skipping until heartbeat
    says REPORT/IDLE. Caller should still peek occasionally.

    Returns:
        (skip, latched): skip this screenshot; updated latch.
    """
    if fighting is True:
        return True, True
    if fighting is False:
        return False, False
    return bool(latched), bool(latched)


def fleet_location_from_heartbeat(config, max_age: float = 3.0) -> Optional[tuple]:
    """ALAS map (x, y)=(col, row) of the active fleet, or None."""
    if not bridge_enabled(config):
        return None
    chapter = chapter_from_heartbeat(config, max_age=max_age)
    if not isinstance(chapter, dict) or not chapter.get('active'):
        return None
    row = chapter.get('fleet_row')
    col = chapter.get('fleet_col')
    if row is None or col is None:
        return None
    try:
        return (int(col), int(row))
    except (TypeError, ValueError):
        return None


def event_pt_from_bridge(config) -> Optional[int]:
    """Event PT from heartbeat player.event_pt or RPC get_event_pt."""
    if not bridge_enabled(config):
        return None
    player = player_from_heartbeat(config)
    if isinstance(player, dict) and player.get('event_pt') is not None:
        try:
            return int(player.get('event_pt') or 0)
        except (TypeError, ValueError):
            pass
    result = send_verb(config, 'get_event_pt', timeout=8.0)
    if isinstance(result, dict) and result.get('pt') is not None:
        try:
            return int(result.get('pt') or 0)
        except (TypeError, ValueError):
            return None
    return None


def raid_remain_from_bridge(config, mode: str = '') -> Optional[int]:
    """
    Raid ticket remain from get_task_remains. Single ticket is used as-is.
    Multiple tickets are ordered by stage_id: easy, normal, hard, then ex=last.
    """
    if not bridge_enabled(config):
        return None
    remains = get_task_remains(config)
    if not isinstance(remains, dict):
        return None
    raid = remains.get('raid')
    if not isinstance(raid, list) or not raid:
        return None
    rows = [r for r in raid if isinstance(r, dict) and r.get('remain') is not None]
    if not rows:
        return None

    def _stage_key(row):
        try:
            return int(row.get('stage_id') or 0)
        except (TypeError, ValueError):
            return 0

    rows.sort(key=_stage_key)
    if len(rows) == 1:
        return int(rows[0].get('remain') or 0)
    mode = (mode or '').lower()
    idx_map = {'easy': 0, 'normal': 1, 'hard': 2, 'ex': -1}
    if mode not in idx_map:
        return None
    idx = idx_map[mode]
    pick = rows[-1] if idx < 0 else rows[idx] if idx < len(rows) else None
    if pick is None:
        return None
    return int(pick.get('remain') or 0)


def refresh_stuck_if_battle_fighting(main, max_age: float = 3.0) -> bool:
    """
    Reset stuck timers while heartbeat confirms combat is still running.
    Long boss fights can exceed the default 180s PAUSE allowance otherwise.

    Returns:
        bool: True if timers were refreshed.
    """
    fighting = battle_is_fighting(getattr(main, 'config', None), max_age=max_age)
    if fighting is not True:
        return False
    device = getattr(main, 'device', None)
    if device is None:
        return False
    device.stuck_timer.reset()
    device.stuck_timer_long.reset()
    return True


def get_resources(config, timeout: float = 8.0) -> Optional[dict]:
    """
    Prefer heartbeat player (no RPC round-trip). Fall back to get_resources verb,
    then None so callers can OCR.
    """
    player = player_from_heartbeat(config)
    if isinstance(player, dict) and ('oil' in player or 'gold' in player):
        return player
    result = send_verb(config, 'get_resources', timeout=timeout)
    if result:
        return result
    return player_from_heartbeat(config)


def oil_from_bridge(config) -> Optional[int]:
    """Oil from heartbeat/RPC when bridge is enabled; None to OCR-fallback."""
    if not bridge_enabled(config):
        return None
    player = get_resources(config)
    if not isinstance(player, dict) or 'oil' not in player:
        return None
    return int(player.get('oil') or 0)


def coin_from_bridge(config) -> Optional[int]:
    """Coins (gold) from heartbeat/RPC when bridge is enabled; None to OCR-fallback."""
    if not bridge_enabled(config):
        return None
    player = get_resources(config)
    if not isinstance(player, dict) or 'gold' not in player:
        return None
    return int(player.get('gold') or 0)


def harvest_res(config, kind: str) -> bool:
    """kind: oil | coin | exp"""
    result = send_verb(config, 'harvest_res', {'kind': kind})
    return result is not None


def dorm_one_key(config) -> bool:
    result = send_verb(config, 'dorm_one_key')
    return result is not None


def get_commissions(config) -> Optional[dict]:
    return send_verb(config, 'get_commissions', timeout=10.0)


def finish_commission(config, event_id: int = 0, all_done: bool = False) -> Optional[dict]:
    args = {'all': True} if all_done else {'id': int(event_id)}
    return send_verb(config, 'finish_commission', args, timeout=20.0)


def start_commission(config, event_id: int) -> Optional[dict]:
    return send_verb(config, 'start_commission', {'id': int(event_id)}, timeout=15.0)


def island_run(config) -> Optional[dict]:
    return send_verb(config, 'island_run', timeout=15.0)


def island_fish(config) -> Optional[dict]:
    return send_verb(config, 'island_fish', timeout=45.0)


def island_restaurant(config) -> Optional[dict]:
    return send_verb(config, 'island_restaurant', timeout=45.0)


def island_order(config) -> Optional[dict]:
    return send_verb(config, 'island_order', timeout=20.0)


def get_task_remains(config, timeout: float = 10.0) -> Optional[dict]:
    return send_verb(config, 'get_task_remains', timeout=timeout)


def get_shop_items(config, kind: str = 'merit', timeout: float = 10.0) -> Optional[dict]:
    return send_verb(config, 'get_shop_items', {'kind': kind}, timeout=timeout)


def get_dock_ships(config, limit: int = 500, timeout: float = 15.0) -> Optional[dict]:
    return send_verb(config, 'get_dock_ships', {'limit': int(limit)}, timeout=timeout)


def get_research(config, timeout: float = 10.0) -> Optional[dict]:
    return send_verb(config, 'get_research', timeout=timeout)


def research_receive(config, timeout: float = 15.0) -> Optional[dict]:
    return send_verb(config, 'research_receive', timeout=timeout)


def research_queue_join(config, timeout: float = 15.0) -> Optional[dict]:
    """Move activate-slot research into the planning queue via JOIN_QUEUE_TECHNOLOGY."""
    return send_verb(config, 'research_queue_join', timeout=timeout)


def research_start(config, tech_id=None, pool_id=None, timeout: float = 15.0) -> Optional[dict]:
    """
    Start selected (or given) technology via GAME.START_TECHNOLOGY.
    Skips RESEARCH_START click + consume INFORMATION msgbox.
    """
    args = {}
    if tech_id is not None:
        args['id'] = tech_id
    if pool_id is not None:
        args['pool_id'] = pool_id
    return send_verb(config, 'research_start', args or None, timeout=timeout)


def get_tactical(config, timeout: float = 10.0) -> Optional[dict]:
    return send_verb(config, 'get_tactical', timeout=timeout)


def tactical_receive(config, room_id=None, timeout: float = 15.0) -> Optional[dict]:
    args = {}
    if room_id is not None:
        args['room_id'] = int(room_id)
    return send_verb(config, 'tactical_receive', args or None, timeout=timeout)


def tactical_start(config, ship_id, skill_id, lesson_id, room_id, timeout: float = 15.0) -> Optional[dict]:
    return send_verb(config, 'tactical_start', {
        'ship_id': int(ship_id),
        'skill_id': int(skill_id),
        'lesson_id': int(lesson_id),
        'room_id': int(room_id),
    }, timeout=timeout)


def tactical_quick_finish(config, room_id, timeout: float = 15.0) -> Optional[dict]:
    return send_verb(config, 'tactical_quick_finish', {
        'room_id': int(room_id),
    }, timeout=timeout)


def get_chapter_map(config, timeout: float = 10.0) -> Optional[dict]:
    return send_verb(config, 'get_chapter_map', timeout=timeout)


def os_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    os_state = state.get('os')
    return os_state if isinstance(os_state, dict) else None


def guild_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    guild = state.get('guild')
    return guild if isinstance(guild, dict) else None


def chapter_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    chapter = state.get('chapter')
    return chapter if isinstance(chapter, dict) else None


def level_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    """Heartbeat `level` snapshot (entrance / in_map / info_showing / fleet_showing)."""
    if not bridge_enabled(config):
        return None
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    level = state.get('level')
    return level if isinstance(level, dict) else None


def map_prep_showing_from_heartbeat(config, max_age: float = 3.0) -> Optional[str]:
    """
    'info' if LevelInfoView is showing, 'fleet' if fleet select is showing.
    None if bridge off/stale or the map-prep modal is closed.
    """
    level = level_from_heartbeat(config, max_age=max_age)
    if not isinstance(level, dict):
        return None
    if level.get('info_showing'):
        return 'info'
    if level.get('fleet_showing'):
        return 'fleet'
    return None


def fleet_ids_for_chapter_track(config) -> list:
    """Dock fleet indices ALAS would pick on the fleet-prep screen."""
    ids = []
    for name in ('Fleet_Fleet1', 'Fleet_Fleet2', 'Submarine_Fleet'):
        n = int(getattr(config, name, 0) or 0)
        if n > 0 and n not in ids:
            ids.append(n)
    return ids


def chapter_track(
        config,
        auto_fight: bool = True,
        loop: bool = True,
        open_fleet: bool = False,
        fleet_ids: Optional[list] = None,
        chapter_id: Optional[int] = None,
        timeout: float = 12.0,
) -> Optional[dict]:
    """
    Sortie from the map-prep modal via GAME.TRACKING (or open fleet select).
    Avoids GO / PROCEED / 出撃へ / HANDOVER template clicks.
    SelectFleet chapters (main 16-4 etc.) require fleet_ids; lastFleetIndex is
    only set after the fleet-select UI, which this path skips.
    """
    args = {
        'auto_fight': bool(auto_fight),
        'loop': bool(loop),
    }
    if open_fleet:
        args['open_fleet'] = True
    if chapter_id is not None:
        args['chapter_id'] = int(chapter_id)
    if fleet_ids is None:
        fleet_ids = fleet_ids_for_chapter_track(config)
    if fleet_ids:
        args['fleet_ids'] = [int(x) for x in fleet_ids if int(x) > 0]
    from module.alas_bridge.sortie_status import (
        chapter_track_expected_stage,
        chapter_track_matches_stage,
    )
    expected = chapter_track_expected_stage(config)
    if expected:
        args['chapter_name'] = expected
    result = send_verb(config, 'chapter_track', args, timeout=timeout)
    if not isinstance(result, dict):
        return None
    if result.get('reason') == 'chapter_mismatch':
        _log(f'Sweeney chapter_track mismatch: {result}', warning=True)
        return result
    if result.get('sent') or result.get('already_active') or result.get('opened_fleet'):
        if not chapter_track_matches_stage(config, result):
            _log(f'Sweeney chapter_track mismatch: {result}', warning=True)
            out = dict(result)
            out['reason'] = 'chapter_mismatch'
            out['sent'] = False
            return out
        return result
    return None


def msgbox_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    """
    Heartbeat msgbox snapshot: {showing, has_yes, has_no, content?}.
    None if bridge unavailable/stale.
    """
    if not bridge_enabled(config):
        return None
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    msgbox = state.get('msgbox')
    return msgbox if isinstance(msgbox, dict) else None


def msgbox_yes(config, timeout: float = 8.0) -> bool:
    """Dismiss MsgboxMgr via onYes (no screenshot click). False if none / failed."""
    if not bridge_enabled(config):
        return False
    result = send_verb(config, 'msgbox_yes', timeout=timeout)
    return bool(isinstance(result, dict) and result.get('acted'))


def msgbox_no(config, timeout: float = 8.0) -> bool:
    """Dismiss MsgboxMgr via onNo (no screenshot click). False if none / failed."""
    if not bridge_enabled(config):
        return False
    result = send_verb(config, 'msgbox_no', timeout=timeout)
    return bool(isinstance(result, dict) and result.get('acted'))


def pq_from_heartbeat(config, max_age: float = 3.0) -> Optional[dict]:
    """Heartbeat pq snapshot: {stamina, stamina_max, ...}. None if unavailable."""
    if not bridge_enabled(config):
        return None
    try:
        gs = GameState.from_config(config)
        state = gs.read(max_age=max_age)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    pq = state.get('pq')
    return pq if isinstance(pq, dict) else None


def get_pq_status(config, timeout: float = 5.0) -> Optional[dict]:
    return send_verb(config, 'get_pq_status', timeout=timeout)


def pq_spend_stamina(config, ship: Optional[str] = None, group_id: Optional[int] = None,
                     timeout: float = 35.0) -> Optional[dict]:
    """
    Spend remaining daily PQ vigor via APARTMENT_TRIGGER_FAVOR (talk).
    Returns result dict on success, else None.
    """
    args = {}
    if group_id is not None:
        args['group_id'] = int(group_id)
    if ship:
        args['ship'] = str(ship)
    result = send_verb(config, 'pq_spend_stamina', args, timeout=timeout)
    if not isinstance(result, dict):
        return None
    after = int(result.get('stamina_after') or 0)
    spent = int(result.get('spent') or 0)
    before = int(result.get('stamina_before') or 0)
    if result.get('already_done') or after == 0 or spent >= 1 or before == 0:
        return result
    return None


def get_wa_status(config, timeout: float = 12.0) -> Optional[dict]:
    return send_verb(config, 'get_wa_status', timeout=timeout)


def wa_goto(config, chapter_id: int, remaster_id=None, timeout: float = 20.0) -> Optional[dict]:
    args = {'chapter_id': int(chapter_id)}
    if remaster_id is not None:
        args['remaster_id'] = int(remaster_id)
    return send_verb(config, 'wa_goto', args, timeout=timeout)


def set_mod_flags(
        config,
        force_auto_fight_without_loop=None,
        auto_fight_clear_before_boss=None,
        timeout: float = 8.0,
) -> Optional[dict]:
    args = {}
    if force_auto_fight_without_loop is not None:
        args['force_auto_fight_without_loop'] = bool(force_auto_fight_without_loop)
    if auto_fight_clear_before_boss is not None:
        args['auto_fight_clear_before_boss'] = bool(auto_fight_clear_before_boss)
    return send_verb(config, 'set_mod_flags', args, timeout=timeout)


def apply_fleet_preset(
        config,
        swap: bool = False,
        chapter_id: Optional[int] = None,
        timeout: float = 12.0,
) -> Optional[dict]:
    args = {'swap': bool(swap)}
    if chapter_id is not None:
        args['chapter_id'] = int(chapter_id)
    result = send_verb(config, 'apply_fleet_preset', args, timeout=timeout)
    if not isinstance(result, dict):
        return None
    if result.get('applied'):
        return result
    return None


def pq_shop_buy(config, roses: bool = False, cake: bool = False,
                timeout: float = 30.0) -> Optional[dict]:
    """
    Weekly roses/cake buys via GAME.SHOPPING.
    Returns result when the verb ack is ok (including already-complete / insufficient floor).
    Pure purchase timeouts return None so ALAS can fall back to screenshots.
    """
    if not roses and not cake:
        return {'buys': [], 'skipped': True, 'reason': 'nothing_requested'}
    result = send_verb(config, 'pq_shop_buy', {'roses': bool(roses), 'cake': bool(cake)},
                       timeout=timeout)
    if not isinstance(result, dict):
        return None
    buys = result.get('buys')
    if isinstance(buys, list) and buys:
        any_bought = any(isinstance(b, dict) and b.get('bought') for b in buys)
        any_timeout = any(isinstance(b, dict) and b.get('reason') == 'timeout' for b in buys)
        soft = {
            'limit', 'insufficient', 'insufficient_floor', 'complete_or_limit', 'ok',
        }
        only_soft_or_timeout = all(
            isinstance(b, dict) and (b.get('bought') or (b.get('reason') in soft)
                                     or b.get('reason') == 'timeout')
            for b in buys
        )
        if any_timeout and not any_bought and only_soft_or_timeout:
            # No successful purchase and at least one timeout → screenshot fallback
            if all(
                isinstance(b, dict) and (b.get('reason') == 'timeout' or b.get('bought'))
                for b in buys
            ):
                return None
    return result