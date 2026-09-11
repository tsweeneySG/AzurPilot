"""扫描当日 AzurPilot 日志，按异常类型聚类，写出 digest 供 agent 审阅。

日日志（log/YYYY-MM-DD_N.txt）是完整计数来源；log/error/<account>/<ms>/
只保留最近若干次现场（keep_last_errlog），用作堆栈样本。

用法（在 AzurPilot 根目录）:
    uv run python -m dev_tools.scan_error_logs
    uv run python -m dev_tools.scan_error_logs --date 2026-09-10
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / 'log'
ERROR_DIR = LOG_DIR / 'error'
OUT_DIR = ROOT / 'docs' / 'log-review'

LOG_LINE_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*\|'
    r'\s*(?P<level>ERROR|CRITICAL|WARNING|INFO)\s*\|\s*(?P<msg>.*)$'
)
ERROR_TITLE_RE = re.compile(r'\[错误\]\s*(.+)')
COMMAND_IN_TITLE_RE = re.compile(r'（([^）]+)）')
COMMAND_LOCAL_RE = re.compile(r"command = '([^']+)'")
EXCEPTION_LINE_RE = re.compile(r'异常：(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:?\s*(?P<detail>.*)$')
THREW_RE = re.compile(r'程序抛出了 ([A-Za-z_][A-Za-z0-9_]*)')
ADDR_RE = re.compile(r'0x[0-9A-Fa-f]+')
COORD_RE = re.compile(r'\(\s*\d+\s*,\s*\d+\s*\)')
TS_IN_TEXT_RE = re.compile(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?')
HINT_PATTERNS = (
    ('chapter_mismatch', re.compile(r'chapter_mismatch')),
    ('no_auto_search', re.compile(r'无自动搜索选项')),
    ('too_many_click', re.compile(r'两个按钮交替点击次数过多|点击次数过多')),
    ('game_stuck', re.compile(r'GameStuckError|游戏卡住')),
    ('page_unknown', re.compile(r'无法识别游戏页面|GamePageUnknownError')),
    ('emulator_offline', re.compile(r'模拟器连接中断|EmulatorNotRunningError')),
    ('game_not_running', re.compile(r'游戏进程未运行|GameNotRunningError')),
    ('request_human', re.compile(r'RequestHumanTakeover')),
    ('auto_search_set', re.compile(r'自动搜索设置失败|AutoSearchSetError')),
    ('script_error', re.compile(r'ScriptError')),
)
RESTART_GAME_RE = re.compile(r'将在10秒后重启|将自动重启游戏|尝试重启游戏|task_call\(\'Restart\'\)')
RESTART_EMU_RE = re.compile(r'正在重启模拟器|尝试重启模拟器')
SAVE_ERROR_RE = re.compile(r'保存错误日志')

LIKELY_MAP = {
    'EmulatorNotRunningError': 'emulator',
    'GameNotRunningError': 'emulator',
    'GameBugError': 'game_client',
    'GameStuckError': 'ui_stuck',
    'GameTooManyClickError': 'ui_stuck',
    'GamePageUnknownError': 'ui_stuck',
    'CampaignNameError': 'code',
    'ScriptError': 'code',
    'AutoSearchSetError': 'code',
    'RequestHumanTakeover': 'code',
    'CampaignEnd': 'expected',
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='扫描当日 AzurPilot 日志并聚类错误')
    parser.add_argument('--date', default='today', help='YYYY-MM-DD，默认今天')
    parser.add_argument('--log-dir', default=str(LOG_DIR), help='日志根目录')
    parser.add_argument('--out-dir', default=str(OUT_DIR), help='digest 输出目录')
    parser.add_argument('--no-write', action='store_true', help='只打印，不写文件')
    return parser.parse_args(argv)


def resolve_date(value: str) -> date:
    if value in ('today', '', None):
        return date.today()
    return date.fromisoformat(value)


def unwrap_lines(path: Path):
    """合并 Rich 折行，产出 (lineno, raw) 逻辑行。"""
    pending = None
    pending_no = 1
    with path.open('r', encoding='utf-8', errors='replace') as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip('\n').rstrip('\r')
            stripped = line.strip()
            if not stripped:
                if pending is not None:
                    yield pending_no, pending
                    pending = None
                continue
            is_log = bool(LOG_LINE_RE.match(stripped))
            is_field = stripped.startswith(('原因：', '影响：', '建议：', '异常：'))
            is_box = stripped.startswith(('╭', '│', '╰', '─'))
            if pending is None:
                pending = stripped
                pending_no = lineno
                continue
            # 新日志行 / 错误字段 / traceback 框：结束上一行
            if is_log or is_field or is_box or stripped in ('CampaignNameError',):
                yield pending_no, pending
                pending = stripped
                pending_no = lineno
            else:
                pending = pending.rstrip() + ' ' + stripped
        if pending is not None:
            yield pending_no, pending


def normalize_signature(text: str) -> str:
    text = ADDR_RE.sub('<addr>', text)
    text = COORD_RE.sub('(x,y)', text)
    text = TS_IN_TEXT_RE.sub('<ts>', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 180:
        text = text[:177] + '...'
    return text


def extract_hints(window: list[str]) -> list[str]:
    blob = '\n'.join(window)
    found = []
    for name, pattern in HINT_PATTERNS:
        if pattern.search(blob):
            found.append(name)
    return found


def classify_likely(exc: str, hints: list[str]) -> str:
    if 'emulator_offline' in hints or 'game_not_running' in hints:
        return 'emulator'
    return LIKELY_MAP.get(exc, 'investigate')


def day_files(log_dir: Path, day: date) -> list[Path]:
    prefix = day.isoformat()
    files = sorted(log_dir.glob(f'{prefix}_*.txt'))
    return [p for p in files if p.is_file()]


def error_accounts(error_dir: Path) -> list[str]:
    if not error_dir.is_dir():
        return []
    return sorted(p.name for p in error_dir.iterdir() if p.is_dir())


def account_from_suffix(suffix: str, accounts: list[str]) -> str:
    if suffix == 'gui':
        return 'gui'
    for name in accounts:
        if name == suffix or name.startswith(f'{suffix}_'):
            return name
    return suffix


def ms_folder_on_date(folder_name: str, day: date) -> bool:
    try:
        ts = int(folder_name)
    except ValueError:
        return False
    # 毫秒时间戳
    if ts > 10**12:
        ts //= 1000
    try:
        dt = datetime.fromtimestamp(ts)
    except (OSError, OverflowError, ValueError):
        return False
    return dt.date() == day


def parse_error_block(msg: str, following: list[str]) -> dict:
    title_m = ERROR_TITLE_RE.search(msg)
    title = title_m.group(1).strip() if title_m else msg.strip()
    command = None
    cmd_m = COMMAND_IN_TITLE_RE.search(title)
    if cmd_m:
        command = cmd_m.group(1).strip()
    reason = impact = action = ''
    exc_name = ''
    exc_detail = ''
    for line in following:
        if line.startswith('原因：'):
            reason = line[3:].strip()
        elif line.startswith('影响：'):
            impact = line[3:].strip()
        elif line.startswith('建议：'):
            action = line[3:].strip()
        elif line.startswith('异常：'):
            em = EXCEPTION_LINE_RE.match(line)
            if em:
                exc_name = em.group('name')
                exc_detail = em.group('detail').strip()
    if not exc_name:
        threw = THREW_RE.search(reason)
        if threw:
            exc_name = threw.group(1)
    if not command:
        for line in following:
            cm = COMMAND_LOCAL_RE.search(line)
            if cm:
                command = cm.group(1)
                break
    return {
        'title': title,
        'command': command or '',
        'reason': reason,
        'impact': impact,
        'action': action,
        'exception': exc_name or 'Unknown',
        'detail': exc_detail,
    }


def cluster_id(exc: str, command: str, hints: list[str], detail: str) -> tuple[str, str]:
    hint = hints[0] if hints else ''
    sig_src = detail or hint or exc
    signature = normalize_signature(sig_src) or exc
    cid = '|'.join([exc, command or '-', hint or signature[:40]])
    return cid, signature


def scan_day_file(path: Path, account: str) -> tuple[list[dict], dict]:
    events = []
    stats = {
        'account': account,
        'file': str(path.as_posix()),
        'restarts_game': 0,
        'restarts_emulator': 0,
        'error_saves': 0,
        'errors': 0,
    }
    window: list[str] = []
    lines = list(unwrap_lines(path))
    i = 0
    while i < len(lines):
        lineno, line = lines[i]
        m = LOG_LINE_RE.match(line)
        if m:
            level = m.group('level')
            msg = m.group('msg').rstrip()
            ts = m.group('ts')
            if level == 'WARNING':
                if RESTART_GAME_RE.search(msg):
                    stats['restarts_game'] += 1
                if RESTART_EMU_RE.search(msg):
                    stats['restarts_emulator'] += 1
                if SAVE_ERROR_RE.search(msg):
                    stats['error_saves'] += 1
            if level in ('ERROR', 'CRITICAL') and '[错误]' in msg:
                following = []
                j = i + 1
                while j < len(lines):
                    _, nxt = lines[j]
                    nm = LOG_LINE_RE.match(nxt)
                    if nm:
                        break
                    following.append(nxt)
                    if nxt.startswith('异常：') or nxt.startswith('╭'):
                        # 再吞一小段 traceback 以便抓 command = '...'
                        k = j + 1
                        while k < len(lines) and k < j + 40:
                            _, extra = lines[k]
                            following.append(extra)
                            if COMMAND_LOCAL_RE.search(extra):
                                break
                            k += 1
                        break
                    j += 1
                parsed = parse_error_block(msg, following)
                hints = extract_hints(window[-30:] + [msg] + following[:15])
                cid, signature = cluster_id(
                    parsed['exception'], parsed['command'], hints, parsed['detail'],
                )
                events.append({
                    'ts': ts,
                    'level': level,
                    'account': account,
                    'source': str(path.as_posix()),
                    'line': lineno,
                    'cluster_id': cid,
                    'signature': signature,
                    'hints': hints,
                    'likely': classify_likely(parsed['exception'], hints),
                    **parsed,
                })
                stats['errors'] += 1
            window.append(line)
            if len(window) > 80:
                window = window[-80:]
        i += 1
    return events, stats


def scan_error_snapshot(log_txt: Path, account: str, folder: Path) -> dict | None:
    events, _ = scan_day_file(log_txt, account)
    if not events:
        # 现场切片可能只有 traceback、没有 error_context 头
        text = log_txt.read_text(encoding='utf-8', errors='replace')[-8000:]
        hints = extract_hints([text])
        threw = THREW_RE.search(text)
        exc = threw.group(1) if threw else ''
        if not exc:
            for name in LIKELY_MAP:
                if name in text:
                    exc = name
                    break
        cmd_m = COMMAND_LOCAL_RE.search(text)
        command = cmd_m.group(1) if cmd_m else ''
        if not exc and not hints:
            return None
        exc = exc or 'Unknown'
        cid, signature = cluster_id(exc, command, hints, '')
        events = [{
            'ts': '',
            'level': 'CRITICAL',
            'account': account,
            'source': str(log_txt.as_posix()),
            'line': 1,
            'cluster_id': cid,
            'signature': signature,
            'hints': hints,
            'likely': classify_likely(exc, hints),
            'title': '',
            'command': command,
            'reason': '',
            'impact': '',
            'action': '',
            'exception': exc,
            'detail': '',
        }]
    # 每份现场只记最后一次错误（切片对应一次 save_error_log）
    event = events[-1]
    event['snapshot'] = str(folder.as_posix())
    event['source'] = str(log_txt.as_posix())
    return event


def build_clusters(events: list[dict], sample_limit: int = 3) -> list[dict]:
    groups = defaultdict(list)
    for ev in events:
        groups[ev['cluster_id']].append(ev)
    clusters = []
    for cid, items in groups.items():
        accounts = sorted({ev['account'] for ev in items})
        samples = []
        for ev in items:
            src = ev.get('snapshot') or ev.get('source')
            if src and src not in samples:
                samples.append(src)
            if len(samples) >= sample_limit:
                break
        first = items[0]
        times = [ev['ts'] for ev in items if ev.get('ts')]
        clusters.append({
            'id': cid,
            'exception': first['exception'],
            'command': first.get('command') or '',
            'signature': first.get('signature') or '',
            'hints': first.get('hints') or [],
            'likely': first.get('likely') or 'investigate',
            'title': first.get('title') or '',
            'count': len(items),
            'accounts': accounts,
            'account_count': len(accounts),
            'samples': samples,
            'first_seen': min(times) if times else '',
            'last_seen': max(times) if times else '',
            'rank': len(items) * max(1, len(accounts)),
        })
    clusters.sort(key=lambda c: (-c['rank'], -c['count'], c['id']))
    return clusters


def _ensure_utf8_stdout():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def print_table(digest: dict) -> None:
    print(f"AzurPilot log scan  {digest['date']}")
    print(f"day files: {len(digest['day_files'])}   "
          f"errors: {digest['error_total']}   "
          f"restarts_game: {digest['restart_game_total']}   "
          f"restarts_emulator: {digest['restart_emulator_total']}   "
          f"snapshots: {digest['snapshot_count']}")
    print()
    print(f"{'rank':<6}{'count':<8}{'accts':<7}{'likely':<12}{'exc':<28}{'cmd':<16}{'signature'}")
    print('-' * 110)
    for c in digest['clusters'][:25]:
        sig = c['signature'][:48]
        print(f"{c['rank']:<6}{c['count']:<8}{c['account_count']:<7}"
              f"{c['likely']:<12}{c['exception']:<28}{(c['command'] or '-'):<16}{sig}")
    print()
    if digest.get('out_file'):
        print(f"digest: {digest['out_file']}")


def main(argv=None) -> int:
    _ensure_utf8_stdout()
    args = parse_args(argv)
    day = resolve_date(args.date)
    log_dir = Path(args.log_dir)
    out_dir = Path(args.out_dir)
    if not log_dir.is_dir():
        print(f'log dir missing: {log_dir}', file=sys.stderr)
        print('This scan must run on the local AzurPilot tree that writes log/.', file=sys.stderr)
        return 2

    accounts = error_accounts(ERROR_DIR if log_dir == LOG_DIR else log_dir / 'error')
    files = day_files(log_dir, day)
    all_events = []
    per_account = []
    for path in files:
        # 2026-09-10_1 -> 1 ; 2026-09-10_gui -> gui
        suffix = path.stem.split('_')[-1]
        account = account_from_suffix(suffix, accounts)
        events, stats = scan_day_file(path, account)
        all_events.extend(events)
        per_account.append(stats)

    snapshot_events = []
    error_root = ERROR_DIR if log_dir == LOG_DIR else log_dir / 'error'
    if error_root.is_dir():
        for acc_dir in sorted(p for p in error_root.iterdir() if p.is_dir()):
            for folder in sorted(p for p in acc_dir.iterdir() if p.is_dir()):
                if not ms_folder_on_date(folder.name, day):
                    continue
                log_txt = folder / 'log.txt'
                if not log_txt.is_file():
                    continue
                ev = scan_error_snapshot(log_txt, acc_dir.name, folder)
                if ev:
                    snapshot_events.append(ev)

    # 聚类以日日志为准（完整计数）；现场只补充 sample 路径
    clusters = build_clusters(all_events)
    snapshot_by_cluster = defaultdict(list)
    for ev in snapshot_events:
        snapshot_by_cluster[ev['cluster_id']].append(ev.get('source'))
    for cluster in clusters:
        extra = [p for p in snapshot_by_cluster.get(cluster['id'], []) if p]
        merged = list(cluster['samples'])
        for path in extra:
            if path not in merged:
                merged.append(path)
            if len(merged) >= 5:
                break
        cluster['samples'] = merged[:5]
        cluster['snapshot_count'] = len(snapshot_by_cluster.get(cluster['id'], []))

    # 日日志没扫到、但现场有的簇（例如日志已轮转）
    known = {c['id'] for c in clusters}
    orphan = [ev for ev in snapshot_events if ev['cluster_id'] not in known]
    if orphan:
        clusters.extend(build_clusters(orphan))
        clusters.sort(key=lambda c: (-c['rank'], -c['count'], c['id']))

    out_file = out_dir / f'{day.isoformat()}.digest.json'
    digest = {
        'date': day.isoformat(),
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'log_dir': str(log_dir),
        'day_files': [str(p.as_posix()) for p in files],
        'accounts': per_account,
        'error_total': sum(a['errors'] for a in per_account),
        'restart_game_total': sum(a['restarts_game'] for a in per_account),
        'restart_emulator_total': sum(a['restarts_emulator'] for a in per_account),
        'snapshot_count': len(snapshot_events),
        'clusters': clusters,
        'out_file': str(out_file.as_posix()) if not args.no_write else '',
    }
    if not args.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding='utf-8')
    print_table(digest)
    return 0


if __name__ == '__main__':
    sys.exit(main())
