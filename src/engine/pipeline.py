import os

from src.core.state import StateManager, PlayerState
from src.engine.client import (
    AIClient,
    AIClientError,
    AuthError,
    RateLimitError,
    TimeoutError,
)
from src.engine.context import ContextBuilder
from src.engine.parser import ResultParser, ParseError, FieldError
from src.engine.updater import StateUpdater


class PipelineError(Exception):
    """管线执行失败。携带可恢复标志。"""

    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


class GamePipeline:
    """完整回合管线：

    StateManager → ContextBuilder → AIClient → ResultParser → StateUpdater → StateManager
    """

    _PARSE_MAX_RETRIES = 1

    def __init__(self, state_manager: StateManager, ai_client: AIClient):
        self._sm = state_manager
        self._ai = ai_client
        self._ctx = ContextBuilder()
        self._parser = ResultParser()
        self._updater = StateUpdater()

    def execute(
        self,
        player_id: str,
        session_id: str,
        player_input: str,
    ) -> dict:
        state = self._sm.get_state(player_id, session_id)
        system_prompt, user_prompt = self._ctx.build(state, player_input)

        try:
            raw = self._ai.call(
                user_prompt, system_prompt=system_prompt, temperature=0.5
            )
        except AuthError as e:
            raise PipelineError(str(e), recoverable=False) from e
        except RateLimitError as e:
            raise PipelineError(f"服务繁忙: {e}", recoverable=True) from e
        except TimeoutError as e:
            raise PipelineError(f"请求超时: {e}", recoverable=True) from e
        except AIClientError as e:
            raise PipelineError(f"AI 调用失败: {e}", recoverable=True) from e

        parsed = self._try_parse(raw, retries=self._PARSE_MAX_RETRIES)
        delta, warnings = self._updater.build_delta(
            state, parsed["state_changes"]
        )
        delta.history_append = {
            "player_input": player_input,
            "narrative": parsed["narrative"],
            "options_shown": parsed["options"],
        }
        new_state = self._sm.apply_delta(player_id, session_id, delta)
        return {
            "narrative": parsed["narrative"],
            "options": parsed["options"],
            "turn": new_state.turn_count,
            "warnings": warnings,
        }

    def _try_parse(self, raw_text: str, retries: int = 0) -> dict:
        """三层降级：严格解析 → 修复解析 → 正则兜底 → AI 重试。"""
        try:
            return self._parser.parse(raw_text)
        except (ParseError, FieldError) as first_error:
            self._dump_debug(raw_text)
            if retries <= 0:
                raise PipelineError(
                    "系统出现短暂的波动，刚才的画面仿佛被什么东西干扰了一瞬。"
                    "你定了定神，一切恢复了正常。",
                    recoverable=True,
                ) from first_error

            retry_prompt = (
                f"你上一次输出的 JSON 格式有误，解析失败。\n"
                f"错误原因：{first_error}\n"
                f"原始输出末尾：...{raw_text[-500:]}\n\n"
                f"请严格按照 JSON 协议 **仅输出** 一份修正后的完整 JSON，"
                f"不要附加任何解释文字，不要添加 ``` 代码块标记。"
                f"特别注意：narrative 字段中的双引号必须转义为 \\\"，"
                f"换行必须写为 \\n。"
            )
            try:
                retry_raw = self._ai.call(
                    retry_prompt, temperature=0.3, max_tokens=4096
                )
            except AIClientError as e:
                raise PipelineError(
                    "系统出现短暂的波动，刚才的画面仿佛被什么东西干扰了一瞬。"
                    "你定了定神，一切恢复了正常。",
                    recoverable=True,
                ) from e

            try:
                return self._parser.parse(retry_raw)
            except (ParseError, FieldError) as second_error:
                self._dump_debug(retry_raw)
                raise PipelineError(
                    "系统出现短暂的波动，刚才的画面仿佛被什么东西干扰了一瞬。"
                    "你定了定神，一切恢复了正常。",
                    recoverable=True,
                ) from second_error

    @staticmethod
    def _dump_debug(raw_text: str):
        import logging
        import time
        logger = logging.getLogger("earth_online.parser")
        ts = int(time.time())
        path = f"storage/debug_response_{ts}.txt"
        os.makedirs("storage", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        logger.warning(f"JSON 解析失败，原始响应已保存至 {path}")

    def generate_opening(self, player_id: str, session_id: str) -> dict:
        """生成第一轮开场叙事。"""
        return self.execute(player_id, session_id, "（游戏开始）")
