import unittest
from datetime import datetime, timedelta

from module.island.island_management import (
    heartbeat_island_scene_ready,
    mega_is_done,
    next_run_from_idle,
)


class TestNextRunFromIdle(unittest.TestCase):
    def test_missing_uses_thirty_minute_fallback(self):
        now = datetime(2026, 10, 29, 12, 0, 0)
        self.assertEqual(next_run_from_idle(None, now), now + timedelta(minutes=30))
        self.assertEqual(next_run_from_idle('nope', now), now + timedelta(minutes=30))
        self.assertEqual(next_run_from_idle(0, now), now + timedelta(minutes=30))
        self.assertEqual(next_run_from_idle(-5, now), now + timedelta(minutes=30))

    def test_past_or_soon_idle_uses_two_minute_floor(self):
        now = datetime(2026, 10, 29, 12, 0, 0)
        stamp = now.timestamp()
        self.assertEqual(next_run_from_idle(stamp, now), now + timedelta(minutes=2))
        self.assertEqual(
            next_run_from_idle(stamp + 30, now),
            now + timedelta(minutes=2),
        )

    def test_future_idle_is_kept(self):
        now = datetime(2026, 10, 29, 12, 0, 0)
        target = now + timedelta(hours=3)
        self.assertEqual(next_run_from_idle(target.timestamp(), now), target)


class TestIslandSceneHud(unittest.TestCase):
    def test_scene_wait_imports_ui_island_check(self):
        import inspect

        import module.island.assets as island_assets
        from module.island.island_management import IslandManagement
        from module.ui.assets import ISLAND_CHECK

        source = inspect.getsource(IslandManagement._wait_island_scene)
        self.assertIn('from module.ui.assets import ISLAND_CHECK', source)
        self.assertFalse(hasattr(island_assets, 'ISLAND_CHECK'))
        self.assertEqual(ISLAND_CHECK.name, 'ISLAND_CHECK')


class TestIslandSceneReady(unittest.TestCase):
    def test_loaded_proxy_is_not_scene_ready(self):
        self.assertFalse(heartbeat_island_scene_ready(None))
        self.assertFalse(heartbeat_island_scene_ready({'loaded': True}))
        self.assertFalse(heartbeat_island_scene_ready({'loaded': True, 'sceneReady': False}))
        self.assertTrue(heartbeat_island_scene_ready({'loaded': True, 'sceneReady': True}))


class TestMegaDone(unittest.TestCase):
    def test_requires_done_phase_and_seq(self):
        self.assertFalse(mega_is_done({'running': True, 'phase': 'workers', 'seq': 4}, 4))
        self.assertFalse(mega_is_done({'running': False, 'phase': 'missions', 'seq': 4}, 4))
        self.assertFalse(mega_is_done({'running': False, 'phase': 'done', 'seq': 3}, 4))
        self.assertTrue(mega_is_done({'running': False, 'phase': 'done', 'seq': 4}, 4))
        self.assertTrue(mega_is_done({'running': False, 'phase': 'done', 'seq': '4'}, 4))


class TestIslandManageAck(unittest.TestCase):
    def test_island_manage_returns_started_and_seq(self):
        from module.alas_bridge import actions

        class FakeRpc:
            def __init__(self, gs):
                pass

            def send(self, name, args=None, timeout=8.0):
                self.last = (name, timeout)
                return {
                    'id': '1',
                    'ok': True,
                    'name': name,
                    'result': {'started': True, 'seq': 7},
                }

        class FakeGS:
            @staticmethod
            def from_config(config):
                return object()

        rpc = FakeRpc(None)
        orig_rpc = actions.BridgeRpc
        orig_gs = actions.GameState
        actions.BridgeRpc = lambda gs: rpc
        actions.GameState = FakeGS
        try:
            result = actions.island_manage(object())
        finally:
            actions.BridgeRpc = orig_rpc
            actions.GameState = orig_gs
        self.assertEqual(result, {'started': True, 'seq': 7})
        self.assertEqual(rpc.last[0], 'island_manage')

    def test_heartbeat_reads_island_mega(self):
        from module.alas_bridge import actions

        class FakeGS:
            def __init__(self):
                pass

            @staticmethod
            def from_config(config):
                return FakeGS()

            def read(self, max_age=8.0):
                return {
                    'alive': True,
                    'island': {
                        'loaded': True,
                        'mega': {
                            'running': False,
                            'phase': 'done',
                            'seq': 7,
                            'nextIdleAt': 1700000000,
                        },
                    },
                }

        orig_gs = actions.GameState
        actions.GameState = FakeGS
        try:
            mega = actions.island_mega_from_heartbeat(object())
        finally:
            actions.GameState = orig_gs
        self.assertEqual(mega['phase'], 'done')
        self.assertEqual(mega['nextIdleAt'], 1700000000)
        self.assertTrue(mega_is_done(mega, 7))


if __name__ == '__main__':
    unittest.main()
