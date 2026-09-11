import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from module.alas_bridge.game_state import (
    GameState,
    page_name_from_state,
    discover_account_dir,
)
from module.alas_bridge.instances import commander_for_serial, instance_for_config


class TestPageNameFromState(unittest.TestCase):
    def test_explicit_page(self):
        self.assertEqual(page_name_from_state({'page': 'page_main'}), 'page_main')

    def test_scene_key(self):
        self.assertEqual(page_name_from_state({'scene_key': 'MAINUI'}), 'page_main')
        self.assertIsNone(page_name_from_state({'scene_key': 'LEVEL'}))
        self.assertEqual(page_name_from_state({'scene': 'scene event'}), 'page_commission')
        self.assertEqual(page_name_from_state({
            'scene_key': 'SETTINGS',
            'scene': 'scene settings',
            'mediator': 'NewSettingsMediator',
        }), 'page_settings')
        self.assertEqual(page_name_from_state({'scene': 'scene settings'}), 'page_settings')

    def test_level_entrance_is_campaign_menu(self):
        self.assertEqual(
            page_name_from_state({
                'page': 'page_campaign',
                'scene_key': 'LEVEL',
                'level': {'entrance': True, 'in_map': False},
            }),
            'page_campaign_menu',
        )
        self.assertEqual(
            page_name_from_state({
                'page': 'page_campaign',
                'scene_key': 'LEVEL',
                'level': {'entrance': False, 'in_map': False},
            }),
            'page_campaign',
        )
        self.assertEqual(
            page_name_from_state({
                'page': 'page_campaign',
                'scene_key': 'LEVEL',
                'level': {'entrance': False, 'in_map': True},
            }),
            'page_in_map',
        )

    def test_login_and_transition(self):
        self.assertEqual(page_name_from_state({'scene_key': 'LOGIN'}), 'page_login')
        self.assertEqual(page_name_from_state({'scene_key': 'TRANSITION'}), 'page_transition')
        self.assertEqual(page_name_from_state({'scene_key': 'COMBATLOAD'}), 'page_transition')

    def test_msgbox_overlay(self):
        self.assertEqual(
            page_name_from_state({
                'page': 'page_guild',
                'scene_key': 'GUILD',
                'overlays': ['MsgboxShowing'],
            }),
            'page_unknown',
        )

    def test_level_activity_chapter_list_is_event(self):
        self.assertEqual(
            page_name_from_state({
                'page': 'page_campaign',
                'scene_key': 'LEVEL',
                'level': {'entrance': False, 'in_map': False, 'activity': True, 'remaster': False},
            }),
            'page_event',
        )
        self.assertEqual(
            page_name_from_state({
                'scene_key': 'LEVEL',
                'level': {'entrance': False, 'in_map': False, 'activity': True, 'remaster': True},
            }),
            'page_campaign',
        )

    def test_overlay_wins(self):
        self.assertEqual(
            page_name_from_state({
                'page': 'page_island',
                'scene_key': 'ISLAND',
                'overlays': ['IslandShopMediator'],
            }),
            'page_island_shop',
        )
        self.assertEqual(
            page_name_from_state({
                'page': 'page_main',
                'scene_key': 'MAINUI',
                'overlays': ['MainLiveAreaPage'],
            }),
            'page_dormmenu',
        )

    def test_combat_unmapped(self):
        self.assertIsNone(page_name_from_state({
            'scene_key': 'BATTLE',
            'scene': 'scene battle',
        }))


class TestPageHops(unittest.TestCase):
    def test_dormmenu_closer_to_dorm_than_main(self):
        from module.ui.page import Page, page_dorm, page_dormmenu, page_main
        Page.init_connection(page_dorm)
        try:
            self.assertEqual(page_dorm.hops_to(page_dorm), 0)
            self.assertEqual(page_dormmenu.hops_to(page_dorm), 1)
            self.assertGreater(page_main.hops_to(page_dorm), 1)
        finally:
            Page.clear_connection()


class TestInstanceMap(unittest.TestCase):
    def test_serial_order_matches_logcat(self):
        self.assertEqual(commander_for_serial('127.0.0.1:16384'), '6ix7even')
        self.assertEqual(commander_for_serial('127.0.0.1:16416'), 'Bradley67')
        self.assertEqual(commander_for_serial('127.0.0.1:16448'), 'Asami67')
        self.assertEqual(commander_for_serial('127.0.0.1:16480'), 'nyazurlane')
        self.assertEqual(commander_for_serial('127.0.0.1:16512'), 'BootySubarashi')
        self.assertEqual(commander_for_serial('127.0.0.1:16544'), 'Margaret67')

    def test_config_name(self):
        self.assertEqual(instance_for_config('1_67')['serial'], '127.0.0.1:16384')
        self.assertEqual(instance_for_config('5_booty.json')['name'], 'BootySubarashi')


class TestGameStateRead(unittest.TestCase):
    def test_discover_by_commander_not_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / '111_6ix7even'
            b = root / '222_Bradley67'
            a.mkdir()
            b.mkdir()
            (a / 'state.json').write_text('{"alive": true, "page": "page_dock"}', encoding='utf-8')
            time.sleep(0.05)
            (b / 'state.json').write_text('{"alive": true, "page": "page_main"}', encoding='utf-8')
            self.assertEqual(discover_account_dir(root, commander='6ix7even').name, '111_6ix7even')
            self.assertEqual(discover_account_dir(root, commander='Bradley67').name, '222_Bradley67')
            self.assertIsNone(discover_account_dir(root))

    def test_from_config_uses_serial(self):
        class Cfg:
            Optimization_SweeneyBridgeRoot = None
            Optimization_SweeneyBridgeAccount = ''
            Emulator_Serial = '127.0.0.1:16512'

        gs = GameState.from_config(Cfg())
        self.assertEqual(gs.commander, 'BootySubarashi')
        self.assertEqual(gs.serial, '127.0.0.1:16512')

    def test_read_fresh_and_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / '9_test'
            acc.mkdir()
            payload = {
                'alive': True,
                'page': 'page_main',
                'scene_key': 'MAINUI',
            }
            (acc / 'state.json').write_text(json.dumps(payload), encoding='utf-8')
            gs = GameState(root=root)
            state = gs.read(max_age=30)
            self.assertIsNotNone(state)
            self.assertEqual(page_name_from_state(state), 'page_main')
            path = gs.state_path()
            old = time.time() - 10
            os.utime(path, (old, old))
            self.assertIsNone(gs.read(max_age=3.0))


