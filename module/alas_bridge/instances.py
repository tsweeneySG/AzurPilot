"""Map ALAS emulator serials to commander names (same table as Open-EmulatorLogcat)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

INSTANCES_FILE = Path(__file__).with_name('emulator_instances.json')


@lru_cache(maxsize=1)
def load_instances() -> list[dict]:
    if not INSTANCES_FILE.is_file():
        return []
    data = json.loads(INSTANCES_FILE.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        return []
    return data


def instance_for_serial(serial: str) -> Optional[dict]:
    serial = (serial or '').strip()
    if not serial:
        return None
    for row in load_instances():
        if str(row.get('serial') or '').strip() == serial:
            return row
    return None


def instance_for_config(config_name: str) -> Optional[dict]:
    name = (config_name or '').strip()
    if name.endswith('.json'):
        name = name[:-5]
    if not name:
        return None
    for row in load_instances():
        if str(row.get('config') or '') == name:
            return row
        if str(row.get('index')) == name:
            return row
    return None


def commander_for_serial(serial: str) -> str:
    row = instance_for_serial(serial)
    return str(row['name']) if row and row.get('name') else ''
