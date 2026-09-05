"""Apply ChapterProxy cell snapshots onto ALAS CampaignMap grids (read-only assist)."""
from __future__ import annotations

from typing import Optional

# Mirrors ChapterConst attachment ids used by the EN client.
ATTACH_BORN = 1
ATTACH_ELITE = 4
ATTACH_ENEMY = 6
ATTACH_TORPEDO_ENEMY = 7
ATTACH_BOSS = 8
CELL_FLAG_ACTIVE = 0
CELL_FLAG_DISABLED = 1
ENEMY_ATTACHMENTS = (ATTACH_ELITE, ATTACH_ENEMY, ATTACH_TORPEDO_ENEMY, ATTACH_BOSS)


def apply_chapter_map_cells(map_obj, cells, config=None) -> int:
    """
    Overlay enemy/boss/cleared flags from bridge cells onto map grids.

    Game cells use (row, col); ALAS locations are (x, y) == (col, row).

    Returns:
        int: number of grids updated.
    """
    if map_obj is None or not isinstance(cells, list):
        return 0
    updated = 0
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        row = cell.get('row')
        col = cell.get('col')
        if row is None or col is None:
            continue
        loc = (int(col), int(row))
        try:
            grid = map_obj[loc]
        except Exception:
            continue
        attachment = cell.get('attachment')
        flag = cell.get('flag')
        try:
            attachment = int(attachment) if attachment is not None else None
            flag = int(flag) if flag is not None else None
        except (TypeError, ValueError):
            continue
        if attachment == ATTACH_BOSS and flag != CELL_FLAG_DISABLED:
            grid.is_boss = True
            grid.is_enemy = True
            grid.enemy_genre = 'Boss'
            updated += 1
        elif attachment in ENEMY_ATTACHMENTS and flag != CELL_FLAG_DISABLED:
            grid.is_enemy = True
            if not grid.enemy_genre:
                grid.enemy_genre = 'Enemy'
            if attachment == ATTACH_ELITE and not grid.enemy_scale:
                grid.enemy_scale = 3
            updated += 1
        elif flag == CELL_FLAG_DISABLED and attachment in ENEMY_ATTACHMENTS:
            grid.is_enemy = False
            grid.is_boss = False
            grid.enemy_genre = None
            updated += 1
    return updated


def fetch_and_apply_chapter_map(map_obj, config) -> Optional[dict]:
    """RPC get_chapter_map and apply cells; returns payload or None."""
    try:
        from module.alas_bridge.actions import bridge_enabled, get_chapter_map
        if not bridge_enabled(config):
            return None
        payload = get_chapter_map(config)
    except Exception:
        return None
    if not isinstance(payload, dict) or not payload.get('active'):
        return payload
    apply_chapter_map_cells(map_obj, payload.get('cells') or [], config=config)
    return payload
