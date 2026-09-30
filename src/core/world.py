import json
import os
from typing import Optional

from src.utils.path import data_path


class WorldConfig:
    """加载/维护静态世界数据（NPC库/地点库/事件/世界观描述），只读。"""

    def __init__(self, config_dir: Optional[str] = None):
        self._config_dir = config_dir or data_path("config/world")
        self._locations: Optional[dict] = None
        self._npcs: Optional[dict] = None
        self._events: Optional[dict] = None

    @property
    def locations(self) -> Optional[dict]:
        if self._locations is None:
            path = os.path.join(self._config_dir, "locations.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._locations = json.load(f)
            else:
                self._locations = {}
        return self._locations

    @property
    def npcs(self) -> Optional[dict]:
        if self._npcs is None:
            path = os.path.join(self._config_dir, "npcs.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._npcs = json.load(f)
            else:
                self._npcs = {}
        return self._npcs

    @property
    def events(self) -> Optional[dict]:
        if self._events is None:
            path = os.path.join(self._config_dir, "events.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._events = json.load(f)
            else:
                self._events = {}
        return self._events

    def get_location(self, name: str) -> Optional[dict]:
        locs = self.locations
        return locs.get(name) if locs else None

    def get_npc(self, name: str) -> Optional[dict]:
        npcs_data = self.npcs
        return npcs_data.get(name) if npcs_data else None

    def reload(self) -> None:
        self._locations = None
        self._npcs = None
        self._events = None
