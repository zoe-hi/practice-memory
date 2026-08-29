# 经验捕手｜后端开发规范 v1.4

> **用途：**全新仓库的后端绿色开发规范，可直接交给 Codex 或后端开发者执行。  
> **推荐仓库路径：**`docs/backend-development-spec.md`  
> **状态：**Phase 1–6 implemented MVP specification  
> **更新时间：**2026-08-29  
> **上位事实源：**`Build-Ledger-v1.md` v1.2  
> **适用范围：**She Nicest 黑客松 Golden Demo；单一演示身份、单实例部署。

---

## 0. 给 Codex 的执行指令

请在全新项目中按本文件实现后端，不要重新发明产品范围。

开始前必须：

1. 在新建的项目根目录创建 `AGENTS.md`、`README.md`、`docs/` 与 `backend/`。
2. 将本文件保存为 `docs/backend-development-spec.md`，并在根目录 `AGENTS.md` 中要求所有后端任务先阅读它。
3. 使用本文冻结的 Python、FastAPI、SQLAlchemy、SQLite 与测试方案，不增加平行技术路线。
4. 先用 FakeAI 跑通完整闭环并写测试，再接真实 AI；不得让真实模型调用阻塞基础开发。
5. 每完成一个阶段运行测试，并让代码始终保持可启动、可验证。
6. 结束时报告：创建文件、运行命令、测试结果、真实 AI 接入状态和仍存在的限制。

---

## 1. 后端目标

实现一条真实、可刷新恢复、可重复演示的主链路：

```text
现场快速记一段语音
→ 立即保存为待复盘标记
→ 活动结束后打开标记
→ AI 基于完整会话进行最多 2 轮追问（硬上限 3）
→ 生成“事情经过 + 我的复盘”草稿
→ 用户修改并确认
→ 保存个人经验
→ 后来的人描述困扰并找回一条相似经验
```

重要语义：

- 一段语音只是一个原始消息，不与 `context` 等经验字段一一对应。
- 一个 `capture_session` 表示一个经验线程，可包含初始标记和多段复盘语音。
- MVP 中，一个 `capture_session` 最终生成一条 `experience`。
- `context / action_and_reason / observed_result` 由整个会话共同还原。
- 记忆标记是临时个人线索，不进入共享经验库。
- 只有用户主动确认后的 `experience` 才能进入经验库。

---

## 2. MVP 完成标准

以下条件全部满足才算后端完成：

1. 可以上传音频或使用文字 fallback 创建快速标记。
2. 创建接口在音频落盘、会话入库后立即返回，不等待完整 AI 处理。
3. “待复盘”记录刷新页面或重启 API 后仍能找回。
4. 同一会话可以保存多轮问题与多段语音/文字回答。
5. AI 使用完整消息历史生成事实层和复盘层，而不是把第一段语音直接当作 `context`。
6. 追问目标最多 2 轮，硬上限 3 轮；到达上限仍缺失的信息保持 `null`，不得编造。
7. 用户可以修正活动名称、初始转写和最终草稿。
8. 确认操作幂等：重复点击只能得到同一条经验。
9. 经验表不保存 `capture_session_id`。
10. 可以从 5–8 条种子经验和新确认记录中返回 1 条相似经验及匹配理由。
11. API Key 只存在后端环境变量，前端不可见。
12. 测试默认使用 FakeAI，不依赖网络或真实密钥，并能通过 `pytest -q`。

---

## 3. 文档存放与仓库入口

完整技术规范不要放进 `AGENTS.md`。推荐结构：

```text
practice-memory/
├── AGENTS.md
├── README.md
├── docs/
│   └── backend-development-spec.md
├── backend/
└── frontend/                         # 前端开始开发时再加入
```

职责分工：

- `AGENTS.md`：Codex 每次工作都应遵守的短规则，包括目录、开发命令、测试命令、密钥规则和本规范的入口。
- `docs/backend-development-spec.md`：本文件，保存完整架构、数据、API、AI 契约、测试和验收标准。
- `README.md`：面向团队成员的安装、启动、环境变量和 Demo 使用说明。

根目录 `AGENTS.md` 初始内容可以是：

```markdown
# Repository instructions

- Read `docs/backend-development-spec.md` before making backend changes.
- Implement backend code under `backend/` and keep API behavior consistent with the specification.
- Use Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic v2, and SQLite.
- Run `cd backend && pytest -q` after backend changes.
- Never commit `.env`, API keys, SQLite data files, or uploaded audio.
- Finish each task with the repository in a runnable state and report verification results.
```

