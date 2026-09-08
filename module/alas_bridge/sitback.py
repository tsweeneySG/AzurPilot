"""Wait out leftover AutoFight so other tasks do not withdraw a live chapter."""
from __future__ import annotations

import time
from typing import Optional

from module.logger import logger
from module.war_archives_catchup.policy import (
    COMBAT_SCENE_KEYS,
    leftover_off_map_ui,
    sitback_on_dock_scene,
    watch_in_sortie,
    watch_on_map_ui,
)

SKIP_TASKS = ('Restart', 'WarArchivesCatchup')
WAIT_TIMEOUT = 3600
RESUME_TRIES = 36
RESUME_SLEEP = 1.5
RESUME_RETRY_EVERY = 8.0
AUTO_ENABLE_EVERY = 8.0
LOG_EVERY = 30.0
DOCK_TICK_SLEEP = 0.4
DOCK_PEEK_SECONDS = 8.0
FIGHTING_BATTLE = ('BATTLE_FIGHT', 'BATTLE_OPENING')
BATTLE_CLICK_SLEEP = 0.5


def _chapter_dict(state: Optional[dict]) -> dict:
    if not isinstance(state, dict):
        return {}
    chapter = state.get('chapter')
    return chapter if isinstance(chapter, dict) else {}


def _battle_fighting(state: Optional[dict]) -> bool:
    """True while the client is in opening/fight, not the victory overlay."""
    if not isinstance(state, dict):
        return False
    if str(state.get('scene_key') or '') not in ('BATTLE', 'COMBATLOAD'):
        return False
    battle = state.get('battle') if isinstance(state.get('battle'), dict) else {}
    return str(battle.get('state') or '') in FIGHTING_BATTLE


def _auto_fight_on(state: Optional[dict]) -> bool:
    return bool(_chapter_dict(state).get('auto_fight'))


def _need_battle_click(state: Optional[dict]) -> bool:
    """
    Victory / Touch-to-continue while AutoFight is not advancing the overlay.

    Raid and exercise have no ChapterProxy, so auto_fight is missing. Sitting
    heartbeat-only then never taps the results screen.
    """
    if not isinstance(state, dict):
        return False
    if str(state.get('scene_key') or '') != 'BATTLE':
        return False
    if _battle_fighting(state):
        return False
    if _auto_fight_on(state):
        return False
    return True


def _retire_handler(config, device, handler=None):
    if handler is not None and hasattr(handler, 'handle_retirement'):
        return handler
    if config is None or device is None:
        return None
    from module.retire.retirement import Retirement
    return Retirement(config=config, device=device)


def _combat_handler(config, device, handler=None):
    if handler is not None and hasattr(handler, 'handle_battle_status'):
        return handler
    if config is None or device is None:
        return None
    from module.combat.combat import Combat
    return Combat(config=config, device=device)


def handle_sitback_battle_status(config, device, handler=None, state=None) -> bool:
    """
    Click victory / drops / exp when leftover wait cannot rely on AutoFight.

    One tick only. Caller keeps sitting until the scene leaves BATTLE.

    Returns:
        True if a click ran.
    """
    if not _need_battle_click(state):
        return False
    combat = _combat_handler(config, device, handler)
    if combat is None or device is None:
        return False
    device.screenshot()
    try:
        device.stuck_record_clear()
    except Exception:
        pass
    if combat.handle_battle_status():
        logger.info('Sit-back battle status click')
        return True
    if hasattr(combat, 'handle_get_items') and combat.handle_get_items():
        logger.info('Sit-back get-items click')
        return True
    if hasattr(combat, 'handle_exp_info') and combat.handle_exp_info():
        logger.info('Sit-back exp-info click')
        return True
    return False


