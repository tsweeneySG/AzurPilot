#!/usr/bin/env python3
"""
Probe the Sweeney ALAS file bridge (state.json / cmd.json / ack.json).

Examples:
  python tools/alas_bridge_probe.py --list
  python tools/alas_bridge_probe.py --config 6_margaret
  python tools/alas_bridge_probe.py -i 6 get_resources
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from module.alas_bridge.game_state import (  # noqa: E402
    DEFAULT_SWMOD_ROOT,
    GameState,
    page_name_from_state,
)
from module.alas_bridge.instances import (  # noqa: E402
    instance_for_config,
    instance_for_serial,
    load_instances,
)
from module.alas_bridge.rpc import BridgeRpc  # noqa: E402


def _print_instances():
    print('index  config        commander        serial')
    for row in load_instances():
        print(
            f"{row.get('index'):<6} {row.get('config'):<13} {row.get('name'):<16} {row.get('serial')}"
        )


def main():
    parser = argparse.ArgumentParser(description='Probe Sweeney ALAS bridge files')
    parser.add_argument('--root', default=str(DEFAULT_SWMOD_ROOT), help='SweeneyMod shared-folder root')
    parser.add_argument('--account', default='', help='Optional {playerId}_{name} folder override')
    parser.add_argument('--serial', default='', help='Emulator serial (same as Alas.Emulator.Serial)')
    parser.add_argument('--config', default='', help='ALAS config name, e.g. 6_margaret')
    parser.add_argument('-i', '--index', type=int, default=0, help='Emulator index 1-6')
    parser.add_argument('--list', action='store_true', help='Print serial to commander map and exit')
    parser.add_argument('--stale', type=float, default=8.0, help='Max state.json age in seconds')
    parser.add_argument('verb', nargs='?', help='Optional RPC verb')
    parser.add_argument('scene', nargs='?', help='Optional verb argument')
    args = parser.parse_args()

    if args.list:
        _print_instances()
        return 0

    serial = args.serial.strip()
    commander = ''
    account = args.account.strip()
    row = None
    if args.index:
        for item in load_instances():
            if int(item.get('index') or 0) == args.index:
                row = item
                break
        if row is None:
            print(f'unknown index {args.index}')
            _print_instances()
            return 2
    elif args.config:
        row = instance_for_config(args.config)
        if row is None:
            print(f'unknown config {args.config}')
            _print_instances()
            return 2
    elif serial:
        row = instance_for_serial(serial)

    if row:
        serial = str(row.get('serial') or serial)
        commander = str(row.get('name') or '')

    if not account and not commander and not serial:
        print('Select an instance (--index / --config / --serial).')
        _print_instances()
        return 2

    gs = GameState(root=Path(args.root), account=account, commander=commander, serial=serial)
    folder = gs.resolve_dir()
    print(f'root      = {gs.root}')
    print(f'serial    = {gs.serial or serial or "-"}')
    print(f'commander = {gs.commander or commander or "-"}')
    print(f'account   = {folder}')
    state = gs.read(max_age=args.stale)
    if state is None:
        print('state     = <missing or stale>')
        path = gs.state_path()
        if path is not None and path.is_file():
            print(f'state_path = {path}')
    else:
        print(f'scene     = {state.get("scene_key")} ({state.get("scene")})')
        print(f'page      = {page_name_from_state(state)}')
        print(f'player    = {state.get("player")}')
        print(f'battle    = {state.get("battle")}')
        print(f'os        = {state.get("os")}')

    if not args.verb:
        return 0 if state is not None else 1

    extra = {}
    if args.verb == 'goto_scene' and args.scene:
        extra = {'scene': args.scene}
    elif args.verb == 'harvest_res':
        extra = {'kind': args.scene or 'oil'}
    elif args.verb == 'echo':
        extra = {'ping': 1}
    ack = BridgeRpc(gs).send(args.verb, extra, timeout=12.0)
    print('ack =')
    print(json.dumps(ack, indent=2, ensure_ascii=False))
    return 0 if ack.get('ok') else 3


if __name__ == '__main__':
    raise SystemExit(main())