代码建立后，再根据真实命令补充 `AGENTS.md`；不要把本规范全文复制进去。

---

## 4. 总体架构

```text
React / TypeScript / Vite 移动 Web 或 PWA
                  ↓ HTTPS JSON / multipart API
               FastAPI 单体后端
                  ├── CaptureSession Service
                  ├── Reflection Orchestrator
                  ├── AI Provider Interface
                  ├── Experience Service
                  ├── Retrieval Service
                  ├── Repository Layer
                  └── Audio Storage / Cleanup
                         ↓
             SQLite + 临时音频目录
                         ↓
                 外部 ASR / 大模型 API
```

技术默认：

- Python 3.11+；
- FastAPI；
- Pydantic v2；
- SQLAlchemy 2.x；
- SQLite；
- FastAPI `BackgroundTasks` 仅用于初始标记的后台转写；
- `pytest` + FastAPI `TestClient`；
- 单进程、单实例部署，SQLite 使用持久化磁盘。

MVP 固定使用 SQLAlchemy 2.x，不引入 Alembic；应用启动时使用 `create_all` 初始化 SQLite。

---

## 5. 核心状态机与业务不变量

### 5.1 状态

```text
marked
→ reflecting
→ needs_confirmation
→ confirmed
```

另有终止状态：

```text
failed
```

含义：

- `marked`：初始标记已可靠保存；转写可以尚未完成。
- `reflecting`：用户已进入活动后复盘，AI 正在追问或等待回答。
- `needs_confirmation`：AI 草稿已生成，等待用户修改和确认。
- `confirmed`：最终经验已保存。
- `failed`：初始音频无法恢复、会话损坏等不可继续的错误。临时 AI 超时不应直接破坏会话，可返回错误并允许重试。

### 5.2 不变量

1. 只有 `needs_confirmation` 可以首次确认。
2. `confirmed` 再次调用确认接口时，返回原有经验，不能新建。
3. 一个会话最多有 3 条 `assistant/question` 消息。
4. AI 不得根据空白补全字段；缺失字段保存为 `null`。
5. 后出现的明确纠正优先于早期表述；存在明显冲突时优先追问确认。
6. `things_to_note` 已表示“给后来人的提醒”，不另设 `advice_to_next_person`。
7. `open_question` 只在用户确实表达不确定时出现。
8. `recorded_at` 使用初始标记时间；直接活动后复盘时使用会话创建时间。

---

## 6. 数据模型

只建立两张核心业务表：`capture_sessions` 与 `experiences`。

### 6.1 `capture_sessions`

| 字段 | 类型建议 | 约束/说明 |
|---|---|---|
| `id` | string UUID | 主键，后端生成 |
| `entry_mode` | string | `marker` 或 `direct_reflection` |
| `activity_name` | string nullable | 快速记时允许为空；复盘/确认时用户可修正 |
| `marker_transcript` | text nullable | 初始标记转写；不是最终 `context` |
| `audio_temp_path` | text nullable | 仅后端内部使用，不返回前端 |
| `status` | string | `marked/reflecting/needs_confirmation/confirmed/failed` |
| `conversation_json` | JSON | 完整消息序列，默认 `[]` |
| `draft_json` | JSON nullable | AI 草稿及内部来源映射 |
| `confirmed_experience_id` | string nullable | 确认后写入，用于幂等 |
| `error_code` | string nullable | 最近一次不可继续错误 |
| `error_message` | text nullable | 可诊断但不得包含密钥 |
| `captured_at` | datetime UTC | 创建时写入 |
| `updated_at` | datetime UTC | 每次修改更新 |
| `expires_at` | datetime UTC | MVP 默认创建后 24 小时，可配置 |

### 6.2 `conversation_json` 消息结构

```json
[
  {
    "turn_id": "uuid",
    "role": "user",
    "kind": "marker",
    "text": "三个孩子一直站在门口，我先改成自由选书。",
    "source": "audio",
    "created_at": "2026-08-28T10:00:00Z"
  },
  {
    "turn_id": "uuid",
    "role": "assistant",
    "kind": "question",
    "text": "你当时为什么决定这样改？",
    "source": "generated",
    "created_at": "2026-08-28T11:30:00Z"
  },
  {
    "turn_id": "uuid",
    "role": "user",
    "kind": "answer",
    "text": "我觉得围坐对第一次来的孩子门槛太高。",
    "source": "audio",
    "created_at": "2026-08-28T11:31:00Z"
  }
]
```

