"""作战档案补完：下一张图选择与自律寻敌开关策略。"""
from __future__ import annotations

from typing import Optional


ACHIEVE_KILL_BOSS = 1
ACHIEVE_KILL_ENEMY = 2
ACHIEVE_KILL_ALL = 3


def chapter_incomplete(ch: Optional[dict]) -> bool:
    """True when an unlocked chapter is missing clear % or stars."""
    if not isinstance(ch, dict):
        return False
    if not ch.get('unlocked'):
        return False
    if ch.get('incomplete') is True:
        return True
    if int(ch.get('clear_pct') or 0) < 100:
        return True
    earned = int(ch.get('stars_earned') or 0)
    total = int(ch.get('stars_total') or 0)
    return total > 0 and earned < total


def chapter_need_hide(ch: Optional[dict]) -> bool:
    """True when hide=1 and already 100% — UI removes the node, stars are frozen."""
    if not isinstance(ch, dict):
        return False
    return ch.get('need_hide') is True


def chapter_targetable(ch: Optional[dict]) -> bool:
    """Incomplete and still enterable (not a hidden-cleared extra stage)."""
    return chapter_incomplete(ch) and not chapter_need_hide(ch)


def _iter_chapters(status: Optional[dict]):
    if not isinstance(status, dict):
        return
    packs = status.get('packs')
    if not isinstance(packs, list):
        return
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        chapters = pack.get('chapters')
        if not isinstance(chapters, list):
            chapters = pack.get('maps')
        if not isinstance(chapters, list):
            continue
        for ch in chapters:
            if isinstance(ch, dict):
                yield pack, ch


def pick_next_chapter(status: Optional[dict]) -> Optional[dict]:
    """
    First accessible incomplete chapter: remaster id order, then config_data order.
    Skips locked maps and hide=1 chapters that are already 100% (cannot re-enter).
    Bonus drop_gain is never a target.
    """
    if not isinstance(status, dict):
        return None
    nxt = status.get('next')
    if isinstance(nxt, dict) and nxt.get('id') and chapter_targetable(nxt):
        return nxt
    for _pack, ch in _iter_chapters(status):
        if chapter_targetable(ch):
            return ch
    return None


def _missing_entries(ch: dict) -> list:
    missing = ch.get('missing')
    if not isinstance(missing, list):
        return []
    out = []
    for item in missing:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            field = item.lower()
            if field in ('kill_all', 'kill_all_enemies'):
                out.append({'type': ACHIEVE_KILL_ALL, 'field': field, 'remaining': 0})
            elif field in ('kill_enemy', 'kill_enemy_count'):
                out.append({'type': ACHIEVE_KILL_ENEMY, 'field': field, 'remaining': 0})
            elif field in ('kill_boss', 'kill_boss_count'):
                out.append({'type': ACHIEVE_KILL_BOSS, 'field': field, 'remaining': 0})
            else:
                out.append({'type': 0, 'field': field, 'remaining': 0})
    return out


def flags_for_chapter(ch: Optional[dict]) -> dict:
    """
    AutoFight flags for one catchup sortie.

    clear-before-boss: missing all-enemies star, or escort remaining > boss_refresh.
    force-without-loop: native loop not available (progress < 100).
    """
    if not isinstance(ch, dict):
        return {
            'force_auto_fight_without_loop': True,
            'auto_fight_clear_before_boss': False,
        }
    missing = _missing_entries(ch)
    types = set()
    escort_remaining = 0
    for item in missing:
        a_type = int(item.get('type') or 0)
        types.add(a_type)
        if a_type == ACHIEVE_KILL_ENEMY:
            escort_remaining = max(escort_remaining, int(item.get('remaining') or 0))
    boss_refresh = int(ch.get('boss_refresh') or 0)
    clear_before = ACHIEVE_KILL_ALL in types or (
        ACHIEVE_KILL_ENEMY in types and escort_remaining > boss_refresh
    )
    can_loop = bool(ch.get('can_loop'))
    if ch.get('exist_loop') is False:
        can_loop = False
    return {
        'force_auto_fight_without_loop': not can_loop,
        'auto_fight_clear_before_boss': clear_before,
    }


