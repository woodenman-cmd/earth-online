import json
from typing import Optional, Tuple

from src.core.state import PlayerState, LEVEL_INDEX
from src.utils.path import data_path

_JSON_PROTOCOL = """

## 输出协议（引擎专用，不在玩家可见的叙事中展示）

在回复的**最后**，附加一段 JSON，用三引号包裹：

```json
{
  "narrative": "此处填写完整的叙事文本（包含①~④结构）",
  "options": ["选项1", "选项2", "选项3"],
  "state_changes": {
    "location": "新位置名（如果地点变了才填）",
    "time": "当前时间描述，如'黄昏·19:15'（只在时间明显推移时填写）",
    "inventory_add": ["获得的新物品"],
    "inventory_remove": ["失去的物品"],
    "relationship_changes": {
      "NPC名": {
        "level": "新的关系层级（冷淡/认识/友好/信任/亲密，只在层级变化时填写）",
        "progress": 0.0 本回合新增的好感度增量（0.0~1.0之间的小数，属于该NPC的新增量值，不是累加后的总值。通常0.05-0.2为轻微波动，0.2-0.4为显著变化）
      }
    }
  }
}
```

规则：
1. narrative 必须包含 ① 当前场景/时间感、② 环境与氛围、③ 角色状态与感知、④ 行动选项列表
2. state_changes 只输出**本回合发生了变化的字段**。没有变化的字段不要出现在 JSON 里
3. 所有值必须和叙事内容一致——如果叙事里没提到捡了东西，inventory_add 就别填
4. options 不得少于 2 项，通常是 3-4 项
5. relationship_changes 中的 progress 是【本回合新增值】，不是累积值。例如：玩家帮了张宇一个忙 → "progress": 0.15
"""


class ContextBuilder:
    """组装主叙事 Prompt。读 prompt.md 为规则基底，注入引擎输出协议，拼接状态和历史。"""

    def __init__(self, prompt_path: Optional[str] = None):
        prompt_path = prompt_path or data_path("prompt.md")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_prompt = f.read()

    @staticmethod
    def _format_state_summary(state: PlayerState) -> str:
        parts = [
            f"玩家姓名：{state.name}",
            f"性别：{state.gender}",
            f"年龄：{state.age}",
            f"外貌：{state.appearance}",
            f"家庭背景：{state.background}",
            f"天赋：{state.talent}",
            f"游戏模式：{state.mode}",
            f"当前时间：{state.time or '未设定'}",
            f"当前位置：{state.location or '未设定'}",
        ]

        style_hint = {
            "理性分析": "叙述倾向于逻辑推演、客观分析和概率判断",
            "感性直觉": "叙述倾向于情绪渲染、氛围感知和共情理解",
            "圆滑机变": "叙述倾向于察言观色、人际博弈和弦外之音",
            "直率果决": "叙述倾向于行动优先、简洁果断和身体感知",
        }
        parts.append(
            f"处世风格：{state.style}"
            f"（{style_hint.get(state.style, '')}。"
            f"注意：任何情况下不得在叙事中直接使用处世风格名称作为副词，"
            f"如'你理性地想到''你圆滑地回应'等。风格必须完全通过措辞倾向自然呈现。）"
        )

        if state.inventory:
            parts.append(f"随身物品：{'、'.join(state.inventory)}")
        else:
            parts.append("随身物品：无")

        if state.relationships:
            rel_parts = []
            for npc_name, rel in state.relationships.items():
                rel_parts.append(
                    f"{npc_name}（{rel.level}，进度{rel.progress:.2f}）"
                )
            parts.append(f"人际关系：{'、'.join(rel_parts)}")
        else:
            parts.append("人际关系：暂无")
        parts.append(f"当前回合数：{state.turn_count}")
        return "\n".join(parts)

    @staticmethod
    def _format_history(state: PlayerState) -> str:
        if not state.history:
            return "（这是游戏的第一回合，还没有历史记录。）"

        lines = ["以下是最近几轮的剧情摘要（按时间从旧到新排列）："]
        reversed_history = list(reversed(state.history))
        for i, entry in enumerate(reversed_history, 1):
            lines.append(f"第{i}轮——")
            lines.append(f"玩家输入：{entry.player_input}")
            lines.append(f"系统叙事：{entry.narrative}")
        return "\n".join(lines)

    def build(
        self,
        player_state: PlayerState,
        player_input: str,
    ) -> tuple[str, str]:
        """返回 (system_prompt, user_prompt)。"""
        system = (
            f"{self._system_prompt}\n"
            f"{_JSON_PROTOCOL}\n"
            "【JSON 格式】回复末尾用 ```json 代码块输出 JSON。"
            "必须包含 narrative、options、state_changes。花括号只写单层 { 和 }。"
            "叙事中不得使用 ① ② ③ ④ 等编号——选项仅出现在 JSON 的 options 数组中。"
        )
        state_section = self._format_state_summary(player_state)
        history_section = self._format_history(player_state)

        user = (
            f"【系统指令】模式选择与角色创建已完成，当前处于剧情推进阶段。"
            f"直接从「第三步游戏开始」生成初始场景叙事。\n\n"
            f"## 当前玩家状态\n\n{state_section}\n\n"
            f"## 剧情历史\n\n{history_section}\n\n"
            f"## 玩家输入\n\n{player_input}\n\n"
            "【叙事节奏】低密度场景压缩到 1 轮，用时间跳跃一笔带过。"
            "不为琐碎动作停顿给选项。每轮 narrative 不少于 600 字。"
        )
        return system, user
