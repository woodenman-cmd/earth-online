import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from src.engine.client import (
    AIClient,
    AIClientError,
    AuthError,
    RateLimitError,
    ServerError,
    TimeoutError,
)

RAW_RESPONSE = (
    "*周五·黄昏·老城区的天桥上*\n\n"
    "路灯啪地一声亮了...\n\n"
    "你感到一阵疲惫...\n\n"
    "①去吧台 ②转转脖子 ③靠墙歇会儿\n\n"
    '{"narrative": "...", "options": ["..."], "state_changes": {...}}'
)


def _make_mock_response(content: str) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    type(mock_resp).choices = PropertyMock(return_value=[mock_choice])
    return mock_resp


@pytest.fixture
def mock_openai():
    with patch("src.engine.client.OpenAI") as mock_cls:
        yield mock_cls


@pytest.fixture
def client(mock_openai):
    c = AIClient(api_key="sk-test")
    mock_openai.return_value.chat.completions.create = MagicMock()
    return c


class TestAIClientInit:
    def test_missing_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("src.engine.client.load_dotenv", return_value=None):
                with pytest.raises(AuthError, match="DEEPSEEK_API_KEY"):
                    AIClient(api_key="")

    def test_explicit_api_key_works(self, mock_openai):
        c = AIClient(api_key="sk-explicit")
        assert c._client is not None

    def test_custom_base_url(self, mock_openai):
        c = AIClient(api_key="sk-test", base_url="https://custom.api/v1")
        assert mock_openai.call_args[1]["base_url"] == "https://custom.api/v1"


class TestAIClientCall:
    def test_returns_raw_string(self, client):
        """AI 返回混合文本（叙事 + JSON），AIClient 原样返回字符串。"""
        client._client.chat.completions.create.return_value = _make_mock_response(
            RAW_RESPONSE
        )
        result = client.call("去吧台点杯东西")
        assert isinstance(result, str)
        assert "老城区的天桥上" in result
        assert '"narrative"' in result

    def test_returns_empty_string_on_none_content(self, client):
        """content 为 None → 返回空字符串。"""
        mock_msg = MagicMock()
        mock_msg.content = None
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        type(mock_resp).choices = PropertyMock(return_value=[mock_choice])
        client._client.chat.completions.create.return_value = mock_resp

        result = client.call("测试")
        assert result == ""

    def test_returns_empty_string_on_empty_content(self, client):
        """AI 返回空内容。"""
        client._client.chat.completions.create.return_value = _make_mock_response("")
        result = client.call("测试")
        assert result == ""

    def test_no_json_parsing_performed(self, client):
        """AIClient 不尝试解析 JSON——即使内容是纯 JSON 也照样返回字符串。"""
        pure_json = '{"a": 1}'
        client._client.chat.completions.create.return_value = _make_mock_response(
            pure_json
        )
        result = client.call("测试")
        assert result == pure_json
        assert isinstance(result, str)


class TestAIClientErrorTranslation:
    def test_auth_error(self, mock_openai):
        from openai import AuthenticationError

        c = AIClient(api_key="sk-test")
        c._client.chat.completions.create.side_effect = AuthenticationError(
            "invalid", response=MagicMock(), body=None
        )
        with pytest.raises(AuthError, match="API key 无效"):
            c.call("测试")

    def test_rate_limit_error(self, mock_openai):
        from openai import RateLimitError as OpenAIRateLimitError

        c = AIClient(api_key="sk-test")
        c._client.chat.completions.create.side_effect = OpenAIRateLimitError(
            "limited", response=MagicMock(), body=None
        )
        with pytest.raises(RateLimitError, match="限流"):
            c.call("测试")

    def test_server_error(self, mock_openai):
        from openai import InternalServerError

        c = AIClient(api_key="sk-test")
        c._client.chat.completions.create.side_effect = InternalServerError(
            "server error", response=MagicMock(), body=None
        )
        with pytest.raises(ServerError, match="内部错误"):
            c.call("测试")

    def test_timeout_error(self, mock_openai):
        from openai import APITimeoutError

        c = AIClient(api_key="sk-test")
        c._client.chat.completions.create.side_effect = APITimeoutError(
            "timed out"
        )
        with pytest.raises(TimeoutError, match="超时"):
            c.call("测试")

    def test_unexpected_error(self, mock_openai):
        c = AIClient(api_key="sk-test")
        c._client.chat.completions.create.side_effect = ValueError("unknown")
        with pytest.raises(AIClientError, match="未预期的 API 错误"):
            c.call("测试")
