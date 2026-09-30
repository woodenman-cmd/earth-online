import pytest
from src.core.state import (
    StateManager,
    PlayerState,
    StateDelta,
    Relationship,
    HistoryEntry,
)
from src.engine.updater import StateUpdater


def make_state(**overrides) -> PlayerState:
    defaults = {
        "player_id": "pid01",
        "session_id": "sid01",
        "turn_count": 3,
        "name": "测试",
        "gender": "男",
        "age": 25,
        "appearance": "普通",
        "background": "无",
        "talent": "无",
        "style": "理性分析",
        "mode": "现代都市",
        "location": "城中村·出租屋",
        "time": "黄昏·19:00",
        "inventory": ["手机"],
        "relationships": {
            "张宇": Relationship(level="友好", progress=0.5),
            "李姐": Relationship(level="认识", progress=0.2),
        },
        "history": [],
    }
    defaults.update(overrides)
    return PlayerState(**defaults)


class TestBuildDelta:
    def test_empty_state_changes(self):
        state = make_state()
        delta, warnings = StateUpdater.build_delta(state, {})
        assert delta.location is None
        assert delta.time is None
        assert delta.inventory_add == []
        assert delta.inventory_remove == []
        assert delta.relationship_changes == {}
        assert warnings == []

    def test_state_changes_is_list(self):
        state = make_state()
        delta, warnings = StateUpdater.build_delta(state, [1, 2, 3])
        assert delta.location is None

    def test_location_change(self):
        state = make_state()
        delta, warnings = StateUpdater.build_delta(state, {"location": "网吧"})
        assert delta.location == "网吧"

    def test_location_empty_string_ignored(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(state, {"location": ""})
        assert delta.location is None

    def test_location_non_string_ignored(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(state, {"location": 123})
        assert delta.location is None

    def test_time_change(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(state, {"time": "黄昏·19:15"})
        assert delta.time == "黄昏·19:15"

    def test_inventory_add(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state, {"inventory_add": ["打火机", "钥匙"]}
        )
        assert "打火机" in delta.inventory_add
        assert "钥匙" in delta.inventory_add

    def test_inventory_add_with_falsy_filtered(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state, {"inventory_add": ["刀", "", None, "绳"]}
        )
        assert delta.inventory_add == ["刀", "绳"]

    def test_inventory_remove(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state, {"inventory_remove": ["手机"]}
        )
        assert "手机" in delta.inventory_remove

    def test_unknown_field_discarded(self):
        state = make_state()
        delta, warnings = StateUpdater.build_delta(
            state, {"hp": 100, "mana": 50, "gold": 999}
        )
        assert delta.location is None
        assert warnings == []

    def test_mixed_known_and_unknown_fields(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state, {
                "location": "公司大楼",
                "hp": 100,
                "inventory_add": ["工牌"],
            }
        )
        assert delta.location == "公司大楼"
        assert "工牌" in delta.inventory_add

    def test_progress_increment(self):
        """AI 输出 progress=0.15 → 转换为绝对 progress=0.65。"""
        state = make_state()
        delta, warnings = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"progress": 0.15}}},
        )
        assert warnings == []
        assert "张宇" in delta.relationship_changes
        assert delta.relationship_changes["张宇"]["progress"] == pytest.approx(0.65)

    def test_progress_increment_from_zero(self):
        """无 history 的 NPC，progress 增量从 0 开始。"""
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"陌生人": {"progress": 0.3}}},
        )
        assert delta.relationship_changes["陌生人"]["progress"] == pytest.approx(0.3)

    def test_level_change_within_one(self):
        """友好→信任 (+1 级) 不触发告警。"""
        state = make_state()
        delta, warnings = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"level": "信任"}}},
        )
        assert warnings == []
        assert delta.relationship_changes["张宇"]["level"] == "信任"
        assert delta.relationship_changes["张宇"]["progress"] == 0.1

    def test_level_change_cross_jump(self):
        """友好→亲密 (+2 级) 触发异常告警。"""
        state = make_state()
        delta, warnings = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"level": "亲密"}}},
        )
        assert len(warnings) == 1
        assert "跨级跃迁" in warnings[0]
        assert "张宇" in warnings[0]
        # 即使告警，变更仍然执行
        assert delta.relationship_changes["张宇"]["level"] == "亲密"

    def test_level_change_extreme_jump(self):
        """冷淡→亲密 (+4) 触发告警但放行。"""
        state = make_state()
        delta, warnings = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"level": "亲密"}}},
        )
        assert len(warnings) == 1
        assert "跨级跃迁" in warnings[0]
        assert delta.relationship_changes["张宇"]["level"] == "亲密"

    def test_level_change_resets_progress(self):
        """层级改变时 progress 重置为 0.1。"""
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"level": "信任"}}},
        )
        assert delta.relationship_changes["张宇"]["progress"] == 0.1

    def test_invalid_level_ignored(self):
        state = make_state()
        delta, warnings = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"level": "生死之交"}}},
        )
        assert warnings == []
        assert "张宇" not in delta.relationship_changes

    def test_relationship_changes_not_dict(self):
        state = make_state()
        delta, warnings = StateUpdater.build_delta(
            state,
            {"relationship_changes": [1, 2, 3]},
        )
        assert delta.relationship_changes == {}
        assert warnings == []

    def test_individual_change_not_dict(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": "不是字典"}},
        )
        assert "张宇" not in delta.relationship_changes

    def test_progress_invalid_value_ignored(self):
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"progress": "很多"}}},
        )
        assert "张宇" not in delta.relationship_changes

    def test_progress_zero_increment_ignored(self):
        """增量为 0 时不产生变更。"""
        state = make_state()
        delta, _ = StateUpdater.build_delta(
            state,
            {"relationship_changes": {"张宇": {"progress": 0}}},
        )
        assert "张宇" not in delta.relationship_changes


class TestApply:
    def test_apply_updates_state(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        _, sid, state = sm.create_player("现代都市", {
            "name": "张三",
            "style": "理性分析",
        })

        new_state, warnings = StateUpdater.apply(
            state,
            {"location": "网吧", "inventory_add": ["打火机"]},
            sm,
        )
        assert new_state.location == "网吧"
        assert "打火机" in new_state.inventory
        assert new_state.turn_count == 1

    def test_apply_returns_warnings(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        _, sid, state = sm.create_player("现代都市", {"name": "张三"})

        _, warnings = StateUpdater.apply(
            state,
            {"relationship_changes": {"路人": {"level": "亲密"}}},
            sm,
        )
        assert len(warnings) == 1
        assert "跨级跃迁" in warnings[0]

    def test_apply_history_appended(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        _, sid, state = sm.create_player("现代都市", {"name": "张三"})

        new_state, _ = StateUpdater.apply(
            state,
            {"location": "便利店"},
            sm,
        )
        assert new_state.turn_count == 1
        assert new_state.location == "便利店"
