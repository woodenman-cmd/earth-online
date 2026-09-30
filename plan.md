# 地球Online —— 从零开始的工业级架构设计

> 第一性原理推演 · 语言选型 · 分层架构 · 模块职责 · 数据流 · 设计原则 · 行动清单


## 一、第一性原理推演

### 1.1 这个产品的本质是什么？

去掉所有表层（文字、选项、UI、AI），留下的核心是：

> **一个维护着"虚拟世界状态"的引擎，接收玩家的行动指令，生成对应的叙事反馈。**

这本质上是一个 **状态机 + 渲染器**。状态机维护世界，渲染器把状态翻译成文字。

- ❌ **不是**"一个会聊天的AI"。如果是那样，直接和DeepSeek对话就行。
- ✅ **是**"一个用AI作为渲染引擎的状态机"。AI的作用是"把状态翻译成美丽的文字"，**不是**"决定状态如何变化"。

### 1.2 谁来决定"状态如何变化"？

| 方案 | 说明 | 结论 |
| :--- | :--- | :--- |
| AI决定 | 把状态变化交给AI——之前所有尝试的本质 | ❌ 不可控 |
| 代码决定 | 用代码逻辑决定状态变化，AI只负责润色文字 | ✅ 正确路径 |

**边界明确的分工（v3.0）：**

本项目本质是互动小说，不是数值模拟器。代码只保留跨世界通用的工程约束，规则判断交给AI一次完成。

| 谁负责 | 具体内容 | 示例 |
| :--- | :--- | :--- |
| **代码（工程约束）** | ①时间单向约束 ②状态增量合并 ③硬约束校验（跨级跃迁/空值/格式）④历史窗口管理 ⑤调度AI调用 | "时间只能向前走，没提到的字段保留不动" |
| **AI（一次完成）** | ①可行性校验 + 意图解析（作为Prompt前导指令）②生成沉浸式叙事 + 场景走向式选项 ③输出结构化状态变更JSON + 自检报告 | 不可行时优雅处理（失败→新线索），可行时正常叙事 |
| **代码（后置校验）** | 对AI输出的状态变更做硬约束检查：时间单调、关系跨级、格式完整性。只在检测异常时触发 AI 复核 | 每回合通常 1 次 API 调用，异常时追加 1 次 |

**核心变化**：取消了 RuleEngine 独立模块和独立校验 API 调用。可行性判断合并进主叙事 Prompt，硬约束由代码后置检查。每回合从固定 3 次 API 降为通常 1 次。

### 1.3 商业级产品需要具备什么？

- ✅ 可扩展：加新剧情不掉链子
- ✅ 可维护：改一个机制不影响其他模块
- ✅ 可运营：支持多玩家、支持内容更新
- ✅ 性能可控：不要让AI负担太重


## 二、语言选型：Python vs C++（第一性原理层面）

不从"哪个语言更好"出发，而是问：**我们需要什么特性？**

| 需求 | Python | C++ |
| :--- | :--- | :--- |
| 快速迭代 | ✅ 极快，写一行测一行 | ❌ 编译慢，迭代周期长 |
| AI生态兼容 | ✅ DeepSeek/OpenAI官方SDK优先支持 | ⚠️ 需自己封装HTTP请求 |
| 数据热更新 | ✅ 改代码即生效 | ❌ 需重新编译部署 |
| 内存控制（多玩家） | ⚠️ 需要技巧（如对象池） | ✅ 完全可控 |
| 学习成本 | ✅ 已学过 | ❌ 会但写起来慢 |
| 招聘人才 | ✅ AI工程岗位大量使用Python | ⚠️ 游戏岗位用C++，AI岗位用Python |

### 🎯 结论

> **这个产品的核心竞争力是"AI叙事质量"，不是"图形渲染性能"。** 瓶颈在API调用延迟，不在CPU执行速度。因此，**Python是唯一理性的选择**。


## 三、工业级架构设计

### 3.1 分层架构（从底层到表层）

