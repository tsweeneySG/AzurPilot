#!/usr/bin/env python3
"""
Parse an ALAS log and sample host RAM/CPU for the farm-loop benchmark.

Examples:
  python tools/farm_loop_bench.py --log log/2026-08-29_1_67.txt
  python tools/farm_loop_bench.py --host-seconds 20
  python tools/farm_loop_bench.py --host-seconds 15 --host-out log/host_sample.csv
  python tools/farm_loop_bench.py --host-watch --host-seconds 15
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PATTERNS = {
    'screenshot_count': re.compile(r'\[ScreenshotCount\]\s+(\d+)'),
    'ocr_count': re.compile(r'\[OcrCount\]\s+(\d+)'),
    'bridge_page': re.compile(r'UI page from Sweeney bridge'),
    'bridge_miss': re.compile(r'Sweeney bridge miss'),
    'combat_idle': re.compile(r'Combat idle skip \(Sweeney BATTLE_FIGHT'),
    'combat_idle_peek': re.compile(r'Combat idle skip peek'),
    'combat_idle_cap': re.compile(r'Combat idle skip cap'),
    'ocr_oil': re.compile(r'\bOCR_OIL\b'),
    'unknown_ui': re.compile(r'Unknown ui page'),
    'battle_ui': re.compile(r'\[BattleUI\]'),
    'adb_nc': re.compile(r'\[nc command\]'),
    'droidcast': re.compile(r'DroidCast', re.I),
    'nemu_ipc': re.compile(r'nemu_ipc', re.I),
}

ALAS_CMD = re.compile(
    r'azurlaneautoscript|alas\.py|\bgui\.py\b|deploy/alas|deploy\\alas',
    re.I,
)
BLUESTACKS_NAMES = {
    'hd-player', 'hd-agent', 'hd-logrotatorhelper',
    'hd-multiinstancemanager', 'bstksvc', 'bluestacks',
}
MUMU_PREFIXES = ('mumu', 'nemu')


def parse_log(text: str) -> dict:
    out = {
        'screenshot_count_last': None,
        'ocr_count_last': None,
        'bridge_page': 0,
        'bridge_miss': 0,
        'combat_idle': 0,
        'combat_idle_peek': 0,
        'combat_idle_cap': 0,
        'ocr_oil': 0,
        'unknown_ui': 0,
        'battle_ui': 0,
        'adb_nc': 0,
        'droidcast': 0,
        'nemu_ipc': 0,
        'lines': text.count('\n') + (1 if text and not text.endswith('\n') else 0),
    }
    last_shot = None
    last_ocr = None
    counts = Counter()
    for line in text.splitlines():
        m = PATTERNS['screenshot_count'].search(line)
        if m:
            last_shot = int(m.group(1))
        m = PATTERNS['ocr_count'].search(line)
        if m:
            last_ocr = int(m.group(1))
        for key in (
            'bridge_page', 'bridge_miss', 'combat_idle', 'combat_idle_peek',
            'combat_idle_cap', 'ocr_oil', 'unknown_ui', 'battle_ui',
            'adb_nc', 'droidcast', 'nemu_ipc',
        ):
            if PATTERNS[key].search(line):
                counts[key] += 1
    out['screenshot_count_last'] = last_shot
    out['ocr_count_last'] = last_ocr
    for key, n in counts.items():
        out[key] = n
    return out


def print_report(label: str, stats: dict):
    print(f'=== {label} ===')
    print(f"  lines                {stats['lines']}")
    print(f"  ScreenshotCount last {stats['screenshot_count_last']}")
    print(f"  OcrCount last        {stats['ocr_count_last']}")
    print(f"  bridge page hits     {stats['bridge_page']}")
    print(f"  bridge miss          {stats['bridge_miss']}")
    print(f"  combat idle skip     {stats['combat_idle']}")
    print(f"  combat idle peek     {stats.get('combat_idle_peek', 0)}")
    print(f"  combat idle cap      {stats['combat_idle_cap']}")
    print(f"  OCR_OIL              {stats['ocr_oil']}")
    print(f"  Unknown ui page      {stats['unknown_ui']}")
    print(f"  BattleUI             {stats['battle_ui']}")
    method = 'unknown'
    if stats.get('nemu_ipc'):
        method = 'C nemu_ipc'
    elif stats.get('droidcast'):
        method = 'B DroidCast'
    elif stats.get('adb_nc'):
        method = 'A ADB_nc'
    if stats['combat_idle']:
        method += '+D idle skip'
    print(f"  inferred matrix      {method}")
    print('Matrix: A=BS ADB_nc  B=BS DroidCast  C=MuMu nemu_ipc  D=+combat idle skip')
    print('See docs/emulator-mumu-migration.md')


def _bare_name(name: str) -> str:
    return (name or '').lower().removesuffix('.exe')


def classify_process(name: str, command: str | None = None, image_path: str | None = None) -> str:
    """Group a Windows process for the host RAM/CPU table."""
    n = _bare_name(name)
    blob = ' '.join(x for x in (command, image_path) if x)
    if n in ('python', 'pythonw') or n.startswith('python'):
        if blob and ALAS_CMD.search(blob):
            return 'alas_python'
        return 'other_python'
    if n in ('alas', 'electron') or (blob and ALAS_CMD.search(blob)):
        return 'alas_gui'
    if n in BLUESTACKS_NAMES or n.startswith('hd-'):
        return 'HD-Player' if n == 'hd-player' else 'bluestacks_other'
    if n.startswith(MUMU_PREFIXES):
        if n == 'mumunxdevice':
            return 'MuMuNxDevice'
        if n in ('mumunxmain', 'mumuplayer'):
            return 'MuMuNxMain'
        return 'mumu_other'
    return ''


def _ps_json(script: str, timeout: int = 60):
    cmd = [
        'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-Command', script,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    text = (proc.stdout or '').strip()
    if proc.returncode != 0 and not text:
        err = (proc.stderr or '').strip() or f'powershell exit {proc.returncode}'
        raise RuntimeError(err)
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict):
        return [data]
    return data or []


def snapshot_processes() -> list[dict]:
    # Get-Process CPU/WorkingSet/Path is live; Win32_Process CommandLine is optional.
    script = r'''
$procs = @(Get-Process | Where-Object {
  $_.ProcessName -match '^(python|pythonw|HD-Player|HD-Agent|HD-MultiInstanceManager|BstkSVC|MuMu|Nemu|alas|electron)'
})
$cmds = @{}
Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^(python|pythonw|alas|electron)'
} | ForEach-Object { $cmds["$($_.ProcessId)"] = $_.CommandLine }
$procs | ForEach-Object {
  $id = "$($_.Id)"
  [PSCustomObject]@{
    ProcessId = $_.Id
    Name = $_.ProcessName
    Path = $_.Path
    WorkingSetSize = $_.WorkingSet64
    CpuSeconds = if ($null -eq $_.CPU) { 0 } else { [double]$_.CPU }
    CommandLine = $cmds[$id]
  }
} | ConvertTo-Json -Compress -Depth 3
'''
    rows = []
    for item in _ps_json(script):
        name = str(item.get('Name') or '')
        command = item.get('CommandLine') or ''
        image_path = item.get('Path') or ''
        group = classify_process(name, command, image_path)
        if not group:
            continue
        rows.append({
            'pid': int(item.get('ProcessId') or 0),
            'name': name,
            'group': group,
            'ws_bytes': int(item.get('WorkingSetSize') or 0),
            'cpu_seconds': float(item.get('CpuSeconds') or 0),
            'command': str(command or image_path).replace('\n', ' ').strip(),
        })
    return rows


def _cpu_metrics(before: dict, after: dict, elapsed: float, ncpu: int) -> tuple[float, float]:
    delta_s = max(0.0, after['cpu_seconds'] - before['cpu_seconds'])
    cores = delta_s / elapsed if elapsed > 0 else 0.0
    host_pct = (cores / ncpu) * 100.0 if ncpu else 0.0
    return cores, host_pct


def sample_host_processes(seconds: float) -> dict:
    elapsed_target = max(1.0, float(seconds))
    ncpu = os.cpu_count() or 1
    t0 = time.perf_counter()
    first = {row['pid']: row for row in snapshot_processes()}
    time.sleep(elapsed_target)
    elapsed = time.perf_counter() - t0
    second = snapshot_processes()

    rows = []
    for row in second:
        prev = first.get(row['pid'])
        if prev is None:
            cores, host_pct = 0.0, 0.0
        else:
            cores, host_pct = _cpu_metrics(prev, row, elapsed, ncpu)
        rows.append({
            'pid': row['pid'],
            'name': row['name'],
            'group': row['group'],
            'ws_mb': row['ws_bytes'] / (1024 * 1024),
            'cpu_cores': cores,
            'cpu_pct_host': host_pct,
            'command': row['command'][:180],
        })
    rows.sort(key=lambda r: (r['group'], -r['ws_mb'], r['pid']))
    return {
        'elapsed': elapsed,
        'ncpu': ncpu,
        'rows': rows,
    }


def summarize_groups(rows: list[dict]) -> list[dict]:
    groups = defaultdict(lambda: {'n': 0, 'ws_mb': 0.0, 'cpu_pct_host': 0.0, 'cpu_cores': 0.0})
    for row in rows:
        g = groups[row['group']]
        g['n'] += 1
        g['ws_mb'] += row['ws_mb']
        g['cpu_pct_host'] += row['cpu_pct_host']
        g['cpu_cores'] += row['cpu_cores']
    order = [
        'alas_python', 'alas_gui', 'other_python',
        'HD-Player', 'bluestacks_other',
        'MuMuNxDevice', 'MuMuNxMain', 'mumu_other',
    ]
    out = []
    seen = set()
    for name in order:
        if name in groups:
            seen.add(name)
            out.append({'group': name, **groups[name]})
    for name, g in groups.items():
        if name not in seen:
            out.append({'group': name, **g})
    return out


def print_host_process_sample(sample: dict):
    rows = sample['rows']
    elapsed = sample['elapsed']
    ncpu = sample['ncpu']
    print(f'=== host process sample ({elapsed:.1f}s, {ncpu} logical CPUs) ===')
    print('CPU% is Task Manager style (share of all logical CPUs). cores is 1.00 = one full core.')
    print('MuMuNxDevice is the Android VM (HD-Player analogue); MuMuNxMain is the UI.')
    print(f"{'group':<20} {'n':>3} {'WS_MB':>10} {'CPU%':>8} {'cores':>7}")
    groups = summarize_groups(rows)
    for g in groups:
        print(
            f"{g['group']:<20} {g['n']:>3} {g['ws_mb']:10.1f} "
            f"{g['cpu_pct_host']:8.1f} {g['cpu_cores']:7.2f}"
        )
    by_name = {g['group']: g for g in groups}

    def _sum(*names):
        n = ws = cpu = cores = 0
        for name in names:
            g = by_name.get(name)
            if not g:
                continue
            n += g['n']
            ws += g['ws_mb']
            cpu += g['cpu_pct_host']
            cores += g['cpu_cores']
        return n, ws, cpu, cores

    print(f"{'PACK':<20} {'n':>3} {'WS_MB':>10} {'CPU%':>8} {'cores':>7}")
    for label, names in (
        ('ALAS (py+gui)', ('alas_python', 'alas_gui')),
        ('BlueStacks', ('HD-Player', 'bluestacks_other')),
        ('MuMu', ('MuMuNxDevice', 'MuMuNxMain', 'mumu_other')),
    ):
        n, ws, cpu, cores = _sum(*names)
        print(f"{label:<20} {n:>3} {ws:10.1f} {cpu:8.1f} {cores:7.2f}")
    print(f"{'pid':<8} {'name':<22} {'group':<18} {'WS_MB':>8} {'CPU%':>7} {'cores':>6}  command")
    for row in rows:
        print(
            f"{row['pid']:<8} {row['name'][:22]:<22} {row['group']:<18} "
            f"{row['ws_mb']:8.1f} {row['cpu_pct_host']:7.1f} {row['cpu_cores']:6.2f}  "
            f"{row['command']}"
        )


def write_host_csv(path: Path, sample: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.is_file()
    with path.open('a', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            'time', 'elapsed', 'ncpu', 'group', 'name', 'pid',
            'ws_mb', 'cpu_pct_host', 'cpu_cores', 'command',
        ])
        if new_file:
            writer.writeheader()
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        for row in sample['rows']:
            writer.writerow({
                'time': stamp,
                'elapsed': f"{sample['elapsed']:.2f}",
                'ncpu': sample['ncpu'],
                'group': row['group'],
                'name': row['name'],
                'pid': row['pid'],
                'ws_mb': f"{row['ws_mb']:.1f}",
                'cpu_pct_host': f"{row['cpu_pct_host']:.2f}",
                'cpu_cores': f"{row['cpu_cores']:.3f}",
                'command': row['command'],
            })
    print(f'wrote {path}')


def typeperf_machine(seconds: int = 2):
    print(f'=== machine totals (typeperf {seconds}s) ===')
    cmd = [
        'typeperf',
        r'\Processor(_Total)\% Processor Time',
        r'\Memory\Available MBytes',
        '-sc', str(max(1, seconds)),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds + 30)
    except FileNotFoundError:
        print('typeperf not found; per-process table above is enough.')
        return
    except subprocess.TimeoutExpired:
        print('typeperf timed out')
        return
    text = (proc.stdout or '') + (proc.stderr or '')
    print(text.strip() or f'typeperf exit {proc.returncode}')


def host_sample(seconds: int, out: Path | None = None, machine: bool = True):
    if os.name != 'nt':
        print('Host process sample is Windows-only.')
        return
    try:
        sample = sample_host_processes(seconds)
    except Exception as e:
        print(f'Host process sample failed: {e}')
        return
    print_host_process_sample(sample)
    if out:
        write_host_csv(out, sample)
    if machine:
        typeperf_machine(2)


def main():
    parser = argparse.ArgumentParser(description='ALAS farm-loop benchmark log parser')
    parser.add_argument('--log', type=Path, help='One ALAS log file')
    parser.add_argument('--log-dir', type=Path, default=ROOT / 'log', help='Directory of logs')
    parser.add_argument('--glob', default='*.log', help='Glob under --log-dir when --log omitted')
    parser.add_argument(
        '--host-seconds', type=float, default=0,
        help='Sample python / HD-Player / MuMuNxMain RAM+CPU over this many seconds',
    )
    parser.add_argument('--host-out', type=Path, help='Append per-process CSV (use with --host-seconds)')
    parser.add_argument(
        '--host-watch', action='store_true',
        help='Repeat --host-seconds samples until Ctrl+C',
    )
    parser.add_argument(
        '--no-machine', action='store_true',
        help='Skip typeperf Processor(_Total) / Available MBytes',
    )
    args = parser.parse_args()

    if args.host_watch and not args.host_seconds:
        args.host_seconds = 15
    if args.host_seconds:
        if args.host_watch:
            try:
                while True:
                    host_sample(args.host_seconds, out=args.host_out, machine=not args.no_machine)
                    print()
            except KeyboardInterrupt:
                print('stopped')
        else:
            host_sample(args.host_seconds, out=args.host_out, machine=not args.no_machine)

    paths = []
    if args.log:
        paths = [args.log]
    elif args.log_dir and args.log_dir.is_dir() and not args.host_seconds:
        paths = sorted(args.log_dir.glob(args.glob), key=lambda p: p.stat().st_mtime, reverse=True)[:5]

    if not paths and not args.host_seconds:
        print('No logs found. Pass --log or --host-seconds.', file=sys.stderr)
        sys.exit(1)

    for path in paths:
        if not path.is_file():
            print(f'missing {path}', file=sys.stderr)
            continue
        stats = parse_log(path.read_text(encoding='utf-8', errors='replace'))
        print_report(str(path), stats)


if __name__ == '__main__':
    main()
