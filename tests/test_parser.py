import json
import pytest
from src.engine.parser import ResultParser, ParseError, FieldError

VALID_NARRATIVE = ("*周五·黄昏·老城区的天桥上*\n\n"
                   "路灯啪地一声亮了。行道树的影子被拉得像栅栏一样长...\n\n"
                   "你感到一阵疲惫，中午就没吃东西。\n\n"
                   "①去桥下买个烤红薯 ②靠着栏杆多站一会儿 ③掏出手机")

VALID_JSON = {
    "narrative": VALID_NARRATIVE,
    "options": [
        "①去桥下买个烤红薯，顺便问问小贩",
        "②靠着栏杆多站一会儿，让脑子冷静",
        "③掏出手机翻翻未读消息",
    ],
    "state_changes": {
        "time": "黄昏·19:30",
        "location": "老城区·天桥",
    },
}


def raw_with_json_at_end() -> str:
    return VALID_NARRATIVE + "\n\n" + json.dumps(VALID_JSON, ensure_ascii=False)


def raw_with_code_block() -> str:
    return (
        VALID_NARRATIVE
        + "\n\n```json\n"
        + json.dumps(VALID_JSON, ensure_ascii=False)
        + "\n```"
    )


def raw_with_code_block_no_lang() -> str:
    return (
        VALID_NARRATIVE
        + "\n\n```\n"
        + json.dumps(VALID_JSON, ensure_ascii=False)
        + "\n```"
    )


@pytest.fixture
def parser():
    return ResultParser()


class TestHappyPath:
    def test_json_at_end_of_text(self, parser):
        result = parser.parse(raw_with_json_at_end())
        assert result["narrative"] == VALID_NARRATIVE
        assert len(result["options"]) == 3
        assert result["state_changes"]["time"] == "黄昏·19:30"

    def test_json_in_code_block(self, parser):
        result = parser.parse(raw_with_code_block())
        assert result["narrative"] == VALID_NARRATIVE
        assert result["options"][0] == VALID_JSON["options"][0]

    def test_json_in_code_block_no_lang_tag(self, parser):
        result = parser.parse(raw_with_code_block_no_lang())
        assert result["narrative"] == VALID_NARRATIVE

    def test_pure_json_no_narrative_text(self, parser):
        result = parser.parse(json.dumps(VALID_JSON, ensure_ascii=False))
        assert result["narrative"] == VALID_NARRATIVE

    def test_state_changes_missing_defaults_to_empty(self, parser):
        json_missing_field = {
            "narrative": "叙事...",
            "options": ["①去吧台", "②离开"],
        }
        result = parser.parse(json.dumps(json_missing_field, ensure_ascii=False))
        assert result["state_changes"] == {}


