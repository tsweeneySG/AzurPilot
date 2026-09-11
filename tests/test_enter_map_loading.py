import unittest

from module.map.camera import Camera
from module.map.map_operation import MapOperation


class TestEnterMapCombatLoading(unittest.TestCase):
    def _op(self, auto_search, loading, executing):
        op = MapOperation.__new__(MapOperation)
        op.map_is_auto_search = auto_search
        op.is_combat_loading = lambda: loading
        op.is_combat_executing = lambda: executing
        return op

    def test_manual_map_loading_bar_does_not_finish_enter(self):
        op = self._op(auto_search=False, loading=True, executing=False)
        self.assertFalse(op._enter_map_combat_loading_means_entered())

    def test_auto_search_combat_loading_finishes_enter(self):
        op = self._op(auto_search=True, loading=True, executing=False)
        self.assertTrue(op._enter_map_combat_loading_means_entered())

    def test_manual_real_combat_finishes_enter(self):
        op = self._op(auto_search=False, loading=True, executing=True)
        self.assertTrue(op._enter_map_combat_loading_means_entered())

    def test_not_loading_does_not_finish_enter(self):
        op = self._op(auto_search=False, loading=False, executing=False)
        self.assertFalse(op._enter_map_combat_loading_means_entered())


class TestCameraWaitForMap(unittest.TestCase):
    def test_wait_while_combat_loading(self):
        cam = Camera.__new__(Camera)
        cam.is_combat_loading = lambda: True
        self.assertTrue(cam._camera_should_wait_for_map())

    def test_do_not_wait_when_not_loading(self):
        cam = Camera.__new__(Camera)
        cam.is_combat_loading = lambda: False
        self.assertFalse(cam._camera_should_wait_for_map())
