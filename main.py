import os
import sys
from datetime import datetime
from src.core.state import StateManager
from src.engine.client import AIClient, AuthError
from src.engine.pipeline import GamePipeline, PipelineError

MODES = [
    "现代都市", "古代历史", "修仙玄幻", "末日生存",
    "娱乐圈养成", "荒野求生", "校园恋爱", "悬疑推理",
]
STYLES = {
    "1": "理性分析", "2": "感性直觉",
    "3": "圆滑机变", "4": "直率果决",
}


def choose_mode() -> str:
    print("\n选择一个世界：")
    for i, mode in enumerate(MODES, 1):
        print(f"  {i}. {mode}")
    while True:
        try:
            choice = int(input("\n> ").strip())
            if 1 <= choice <= 8:
                return MODES[choice - 1]
            print("请输入 1-8。")
        except ValueError:
            print("请输入数字。")


def create_character(pipeline: GamePipeline) -> dict:
    print("\n创建角色：")
    name = input("  姓名: ").strip() or "无名"
    gender = input("  性别 (男/女): ").strip() or "男"
    age_str = input("  年龄: ").strip() or "20"
    age = int(age_str) if age_str.isdigit() else 20
    appearance = input("  外貌: ").strip() or "普通"
    background = input("  家庭背景: ").strip() or "普通家庭"
    talent = input("  天赋: ").strip() or "无"

    print("\n处世风格：")
    for k, v in STYLES.items():
        print(f"  {k}. {v}")
    style_choice = input("\n> ").strip()
    style = STYLES.get(style_choice, "感性直觉")

    return {
        "name": name, "gender": gender, "age": age,
        "appearance": appearance, "background": background,
        "talent": talent, "style": style,
    }


def resolve_option(player_input: str, options: list[str]) -> str:
    """玩家输入 '1' → 映射为 options[0] 的文本。"""
    stripped = player_input.strip()
    if stripped.isdigit():
        idx = int(stripped) - 1
        if 0 <= idx < len(options):
            return options[idx]
    return player_input


def display_narrative(narrative: str, options: list[str], turn: int):
    print(f"\n{'=' * 50}")
    print(narrative)
    print(f"{'-' * 50}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    print(f"{'-' * 50}")
    print(f"[第 {turn} 回合] 输入选项编号或自由输入:", end=" ")


def main_menu() -> str:
    print("=" * 50)
    print("          地球Online")
    print("=" * 50)
    print("  1. 新的冒险")
    print("  2. 继续冒险")
    print("  3. 退出")
    while True:
        choice = input("\n> ").strip()
        if choice in ("1", "2", "3"):
            return choice
        print("请输入 1-3。")


def format_time(iso_str: str) -> str:
    if not iso_str:
        return "未知时间"
    try:
        return datetime.fromisoformat(iso_str).strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str


def choose_save(sm: StateManager):
    saves = sm.list_saves()
    if not saves:
        print("\n还没有存档。")
        return None

    print("\n选择一个存档：")
    for i, s in enumerate(saves, 1):
        print(
            f"  {i}. {s['name']} | {s['mode']} | "
            f"第{s['turn_count']}回合 | {format_time(s['last_played'])}"
        )
    print("  0. 返回主菜单")

    while True:
        choice = input("\n> ").strip()
        if choice == "0":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(saves):
            return saves[int(choice) - 1]
        print("请输入有效编号。")


def start_new_game(pipeline: GamePipeline, sm: StateManager):
    mode = choose_mode()
    profile = create_character(pipeline)
    pid, sid, state = sm.create_player(mode, profile)
    print(f"\n角色创建完毕！进入 {mode} 世界……")

    try:
        opening = pipeline.generate_opening(pid, sid)
    except PipelineError as e:
        print(f"开场失败: {e}")
        return

    game_loop(pipeline, sm, pid, sid, opening)


def continue_game(pipeline: GamePipeline, sm: StateManager):
    save = choose_save(sm)
    if save is None:
        return
    game_loop(pipeline, sm, save["player_id"], save["session_id"], None)


def game_loop(
    pipeline: GamePipeline,
    sm: StateManager,
    pid: str,
    sid: str,
    opening,
):
    """完整的游戏回合循环。opening 为 dict 表示新游戏（含首轮叙事），
    None 表示继续游戏（跳过开场，显示静态摘要后等玩家输入）。"""
    if opening is not None:
        display_narrative(opening["narrative"], opening["options"], opening["turn"])
        options = opening["options"]
    else:
        state = sm.get_state(pid, sid)
        print(f"\n{'=' * 50}")
        print(f"【继续游戏】{state.name} | {state.mode} | 第 {state.turn_count} 回合")
        if state.location:
            print(f"  位置：{state.location}")
        if state.time:
            print(f"  时间：{state.time}")
        if state.history:
            last = state.history[0]
            print(f"{'-' * 50}")
            print("【上次剧情】")
            print(last.narrative)
            if last.options_shown:
                print()
                print("上次你可选：")
                for i, opt in enumerate(last.options_shown, 1):
                    print(f"  {i}. {opt}")
        print(f"{'-' * 50}")
        print("输入你的下一个行动：", end=" ")
        options = []

    while True:
        try:
            raw = input()
        except (EOFError, KeyboardInterrupt):
            print("\n退出游戏。")
            break

        if raw.lower() in ("exit", "退出", "quit"):
            print("退出游戏。")
            break

        if not raw.strip():
            continue

        user_input = resolve_option(raw, options)

        try:
            result = pipeline.execute(pid, sid, user_input)
        except PipelineError as e:
            if e.recoverable:
                print(f"\n  [{e}]")
                print("  请重试：", end=" ")
                continue
            else:
                print(f"\n不可恢复错误: {e}")
                break

        options = result["options"]
        display_narrative(result["narrative"], result["options"], result["turn"])


def main():
    sm = StateManager()
    try:
        ai = AIClient()
    except AuthError:
        print("\n需要 DeepSeek API 密钥才能运行。")
        print("获取地址：https://platform.deepseek.com/api_keys")
        api_key = input("\n请输入你的 API Key: ").strip()
        if not api_key:
            print("未输入密钥，退出。")
            sys.exit(1)
        os.environ["DEEPSEEK_API_KEY"] = api_key
        with open(".env", "w", encoding="utf-8") as f:
            f.write(f"DEEPSEEK_API_KEY={api_key}\n")
            f.write("DEEPSEEK_BASE_URL=https://api.deepseek.com/v1\n")
        try:
            ai = AIClient(api_key=api_key)
        except AuthError:
            print("API Key 无效，请检查后重试。")
            sys.exit(1)

    pipeline = GamePipeline(sm, ai)

    while True:
        choice = main_menu()
        if choice == "1":
            start_new_game(pipeline, sm)
        elif choice == "2":
            continue_game(pipeline, sm)
        else:
            print("再见！")
            break


if __name__ == "__main__":
    main()
