import json
import re
from typing import Optional


class ParseError(Exception):
    """无法从 AI 回复中提取合法 JSON。"""


class FieldError(ParseError):
    """JSON 解析成功，但缺少必要字段或类型错误。"""


class ResultParser:
    """从 AI 返回的混合文本中提取 JSON，拆分为 narrative / options / state_changes。

    提取策略（按优先级）：
    ① 正则匹配 ```json ... ``` 或 ``` ... ``` 代码块，内部严格解析
    ② 代码块内解析失败 → 对内容做 JSON 修复后重试
    ③ 无代码块 → 在全文所有 { 位置尝试解码
    ④ 全部失败 → 正则降级兜底，从自由文本中提取 narrative + options
    """

    _CODE_BLOCK_RE = re.compile(
        r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
    )

    _TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")

    _BRACKET_STRIP_RE = re.compile(r"^[^{]*|[^}]*$")

    _OPTIONS_LIST_RE = re.compile(
        r"options\s*:?\s*\[(.*?)\]", re.DOTALL
    )

    _OPTION_LINES_RE = re.compile(
        r'"([^"]+)"'
    )

    _NARRATIVE_KEY_RE = re.compile(
        r'"narrative"\s*:\s*"', re.DOTALL
    )

    def parse(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            raise ParseError("AI 返回了空内容")

        data = self._extract_json(raw_text)
        return self._split_fields(data)

    # ── JSON 提取 ────────────────────────────────────────

    def _extract_json(self, raw_text: str) -> dict:
        """逐层尝试：严格解析 → 修复解析 → 正则降级。"""
        decoder = json.JSONDecoder()

        # 策略①：从代码块提取
        if "```" in raw_text:
            blocks = list(self._CODE_BLOCK_RE.finditer(raw_text))
            for match in reversed(blocks):
                inner = match.group(1).strip()
                data = self._try_strict_decode(decoder, inner)
                if data is not None:
                    return data
                data = self._try_repair_decode(decoder, inner)
                if data is not None:
                    return data

        # 策略②：从全文 { 位置尝试
        positions = self._find_brace_starts(raw_text)
        for pos in positions:
            data = self._try_strict_decode(decoder, raw_text[pos:])
            if data is not None:
                return data
            data = self._try_repair_decode(decoder, raw_text[pos:])
            if data is not None:
                return data

        # 策略③：降级到正则兜底
        data = self._regex_fallback(raw_text)
        if data is not None:
            return data

        raise ParseError(
            "无法从 AI 回复中提取合法 JSON。"
            f"末尾 200 字符: ...{raw_text[-200:]}"
        )

    # ── 严格解码 ─────────────────────────────────────────

    @staticmethod
    def _try_strict_decode(decoder: json.JSONDecoder, text: str) -> Optional[dict]:
        try:
            obj = decoder.raw_decode(text)[0]
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        if "narrative" not in obj and "options" not in obj:
            return None
        return obj

    # ── 修复解码 ─────────────────────────────────────────

    @staticmethod
    def _try_repair_decode(decoder: json.JSONDecoder, text: str) -> Optional[dict]:
        repaired = ResultParser._repair_json_text(text)
        if repaired is None:
            return None
        try:
            obj = decoder.raw_decode(repaired)[0]
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        if "narrative" not in obj and "options" not in obj:
            return None
        return obj

    @staticmethod
    def _repair_json_text(text: str) -> Optional[str]:
        """对破损 JSON 应用一组修复策略，返回修复后的文本，或 None。"""
        s = text.strip()
        if not s:
            return None

        # ① 截取从第一个 { 到最后一个 } 的范围
        first_brace = s.find("{")
        if first_brace == -1:
            return None
        last_brace = s.rfind("}")
        if last_brace == -1 or first_brace >= last_brace:
            # 无闭合花括号 → 取到末尾，稍后补齐
            s = s[first_brace:]
        else:
            s = s[first_brace:last_brace + 1]

        # ② 去尾逗号: ,}  ,]
        s = ResultParser._TRAILING_COMMA_RE.sub(r"\1", s)

        # ③ 尝试修复 JSON 字符串内的裸换行（将值中的真实换行替换为 \n）
        s = ResultParser._fix_naked_newlines_in_strings(s)

        # ④ 缺闭合花括号？尝试补齐
        open_count = s.count("{") - s.count("}")
        if open_count > 0:
            s += "}" * open_count

        return s if s else None

    @staticmethod
    def _fix_naked_newlines_in_strings(text: str) -> str:
        """将 JSON 字符串值内的真实换行替换为 \\n 转义序列。
        仅处理 \r\n 和 \n，跳过已经是被转义的反斜杠-n。"""
        result = []
        in_string = False
        escape = False
        i = 0
        while i < len(text):
            ch = text[i]
            if escape:
                result.append(ch)
                escape = False
                i += 1
                continue
            if ch == "\\":
                result.append(ch)
                escape = True
                i += 1
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                i += 1
                continue
            if in_string:
                if ch == "\r" and i + 1 < len(text) and text[i + 1] == "\n":
                    result.append("\\n")
                    i += 2
                    continue
                if ch == "\n":
                    result.append("\\n")
                    i += 1
                    continue
                if ch == "\t":
                    result.append("\\t")
                    i += 1
                    continue
            result.append(ch)
            i += 1
        return "".join(result)

    # ── 正则降级兜底 ─────────────────────────────────────

    @staticmethod
    def _regex_fallback(raw_text: str) -> Optional[dict]:
        """当 JSON 彻底无法解析时，尝试用正则从自由文本中提取
        narrative 和 options，state_changes 留空。"""
        narrative = ResultParser._extract_narrative_by_heuristic(raw_text)
        if narrative is None:
            return None

        options = ResultParser._extract_options_by_heuristic(raw_text)
        return {
            "narrative": narrative,
            "options": options,
            "state_changes": {},
        }

    @staticmethod
    def _extract_narrative_by_heuristic(text: str) -> Optional[str]:
        """尝试从破损 JSON 或自由文本中提取 narrative 字段的值。
        策略：找到 "narrative": " 之后，手动找闭合的 "。"""
        match = ResultParser._NARRATIVE_KEY_RE.search(text)
        if match is None:
            # 没有 "narrative" 键 → 尝试把 JSON 之外的内容当叙事
            stripped = ResultParser._BODY_OUTSIDE_JSON(text)
            if stripped and len(stripped) > 50:
                return stripped
            return None

        start = match.end()
        result = []
        escape = False
        for ch in text[start:]:
            if escape:
                if ch in ('"', "\\", "n", "t", "r"):
                    result.append({"n": "\n", "t": "\t", "r": "\r"}.get(ch, ch))
                else:
                    result.append(ch)
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                break
            result.append(ch)

        narrative = "".join(result)
        return narrative if len(narrative) >= 10 else None

    @staticmethod
    def _extract_options_by_heuristic(text: str) -> list[str]:
        """从文本中提取 options 列表。"""
        match = ResultParser._OPTIONS_LIST_RE.search(text)
        if match is None:
            return ["继续探险", "稍作休息"]
        inner = match.group(1)
        items = ResultParser._OPTION_LINES_RE.findall(inner)
        items = [item.strip() for item in items if item.strip()]
        if len(items) < 2:
            lines = [line.strip() for line in inner.split(",") if line.strip()]
            items = [line.strip(' "') for line in lines if len(line) > 2]
        return items if len(items) >= 2 else ["继续前进", "换个方向"]

    @staticmethod
    def _BODY_OUTSIDE_JSON(text: str) -> Optional[str]:
        """提取 JSON 代码块之外的正文内容。"""
        # 去掉代码块
        body = ResultParser._CODE_BLOCK_RE.sub("", text)
        # 去掉残留的 JSON 结构
        body = re.sub(r'[{}\[\]]', "", body)
        body = re.sub(r'"[a-z_]+":', "", body)
        # 压缩多余空行
        body = re.sub(r"\n{3,}", "\n\n", body)
        result = body.strip()
        return result if len(result) > 50 else None

    # ── 工具 ─────────────────────────────────────────────

    @staticmethod
    def _find_brace_starts(text: str) -> list[int]:
        positions = []
        for i, ch in enumerate(text):
            if ch == "{":
                positions.append(i)
        return positions

    # ── 字段拆分 ─────────────────────────────────────────

    @staticmethod
    def _split_fields(data: dict) -> dict:
        narrative = data.get("narrative", "")
        if not narrative or not isinstance(narrative, str):
            raise FieldError(f"缺少 narrative 字段或类型错误: {type(narrative).__name__}")

        options = data.get("options", [])
        if not isinstance(options, list) or len(options) < 2:
            raise FieldError(
                f"options 必须是不少于 2 项的列表，"
                f"得到 {len(options) if isinstance(options, list) else type(options).__name__}"
            )
        for i, opt in enumerate(options):
            if not isinstance(opt, str) or not opt.strip():
                raise FieldError(f"options[{i}] 必须是有效字符串，得到: {repr(opt)}")

        state_changes = data.get("state_changes", {})
        if not isinstance(state_changes, dict):
            state_changes = {}

        return {
            "narrative": narrative,
            "options": options,
            "state_changes": state_changes,
        }
