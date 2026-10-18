"""EventA~D LastStage 须对照桥接今日击败次数，不能把空断点当成已打完。"""

import unittest

from module.event.campaign_abcd import event_daily_letter_cleared, event_daily_today_defeat


class EventDailyRemainTests(unittest.TestCase):
    def test_today_defeat_reads_named_row(self):
        remains = {'event_daily': {'a3': {'today_defeat': 1, 'chapter_id': 1830003}}}
        self.assertEqual(event_daily_today_defeat(remains, 'A3'), 1)
        self.assertEqual(event_daily_today_defeat(remains, 'a1'), None)

    def test_letter_cleared_any_stage(self):
        remains = {
            'event_daily': {
                'a1': {'today_defeat': 0},
                'a2': {'today_defeat': 0},
                'a3': {'today_defeat': 1},
            }
        }
        self.assertTrue(event_daily_letter_cleared(remains, ['a1', 'a2', 'a3']))

    def test_letter_not_cleared(self):
        remains = {
            'event_daily': {
                'a1': {'today_defeat': 0},
                'a2': {'today_defeat': 0},
                'a3': {'today_defeat': 0},
            }
        }
        self.assertFalse(event_daily_letter_cleared(remains, ['a1', 'a2', 'a3']))

    def test_unknown_without_snapshot(self):
        self.assertIsNone(event_daily_letter_cleared(None, ['a1', 'a2', 'a3']))
        self.assertIsNone(event_daily_letter_cleared({'event_daily': {}}, ['a1']))
        self.assertIsNone(event_daily_today_defeat({'event_daily': {}}, 'a3'))