约束：

- `role`：`user | assistant`；
- `kind`：`marker | question | answer`；
- `source`：`audio | text | generated`；
- 前端只接收消息文本和时间，不接收服务器文件路径；
- 初始标记转写成功后，同时写入 `marker_transcript` 和第一条 `marker` 消息；
- 后续语音回答转写后只在消息中保存文字，原音频可立即删除。

### 6.3 `experiences`

| 字段 | 类型建议 | 约束/说明 |
|---|---|---|
| `id` | string UUID | 主键 |
| `activity_name` | string | 确认时必须非空 |
| `contributor_name` | string | MVP 从配置或确认请求取得 |
| `contributor_role` | string nullable | 演示身份可预置 |
| `context` | text nullable | 当时发生了什么 |
| `action_and_reason` | text nullable | 做了什么、为什么 |
| `observed_result` | text nullable | 后来发生了什么 |
| `went_well` | text nullable | 做得好的地方 |
| `shortcomings` | text nullable | 不足的地方 |
| `things_to_note` | text nullable | 后来人需要注意的事情 |
| `open_question` | text nullable | 用户仍有的疑问 |
| `recorded_at` | datetime UTC | 初始标记/会话创建时间 |
| `updated_at` | datetime UTC | 最近修改时间 |

规则：

- 不保存标题；列表头部由“活动名称 + 自动时间 + 贡献者”组成。
- 不保存 `capture_session_id`。
- 确认时至少一个正文内容字段非空；不得因字段缺失而让 AI 编造。
- MVP 不提供经验删除和版本历史。

---

## 7. AI 数据契约

### 7.1 Provider 接口

至少定义以下抽象接口，业务层不得直接调用具体供应商 SDK：

```python
class AIProvider(Protocol):
    def transcribe(self, audio_path: str) -> str: ...

    def advance_reflection(
        self,
        messages: list[ConversationMessage],
        current_draft: ExperienceDraft | None,
        question_count: int,
    ) -> ReflectionAdvanceResult: ...

    def rank_experiences(
        self,
        concern: str,
        candidates: list[ExperienceCandidate],
    ) -> ExperienceMatch | None: ...
```

实现：

- `FakeAIProvider`：默认测试和无密钥 Demo 使用，确定性输出；
- `DashScopeAIProvider`：使用环境变量配置的阿里云 Qwen ASR/大模型；
- 具体 SDK 调用必须封装在独立适配层中，业务服务不得依赖 DashScope SDK。

### 7.2 `ExperienceDraft`

```json
{
  "context": "亲子共读活动中，三个孩子一直站在门口。",
  "action_and_reason": "吴瑶儿判断围坐门槛较高，因此改为自由选书。",
  "observed_result": "孩子进入了活动，但现场变得更分散。",
  "went_well": "降低了第一次参加活动的孩子的参与门槛。",
  "shortcomings": "自由选择后缺少重新收拢现场的方法。",
  "things_to_note": "提前准备自由选择后的收拢方式。",
  "open_question": null,
  "source_turn_ids": {
    "context": ["turn-1"],
    "action_and_reason": ["turn-1", "turn-3"],
    "observed_result": ["turn-5"],
    "went_well": ["turn-7"],
    "shortcomings": ["turn-7"],
    "things_to_note": ["turn-7"],
    "open_question": []
  },
  "warnings": []
}
```

`source_turn_ids` 和 `warnings` 只保存在 `draft_json`，不进入最终经验表。其目的：让测试可以验证每个事实来自会话，而不是模型臆造。

Pydantic 模型使用 `extra="forbid"`。模型输出解析失败时不得把原始字符串直接写入经验表。

### 7.3 `ReflectionAdvanceResult`

```json
{
  "ready_for_confirmation": false,
  "next_question": "改成自由选书后，那三个孩子后来怎么样了？",
  "draft": null
}
```

或：

```json
{
  "ready_for_confirmation": true,
  "next_question": null,
  "draft": {}
}
```

### 7.4 追问规则

AI 必须：

1. 读取整个 `conversation_json`，而不是只读取最近一段语音。
2. 优先补齐影响理解的事实链：`context → action_and_reason → observed_result`。
3. 再获得最重要的复盘判断：做得好、不足、提醒、仍有疑问。
4. 每轮只问一个简短、现场化的问题；必要时可把紧密相关的“行动与结果”放在同一句。
5. 目标最多 2 个问题，硬上限 3 个。
6. 不问用户“适用条件是什么”“证据等级是什么”等抽象问题。
7. 不生成 `result_type`、`evidence_status`、标签或组织结论。
8. 不把个人表达改写成“普遍有效”“最佳实践”。
9. 发现前后冲突时先询问确认；达到硬上限后保留 `warning`，不要自行选择。
10. 到达硬上限时，无论是否完整，都必须返回可确认草稿，缺失项为 `null`。

