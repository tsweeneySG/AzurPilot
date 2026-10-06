import unittest

from module.shop.bridge_snapshot import (
    bridge_shop_snapshot_looks_empty,
    bridge_shop_snapshot_skips_buy,
)


class TestShopBridgeSnapshot(unittest.TestCase):
    def test_merit_unbought_is_not_a_skip(self):
        # buyCount 0 is "not bought yet" on the merit shop, not sold out.
        snap = {
            'kind': 'merit',
            'items': [
                {'id': 1, 'stock': 0},
                {'id': 2, 'stock': 0, 'can_purchase': True},
            ],
        }
        self.assertTrue(bridge_shop_snapshot_looks_empty(snap))
        self.assertFalse(bridge_shop_snapshot_skips_buy('merit', snap))

    def test_core_snapshot_never_skips(self):
        # Old bridge answers kind=core with the merit shop, often all stock 0.
        snap = {'kind': 'merit', 'items': [{'id': 1, 'stock': 0}]}
        self.assertFalse(bridge_shop_snapshot_skips_buy('core', snap))
        self.assertFalse(bridge_shop_snapshot_skips_buy('quota', {'kind': 'quota', 'items': []}))

    def test_guild_sold_out_still_skips(self):
        snap = {'kind': 'guild', 'items': [{'id': 1, 'stock': 0}, {'id': 2, 'stock': 0}]}
        self.assertTrue(bridge_shop_snapshot_skips_buy('guild', snap))

    def test_guild_with_stock_does_not_skip(self):
        snap = {'kind': 'guild', 'items': [{'id': 1, 'stock': 0}, {'id': 2, 'stock': 4}]}
        self.assertFalse(bridge_shop_snapshot_looks_empty(snap))
        self.assertFalse(bridge_shop_snapshot_skips_buy('guild', snap))

    def test_missing_snapshot_does_not_skip(self):
        self.assertFalse(bridge_shop_snapshot_skips_buy('guild', None))
        self.assertFalse(bridge_shop_snapshot_skips_buy('medal', {'error': 'no shop'}))
