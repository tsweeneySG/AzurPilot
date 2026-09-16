import unittest

from module.alas_bridge.os_missions import (
    is_archive,
    is_monthly,
    is_siren,
    pick_next_goto,
    pick_submit_ids,
    run_os_accept_daily,
    run_os_mission_handshake,
)


class TestOsMissionPick(unittest.TestCase):
    def test_skip_monthly_and_siren(self):
        doing = [
            {'id': 1, 'state': 1, 'type': 7, 'monthly': True, 'following_entrance': 10},
            {'id': 2, 'state': 1, 'type': 5, 'siren': True, 'following_entrance': 11},
            {'id': 3, 'state': 1, 'type': 0, 'priority': 2, 'following_entrance': 12},
            {'id': 4, 'state': 1, 'type': 0, 'priority': 9, 'following_entrance': 13},
        ]
        nxt = pick_next_goto(doing, skip_siren=True, skip_monthly=True)
        self.assertEqual(nxt['id'], 4)
        nxt = pick_next_goto(doing, skip_siren=False, skip_monthly=True)
        self.assertEqual(nxt['id'], 4)
        nxt = pick_next_goto(doing, skip_entrances={13})
        self.assertEqual(nxt['id'], 3)

    def test_submit_finished_skips_monthly(self):
        doing = [
            {'id': 7, 'state': 2, 'type': 7, 'monthly': True},
            {'id': 8, 'state': 2, 'type': 0},
            {'id': 9, 'state': 1, 'type': 0},
        ]
        self.assertEqual(pick_submit_ids(doing), [8])

    def test_archive_flags(self):
        self.assertTrue(is_archive({'collection': True}))
        self.assertTrue(is_archive({'map_kind': 'archive_chapter'}))
        self.assertFalse(is_archive({'type': 0}))
        self.assertTrue(is_siren({'type': 5}))
        self.assertTrue(is_monthly({'type': 7}))


