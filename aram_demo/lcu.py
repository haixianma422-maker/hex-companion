"""Read-only, localhost-only League client access."""
import base64
import json
import os
import re
import ssl
import subprocess
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path

from .companion_state import ACTIVE


@dataclass(frozen=True)
class ClientState:
    phase: str = 'Disconnected'
    champion_id: int | None = None
    candidate_ids: list[int] = field(default_factory=list)
    source: str = 'LCU'
    message: str = ''
    match_id: int | None = None
    queue_id: int | None = None


@dataclass(frozen=True)
class Credentials:
    port: int
    token: str = field(repr=False)
    protocol: str = 'https'


def parse_lockfile(text):
    parts = text.strip().split(':')
    if len(parts) != 5:
        raise ValueError('lockfile 格式不正确')
    port = int(parts[2])
    if not 1 <= port <= 65535 or parts[4] not in ('https', 'http') or not parts[3]:
        raise ValueError('lockfile 端口或协议不正确')
    return Credentials(port, parts[3], parts[4])


def positive(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def parse_session(session):
    cell = session.get('localPlayerCellId')
    me = next((p for p in session.get('myTeam', []) if p.get('cellId') == cell), {}) if cell is not None else {}
    candidates = list(dict.fromkeys(c for x in session.get('benchChampions', [])
                                   if (c := positive(x.get('championId')))))
    return ClientState('ChampSelect', positive(me.get('championId')), candidates, 'LCU',
                       '已读取选人状态' if candidates else '未返回替补席，可手动补充候选')


def validate_install_path(value):
    if not value:
        return
    root = Path(value)
    if not any(path.is_file() for path in (root / 'LeagueClient.exe', root / 'LeagueClient' / 'LeagueClient.exe')):
        raise ValueError('请选择包含 LeagueClient.exe 或 LeagueClient 子文件夹的游戏安装目录。Documents\\League of Legends 通常是录像目录。')


def client_processes():
    if os.name != 'nt':
        return []
    command = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process -Filter \"Name='LeagueClientUx.exe' OR Name='LeagueClient.exe'\" | Select-Object Name,ProcessId,CommandLine,ExecutablePath | ConvertTo-Json -Compress"
    try:
        raw = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True,
                             text=True, encoding='utf-8', timeout=7, creationflags=subprocess.CREATE_NO_WINDOW)
        processes = json.loads(raw.stdout or '[]')
        if isinstance(processes, dict):
            return [processes]
        return [p for p in processes or [] if isinstance(p, dict)]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def discovery_message(processes):
    if processes:
        return '客户端已运行，但无法读取连接凭据。若联盟以管理员运行，请退出工具后使用 start_companion_admin.cmd。'
    return '未发现客户端；请启动联盟。安装目录应包含 LeagueClient.exe，不能选择录像目录。'


def discover(install_path=None, processes=None):
    if processes is None:
        processes = client_processes()
    for process in processes:
        cmd = process.get('CommandLine') or ''
        port = re.search(r'--app-port[= ](\d+)', cmd)
        token = re.search(r'--remoting-auth-token[= ]([^\s"]+)', cmd)
        if port and token and 1 <= int(port[1]) <= 65535:
            return Credentials(int(port[1]), token[1])
    roots = [Path(install_path)] if install_path else []
    # A running client's path also locates lockfile when startup flags are absent.
    roots += [Path(p['ExecutablePath']).parent for p in processes if p.get('ExecutablePath')]
    if os.name == 'nt':
        roots += [Path(p) for p in (r'C:\Riot Games\League of Legends', r'D:\WeGameApps\英雄联盟', r'D:\WeGame\英雄联盟')]
    for root in roots:
        for path in (root / 'lockfile', root / 'LeagueClient' / 'lockfile'):
            try:
                return parse_lockfile(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
    return None


def local_json(url, headers=None):
    # This helper is only called with hard-coded localhost URLs.
    request = urllib.request.Request(url, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    with opener.open(request, timeout=3) as response:
        return json.load(response)


class LCUClient:
    def __init__(self, install_path=None):
        self.install_path = install_path
        # Discovery starts PowerShell; reuse credentials until a request fails.
        self.credentials = None

    def read_state(self):
        if self.credentials is None:
            processes = client_processes()
            self.credentials = discover(self.install_path, processes)
            if not self.credentials:
                return ClientState(message=discovery_message(processes))
        credentials = self.credentials
        auth = base64.b64encode(('riot:' + credentials.token).encode()).decode()

        def get(path):
            return local_json(f'{credentials.protocol}://127.0.0.1:{credentials.port}{path}', {'Authorization': 'Basic ' + auth})

        phase, match_id, queue_id = 'Disconnected', None, None
        failures = []
        def optional(path):
            try:
                return get(path)
            except (OSError, ValueError, TypeError):
                failures.append(path)
                return None
        try:
            phase = get('/lol-gameflow/v1/gameflow-phase')
            session = optional('/lol-gameflow/v1/session') if phase in ACTIVE else None
            game = session.get('gameData', {}) if isinstance(session, dict) else {}
            queue_info = game.get('queue') or {}
            queue_id = positive(queue_info.get('id')) or positive(game.get('queueId'))
            match_id = positive(game.get('gameId'))
            if queue_id is None and phase in ('Lobby', 'Matchmaking', 'ReadyCheck', 'ChampSelect'):
                lobby = optional('/lol-lobby/v2/lobby')
                if isinstance(lobby, dict):
                    queue_id = positive((lobby.get('gameConfig') or {}).get('queueId'))
            if phase == 'ChampSelect':
                selected = get('/lol-champ-select/v1/session')
                return replace(parse_session(selected), match_id=match_id,
                               queue_id=queue_id or positive(selected.get('queueId')))
            if phase in ('InProgress', 'GameStart', 'Reconnect'):
                me = (optional('/lol-summoner/v1/current-summoner') or {}) if game else {}
                players = game.get('teamOne', []) + game.get('teamTwo', [])
                identity = positive(me.get('summonerId'))
                player = next((p for p in players if identity is not None and p.get('summonerId') == identity), {})
                message = '部分客户端接口暂不可用' if failures else '游戏进行中'
                return ClientState(phase, positive(player.get('championId')), message=message, match_id=match_id, queue_id=queue_id)
            return ClientState(str(phase), message='等待选人或对局开始', match_id=match_id, queue_id=queue_id)
        except (OSError, ValueError, TypeError, AttributeError):
            if phase == 'Disconnected':
                # The gameflow request itself failed: the client restarted or exited.
                self.credentials = None
            return ClientState(str(phase), message='客户端接口暂不可用；请刷新或检查运行权限', match_id=match_id, queue_id=queue_id)


def live_champion_id(champions):
    try:
        name = local_json('https://127.0.0.1:2999/liveclientdata/activeplayername')
        if not isinstance(name, str) or not name.strip():
            return None
        players = local_json('https://127.0.0.1:2999/liveclientdata/playerlist')
        me = next((p for p in players if name in (p.get('riotId'), p.get('summonerName'))), None)
        if not me:
            return None
        raw = str(me.get('rawChampionName', '')).removeprefix('game_character_displayname_').casefold()
        plain = str(me.get('championName', '')).casefold()
        return next((c.id for c in champions if c.slug.casefold() in (raw, plain) or c.name.casefold() == plain), None)
    except (OSError, ValueError, TypeError):
        return None
