import json
import os
import shutil
import tempfile
import pytest
from src.core.state import (
    StateManager,
    PlayerState,
    StateDelta,
    Relationship,
    HistoryEntry,
)


class TestPlayerState:
    def test_create_minimal(self):
        state = PlayerState(
            player_id="test001",
            session_id="abc12345",
            turn_count=0,
            name="测试",
            gender="男",
            age=25,
            appearance="普通",
            background="无",
            talent="无",
            style="理性分析",
            mode="现代都市",
        )
        assert state.session_id == "abc12345"
        assert state.turn_count == 0
        assert state.style == "理性分析"
        assert state.inventory == []

    def test_to_dict_and_back(self):
        state = PlayerState(
            player_id="test001",
            session_id="abc12345",
            turn_count=5,
            name="测试",
            gender="男",
            age=25,
            appearance="普通",
            background="无",
            talent="无",
            style="感性直觉",
            mode="现代都市",
            location="网吧",
            time="黄昏",
            inventory=["手机", "钱包"],
            relationships={"张宇": Relationship(level="友好", progress=0.5)},
            history=[
                HistoryEntry(
                    player_input="去网吧",
                    narrative="你走进网吧...",
                    options_shown=["继续", "离开"],
                )
            ],
        )
        d = state.to_dict()
        restored = PlayerState.from_dict(d)
        assert restored.session_id == "abc12345"
        assert restored.turn_count == 5
        assert restored.location == "网吧"
        assert restored.inventory == ["手机", "钱包"]
        assert restored.relationships["张宇"].level == "友好"
        assert restored.relationships["张宇"].progress == 0.5
        assert len(restored.history) == 1

    def test_from_dict_missing_session_defaults(self):
        d = {
            "player_id": "x",
            "name": "x", "gender": "x", "age": 1,
            "appearance": "x", "background": "x", "talent": "x",
            "style": "理性分析", "mode": "x",
        }
        state = PlayerState.from_dict(d)
        assert state.session_id == "default"
        assert state.turn_count == 0


