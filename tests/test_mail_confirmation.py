"""邮件批量领取确认窗。

2026-11 客户端弹出 MailConfirmationWindow，白字 Confirm 对不上 POPUP_CONFIRM_WHITE。
用卡住时的国际服截图确认新按钮能匹配，旧确认钮不能。
"""
import os
import unittest

import numpy as np
from PIL import Image

import module.config.server as server

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'mail', 'en_confirmation.png')


class TestMailConfirmation(unittest.TestCase):
    def setUp(self):
        self._server = server.server
        server.server = 'en'
        import importlib
        import module.freebies.assets as freebies_assets
        import module.ui_white.assets as white_assets
        self.freebies = importlib.reload(freebies_assets)
        self.white = importlib.reload(white_assets)
        self.image = np.array(Image.open(FIXTURE).convert('RGB'))

    def tearDown(self):
        server.server = self._server

    def test_new_confirm_matches_and_old_confirm_does_not(self):
        button = self.freebies.MAIL_CONFIRMATION_CONFIRM
        self.assertTrue(button.match(self.image, offset=(20, 20), similarity=0.85))
        old = self.white.POPUP_CONFIRM_WHITE
        self.assertFalse(old.match(self.image, offset=(30, 30), similarity=0.85))

    def test_confirm_does_not_match_after_the_button_is_covered(self):
        button = self.freebies.MAIL_CONFIRMATION_CONFIRM
        covered = self.image.copy()
        x1, y1, x2, y2 = button.area
        covered[y1:y2, x1:x2] = 0
        self.assertFalse(button.match(covered, offset=(20, 20), similarity=0.85))
