"""多实例共用配置编辑器。

`All` 侧栏读取各实例的共识值；不一致时显示混合占位。序列号、包名、
SweeneyBridge 账号等身份字段锁定，避免一次保存改写全部模拟器身份。
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from module.config.deep import deep_get
from module.config.utils import alas_instance
from module.submodule.utils import MOD_DICT, get_config_mod

ALL_ASIDE = "All"
MIXED_SENTINEL = "__ALAS_MIXED__"

IDENTITY_PATHS = frozenset({
    "Alas.Emulator.Serial",
    "Alas.Emulator.PackageName",
    "Alas.Emulator.ServerName",
    "Alas.EmulatorInfo.name",
    "Alas.EmulatorInfo.path",
    "Alas.Optimization.SweeneyBridgeAccount",
    "Alas.DropRecord.AzurStatsID",
})

READONLY_ALL_TYPES = frozenset({
    "storage",
    "lock",
    "state",
    "stored",
})


def is_all_mode(name: Optional[str]) -> bool:
    return name == ALL_ASIDE


def instance_mod(name: str) -> str:
    """文件名带 `.maa` / `.fpy` 时直接认定子模块，否则查模块登记。"""
    _stem, ext = os.path.splitext(name)
    mod = ext[1:]
    if mod in MOD_DICT:
        return mod
    return get_config_mod(name)


def common_editor_instances(names: Optional[Sequence[str]] = None) -> List[str]:
    """普通 AzurPilot 实例名（排除 MAA/FPY、template 与 All）。

    Args:
        names: 候选实例名。缺省时扫描当前工作目录下的 config/。
    """
    chosen = alas_instance() if names is None else names
    return [name for name in chosen if name not in (ALL_ASIDE, "template") and instance_mod(name) == "alas"]


def is_identity_path(path: str) -> bool:
    return path in IDENTITY_PATHS


def is_locked_in_all(path: str, widget_type: Optional[str] = None) -> bool:
    if path in IDENTITY_PATHS:
        return True
    if widget_type in READONLY_ALL_TYPES:
        return True
    return False


def consensus(
        configs: Sequence[dict],
        path: Any,
        default: Any = None,
) -> Tuple[Any, bool]:
    """
    Args:
        configs: 各实例配置字典。
        path: deep_get 键（列表或点分路径）。
        default: 缺键时的回退值。

    Returns:
        (value, mixed)
        一致时返回该值；混合时返回第一份配置的值并标记 mixed。
    """
    if not configs:
        return default, False
    values = [deep_get(cfg, path, default) for cfg in configs]
    first = values[0]
    for v in values[1:]:
        if v != first:
            return first, True
    return first, False


def displayed_pin_value(widget_type: str, value: Any, mixed: bool) -> Any:
    """实际显示在控件上的 pin 值，供基线跳过未改动字段。"""
    if mixed:
        if widget_type == "select":
            return MIXED_SENTINEL
        if widget_type == "checkbox":
            return []
        return ""
    if widget_type == "checkbox":
        return [True] if value else []
    if isinstance(value, datetime):
        return str(value)
    return value


def read_common_configs(config_updater) -> Tuple[List[str], List[dict]]:
    names = common_editor_instances()
    configs = [config_updater.read_file(name) for name in names]
    return names, configs