class TestStateManager:
    @pytest.fixture
    def tmp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def sm(self, tmp_dir):
        return StateManager(storage_dir=tmp_dir)

    def test_create_player(self, sm):
        pid, sid, state = sm.create_player("现代都市", {
            "name": "张三",
            "gender": "男",
            "age": 22,
            "appearance": "戴眼镜",
            "background": "普通家庭",
            "talent": "记忆力好",
            "style": "理性分析",
        })
        assert state.name == "张三"
        assert state.mode == "现代都市"
        assert state.style == "理性分析"
        assert state.turn_count == 0
        assert len(pid) == 12
        assert len(sid) == 8
        assert sm.player_exists(pid, sid)

    def test_create_player_custom_session(self, sm):
        pid, sid, state = sm.create_player("现代都市", {"name": "张三"}, session_id="mysave")
        assert sid == "mysave"

    def test_get_state_not_found(self, sm):
        with pytest.raises(FileNotFoundError):
            sm.get_state("nonexistent", "default")

    def test_turn_count_auto_increment(self, sm):
        pid, sid, state = sm.create_player("现代都市", {"name": "张三"})
        assert state.turn_count == 0
        state = sm.apply_delta(pid, sid, StateDelta())
        assert state.turn_count == 1
        state = sm.apply_delta(pid, sid, StateDelta())
        assert state.turn_count == 2
        state = sm.apply_delta(pid, sid, StateDelta(turn_count=99))
        assert state.turn_count == 99

    def test_apply_delta_location(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(location="网吧"))
        updated = sm.get_state(pid, sid)
        assert updated.location == "网吧"

    def test_apply_delta_inventory(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(inventory_add=["手机", "钥匙"]))
        updated = sm.get_state(pid, sid)
        assert "手机" in updated.inventory
        assert "钥匙" in updated.inventory

        sm.apply_delta(pid, sid, StateDelta(
            inventory_add=["手机"],
            inventory_remove=["钥匙"],
        ))
        updated = sm.get_state(pid, sid)
        assert "手机" in updated.inventory
        assert "钥匙" not in updated.inventory
        assert len(updated.inventory) == 1

    def test_apply_delta_relationship(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"level": "友好", "progress": 0.5}},
        ))
        updated = sm.get_state(pid, sid)
        assert updated.relationships["张宇"].level == "友好"
        assert updated.relationships["张宇"].progress == 0.5

    def test_apply_delta_relationship_new_npc(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"陌生人": {"progress": 0.3}},
        ))
        updated = sm.get_state(pid, sid)
        assert updated.relationships["陌生人"].level == "冷淡"
        assert updated.relationships["陌生人"].progress == 0.3

    def test_apply_delta_relationship_invalid_level(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"level": "不存在的等级"}},
        ))
        updated = sm.get_state(pid, sid)
        assert updated.relationships["张宇"].level == "冷淡"

    def test_apply_delta_history_and_window(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        entry = {
            "player_input": "走向网吧",
            "narrative": "你穿过街道...",
            "options_shown": ["进去", "离开"],
        }
        state = sm.apply_delta(pid, sid, StateDelta(history_append=entry))
        assert len(state.history) == 1
        assert state.history[0].player_input == "走向网吧"

    def test_history_window_limit(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        for i in range(15):
            sm.apply_delta(pid, sid, StateDelta(history_append={
                "player_input": f"动作{i}",
                "narrative": "叙事",
                "options_shown": [],
            }))
        state = sm.get_state(pid, sid)
        assert len(state.history) == 10
        assert state.history[0].player_input == "动作14"

    def test_list_sessions(self, sm):
        pid, _, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.create_player("现代都市", {"name": "张三"},
                         player_id=pid, session_id="save2")
        sessions = sm.list_sessions(pid)
        assert len(sessions) == 2

    def test_progress_clamped(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"progress": 1.5}},
        ))
        updated = sm.get_state(pid, sid)
        assert updated.relationships["张宇"].progress <= 1.0

        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"progress": -0.5}},
        ))
        updated = sm.get_state(pid, sid)
        assert updated.relationships["张宇"].progress == 0.0

    def test_level_up_on_progress_overflow(self, sm):
        """progress 到达 1.0 以上时直接跃迁，多余部分保留。"""
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"level": "认识", "progress": 0.9}},
        ))
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"progress": 1.2}},
        ))
        updated = sm.get_state(pid, sid)
        assert updated.relationships["张宇"].level == "友好"
        assert 0 <= updated.relationships["张宇"].progress < 1.0

    def test_level_up_at_max_stays(self, sm):
        """亲密为最高级，溢出不改变级别。"""
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"level": "亲密", "progress": 0.9}},
        ))
        sm.apply_delta(pid, sid, StateDelta(
            relationship_changes={"张宇": {"progress": 1.2}},
        ))
        updated = sm.get_state(pid, sid)
        assert updated.relationships["张宇"].level == "亲密"
        assert 0 <= updated.relationships["张宇"].progress < 1.0

    # ── list_saves / last_played ──────────────────────

    def test_list_saves_empty(self, sm):
        assert sm.list_saves() == []

    def test_list_saves_returns_metadata(self, sm):
        pid, sid, _ = sm.create_player("修仙玄幻", {"name": "张三"})
        sm.apply_delta(pid, sid, StateDelta())
        saves = sm.list_saves()
        assert len(saves) == 1
        s = saves[0]
        assert s["name"] == "张三"
        assert s["mode"] == "修仙玄幻"
        assert s["turn_count"] == 1
        assert s["player_id"] == pid
        assert s["session_id"] == sid
        assert s["last_played"] != ""

    def test_last_played_written_on_save(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})
        state = sm.get_state(pid, sid)
        assert state.last_played != ""

    def test_last_played_backward_compatible(self):
        """旧存档没有 last_played 字段，from_dict 应补默认空串。"""
        d = {
            "player_id": "x", "session_id": "s",
            "turn_count": 0, "name": "x", "gender": "x", "age": 1,
            "appearance": "x", "background": "x", "talent": "x",
            "style": "理性分析", "mode": "x",
        }
        state = PlayerState.from_dict(d)
        assert state.last_played == ""

    def test_list_saves_skips_corrupt_file(self, sm):
        sm.create_player("现代都市", {"name": "张三"})
        corrupt_path = os.path.join(sm._storage_dir, "broken_x_y.json")
        with open(corrupt_path, "w", encoding="utf-8") as f:
            f.write("{ 这不是合法 JSON")
        saves = sm.list_saves()
        assert len(saves) == 1
        assert saves[0]["name"] == "张三"

    def test_list_saves_sorted_desc(self, sm):
        pid, sid, _ = sm.create_player("现代都市", {"name": "旧档"})
        path = sm._save_path(pid, sid)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["last_played"] = "2020-01-01T00:00:00"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        sm.create_player("现代都市", {"name": "新档"})
        saves = sm.list_saves()
        assert saves[0]["name"] == "新档"
        assert saves[1]["name"] == "旧档"