```
┌─────────────────────────────────────────────────────┐
│                    用户界面层                       │
│        (CLI / Web / 手机App / Discord Bot)          │
│                  只做"接收输入，显示输出"            │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                   API 网关层                        │
│         (FastAPI / Flask)                          │
│         只做"鉴权、限流、路由转发、输入长度校验"      │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                   核心引擎层                        │
│    ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│    │ 状态管理器  │  │ 上下文组装器│  │   AI客户端  │ │
│    │(玩家账本)   │  │(Prompt构建)│  │ (DeepSeek) │ │
│    └────────────┘  └────────────┘  └────────────┘ │
│    ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│    │ 结果分拣器  │  │ 状态更新器 │  │ 世界配置器 │ │
│    │(字段分拣)   │  │(校验+翻译) │  │(静态数据)  │ │
│    └────────────┘  └────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                  数据持久化层                       │
│    ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│    │   JSON文件  │  │   Redis    │  │   YAML配置  │ │
│    │(玩家存档)  │  │(会话/缓存) │  │(世界配置)  │ │
│    └────────────┘  └────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 3.2 核心模块职责划分（低耦合关键）

| 模块 | 职责 | 不做什么 |
| :--- | :--- | :--- |
| **StateManager** | 维护玩家状态 + 会话管理（turn_count、历史窗口、存档/加载）。关系采用 **C+ 模型**（粗粒度层级+内部进度，progress≥1.0直接跃迁，见3.5）。支持增量更新 | 不生成叙事，不调用API |
| **ContextBuilder** | 纯函数拼接工。组装主叙事Prompt，输入零件：①System Prompt（含可行性校验前导指令）②状态摘要③最近N轮历史④玩家原始输入。输出：完整Prompt字符串 | 不调用API，不做逻辑判断 |
| **AIClient** | 调用DeepSeek API的统一接口封装，处理重试/超时/错误 | 不解析结果，不修改状态 |
| **ResultParser** | 字段分拣器。`json.loads()` 拆出主叙事返回的原始数据，分拣为：①narrative+options（→返回玩家）②state_changes（→送入StateUpdater校验） | 不调用API，不判断合理性 |
| **StateUpdater** | ①硬约束校验（时间单调/关系跨级/格式完整性）②将AI描述翻译为C+模型操作 ③对检测到的异常触发AI复核（偶发）④生成增量写入StateManager | 不生成叙事 |
| **WorldConfig** | 加载/维护静态数据（NPC库/地点库/预设事件/世界观描述） | 不涉及玩家状态，只读 |

> **设计说明**：
> ① 可行性校验不再独立调用API。System Prompt中包含前导指令，AI在生成叙事前先判断合理性。不可行的动作按prompt.md第7条处理（失败→新线索），无需额外步骤。
> ② 每回合通常 1 次 API 调用。StateUpdater 硬约束校验发现异常（关系跨3级、时间倒退等）时才触发第 2 次 AI 复核。
> ③ 关系状态采用 C+ 模型（简化版），详见 3.5 节。
> ④ 玩家输入上限 500 字，API 网关拦截超长输入。

### 3.2.1 数据结构定义

**PlayerState（玩家状态对象）：**

```python
{
    "player_id": str,                  # 唯一标识（UUID）
    "session_id": str,                 # 会话标识（同一玩家的不同存档）
    "turn_count": int,                 # 当前回合数（自增）
    "name": str,                       # 角色名
    "gender": str,                     # 性别
    "age": int,                        # 年龄
    "appearance": str,                 # 外貌描述（自然语言）
    "background": str,                 # 家庭背景（自然语言）
    "talent": str,                     # 天赋（自然语言）
    "style": "理性分析"|"感性直觉"|"圆滑机变"|"直率果决",  # 处世风格
    "mode": str,                       # 游戏模式（如"现代都市"）
    "location": str,                   # 当前位置名
    "time": str,                       # 当前时间描述（如"黄昏·19:00"）
    "inventory": [str],                # 物品列表
    "relationships": {                 # 关系状态（C+简化模型，见3.5）
        "NPC名": {
            "level": "冷淡"|"认识"|"友好"|"信任"|"亲密",
            "progress": float          # 0.0 ~ 1.0，≥1.0 直接跃迁
        }
    },
    "history": [                       # 最近 10 轮叙事记录（历史窗口）
        {
            "player_input": str,
            "narrative": str,
            "options_shown": [str]
        }
    ],
    "last_played": str                 # 最后游玩时间戳（ISO格式），save_state 时自动写入，用于存档列表展示
}
```

**StateDelta（增量变更）：**

```python
# 只包含需要变更的字段，未提及保留不动
{
    "turn_count": int | None,          # 回合数 +1
    "location": str | None,
    "time": str | None,
    "inventory_add": [str],
    "inventory_remove": [str],
    "relationship_changes": {
        "NPC名": {"level": str | None, "progress": float | None}
    },
    "history_append": dict | None      # 新增一条叙事记录（头部插入）
}
```

### 3.2.2 模块接口契约

**StateManager**
```
get_state(player_id: str, session_id: str) → PlayerState         # 从 JSON 恢复单个存档
save_state(state: PlayerState) → None                            # 持久化单个存档到 JSON
create_player(mode: str, profile: dict) → (player_id, session_id, PlayerState)
apply_delta(player_id: str, session_id: str, delta: StateDelta) → PlayerState   # 读→改→存，每回合自动存档
player_exists(player_id: str, session_id: str = "default") → bool
list_sessions(player_id: str) → list[str]                        # 某玩家的所有 session_id
list_saves() → list[dict]                                        # 全局扫描所有存档（"继续游戏"入口）
```
- `history` 保留最近 10 轮，超出时丢弃最旧记录
- `turn_count` 每次 apply_delta 自增
- `save_state` / `apply_delta` 自动写入 `last_played = datetime.now().isoformat()`
- `list_saves()` 遍历 `storage/players/*.json`，每个元素返回：
  `{player_id, session_id, name, mode, turn_count, last_played}`，按 `last_played` 倒序
- 存档文件损坏时 `list_saves()` 跳过该文件并记 warning，不影响整体

**ContextBuilder**
```
输入:
    system_prompt: str          # 从 prompt.md 加载（含可行性校验前导指令）
    player_state: PlayerState   # 当前状态
    player_input: str           # 玩家原始输入（≤500字）

输出:
    str                         # 完整 Prompt 字符串
```

**AIClient**
```
call(prompt: str, system_prompt: str, expect_json: bool = True) → dict
# 唯一 API 调用点，被主叙事和异常复核共用
```

**ResultParser**
```
输入:
    ai_response: dict    # AI 返回的原始字典

输出:
    {
        "narrative": str,        # → 返回给玩家
        "options": [str],        # → 返回给玩家
        "state_changes": dict    # → 送入 StateUpdater
    }
```

**StateUpdater**
```
输入:
    current_state: PlayerState
    state_changes: dict      # ResultParser 输出的原始变更

输出:
    StateDelta               # → 传入 StateManager.apply_delta()

内部流程:
    1. 硬约束校验：
       - 时间：新时间 ≥ 当前时间（否则丢弃）
       - 关系：跨级跃迁（如 冷淡→亲密）→ 标记异常，触发 AI 复核
       - 格式：变更字段是否在合法集合内
    2. 翻译：
       - 关系变更：根据 C+ 模型翻译 AI 描述为 level/progress 操作
       - progress ≥ 1.0 → 直接跃迁到下一级，重置 progress
    3. 若存在异常 → AIClient 调一次复核 → 合并结果
    4. 构建 StateDelta
```

**AI 复核（条件触发，无独立模块）**
```
触发条件：StateUpdater 硬约束校验检测到异常
输入:
    world_setting: str
    current_state: PlayerState
    anomalous_changes: list   # 仅包含异常的变更

输出:
    {
        "approved": [...],     # 复核后通过的
        "rejected": [...]      # 复核后驳回的
    }
```

### 3.2.3 API 端点

```
POST /api/v1/players
    创建新玩家
    请求体: { "mode": "现代都市", "profile": {...} }
    响应:   { "player_id": "xxx", "session_id": "xxx", "state": PlayerState }

POST /api/v1/players/{player_id}/sessions/{session_id}/action
    执行一个回合
    请求体: { "input": "..." }       # ≤500字，超长返回 400
    响应:   { "narrative": "...", "options": ["①...", "②..."] }

GET  /api/v1/players/{player_id}/sessions/{session_id}/state
    查看当前状态（调试用）
    响应:   PlayerState
```

### 3.3 数据流（一次完整交互）

```
1. 玩家输入 "去网吧找张宇"
        │
        ▼
2. API网关：校验长度（≤500字）→ 验证身份 → 转发给引擎
        │
        ▼
3. StateManager.get_state() → 加载当前 PlayerState
        │
        ▼
4. ContextBuilder 组装 Prompt：
   ┌────────────────────────────────────────────────────┐
   │ [System Prompt]                                    │
   │   含可行性校验前导指令：                            │
   │   "第一步：判断玩家动作在当前世界+角色能力下是否可行" │
   │   "不可行时优雅处理（失败→新线索），可行时正常叙事"  │
   │ [当前状态摘要] 时间/地点/物品/关系/风格              │
   │ [最近10轮历史]                                     │
   │ [玩家原始输入]                                     │
   └────────────────────────────────────────────────────┘
        │
        ▼
5. AIClient.call() → DeepSeek 一次返回：
   {
     "narrative": "你穿过三条街，推开网吧玻璃门...",
     "options": ["①去吧台找网管", "②径直走向张宇的常坐位置"],
     "state_changes": {
       "location": "网吧",
       "time": "黄昏·19:15",
       "relationship_changes": {"张宇": {"change": "轻微提升"}}
     }
   }
        │
        ▼
6. ResultParser 分拣：
   → narrative + options → 缓存（准备返回玩家）
   → state_changes → 送入 StateUpdater
        │
        ▼
7. StateUpdater 校验 + 翻译：
   ┌──────────────────────────────────────────────┐
   │ 硬约束检查：                                   │
   │ ✓ 时间: "黄昏·19:15" ≥ "黄昏·19:00"         │
   │ ✓ 关系: 张宇 "轻微提升" 未跨级               │
   │ ✓ 格式: 所有字段合法                         │
   │ → 无异常，不触发复核 ←                        │
   │                                              │
   │ 翻译:                                        │
   │ 张宇 progress += 0.15                        │
   │ 构建 StateDelta → apply_delta()              │
   └──────────────────────────────────────────────┘
        │
        ▼
8. StateManager 写入增量（turn_count+1, history头部插入新记录）
        │
        ▼
9. 返回给玩家：narrative + options
```

> **异常分支示例**（偶发，约5%回合）：
> AI 返回 `"relationship_changes": {"张宇": {"level_change": "冷淡→亲密"}}`
> → StateUpdater 检测到跨 3 级跃迁 → 触发 AIClient 复核 → 复核确认不合理 → rejected → 记录日志，忽略此变更

### 3.4 设计推演记录

> **本节记录架构推演的完整过程，供后续维护者理解每个决策的"为什么"。**

#### 架构总览演进

| 版本 | 核心变化 | API调用/回合 |
| :--- | :--- | :--- |
| v1.0（初始） | RuleEngine 预判规则 + 代码计算时间 → 7步线性流 | 2次 |
| v2.0 | RuleEngine 重构为前置校验门，数据流三段式（前置→叙事→后置校验） | 3次 |
| v2.4 | ResultParser 降级为分拣器，补充接口契约，C+关系模型 | 3次 |
| **v3.0（当前）** | **①②合并（可行性进主Prompt），③降级（硬约束+条件复核）** | **通常1次，偶发2次** |

#### RuleEngine 的一生（建立→重构→废除）

| 推演轮次 | 问题 | 结论 |
| :--- | :--- | :--- |
| v1.0 | RuleEngine 应输出什么？ | 确定性变更 + 叙事指导 + 冲突判定 |
| v2.0 | 代码能枚举所有规则吗？ | 不能。不同世界规则天差地别 |
| v2.0 | RuleEngine 审核谁？ | 前置审核玩家输入（非AI产出） |
| v2.0 | 可行性+意图分类能合并吗？ | 单次API，两条分支 |
| **v3.0** | **RuleEngine 真的省了API吗？** | **不省。不可行仍需走叙事（失败版本），等于浪费一次额外API** |
| **v3.0** | **可行性能合并进主Prompt吗？** | **能。prompt.md第7条已规定AI优雅处理不可行动作** |
| **v3.0（废除）** | **结论** | **RuleEngine 作为独立模块被废除，功能并入主Prompt前导指令** |

#### 其他推演亮点

- **ResultParser**：从解析器→清洗器→纯分拣器，最终定位"字段分拣，不洗不判"
- **校验环节**：从独立AI调用→suspicious三分→approved/rejected二分→硬约束代码化+条件复核
- **关系模型**：从数值→粗粒度层级→层级+等待确认→层级+直接跃迁（最终简化版）


### 3.5 关系状态模型（C+ 简化版）

> 设计目标：对外保持模糊的叙事沉浸感，对内保留可校验的量化锚点。

**模型结构：**

```
NPC关系 = {
    "level": "友好",        # 对外：AI 和玩家只看到层级名
    "progress": 0.7         # 对内：0→1 缓慢累积，≥1.0 直接跃迁
}
```

**五个层级（依次递进）：**

| 层级 | 叙事含义 | 校验约束 |
| :--- | :--- | :--- |
| `冷淡` | 陌生人、不信任 | 不能直接跳到信任/亲密 |
| `认识` | 见过面、有基本印象 | 可跳到友好 |
| `友好` | 愿意聊天、偶尔帮忙 | 可跳到信任 |
| `信任` | 分享私事、主动帮助 | 只能到亲密 |
| `亲密` | 无条件支持、深层羁绊 | 最高级 |

**跃迁逻辑（StateUpdater 内部）：**

```
progress < 1.0  → 微调：progress += 0.1~0.3（取决于AI描述强度）
progress ≥ 1.0  → 跃迁：level 升一级，progress 重置为 0.1
                     → 硬约束检查：跨级跃迁 → rejected
```


## 四、关键设计原则

| 原则 | 在本项目中的体现 |
| :--- | :--- |
| **单一职责** | 每个模块只干一件事（StateManager只管理状态，AIClient只发送请求） |
| **依赖倒置** | 引擎层依赖抽象接口，不依赖具体实现（DeepSeek可换成Claude） |
| **状态增量更新** | 只改指定字段，未提及的保留——防止信息意外丢失 |
| **最小 API 调用** | 可行性校验并入主 Prompt，硬约束由代码后置检查，异常才复核 |
| **配置与代码分离** | NPC数据、地点描述、预设事件→放在JSON/YAML文件中 |


## 五、项目目录结构

```
earth_online/
│
├── config/
│   ├── world/                    # 静态世界配置（只读）
│   │   ├── locations.json
│   │   ├── npcs.json
│   │   └── events.yaml
│   └── system_prompt.txt         # 系统提示词（含可行性校验前导指令）
│
├── src/
│   ├── core/                     # 核心数据与逻辑
│   │   ├── state.py              # GameState 类定义 + StateManager（含会话/窗口/存档）
│   │   └── world.py              # WorldConfig 加载器
│   │
│   ├── engine/                   # AI交互引擎
│   │   ├── context.py            # ContextBuilder
│   │   ├── client.py             # AIClient（DeepSeek封装）
│   │   ├── parser.py             # ResultParser（字段分拣）
│   │   └── updater.py            # StateUpdater（硬约束校验+翻译+条件复核）
│   │
│   ├── api/                      # 接口层
│   │   └── server.py             # FastAPI 入口（含输入长度校验）
│   │
│   └── utils/                    # 工具函数
│       ├── logger.py
│       └── retry.py
│
├── tests/                        # 单元测试
│   ├── test_state.py
│   └── test_parser.py
│
├── storage/                      # 运行时数据
│   └── players/                  # 每个 session 一个 JSON 文件
│       └── {player_id}_{session_id}.json
│
├── main.py                       # CLI 开发入口
└── requirements.txt              # 依赖清单
```


## 六、三种"工业级"程度的区分

| 程度 | 特征 | 当前阶段 |
| :--- | :--- | :--- |
| **作坊级** | 单文件、全局变量、改一处崩十处 | ❌ 避免 |
| **工程级** | 分层架构、单元测试、配置分离 | ✅ **目标** |
| **商业级** | 微服务、容器化、多区域部署 | ⚠️ 知道即可，暂不实现 |


## 七、接下来行动

| 天数 | 任务 |
| :--- | :--- |
| **第1天** | 接口设计完成（当前阶段）。**已产出：** 全部模块接口契约 + 数据流 + 数据结构定义 |
| **第2天** | 搭建 `state.py` + `server.py`，不走 AI，手工返回测试叙事，验证状态流转 |
| **第3天** | 接入 DeepSeek API，打通 ContextBuilder + AIClient + ResultParser，跑通完整回合 |


## 八、一句话总结

> **代码是"世界的骨架"，AI是"世界的皮肤"。** 代码只做最少的硬约束（时间/关系/格式），AI一次调用完成可行性判断+叙事生成+状态变更输出。

这不是一个调用AI的脚本，而是一个 **以 AI 为一体化推理引擎、以代码为硬约束校验层** 的互动小说服务器。

---

*文档版本：v3.0 | 更新日期：2026年7月4日*
*v3.0 变更：①废除 RuleEngine 独立模块，可行性校验并入主 Prompt 前导指令；②废弃独立校验 API，改为代码硬约束+条件复核；③API 调用从固定 3 次降为通常 1 次；④C+ 模型简化（progress≥1.0 直接跃迁）；⑤补充 Session/存档/历史窗口设计；⑥ prompt.md 同步删除了 AI 自维护锚点*

*v3.1 变更（存档功能，未实现）：①对齐 StateManager 接口契约与实际代码（save_to_file→save_state、load_from_file→get_state，修正 apply_delta 返回值，补充 player_exists/list_sessions）；②PlayerState 新增 last_played 时间戳字段；③新增 list_saves() 接口用于"继续游戏"入口；④main.py 抽取 game_loop()，新游戏/继续游戏共用*
