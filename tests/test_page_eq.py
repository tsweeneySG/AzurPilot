import unittest

from module.ui.page import Page, page_munitions, page_shop


class TestPageEq(unittest.TestCase):
    def test_none_in_page_tuple_does_not_raise(self):
        self.assertFalse(None in (page_munitions, page_shop))
        self.assertNotEqual(page_munitions, None)
        self.assertEqual(page_munitions, page_munitions)
        self.assertIsInstance(page_munitions, Page)