def handle_sitback_dock_full(
    config,
    device,
    handler=None,
    state=None,
    force_peek=False,
) -> bool:
    """
    Run Sort/Expand/Enhance → retire/enhance while AutoFight is paused on dock full.

    Heartbeat-only sit-back must not screenshot a frozen map. Screenshot when:
    - `player.dock_full` or msgbox `switch_to_shop_tip_noDockyard` (or
      `msgbox.dock_overload` from Lua)
    - `force_peek` / an unknown MsgboxMgr overlay: screenshot and continue
      only if RETIRE_APPEAR_* is on screen

    Clicking Enhance/Retire returns False on the first tick — that is progress,
    not failure. Does not click Auto-Search.

    Returns:
        True if a retirement tick ran.
    """
    from module.alas_bridge.actions import dock_full_from_heartbeat
    from module.war_archives_catchup.policy import (
        sitback_dock_full_from_state,
        sitback_on_dock_scene,
        sitback_unknown_modal,
    )

    hinted = sitback_dock_full_from_state(state)
    if not hinted:
        hinted = dock_full_from_heartbeat(config, max_age=15.0) is True
    on_dock = sitback_on_dock_scene(state)
    peek = force_peek or on_dock or sitback_unknown_modal(state)
    if not hinted and not peek:
        return False
    retire = _retire_handler(config, device, handler)
    if retire is None or device is None:
        return False
    device.screenshot()
    try:
        device.stuck_record_clear()
    except Exception:
        pass
    if not hinted and not on_dock:
        appear = getattr(retire, 'dock_full_popup_appear', None)
        if not callable(appear) or not appear():
            return False
        logger.info('Sit-back dock full (popup on screen)')
    elif not getattr(retire, '_sitback_dock_logged', False):
        logger.info('Sit-back dock full, enhance/retire')
        try:
            retire._sitback_dock_logged = True
        except Exception:
            pass

    def _run_one_click() -> bool:
        if not hasattr(retire, '_retire_handler'):
            return False
        logger.info('Sit-back dock retire page, one-click retire')
        try:
            device.stuck_record_clear()
        except Exception:
            pass
        retire._retire_handler()
        return True

    on_page = False
    if hasattr(retire, '_on_retirement_page'):
        try:
            on_page = bool(retire._on_retirement_page())
        except Exception:
            on_page = False
    if on_page or on_dock:
        if _run_one_click():
            return True
    retired = retire.handle_retirement()
    # RETIRE_APPEAR_1 leaves the popup for the dock; leftover wait must not
    # drop to heartbeat-only before Quick Retire is clicked.
    if not retired:
        time.sleep(0.5)
        device.screenshot()
        try:
            device.stuck_record_clear()
        except Exception:
            pass
        follow = False
        if hasattr(retire, '_on_retirement_page'):
            try:
                follow = bool(retire._on_retirement_page())
            except Exception:
                follow = False
        if follow or on_dock:
            _run_one_click()
    return True


def should_skip_wait(task: str) -> bool:
    """Catchup owns its own resume/watch; Restart must not block on a dead heartbeat."""
    return task in SKIP_TASKS


def _read_state(config, max_age=15.0) -> Optional[dict]:
    try:
        from module.alas_bridge.game_state import GameState
        return GameState.from_config(config).read(max_age=max_age)
    except Exception:
        return None


def _chapter_id(state: Optional[dict]) -> Optional[int]:
    if not isinstance(state, dict):
        return None
    chapter = state.get('chapter') if isinstance(state.get('chapter'), dict) else {}
    try:
        cid = int(chapter.get('id') or 0)
    except (TypeError, ValueError):
        return None
    return cid if cid > 0 else None


def leftover_needs_enable_auto(state: Optional[dict]) -> bool:
    """True on the live map with ChapterProxy auto off (dock-full / toggle)."""
    if not isinstance(state, dict):
        return False
    if leftover_off_map_ui(state) or sitback_on_dock_scene(state):
        return False
    if str(state.get('scene_key') or '') in COMBAT_SCENE_KEYS:
        return False
    if not watch_on_map_ui(state):
        return False
    if _auto_fight_on(state):
        return False
    if not _chapter_dict(state).get('active') and not _chapter_id(state):
        return False
    return True


def _enable_leftover_autofight(config) -> None:
    from module.alas_bridge.actions import set_mod_flags

    logger.info('Leftover AutoFight auto is off on map, enabling')
    set_mod_flags(config, force_auto_fight_without_loop=True)


def _resume_active_chapter(config, chapter_id: int) -> bool:
    from module.alas_bridge.actions import wa_goto

    for attempt in range(RESUME_TRIES):
        result = wa_goto(config, chapter_id=chapter_id)
        state = _read_state(config, max_age=8.0)
        if isinstance(result, dict) and result.get('pending_battle'):
            logger.info(
                f'Leftover AutoFight resumed chapter={chapter_id} try={attempt + 1} (battle)'
            )
            return True
        if watch_on_map_ui(state):
            logger.info(
                f'Leftover AutoFight resumed chapter={chapter_id} try={attempt + 1}'
            )
            return True
        if attempt == 0 or attempt % 5 == 4:
            scene = None if not isinstance(state, dict) else state.get('scene_key')
            page = None if not isinstance(state, dict) else state.get('page')
            flags = []
            if isinstance(result, dict):
                flags = sorted(k for k, v in result.items() if v)
            logger.info(
                f'Leftover AutoFight resume pending chapter={chapter_id} '
                f'try={attempt + 1} scene={scene} page={page} wa_goto={flags}'
            )
        time.sleep(RESUME_SLEEP)
    return False


