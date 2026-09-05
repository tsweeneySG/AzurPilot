"""作战档案补完：桥接驱动模组自律寻敌，AzurPilot 只监视。"""
from __future__ import annotations

import time
from typing import Optional

from module.campaign.campaign_event import CampaignEvent
from module.combat.combat import Combat
from module.combat.emotion import Emotion
from module.config.config import TaskEnd
from module.exception import CampaignEnd, RequestHumanTakeover, ScriptEnd
from module.logger import logger
from module.notify import handle_notify
from module.war_archives_catchup.policy import (
    battles_for_emotion,
    flags_for_chapter,
    hidden_incomplete,
    incomplete_bonus,
    is_data_key_msgbox,
    is_low_emotion_msgbox,
    pick_next_chapter,
    wa_goto_ready_to_sit,
    watch_in_sortie,
    watch_map_ended,
    watch_on_map_ui,
)

STUCK_SECONDS = 90
ENTER_MAP_SECONDS = 180
WATCH_TIMEOUT = 1800
ENDED_HOLD_SECONDS = 8
SORTIE_GRACE_SECONDS = 25
WA_GOTO_TRIES = 36
WA_GOTO_SLEEP = 1.5


class WarArchivesCatchup(CampaignEvent, Combat):
    def __init__(self, config, device):
        super().__init__(config, device)
        self.emotion = Emotion(config=config)
        self._flag_restore = None
        self._bonus_logged = False
        self._hidden_logged = False
        self._last_sortie_skip = False

    def _bridge_ok(self) -> bool:
        try:
            from module.alas_bridge.actions import bridge_enabled, player_from_heartbeat
        except Exception as e:
            logger.warning(f'WarArchivesCatchup bridge import failed: {e}')
            return False
        if not bridge_enabled(self.config):
            return False
        player = player_from_heartbeat(self.config, max_age=8.0)
        return isinstance(player, dict)

    def _read_state(self, max_age=8.0):
        try:
            from module.alas_bridge.game_state import GameState
            return GameState.from_config(self.config).read(max_age=max_age)
        except Exception as e:
            logger.info(f'WarArchivesCatchup heartbeat miss: {e}')
            return None

    def _stop_no_bridge(self):
        logger.error('WarArchivesCatchup requires Optimization.SweeneyBridge')
        self.config.task_delay(minute=30)
        self.config.task_stop('WarArchivesCatchup: SweeneyBridge off or stale')

    def _disable_done(self, reason):
        logger.hr(reason)
        self.config.Scheduler_Enable = False
        handle_notify(
            self.config.Error_OnePushConfig,
            title=f'Alas <{self.config.config_name}> War Archives catchup finished',
            content=f'<{self.config.config_name}> {reason}',
        )
        self.config.task_stop(reason)

    def _bind_sortie(self, target: dict):
        self.config.SweeneySortieChapterId = int(target.get('id') or 0)
        hard = bool(target.get('hard'))
        self.config.SweeneySortieHard = hard
        self.config.SweeneySortieChapterName = str(target.get('name') or '')
        # SelectFleet remaster uses dock 5/6 (swap 6/5 on hard CustomFleet maps).
        self.config.SweeneySortieFleetIds = [6, 5] if hard else [5, 6]

    def _log_bonus(self, status: dict):
        if self._bonus_logged:
            return
        self._bonus_logged = True
        rows = incomplete_bonus(status)
        if not rows:
            return
        logger.info(f'BONUS incomplete {len(rows)} drop_gain row(s) (not targeted)')
        for row in rows[:8]:
            logger.info(
                f"BONUS incomplete {row.get('chapter_name') or row.get('chapter_id')} "
                f"{row.get('have')}/{row.get('need')} drop={row.get('drop')} (not targeted)"
            )
        extra = len(rows) - 8
        if extra > 0:
            logger.info(f'BONUS incomplete … {extra} more (not targeted)')

    def _log_hidden(self, status: dict):
        if self._hidden_logged:
            return
        self._hidden_logged = True
        rows = hidden_incomplete(status)
        if not rows:
            return
        logger.info(
            f'SKIP hidden-cleared {len(rows)} chapter(s) '
            f'(cannot re-enter for leftover stars)'
        )
        for row in rows[:8]:
            logger.info(
                f"SKIP hidden-cleared {row.get('name') or row.get('id')} "
                f"{row.get('clear_pct')}% "
                f"stars={row.get('stars_earned')}/{row.get('stars_total')}"
            )
        extra = len(rows) - 8
        if extra > 0:
            logger.info(f'SKIP hidden-cleared … {extra} more')

    def _set_flags(self, target: dict):
        from module.alas_bridge.actions import set_mod_flags
        flags = flags_for_chapter(target)
        logger.info(
            f"WA flags clear_before_boss={flags['auto_fight_clear_before_boss']} "
            f"force_noloop={flags['force_auto_fight_without_loop']}"
        )
        result = set_mod_flags(
            self.config,
            force_auto_fight_without_loop=flags['force_auto_fight_without_loop'],
            auto_fight_clear_before_boss=flags['auto_fight_clear_before_boss'],
        )
        if isinstance(result, dict) and self._flag_restore is None:
            prev = result.get('previous')
            if isinstance(prev, dict):
                self._flag_restore = prev
        return flags

    def _restore_flags(self):
        if not isinstance(self._flag_restore, dict):
            return
        try:
            from module.alas_bridge.actions import set_mod_flags
            set_mod_flags(
                self.config,
                force_auto_fight_without_loop=self._flag_restore.get(
                    'forceAutoFightWithoutLoop', False),
                auto_fight_clear_before_boss=self._flag_restore.get(
                    'autoFightClearBeforeBoss', False),
            )
        except Exception as e:
            logger.warning(f'WarArchivesCatchup restore flags failed: {e}')
        self._flag_restore = None

    def _wa_goto(self, target: dict) -> Optional[dict]:
        from module.alas_bridge.actions import wa_goto
        chapter_id = int(target.get('id') or 0)
        remaster_id = target.get('remaster_id')
        for attempt in range(WA_GOTO_TRIES):
            result = wa_goto(self.config, chapter_id=chapter_id, remaster_id=remaster_id)
            if not isinstance(result, dict):
                logger.warning(f'wa_goto failed attempt={attempt + 1}')
                time.sleep(WA_GOTO_SLEEP)
                continue
            state = self._read_state(max_age=8.0)
            if wa_goto_ready_to_sit(result, state):
                logger.info(
                    f"wa_goto already in chapter "
                    f"battle={result.get('pending_battle')} try={attempt + 1}"
                )
                return result
            if result.get('already_in_map') and not wa_goto_ready_to_sit(result, state):
                scene = None if not isinstance(state, dict) else state.get('scene_key')
                logger.info(
                    f'wa_goto already_in_map but scene={scene}, resume try={attempt + 1}'
                )
                time.sleep(WA_GOTO_SLEEP)
                continue
            if result.get('info_showing'):
                return result
            logger.info(
                f"wa_goto pending scene={result.get('pending_scene')} "
                f"map={result.get('pending_map')} "
                f"resume={result.get('resume_active')} try={attempt + 1}"
            )
            time.sleep(WA_GOTO_SLEEP)
        return None

    def _apply_fleet(self, target: dict) -> dict:
        from module.alas_bridge.actions import apply_fleet_preset
        swap = bool(target.get('hard'))
        result = apply_fleet_preset(
            self.config, swap=swap, chapter_id=int(target.get('id') or 0))
        if not isinstance(result, dict) or not result.get('applied'):
            logger.error('apply_fleet_preset failed (empty fleet, in_event, or no chapter)')
            raise RequestHumanTakeover
        logger.info(
            f"WA fleet preset swap={swap} custom={result.get('custom_fleet')} "
            f"ids={result.get('fleet_ids')}"
        )
        return result

    def _sortie(self, target: dict, fleet_result: dict, flags: dict) -> bool:
        from module.alas_bridge.actions import chapter_track
        self._last_sortie_skip = False
        fleet_ids = fleet_result.get('fleet_ids') if isinstance(fleet_result, dict) else None
        custom = bool(fleet_result.get('custom_fleet')) if isinstance(fleet_result, dict) else False
        loop = bool(target.get('can_loop')) and not flags.get('force_auto_fight_without_loop')
        if target.get('exist_loop') is False:
            loop = False
        # Empty list skips config Fleet_Fleet1 defaults (this task has no Fleet group).
        result = chapter_track(
            self.config,
            auto_fight=True,
            loop=loop,
            chapter_id=int(target.get('id') or 0),
            fleet_ids=[] if custom else (fleet_ids or []),
        )
        if not isinstance(result, dict):
            logger.warning('chapter_track failed')
            return False
        logger.info(f'Sweeney chapter_track: {result}')
        if result.get('reason') == 'need_hide':
            logger.warning(
                f"chapter_track skipped need_hide id={result.get('chapter_id')}"
            )
            self._last_sortie_skip = True
            return False
        return bool(result.get('sent') or result.get('already_active') or result.get('confirmed_ticket'))

    def _confirm_data_key_popup(self, *, screenshot=False, msgbox=None) -> bool:
        """
        Confirm the remaster Data Key dialog only (not retreat / emotion).
        TrackingCommand blocks on this until onYes.
        """
        from module.alas_bridge.actions import msgbox_from_heartbeat, msgbox_yes

        snap = msgbox if isinstance(msgbox, dict) else None
        if not is_data_key_msgbox(snap):
            snap = msgbox_from_heartbeat(self.config, max_age=8.0)
        if is_data_key_msgbox(snap):
            if msgbox_yes(self.config):
                logger.info('WA data key confirm via Sweeney bridge')
                return True
        if not screenshot:
            return False
        self.config.USE_DATA_KEY = True
        if self.handle_use_data_key():
            logger.info('WA data key confirm via template')
            self.config.USE_DATA_KEY = True
            return True
        self.config.USE_DATA_KEY = True
        return False

    def _watch(self) -> str:
        """
        Sit back while mod AutoFight runs.

        Returns:
            ended / tickets / dock / stuck / timeout
        """
        from module.alas_bridge.sitback import handle_sitback_dock_full
        from module.base.timer import Timer
        from module.map.assets import WITHDRAW

        stuck = Timer(STUCK_SECONDS).start()
        enter_map = Timer(ENTER_MAP_SECONDS).start()
        overall = Timer(WATCH_TIMEOUT).start()
        grace = Timer(SORTIE_GRACE_SECONDS).start()
        ended_hold = Timer(ENDED_HOLD_SECONDS)
        dock_busy = [Timer(180)]
        dock_peek = Timer(8)
        self._bridge_combat_idle_reset()
        saw_in_map = False
        skip_shot = True
        last_pos = None
        sit_logged = False

        def _dock_tick(state, force_peek=False) -> Optional[str]:
            nonlocal skip_shot
            if not handle_sitback_dock_full(
                self.config,
                self.device,
                handler=self,
                state=state,
                force_peek=force_peek,
            ):
                return None
            stuck.reset()
            skip_shot = True
            busy = dock_busy[0]
            if not busy.started():
                busy.start()
            elif busy.reached():
                logger.warning('WarArchivesCatchup dock full, enhance/retire did not finish')
                return 'dock'
            return 'handled'

        while 1:
            state = self._read_state(max_age=15.0)
            stale = not isinstance(state, dict)
            scene = str(state.get('scene_key') or '') if not stale else ''
            on_battle_scene = scene in ('BATTLE', 'COMBATLOAD')
            if not stale and watch_on_map_ui(state):
                saw_in_map = True

            # Dock overlay before combat-idle continue. Stale BATTLE_FIGHT latch
            # used to skip this for the whole 30 min watch timeout. Peek the
            # map (not BATTLE) so Sort/Expand/Enhance is seen even when
            # player.dock_full is false or heartbeat mtime froze on the modal.
            peek = False
            if scene == 'DOCKYARD' or (saw_in_map and not on_battle_scene):
                if scene == 'DOCKYARD' or not dock_peek.started() or dock_peek.reached():
                    peek = True
                    if not dock_peek.started():
                        dock_peek.start()
                    else:
                        dock_peek.reset()
            dock_out = _dock_tick(state, force_peek=peek)
            if dock_out == 'dock':
                return 'dock'
            if dock_out == 'handled':
                continue
            dock_busy[0] = Timer(180)

            if stale:
                if self._bridge_combat_idle_tick():
                    stuck.reset()
                    skip_shot = True
                time.sleep(1)
                continue

            chapter = state.get('chapter') if isinstance(state.get('chapter'), dict) else {}
            battle = state.get('battle') if isinstance(state.get('battle'), dict) else {}
            wa = state.get('wa') if isinstance(state.get('wa'), dict) else {}
            in_sortie = watch_in_sortie(state)
            on_map_ui = watch_on_map_ui(state)
            scene = str(state.get('scene_key') or '')
            battle_state = str(battle.get('state') or '')
            on_battle_scene = scene in ('BATTLE', 'COMBATLOAD')
            # BattleState can stay FIGHT after returning to LEVEL; do not treat
            # that as combat or the dock popup is ignored until watch timeout.
            fighting = on_battle_scene and battle_state in ('BATTLE_FIGHT', 'BATTLE_OPENING')
            auto_fight = bool(chapter.get('auto_fight'))
            pos = (chapter.get('fleet_row'), chapter.get('fleet_col'), chapter.get('cell_count'))

            if self._handle_low_emotion_popup(state):
                stuck.reset()
                skip_shot = True
                time.sleep(0.5)
                continue

            if not saw_in_map and self._confirm_data_key_popup(
                    screenshot=False, msgbox=state.get('msgbox')):
                stuck.reset()
                enter_map.reset()
                skip_shot = True
                time.sleep(0.5)
                continue

            if on_map_ui:
                saw_in_map = True
                ended_hold = Timer(ENDED_HOLD_SECONDS)

            if not on_battle_scene:
                self._bridge_combat_idle_reset()
            idle = on_battle_scene and self._bridge_combat_idle_tick()
            if fighting or idle:
                stuck.reset()
                skip_shot = True
                self.device.stuck_record_clear()
                time.sleep(0 if idle else 1)
                continue

            if watch_map_ended(state, saw_in_map=saw_in_map, grace_ok=grace.reached()):
                if not ended_hold.started():
                    ended_hold.start()
                elif ended_hold.reached():
                    logger.info('WarArchivesCatchup map ended')
                    return 'ended'
            else:
                ended_hold = Timer(ENDED_HOLD_SECONDS)

            if auto_fight or (in_sortie and pos != last_pos and last_pos is not None):
                stuck.reset()
            if in_sortie:
                last_pos = pos

            tickets = wa.get('tickets')
            cost = int(wa.get('ticket_cost') or 5)
            if tickets is not None and int(tickets) < cost and not in_sortie:
                logger.info(f'WarArchivesCatchup tickets {tickets} < {cost}')
                return 'tickets'

            # AutoFight map UI is visually static. Template matching retirement /
            # info-bar fills detect_record and trips GameStuckError (~60s), which
            # restarts the client and kills the AutoFight overlay.
            sit_heartbeat = on_map_ui or auto_fight or in_sortie
            if sit_heartbeat:
                self.device.stuck_record_clear()
                skip_shot = True
                if not sit_logged:
                    logger.info('WarArchivesCatchup sit-back (heartbeat only, no screenshot)')
                    sit_logged = True
            elif skip_shot:
                skip_shot = False
            else:
                self.device.screenshot()
                if not saw_in_map and self._confirm_data_key_popup(screenshot=True):
                    stuck.reset()
                    enter_map.reset()
                    continue
                if self.handle_info_bar():
                    stuck.reset()
                    continue
                if self.handle_retirement():
                    stuck.reset()
                    continue

            if overall.reached():
                logger.warning('WarArchivesCatchup watch timeout')
                return 'timeout'

            if not saw_in_map and enter_map.reached():
                logger.warning('WarArchivesCatchup never entered map')
                return 'stuck'

            if saw_in_map and stuck.reached() and not fighting and not auto_fight and not in_sortie:
                logger.warning('WarArchivesCatchup stuck (AutoFight off, not in combat)')
                self.device.screenshot()
                if self.handle_info_bar():
                    stuck.reset()
                    continue
                if self.appear_then_click(WITHDRAW, interval=5):
                    continue
                return 'stuck'

            time.sleep(1)

    def _emotion_sync(self):
        """Replace the ledger with live energy of the bound sortie fleets."""
        if not self.emotion.is_calculate:
            return
        self.emotion.update()
        if self.emotion._bridge_enabled():
            self.emotion._apply_sortie_energy(replace_if_matched=True)
        self.emotion.record()
        self.emotion.show()

    def _emotion_gate(self, target: dict, flags: Optional[dict] = None):
        self._bind_sortie(target)
        self.emotion.check_reduce(battles_for_emotion(target, flags))

    def _handle_low_emotion_popup(self, state) -> bool:
        """
        Cancel the exhausted popup (do not Ignore) and delay the task.

        Sit-back is heartbeat-only, so template POPUP_CANCEL never runs.
        """
        msgbox = state.get('msgbox') if isinstance(state, dict) else None
        if not is_low_emotion_msgbox(msgbox):
            return False
        logger.warning('WarArchivesCatchup exhausted / low-emotion popup')
        if self.emotion.is_ignore:
            from module.alas_bridge.actions import msgbox_yes
            msgbox_yes(self.config)
            return True
        from module.alas_bridge.actions import msgbox_no
        msgbox_no(self.config)
        self._emotion_sync()
        self.emotion.check_reduce(1)
        return True

    def run(self):
        logger.hr('War Archives Catchup', level=1)
        if not self._bridge_ok():
            self._stop_no_bridge()
            return

        from module.alas_bridge.actions import get_wa_status

        try:
            while 1:
                try:
                    status = get_wa_status(self.config)
                    if not isinstance(status, dict):
                        logger.warning('get_wa_status failed')
                        self.config.task_delay(minute=5)
                        self.config.task_stop('WarArchivesCatchup: get_wa_status failed')
                        return

                    tickets = int(status.get('tickets') or 0)
                    cost = int(status.get('ticket_cost') or 5)
                    logger.attr('WA tickets', f'{tickets} / {status.get("tickets_max")} cost={cost}')
                    self._log_bonus(status)
                    self._log_hidden(status)

                    if tickets < cost:
                        logger.hr('Triggered out of data keys')
                        self.config.task_delay(server_update=True)
                        self.config.task_stop('WarArchivesCatchup: out of remaster tickets')
                        return

                    oil = self.get_oil()
                    limit = max(500, int(getattr(self.config, 'StopCondition_OilLimit', 1000) or 0))
                    if oil < limit:
                        logger.hr('Triggered stop condition: Oil limit')
                        self.config.task_delay(minute=(120, 240))
                        self.config.task_stop('WarArchivesCatchup: oil limit')
                        return

                    target = pick_next_chapter(status)
                    if target is None:
                        self._disable_done('War Archives catchup: nothing incomplete and accessible')
                        return

                    logger.hr(
                        f"WA target {target.get('pack_name')} {target.get('name')} "
                        f"id={target.get('id')} {target.get('clear_pct')}% "
                        f"stars={target.get('stars_earned')}/{target.get('stars_total')}",
                        level=2,
                    )
                    missing = target.get('missing') or []
                    logger.info(f'WA missing={missing}')

                    flags = self._set_flags(target)
                    self._emotion_gate(target, flags)

                    goto = self._wa_goto(target)
                    if goto is None:
                        raise RequestHumanTakeover
                    if goto.get('already_in_map') or goto.get('pending_battle'):
                        logger.info('WarArchivesCatchup chapter already running, sit back')
                    else:
                        fleet_result = self._apply_fleet(target)
                        if not self._sortie(target, fleet_result, flags):
                            if self._last_sortie_skip:
                                continue
                            raise RequestHumanTakeover
                        self.device.screenshot()
                        self._confirm_data_key_popup(screenshot=True)

                    outcome = self._watch()
                    logger.info(f'WarArchivesCatchup outcome={outcome}')
                    if outcome == 'tickets':
                        self.config.task_delay(server_update=True)
                        self.config.task_stop('WarArchivesCatchup: out of remaster tickets')
                        return
                    if outcome == 'dock':
                        self.config.task_call('Reward')
                        self.config.task_delay(minute=5)
                        self.config.task_stop('WarArchivesCatchup: dock full')
                        return
                    if outcome in ('stuck', 'timeout'):
                        raise RequestHumanTakeover
                    self._emotion_sync()
                    # ended → re-query
                except CampaignEnd:
                    logger.info('WarArchivesCatchup CampaignEnd, re-query')
                    continue
        except ScriptEnd as e:
            # check_reduce already delayed NextRun. Catch here so alas.py does
            # not treat Emotion control as a crash (traceback + exit).
            logger.hr('Script end')
            logger.info(str(e))
        except TaskEnd:
            raise
        finally:
            self._restore_flags()