### 7.5 FakeAI 的确定性行为

FakeAI 不是空壳。它必须足以跑通自动测试和 Golden Demo：

1. 初始消息后返回关于“后来发生了什么”的第一个问题；
2. 第一条回答后返回关于“做得好 / 不足 / 提醒”的第二个问题；
3. 第二条回答后返回 `ready_for_confirmation=true` 和完整草稿；
4. 对 Golden Demo 文本生成本文件示例中的亲子共读草稿；
5. 对非示例输入也返回 Schema 合法的保守草稿，无法提取的字段为 `null`；
6. FakeAI 不得产生第三个问题，硬上限 3 仅用于真实 Provider 的异常保护；
7. API 测试优先使用文字 fallback，FakeAI 的 `transcribe` 可通过依赖注入返回测试指定文本。

### 7.6 DashScope Provider

- ASR 默认使用 `qwen3-asr-flash` 的同步 `MultiModalConversation` 调用，只接受后端已校验的本地绝对文件并转换为 `file://` URI；
- 复盘默认使用 `qwen-plus` 的 `Generation` 调用和 `json_object` 输出模式，不设置可能截断 JSON 的 `max_tokens`；
- 模型输入包含完整有序会话、当前草稿、问题数和合法 turn ID，不包含 API Key、服务器音频路径或数据库内部字段；
- 输出必须经过 JSON 解析、`ReflectionAdvanceResult`/`ExperienceDraft` 校验，并拒绝不存在的 `source_turn_ids`；
- 超时、网络错误、HTTP 429/5xx 和首次非法 JSON 最多重试一次；认证错误和确定性 4xx 不重试；
- `rank_experiences` 使用严格 `{match: ExperienceMatch | null}` JSON，只能从最多 20 条输入候选中选择；非法输出由检索服务回退到本地确定性评分。

---

## 8. API 契约

统一前缀：`/api/v1`。  
时间统一返回 UTC ISO 8601。  
所有 JSON 响应字段使用 `snake_case`。

### 8.1 健康检查

```http
GET /api/v1/health
```

```json
{
  "status": "ok"
}
```

### 8.2 创建捕捉会话

```http
POST /api/v1/capture-sessions
Content-Type: multipart/form-data
```

字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `audio` | 与 `text` 二选一 | 快速标记音频 |
| `text` | 与 `audio` 二选一 | 测试/失败 fallback |
| `activity_name` | 否 | MVP Demo 可预置“亲子共读活动” |
| `entry_mode` | 否 | `marker` 默认；或 `direct_reflection` |

必须恰好提供 `audio` 或 `text` 之一。

响应 `201`：

```json
{
  "id": "uuid",
  "entry_mode": "marker",
  "activity_name": "亲子共读活动",
  "status": "marked",
  "marker_transcript": null,
  "captured_at": "2026-08-28T10:00:00Z",
  "expires_at": "2026-08-29T10:00:00Z"
}
```

行为：

- 先把音频安全落盘并写入数据库，再返回；
- 音频转写使用 `BackgroundTasks`；
- 后台任务只有在 `marker_transcript` 仍为空时才能写入，不能覆盖用户已经修正的转写；
- 不等待 AI 追问或卡片生成；
- 文字输入立即写入 `marker_transcript` 与第一条消息；
- `entry_mode=direct_reflection` 可以把状态直接设为 `reflecting`，但仍使用同一会话模型。

### 8.3 获取待复盘列表

```http
GET /api/v1/capture-sessions?status=marked&limit=20
```

只返回摘要：`id / activity_name / marker_transcript preview / status / captured_at`。

### 8.4 获取会话详情

```http
GET /api/v1/capture-sessions/{session_id}
```

响应应包含：

- 会话公开字段；
- `conversation` 消息数组；
- `draft`；
- 当前是否可以确认；
- 不包含任何服务器文件路径、密钥或原始模型响应。

### 8.5 修正活动名称或初始转写

```http
PATCH /api/v1/capture-sessions/{session_id}
Content-Type: application/json
```

```json
{
  "activity_name": "亲子共读活动",
  "marker_transcript": "三个孩子一直站在门口，我先改成自由选书。"
}
```