class TestJsonExtractionEdgeCases:
    def test_no_json_in_response(self, parser):
        with pytest.raises(ParseError, match="无法从 AI 回复中提取"):
            parser.parse("只有一段普通的叙事文本，没有任何 JSON。")

    def test_empty_string(self, parser):
        with pytest.raises(ParseError, match="空内容"):
            parser.parse("")

    def test_whitespace_only(self, parser):
        with pytest.raises(ParseError, match="空内容"):
            parser.parse("   \n\t  ")

    def test_multiple_code_blocks_last_wins(self, parser):
        first_json = {"narrative": "第一段", "options": ["①A", "②B"]}
        text = (
            "```json\n" + json.dumps(first_json) + "\n```\n"
            + "中间叙事...\n"
            + "```json\n" + json.dumps(VALID_JSON, ensure_ascii=False) + "\n```"
        )
        result = parser.parse(text)
        assert result["narrative"] == VALID_NARRATIVE

    def test_json_inside_nested_braces(self, parser):
        """JSON 中包含嵌套对象，如 {"a": {"b": 1}}。"""
        nested = {
            "narrative": "深层次的叙事",
            "options": ["①深入", "②浅出"],
            "state_changes": {"nested": {"key": "value"}},
        }
        raw = "叙事文本\n" + json.dumps(nested, ensure_ascii=False)
        result = parser.parse(raw)
        assert result["state_changes"]["nested"]["key"] == "value"

    def test_braces_in_string_values(self, parser):
        """JSON 字符串值中包含花括号，如 "text": "hello {world}"。"""
        data = {
            "narrative": "墙上有刻字: {hello}",
            "options": ["①走近看 {刻字}", "②离开"],
            "state_changes": {},
        }
        raw = "叙事\n" + json.dumps(data, ensure_ascii=False)
        result = parser.parse(raw)
        assert "{hello}" in result["narrative"]

    def test_extra_text_after_json(self, parser):
        raw = json.dumps(VALID_JSON, ensure_ascii=False) + "\n以上是系统的回复。"
        result = parser.parse(raw)
        assert result["narrative"] == VALID_NARRATIVE

    def test_chinese_text_before_json(self, parser):
        result = parser.parse(raw_with_json_at_end())
        assert "老城区的天桥上" in result["narrative"]

    def test_truncated_json(self, parser):
        with pytest.raises(ParseError, match="无法从 AI 回复中提取"):
            parser.parse('叙事\n{"narrative": "不完整的')

    def test_multiple_braces_in_narrative(self, parser):
        """叙事文本中本身有花括号（如对话），JSON 在末尾。"""
        text = (
            "你听到有人说：{'key': 'value'}。那是一个奇怪的句子。\n\n"
            + json.dumps(VALID_JSON, ensure_ascii=False)
        )
        result = parser.parse(text)
        assert result["narrative"] == VALID_NARRATIVE


class TestFieldValidation:
    def test_missing_narrative(self, parser):
        with pytest.raises(FieldError, match="narrative"):
            parser.parse(json.dumps({"options": ["①A", "②B"]}))

    def test_empty_narrative_string(self, parser):
        with pytest.raises(FieldError, match="narrative"):
            parser.parse(json.dumps({"narrative": "", "options": ["①A", "②B"]}))

    def test_narrative_is_number(self, parser):
        with pytest.raises(FieldError, match="narrative"):
            parser.parse(json.dumps({"narrative": 123, "options": ["①A", "②B"]}))

    def test_missing_options(self, parser):
        with pytest.raises(FieldError, match="options"):
            parser.parse(json.dumps({"narrative": "叙事..."}))

    def test_options_not_a_list(self, parser):
        with pytest.raises(FieldError, match="options"):
            parser.parse(json.dumps({
                "narrative": "叙事",
                "options": "这不是列表",
            }))

    def test_options_too_few(self, parser):
        with pytest.raises(FieldError, match="不少于 2 项"):
            parser.parse(json.dumps({
                "narrative": "叙事",
                "options": ["①唯一的选项"],
            }))

    def test_options_contain_non_string(self, parser):
        with pytest.raises(FieldError, match="有效字符串"):
            parser.parse(json.dumps({
                "narrative": "叙事",
                "options": ["①可以", 42, "③还行"],
            }))

    def test_options_contain_empty_string(self, parser):
        with pytest.raises(FieldError, match="有效字符串"):
            parser.parse(json.dumps({
                "narrative": "叙事",
                "options": ["①好", "   ", "③也行"],
            }))

    def test_state_changes_is_list_falls_back(self, parser):
        result = parser.parse(json.dumps({
            "narrative": "叙事",
            "options": ["①A", "②B"],
            "state_changes": [1, 2, 3],
        }))
        assert result["state_changes"] == {}


# ═══════════════════════════════════════════════════════════
#  对抗性测试 — 模拟真实 AI 输出中的各种破损 JSON
# ═══════════════════════════════════════════════════════════

