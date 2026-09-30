import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class AIClientError(Exception):
    """所有 AI 客户端异常的基类。"""


class AuthError(AIClientError):
    """API key 无效 (401)。"""


class RateLimitError(AIClientError):
    """限流 (429)，重试耗尽。"""


class ServerError(AIClientError):
    """服务端故障 (5xx)，重试耗尽。"""


class TimeoutError(AIClientError):
    """请求超时。"""


class AIClient:
    """DeepSeek API 封装。只传管道，不解析内容。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise AuthError("DEEPSEEK_API_KEY 未设置")

        base_url = base_url or os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        )

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._timeout = timeout

    def call(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            self._translate_exception(e)
            raise

    @staticmethod
    def _translate_exception(exc: Exception) -> None:
        from openai import (
            AuthenticationError,
            RateLimitError as OpenAIRateLimitError,
            APITimeoutError,
            InternalServerError,
        )

        if isinstance(exc, AuthenticationError):
            raise AuthError(
                "API key 无效，请检查 DEEPSEEK_API_KEY 是否正确"
            ) from exc
        if isinstance(exc, OpenAIRateLimitError):
            raise RateLimitError(
                "API 限流，重试已耗尽，请稍后再试"
            ) from exc
        if isinstance(exc, APITimeoutError):
            raise TimeoutError(
                f"请求超时（{exc}），请检查网络连接"
            ) from exc
        if isinstance(exc, InternalServerError):
            raise ServerError(
                "DeepSeek 服务端内部错误，重试已耗尽"
            ) from exc

        raise AIClientError(f"未预期的 API 错误: {exc}") from exc
