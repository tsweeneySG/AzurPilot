import logging
import unittest
from unittest.mock import Mock, patch

from alas import AzurLaneAutoScript
from module.exception import GameNotRunningError, GameStuckError, RequestHumanTakeover
from module.logger import error_context


class TestErrorContext(unittest.TestCase):
    def test_can_log_exception_summary_without_traceback(self):
        error = GameNotRunningError('Game not running')

        with patch('module.logger.logger.log') as log:
            error_context(
                title='游戏进程未运行',
                reason='任务执行前未检测到碧蓝航线游戏进程。',
                impact='当前任务跳过。',
                action='自动重启游戏。',
                exc=error,
                level=logging.WARNING,
                with_traceback=False,
            )

        self.assertFalse(log.call_args.kwargs['exc_info'])
        self.assertIn('异常：GameNotRunningError: Game not running', log.call_args.args[1])


class TestGameNotRunningErrorHandling(unittest.TestCase):
    def test_schedules_restart_without_requesting_traceback(self):
        script = AzurLaneAutoScript.__new__(AzurLaneAutoScript)
        script.config_name = 'test'
        script.__dict__['config'] = Mock()
        script.config.cross_get.return_value = False
        error = GameNotRunningError('Game not running')
        script.__dict__['commission'] = Mock(side_effect=error)

        with (
            patch('alas.logger.error_context') as error_context_mock,
            patch('alas.handle_notify'),
            patch('alas.notify_webui'),
        ):
            result = script.run('commission', skip_first_screenshot=True)

        self.assertEqual('recoverable', result)
        script.config.task_call.assert_called_once_with('Restart')
        error_context_mock.assert_called_once_with(
            title='游戏进程未运行',
            reason='任务执行前未检测到碧蓝航线游戏进程。',
            impact='当前任务跳过，调度器将自动安排 Restart 任务。',
            action='通常无需处理；若反复发生，请检查游戏包名、模拟器状态和登录流程。',
            exc=error,
            level=30,
            with_traceback=False,
        )


def _script_with_sensitive_config(strict_restart=False, sensitive=True):
    script = AzurLaneAutoScript.__new__(AzurLaneAutoScript)
    script.config_name = '2_brad'
    script.__dict__['config'] = Mock()
    script.config.Error_StrictRestart = strict_restart
    script.config.Error_OnePushConfig = 'provider: null'
    script.config.cross_get.return_value = sensitive
    return script


class TestSensitiveTaskExit(unittest.TestCase):
    def test_defers_when_strict_restart_is_off(self):
        script = _script_with_sensitive_config(strict_restart=False)

        with patch('alas.notify_webui') as notify:
            result = script._check_sensitive_exit(
                'opsi_abyssal', RequestHumanTakeover()
            )

        self.assertTrue(result)
        script.config.task_delay.assert_called_once_with(success=False)
        notify.assert_called_once()

    def test_halts_when_strict_restart_is_on(self):
        script = _script_with_sensitive_config(strict_restart=True)

        with (
            patch('alas.logger.error_context'),
            patch('alas.handle_notify'),
            patch('alas.notify_webui'),
            self.assertRaises(SystemExit) as cm,
        ):
            script._check_sensitive_exit('opsi_abyssal', RequestHumanTakeover())

        self.assertEqual(cm.exception.code, 1)
        script.config.task_delay.assert_not_called()

    def test_game_not_running_still_restarts_on_sensitive_task(self):
        script = _script_with_sensitive_config(strict_restart=True)
        error = GameNotRunningError('Game not running')

        self.assertFalse(script._check_sensitive_exit('opsi_abyssal', error))
        script.config.task_delay.assert_not_called()

    def test_request_human_takeover_does_not_halt_without_strict_restart(self):
        script = _script_with_sensitive_config(strict_restart=False)
        script.save_error_log = Mock()
        script._try_restart_emulator = Mock()
        script.__dict__['opsi_abyssal'] = Mock(side_effect=RequestHumanTakeover())

        with (
            patch('alas.logger.error_context'),
            patch('alas.handle_notify'),
            patch('alas.notify_webui'),
        ):
            result = script.run('opsi_abyssal', skip_first_screenshot=True)

        self.assertEqual('recoverable', result)
        script.config.task_delay.assert_called_once_with(success=False)
        script._try_restart_emulator.assert_not_called()
        script.config.task_call.assert_not_called()


def _script_for_restart_stuck(consecutive=0, threshold=3):
    script = AzurLaneAutoScript.__new__(AzurLaneAutoScript)
    script.config_name = 'test'
    script.__dict__['config'] = Mock()
    script.config.cross_get.return_value = False
    script.config.Error_GameStuckRestart = False
    script.config.Error_GameStuckThreshold = threshold
    script.config.Error_OnePushConfig = 'provider: null'
    script.consecutive_game_stuck = consecutive
    script.save_error_log = Mock()
    script._try_restart_emulator = Mock(return_value=True)
    script.__dict__['device'] = Mock()
    script.__dict__['restart'] = Mock(
        side_effect=GameStuckError('[设备-卡死] 截图未变化')
    )
    return script


class TestRestartLoginStuck(unittest.TestCase):
    def test_game_stuck_during_restart_does_not_relaunch_immediately(self):
        script = _script_for_restart_stuck()

        with (
            patch('alas.logger.error_context'),
            patch('alas.handle_notify'),
            patch('alas.notify_webui'),
        ):
            result = script.run('restart', skip_first_screenshot=True)

        self.assertEqual('recoverable', result)
        self.assertEqual(script.consecutive_game_stuck, 1)
        script.config.task_call.assert_not_called()
        script.config.task_delay.assert_called_once_with(minute=2)
        script._try_restart_emulator.assert_not_called()

    def test_repeated_restart_stuck_restarts_emulator(self):
        script = _script_for_restart_stuck(consecutive=2, threshold=3)

        with (
            patch('alas.logger.error_context'),
            patch('alas.handle_notify'),
            patch('alas.notify_webui'),
        ):
            result = script.run('restart', skip_first_screenshot=True)

        self.assertEqual('recoverable', result)
        script._try_restart_emulator.assert_called_once()
        script.config.task_call.assert_called_once_with('Restart')
        script.config.task_delay.assert_not_called()