class TestSortieStatus(unittest.TestCase):
    def test_args_regular_uses_fleet_ids(self):
        from module.alas_bridge.sortie_status import sortie_args_from_config

        class Cfg:
            task = type('T', (), {'command': 'Main'})()
            Campaign_Mode = 'normal'
            Fleet_Fleet1 = 3
            Fleet_Fleet2 = 4

        args = sortie_args_from_config(Cfg())
        self.assertEqual(args['source'], 'regular')
        self.assertEqual(args['fleet_ids'], [3, 4])

    def test_args_hard_and_raid_and_coalition(self):
        from module.alas_bridge.sortie_status import sortie_args_from_config

        class Hard:
            task = type('T', (), {'command': 'Hard'})()
            Campaign_Mode = 'normal'
            Campaign_Event = 'campaign_main'
            Hard_HardFleet = 2
            Hard_HardStage = '14-4'

        class Raid:
            task = type('T', (), {'command': 'Raid'})()
            Raid_Mode = 'hard'

        class Coal:
            task = type('T', (), {'command': 'CoalitionSp'})()

        hard_args = sortie_args_from_config(Hard())
        self.assertEqual(hard_args['source'], 'hard')
        self.assertEqual(hard_args['hard_index'], 2)
        self.assertFalse(hard_args['activity'])
        self.assertEqual(hard_args['chapter_name'], '14-4')
        self.assertEqual(sortie_args_from_config(Raid())['source'], 'raid')
        self.assertEqual(sortie_args_from_config(Coal())['source'], 'boss_rush')

    def test_args_event_cd_requests_activity_hard_both_fleets(self):
        from module.alas_bridge.sortie_status import sortie_args_from_config

        class EventC:
            task = type('T', (), {'command': 'Event'})()
            Campaign_Mode = 'hard'
            Campaign_Name = 'c2'
            Campaign_Event = 'event_20260813_cn'
            Hard_HardFleet = 1
            Fleet_Fleet1 = 6
            Fleet_Fleet2 = 5

        class EventD:
            # Event GUI Mode is always normal; D still uses CustomFleet.
            task = type('T', (), {'command': 'Event'})()
            Campaign_Mode = 'normal'
            Campaign_Name = 'd2'
            Campaign_Event = 'event_20260813_cn'
            Hard_HardFleet = 1
            Fleet_Fleet1 = 6
            Fleet_Fleet2 = 5

        class EventA:
            task = type('T', (), {'command': 'Event'})()
            Campaign_Mode = 'normal'
            Campaign_Name = 'a1'
            Campaign_Event = 'event_20260813_cn'
            Fleet_Fleet1 = 6
            Fleet_Fleet2 = 5

        c_args = sortie_args_from_config(EventC())
        self.assertEqual(c_args['source'], 'hard')
        self.assertTrue(c_args['activity'])
        self.assertEqual(c_args['chapter_name'], 'c2')
        self.assertNotIn('hard_index', c_args)
        d_args = sortie_args_from_config(EventD())
        self.assertEqual(d_args['source'], 'hard')
        self.assertTrue(d_args['activity'])
        self.assertEqual(d_args['chapter_name'], 'd2')
        self.assertNotIn('hard_index', d_args)
        self.assertNotIn('fleet_ids', d_args)
        a_args = sortie_args_from_config(EventA())
        self.assertEqual(a_args['source'], 'regular')
        self.assertEqual(a_args['fleet_ids'], [6, 5])

    def test_chapter_track_matches_event_cd_not_select_fleet(self):
        from module.alas_bridge.sortie_status import chapter_track_matches_stage

        class EventD:
            Campaign_Name = 'd2'

        class Main:
            Campaign_Name = '16-4'

        self.assertFalse(chapter_track_matches_stage(
            EventD(), {'sent': True, 'chapter_id': 2060005, 'custom_fleet': False}))
        self.assertFalse(chapter_track_matches_stage(
            EventD(), {'sent': True, 'chapter_name': 'b2', 'custom_fleet': False}))
        self.assertTrue(chapter_track_matches_stage(
            EventD(), {'sent': True, 'chapter_name': 'd2', 'custom_fleet': True}))
        self.assertTrue(chapter_track_matches_stage(Main(), {'sent': True, 'chapter_id': 16004}))

    def test_chapter_track_expected_stage_hard_ignores_main_and_catchup_name(self):
        from module.alas_bridge.sortie_status import chapter_track_expected_stage

        class HardCfg:
            task = type('T', (), {'command': 'Hard'})()
            Hard_HardStage = '14-4'
            Campaign_Name = '16-4'
            SweeneySortieChapterName = 'D3'

        class CatchupCfg:
            task = type('T', (), {'command': 'WarArchivesCatchup'})()
            Campaign_Name = 'sp1'
            SweeneySortieChapterName = 'B3'

        self.assertEqual(chapter_track_expected_stage(HardCfg()), '14-4')
        self.assertEqual(chapter_track_expected_stage(CatchupCfg()), 'B3')

    def test_hard_roster_family_and_match(self):
        from module.alas_bridge.sortie_status import (
            hard_roster_family,
            hard_stage_family_match,
            roster_matches_request,
        )

        self.assertEqual(hard_roster_family('C2'), 'c')
        self.assertEqual(hard_roster_family('c1'), 'c')
        self.assertEqual(hard_roster_family('D3'), 'd')
        self.assertEqual(hard_roster_family('14–4'), '14')
        self.assertTrue(hard_stage_family_match('c2', 'C1'))
        self.assertFalse(hard_stage_family_match('c2', 'D1'))
        self.assertTrue(hard_stage_family_match('14-1', '14–4'))

        status = {
            'matched': True,
            'source': 'hard_elite',
            'chapter_name': 'C2',
            'map_type': 'activity_hard',
            'fleets': [{'id': 1, 'ships': [{'energy': 119}]}],
        }
        event_args = {'source': 'hard', 'activity': True, 'chapter_name': 'c2'}
        self.assertTrue(roster_matches_request(status, event_args))
        d_args = dict(event_args)
        d_args['chapter_name'] = 'd2'
        self.assertFalse(roster_matches_request(status, d_args))
        main_args = {'source': 'hard', 'activity': False, 'chapter_name': '14-4'}
        self.assertFalse(roster_matches_request(status, main_args))
        self.assertFalse(roster_matches_request(
            {'source': 'hard_elite', 'chapter_name': 'C2', 'map_type': 'activity_hard'},
            event_args,
        ))

    def test_args_remaster_chapter_id(self):
        from module.alas_bridge.sortie_status import roster_matches_request, sortie_args_from_config

        class Catchup:
            task = type('T', (), {'command': 'WarArchivesCatchup'})()
            SweeneySortieChapterId = 16004
            SweeneySortieHard = True
            SweeneySortieChapterName = 'D3'

        args = sortie_args_from_config(Catchup())
        self.assertEqual(args['chapter_id'], 16004)
        self.assertTrue(args['activity'])
        self.assertEqual(args['source'], 'hard')
        self.assertEqual(args['chapter_name'], 'D3')
        self.assertTrue(roster_matches_request(
            {'matched': True, 'chapter_id': 16004, 'source': 'hard_elite'},
            args,
        ))
        self.assertFalse(roster_matches_request(
            {'matched': True, 'chapter_id': 999, 'source': 'hard_elite'},
            args,
        ))
        self.assertFalse(roster_matches_request(
            {'matched': True, 'source': 'regular'},
            args,
        ))

    def test_args_remaster_select_fleet_not_dock_1_2(self):
        from module.alas_bridge.sortie_status import roster_matches_request, sortie_args_from_config

        class Easy:
            task = type('T', (), {'command': 'WarArchivesCatchup'})()
            SweeneySortieChapterId = 2100526
            SweeneySortieHard = False
            SweeneySortieChapterName = 'B3'
            SweeneySortieFleetIds = [5, 6]

        args = sortie_args_from_config(Easy())
        self.assertEqual(args['chapter_id'], 2100526)
        self.assertEqual(args['source'], 'regular')
        self.assertEqual(args['fleet_ids'], [5, 6])
        self.assertFalse(roster_matches_request(
            {'matched': True, 'source': 'regular'},
            args,
        ))
        self.assertTrue(roster_matches_request(
            {'matched': True, 'source': 'regular', 'chapter_id': 2100526},
            args,
        ))

    def test_min_energy_and_at_cap(self):
        from module.alas_bridge.sortie_status import any_at_cap, min_energy, ships_in_group

        status = {
            'source': 'hard_elite',
            'fleets': [
                {
                    'id': 1,
                    'ships': [
                        {'name': 'A', 'energy': 80, 'at_cap': False},
                        {'name': 'B', 'energy': 41, 'at_cap': False},
                    ],
                },
                {
                    'id': 2,
                    'ships': [
                        {'name': 'C', 'energy': 120, 'hard_cap': True, 'soft_cap': False, 'at_cap': True},
                    ],
                },
            ],
        }
        self.assertEqual(min_energy(ships_in_group(status, 1)), 41)
        cap = any_at_cap(status)
        self.assertIsNotNone(cap)
        self.assertEqual(cap['name'], 'C')

    def test_eta_none_when_already_ok(self):
        from module.alas_bridge.sortie_status import eta_until_energy

        ships = [{'energy': 50, 'dorm_floor': 0, 'propose': False}]
        self.assertIsNone(eta_until_energy(ships, 40))

    def test_level_cap_triggered_without_rpc(self):
        from module.alas_bridge import sortie_status as ss

        class Cfg:
            Optimization_SweeneyBridge = True
            StopCondition_LevelCap = True
            LV_TRIGGERED = False

        original = ss.fetch_sortie_status
        ss.fetch_sortie_status = lambda config, timeout=8.0: {
            'source': 'regular',
            'fleets': [{'id': 1, 'ships': [{'name': 'D', 'level': 70, 'max_level': 70, 'at_cap': True}]}],
        }
        try:
            cfg = Cfg()
            self.assertTrue(ss.level_cap_triggered(cfg))
            self.assertTrue(cfg.LV_TRIGGERED)
        finally:
            ss.fetch_sortie_status = original

    def test_level_cap_skipped_without_bridge(self):
        from module.alas_bridge.sortie_status import level_cap_triggered

        class Cfg:
            Optimization_SweeneyBridge = False
            StopCondition_LevelCap = True

        self.assertFalse(level_cap_triggered(Cfg()))

    def test_empty_or_object_fleets_are_rejected(self):
        from module.alas_bridge.sortie_status import parse_sortie_ack

        self.assertIsNone(parse_sortie_ack({'ok': True, 'result': {'fleets': []}}))
        self.assertIsNone(parse_sortie_ack({'ok': True, 'result': {'fleets': [{'id': 1, 'ships': []}]}}))
        self.assertIsNone(parse_sortie_ack({'ok': True, 'result': {'fleets': {}}}))
        self.assertIsNotNone(parse_sortie_ack({
            'ok': True,
            'result': {'fleets': [{'id': 1, 'ships': [{'energy': 80}]}]},
        }))


class _EmotionCfg:
    Emotion_Mode = 'calculate'
    Emotion_Fleet1Value = 119
    Emotion_Fleet1Record = None
    Emotion_Fleet1Control = 'prevent_green_face'
    Emotion_Fleet1Recover = 'not_in_dormitory'
    Emotion_Fleet1Oath = False
    Emotion_Fleet1Onsen = False
    Emotion_Fleet2Value = 119
    Emotion_Fleet2Record = None
    Emotion_Fleet2Control = 'prevent_green_face'
    Emotion_Fleet2Recover = 'not_in_dormitory'
    Emotion_Fleet2Oath = False
    Emotion_Fleet2Onsen = False
    Optimization_SweeneyBridge = True
    Fleet_FleetOrder = 'fleet1_all_fleet2_standby'
    Campaign_Use2xBook = False
    delayed = None

    def __init__(self, value=119):
        from datetime import datetime
        now = datetime.now().replace(microsecond=0)
        self.Emotion_Fleet1Value = value
        self.Emotion_Fleet1Record = now
        self.Emotion_Fleet2Value = value
        self.Emotion_Fleet2Record = now

    def set_record(self, **kwargs):
        from datetime import datetime
        now = datetime.now().replace(microsecond=0)
        for key, val in kwargs.items():
            setattr(self, key, val)
            setattr(self, key.replace('Value', 'Record'), now)

    def task_delay(self, **kwargs):
        self.delayed = kwargs

    def multi_set(self):
        from contextlib import nullcontext
        return nullcontext()