class TestOsMissionHandshake(unittest.TestCase):
    def test_unloaded_world_falls_back(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig = om.get_os_missions
        om.get_os_missions = lambda config, timeout=12.0: {'loaded': False, 'doing': []}
        try:
            self.assertIsNone(run_os_mission_handshake(Cfg()))
        finally:
            om.get_os_missions = orig

    def test_no_tasks_returns_false(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig = om.get_os_missions
        om.get_os_missions = lambda config, timeout=12.0: {'loaded': True, 'doing': []}
        try:
            self.assertIs(run_os_mission_handshake(Cfg()), False)
        finally:
            om.get_os_missions = orig

    def test_goto_then_in_map(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig_get = om.get_os_missions
        orig_goto = om.os_goto_task
        orig_wait = om.wait_os_arrival
        orig_submit = om.os_submit_tasks
        orig_zone = om.os_goto_zone
        om.get_os_missions = lambda config, timeout=12.0: {
            'loaded': True,
            'doing': [{
                'id': 3100, 'state': 1, 'type': 0, 'priority': 1,
                'following_entrance': 44,
            }],
        }
        om.os_submit_tasks = lambda *a, **k: {'sent': []}
        om.os_goto_task = lambda *a, **k: {
            'sent': True, 'task_id': 3100, 'following_entrance': 44,
        }
        om.wait_os_arrival = lambda *a, **k: {
            'in_map': True, 'zone_id': 44, 'ui': 'map',
        }
        om.os_goto_zone = lambda *a, **k: self.fail('should not transport')
        try:
            self.assertEqual(run_os_mission_handshake(Cfg()), 'pinned_at_mission_zone')
        finally:
            om.get_os_missions = orig_get
            om.os_goto_task = orig_goto
            om.wait_os_arrival = orig_wait
            om.os_submit_tasks = orig_submit
            om.os_goto_zone = orig_zone

    def test_already_in_zone(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig_get = om.get_os_missions
        orig_goto = om.os_goto_task
        orig_wait = om.wait_os_arrival
        orig_submit = om.os_submit_tasks
        om.get_os_missions = lambda config, timeout=12.0: {
            'loaded': True,
            'doing': [{'id': 1, 'state': 1, 'type': 0, 'following_entrance': 8}],
        }
        om.os_submit_tasks = lambda *a, **k: {'sent': []}
        om.os_goto_task = lambda *a, **k: {
            'sent': False, 'already_in_zone': True, 'task_id': 1, 'following_entrance': 8,
        }
        om.wait_os_arrival = lambda *a, **k: {'in_map': True, 'zone_id': 8, 'ui': 'map'}
        try:
            self.assertEqual(run_os_mission_handshake(Cfg()), 'already_at_mission_zone')
        finally:
            om.get_os_missions = orig_get
            om.os_goto_task = orig_goto
            om.wait_os_arrival = orig_wait
            om.os_submit_tasks = orig_submit

    def test_handshake_globe_pin_is_not_arrival(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        waits = []
        orig_get = om.get_os_missions
        orig_goto = om.os_goto_task
        orig_wait = om.wait_os_arrival
        orig_submit = om.os_submit_tasks
        orig_zone = om.os_goto_zone
        om.get_os_missions = lambda config, timeout=12.0: {
            'loaded': True,
            'doing': [{'id': 1, 'state': 1, 'type': 0, 'following_entrance': 64}],
        }
        om.os_submit_tasks = lambda *a, **k: {'sent': []}
        om.os_goto_task = lambda *a, **k: {
            'sent': True, 'task_id': 1, 'following_entrance': 64,
        }
        om.os_goto_zone = lambda *a, **k: {'sent': True, 'zone_id': 64}

        def wait(*a, **k):
            waits.append(k)
            return {'in_map': False, 'ui': 'globe', 'pinned': True, 'zone_id': 64}

        om.wait_os_arrival = wait
        try:
            self.assertIs(run_os_mission_handshake(Cfg()), False)
            self.assertTrue(any(w.get('require_in_map') for w in waits))
        finally:
            om.get_os_missions = orig_get
            om.os_goto_task = orig_goto
            om.wait_os_arrival = orig_wait
            om.os_submit_tasks = orig_submit
            om.os_goto_zone = orig_zone

    def test_handshake_skips_empty_entrance_then_next(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig_get = om.get_os_missions
        orig_goto = om.os_goto_task
        orig_wait = om.wait_os_arrival
        orig_submit = om.os_submit_tasks
        orig_zone = om.os_goto_zone
        got_ids = []
        om.get_os_missions = lambda config, timeout=12.0: {
            'loaded': True,
            'doing': [
                {'id': 1, 'state': 1, 'type': 0, 'priority': 9, 'following_entrance': 64},
                {'id': 2, 'state': 1, 'type': 0, 'priority': 1, 'following_entrance': 12},
            ],
        }
        om.os_submit_tasks = lambda *a, **k: {'sent': []}

        def goto(config, task_id=None, **k):
            got_ids.append(int(task_id))
            return {
                'sent': True, 'task_id': int(task_id),
                'following_entrance': 64 if int(task_id) == 1 else 12,
            }

        om.os_goto_task = goto
        om.os_goto_zone = lambda *a, **k: {'sent': True}

        def wait(config, zone_id=None, **k):
            if zone_id is not None and int(zone_id) == 64:
                return {'in_map': False, 'ui': 'globe', 'pinned': True, 'zone_id': 64}
            return {'in_map': True, 'ui': 'map', 'zone_id': 12}

        om.wait_os_arrival = wait
        try:
            self.assertEqual(run_os_mission_handshake(Cfg()), 'pinned_at_mission_zone')
            self.assertEqual(got_ids, [1, 2])
        finally:
            om.get_os_missions = orig_get
            om.os_goto_task = orig_goto
            om.wait_os_arrival = orig_wait
            om.os_submit_tasks = orig_submit
            om.os_goto_zone = orig_zone

    def test_accept_limit_is_false(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig = om.os_accept_daily
        orig_en = om.bridge_enabled
        om.bridge_enabled = lambda config: True
        om.os_accept_daily = lambda *a, **k: {'sent': [], 'reason': 'limit'}
        try:
            self.assertIs(run_os_accept_daily(Cfg()), False)
        finally:
            om.os_accept_daily = orig
            om.bridge_enabled = orig_en

    def test_bridge_off_is_none(self):
        class Cfg:
            Optimization_SweeneyBridge = False

        self.assertIsNone(run_os_mission_handshake(Cfg()))
        self.assertIsNone(run_os_accept_daily(Cfg()))


class TestOsGlobeGoto(unittest.TestCase):
    def test_map_types_prefer_safe_then_base(self):
        from module.alas_bridge.os_missions import map_types_for_alas
        self.assertEqual(
            map_types_for_alas(('SAFE', 'DANGEROUS')),
            ['complete_chapter', 'base_chapter'],
        )
        self.assertEqual(
            map_types_for_alas('STRONGHOLD'),
            ['sairen_chapter', 'base_chapter'],
        )

    def test_port_alas_game_id_mapping(self):
        from module.alas_bridge.os_missions import (
            alas_zone_to_game_entrance, game_entrance_to_alas_zone)
        self.assertEqual(alas_zone_to_game_entrance(0), 1)  # NY City
        self.assertEqual(alas_zone_to_game_entrance(7), 8)  # Dakar
        self.assertEqual(alas_zone_to_game_entrance(13), 13)  # Caribbean C
        self.assertEqual(game_entrance_to_alas_zone(1), 0)
        self.assertEqual(game_entrance_to_alas_zone(8), 7)
        self.assertEqual(game_entrance_to_alas_zone(13), 13)

    def test_globe_goto_ny_sends_game_entrance_1(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        sent = []
        orig_en = om.bridge_enabled
        orig_zone = om.os_goto_zone
        orig_wait = om.wait_os_arrival
        om.bridge_enabled = lambda config: True
        om.os_goto_zone = lambda config, zone_id, **k: (
            sent.append(int(zone_id)) or {'sent': True, 'zone_id': int(zone_id)})
        om.wait_os_arrival = lambda *a, **k: {'in_map': True, 'zone_id': 1, 'ui': 'map'}
        try:
            self.assertIs(om.run_os_globe_goto(Cfg(), 0), True)
            self.assertEqual(sent, [1])
        finally:
            om.bridge_enabled = orig_en
            om.os_goto_zone = orig_zone
            om.wait_os_arrival = orig_wait

    def test_globe_goto_waits_in_map(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig_en = om.bridge_enabled
        orig_zone = om.os_goto_zone
        orig_wait = om.wait_os_arrival
        om.bridge_enabled = lambda config: True
        om.os_goto_zone = lambda *a, **k: {'sent': True, 'zone_id': 13}
        om.wait_os_arrival = lambda *a, **k: {'in_map': True, 'zone_id': 13, 'ui': 'map'}
        try:
            self.assertIs(om.run_os_globe_goto(Cfg(), 13, types=('SAFE', 'DANGEROUS')), True)
        finally:
            om.bridge_enabled = orig_en
            om.os_goto_zone = orig_zone
            om.wait_os_arrival = orig_wait

    def test_globe_goto_already_active_still_waits(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig_en = om.bridge_enabled
        orig_zone = om.os_goto_zone
        orig_wait = om.wait_os_arrival
        waited = []
        om.bridge_enabled = lambda config: True
        om.os_goto_zone = lambda *a, **k: {
            'already_active': True, 'in_map': True, 'zone_id': 13}
        def wait(*a, **k):
            waited.append(True)
            return {'in_map': True, 'zone_id': 13, 'ui': 'map'}
        om.wait_os_arrival = wait
        try:
            self.assertIs(om.run_os_globe_goto(Cfg(), 13), False)
            self.assertTrue(waited)
        finally:
            om.bridge_enabled = orig_en
            om.os_goto_zone = orig_zone
            om.wait_os_arrival = orig_wait

    def test_globe_goto_globe_pin_is_not_arrival(self):
        from module.alas_bridge import os_missions as om

        class Cfg:
            Optimization_SweeneyBridge = True

        orig_en = om.bridge_enabled
        orig_zone = om.os_goto_zone
        orig_wait = om.wait_os_arrival
        om.bridge_enabled = lambda config: True
        om.os_goto_zone = lambda *a, **k: {'sent': True, 'zone_id': 1}
        om.wait_os_arrival = lambda *a, **k: {'in_map': False, 'ui': 'globe', 'pinned': True}
        try:
            self.assertIsNone(om.run_os_globe_goto(Cfg(), 1))
        finally:
            om.bridge_enabled = orig_en
            om.os_goto_zone = orig_zone
            om.wait_os_arrival = orig_wait


if __name__ == '__main__':
    unittest.main()
