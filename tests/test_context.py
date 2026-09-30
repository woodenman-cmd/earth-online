import pytest
from src.engine.context import ContextBuilder, _JSON_PROTOCOL
from src.core.state import PlayerState, Relationship, HistoryEntry


def make_state(**overrides) -> PlayerState:
    defaults = {
        "player_id": "pid01",
        "session_id": "sid01",
        "turn_count": 3,
        "name": "测试者",
        "gender": "男",
        "age": 25,
        "appearance": "戴眼镜，瘦高",
        "background": "普通工薪家庭",
        "talent": "过目不忘",
        "style": "理性分析",
        "mode": "现代都市",
        "location": "网吧",
        "time": "黄昏·19:00",
        "inventory": ["手机", "钱包"],
        "relationships": {},
        "history": [],
    }
    defaults.update(overrides)
    return PlayerState(**defaults)


def build(cb, state, inp):
    """便捷：返回 system 和 user 两部分。"""
    return cb.build(state, inp)


class TestContextBuilder:
    def test_init_reads_prompt_md(self):
        cb = ContextBuilder()
        assert "地球Online" in cb._system_prompt
        assert "叙事风格" in cb._system_prompt

    def test_build_returns_tuple_of_strings(self):
        cb = ContextBuilder()
        system, user = build(cb, make_state(), "去网吧")
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 500
        assert len(user) > 100

    def test_system_contains_rules_and_json_protocol(self):
        cb = ContextBuilder()
        system, user = build(cb, make_state(), "去网吧")
        assert "地球Online" in system
        assert '"narrative"' in system
        assert '"options"' in system
        assert '"state_changes"' in system

    def test_user_contains_state_and_history(self):
        cb = ContextBuilder()
        system, user = build(cb, make_state(), "去网吧找张宇")
        assert "当前玩家状态" in user
        assert "剧情历史" in user
        assert "玩家输入" in user
        assert "去网吧找张宇" in user

    def test_system_contains_no_state_data(self):
        cb = ContextBuilder()
        system, user = build(cb, make_state(name="张三"), "走")
        assert "张三" not in system

    def test_user_contains_player_name_and_style(self):
        cb = ContextBuilder()
        _, user = build(cb, make_state(name="张三", style="理性分析"), "向前")
        assert "张三" in user
        assert "处世风格" in user
        assert "逻辑推演" in user

    def test_user_contains_location_and_time(self):
        cb = ContextBuilder()
        _, user = build(cb, make_state(location="公司大楼", time="清晨·07:30"), "走")
        assert "公司大楼" in user
        assert "清晨·07:30" in user

    def test_user_contains_inventory(self):
        cb = ContextBuilder()
        _, user = build(cb, make_state(inventory=[]), "走")
        assert "随身物品：无" in user

        _, user = build(cb, make_state(inventory=["匕首", "地图"]), "走")
        assert "匕首" in user

    def test_user_contains_relationships(self):
        cb = ContextBuilder()
        state = make_state(relationships={
            "张宇": Relationship(level="友好", progress=0.5),
        })
        _, user = build(cb, state, "走")
        assert "张宇（友好，进度0.50）" in user

    def test_user_empty_relationships(self):
        cb = ContextBuilder()
        _, user = build(cb, make_state(relationships={}), "走")
        assert "人际关系：暂无" in user

    def test_history_chronological_order(self):
        cb = ContextBuilder()
        state = make_state(history=[
            HistoryEntry(player_input="动作3", narrative="叙事3", options_shown=[]),
            HistoryEntry(player_input="动作2", narrative="叙事2", options_shown=[]),
            HistoryEntry(player_input="动作1", narrative="叙事1", options_shown=[]),
        ])
        _, user = build(cb, state, "新输入")
        assert user.index("动作1") < user.index("动作2") < user.index("动作3")

    def test_history_empty(self):
        cb = ContextBuilder()
        _, user = build(cb, make_state(history=[]), "新输入")
        assert "第一回合" in user

    def test_turn_count_in_state(self):
        cb = ContextBuilder()
        _, user = build(cb, make_state(turn_count=42), "走")
        assert "当前回合数：42" in user

    def test_style_never_explicit_in_hint(self):
        cb = ContextBuilder()
        for style in ["理性分析", "感性直觉", "圆滑机变", "直率果决"]:
            _, user = build(cb, make_state(style=style), "走")
            assert "任何情况下不得在叙事中直接使用处世风格名称作为副词" in user
