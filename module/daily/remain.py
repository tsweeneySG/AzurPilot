"""每日任务剩余次数：UI 索引与桥接 expedition_daily_template id 对齐。"""

# daily_current -> pg.expedition_daily_template id
# Matches get_daily_stage_and_fleet ordering (JP carousel; CN/EN share the same maps here).
_DAILY_TEMPLATE_ID_NORMAL = {
    1: 601,  # Tactical Training
    2: 501,  # Supply Line Disruption
    3: 701,  # Module Development
    4: 101,  # Unavailable / empty slot
    5: 201,  # Escort Mission
    6: 301,  # Advance Mission
    7: 401,  # Fierce Assault
}
_DAILY_TEMPLATE_ID_EMERGENCY = {
    1: 801,  # Emergency Module Development
    2: 201,  # Escort Mission
    3: 301,  # Advance Mission
    4: 401,  # Fierce Assault
    5: 601,  # Tactical Training
    6: 501,  # Supply Line Disruption
    7: 701,  # Module Development
}


def daily_template_id(daily_current, emergency_module_development=False):
    """Map UI carousel index to expedition_daily_template id.

    Args:
        daily_current (int): 1-7 carousel index used by Daily.
        emergency_module_development (bool): Whether the emergency module slot is present.

    Returns:
        int or None: Template id, or None if index is unknown.
    """
    table = _DAILY_TEMPLATE_ID_EMERGENCY if emergency_module_development else _DAILY_TEMPLATE_ID_NORMAL
    return table.get(int(daily_current))


def bridge_daily_remain_for_id(daily_rows, template_id):
    """Pick remain for one daily template from bridge get_task_remains().daily.

    Args:
        daily_rows (list): Rows like {id, used, remain, limit}.
        template_id (int): expedition_daily_template id.

    Returns:
        int or None: Remain count when the matching row exists, else None.
    """
    if not isinstance(daily_rows, list) or template_id is None:
        return None
    want = int(template_id)
    for row in daily_rows:
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get('id')) != want:
                continue
        except (TypeError, ValueError):
            continue
        try:
            return max(0, int(row.get('remain') or 0))
        except (TypeError, ValueError):
            return None
    return None