COMBAT_SCENE_KEYS = {
    'BATTLE',
    'COMBATLOAD',
    'TRANSITION',
    'BOSSRUSH_PASSED_COMBATLOAD',
}
BATTLE_BUSY = ('BATTLE_FIGHT', 'BATTLE_OPENING', 'BATTLE_REPORT')

DATA_KEY_CONTENT_HINTS = (
    'data key',
    '档案秘钥',
    '檔案密鑰',
    'データキー',
    '데이터 키',
)
LOW_EMOTION_CONTENT_HINTS = (
    'exhausted',
    'low mood',
    'morale',
    '疲劳',
    '疲勞',
    '疲労',
    '지침',
    '心情',
)
# BeginStageCommand.DockOverload / GetShipCommand NoPosMsgBox
# i18n("switch_to_shop_tip_noDockyard") — Sort / Expand / Enhance.
DOCK_FULL_CONTENT_HINTS = (
    'sort or expand your dock',
    'please sort or expand',
    '船坞已满',
    '船塢已滿',
    'ドックが一杯',
    '도크에 공간이 없습니다',
)


def is_data_key_msgbox(msgbox: Optional[dict]) -> bool:
    """True when MsgboxMgr is the remaster Data Key unlock dialog."""
    if not isinstance(msgbox, dict):
        return False
    if msgbox.get('showing') is not True:
        return False
    content = str(msgbox.get('content') or '')
    if not content:
        return False
    lowered = content.lower()
    for hint in DATA_KEY_CONTENT_HINTS:
        if hint in content or hint in lowered:
            return True
    return False


def is_low_emotion_msgbox(msgbox: Optional[dict]) -> bool:
    """True when MsgboxMgr is the fleet exhausted / low-mood confirm."""
    if not isinstance(msgbox, dict):
        return False
    if msgbox.get('showing') is not True:
        return False
    content = str(msgbox.get('content') or '')
    if not content:
        return False
    lowered = content.lower()
    for hint in LOW_EMOTION_CONTENT_HINTS:
        if hint in content or hint in lowered:
            return True
    return False


def is_dock_full_msgbox(msgbox: Optional[dict]) -> bool:
    """True when MsgboxMgr is Sort / Expand / Enhance (dock overload)."""
    if not isinstance(msgbox, dict):
        return False
    if msgbox.get('showing') is not True:
        return False
    if msgbox.get('dock_overload') is True:
        return True
    content = str(msgbox.get('content') or '')
    if not content:
        return False
    lowered = content.lower()
    for hint in DOCK_FULL_CONTENT_HINTS:
        if hint in content or hint in lowered:
            return True
    return False


def sitback_dock_full_from_state(state: Optional[dict]) -> bool:
    """True when heartbeat player.dock_full or the dock-overload msgbox is up."""
    if not isinstance(state, dict):
        return False
    player = state.get('player') if isinstance(state.get('player'), dict) else {}
    if player.get('dock_full') is True:
        return True
    return is_dock_full_msgbox(state.get('msgbox'))


def sitback_unknown_modal(state: Optional[dict]) -> bool:
    """True when a MsgboxMgr overlay is showing but is not a known dock tip."""
    if not isinstance(state, dict):
        return False
    if sitback_dock_full_from_state(state):
        return False
    msgbox = state.get('msgbox') if isinstance(state.get('msgbox'), dict) else {}
    if msgbox.get('showing') is True:
        return True
    overlays = state.get('overlays')
    if isinstance(overlays, (list, tuple)) and 'MsgboxShowing' in overlays:
        return True
    return False


def sitback_on_dock_scene(state: Optional[dict]) -> bool:
    """True when heartbeat says the dock UI is up (retire/enhance/normal)."""
    if not isinstance(state, dict):
        return False
    if str(state.get('scene_key') or '') == 'DOCKYARD':
        return True
    return str(state.get('page') or '') == 'page_dock'


def battles_for_emotion(ch: Optional[dict], flags: Optional[dict] = None) -> int:
    """How many fights check_reduce should budget for this remaster sortie."""
    flags = flags or {}
    remaining = 0
    if isinstance(ch, dict):
        for item in ch.get('missing') or []:
            if not isinstance(item, dict):
                continue
            if int(item.get('type') or 0) == 2:
                remaining = max(remaining, int(item.get('remaining') or 0))
    if flags.get('auto_fight_clear_before_boss') and remaining > 0:
        return min(12, max(6, remaining + 1))
    return 6


