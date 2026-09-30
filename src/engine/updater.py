import json
import os
from typing import Optional

from src.core.state import (
    PlayerState,
    StateDelta,
    LEVEL_INDEX,
    RELATIONSHIP_LEVELS,
)

VALID_STATE_FIELDS = frozenset({
    "location", "time",
    "inventory_add", "inventory_remove",
    "relationship_changes",
})


class StateUpdater:
    """AI 状态变更 → StateDelta 的翻译器 + 硬约束校验层。

    核心翻译：
    - AI 输出的 progress 是【增量】，转换为 StateDelta 的【绝对 progress】
    - AI 输出的 level 是【目标层级】，校验跨级跃迁

    硬约束：
    - 跨级关系跃迁（冷淡→信任 = +3）→ 标记异常，暂记录警告后放行（AI 复核待实现）
    - 非法字段名 → 静默丢弃
    """

    @staticmethod
    def build_delta(
        current_state: PlayerState,
        state_changes: dict,
    ) -> tuple[StateDelta, list[str]]:
        """
        Returns:
            (StateDelta, 异常警告列表)
        """
        warnings: list[str] = []
        delta = StateDelta()

        if not isinstance(state_changes, dict):
            return delta, warnings

        for field, value in state_changes.items():
            if field == "location" and isinstance(value, str) and value:
                delta.location = value
            elif field == "time" and isinstance(value, str) and value:
                delta.time = value
            elif field == "inventory_add" and isinstance(value, list):
                delta.inventory_add = [str(v) for v in value if v]
            elif field == "inventory_remove" and isinstance(value, list):
                delta.inventory_remove = [str(v) for v in value if v]
            elif field == "relationship_changes" and isinstance(value, dict):
                rel_warnings = StateUpdater._process_relationships(
                    current_state, value, delta
                )
                warnings.extend(rel_warnings)
            elif field not in VALID_STATE_FIELDS:
                # 未知字段：静默丢弃
                pass

        return delta, warnings

    @staticmethod
    def _process_relationships(
        current_state: PlayerState,
        raw_changes: dict,
        delta: StateDelta,
    ) -> list[str]:
        warnings: list[str] = []

        for npc_name, change in raw_changes.items():
            if not isinstance(change, dict):
                continue

            current_rel = current_state.relationships.get(npc_name)
            current_level = current_rel.level if current_rel else "冷淡"
            current_progress = current_rel.progress if current_rel else 0.0

            rel_delta: dict = {}

            # --- level ---
            if "level" in change:
                new_level = change["level"]
                if new_level in RELATIONSHIP_LEVELS:
                    old_idx = LEVEL_INDEX[current_level]
                    new_idx = LEVEL_INDEX[new_level]
                    jump = new_idx - old_idx
                    if jump > 1:
                        warnings.append(
                            f"[跨级跃迁] {npc_name}: {current_level}→{new_level} "
                            f"(跳了 {jump} 级)。暂放行，需 AI 复核。"
                        )
                    rel_delta["level"] = new_level
                    # 层级变化时重置 progress
                    rel_delta["progress"] = 0.1

            # --- progress (AI 输出的是增量) ---
            if "progress" in change and "level" not in rel_delta:
                try:
                    increment = float(change["progress"])
                except (ValueError, TypeError):
                    continue
                if increment == 0:
                    continue
                absolute = current_progress + increment
                rel_delta["progress"] = absolute

            if rel_delta:
                delta.relationship_changes[npc_name] = rel_delta

        return warnings

    @staticmethod
    def apply(
        current_state: PlayerState,
        state_changes: dict,
        state_manager,
    ) -> tuple[PlayerState, list[str]]:
        """
        一站式：build_delta + apply。
        Args:
            current_state: 当前玩家状态
            state_changes: ResultParser 输出的原始 state_changes
            state_manager: StateManager 实例（用于 apply_delta）
        Returns:
            (新 PlayerState, 异常警告列表)
        """
        delta, warnings = StateUpdater.build_delta(current_state, state_changes)
        new_state = state_manager.apply_delta(
            current_state.player_id,
            current_state.session_id,
            delta,
        )
        return new_state, warnings
