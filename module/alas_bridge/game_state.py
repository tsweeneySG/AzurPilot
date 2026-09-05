"""Read Sweeney ALAS-bridge heartbeat (state.json) from the shared folder."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from module.alas_bridge.instances import commander_for_serial

STATE_FILE = 'state.json'
CMD_FILE = 'cmd.json'
ACK_FILE = 'ack.json'
PROTOCOL = 1
STALE_AFTER = 3.0

BLUESTACKS_SWMOD_ROOT = Path(
    r'C:\ProgramData\BlueStacks_nxt\Engine\UserData\SharedFolder\SweeneyMod'
)

# Local-only host share. Do not put this under Documents — Windows Known Folder
# Move parks Documents in OneDrive and the folder cannot be excluded, so the
# 0.25s heartbeat JSON would churn OneDrive forever.
MUMU_HOST_SHARE = Path(r'E:\Azur\MuMuSharedFolder')
MUMU_SWMOD_ROOT = MUMU_HOST_SHARE / 'SweeneyMod'


def _mumu_swmod_candidates():
    home = Path.home()
    return (
        MUMU_SWMOD_ROOT,
        Path(r'E:\Program Files\Netease\MuMuPlayer\vms\share\SweeneyMod'),
        Path(r'C:\Program Files\Netease\MuMuPlayer-12.0\vms\share\SweeneyMod'),
        Path(r'D:\Program Files\Netease\MuMuPlayer-12.0\vms\share\SweeneyMod'),
        # Last-resort leftovers. Documents is OneDrive on this machine.
        home / 'Documents' / 'MuMuSharedFolder' / 'SweeneyMod',
        home / 'OneDrive' / 'Documents' / 'MuMuSharedFolder' / 'SweeneyMod',
        home / 'Documents' / 'MuMu shared folder' / 'SweeneyMod',
        home / 'Documents' / 'MuMu共享文件夹' / 'SweeneyMod',
    )


def resolve_default_swmod_root() -> Path:
    """
    Host SweeneyMod root. Prefer the local MuMu share so tools do not scan a
    stale BlueStacks tree or OneDrive Documents. Config/env still win.
    """
    env = (os.environ.get('SWEENEY_SWMOD_ROOT') or '').strip()
    if env:
        return Path(env)
    if MUMU_SWMOD_ROOT.is_dir():
        return MUMU_SWMOD_ROOT
    if BLUESTACKS_SWMOD_ROOT.is_dir():
        return BLUESTACKS_SWMOD_ROOT
    for cand in _mumu_swmod_candidates():
        if cand.is_dir():
            return cand
    return MUMU_SWMOD_ROOT


DEFAULT_SWMOD_ROOT = resolve_default_swmod_root()

# SCENE key and SCENE value -> ALAS Page.name (keep in sync with mod_alas_bridge.lua)
# SCENE.LEVEL is the sortie hub, chapter list, and in-map. Sub-state is in
# heartbeat `level.entrance` / `level.in_map` (see page_name_from_state).
SCENE_TO_PAGE = {
    'MAINUI': 'page_main',
    'scene mainUI': 'page_main',
    'EVENT': 'page_commission',
    'scene event': 'page_commission',
    'DAILYLEVEL': 'page_daily',
    'scene dailylevel': 'page_daily',
    'COURTYARD': 'page_dorm',
    'BACKYARD': 'page_dorm',
    'scene court yard': 'page_dorm',
    'NAVALTACTICS': 'page_tactical',
    'naval tactics': 'page_tactical',
    'WORLD': 'page_os',
    'scene world': 'page_os',
    'SHOP': 'page_shop',
    'NEW_SHOP': 'page_shop',
    'scene shop': 'page_shop',
    'new shop': 'page_shop',
    'DOCKYARD': 'page_dock',
    'scene dockyard': 'page_dock',
    'NAVALACADEMYSCENE': 'page_academy',
    'naval academy scene': 'page_academy',
    'CLASS': 'page_academy',
    'scene class': 'page_academy',
    'SETTINGS': 'page_settings',
    'scene settings': 'page_settings',
    'TASK': 'page_mission',
    'scene task': 'page_mission',
    'GUILD': 'page_guild',
    'NEWGUILD': 'page_guild',
    'scene guild': 'page_guild',
    'scene newguild': 'page_guild',
    'TECHNOLOGY': 'page_research',
    'technology': 'page_research',
    'BIANDUI': 'page_fleet',
    'scene biandui': 'page_fleet',
    'ISLAND': 'page_island',
    'ISLAND_TASK': 'page_island',
    'scene island': 'page_island',
    'island task': 'page_island',
    'DORM3DSELECT': 'page_private_quarters',
    'DORM3D_ROOM': 'page_private_quarters',
    'dorm 3d select': 'page_private_quarters',
    'dorm 3d room': 'page_private_quarters',
    'COMMANDERCAT': 'page_meowfficer',
    'scene commander cat room': 'page_meowfficer',
    'MAIL': 'page_mail',
    'mail': 'page_mail',
    'CRUSING': 'page_battle_pass',
    'crusing': 'page_battle_pass',
    'GETBOAT': 'page_build',
    'scene get boat': 'page_build',
    'CHARGE': 'page_shop',
    'CHARGE_MENU': 'page_shop',
    'scene charge': 'page_shop',
    'scene charge_menu': 'page_shop',
    'ACTIVITY': 'page_event_list',
    'scene activity': 'page_event_list',
    'BOSSRUSH_MAIN': 'page_coalition',
    'bossrush main': 'page_coalition',
    'ACT_BOSS_BATTLE': 'page_raid',
    'act boss battle': 'page_raid',
    'EXERCISEFORMATION': 'page_exercise',
    'scene exerciseformation': 'page_exercise',
    'LOGIN': 'page_login',
    'scene login': 'page_login',
    'TRANSITION': 'page_transition',
    'scene transition': 'page_transition',
    'COMBATLOAD': 'page_transition',
    'scene combat load': 'page_transition',
}

OVERLAY_TO_PAGE = {
    'IslandShopMediator': 'page_island_shop',
    'IslandMapMediator': 'page_island_map',
    'IslandSeasonMediator': 'page_island_season',
    'IslandTechnologyMediator': 'page_island_technology',
    'IslandOrderMediator': 'page_island_order',
    'IslandManageMediator': 'page_island_manage',
    'MailMediator': 'page_mail',
    'MainLiveAreaPage': 'page_dormmenu',
    'MainLiveAreaOldPage': 'page_dormmenu',
    # MAINUI commission panel (oil/coin/tactical entry) — ALAS page_reward.
    'CommissionInfoMediator': 'page_reward',
    # Synthetic overlays from CollectOverlays (msgbox / story).
    'MsgboxShowing': 'page_unknown',
    'StoryPlaying': 'page_unknown',
}


def _level_page_from_state(state: dict) -> Optional[str]:
    """SCENE.LEVEL is sortie hub, main/event chapter list, or in-map."""
    scene = state.get('scene_key') or state.get('scene')
    page = state.get('page')
    on_level = scene in ('LEVEL', 'scene level') or page in (
        'page_campaign',
        'page_campaign_menu',
        'page_event',
    )
    if not on_level:
        return None
    level = state.get('level')
    if not isinstance(level, dict):
        return None
    if level.get('in_map'):
        return 'page_in_map'
    if level.get('entrance'):
        return 'page_campaign_menu'
    if level.get('activity') and not level.get('remaster'):
        return 'page_event'
    if level.get('entrance') is False:
        return 'page_campaign'
    return None


def page_name_from_state(state: dict) -> Optional[str]:
    """Map a heartbeat dict to an ALAS Page.name, or None if unknown/combat."""
    if not isinstance(state, dict):
        return None
    overlays = state.get('overlays') or []
    if isinstance(overlays, list):
        for name in overlays:
            mapped = OVERLAY_TO_PAGE.get(name)
            if mapped:
                return mapped
    level_page = _level_page_from_state(state)
    if level_page:
        return level_page
    page = state.get('page')
    if isinstance(page, str) and page:
        return page
    for key in (state.get('scene_key'), state.get('scene')):
        if isinstance(key, str) and key in SCENE_TO_PAGE:
            return SCENE_TO_PAGE[key]
    return None


def page_from_name(name: Optional[str]):
    if not name:
        return None
    from module.ui.page import Page
    return Page.all_pages.get(name)


def _folder_matches_commander(folder: Path, commander: str) -> bool:
    if not commander:
        return False
    suffix = '_' + commander.lower()
    return folder.name.lower().endswith(suffix) or folder.name.lower() == commander.lower()


def _player_name_from_state_file(folder: Path) -> str:
    path = folder / STATE_FILE
    if not path.is_file():
        return ''
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return ''
    player = data.get('player') if isinstance(data, dict) else None
    if isinstance(player, dict):
        return str(player.get('name') or '')
    return ''


def iter_account_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    for child in root.iterdir():
        if child.is_dir() and child.name != 'unknown_account':
            out.append(child)
    return out


def discover_account_dir(root: Path, account: str = '', commander: str = '') -> Optional[Path]:
    """
    Resolve `{playerId}_{commander}` under the SweeneyMod root.

    Prefer an explicit folder, then commander-name suffix (from Emulator.Serial
    via emulator_instances.json). Never pick the globally newest state.json when
    multiple accounts exist.
    """
    if not root.is_dir():
        return None
    if account:
        direct = root / account
        if direct.is_dir():
            return direct
        lowered = account.lower()
        hits = [p for p in iter_account_dirs(root) if p.name.lower() == lowered or p.name.lower().endswith('_' + lowered)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return max(hits, key=lambda p: (p / STATE_FILE).stat().st_mtime if (p / STATE_FILE).is_file() else 0)
    if commander:
        hits = []
        for child in iter_account_dirs(root):
            if _folder_matches_commander(child, commander):
                hits.append(child)
                continue
            if _player_name_from_state_file(child).lower() == commander.lower():
                hits.append(child)
        if len(hits) == 1:
            return hits[0]
        if hits:
            return max(hits, key=lambda p: (p / STATE_FILE).stat().st_mtime if (p / STATE_FILE).is_file() else 0)
        return None
    with_state = [p for p in iter_account_dirs(root) if (p / STATE_FILE).is_file()]
    if len(with_state) == 1:
        return with_state[0]
    return None


class GameState:
    def __init__(self, root: Optional[Path] = None, account: str = '', commander: str = '', serial: str = ''):
        self.root = Path(root) if root else DEFAULT_SWMOD_ROOT
        self.account = account or ''
        self.serial = serial or ''
        self.commander = commander or (commander_for_serial(self.serial) if self.serial else '')
        self.account_dir: Optional[Path] = None
        self._state: Optional[dict] = None
        self._mtime: float = 0.0

    @classmethod
    def from_config(cls, config) -> 'GameState':
        root = getattr(config, 'Optimization_SweeneyBridgeRoot', None) or ''
        account = getattr(config, 'Optimization_SweeneyBridgeAccount', None) or ''
        serial = getattr(config, 'Emulator_Serial', None) or ''
        path = Path(root) if str(root).strip() else resolve_default_swmod_root()
        return cls(
            root=path,
            account=str(account).strip(),
            serial=str(serial).strip(),
        )

    def resolve_dir(self) -> Optional[Path]:
        if self.account_dir is not None and self.account_dir.is_dir():
            return self.account_dir
        self.account_dir = discover_account_dir(self.root, account=self.account, commander=self.commander)
        return self.account_dir

    def state_path(self) -> Optional[Path]:
        folder = self.resolve_dir()
        if folder is None:
            return None
        return folder / STATE_FILE

    def read(self, max_age: float = STALE_AFTER) -> Optional[dict]:
        path = self.state_path()
        if path is None or not path.is_file():
            return None
        try:
            mtime = path.stat().st_mtime
            age = time.time() - mtime
            if max_age is not None and age > max_age:
                return None
            text = path.read_text(encoding='utf-8')
            data = json.loads(text)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or not data.get('alive'):
            return None
        self._state = data
        self._mtime = mtime
        return data

    def get_page(self, max_age: float = STALE_AFTER):
        state = self.read(max_age=max_age)
        if state is None:
            return None
        name = page_name_from_state(state)
        page = page_from_name(name)
        return page