def watch_on_map_ui(state: Optional[dict]) -> bool:
    """True when the client is actually on the sortie UI (not Home with an active chapter).

    Attack hub (`level.entrance`) and LEVEL chapter list (`in_map` false) are
    not the map. Stale BATTLE_FIGHT/REPORT off the battle scene is not either.
    """
    if not isinstance(state, dict):
        return False
    scene = str(state.get('scene_key') or '')
    if scene in COMBAT_SCENE_KEYS:
        return True
    if scene == 'MAINUI':
        return False
    level = state.get('level') if isinstance(state.get('level'), dict) else {}
    # Stage view showing is the map even if entranceStatus lingered true.
    if level.get('in_map'):
        return True
    if level.get('entrance') is True:
        return False
    return False


def leftover_off_map_ui(state: Optional[dict]) -> bool:
    """True when a live chapter is on Home / Attack hub / chapter list.

    AutoFight cannot advance there; leftover wait must `wa_goto` into combat
    (same as tapping Combat) instead of heartbeat-only sit.
    """
    if not isinstance(state, dict):
        return False
    if sitback_on_dock_scene(state):
        return False
    if not watch_in_sortie(state):
        return False
    if watch_on_map_ui(state):
        return False
    scene = str(state.get('scene_key') or '')
    if scene in COMBAT_SCENE_KEYS:
        return False
    return True


def watch_in_sortie(state: Optional[dict]) -> bool:
    """True while a remaster sortie is still running (map, combat, or load)."""
    if not isinstance(state, dict):
        return False
    scene = str(state.get('scene_key') or '')
    if scene in COMBAT_SCENE_KEYS:
        return True
    chapter = state.get('chapter') if isinstance(state.get('chapter'), dict) else {}
    level = state.get('level') if isinstance(state.get('level'), dict) else {}
    battle = state.get('battle') if isinstance(state.get('battle'), dict) else {}
    if chapter.get('active') or level.get('in_map'):
        return True
    if str(battle.get('state') or '') in BATTLE_BUSY:
        return True
    return False


def wa_goto_ready_to_sit(result: Optional[dict], state: Optional[dict]) -> bool:
    """
    True when wa_goto means the sortie UI is up.

    `already_in_map` from an older mod while scene is MAINUI is not ready:
    ChapterProxy can stay active after an app restart with AutoFight still
    running, and sitting on Home trips GameStuckError.
    """
    if not isinstance(result, dict):
        return False
    if result.get('pending_battle'):
        return True
    if result.get('resume_active'):
        return False
    if not result.get('already_in_map'):
        return False
    if not isinstance(state, dict):
        return False
    if watch_on_map_ui(state):
        return True
    scene = str(state.get('scene_key') or '')
    if scene in COMBAT_SCENE_KEYS:
        return True
    return False


def watch_map_ended(state: Optional[dict], *, saw_in_map: bool, grace_ok: bool) -> bool:
    """
    True only on a fresh LEVEL heartbeat after the sortie really left the map.

    Stale/missing state is unknown, not ended. Combat load and BATTLE must
    not look like map-select.
    """
    if not saw_in_map or not grace_ok or not isinstance(state, dict):
        return False
    if watch_in_sortie(state):
        return False
    scene = str(state.get('scene_key') or '')
    if scene and scene != 'LEVEL':
        return False
    return True


def incomplete_bonus(status: Optional[dict]) -> list:
    """drop_gain rows still short of the required count (log only, not targeted)."""
    if not isinstance(status, dict):
        return []
    rows = status.get('bonus')
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get('incomplete') is True:
            out.append(row)
            continue
        have = int(row.get('have') or 0)
        need = int(row.get('need') or 0)
        if need > 0 and have < need:
            out.append(row)
    return out


def hidden_incomplete(status: Optional[dict]) -> list:
    """hide=1 chapters already 100% with leftover stars (cannot re-enter)."""
    out = []
    for _pack, ch in _iter_chapters(status):
        if chapter_need_hide(ch) and chapter_incomplete(ch):
            out.append(ch)
        elif ch.get('need_hide') is True:
            earned = int(ch.get('stars_earned') or 0)
            total = int(ch.get('stars_total') or 0)
            if total > 0 and earned < total:
                out.append(ch)
    return out