def _status(energy, **extra):
    both = extra.pop('both', False)
    ships2 = [{'energy': energy, 'dorm_floor': 0, 'propose': False}] if both else []
    row = {
        'source': extra.pop('source', 'regular'),
        'fleets': [
            {'id': 1, 'ships': [{'energy': energy, 'dorm_floor': 0, 'propose': False}]},
            {'id': 2, 'ships': ships2},
        ],
    }
    row.update(extra)
    return row


class TestEmotionBridge(unittest.TestCase):
    def test_reduce_still_subtracts_when_live_is_pre_battle(self):
        from module.combat.emotion import Emotion

        cfg = _EmotionCfg(119)
        emo = Emotion(cfg)
        emo._fetch_sortie = lambda: _status(119)
        emo.reduce(1)
        self.assertEqual(emo.fleet_1.current, 117)
        self.assertEqual(cfg.Emotion_Fleet1Value, 117)

    def test_stale_high_live_does_not_block_dead_reckon_delay(self):
        from module.combat.emotion import Emotion
        from module.exception import ScriptEnd

        cfg = _EmotionCfg(30)
        emo = Emotion(cfg)
        emo._fetch_sortie = lambda: _status(150)
        with self.assertRaises(ScriptEnd):
            emo.check_reduce(5)
        self.assertIsNotNone(cfg.delayed)

    def test_live_exhausted_delays_even_if_ledger_is_full(self):
        from module.combat.emotion import Emotion
        from module.exception import ScriptEnd

        cfg = _EmotionCfg(119)
        emo = Emotion(cfg)
        emo._fetch_sortie = lambda: _status(0)
        with self.assertRaises(ScriptEnd):
            emo.check_reduce(5)
        self.assertIsNotNone(cfg.delayed)

    def test_verified_event_cd_live_replaces_stale_ledger(self):
        from module.combat.emotion import Emotion

        class Cfg(_EmotionCfg):
            task = type('T', (), {'command': 'Event'})()
            Campaign_Mode = 'hard'
            Campaign_Name = 'c2'
            Campaign_Event = 'event_20260813_cn'

        cfg = Cfg(30)
        emo = Emotion(cfg)
        emo._fetch_sortie = lambda: _status(
            119,
            both=True,
            source='hard_elite',
            matched=True,
            chapter_name='C2',
            map_type='activity_hard',
        )
        emo.check_reduce(5)
        self.assertIsNone(cfg.delayed)
        self.assertEqual(cfg.Emotion_Fleet1Value, 119)

    def test_verified_wrong_family_stays_dead_reckon_floor(self):
        from module.combat.emotion import Emotion
        from module.exception import ScriptEnd

        class Cfg(_EmotionCfg):
            task = type('T', (), {'command': 'Event'})()
            Campaign_Mode = 'hard'
            Campaign_Name = 'c2'
            Campaign_Event = 'event_20260813_cn'

        cfg = Cfg(30)
        emo = Emotion(cfg)
        emo._fetch_sortie = lambda: _status(
            150,
            source='hard_elite',
            matched=True,
            chapter_name='D2',
            map_type='activity_hard',
        )
        with self.assertRaises(ScriptEnd):
            emo.check_reduce(5)
        self.assertIsNotNone(cfg.delayed)
        self.assertEqual(cfg.Emotion_Fleet1Value, 30)

    def test_reduce_keeps_floor_even_when_roster_matched(self):
        from module.combat.emotion import Emotion

        class Cfg(_EmotionCfg):
            task = type('T', (), {'command': 'Event'})()
            Campaign_Mode = 'hard'
            Campaign_Name = 'c2'
            Campaign_Event = 'event_20260813_cn'

        cfg = Cfg(50)
        emo = Emotion(cfg)
        emo._fetch_sortie = lambda: _status(
            119,
            source='hard_elite',
            matched=True,
            chapter_name='C2',
            map_type='activity_hard',
        )
        emo.reduce(1)
        self.assertEqual(emo.fleet_1.current, 48)


class TestCommissionBridgeRow(unittest.TestCase):
    def test_from_bridge_row_running_finish_time(self):
        from datetime import datetime
        from module.commission.project import Commission

        class Cfg:
            SERVER = 'en'

        now = int(time.time())
        row = {
            'id': 42,
            'title': 'Event Commission',
            'status': 'running',
            'type': 1,
            'collect_time': 3600,
            'activity': True,
            'finish_unix': now + 600,
            'over_unix': 0,
            'server_now': now,
        }
        comm = Commission.from_bridge_row(row, Cfg())
        self.assertEqual(comm.event_id, 42)
        self.assertEqual(comm.status, 'running')
        self.assertEqual(comm.genre, 'daily_event')
        self.assertIsNotNone(comm.finish_time)
        self.assertGreater(comm.finish_time, datetime.fromtimestamp(now))

    def test_from_bridge_row_expired_and_pending(self):
        from module.commission.project import Commission

        class Cfg:
            SERVER = 'en'

        row = {
            'id': 7,
            'title': 'Gone',
            'status': 'expired',
            'type': 1,
            'collect_time': 0,
            'activity': False,
            'finish_unix': 0,
            'over_unix': 1,
            'server_now': 10,
        }
        comm = Commission.from_bridge_row(row, Cfg())
        self.assertEqual(comm.status, 'expired')
        self.assertIsNone(comm.finish_time)


