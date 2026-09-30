import json
import logging
import os
import uuid
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal, Optional, Tuple

Style = Literal["理性分析", "感性直觉", "圆滑机变", "直率果决"]
RelationshipLevel = Literal["冷淡", "认识", "友好", "信任", "亲密"]

RELATIONSHIP_LEVELS: tuple[RelationshipLevel, ...] = (
    "冷淡", "认识", "友好", "信任", "亲密"
)
LEVEL_INDEX: dict[RelationshipLevel, int] = {
    "冷淡": 0, "认识": 1, "友好": 2, "信任": 3, "亲密": 4
}

HISTORY_WINDOW = 10


@dataclass
class Relationship:
    level: RelationshipLevel = "冷淡"
    progress: float = 0.0


@dataclass
class HistoryEntry:
    player_input: str
    narrative: str
    options_shown: list[str] = field(default_factory=list)


@dataclass
class PlayerState:
    player_id: str
    session_id: str
    turn_count: int
    name: str
    gender: str
    age: int
    appearance: str
    background: str
    talent: str
    style: Style
    mode: str
    location: str = ""
    time: str = ""
    inventory: list[str] = field(default_factory=list)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    history: list[HistoryEntry] = field(default_factory=list)
    last_played: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["relationships"] = {
            k: asdict(v) for k, v in self.relationships.items()
        }
        d["history"] = [asdict(h) for h in self.history]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PlayerState":
        d = deepcopy(d)
        d["relationships"] = {
            k: Relationship(**v)
            for k, v in d.get("relationships", {}).items()
        }
        d["history"] = [HistoryEntry(**h) for h in d.get("history", [])]
        if "session_id" not in d:
            d["session_id"] = "default"
        if "turn_count" not in d:
            d["turn_count"] = 0
        if "last_played" not in d:
            d["last_played"] = ""
        return cls(**d)


@dataclass
class StateDelta:
    turn_count: Optional[int] = None
    location: Optional[str] = None
    time: Optional[str] = None
    inventory_add: list[str] = field(default_factory=list)
    inventory_remove: list[str] = field(default_factory=list)
    relationship_changes: dict[str, dict] = field(default_factory=dict)
    history_append: Optional[dict] = None


def _next_level(current: RelationshipLevel) -> RelationshipLevel:
    idx = LEVEL_INDEX.get(current, 0)
    if idx + 1 < len(RELATIONSHIP_LEVELS):
        return RELATIONSHIP_LEVELS[idx + 1]
    return current


class StateManager:
    """维护玩家状态 + 会话管理 + 历史窗口 + 持久化。

    存储格式: storage/players/{player_id}_{session_id}.json
    """

    def __init__(self, storage_dir: str = "storage/players"):
        self._storage_dir = storage_dir
        os.makedirs(self._storage_dir, exist_ok=True)

    def _save_path(self, player_id: str, session_id: str) -> str:
        return os.path.join(
            self._storage_dir, f"{player_id}_{session_id}.json"
        )

    def get_state(self, player_id: str, session_id: str) -> PlayerState:
        path = self._save_path(player_id, session_id)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"未找到存档: player={player_id}, session={session_id}"
            )
        with open(path, "r", encoding="utf-8") as f:
            return PlayerState.from_dict(json.load(f))

    def save_state(self, state: PlayerState) -> None:
        state.last_played = datetime.now().isoformat()
        path = self._save_path(state.player_id, state.session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

    def create_player(
        self, mode: str, profile: dict,
        player_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[str, str, PlayerState]:
        player_id = player_id or uuid.uuid4().hex[:12]
        session_id = session_id or uuid.uuid4().hex[:8]
        state = PlayerState(
            player_id=player_id,
            session_id=session_id,
            turn_count=0,
            name=profile.get("name", "未知"),
            gender=profile.get("gender", "未知"),
            age=profile.get("age", 18),
            appearance=profile.get("appearance", ""),
            background=profile.get("background", ""),
            talent=profile.get("talent", ""),
            style=profile.get("style", "感性直觉"),
            mode=mode,
        )
        self.save_state(state)
        return player_id, session_id, state

    def apply_delta(
        self, player_id: str, session_id: str, delta: StateDelta
    ) -> PlayerState:
        state = self.get_state(player_id, session_id)

        if delta.turn_count is not None:
            state.turn_count = delta.turn_count
        else:
            state.turn_count += 1

        if delta.location is not None:
            state.location = delta.location

        if delta.time is not None:
            state.time = delta.time

        for item in delta.inventory_add:
            if item and item not in state.inventory:
                state.inventory.append(item)

        for item in delta.inventory_remove:
            if item in state.inventory:
                state.inventory.remove(item)

        for npc_name, change in delta.relationship_changes.items():
            if npc_name not in state.relationships:
                state.relationships[npc_name] = Relationship()
            rel = state.relationships[npc_name]

            if "level" in change:
                new_level = change["level"]
                if new_level in RELATIONSHIP_LEVELS:
                    rel.level = new_level

            if "progress" in change:
                rel.progress = max(0.0, float(change["progress"]))

            self._handle_level_up(rel)

        if delta.history_append is not None:
            entry = HistoryEntry(
                player_input=delta.history_append.get("player_input", ""),
                narrative=delta.history_append.get("narrative", ""),
                options_shown=delta.history_append.get("options_shown", []),
            )
            state.history.insert(0, entry)
            if len(state.history) > HISTORY_WINDOW:
                state.history = state.history[:HISTORY_WINDOW]

        self.save_state(state)
        return state

    @staticmethod
    def _handle_level_up(rel: Relationship) -> None:
        while rel.progress >= 1.0:
            rel.level = _next_level(rel.level)
            rel.progress -= 1.0
        if rel.progress < 0.0:
            rel.progress = 0.0

    def player_exists(self, player_id: str, session_id: str = "default") -> bool:
        return os.path.exists(self._save_path(player_id, session_id))

    def list_sessions(self, player_id: str) -> list[str]:
        if not os.path.exists(self._storage_dir):
            return []
        prefix = f"{player_id}_"
        return sorted([
            f[len(prefix):-5]
            for f in os.listdir(self._storage_dir)
            if f.startswith(prefix) and f.endswith(".json")
        ])

    def list_saves(self) -> list[dict]:
        """全局扫描所有存档，返回元数据列表，按 last_played 倒序。"""
        saves = []
        if not os.path.exists(self._storage_dir):
            return saves

        logger = logging.getLogger("earth_online.state")
        for filename in os.listdir(self._storage_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._storage_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"跳过损坏存档 {filename}: {e}")
                continue

            saves.append({
                "player_id": data.get("player_id", ""),
                "session_id": data.get("session_id", ""),
                "name": data.get("name", "未知"),
                "mode": data.get("mode", ""),
                "turn_count": data.get("turn_count", 0),
                "last_played": data.get("last_played", ""),
            })

        saves.sort(key=lambda s: s.get("last_played", ""), reverse=True)
        return saves