如修改 `marker_transcript`，必须同步更新第一条 `marker` 消息；如果后台转写尚未写入该消息，则创建它。

### 8.6 开始活动后复盘

```http
POST /api/v1/capture-sessions/{session_id}/start-reflection
```

行为：

1. 校验会话状态；
2. 确保初始转写存在；如果后台任务尚未完成但临时音频仍在，则在本次请求中同步重试转写；
3. 状态改为 `reflecting`；
4. 调用 `advance_reflection`；
5. 写入第一个问题，或直接生成草稿。

该接口允许从 `marked` 进入，也允许 `entry_mode=direct_reflection` 的会话在尚未产生任何 AI 问题时调用。转写重试失败时返回可重试的 `TRANSCRIPTION_FAILED`，但保留原会话和音频，不直接把会话置为不可恢复的 `failed`。

正常响应：

```json
{
  "session_id": "uuid",
  "status": "reflecting",
  "next_question": {
    "turn_id": "uuid",
    "text": "改成自由选书后，那三个孩子后来怎么样了？"
  },
  "draft": null
}
```

### 8.7 提交一轮回答

```http
POST /api/v1/capture-sessions/{session_id}/turns
Content-Type: multipart/form-data
```

字段：`audio` 与 `text` 恰好提供一个。

行为：

1. 转写或直接读取文字；
2. 追加一条 `user/answer` 消息；
3. 统计已有问题数量；
4. 调用 AI；
5. 若继续追问，追加 `assistant/question`；
6. 若信息足够或到达硬上限，保存 `draft_json` 并转为 `needs_confirmation`；
7. 后续回答音频在成功转写后立即删除。

继续追问响应：

```json
{
  "session_id": "uuid",
  "status": "reflecting",
  "answer_transcript": "后来三个孩子进来了，但现场变得比较分散。",
  "next_question": {
    "turn_id": "uuid",
    "text": "回头看，哪里做得好、哪里还不理想，后来的人最需要注意什么？"
  },
  "draft": null
}
```

草稿响应：

```json
{
  "session_id": "uuid",
  "status": "needs_confirmation",
  "answer_transcript": "下次要提前准备把孩子重新收拢的方法。",
  "next_question": null,
  "draft": {}
}
```

### 8.8 修改草稿

```http
PATCH /api/v1/capture-sessions/{session_id}/draft
Content-Type: application/json
```

请求体只允许：

```json
{
  "context": "...",
  "action_and_reason": "...",
  "observed_result": "...",
  "went_well": "...",
  "shortcomings": "...",
  "things_to_note": "...",
  "open_question": null
}
```

不得允许前端直接修改 `source_turn_ids`、状态或内部警告。后端应把用户实际修改过的字段在内部来源映射中标记为 `manual_edit`，避免继续声称该文本完全来自原语音轮次。

### 8.9 确认并创建经验

```http
POST /api/v1/capture-sessions/{session_id}/confirm
Content-Type: application/json
```

```json
{
  "contributor_name": "吴瑶儿",
  "contributor_role": "乡村图书馆员"
}
```

行为必须在一个事务中完成：

1. 如果已有 `confirmed_experience_id`，直接返回原经验；
2. 校验状态与草稿；
3. 创建 `experience`；
4. 写回 `confirmed_experience_id`；
5. 状态改为 `confirmed`；
6. 提交事务；
7. 删除或安排清理初始临时音频。

响应 `201`；重复调用可返回 `200`，但必须是同一个 `experience.id`。

### 8.10 经验列表与详情

```http
GET /api/v1/experiences?activity_name=亲子共读活动&limit=20
GET /api/v1/experiences/{experience_id}
```

`activity_name` 可选；`limit` 范围为 1–100、默认 20。列表按 `recorded_at DESC`，不返回内部草稿、会话或音频信息。详情不存在时返回 `404 EXPERIENCE_NOT_FOUND`。

### 8.11 相似经验检索

```http
POST /api/v1/experiences/search
Content-Type: application/json
```

```json
{
  "activity_name": "亲子共读活动",
  "concern": "现场很热闹，但总有孩子站在门口"
}
```

`activity_name` 与 `concern` 必须为非空文字；`concern` 最长 4000 字符。

响应：

```json
{
  "match": {
    "experience": {},
    "why_similar": "都出现了孩子停留在活动边缘、没有进入围坐区域的情况。"
  }
}
```

无匹配时：

```json
{
  "match": null
}
```

---

## 9. 检索实现

