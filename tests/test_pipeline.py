import json
import pytest
from unittest.mock import MagicMock, patch

from src.core.state import StateManager, PlayerState
from src.engine.client import AIClient, AuthError, RateLimitError, TimeoutError
from src.engine.parser import ParseError, FieldError
from src.engine.pipeline import GamePipeline, PipelineError

VALID_AI_RESPONSE = json.dumps({
    "narrative": "你推开网吧的玻璃门，烟雾扑面而来……\n\n你感到一阵疲惫。\n\n①去吧台 ②找张宇 ③坐下",
    "options": ["①去吧台", "②找张宇", "③找个空位坐下"],
    "state_changes": {"location": "网吧", "time": "黄昏·19:15"},
}, ensure_ascii=False)


def make_pipeline(tmp_path) -> tuple[GamePipeline, StateManager, MagicMock]:
    sm = StateManager(storage_dir=str(tmp_path))
    mock_ai = MagicMock(spec=AIClient)
    mock_ai.call.return_value = VALID_AI_RESPONSE
    pipeline = GamePipeline(sm, mock_ai)
    return pipeline, sm, mock_ai


@pytest.fixture
def pipeline_fixture(tmp_path):
    return make_pipeline(tmp_path)


class TestGamePipeline:
    def test_execute_happy_path(self, pipeline_fixture):
        pipeline, sm, mock_ai = pipeline_fixture
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        result = pipeline.execute(pid, sid, "去网吧")

        assert "你推开网吧" in result["narrative"]
        assert len(result["options"]) == 3
        assert result["turn"] == 1

    def test_execute_stores_state(self, pipeline_fixture):
        pipeline, sm, mock_ai = pipeline_fixture
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        pipeline.execute(pid, sid, "去网吧")
        state = sm.get_state(pid, sid)

        assert state.location == "网吧"
        assert state.time == "黄昏·19:15"
        assert state.turn_count == 1

    def test_execute_appends_history(self, pipeline_fixture):
        pipeline, sm, mock_ai = pipeline_fixture
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        pipeline.execute(pid, sid, "第一个动作")
        state = sm.get_state(pid, sid)
        assert len(state.history) == 1
        assert state.history[0].player_input == "第一个动作"

    def test_generate_opening(self, pipeline_fixture):
        pipeline, sm, mock_ai = pipeline_fixture
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        result = pipeline.generate_opening(pid, sid)

        assert result["turn"] == 1
        assert result["narrative"]
        assert result["options"]

    def test_execute_multiround(self, pipeline_fixture):
        pipeline, sm, mock_ai = pipeline_fixture
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        r1 = pipeline.execute(pid, sid, "回合1")
        assert r1["turn"] == 1

        r2 = pipeline.execute(pid, sid, "回合2")
        assert r2["turn"] == 2

        r3 = pipeline.execute(pid, sid, "回合3")
        assert r3["turn"] == 3


class TestPipelineErrors:
    def test_parse_error_recoverable(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        mock_ai = MagicMock(spec=AIClient)
        mock_ai.call.return_value = "这不是合法的 JSON 输出"
        pipeline = GamePipeline(sm, mock_ai)
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        with pytest.raises(PipelineError) as exc_info:
            pipeline.execute(pid, sid, "往前走")

        assert exc_info.value.recoverable is True
        assert "波动" in str(exc_info.value)

    def test_field_error_recoverable(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        mock_ai = MagicMock(spec=AIClient)
        mock_ai.call.return_value = json.dumps({
            "narrative": "", "options": ["①A", "②B"]
        })
        pipeline = GamePipeline(sm, mock_ai)
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        with pytest.raises(PipelineError) as exc_info:
            pipeline.execute(pid, sid, "走")


        assert exc_info.value.recoverable is True
        assert "波动" in str(exc_info.value)

    def test_auth_error_non_recoverable(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        mock_ai = MagicMock(spec=AIClient)
        mock_ai.call.side_effect = AuthError("bad key")
        pipeline = GamePipeline(sm, mock_ai)
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        with pytest.raises(PipelineError) as exc_info:
            pipeline.execute(pid, sid, "走")


        assert exc_info.value.recoverable is False

    def test_rate_limit_error_recoverable(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        mock_ai = MagicMock(spec=AIClient)
        mock_ai.call.side_effect = RateLimitError("rate limited")
        pipeline = GamePipeline(sm, mock_ai)
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        with pytest.raises(PipelineError) as exc_info:
            pipeline.execute(pid, sid, "走")


        assert exc_info.value.recoverable is True
        assert "服务繁忙" in str(exc_info.value)

    def test_timeout_error_recoverable(self, tmp_path):
        sm = StateManager(storage_dir=str(tmp_path))
        mock_ai = MagicMock(spec=AIClient)
        mock_ai.call.side_effect = TimeoutError("timed out")
        pipeline = GamePipeline(sm, mock_ai)
        pid, sid, _ = sm.create_player("现代都市", {"name": "张三"})

        with pytest.raises(PipelineError) as exc_info:
            pipeline.execute(pid, sid, "走")


        assert exc_info.value.recoverable is True
        assert "超时" in str(exc_info.value)

    def test_parse_error_does_not_change_state(self, tmp_path):
        """解析失败时状态不变。"""
        sm = StateManager(storage_dir=str(tmp_path))
        mock_ai = MagicMock(spec=AIClient)
        mock_ai.call.return_value = "纯文本，没有 JSON"
        pipeline = GamePipeline(sm, mock_ai)
        pid, sid, state = sm.create_player("现代都市", {"name": "张三"})

        try:
            pipeline.execute(pid, sid, "走")
        except PipelineError:
            pass

        state = sm.get_state(pid, sid)
        assert state.turn_count == 0  # 没变


class TestResolveOption:
    """测试选项编号解析逻辑（原在 main.py 中的函数）。"""

    @staticmethod
    def resolve(player_input: str, options: list[str]) -> str:
        stripped = player_input.strip()
        if stripped.isdigit():
            idx = int(stripped) - 1
            if 0 <= idx < len(options):
                return options[idx]
        return player_input

    def test_valid_number(self):
        options = ["①去吧台", "②找张宇", "③坐下"]
        assert self.resolve("2", options) == "②找张宇"

    def test_valid_number_boundary(self):
        options = ["①A", "②B", "③C"]
        assert self.resolve("1", options) == "①A"
        assert self.resolve("3", options) == "③C"

    def test_out_of_range(self):
        options = ["①A", "②B"]
        assert self.resolve("5", options) == "5"

    def test_zero(self):
        options = ["①A", "②B"]
        assert self.resolve("0", options) == "0"

    def test_free_text(self):
        options = ["①A", "②B"]
        assert self.resolve("我想去别的地方看看", options) == "我想去别的地方看看"

    def test_non_digit_string(self):
        options = ["①A", "②B"]
        assert self.resolve("abc", options) == "abc"
