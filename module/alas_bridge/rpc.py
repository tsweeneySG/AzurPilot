"""Write cmd.json and wait for ack.json on the Sweeney ALAS bridge."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from module.alas_bridge.game_state import ACK_FILE, CMD_FILE, GameState


def _log_warning(msg: str):
    try:
        from module.logger import logger
        logger.warning(msg)
    except Exception:
        print(msg)


class BridgeRpc:
    def __init__(self, game_state: GameState):
        self.game_state = game_state

    def _folder(self) -> Optional[Path]:
        return self.game_state.resolve_dir()

    def send(self, name: str, args: Optional[dict] = None, timeout: float = 8.0) -> dict:
        folder = self._folder()
        if folder is None:
            raise FileNotFoundError('Sweeney bridge account folder not found')
        cmd_id = str(uuid.uuid4())
        payload = {
            'id': cmd_id,
            'name': name,
            'args': args or {},
            'issued_at': time.time(),
        }
        cmd_path = folder / CMD_FILE
        ack_path = folder / ACK_FILE
        tmp = cmd_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        tmp.replace(cmd_path)
        deadline = time.time() + timeout
        last_err = 'timeout'
        while time.time() < deadline:
            if ack_path.is_file():
                try:
                    ack = json.loads(ack_path.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError) as e:
                    last_err = str(e)
                    time.sleep(0.1)
                    continue
                if isinstance(ack, dict) and ack.get('id') == cmd_id:
                    return ack
            time.sleep(0.1)
        _log_warning(f'Sweeney bridge RPC {name} failed: {last_err}')
        return {
            'id': cmd_id,
            'ok': False,
            'name': name,
            'error': last_err,
        }