MVP 不使用向量数据库。

步骤：

1. 对 `activity_name` 做 Unicode NFKC、`casefold`、去首尾和合并空白后精确筛选；
2. 精确筛选无结果时放宽为双向包含匹配；
3. 候选上限 20；
4. FakeAI 使用中文双字片段和字母数字词的确定性重合评分；零重合返回 `null`，同分保持候选时间顺序；
5. RealAI 只在这些候选中选择一条并解释理由；
6. Provider 异常、超时、非法结构或候选外 ID 使用同一确定性本地评分；Provider 合法返回 `null` 时不强制 fallback；
7. Provider 和服务层都必须验证返回 ID 存在于候选集合；
8. 不生成候选中不存在的经验，不输出脱离来源的建议。

提供 `python -m app.seed` 幂等脚本，写入 6 条固定 UUID 和固定 UTC 时间的脱敏个人经验。重复运行按固定主键跳过已有记录，不覆盖已有数据；应用启动时不自动 seed。

---

## 10. 音频、隐私与安全

### 10.1 音频处理

- 允许 MIME：`audio/webm`、`audio/mp4`、`audio/x-m4a`、`audio/mpeg`、`audio/wav`；
- 默认最大文件大小：15 MiB，通过环境变量修改；
- 文件名必须由后端 UUID 生成，禁止使用上传文件名拼接路径；
- 保存目录：`storage/audio/{session_id}/`；
- 初始标记音频在确认或过期后删除；
- 后续回答音频在成功转写后立即删除；
- MVP 不强制依赖 ffmpeg 检查时长；前端限制时长，后端检查 MIME 和大小；
- 不在日志中输出音频内容、完整转写、模型原始响应或 API Key。

### 10.2 会话清理

实现 `cleanup_expired_sessions()`：

1. 找出 `expires_at < now`、状态未确认且没有 `confirmed_experience_id` 的会话；
2. 先删除 `storage/audio/{session_id}`，成功后删除会话数据库行；
3. 音频清理失败时保留数据库行，置为 `failed` 并记录通用 `STORAGE_ERROR`，下次可重试；
4. 已确认或尚未过期的会话永不删除；
5. 返回删除数、失败数和跳过数，不返回会话内容；
6. 在 `create_all` 后、应用开始接收请求前执行一次；单条音频清理失败不阻止启动，数据库级失败仍阻止启动；
7. 提供 `python -m app.cleanup`，输出安全汇总，存在清理失败时以非零状态退出；
8. 应用内不增加定时器，运行期间的清理由部署方显式调用；
9. `SESSION_TTL_HOURS=24` 是 MVP 默认值，不代表正式产品政策。

### 10.3 基础安全

- API Key 仅从环境变量读取；
- `.env` 不提交，提供 `.env.example`；
- `CORS_ORIGINS` 至少包含一个合法 HTTP/HTTPS Origin，拒绝用户信息、路径、查询和 fragment，生产环境不允许 `*`；
- MVP 无 Cookie/登录，CORS 使用 `allow_credentials=False`，仅允许 `GET/POST/PATCH/OPTIONS` 和 `Accept/Content-Type` 请求头；
- `LOG_LEVEL` 仅接受 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`；
- 限制上传大小；
- 捕获路径穿越；
- 错误响应不返回堆栈、文件路径或供应商密钥；
- 应用日志只记录启动、清理数量和安全错误事件，不记录完整转写、会话、模型原文、API Key、音频路径或 Provider 异常文本；
- MVP 无登录，因此不得保存真实敏感身份信息，种子数据必须脱敏。

---

## 11. 统一错误格式

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "当前会话不能执行此操作。",
    "retryable": false
  }
}
```

至少定义：

| HTTP | code | 场景 |
|---|---|---|
| 400 | `INPUT_REQUIRED` | audio/text 未提供或同时提供 |
| 400 | `AUDIO_TOO_LARGE` | 超过大小限制 |
| 400 | `UNSUPPORTED_AUDIO_TYPE` | MIME 不支持 |
| 404 | `SESSION_NOT_FOUND` | 会话不存在 |
| 404 | `EXPERIENCE_NOT_FOUND` | 经验不存在 |
| 409 | `INVALID_STATE` | 状态不允许操作 |
| 422 | `INVALID_DRAFT` | 草稿不符合 Schema |
| 502 | `TRANSCRIPTION_FAILED` | ASR 失败 |
| 502 | `AI_INVALID_OUTPUT` | 模型 JSON 无法校验 |
| 504 | `AI_TIMEOUT` | AI 超时，可重试 |
| 500 | `STORAGE_ERROR` | 文件或数据库写入失败 |

