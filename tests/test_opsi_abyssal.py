import unittest
from contextlib import nullcontext
from unittest.mock import Mock

from module.config.config import TaskEnd
from module.os.tasks.abyssal import OpsiAbyssal


class TestAbyssalFleetExhausted(unittest.TestCase):
    def _make(self, smart=False):
        inst = OpsiAbyssal.__new__(OpsiAbyssal)
        inst.config = Mock()
        inst.config.task_stop.side_effect = TaskEnd
        inst.is_running_smart_scheduling_task = Mock(return_value=smart)
        inst.map_exit = Mock()
        inst.handle_fleet_repair_by_config = Mock()
        return inst

    def test_delays_and_stops_standalone_task(self):
        inst = self._make(smart=False)

        with self.assertRaises(TaskEnd):
            inst._handle_abyssal_fleet_exhausted()

        inst.map_exit.assert_called_once_with()
        inst.handle_fleet_repair_by_config.assert_called_once_with(revert=False)
        inst.config.task_delay.assert_called_once_with(success=False)

    def test_skips_stop_during_smart_scheduling(self):
        inst = self._make(smart=True)

        inst._handle_abyssal_fleet_exhausted()

        self.assertEqual(inst._smart_scheduling_no_content_task, 'OpsiAbyssal')
        inst.config.task_stop.assert_not_called()
        inst.config.task_delay.assert_not_called()

    def test_clear_abyssal_defers_instead_of_human_takeover(self):
        inst = self._make(smart=False)
        inst.config.OpsiGeneral_UseLogger = True
        inst.config.temporary.return_value = nullcontext()
        inst.cl1_ap_preserve = Mock()
        inst._has_call_submarine = Mock(return_value=False)
        inst.storage_get_next_item = Mock(return_value=True)
        inst.zone_init = Mock()
        inst.run_abyssal = Mock(return_value=False)
        inst._handle_abyssal_fleet_exhausted = Mock()

        result = inst.clear_abyssal()

        inst._handle_abyssal_fleet_exhausted.assert_called_once_with()
        inst.handle_fleet_repair_by_config.assert_not_called()
        self.assertFalse(result)