def wait_leftover_autofight(config, device, timeout: float = WAIT_TIMEOUT, handler=None) -> str:
    """
    Sit on heartbeat until ChapterProxy is idle.

    If the chapter is still active on MAINUI or the Attack/chapter list (client
    restart, or leftover wait bounced to a menu), resume via wa_goto /
    GO_SCENE LEVEL the same way tapping Combat would. Heartbeat-only sit is
    only for the live map or combat flow with AutoFight on. If AutoFight was
    toggled off (dock full, retire, map option), leftover wait re-enables it
    via set_mod_flags / ApplyChapterAutoFightFlag. While sitting, dock-full
    Sort/Expand/Enhance is handled (enhance then retire), then AutoFight
    can continue. Victory overlays with AutoFight off (or no chapter, e.g. raid)
    are clicked through instead of heartbeat-only sit.

    Returns:
        idle: no live chapter (or bridge off)
        ended: waited until the sortie finished
        timeout: still live after timeout
    """
    from module.alas_bridge.actions import bridge_enabled

    if not bridge_enabled(config):
        return 'idle'

    state = _read_state(config, max_age=8.0)
    if not watch_in_sortie(state):
        return 'idle'

    chapter_id = _chapter_id(state)
    scene = str((state or {}).get('scene_key') or '') if isinstance(state, dict) else ''
    chapter = _chapter_dict(state)
    battle = state.get('battle') if isinstance(state, dict) and isinstance(state.get('battle'), dict) else {}
    logger.info(
        f'Leftover AutoFight detected chapter={chapter_id} scene={scene} '
        f'auto={chapter.get("auto_fight")} battle={battle.get("state")} '
        f'on_map={watch_on_map_ui(state)} click={_need_battle_click(state)}'
    )

    if sitback_on_dock_scene(state):
        logger.info('Leftover AutoFight on dock, retire before resume')
    elif leftover_off_map_ui(state) and chapter_id:
        if not _resume_active_chapter(config, chapter_id):
            logger.warning('Leftover AutoFight resume via wa_goto did not reach map UI')

    started = time.time()
    last_log = started
    last_dock_peek = 0.0
    last_resume = 0.0
    last_auto_enable = 0.0
    logged_sit = False
    retire = handler
    while time.time() - started < timeout:
        if device is not None:
            try:
                device.stuck_record_clear()
            except Exception:
                pass
        state = _read_state(config, max_age=15.0)
        stale = not isinstance(state, dict)
        now = time.time()
        on_dock = sitback_on_dock_scene(state)
        peek = on_dock or (stale and (now - last_dock_peek) >= DOCK_PEEK_SECONDS)
        if peek:
            last_dock_peek = now
        if handle_sitback_dock_full(
            config, device, handler=retire, state=state, force_peek=peek
        ):
            time.sleep(DOCK_TICK_SLEEP)
            continue
        if stale:
            time.sleep(1)
            continue
        if not watch_in_sortie(state):
            logger.info('Leftover AutoFight ended')
            return 'ended'
        if leftover_off_map_ui(state):
            cid = _chapter_id(state) or chapter_id
            if cid and (now - last_resume) >= RESUME_RETRY_EVERY:
                last_resume = now
                level = state.get('level') if isinstance(state.get('level'), dict) else {}
                logger.info(
                    f'Leftover AutoFight off map scene={state.get("scene_key")} '
                    f'page={state.get("page")} entrance={level.get("entrance")} '
                    f'in_map={level.get("in_map")} — resume into combat'
                )
                if _resume_active_chapter(config, cid):
                    logged_sit = False
            time.sleep(1)
            continue
        if leftover_needs_enable_auto(state):
            if (now - last_auto_enable) >= AUTO_ENABLE_EVERY:
                last_auto_enable = now
                _enable_leftover_autofight(config)
                logged_sit = False
            time.sleep(1)
            continue
        if handle_sitback_battle_status(
            config, device, handler=handler, state=state
        ):
            time.sleep(DOCK_TICK_SLEEP)
            continue
        if _need_battle_click(state):
            # AutoFight is not advancing this overlay; keep screenshot-clicking.
            time.sleep(BATTLE_CLICK_SLEEP)
            continue
        now = time.time()
        if not logged_sit:
            logger.info('Leftover AutoFight sit-back (heartbeat only, no screenshot)')
            logged_sit = True
        if now - last_log >= LOG_EVERY:
            last_log = now
            chapter = _chapter_dict(state)
            battle = state.get('battle') if isinstance(state.get('battle'), dict) else {}
            logger.attr(
                'LeftoverAutoFight',
                f'{int(now - started)}s chapter={_chapter_id(state)} '
                f'auto={chapter.get("auto_fight")} '
                f'scene={state.get("scene_key")} '
                f'battle={battle.get("state")}',
            )
        time.sleep(1)

    logger.warning('Leftover AutoFight wait timeout')
    return 'timeout'