不要使用 HTTP 500 表示用户输入或状态错误。

---

## 12. 推荐工程目录

新建后端的目标结构如下：

```text
backend/
├── app/
│   ├── api/
│   │   ├── health.py
│   │   ├── capture_sessions.py
│   │   └── experiences.py
│   ├── core/
│   │   ├── config.py
│   │   ├── errors.py
│   │   └── logging.py
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   │   ├── capture_session.py
│   │   └── experience.py
│   ├── schemas/
│   │   ├── capture_session.py
│   │   ├── conversation.py
│   │   ├── experience.py
│   │   └── errors.py
│   ├── repositories/
│   │   ├── capture_sessions.py
│   │   └── experiences.py
│   ├── services/
│   │   ├── audio.py
│   │   ├── cleanup.py
│   │   ├── reflection.py
│   │   ├── retrieval.py
│   │   └── ai/
│   │       ├── base.py
│   │       ├── fake_provider.py
│   │       ├── real_provider.py
│   │       ├── prompts/
│   │       │   ├── reflection.md
│   │       │   └── retrieval.md
│   │       └── parser.py
│   ├── seed.py
│   └── main.py
├── storage/
│   └── audio/
├── tests/
│   ├── conftest.py
│   ├── test_capture_sessions.py
│   ├── test_reflection.py
│   ├── test_confirmation.py
│   ├── test_experiences.py
│   └── test_retrieval.py
├── .env.example
├── requirements.txt 或 pyproject.toml
└── README.md
```

避免为每个文件只写几行无意义封装；可以在不改变职责边界的前提下合并小模块，但 API、业务服务与数据访问必须能区分并测试。

---

## 13. 环境变量

`.env.example` 至少包含：

```dotenv
APP_ENV=development
DATABASE_URL=sqlite:///./data/app.db
AUDIO_STORAGE_DIR=./storage/audio
MAX_AUDIO_BYTES=15728640
SESSION_TTL_HOURS=24
CORS_ORIGINS=http://localhost:5173
LOG_LEVEL=INFO

AI_PROVIDER=fake
AI_API_KEY=
AI_BASE_URL=https://dashscope.aliyuncs.com/api/v1
AI_MODEL=qwen-plus
AI_ASR_MODEL=qwen3-asr-flash
AI_TIMEOUT_SECONDS=75
AI_MAX_RETRIES=1

DEMO_CONTRIBUTOR_NAME=吴瑶儿
DEMO_CONTRIBUTOR_ROLE=乡村图书馆员
```

配置读取应在应用启动时校验。`AI_PROVIDER` 只接受 `fake` 或 `dashscope`；`fake` 时不要求密钥，选择 DashScope 而缺少密钥、模型名或合法 HTTPS Base URL 时应启动失败并给出明确错误。`AI_MAX_RETRIES` 只允许 `0` 或 `1`。`CORS_ORIGINS` 与 `LOG_LEVEL` 必须符合 10.3 节约束。

SQLite 建议：

- 启用 `foreign_keys=ON`；
- 单实例可启用 WAL；
- FastAPI 开发环境使用 `check_same_thread=False`；
- 部署时保持单 worker，避免用 SQLite 支撑并行多实例。

---

## 14. 测试要求

测试必须使用临时 SQLite 数据库和临时音频目录，不访问真实网络。

### 14.1 必测用例

1. 文字快速标记创建成功并写入第一条消息。
2. 音频快速标记安全落盘，响应不暴露路径。
3. 不提供或同时提供 audio/text 返回 400。
4. 不支持 MIME、超大文件被拒绝且无残留文件。
5. 待复盘会话在新数据库 Session 中仍可读取。
6. 初始转写缺失但音频仍在时，开始复盘会同步重试转写；失败可重试且不丢失会话。
7. 初始转写修改会同步第一条 marker 消息。
8. 多轮回答都进入同一个 `conversation_json`。
9. 事实字段可分别引用不同语音轮次。
10. AI 最多追加 3 个问题。
11. 到达硬上限时产生草稿，缺失字段保持 `null`。
12. 非 `needs_confirmation` 状态不能首次确认。
13. 确认后创建一条经验，且经验中没有 `capture_session_id`。
14. 重复确认返回同一 ID，数据库中仍只有一条经验。
15. 用户修改的草稿覆盖 AI 草稿并被最终保存。
16. 检索结果 ID 必须来自候选集合。
17. AI 检索失败时本地 fallback 仍可返回确定结果。
18. 会话确认或过期后音频被清理。
19. 所有错误使用统一错误格式。

