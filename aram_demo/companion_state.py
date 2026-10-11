"""Mode-gated companion lifecycle. No GUI, network or game writes."""
from dataclasses import dataclass, field

MAYHEM_QUEUE = 2400  # Riot's official queues.json: ARAM: Mayhem.
MAYHEM_QUEUES = frozenset((MAYHEM_QUEUE, 3270))  # 3270: Tencent custom KIWI, verified in local client logs.
PLAYING = ('GameStart', 'InProgress', 'Reconnect')
ACTIVE = ('Lobby', 'Matchmaking', 'ReadyCheck', 'ChampSelect', *PLAYING)


@dataclass(frozen=True)
class PanelState:
    stage: str = 'hidden'
    phase: str = 'Disconnected'
    champion_id: int | None = None
    candidate_ids: list[int] = field(default_factory=list)
    queue_id: int | None = None
    match_id: int | None = None
    revision: int = 0


class SessionTracker:
    def __init__(self):
        self.state = PanelState()

    def update(self, raw):
        old = self.state
        new_match = bool(old.match_id and raw.match_id and old.match_id != raw.match_id)
        continuing = old.phase in ACTIVE and raw.phase in ACTIVE and not new_match
        queue_id = raw.queue_id if raw.queue_id is not None else old.queue_id if continuing else None
        target = queue_id in MAYHEM_QUEUES and raw.phase in ACTIVE
        if target:
            stage = 'game' if raw.phase in PLAYING else 'select' if raw.phase == 'ChampSelect' else 'lobby'
            retain = raw.phase in PLAYING and old.phase in ('ChampSelect', *PLAYING) and continuing
            cid = raw.champion_id or (old.champion_id if retain else None)
            candidates = list(dict.fromkeys(raw.candidate_ids)) if stage == 'select' else []
            match_id = raw.match_id or (old.match_id if continuing else None)
        else:
            stage, cid, candidates, match_id = 'hidden', None, [], None
            if raw.phase not in ACTIVE:
                queue_id = None
        changed = (stage, cid, queue_id, match_id) != (old.stage, old.champion_id, old.queue_id, old.match_id)
        self.state = PanelState(stage, raw.phase, cid, candidates, queue_id, match_id, old.revision + int(changed))
        return self.state