class TestJsonRepair:
    """验证 JSON 修复层能否纠正 LLM 的常见格式错误。"""

    def test_trailing_comma_before_brace(self, parser):
        raw = '{\n  "narrative": "测试叙事",\n  "options": ["①A", "②B"],\n}'
        result = parser.parse(raw)
        assert result["narrative"] == "测试叙事"
        assert len(result["options"]) == 2

    def test_trailing_comma_in_nested_object(self, parser):
        raw = (
            '{\n  "narrative": "测试",\n  "options": ["①A", "②B"],\n'
            '  "state_changes": {"location": "酒吧",}\n}'
        )
        result = parser.parse(raw)
        assert result["state_changes"]["location"] == "酒吧"

    def test_trailing_comma_in_array(self, parser):
        raw = '{"narrative": "测试", "options": ["①A", "②B",]}'
        result = parser.parse(raw)
        assert len(result["options"]) == 2

    def test_real_newline_inside_narrative_value(self, parser):
        raw = '{\n  "narrative": "第一行\n第二行\n第三行",\n  "options": ["①继续", "②停下"]\n}'
        result = parser.parse(raw)
        assert "第一行" in result["narrative"]
        assert "第三行" in result["narrative"]

    def test_windows_crlf_inside_narrative(self, parser):
        raw = '{\n  "narrative": "第一行\r\n第二行",\n  "options": ["①A", "②B"]\n}'
        result = parser.parse(raw)
        assert "第一行" in result["narrative"]

    def test_escaped_newline_kept_intact(self, parser):
        """\\n 转义序列不应被二次转义。"""
        valid = json.dumps({
            "narrative": "第一行\\n第二行",
            "options": ["①A", "②B"],
        }, ensure_ascii=False)
        result = parser.parse(valid)
        assert "第一行\\n第二行" == result["narrative"]

    def test_escaped_quote_inside_narrative(self, parser):
        valid = json.dumps({
            "narrative": '他说\\"你好\\"',
            "options": ["①A", "②B"],
        }, ensure_ascii=False)
        result = parser.parse(valid)
        assert result["narrative"] == '他说\\"你好\\"'

    def test_text_before_brace_is_stripped(self, parser):
        raw = '以下是系统的 JSON 输出：\n\n{"narrative": "测试叙事", "options": ["①A", "②B"]}\n\n以上。'
        result = parser.parse(raw)
        assert result["narrative"] == "测试叙事"

    def test_chinese_colon_variation_in_text(self, parser):
        data = {
            "narrative": "你说：好的，我明白了。然后转身离开。",
            "options": ["①追上去", "②站在原地"],
        }
        raw = json.dumps(data, ensure_ascii=False)
        result = parser.parse(raw)
        assert "好的" in result["narrative"]


class TestRegexFallback:
    """验证 JSON 彻底不可解析时的正则降级兜底。"""

    def test_no_braces_pure_narrative(self, parser):
        """纯叙事无 JSON → 正则兜底提取，不应报错。"""
        raw = (
            "你推开沉重的铁门，灰尘在光束中飞舞。"
            "这是一个被遗忘很久的地方。\n\n"
            "①进去看看 ②转身离开 ③先用手电筒照一照"
        )
        result = parser.parse(raw)
        assert "铁门" in result["narrative"]
        assert len(result["options"]) >= 2

    def test_narrative_key_present_but_brace_broken(self, parser):
        raw = '"narrative": "你走进房间，灯光昏黄。", "options": ["①四处查看", "②坐下休息"]'
        result = parser.parse(raw)
        assert "你走进房间" in result["narrative"]
        assert len(result["options"]) == 2
        assert result["state_changes"] == {}

    def test_narrative_and_options_in_free_text_fallback(self, parser):
        """JSON 花括号位置混乱，但 narrative 键仍可定位。"""
        raw = (
            '你看见 { 一个人影 { "narrative": "雾气弥漫的街道上，'
            '你隐约看到一个人影闪过。", "options": ["①追上去", "②原路返回", "③大声喊叫"], '
            ' "state_changes": {"location": "雾气街道"} } 在巷子尽头。'
        )
        result = parser.parse(raw)
        assert "雾气弥漫" in result["narrative"]
        assert len(result["options"]) == 3

    def test_single_option_fallback_generates_defaults(self, parser):
        """合法 JSON 但只有 1 个选项 → 字段校验阶段报 FieldError。"""
        raw = '{"narrative": "测试", "options": ["①唯一选项"]}'
        with pytest.raises(FieldError, match="不少于 2 项"):
            parser.parse(raw)

    def test_completely_broken_brace_narrative_still_extracted(self, parser):
        """最坏情况：花括号全错，但 narrative 键值可定位。"""
        raw = (
            "{ { {\n"
            '  "narrative": "暴雨中的城市，霓虹灯在水洼里碎成千万片。",\n'
            '  "options": ["①躲进便利店", "②冒雨狂奔"],\n'
            "} } }"
        )
        result = parser.parse(raw)
        assert "暴雨中的城市" in result["narrative"]


