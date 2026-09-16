import unittest
from unittest.mock import Mock

from module.handler.login import LOGIN_WAIT_TIMEOUT_DEFAULT, LoginHandler


class TestLoginWaitTimeout(unittest.TestCase):
    def _timeout(self, value):
        handler = LoginHandler.__new__(LoginHandler)
        handler.config = Mock()
        handler.config.data = {'Restart': {'Restart': {'LoginWaitTimeout': value}}}
        return handler._login_wait_timeout()

    def test_legacy_default_30_is_floored(self):
        self.assertEqual(self._timeout(30), LOGIN_WAIT_TIMEOUT_DEFAULT)

    def test_missing_uses_default(self):
        handler = LoginHandler.__new__(LoginHandler)
        handler.config = Mock()
        handler.config.data = {}
        self.assertEqual(handler._login_wait_timeout(), LOGIN_WAIT_TIMEOUT_DEFAULT)

    def test_explicit_higher_value_is_honored(self):
        self.assertEqual(self._timeout(300), 300.0)

    def test_invalid_falls_back(self):
        self.assertEqual(self._timeout('nope'), LOGIN_WAIT_TIMEOUT_DEFAULT)