### 14.2 Golden Path 集成测试

用文字 fallback 完成以下流程，不依赖真实 ASR：

```text
创建 marker：三个孩子一直站在门口，我先改成自由选书
→ 开始复盘
→ 回答：因为围坐对第一次来的孩子门槛太高
→ 回答：孩子进来了，但活动更分散
→ 回答：下次要提前准备把孩子重新收拢的方法（若 FakeAI 第二轮已成稿则不需要第三轮）
→ 修改/确认草稿
→ 查询经验详情
→ 用“总有孩子站在门口”检索
→ 返回刚确认的经验及匹配理由
```

真实 Provider 的集成测试默认跳过，仅在明确设置测试密钥时运行。

---

## 15. 实现顺序

严格按以下顺序推进：

### Phase 1：工程与配置

- 建立 FastAPI 应用、配置、数据库连接、统一错误和测试夹具；
- 提供 `/health`；
- 测试可运行。

### Phase 2：数据与 FakeAI 闭环

- 建立两张表；
- 实现文字 marker、待复盘列表、会话详情；
- 实现 FakeAI 多轮复盘；
- 实现草稿修改与幂等确认；
- 完成 Golden Path 自动测试。

### Phase 3：音频路径

- 实现安全上传、大小/MIME 校验、临时目录；
- 实现后台初始转写；
- 实现后续回答音频同步转写和立即清理；
- 覆盖失败与重试。

### Phase 4：真实 AI Provider

- 使用官方 DashScope SDK 实现 Qwen-ASR 与 Qwen 复盘调用及 JSON 解析；
- 遵守 Pydantic Schema；
- 添加 timeout、一次重试和错误映射；
- 不改变业务层 API。

### Phase 5：经验库与检索

- 实现 seed 脚本；
- 列表、详情、搜索；
- 确定性 fallback；
- 验证不能返回候选外 ID。

### Phase 6：交付清理

- 完成启动时及 `python -m app.cleanup` 的过期未确认会话清理与失败重试；
- 完成 `.env.example`、README、运行与部署命令；
- 收紧 CORS 白名单、方法、请求头和日志安全；
- 运行全量测试、依赖检查、健康检查以及 seed/cleanup CLI 验收。

不要在 Phase 2 完成前接真实模型，不要在 Golden Path 跑通前开发非 P0 能力。

---

## 16. 本地运行与交付

README 应提供以下等价命令：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
pytest -q
```

Windows 命令可以补充，但不要让 Windows 专用路径进入业务代码。

部署要求：

- 单 FastAPI 实例；
- 单 worker；
- SQLite 与音频目录位于持久化磁盘；
- 前端与后端通过 `CORS_ORIGINS` 配置；
- Golden Demo 必须准备 FakeAI/固定文字 fallback，真实 AI 失败不能导致整条演示中断。

---

## 17. 最终验收清单

交付前逐项确认：

- [x] API 可以启动，`/api/v1/health` 返回 200。
- [x] SQLite 自动初始化成功。
- [x] 快速记在数据库写入后立即返回 `marked`。
- [x] 首页可查询“待复盘”。
- [x] 初始标记与多轮回答共同生成事实部分。
- [x] 追问不超过硬上限 3。
- [x] 确认页字段与本规范完全一致。
- [x] 重复确认不会重复插入。
- [x] 经验表与本规范 Schema 一致，且没有 `capture_session_id`。
- [x] 5–8 条种子经验可读取。
- [x] 相似检索返回一条已有经验和匹配理由。
- [x] 前端拿不到 API Key、文件路径或原始模型响应。
- [x] 临时音频可清理。
- [x] FakeAI 路径不需要网络。
- [x] `pytest -q` 全部通过。
- [x] README 记录启动、配置、测试和 Demo fallback。

---

## 18. Codex 完工回复格式

完成实现后，回复必须包含：

1. **结果：**Golden Path 是否完整跑通。
2. **主要修改：**按模块列出关键文件。
3. **接口：**新增/修改的 API 列表。
4. **数据：**实际建立的表和状态。
5. **验证：**运行过的测试命令及结果。
6. **真实 AI：**当前是 FakeAI、真实 Provider，还是两者均支持。
7. **剩余限制：**只列真实存在且会影响 Demo 的问题。

不要只说“代码已完成”；必须给出可复核证据。