class TestFixNakedNewlines:
    """针对 _fix_naked_newlines_in_strings 的单元级测试。"""

    def test_simple_newline(self):
        fixed = ResultParser._fix_naked_newlines_in_strings('"line1\nline2"')
        assert '"line1\\nline2"' == fixed

    def test_already_escaped_unchanged(self):
        fixed = ResultParser._fix_naked_newlines_in_strings('"line1\\nline2"')
        assert '"line1\\nline2"' == fixed

    def test_tab_in_string(self):
        fixed = ResultParser._fix_naked_newlines_in_strings('"col1\tcol2"')
        assert '"col1\\tcol2"' == fixed

    def test_double_backslash_before_newline(self):
        """\\\\n 是字面反斜杠+字面n，不应被改动 \\n 部分。"""
        fixed = ResultParser._fix_naked_newlines_in_strings('"path\\\\nhere"')
        assert '"path\\\\nhere"' == fixed

    def test_outside_string_unchanged(self):
        fixed = ResultParser._fix_naked_newlines_in_strings('123\n456')
        assert '123\n456' == fixed

    def test_repaired_json_then_parsed(self, parser):
        """端到端：修复后能正常解析。"""
        raw = '{\n  "narrative": "第一段\n第二段\n第三段",\n  "options": ["①走", "②停"]\n}'
        result = parser.parse(raw)
        assert "第一段" in result["narrative"]
        assert "第三段" in result["narrative"]


class TestRepairJsonText:
    """针对 _repair_json_text 的单元测试。"""

    def test_no_braces_returns_none(self):
        assert ResultParser._repair_json_text("no braces here") is None

    def test_only_opening_brace(self, parser):
        """缺 } 应该能补全后解析成功。"""
        raw = '{"narrative": "测试短叙事", "options": ["①A", "②B"]'
        result = parser.parse(raw)
        assert result["narrative"] == "测试短叙事"
        assert len(result["options"]) == 2

    def test_empty_input(self):
        assert ResultParser._repair_json_text("") is None

    def test_braces_only_inside_string(self):
        """如果全文唯一的花括号在字符串内，仍应被裁切。"""
        # 这里 { 在字符串里，但仍然能找到
        text = '{"narrative": "他说{你好}", "options": ["a", "b"]}'
        result = ResultParser._repair_json_text(text)
        assert result is not None

    def test_mismatched_brace_count(self, parser):
        """缺一个 } 的情况：repair 现在会自动补全。"""
        raw = '{"narrative": "完整叙事", "options": ["①好的", "②不好"]'
        result = ResultParser._repair_json_text(raw)
        assert result is not None
        assert result.endswith("}")
        parsed = parser.parse(raw)
        assert parsed["narrative"] == "完整叙事"
        assert len(parsed["options"]) == 2
