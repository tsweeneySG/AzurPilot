"""Sweeney get_shop_items 快照能否代替截图购买。

功勋商品的 buyCount 为 0 表示本周期还没买（CommonCommodity TYPE_MILITARY
的 canPurchase 即 buyCount == 0）。旧快照把 buyCount 写进 stock，再把
stock == 0 当成售罄，于是整间功勋商店被跳过，魔方永远不会点到。

核心月度（心智单元 / 心智芯片）在商店里是 quota 页。旧快照没有 quota
分支，kind=core 会落到功勋商店上。快照说「空」时，月度页根本没被看过。

这两类商店的截图购买仍是最终依据。其它商店保持原有的空/售罄跳过。
"""

# 漏买会跨日甚至跨月，不能用不可靠快照提前结束。
VISUAL_REQUIRED_KINDS = frozenset({'merit', 'core', 'quota'})


def bridge_shop_snapshot_looks_empty(snap) -> bool:
    """旧跳过条件：快照没有可购行。

    stock 缺省或为 0，且 can_purchase 不是 True，都算不可购。
    空列表同样视为空。非 dict / 没有 items 列表则不算空（调用方应继续购买）。

    Args:
        snap: get_shop_items 的 result，或 None。

    Returns:
        bool: 按旧规则是否「空/售罄」。
    """
    if not isinstance(snap, dict):
        return False
    items = snap.get('items')
    if not isinstance(items, list):
        return False
    for row in items:
        if not isinstance(row, dict):
            continue
        if row.get('can_purchase') is False:
            continue
        try:
            stock = int(row.get('stock') or 0)
        except (TypeError, ValueError):
            return False
        if stock != 0:
            return False
    return True


def bridge_shop_snapshot_skips_buy(kind, snap) -> bool:
    """快照是否允许跳过截图购买。

    Args:
        kind (str): 商店种类，如 merit / core / guild。
        snap: get_shop_items 的 result。

    Returns:
        bool: True 表示可以跳过截图购买。
    """
    if kind in VISUAL_REQUIRED_KINDS:
        return False
    return bridge_shop_snapshot_looks_empty(snap)