class TestBridgeActions(unittest.TestCase):
    def test_harvest_empty_ack_is_success(self):
        from module.alas_bridge import actions

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                if name == 'chapter_track':
                    return {
                        'id': '1',
                        'ok': True,
                        'name': name,
                        'result': {'sent': True, 'chapter_id': 16004},
                    }
                if name == 'apply_fleet_preset':
                    return {
                        'id': '1',
                        'ok': True,
                        'name': name,
                        'result': {'applied': True, 'swap': True, 'custom_fleet': True},
                    }
                if name == 'set_mod_flags':
                    return {
                        'id': '1',
                        'ok': True,
                        'name': name,
                        'result': {
                            'previous': {'forceAutoFightWithoutLoop': False},
                            'current': {'forceAutoFightWithoutLoop': True},
                        },
                    }
                if name in ('get_wa_status', 'wa_goto'):
                    return {'id': '1', 'ok': True, 'name': name, 'result': {'ok': True}}
                return {'id': '1', 'ok': True, 'name': name, 'result': {'kind': (args or {}).get('kind')}}

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = FakeRpc
        actions.GameState = FakeGS
        try:
            self.assertTrue(actions.harvest_res(object(), 'oil'))
            self.assertTrue(actions.dorm_one_key(object()))
            self.assertIsNotNone(actions.island_run(object()))
            self.assertIsNotNone(actions.get_pq_status(object()))
            self.assertIsNotNone(actions.pq_spend_stamina(object(), ship='new_jersey'))
            self.assertIsNotNone(actions.pq_shop_buy(object(), roses=True))
            self.assertIsNotNone(actions.chapter_track(object(), auto_fight=True, loop=True))
            self.assertIsNotNone(actions.get_wa_status(object()))
            self.assertIsNotNone(actions.wa_goto(object(), chapter_id=16004, remaster_id=1))
            self.assertIsNotNone(actions.set_mod_flags(
                object(), force_auto_fight_without_loop=True, auto_fight_clear_before_boss=False))
            self.assertIsNotNone(actions.apply_fleet_preset(object(), swap=True, chapter_id=16004))
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = orig_gs

    def test_chapter_track_sends_alas_fleet_ids(self):
        from module.alas_bridge import actions

        seen = {}

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                seen['name'] = name
                seen['args'] = args or {}
                return {
                    'id': '1',
                    'ok': True,
                    'name': name,
                    'result': {'sent': True, 'chapter_id': 16004},
                }

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        class Cfg:
            Fleet_Fleet1 = 3
            Fleet_Fleet2 = 4
            Submarine_Fleet = 0

        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = FakeRpc
        actions.GameState = FakeGS
        try:
            result = actions.chapter_track(Cfg(), auto_fight=True, loop=True)
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = orig_gs
        self.assertIsNotNone(result)
        self.assertEqual(seen['name'], 'chapter_track')
        self.assertEqual(seen['args']['fleet_ids'], [3, 4])
        self.assertTrue(seen['args']['auto_fight'])
        self.assertTrue(seen['args']['loop'])

    def test_chapter_track_sends_chapter_name_and_rejects_event_b_for_d(self):
        """Cross-aside B vs D must still mismatch. In-group A/C is switched in Lua."""
        from module.alas_bridge import actions

        seen = {}

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                seen['name'] = name
                seen['args'] = args or {}
                return {
                    'id': '1',
                    'ok': True,
                    'name': name,
                    'result': {
                        'sent': True,
                        'chapter_id': 2060005,
                        'chapter_name': 'b2',
                        'custom_fleet': False,
                    },
                }

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        class Cfg:
            Campaign_Name = 'd2'
            Fleet_Fleet1 = 6
            Fleet_Fleet2 = 5
            Submarine_Fleet = 0

        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = FakeRpc
        actions.GameState = FakeGS
        try:
            result = actions.chapter_track(Cfg(), auto_fight=True, loop=True)
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = FakeGS
        self.assertEqual(seen['args']['chapter_name'], 'd2')
        self.assertEqual(result.get('reason'), 'chapter_mismatch')
        self.assertFalse(result.get('sent'))

    def test_pq_spend_stamina_rejects_incomplete(self):
        from module.alas_bridge import actions

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                if name == 'pq_spend_stamina':
                    return {
                        'id': '1',
                        'ok': True,
                        'name': name,
                        'result': {
                            'spent': 0,
                            'stamina_before': 3,
                            'stamina_after': 3,
                            'timeout': True,
                        },
                    }
                return {'id': '1', 'ok': True, 'name': name, 'result': {}}

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = FakeRpc
        actions.GameState = FakeGS
        try:
            self.assertIsNone(actions.pq_spend_stamina(object(), ship='sirius'))
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = orig_gs

    def test_send_verb_error_returns_none(self):
        from module.alas_bridge import actions

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                return {'id': '1', 'ok': False, 'name': name, 'error': 'boom'}

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = FakeRpc
        actions.GameState = FakeGS
        try:
            self.assertFalse(actions.harvest_res(object(), 'oil'))
            self.assertIsNone(actions.island_run(object()))
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = orig_gs

    def test_player_from_heartbeat_keeps_zero_oil(self):
        from module.alas_bridge.actions import player_from_heartbeat

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / '9_test'
            acc.mkdir()
            (acc / 'state.json').write_text(json.dumps({
                'alive': True,
                'player': {'oil': 0, 'gold': 12, 'oil_field': 3},
            }), encoding='utf-8')

            class Cfg:
                Optimization_SweeneyBridgeRoot = str(root)
                Optimization_SweeneyBridgeAccount = '9_test'
                Emulator_Serial = ''

            player = player_from_heartbeat(Cfg(), max_age=30)
            self.assertIsNotNone(player)
            self.assertIn('oil', player)
            self.assertEqual(int(player['oil']), 0)
            self.assertEqual(int(player['gold']), 12)

    def test_msgbox_from_heartbeat(self):
        from module.alas_bridge.actions import msgbox_from_heartbeat

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / '9_test'
            acc.mkdir()
            (acc / 'state.json').write_text(json.dumps({
                'alive': True,
                'msgbox': {
                    'showing': True,
                    'has_yes': True,
                    'has_no': True,
                    'content': 'continue training?',
                },
            }), encoding='utf-8')

            class Cfg:
                Optimization_SweeneyBridge = True
                Optimization_SweeneyBridgeRoot = str(root)
                Optimization_SweeneyBridgeAccount = '9_test'
                Emulator_Serial = ''

            msgbox = msgbox_from_heartbeat(Cfg(), max_age=30)
            self.assertIsNotNone(msgbox)
            self.assertTrue(msgbox['showing'])
            self.assertTrue(msgbox['has_yes'])
            self.assertTrue(msgbox['has_no'])

    def test_map_prep_from_heartbeat(self):
        from module.alas_bridge.actions import (
            level_from_heartbeat,
            map_prep_showing_from_heartbeat,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / '9_test'
            acc.mkdir()
            (acc / 'state.json').write_text(json.dumps({
                'alive': True,
                'level': {
                    'entrance': False,
                    'in_map': False,
                    'info_showing': True,
                    'fleet_showing': False,
                    'prep_chapter_id': 16004,
                },
            }), encoding='utf-8')

            class Cfg:
                Optimization_SweeneyBridge = True
                Optimization_SweeneyBridgeRoot = str(root)
                Optimization_SweeneyBridgeAccount = '9_test'
                Emulator_Serial = ''

            level = level_from_heartbeat(Cfg(), max_age=30)
            self.assertIsNotNone(level)
            self.assertTrue(level['info_showing'])
            self.assertEqual(map_prep_showing_from_heartbeat(Cfg(), max_age=30), 'info')

    def test_battle_is_fighting_and_stuck_refresh(self):
        from module.alas_bridge.actions import (
            battle_is_fighting,
            refresh_stuck_if_battle_fighting,
        )
        from module.base.timer import Timer

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / '9_test'
            acc.mkdir()
            (acc / 'state.json').write_text(json.dumps({
                'alive': True,
                'battle': {'state': 'BATTLE_FIGHT', 'type': 1},
            }), encoding='utf-8')

            class Cfg:
                Optimization_SweeneyBridge = True
                Optimization_SweeneyBridgeRoot = str(root)
                Optimization_SweeneyBridgeAccount = '9_test'
                Emulator_Serial = ''

            self.assertTrue(battle_is_fighting(Cfg(), max_age=30))
            self.assertFalse(battle_is_fighting(Cfg(), max_age=30) is False)

            class Device:
                def __init__(self):
                    self.stuck_timer = Timer(60, count=60).start()
                    self.stuck_timer_long = Timer(180, count=180).start()

            class Main:
                config = Cfg()
                device = Device()

            main = Main()
            self.assertTrue(refresh_stuck_if_battle_fighting(main, max_age=30))
            self.assertFalse(main.device.stuck_timer.reached())
            self.assertFalse(main.device.stuck_timer_long.reached())


class TestCombatIdleSkip(unittest.TestCase):
    def test_allowed_only_for_auto_no_record(self):
        from module.alas_bridge.actions import combat_idle_skip_allowed

        class Cfg:
            Optimization_SweeneyBridge = True
            DropRecord_CombatRecord = 'do_not'

        self.assertTrue(combat_idle_skip_allowed(Cfg(), auto='combat_auto', submarine='do_not_use'))
        self.assertFalse(combat_idle_skip_allowed(Cfg(), auto='combat_manual'))
        self.assertFalse(combat_idle_skip_allowed(Cfg(), submarine='hunt_only'))
        self.assertFalse(combat_idle_skip_allowed(Cfg(), drop=object()))

        class SaveCfg:
            Optimization_SweeneyBridge = True
            DropRecord_CombatRecord = 'save'

        self.assertFalse(combat_idle_skip_allowed(SaveCfg()))

        class OffCfg:
            Optimization_SweeneyBridge = False
            DropRecord_CombatRecord = 'do_not'

        self.assertFalse(combat_idle_skip_allowed(OffCfg()))

    def test_should_skip_latches_through_stale_heartbeat(self):
        from module.alas_bridge.actions import combat_idle_should_skip

        skip, latched = combat_idle_should_skip(True, False)
        self.assertTrue(skip)
        self.assertTrue(latched)
        skip, latched = combat_idle_should_skip(None, True)
        self.assertTrue(skip)
        self.assertTrue(latched)
        skip, latched = combat_idle_should_skip(None, False)
        self.assertFalse(skip)
        self.assertFalse(latched)
        skip, latched = combat_idle_should_skip(False, True)
        self.assertFalse(skip)
        self.assertFalse(latched)

    def test_report_click_button_is_mode_specific(self):
        from module.combat.assets import BATTLE_STATUS_S
        from module.combat.combat import Combat
        from module.guild.assets import BATTLE_STATUS_CF
        from module.guild.guild_combat import GuildCombat
        from module.os_ash.ash import AshCombat
        from module.os_ash.assets import BATTLE_STATUS
        from module.raid.combat import RaidCombat

        # Heartbeat BATTLE_REPORT must not always click vanilla S-rank confirm.
        self.assertIs(Combat._battle_status_report_click_button(None), BATTLE_STATUS_S)
        self.assertIs(AshCombat._battle_status_report_click_button(None), BATTLE_STATUS)
        self.assertIs(RaidCombat._battle_status_report_click_button(None), BATTLE_STATUS_CF)
        self.assertIs(GuildCombat._battle_status_report_click_button(None), BATTLE_STATUS_CF)

    def test_ash_combat_keeps_confirm_interval_without_drop_record(self):
        from module.combat.combat import Combat
        from module.os_ash.ash import AshCombat

        # Heartbeat BATTLE_REPORT plus interval 0 12-clicked META Confirm in ~6s.
        self.assertEqual(AshCombat.battle_status_click_interval, 2)
        ash = AshCombat.__new__(AshCombat)
        ash.battle_status_click_interval = AshCombat.battle_status_click_interval
        Combat._apply_battle_status_click_interval(ash, False)
        self.assertEqual(ash.battle_status_click_interval, 2)
        Combat._apply_battle_status_click_interval(ash, True)
        self.assertEqual(ash.battle_status_click_interval, 7)
        vanilla = Combat.__new__(Combat)
        vanilla.battle_status_click_interval = Combat.battle_status_click_interval
        Combat._apply_battle_status_click_interval(vanilla, False)
        self.assertEqual(vanilla.battle_status_click_interval, 0)

    def test_report_overlay_requires_battle_scene(self):
        from module.alas_bridge.actions import battle_report_overlay_from_state

        self.assertTrue(battle_report_overlay_from_state({
            'scene_key': 'BATTLE',
            'battle': {'state': 'BATTLE_REPORT'},
        }))
        self.assertFalse(battle_report_overlay_from_state({
            'battle': {'state': 'BATTLE_REPORT'},
        }))
        self.assertFalse(battle_report_overlay_from_state({
            'scene_key': 'WORLDBOSS',
            'battle': {'state': 'BATTLE_REPORT'},
        }))
        self.assertFalse(battle_report_overlay_from_state({
            'scene_key': 'BATTLE',
            'battle': {'state': 'BATTLE_FIGHT'},
        }))
        self.assertFalse(battle_report_overlay_from_state(None))

    def test_event_pt_from_heartbeat(self):
        from module.alas_bridge.actions import event_pt_from_bridge

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / '9_test'
            acc.mkdir()
            (acc / 'state.json').write_text(json.dumps({
                'alive': True,
                'player': {'oil': 1, 'event_pt': 12345},
            }), encoding='utf-8')

            class Cfg:
                Optimization_SweeneyBridge = True
                Optimization_SweeneyBridgeRoot = str(root)
                Optimization_SweeneyBridgeAccount = '9_test'
                Emulator_Serial = ''

            self.assertEqual(event_pt_from_bridge(Cfg()), 12345)

    def test_raid_remain_orders_by_stage(self):
        from module.alas_bridge import actions

        orig_remains = actions.get_task_remains
        orig_enabled = actions.bridge_enabled
        actions.bridge_enabled = lambda config: True
        actions.get_task_remains = lambda config: {
            'raid': [
                {'stage_id': 300, 'remain': 1},
                {'stage_id': 100, 'remain': 3},
                {'stage_id': 200, 'remain': 2},
                {'stage_id': 400, 'remain': 0},
            ]
        }
        try:
            self.assertEqual(actions.raid_remain_from_bridge(object(), 'easy'), 3)
            self.assertEqual(actions.raid_remain_from_bridge(object(), 'normal'), 2)
            self.assertEqual(actions.raid_remain_from_bridge(object(), 'hard'), 1)
            self.assertEqual(actions.raid_remain_from_bridge(object(), 'ex'), 0)
            self.assertIsNone(actions.raid_remain_from_bridge(object(), 'unknown'))
        finally:
            actions.get_task_remains = orig_remains
            actions.bridge_enabled = orig_enabled

    def test_fleet_location_from_heartbeat(self):
        from module.alas_bridge.actions import fleet_location_from_heartbeat

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / '9_test'
            acc.mkdir()
            (acc / 'state.json').write_text(json.dumps({
                'alive': True,
                'chapter': {
                    'active': True,
                    'fleet_row': 2,
                    'fleet_col': 5,
                },
            }), encoding='utf-8')

            class Cfg:
                Optimization_SweeneyBridge = True
                Optimization_SweeneyBridgeRoot = str(root)
                Optimization_SweeneyBridgeAccount = '9_test'
                Emulator_Serial = ''

            # ALAS map (x, y) is (col, row)
            self.assertEqual(fleet_location_from_heartbeat(Cfg(), max_age=30), (5, 2))

    def test_resolve_default_swmod_root_env(self):
        from module.alas_bridge import game_state

        with tempfile.TemporaryDirectory() as tmp:
            prev = os.environ.get('SWEENEY_SWMOD_ROOT')
            os.environ['SWEENEY_SWMOD_ROOT'] = tmp
            try:
                self.assertEqual(game_state.resolve_default_swmod_root(), Path(tmp))
            finally:
                if prev is None:
                    os.environ.pop('SWEENEY_SWMOD_ROOT', None)
                else:
                    os.environ['SWEENEY_SWMOD_ROOT'] = prev

    def test_mumu_swmod_candidates_prefer_local_azur_over_documents(self):
        from module.alas_bridge import game_state

        cands = list(game_state._mumu_swmod_candidates())
        self.assertEqual(cands[0], game_state.MUMU_SWMOD_ROOT)
        first_docs = next(
            (i for i, p in enumerate(cands) if 'Documents' in p.parts or 'OneDrive' in p.parts),
            None,
        )
        self.assertIsNotNone(first_docs)
        self.assertGreater(first_docs, 0)

    def test_farm_loop_bench_parse(self):
        import importlib.util

        bench = Path(__file__).resolve().parents[1] / 'tools' / 'farm_loop_bench.py'
        spec = importlib.util.spec_from_file_location('farm_loop_bench', bench)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        parse_log = mod.parse_log

        text = (
            '2026-08-28 12:00:00.000 | INFO | [ScreenshotCount] 50\n'
            '2026-08-28 12:00:01.000 | INFO | [OcrCount] 20\n'
            '2026-08-28 12:00:02.000 | INFO | UI page from Sweeney bridge\n'
            '2026-08-28 12:00:03.000 | INFO | Sweeney bridge miss, screenshot fallback\n'
            '2026-08-28 12:00:04.000 | INFO | Combat idle skip (Sweeney BATTLE_FIGHT, no ADB screencap)\n'
            '2026-08-28 12:00:05.000 | INFO | Combat idle skip peek (report watchdog)\n'
            '2026-08-28 12:00:06.000 | INFO | [BattleUI] PAUSE\n'
            '2026-08-28 12:00:07.000 | INFO | [nc command] [\'busybox\', \'nc\']\n'
        )
        stats = parse_log(text)
        self.assertEqual(stats['screenshot_count_last'], 50)
        self.assertEqual(stats['ocr_count_last'], 20)
        self.assertEqual(stats['bridge_page'], 1)
        self.assertEqual(stats['bridge_miss'], 1)
        self.assertEqual(stats['combat_idle'], 1)
        self.assertEqual(stats['combat_idle_peek'], 1)
        self.assertEqual(stats['battle_ui'], 1)
        self.assertGreaterEqual(stats['adb_nc'], 1)

    def test_classify_host_processes(self):
        import importlib.util

        bench = Path(__file__).resolve().parents[1] / 'tools' / 'farm_loop_bench.py'
        spec = importlib.util.spec_from_file_location('farm_loop_bench', bench)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        classify = mod.classify_process

        self.assertEqual(
            classify('python.exe', r'E:\Azur\AzurLaneAutoScript\toolkit\python.exe alas.py'),
            'alas_python',
        )
        self.assertEqual(
            classify('python', '', r'E:\Azur\AzurLaneAutoScript\toolkit\python.exe'),
            'alas_python',
        )
        self.assertEqual(classify('python.exe', r'C:\Python\python.exe -m pytest'), 'other_python')
        self.assertEqual(classify('HD-Player.exe', ''), 'HD-Player')
        self.assertEqual(classify('BstkSVC.exe', ''), 'bluestacks_other')
        self.assertEqual(classify('MuMuNxMain.exe', ''), 'MuMuNxMain')
        self.assertEqual(classify('MuMuNxDevice', ''), 'MuMuNxDevice')
        self.assertEqual(classify('MuMuVMM.exe', ''), 'mumu_other')
        self.assertEqual(classify('chrome.exe', ''), '')


class TestTacticalBookPick(unittest.TestCase):
    def test_same_t4_preferred(self):
        from module.tactical.tactical_class import pick_tactical_book

        books = [
            {'id': 16001, 'count': 5, 'tier': 1, 'skill_type': 1, 'exp': 100, 'bonus': 50},
            {'id': 16004, 'count': 2, 'tier': 4, 'skill_type': 1, 'exp': 1500, 'bonus': 100},
            {'id': 16014, 'count': 2, 'tier': 4, 'skill_type': 2, 'exp': 1500, 'bonus': 100},
        ]
        book = pick_tactical_book(
            books, skill_type=1, filter_str='SameT4 > SameT3 > first')
        self.assertIsNotNone(book)
        self.assertEqual(book.id, 16004)
        self.assertEqual(book.same_str, 'same')
        self.assertEqual(book.exp_value, 3000)

    def test_overflow_clips_t4_on_lv9(self):
        from module.tactical.tactical_class import pick_tactical_book

        books = [
            {'id': 16004, 'count': 1, 'tier': 4, 'skill_type': 1, 'exp': 1500, 'bonus': 100},
            {'id': 16001, 'count': 1, 'tier': 1, 'skill_type': 1, 'exp': 100, 'bonus': 50},
        ]
        book = pick_tactical_book(
            books,
            skill_type=1,
            filter_str='SameT4 > SameT1',
            skill_exp=4000,
            skill_next=5800,
            overflow_by_tier={1: 200, 4: 10},
        )
        self.assertIsNotNone(book)
        self.assertEqual(book.id, 16001)


class TestWarArchivesCatchupPolicy(unittest.TestCase):
    def _status(self, chapters, bonus=None, nxt=None):
        return {
            'tickets': 10,
            'ticket_cost': 5,
            'packs': [{
                'remaster_id': 1,
                'name': 'pack',
                'chapters': chapters,
            }],
            'bonus': bonus or [],
            'next': nxt,
        }

    def test_pick_next_skips_locked_and_complete(self):
        from module.war_archives_catchup.policy import pick_next_chapter

        locked = {
            'id': 1, 'name': 'A1', 'unlocked': False, 'incomplete': True,
            'clear_pct': 0, 'stars_earned': 0, 'stars_total': 3,
        }
        done = {
            'id': 2, 'name': 'A2', 'unlocked': True, 'incomplete': False,
            'clear_pct': 100, 'stars_earned': 3, 'stars_total': 3,
        }
        first = {
            'id': 3, 'name': 'A3', 'unlocked': True, 'incomplete': True,
            'clear_pct': 40, 'stars_earned': 1, 'stars_total': 3,
        }
        later = {
            'id': 4, 'name': 'B1', 'unlocked': True, 'incomplete': True,
            'clear_pct': 0, 'stars_earned': 0, 'stars_total': 3,
        }
        picked = pick_next_chapter(self._status([locked, done, first, later]))
        self.assertIsNotNone(picked)
        self.assertEqual(picked['id'], 3)

    def test_pick_next_skips_bonus_only(self):
        from module.war_archives_catchup.policy import incomplete_bonus, pick_next_chapter

        done = {
            'id': 10, 'name': 'D3', 'unlocked': True, 'incomplete': False,
            'clear_pct': 100, 'stars_earned': 3, 'stars_total': 3,
        }
        status = self._status(
            [done],
            bonus=[{
                'chapter_id': 10, 'chapter_name': 'D3',
                'have': 12, 'need': 60, 'drop': 307061, 'incomplete': True,
            }],
        )
        self.assertIsNone(pick_next_chapter(status))
        bonus = incomplete_bonus(status)
        self.assertEqual(len(bonus), 1)
        self.assertEqual(bonus[0]['drop'], 307061)

    def test_pick_next_honors_status_next(self):
        from module.war_archives_catchup.policy import pick_next_chapter

        nxt = {
            'id': 99, 'name': 'C1', 'unlocked': True, 'incomplete': True,
            'clear_pct': 80, 'stars_earned': 2, 'stars_total': 3,
        }
        other = {
            'id': 1, 'name': 'A1', 'unlocked': True, 'incomplete': True,
            'clear_pct': 0, 'stars_earned': 0, 'stars_total': 3,
        }
        picked = pick_next_chapter(self._status([other], nxt=nxt))
        self.assertEqual(picked['id'], 99)

    def test_pick_next_skips_hidden_cleared(self):
        from module.war_archives_catchup.policy import (
            hidden_incomplete,
            pick_next_chapter,
        )

        hidden = {
            'id': 2100187, 'name': 'AS1', 'unlocked': True, 'incomplete': False,
            'need_hide': True, 'exist_loop': False,
            'clear_pct': 100, 'stars_earned': 1, 'stars_total': 3,
        }
        later = {
            'id': 2100191, 'name': 'C1', 'unlocked': True, 'incomplete': True,
            'need_hide': False, 'exist_loop': True,
            'clear_pct': 40, 'stars_earned': 1, 'stars_total': 3,
        }
        status = self._status([hidden, later], nxt=hidden)
        picked = pick_next_chapter(status)
        self.assertIsNotNone(picked)
        self.assertEqual(picked['id'], 2100191)
        skipped = hidden_incomplete(status)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]['id'], 2100187)

    def test_flags_no_loop_template_forces_noloop(self):
        from module.war_archives_catchup.policy import flags_for_chapter

        flags = flags_for_chapter({
            'can_loop': True,
            'exist_loop': False,
            'boss_refresh': 3,
            'missing': [{'type': 2, 'field': 'kill_enemy', 'remaining': 12}],
        })
        self.assertTrue(flags['force_auto_fight_without_loop'])

    def test_flags_clear_before_boss_all_enemies(self):
        from module.war_archives_catchup.policy import flags_for_chapter

        flags = flags_for_chapter({
            'can_loop': False,
            'boss_refresh': 5,
            'missing': [{'type': 3, 'field': 'kill_all', 'remaining': 0}],
        })
        self.assertTrue(flags['auto_fight_clear_before_boss'])
        self.assertTrue(flags['force_auto_fight_without_loop'])

    def test_flags_escort_remaining_vs_boss_refresh(self):
        from module.war_archives_catchup.policy import flags_for_chapter

        over = flags_for_chapter({
            'can_loop': True,
            'boss_refresh': 5,
            'missing': [{'type': 2, 'field': 'kill_enemy', 'remaining': 8}],
        })
        self.assertTrue(over['auto_fight_clear_before_boss'])
        self.assertFalse(over['force_auto_fight_without_loop'])
        under = flags_for_chapter({
            'can_loop': True,
            'boss_refresh': 5,
            'missing': [{'type': 2, 'field': 'kill_enemy', 'remaining': 3}],
        })
        self.assertFalse(under['auto_fight_clear_before_boss'])

    def test_flags_boxes_only_do_not_force_clear(self):
        from module.war_archives_catchup.policy import flags_for_chapter

        flags = flags_for_chapter({
            'can_loop': True,
            'boss_refresh': 5,
            'missing': [{'type': 0, 'field': 'take_box_count', 'remaining': 2}],
        })
        self.assertFalse(flags['auto_fight_clear_before_boss'])
        self.assertFalse(flags['force_auto_fight_without_loop'])

    def test_watch_does_not_end_during_combat_or_stale(self):
        from module.war_archives_catchup.policy import watch_in_sortie, watch_map_ended

        self.assertFalse(watch_map_ended(None, saw_in_map=True, grace_ok=True))
        battle = {
            'scene_key': 'BATTLE',
            'chapter': {'active': True},
            'battle': {'state': 'BATTLE_FIGHT'},
        }
        self.assertTrue(watch_in_sortie(battle))
        self.assertFalse(watch_map_ended(battle, saw_in_map=True, grace_ok=True))
        load = {'scene_key': 'COMBATLOAD', 'chapter': {'active': False}, 'level': {}}
        self.assertTrue(watch_in_sortie(load))
        self.assertFalse(watch_map_ended(load, saw_in_map=True, grace_ok=True))
        report = {
            'scene_key': 'LEVEL',
            'chapter': {'active': True},
            'level': {'in_map': False},
            'battle': {'state': 'BATTLE_REPORT'},
        }
        self.assertTrue(watch_in_sortie(report))
        self.assertFalse(watch_map_ended(report, saw_in_map=True, grace_ok=True))

    def test_watch_on_map_ui_not_home_with_active_chapter(self):
        from module.war_archives_catchup.policy import (
            wa_goto_ready_to_sit,
            watch_in_sortie,
            watch_map_ended,
            watch_on_map_ui,
        )

        home = {
            'scene_key': 'MAINUI',
            'chapter': {'active': True, 'id': 16004, 'auto_fight': True},
            'level': {'in_map': False},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertTrue(watch_in_sortie(home))
        self.assertFalse(watch_on_map_ui(home))
        self.assertFalse(watch_map_ended(home, saw_in_map=True, grace_ok=True))
        self.assertFalse(wa_goto_ready_to_sit({'already_in_map': True}, home))
        self.assertFalse(wa_goto_ready_to_sit({'already_in_map': True}, None))
        on_map = {
            'scene_key': 'LEVEL',
            'chapter': {'active': True, 'id': 16004, 'auto_fight': True},
            'level': {'in_map': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertTrue(watch_on_map_ui(on_map))
        self.assertTrue(wa_goto_ready_to_sit({'already_in_map': True}, on_map))
        self.assertFalse(wa_goto_ready_to_sit(
            {'already_in_map': True, 'resume_active': True}, on_map))
        self.assertTrue(wa_goto_ready_to_sit({'pending_battle': True}, home))

        hub = {
            'scene_key': 'LEVEL',
            'page': 'page_campaign_menu',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': True},
            'level': {'in_map': False, 'entrance': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertFalse(watch_on_map_ui(hub))
        self.assertTrue(watch_in_sortie(hub))
        chapter_list = {
            'scene_key': 'LEVEL',
            'page': 'page_campaign',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
            'level': {'in_map': False, 'entrance': False},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertFalse(watch_on_map_ui(chapter_list))

        live_map_stale_entrance = {
            'scene_key': 'LEVEL',
            'page': 'page_in_map',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
            'level': {'in_map': True, 'entrance': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertTrue(watch_on_map_ui(live_map_stale_entrance))
        self.assertTrue(watch_in_sortie(live_map_stale_entrance))

    def test_leftover_off_map_ui_menus(self):
        from module.war_archives_catchup.policy import leftover_off_map_ui

        home = {
            'scene_key': 'MAINUI',
            'page': 'page_main',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
            'level': {'in_map': False, 'entrance': False},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertTrue(leftover_off_map_ui(home))
        attack = {
            'scene_key': 'LEVEL',
            'page': 'page_campaign_menu',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': True},
            'level': {'in_map': False, 'entrance': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertTrue(leftover_off_map_ui(attack))
        on_map = {
            'scene_key': 'LEVEL',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': True},
            'level': {'in_map': True, 'entrance': False},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertFalse(leftover_off_map_ui(on_map))
        battle = {
            'scene_key': 'BATTLE',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': True},
            'battle': {'state': 'BATTLE_FIGHT'},
        }
        self.assertFalse(leftover_off_map_ui(battle))
        dock = {
            'scene_key': 'DOCKYARD',
            'page': 'page_dock',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': True},
            'level': {'in_map': False},
        }
        self.assertFalse(leftover_off_map_ui(dock))
        live_map_stale_entrance = {
            'scene_key': 'LEVEL',
            'page': 'page_in_map',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
            'level': {'in_map': True, 'entrance': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertFalse(leftover_off_map_ui(live_map_stale_entrance))

    def test_watch_ends_on_level_after_grace(self):
        from module.war_archives_catchup.policy import watch_map_ended

        select = {
            'scene_key': 'LEVEL',
            'chapter': {'active': False},
            'level': {'in_map': False, 'remaster': True, 'info_showing': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertFalse(watch_map_ended(select, saw_in_map=True, grace_ok=False))
        self.assertFalse(watch_map_ended(select, saw_in_map=False, grace_ok=True))
        self.assertTrue(watch_map_ended(select, saw_in_map=True, grace_ok=True))

    def test_is_data_key_msgbox(self):
        from module.war_archives_catchup.policy import is_data_key_msgbox

        self.assertFalse(is_data_key_msgbox(None))
        self.assertFalse(is_data_key_msgbox({'showing': True}))
        self.assertFalse(is_data_key_msgbox({
            'showing': True,
            'content': 'Retreat from this stage?',
        }))
        self.assertTrue(is_data_key_msgbox({
            'showing': True,
            'has_yes': True,
            'content': 'Unlocking this stage requires 5 Data Key(s). Would you like to unlock this stage?',
        }))
        self.assertTrue(is_data_key_msgbox({
            'showing': True,
            'content': '进入所选关卡需要消耗档案秘钥x5，是否进入？',
        }))
        self.assertTrue(is_data_key_msgbox({
            'showing': True,
            'content': 'ステージを開放するにはデータキーx5を消費します。',
        }))

    def test_is_low_emotion_msgbox(self):
        from module.war_archives_catchup.policy import is_low_emotion_msgbox

        self.assertFalse(is_low_emotion_msgbox(None))
        self.assertFalse(is_low_emotion_msgbox({
            'showing': True,
            'content': 'Unlocking this stage requires 5 Data Key(s).',
        }))
        self.assertTrue(is_low_emotion_msgbox({
            'showing': True,
            'has_no': True,
            'content': 'Your fleet is exhausted. Continue sortie?',
        }))

    def test_is_dock_full_msgbox(self):
        from module.war_archives_catchup.policy import (
            is_dock_full_msgbox,
            sitback_dock_full_from_state,
            sitback_unknown_modal,
        )

        self.assertFalse(is_dock_full_msgbox(None))
        self.assertFalse(is_dock_full_msgbox({
            'showing': True,
            'content': 'Unlocking this stage requires 5 Data Key(s).',
        }))
        self.assertTrue(is_dock_full_msgbox({
            'showing': True,
            'content': 'Please sort or expand your dock!',
        }))
        self.assertTrue(is_dock_full_msgbox({
            'showing': True,
            'content': '船坞已满，请前往整理或扩展',
        }))
        self.assertTrue(is_dock_full_msgbox({
            'showing': True,
            'content': 'ドックが一杯です。艦を退役するか、所持枠拡張をお願いします',
        }))
        self.assertTrue(is_dock_full_msgbox({
            'showing': True,
            'dock_overload': True,
            'content': '',
        }))
        self.assertTrue(sitback_dock_full_from_state({
            'player': {'dock_full': True},
        }))
        self.assertTrue(sitback_dock_full_from_state({
            'player': {'dock_full': False},
            'msgbox': {
                'showing': True,
                'content': 'Please sort or expand your dock!',
            },
        }))
        self.assertFalse(sitback_dock_full_from_state({
            'player': {'dock_full': False},
            'msgbox': {'showing': False},
        }))
        self.assertTrue(sitback_unknown_modal({
            'msgbox': {'showing': True, 'content': 'Retreat from this stage?'},
        }))
        self.assertFalse(sitback_unknown_modal({
            'player': {'dock_full': True},
            'msgbox': {
                'showing': True,
                'content': 'Please sort or expand your dock!',
            },
        }))
        from module.war_archives_catchup.policy import sitback_on_dock_scene
        self.assertTrue(sitback_on_dock_scene({'scene_key': 'DOCKYARD'}))
        self.assertTrue(sitback_on_dock_scene({'page': 'page_dock'}))
        self.assertFalse(sitback_on_dock_scene({'scene_key': 'LEVEL'}))

    def test_battles_for_emotion(self):
        from module.war_archives_catchup.policy import battles_for_emotion

        self.assertEqual(battles_for_emotion(None), 6)
        self.assertEqual(battles_for_emotion({
            'missing': [{'type': 2, 'remaining': 12}],
        }, {'auto_fight_clear_before_boss': False}), 6)
        self.assertEqual(battles_for_emotion({
            'missing': [{'type': 2, 'remaining': 12}],
        }, {'auto_fight_clear_before_boss': True}), 12)
        self.assertEqual(battles_for_emotion({
            'missing': [{'type': 2, 'remaining': 10, 'field': 'kill_enemy'}],
        }, {'auto_fight_clear_before_boss': True}), 11)


class TestWarArchivesCatchupActions(unittest.TestCase):
    def test_wa_verbs_send_args(self):
        from module.alas_bridge import actions

        seen = []

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                seen.append((name, args or {}, timeout))
                if name == 'apply_fleet_preset':
                    result = {'applied': True, 'swap': args.get('swap')}
                elif name == 'set_mod_flags':
                    result = {'previous': {}, 'current': args}
                else:
                    result = {'ok': True, 'chapter_id': (args or {}).get('chapter_id')}
                return {'id': '1', 'ok': True, 'name': name, 'result': result}

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = FakeRpc
        actions.GameState = FakeGS
        try:
            self.assertIsNotNone(actions.get_wa_status(object()))
            self.assertIsNotNone(actions.wa_goto(object(), chapter_id=16004, remaster_id=7))
            self.assertIsNotNone(actions.set_mod_flags(
                object(), force_auto_fight_without_loop=True, auto_fight_clear_before_boss=False))
            self.assertIsNotNone(actions.apply_fleet_preset(object(), swap=True, chapter_id=16004))
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = orig_gs

        names = [row[0] for row in seen]
        self.assertEqual(names, [
            'get_wa_status', 'wa_goto', 'set_mod_flags', 'apply_fleet_preset',
        ])
        goto_args = seen[1][1]
        self.assertEqual(goto_args['chapter_id'], 16004)
        self.assertEqual(goto_args['remaster_id'], 7)
        flag_args = seen[2][1]
        self.assertTrue(flag_args['force_auto_fight_without_loop'])
        self.assertFalse(flag_args['auto_fight_clear_before_boss'])
        fleet_args = seen[3][1]
        self.assertTrue(fleet_args['swap'])
        self.assertEqual(fleet_args['chapter_id'], 16004)

    def test_apply_fleet_preset_rejects_unapplied(self):
        from module.alas_bridge import actions

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                return {
                    'id': '1',
                    'ok': True,
                    'name': name,
                    'result': {'applied': False, 'error': 'empty_fleet_5'},
                }

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = FakeRpc
        actions.GameState = FakeGS
        try:
            self.assertIsNone(actions.apply_fleet_preset(object(), swap=False, chapter_id=1))
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = orig_gs


class TestSitback(unittest.TestCase):
    def test_should_skip_wait(self):
        from module.alas_bridge.sitback import should_skip_wait

        self.assertTrue(should_skip_wait('Restart'))
        self.assertTrue(should_skip_wait('WarArchivesCatchup'))
        self.assertFalse(should_skip_wait('Main'))
        self.assertFalse(should_skip_wait('Hard'))

    def test_wait_idle_when_bridge_off_or_no_chapter(self):
        from module.alas_bridge import actions, sitback

        orig_en = actions.bridge_enabled
        orig_read = sitback._read_state
        try:
            actions.bridge_enabled = lambda config: False
            self.assertEqual(sitback.wait_leftover_autofight(object(), None), 'idle')
            actions.bridge_enabled = lambda config: True
            sitback._read_state = lambda config, max_age=8.0: {
                'scene_key': 'MAINUI',
                'chapter': {'active': False},
            }
            self.assertEqual(sitback.wait_leftover_autofight(object(), None), 'idle')
        finally:
            actions.bridge_enabled = orig_en
            sitback._read_state = orig_read

    def test_wait_ended_when_chapter_clears(self):
        from module.alas_bridge import actions, sitback

        class Dev:
            def stuck_record_clear(self):
                pass

        n = {'i': 0}

        def fake_read(config, max_age=8.0):
            n['i'] += 1
            if n['i'] <= 2:
                return {
                    'scene_key': 'LEVEL',
                    'chapter': {'active': True, 'id': 12204, 'auto_fight': True},
                    'level': {'in_map': True},
                    'battle': {'state': 'BATTLE_IDLE'},
                }
            return {
                'scene_key': 'LEVEL',
                'chapter': {'active': False},
                'level': {'in_map': False},
                'battle': {'state': 'BATTLE_IDLE'},
            }

        orig_en = actions.bridge_enabled
        orig_read = sitback._read_state
        orig_sleep = sitback.time.sleep
        try:
            actions.bridge_enabled = lambda config: True
            sitback._read_state = fake_read
            sitback.time.sleep = lambda s: None
            self.assertEqual(sitback.wait_leftover_autofight(object(), Dev()), 'ended')
        finally:
            actions.bridge_enabled = orig_en
            sitback._read_state = orig_read
            sitback.time.sleep = orig_sleep

    def test_wait_clicks_battle_report_when_auto_off(self):
        from module.alas_bridge import actions, sitback

        class Dev:
            def stuck_record_clear(self):
                pass

        clicks = []
        n = {'i': 0}

        def fake_read(config, max_age=8.0):
            n['i'] += 1
            if n['i'] <= 3:
                return {
                    'scene_key': 'BATTLE',
                    'chapter': {'active': False},
                    'battle': {'state': 'BATTLE_REPORT'},
                }
            return {
                'scene_key': 'MAINUI',
                'chapter': {'active': False},
                'battle': {'state': 'BATTLE_IDLE'},
            }

        def fake_click(*a, **k):
            clicks.append(1)
            return True

        orig_en = actions.bridge_enabled
        orig_read = sitback._read_state
        orig_sleep = sitback.time.sleep
        orig_click = sitback.handle_sitback_battle_status
        try:
            actions.bridge_enabled = lambda config: True
            sitback._read_state = fake_read
            sitback.time.sleep = lambda s: None
            sitback.handle_sitback_battle_status = fake_click
            self.assertEqual(sitback.wait_leftover_autofight(object(), Dev()), 'ended')
            self.assertTrue(clicks)
        finally:
            actions.bridge_enabled = orig_en
            sitback._read_state = orig_read
            sitback.time.sleep = orig_sleep
            sitback.handle_sitback_battle_status = orig_click

    def test_need_battle_click_raid_report(self):
        from module.alas_bridge.sitback import _need_battle_click

        self.assertTrue(_need_battle_click({
            'scene_key': 'BATTLE',
            'chapter': {},
            'battle': {'state': 'BATTLE_REPORT'},
        }))
        self.assertFalse(_need_battle_click({
            'scene_key': 'BATTLE',
            'chapter': {'auto_fight': True},
            'battle': {'state': 'BATTLE_REPORT'},
        }))
        self.assertFalse(_need_battle_click({
            'scene_key': 'BATTLE',
            'chapter': {},
            'battle': {'state': 'BATTLE_FIGHT'},
        }))

    def test_wait_does_not_resume_from_dockyard(self):
        from module.alas_bridge import actions, sitback

        class Dev:
            def stuck_record_clear(self):
                pass

        resumed = []
        n = {'i': 0}

        def fake_read(config, max_age=8.0):
            n['i'] += 1
            if n['i'] <= 2:
                return {
                    'scene_key': 'DOCKYARD',
                    'page': 'page_dock',
                    'chapter': {'active': True, 'id': 2100033, 'auto_fight': True},
                    'player': {'dock_full': True},
                    'level': {'in_map': False},
                }
            return {
                'scene_key': 'LEVEL',
                'chapter': {'active': False},
                'level': {'in_map': False},
            }

        orig_en = actions.bridge_enabled
        orig_read = sitback._read_state
        orig_sleep = sitback.time.sleep
        orig_resume = sitback._resume_active_chapter
        orig_dock = sitback.handle_sitback_dock_full
        try:
            actions.bridge_enabled = lambda config: True
            sitback._read_state = fake_read
            sitback.time.sleep = lambda s: None
            sitback._resume_active_chapter = lambda *a, **k: resumed.append(1) or True
            sitback.handle_sitback_dock_full = lambda *a, **k: False
            self.assertEqual(sitback.wait_leftover_autofight(object(), Dev()), 'ended')
            self.assertEqual(resumed, [])
        finally:
            actions.bridge_enabled = orig_en
            sitback._read_state = orig_read
            sitback.time.sleep = orig_sleep
            sitback._resume_active_chapter = orig_resume
            sitback.handle_sitback_dock_full = orig_dock

    def test_wait_resumes_again_when_stuck_on_menu(self):
        from module.alas_bridge import actions, sitback

        class Dev:
            def stuck_record_clear(self):
                pass

        resumed = []
        n = {'i': 0}

        def fake_read(config, max_age=8.0):
            n['i'] += 1
            if n['i'] <= 4:
                return {
                    'scene_key': 'LEVEL',
                    'page': 'page_campaign_menu',
                    'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
                    'level': {'in_map': False, 'entrance': True},
                    'battle': {'state': 'BATTLE_IDLE'},
                }
            return {
                'scene_key': 'LEVEL',
                'chapter': {'active': False},
                'level': {'in_map': False, 'entrance': False},
            }

        orig_en = actions.bridge_enabled
        orig_read = sitback._read_state
        orig_sleep = sitback.time.sleep
        orig_resume = sitback._resume_active_chapter
        orig_every = sitback.RESUME_RETRY_EVERY
        orig_dock = sitback.handle_sitback_dock_full
        try:
            actions.bridge_enabled = lambda config: True
            sitback._read_state = fake_read
            sitback.time.sleep = lambda s: None
            sitback.RESUME_RETRY_EVERY = 0
            sitback._resume_active_chapter = lambda *a, **k: resumed.append(1) or True
            sitback.handle_sitback_dock_full = lambda *a, **k: False
            self.assertEqual(sitback.wait_leftover_autofight(object(), Dev()), 'ended')
            self.assertGreaterEqual(len(resumed), 2)
        finally:
            actions.bridge_enabled = orig_en
            sitback._read_state = orig_read
            sitback.time.sleep = orig_sleep
            sitback._resume_active_chapter = orig_resume
            sitback.RESUME_RETRY_EVERY = orig_every
            sitback.handle_sitback_dock_full = orig_dock

    def test_leftover_needs_enable_auto(self):
        from module.alas_bridge.sitback import leftover_needs_enable_auto

        on_map_off = {
            'scene_key': 'LEVEL',
            'page': 'page_in_map',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
            'level': {'in_map': True, 'entrance': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertTrue(leftover_needs_enable_auto(on_map_off))
        on_map_on = {
            'scene_key': 'LEVEL',
            'page': 'page_in_map',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': True},
            'level': {'in_map': True, 'entrance': False},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertFalse(leftover_needs_enable_auto(on_map_on))
        hub = {
            'scene_key': 'LEVEL',
            'page': 'page_campaign_menu',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
            'level': {'in_map': False, 'entrance': True},
            'battle': {'state': 'BATTLE_IDLE'},
        }
        self.assertFalse(leftover_needs_enable_auto(hub))
        battle = {
            'scene_key': 'BATTLE',
            'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
            'battle': {'state': 'BATTLE_REPORT'},
        }
        self.assertFalse(leftover_needs_enable_auto(battle))

    def test_wait_enables_auto_when_off_on_map(self):
        from module.alas_bridge import actions, sitback

        class Dev:
            def stuck_record_clear(self):
                pass

        flags = []
        n = {'i': 0}

        def fake_read(config, max_age=8.0):
            n['i'] += 1
            if n['i'] <= 3:
                return {
                    'scene_key': 'LEVEL',
                    'page': 'page_in_map',
                    'chapter': {'active': True, 'id': 1604, 'auto_fight': False},
                    'level': {'in_map': True, 'entrance': True},
                    'battle': {'state': 'BATTLE_IDLE'},
                }
            return {
                'scene_key': 'LEVEL',
                'chapter': {'active': False},
                'level': {'in_map': False},
            }

        orig_en = actions.bridge_enabled
        orig_read = sitback._read_state
        orig_sleep = sitback.time.sleep
        orig_flags = actions.set_mod_flags
        orig_dock = sitback.handle_sitback_dock_full
        orig_every = sitback.AUTO_ENABLE_EVERY
        try:
            actions.bridge_enabled = lambda config: True
            sitback._read_state = fake_read
            sitback.time.sleep = lambda s: None
            sitback.AUTO_ENABLE_EVERY = 0
            sitback.handle_sitback_dock_full = lambda *a, **k: False
            actions.set_mod_flags = lambda *a, **k: flags.append(k) or {}
            self.assertEqual(sitback.wait_leftover_autofight(object(), Dev()), 'ended')
            self.assertTrue(flags)
            self.assertTrue(flags[0].get('force_auto_fight_without_loop'))
        finally:
            actions.bridge_enabled = orig_en
            sitback._read_state = orig_read
            sitback.time.sleep = orig_sleep
            actions.set_mod_flags = orig_flags
            sitback.handle_sitback_dock_full = orig_dock
            sitback.AUTO_ENABLE_EVERY = orig_every

    def test_dock_full_runs_retirement(self):
        from module.alas_bridge import actions, sitback

        class Dev:
            def __init__(self):
                self.shots = 0

            def screenshot(self):
                self.shots += 1
                return True

            def stuck_record_clear(self):
                pass

        class Retire:
            def __init__(self, popup=False, on_page=False):
                self.calls = 0
                self.handler_calls = 0
                self.popup = popup
                self.on_page = on_page

            def handle_retirement(self):
                self.calls += 1
                return self.calls > 1

            def dock_full_popup_appear(self):
                return self.popup

            def _on_retirement_page(self, interval=0):
                return self.on_page

            def _retire_handler(self, mode=None):
                self.handler_calls += 1
                return 10

        orig_dock = actions.dock_full_from_heartbeat
        orig_sleep = sitback.time.sleep
        try:
            sitback.time.sleep = lambda s: None
            actions.dock_full_from_heartbeat = lambda config, max_age=8.0: True
            retire = Retire()
            dev = Dev()
            self.assertTrue(sitback.handle_sitback_dock_full(object(), dev, handler=retire))
            self.assertEqual(retire.calls, 1)
            self.assertGreaterEqual(dev.shots, 1)
            actions.dock_full_from_heartbeat = lambda config, max_age=8.0: False
            self.assertFalse(sitback.handle_sitback_dock_full(object(), dev, handler=retire))
            self.assertEqual(retire.calls, 1)
            self.assertTrue(sitback.handle_sitback_dock_full(
                object(),
                dev,
                handler=retire,
                state={'player': {'dock_full': False}, 'msgbox': {
                    'showing': True,
                    'content': 'Please sort or expand your dock!',
                }},
            ))
            self.assertEqual(retire.calls, 2)
            peek_miss = Retire(popup=False)
            self.assertFalse(sitback.handle_sitback_dock_full(
                object(), Dev(), handler=peek_miss, force_peek=True
            ))
            self.assertEqual(peek_miss.calls, 0)
            peek_hit = Retire(popup=True)
            peek_dev = Dev()
            self.assertTrue(sitback.handle_sitback_dock_full(
                object(), peek_dev, handler=peek_hit, force_peek=True
            ))
            self.assertEqual(peek_hit.calls, 1)
            self.assertGreaterEqual(peek_dev.shots, 1)
            page = Retire(on_page=True)
            page_dev = Dev()
            self.assertTrue(sitback.handle_sitback_dock_full(
                object(),
                page_dev,
                handler=page,
                state={'player': {'dock_full': True}, 'scene_key': 'DOCKYARD'},
            ))
            self.assertEqual(page.handler_calls, 1)
            self.assertEqual(page.calls, 0)
        finally:
            actions.dock_full_from_heartbeat = orig_dock
            sitback.time.sleep = orig_sleep


if __name__ == '__main__':
    unittest.main()
