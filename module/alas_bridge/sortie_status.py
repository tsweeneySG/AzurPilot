"""Fetch sortie roster (energy + level-cap flags) from the Sweeney ALAS bridge."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from module.alas_bridge.game_state import GameState
from module.alas_bridge.rpc import BridgeRpc

RECOVER_PER_TICK = {
    0: 2,  # docks / not in dormitory
    1: 4,  # dorm 1F
    2: 5,  # dorm 2F
}
OATH_BONUS = 1
TICK_SECONDS = 360


def _task_command(config) -> str:
    try:
        return str(getattr(getattr(config, 'task', None), 'command', '') or '')
    except Exception:
        return ''


def _campaign_event(config) -> str:
    return str(getattr(config, 'Campaign_Event', '') or '').strip().lower()


def _is_activity_campaign(config) -> bool:
    event = _campaign_event(config)
    return event not in ('', 'campaign_main')


def _campaign_stage_name(config) -> str:
    task = _task_command(config).lower()
    if task == 'hard':
        return str(getattr(config, 'Hard_HardStage', '') or getattr(config, 'Campaign_Name', '') or '')
    return str(getattr(config, 'Campaign_Name', '') or '')


def normalize_chapter_name(name) -> str:
    if name is None:
        return ''
    s = str(name).strip().lower().replace('–', '-').replace('—', '-').replace(' ', '')
    return s


def hard_roster_family(name) -> str:
    """C1/C2/C3 share one elite roster; D-side another; main 14-x another."""
    n = normalize_chapter_name(name)
    if not n:
        return ''
    if n.startswith('ht'):
        return 'ht'
    rest = n[1:2]
    if n[:1] in ('c', 'd') and (not rest or rest == 's' or rest.isdigit()):
        return n[:1]
    if '-' in n:
        return n.split('-', 1)[0]
    return n


def hard_stage_family_match(want, got) -> bool:
    if not want:
        return True
    if not got:
        return False
    return hard_roster_family(want) == hard_roster_family(got)


def is_activity_hard_stage_name(name) -> bool:
    """Event C/D/HT chapters use CustomFleet elite rosters, not dock 1–6."""
    return hard_roster_family(name) in ('c', 'd', 'ht')


def event_stage_letter(name) -> str:
    """A/B/C/D/HT family letter for live-event stage names. Empty if not those."""
    n = normalize_chapter_name(name)
    if n.startswith('ht'):
        return 'ht'
    if n[:1] in 'abcd' and (len(n) == 1 or n[1:2].isdigit() or n[1:2] == 's'):
        return n[:1]
    return ''


def chapter_track_expected_stage(config) -> str:
    """Stage the live map-prep modal should match.

    Hard binds ``Hard_HardStage``, not ``Campaign_Name`` (that stays the Main
    farm). ``SweeneySortieChapterName`` is only the War Archives catchup
    overlay — leftover B3/D3 from that task must not win on Main 16-4 or the
    mod returns chapter_mismatch and AutoFight TRACKING never sends
    ``use_2x_book``.
    """
    stage = _campaign_stage_name(config).strip()
    task = _task_command(config).lower()
    if task == 'hard':
        return stage
    if task == 'wararchivescatchup':
        overlay = str(getattr(config, 'SweeneySortieChapterName', None) or '').strip()
        return overlay or stage
    return stage


def chapter_track_matches_stage(config, result: Optional[dict]) -> bool:
    """False when TRACKING would sortie A/B SelectFleet for a C/D request (or the reverse)."""
    if not isinstance(result, dict):
        return False
    letter = event_stage_letter(chapter_track_expected_stage(config))
    if not letter:
        return True
    got_name = result.get('chapter_name')
    if got_name:
        got_letter = event_stage_letter(got_name)
        if got_letter and got_letter != letter:
            return False
        if not got_letter and normalize_chapter_name(got_name) != normalize_chapter_name(
                chapter_track_expected_stage(config)):
            return False
    custom = result.get('custom_fleet')
    if letter in ('c', 'd', 'ht') and custom is False:
        return False
    if letter in ('a', 'b') and custom is True:
        return False
    return True


def sortie_args_from_config(config) -> dict:
    """Content hint so the mod can resolve elite/raid/boss-rush rosters from the main menu."""
    task_l = _task_command(config).lower()
    campaign_mode = str(getattr(config, 'Campaign_Mode', 'normal') or 'normal').lower()
    stage_name = _campaign_stage_name(config)
    activity = _is_activity_campaign(config)
    # Event GUI Mode is always `normal` (override.yaml). Auto-Search continue
    # also skips the campaign-UI override to hard. Key C/D/HT off the stage
    # name so live emotion is the elite roster, not dock Fleet 5/6.
    event_elite = activity and is_activity_hard_stage_name(stage_name)

    args = {'source': 'regular'}
    chapter_id = getattr(config, 'SweeneySortieChapterId', None)
    try:
        chapter_id = int(chapter_id) if chapter_id else None
    except (TypeError, ValueError):
        chapter_id = None
    if chapter_id:
        args['chapter_id'] = chapter_id
        args['activity'] = True
        name = str(getattr(config, 'SweeneySortieChapterName', '') or '')
        if name:
            args['chapter_name'] = name
        if bool(getattr(config, 'SweeneySortieHard', False)):
            args['source'] = 'hard'
            return args
        # SelectFleet remaster (WA B/A): dock 5/6, not fleets 1/2.
        args['source'] = 'regular'
        fleet_ids = getattr(config, 'SweeneySortieFleetIds', None)
        parsed = []
        if isinstance(fleet_ids, (list, tuple)):
            for n in fleet_ids:
                try:
                    i = int(n)
                except (TypeError, ValueError):
                    continue
                if i > 0 and i not in parsed:
                    parsed.append(i)
        args['fleet_ids'] = parsed or [5, 6]
        return args
    if task_l in ('raid', 'raiddaily'):
        args['source'] = 'raid'
        args['raid_mode'] = str(getattr(config, 'Raid_Mode', '') or '')
        return args
    if task_l.startswith('coalition'):
        args['source'] = 'boss_rush'
        return args
    if task_l == 'hard' or campaign_mode == 'hard' or event_elite:
        args['source'] = 'hard'
        args['chapter_name'] = stage_name
        args['activity'] = activity
        # Event C/D (and HT) use that event's two elite fleets, not Hard_HardFleet.
        if not args['activity']:
            args['hard_index'] = int(getattr(config, 'Hard_HardFleet', 1) or 1)
        return args

    fleet_ids = []
    for name in ('Fleet_Fleet1', 'Fleet_Fleet2'):
        n = int(getattr(config, name, 0) or 0)
        if n > 0 and n not in fleet_ids:
            fleet_ids.append(n)
    if not fleet_ids:
        fleet_ids = [1, 2]
    args['fleet_ids'] = fleet_ids
    return args


def roster_matches_request(status: Optional[dict], args: Optional[dict] = None, config=None) -> bool:
    """True when get_sortie_status hit the requested elite/regular roster.

    Old mods omit `matched`; treat that as unverified so live energy stays a floor.
    """
    if not isinstance(status, dict) or not status.get('matched'):
        return False
    if args is None and config is not None:
        args = sortie_args_from_config(config)
    args = args or {}
    want_id = args.get('chapter_id')
    got_id = status.get('chapter_id')
    if want_id:
        if not got_id:
            return False
        try:
            return int(want_id) == int(got_id) and bool(status.get('matched'))
        except (TypeError, ValueError):
            return False
    want = str(args.get('source') or 'regular').lower()
    got = str(status.get('source') or '').lower()
    if want == 'hard':
        if got not in ('hard', 'hard_elite'):
            return False
        want_act = bool(args.get('activity'))
        got_type = str(status.get('map_type') or '').lower()
        if want_act and got_type != 'activity_hard':
            return False
        if not want_act and got_type == 'activity_hard':
            return False
        if not hard_stage_family_match(args.get('chapter_name'), status.get('chapter_name')):
            return False
        return True
    if want == 'regular':
        return got in ('regular', '')
    if want == 'raid':
        return got == 'raid'
    if want in ('boss_rush', 'coalition'):
        return got in ('boss_rush', 'coalition')
    if want == 'chapter':
        return got == 'chapter'
    return got == want or not got


def _log(msg: str, warning: bool = False):
    try:
        from module.logger import logger
        if warning:
            logger.warning(msg)
        else:
            logger.info(msg)
    except Exception:
        print(msg)


def parse_sortie_ack(ack) -> Optional[dict]:
    """Validate get_sortie_status ack. None if missing, empty, or malformed."""
    if not isinstance(ack, dict) or not ack.get('ok'):
        _log(f'Sweeney sortie status error: {ack.get("error") if isinstance(ack, dict) else ack}', warning=True)
        return None
    result = ack.get('result')
    if not isinstance(result, dict):
        return None
    fleets = result.get('fleets')
    if not isinstance(fleets, list):
        _log('Sweeney sortie status fleets missing or not a list', warning=True)
        return None
    has_ships = False
    for group in fleets:
        if isinstance(group, dict) and any(isinstance(s, dict) for s in (group.get('ships') or [])):
            has_ships = True
            break
    if not has_ships:
        _log('Sweeney sortie status returned no ships; ignoring live roster', warning=True)
        return None
    return result


def fetch_sortie_status(config, timeout: float = 8.0, args: Optional[dict] = None) -> Optional[dict]:
    """
    Returns:
        dict with keys source, fleets (list of {id, ships:[...]})
        or None on failure.
    """
    try:
        gs = GameState.from_config(config)
        rpc = BridgeRpc(gs)
        if args is None:
            args = sortie_args_from_config(config)
        ack = rpc.send('get_sortie_status', args, timeout=timeout)
    except Exception as e:
        _log(f'Sweeney sortie status failed: {e}', warning=True)
        return None
    return parse_sortie_ack(ack)


def iter_ships(status: Optional[dict]):
    if not isinstance(status, dict):
        return
    for group in status.get('fleets') or []:
        if not isinstance(group, dict):
            continue
        for ship in group.get('ships') or []:
            if isinstance(ship, dict):
                yield group, ship


def ships_in_group(status: Optional[dict], index: int) -> list:
    """1-based group index matching ALAS fleet_index / Emotion Fleet1/Fleet2."""
    if not isinstance(status, dict):
        return []
    fleets = status.get('fleets') or []
    if index < 1 or index > len(fleets):
        return []
    group = fleets[index - 1]
    if not isinstance(group, dict):
        return []
    return [s for s in (group.get('ships') or []) if isinstance(s, dict)]


def min_energy(ships: list) -> Optional[int]:
    vals = []
    for ship in ships:
        try:
            vals.append(int(ship.get('energy')))
        except (TypeError, ValueError):
            continue
    if not vals:
        return None
    return min(vals)


def recover_speed(ship: dict) -> int:
    floor = int(ship.get('dorm_floor') or 0)
    if floor not in RECOVER_PER_TICK:
        floor = 0
    speed = RECOVER_PER_TICK[floor]
    if ship.get('propose'):
        speed += OATH_BONUS
    return max(speed, 1)


def eta_until_energy(ships: list, need: int) -> Optional[datetime]:
    """When every ship in the list will be at least `need`. None if already met or empty."""
    if not ships:
        return None
    now = datetime.now()
    worst = now
    any_wait = False
    for ship in ships:
        try:
            energy = int(ship.get('energy'))
        except (TypeError, ValueError):
            continue
        if energy >= need:
            continue
        deficit = need - energy
        speed = recover_speed(ship)
        ticks = (deficit + speed - 1) // speed
        recovered = (int(now.timestamp()) // TICK_SECONDS + ticks + 1) * TICK_SECONDS
        when = datetime.fromtimestamp(recovered)
        if when > worst:
            worst = when
        any_wait = True
    if not any_wait:
        return None
    return worst


def any_at_cap(status: Optional[dict]) -> Optional[dict]:
    """First ship with at_cap, or None."""
    for _group, ship in iter_ships(status):
        if ship.get('at_cap') or ship.get('hard_cap') or ship.get('soft_cap'):
            return ship
    return None


def level_cap_triggered(config) -> bool:
    """True when SweeneyBridge + StopCondition.LevelCap and a sortie ship is at cap."""
    if not getattr(config, 'Optimization_SweeneyBridge', False):
        return False
    if not getattr(config, 'StopCondition_LevelCap', False):
        return False
    status = fetch_sortie_status(config)
    ship = any_at_cap(status)
    if ship is None:
        return False
    _log(
        f'Level cap reached: {ship.get("name")} '
        f'Lv.{ship.get("level")}/{ship.get("max_level")} '
        f'hard={ship.get("hard_cap")} soft={ship.get("soft_cap")}'
    )
    try:
        config.LV_TRIGGERED = True
    except Exception:
        pass
    return True
