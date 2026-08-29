# 迹忆／经验捕手｜决策支持后端增量开发规范 v1.0

> **用途：**直接交给 Codex，在现有后端代码上增加“有来源的决策支持”。  
> **变更类型：**现有系统增量开发，不是重写。  
> **上位产品决定：**Build Ledger v1.5。  
> **核心要求：先更新相关文档，再修改代码；实现完成后再次回写交接文档和 README。**

---

## 0. 给 Codex 的执行指令

你正在修改一个已经完成 Phase 1–6 的 FastAPI + SQLite 后端。不要重新设计既有捕捉、复盘、确认和经验检索链路，也不要借此扩展非 P0 功能。

必须严格按以下顺序执行：

### Phase 0A：先读取并核对现有文档

在写代码前，先阅读仓库中实际存在的：

1. 根目录 `AGENTS.md`；
2. `docs/backend-development-spec.md`；
3. `backend-implementation-handoff.md`，或仓库中同名交接文档的实际路径；
4. `README.md`；
5. `.env.example`；
6. 当前 FastAPI `/openapi.json` 或路由与 Pydantic Schema；
7. 与 `audio`、`AIProvider`、经验检索、统一错误和测试相关的现有代码。

如果文件名或位置不同，使用现有文件，不要创建内容重复的第二份规范或交接文档。

### Phase 0B：先更新规范文档，暂不宣称代码已完成

代码修改前必须先完成以下文档变更：

1. 更新 `docs/backend-development-spec.md`：
   - 提升文档版本号；
   - 新增“决策支持”产品语义与边界；
   - 新增本文冻结的 API、Schema、Provider、音频生命周期、fallback 和测试要求；
   - 明确不复用 `capture_session`，不新增数据库表。
2. 更新现有后端交接文档：
   - 新增“Phase 7：有来源的决策支持”；
   - 此时状态写为 `Planned` 或 `In progress`；
   - 不得在代码和测试完成前写成“已实现”。
3. 更新 README 的待实现接口、环境变量和本地验证说明草案。
4. 如果 `AGENTS.md` 要求后端改动必须同步某些文档，补充本次必要入口；不要把本规范全文复制进 `AGENTS.md`。

完成 Phase 0B 后，先检查文档 diff，确认没有把“决策支持”写成无来源的 AI 顾问，再开始代码。

### Phase 1–5：实现与测试

按本文后续顺序实现。每个阶段结束后运行相关测试；不要等全部完成后才第一次测试。

### Phase 6：实现后再次回写文档

代码和测试完成后必须：

1. 把后端交接文档中 Phase 7 的状态改为真实状态；
2. 补充实际文件、API、配置、测试命令与结果；
3. 更新 README，使运行说明与真实代码一致；
4. 若实现与 Phase 0B 的规范有差异，先判断是实现错误还是规范需要调整，不能静默留下冲突；
5. 运行全量测试与依赖检查后再结束任务。

---

## 1. 为什么需要这次改动

现有后端已经完成：

```text
现场快速记
→ 活动后 AI 引导复盘
→ 用户确认个人经验
→ 按活动名称和自然语言困扰找回 1 条相似经验
```

但现有复用端只完成了“检索层”：

```text
activity_name + concern
→ 一条相似 experience
→ why_similar
```

这保住了经验来源，却没有完整兑现产品需求：后来的人往往不知道应该搜索什么，只知道自己被一个现场问题卡住了。她需要直接说出困境，让系统结合机构宗旨和真实前人经验，帮助她看见：

- 过去有人怎样处理；
- 当时发生了什么；
- 这个做法带来了什么效果和代价；
- 她现在可以考虑哪些有依据的方向；
- 哪些差异仍必须由她根据现场判断。

因此这次增加的不是通用聊天机器人，而是：

> **基于机构语境和有来源个人经验的一次性、结构化决策支持。**

---

## 2. 产品边界

### 2.1 必须做到

1. 用户可以通过语音优先、文字兜底的方式描述当前困境。
2. 系统读取后端预置的机构宗旨和工作原则。
3. 系统只从已确认的 `experiences` 中检索 1 条最相关个人经验。
4. 响应展示经验贡献者、日期、为什么相关和完整公开经验内容。
5. 最多给出 2 个“可考虑方向”，并展示可能代价。
6. 每个方向必须绑定检索到的经验 ID，不能无来源生成。
7. 返回 1 个“仍需本人判断的问题”。
8. 没有匹配经验时承认没有依据，不生成建议。
9. FakeAI 和确定性 fallback 必须可以离线跑通文字路径。

### 2.2 明确不做

- 不把 AI 包装成标准答案或组织权威；
- 不做开放式多轮顾问；
- 不自动生成完整活动方案；
- 不使用 RAG、向量数据库或新增检索基础设施；
- 不新增组织配置后台；
- 不新增 `decision_sessions` 表；
- 不保存求助录音、求助历史或模型原始响应；
- 不把求助内容写入 `capture_sessions`；
- 不把求助内容写入 `experiences`；
- 不改变既有捕捉、复盘、确认和检索 API 的行为；
- 不在本任务中实现前端。

---

## 3. 最重要的数据边界

### 3.1 可以复用

- 前后端 `multipart/form-data` 约定；
- `audio` 与 `text` 恰好提供一个的校验逻辑；
- 现有音频 MIME 白名单；
- 15 MiB 默认上限；
- UUID 文件名和路径安全校验；
- 现有同步 ASR Provider；
- 统一错误格式与错误码；
- 现有经验候选筛选、AI 排序和本地 fallback；
- 现有公开 `Experience` Schema。

### 3.2 绝对不能复用

决策支持请求不是经验捕捉会话，不得调用以下方式绕过新设计：

```http
POST /api/v1/capture-sessions
entry_mode=direct_reflection
```

也不得为求助创建：

- `capture_sessions` 数据库行；
- `conversation_json`；
- `draft_json`；
- `marked / reflecting / needs_confirmation / confirmed` 状态；
- 可被确认成经验的临时记录。

原因：求助者是在使用已有组织记忆，不是在贡献一条新经验。混用会污染“待复盘”、状态机和经验确认语义。

### 3.3 持久化决定

MVP 决策支持是一次无状态请求：

```text
输入 → 转写 → 检索 → 决策支持生成 → 返回
```

不新增数据库表，不做数据库迁移。

---

## 4. 新 API 契约

### 4.1 路径

```http
POST /api/v1/decision-support
Content-Type: multipart/form-data
```

### 4.2 请求字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `audio` | 与 `text` 二选一 | 用户描述困境的短语音 |
| `text` | 与 `audio` 二选一 | 文字输入、测试和 Demo fallback |
| `activity_name` | 是 | MVP 当前活动或主题，例如“亲子共读活动” |

规则：

- `audio` 与 `text` 必须恰好提供一个；
- `activity_name` 去首尾空白后必须非空；
- `text` 去首尾空白后必须非空；
- 音频使用现有 MIME、大小和路径安全规则；
- 不要手工解析 multipart boundary。

### 4.3 成功响应

```json
{
  "activity_name": "亲子共读活动",
  "concern_transcript": "现场很热闹，但几个孩子一直站在门口，我不知道该继续围坐还是让他们自由选书。",
  "understanding": "你在判断应该继续维持围坐秩序，还是先降低孩子进入活动的门槛。",
  "match": {
    "experience": {
      "id": "00000000-0000-0000-0000-000000000001",
      "activity_name": "亲子共读活动",
      "contributor_name": "吴瑶儿",
      "contributor_role": "乡村图书馆员",
      "context": "亲子共读活动中，三个孩子一直站在门口。",
      "action_and_reason": "判断围坐门槛较高，因此改为自由选书。",
      "observed_result": "孩子进入了活动，但现场变得更分散。",
      "went_well": "降低了第一次参加活动的孩子的参与门槛。",
      "shortcomings": "自由选择后缺少重新收拢现场的方法。",
      "things_to_note": "提前准备自由选择后的收拢方式。",
      "open_question": null,
      "recorded_at": "2026-08-29T10:00:00Z",
      "updated_at": "2026-08-29T10:30:00Z"
    },
    "why_similar": "两次活动中都出现了孩子停留在活动边缘、尚未进入主要活动区域的情况。"
  },
  "considerations": [
    {
      "direction": "可以考虑先提供自由选书等低门槛入口。",
      "tradeoff": "孩子可能更愿意进入，但现场也可能变得分散。",
      "basis_experience_id": "00000000-0000-0000-0000-000000000001"
    }
  ],
  "question_to_consider": "这些孩子是在犹豫是否参加，还是还没有理解活动规则？"
}
```

### 4.4 无匹配响应

无匹配仍返回 `200`：

```json
{
  "activity_name": "亲子共读活动",
  "concern_transcript": "……",
  "understanding": "……",
  "match": null,
  "considerations": [],
  "question_to_consider": null
}
```

无匹配时不要调用无来源建议生成，也不要返回通用处理方案。

---

## 5. Pydantic Schema

复用当前公开经验响应类型，不重新定义一套字段不同的经验对象。

新增等价模型：

```python
class DecisionConsideration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str
    tradeoff: str | None = None
    basis_experience_id: UUID


class DecisionSupportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_name: str
    concern_transcript: str
    understanding: str
    match: ExperienceMatchResponse | None
    considerations: list[DecisionConsideration]
    question_to_consider: str | None
```

对 `considerations` 增加长度限制：最多 2 条。

### 5.1 Provider 内部输出 Schema

不要让模型重新生成整条经验，也不要让模型选择新的经验 ID。经验匹配由现有检索服务决定。

建议 Provider 只输出：

```python
class DecisionConsiderationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str
    tradeoff: str | None = None
    basis_fields: list[
        Literal[
            "context",
            "action_and_reason",
            "observed_result",
            "went_well",
            "shortcomings",
            "things_to_note",
            "open_question",
        ]
    ]


class DecisionSupportAIResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    understanding: str
    considerations: list[DecisionConsiderationDraft]
    question_to_consider: str | None
```

服务层在输出公开响应时，为每个 consideration 写入已经选定的 `match.experience.id`，生成 `basis_experience_id`。模型不能控制公开来源 ID。

额外校验：

- `considerations` 最多 2 条；
- 每条 `basis_fields` 至少 1 项；
- `basis_fields` 只能引用所选经验中非空字段；
- 输出禁止额外字段；
- 空白字符串规范化为 `None` 或判为无效，遵守现有 Schema 风格。

---

## 6. AI Provider 改动

### 6.1 Protocol

在现有 `AIProvider` Protocol 增加等价方法：

```python
def support_decision(
    self,
    organization_context: str,
    concern: str,
    matched_experience: ExperienceCandidate,
) -> DecisionSupportAIResult:
    ...
```

不要修改现有：

- `transcribe()`；
- `advance_reflection()`；
- `rank_experiences()`。

### 6.2 FakeAIProvider

FakeAI 必须完全离线、确定性，并足以跑通文字 Golden Path。

建议规则：

1. `understanding` 保守改写用户困扰，不加入新事实；
2. 优先用 `action_and_reason` 生成第一个 `direction`；
3. 优先用 `shortcomings`，其次 `observed_result` 生成 `tradeoff`；
4. 若 `things_to_note` 非空且与第一条方向不同，可生成第二个方向；
5. 若 `open_question` 非空，将其作为 `question_to_consider`；
6. 否则使用保守问题：“你的现场与这条经验有哪些不同？”；
7. 缺失信息保持空，不编造。

### 6.3 DashScopeAIProvider

新增一次严格 JSON 的决策支持调用。Prompt 必须包含：

- 机构宗旨和工作原则；
- 用户当前困扰；
- 唯一允许使用的匹配经验；
- 允许引用的非空字段名；
- 最多 2 个考虑方向；
- 禁止生成候选经验中不存在的事实；
- 禁止使用“最佳实践”“一定应该”“组织标准答案”等表达；
- 最终判断属于用户本人；
- 没有依据时少输出或留空，而不是补齐。

沿用现有：

- 超时；
- 最多一次重试；
- JSON 解析；
- Pydantic `extra="forbid"`；
- 安全错误映射；
- 不记录模型原始响应。

---

## 7. 服务编排

新增独立的决策支持服务，例如：

```text
app/decision_support.py
```

如果现有工程命名和职责更适合放在其他位置，可以遵守仓库风格，但不能把所有逻辑写进路由。

推荐流程：

```python
def create_decision_support(...):
    concern = normalize_text_or_transcribe_audio(...)
    match = experience_service.search(activity_name, concern)

    if match is None:
        return no_match_response(...)

    try:
        ai_result = ai_provider.support_decision(
            organization_context=settings.demo_org_context,
            concern=concern,
            matched_experience=match.experience,
        )
        validated = validate_decision_support(ai_result, match.experience)
    except retryable_or_invalid_ai_error:
        validated = build_deterministic_fallback(concern, match.experience)

    return build_public_response(concern, match, validated)
```

### 7.1 检索复用

必须复用现有经验候选筛选、排序和 fallback，不复制第二套检索实现。

决策支持只能读取：

- 已确认的 `experiences`；
- 最多 20 条现有候选；
- 现有服务最终选出的 1 条匹配经验。

未确认的 `capture_sessions` 永远不能成为依据。

### 7.2 Provider 失败时的确定性 fallback

如果已经找到匹配经验，但决策支持 Provider 超时、异常或输出无效，不让整条 Demo 失败。

使用所选经验已有字段生成保守结果：

- `understanding`：用户困扰的保守复述；
- `direction`：优先取 `action_and_reason`，其次 `things_to_note`；
- `tradeoff`：优先取 `shortcomings`，其次 `observed_result`；
- `basis_experience_id`：服务层写入匹配经验 ID；
- `question_to_consider`：优先取 `open_question`，否则使用“你的现场与这条经验有哪些不同？”。

不得调用外部知识补写。

---

## 8. 音频生命周期与隐私

### 8.1 音频处理

决策支持语音与复盘回答语音的处理语义一致：只有拿到文字后才能继续，因此使用同步转写。

必须：

1. 复用现有音频写入、大小、MIME 和路径安全工具；
2. 使用服务端 UUID，不使用客户端文件名拼路径；
3. 音频只保存在配置的音频根目录内；
4. 在 `try/finally` 中清理临时文件和请求目录；
5. 转写成功后立即清理；
6. 转写失败或超时也尽力立即清理；
7. 不在日志中输出完整困扰、转写、音频路径、模型原始响应或 API Key；
8. 不把音频路径返回前端。

如果现有启动/CLI 清理只能根据 `capture_sessions` 找文件，应最小化扩展为也能清理决策支持临时目录中的孤儿文件；不新增数据库记录只为清理文件。

### 8.2 不保存求助历史

本次请求结束后，数据库中不能新增：

- `capture_sessions` 行；
- `experiences` 行；
- 任何决策支持会话行。

---

## 9. 配置

在现有 Settings 和 `.env.example` 增加：

```dotenv
DEMO_ORG_CONTEXT=本机构服务村庄儿童、青少年与妇女；活动设计应从当地需求和环境出发，保留一线工作者判断，不让 AI 替代当地经验。
```

要求：

- 这是非敏感演示配置；
- 后端读取，前端不提交；
- FakeAI 和真实 Provider 使用同一个设置入口；
- 不新增组织配置表或管理界面；
- 不在响应中完整回传系统 Prompt 或内部机构配置。

---

## 10. 错误处理

沿用现有统一错误格式：

```json
{
  "error": {
    "code": "TRANSCRIPTION_FAILED",
    "message": "语音转写失败，请重试或改用文字描述。",
    "retryable": true
  }
}
```

复用或补齐以下场景：

| HTTP | code | 场景 |
|---|---|---|
| 400 | `INPUT_REQUIRED` | audio/text 均未提供或同时提供 |
| 400 | `INVALID_INPUT` | activity_name 或 text 为空 |
| 400 | `AUDIO_TOO_LARGE` | 超过上限 |
| 400 | `UNSUPPORTED_AUDIO_TYPE` | MIME 不支持 |
| 502 | `TRANSCRIPTION_FAILED` | ASR 失败 |
| 504 | `AI_TIMEOUT` | 必须向前端暴露且无可用 fallback 的超时 |
| 500 | `STORAGE_ERROR` | 音频写入或必要清理失败 |

若已经有匹配经验，决策支持生成失败应优先使用确定性 fallback 并返回 `200`，而不是把可恢复的 AI 失败暴露给前端。

---

## 11. 推荐文件改动

以当前实际工程结构为准，预期最小改动包括：

```text
backend/app/
├── api/
│   └── decision_support.py        # 新路由
├── core/
│   └── config.py                  # DEMO_ORG_CONTEXT
├── ai.py                          # Protocol、FakeAI、内部 Schema
├── dashscope_provider.py          # 真实 Provider
├── decision_support.py            # 新服务编排
├── experience_services.py         # 仅在需要抽取可复用检索函数时小改
├── audio.py                       # 仅在需要通用临时清理 helper 时小改
├── schemas.py                     # 公开请求/响应 Schema
└── main.py                        # 注册路由

backend/tests/
└── test_decision_support.py

backend/.env.example
backend/README.md 或根 README.md
docs/backend-development-spec.md
backend-implementation-handoff.md
```

不要为了匹配建议目录而做无关重构。保持当前仓库的合并文件风格和职责边界。

---

## 12. 必须覆盖的测试

测试默认使用临时 SQLite、临时音频目录和 FakeAI，不访问真实网络。

### 12.1 API 与输入

1. 文字决策支持请求成功。
2. 音频决策支持请求通过注入转写结果成功。
3. audio/text 均缺失返回 `INPUT_REQUIRED`。
4. audio/text 同时提供返回 `INPUT_REQUIRED`。
5. activity_name 为空返回 `INVALID_INPUT`。
6. 不支持 MIME 和超大文件被拒绝。

### 12.2 数据边界

7. 请求前后 `capture_sessions` 行数不变。
8. 请求前后 `experiences` 行数不变。
9. 未确认会话永远不会成为匹配依据。
10. 无匹配时返回 `match: null`、空 considerations 和 null question。

### 12.3 来源与 AI 边界

11. 每个公开 `basis_experience_id` 都等于返回的匹配经验 ID。
12. considerations 最多 2 条。
13. Provider 引用空字段或非法字段时判为无效。
14. Provider 返回额外字段时判为无效。
15. Provider 失败或返回非法结构时使用确定性 fallback。
16. fallback 只使用匹配经验已有字段。
17. 无匹配时不调用决策支持 Provider。

### 12.4 音频和隐私

18. 音频转写成功后临时文件和目录被删除。
19. 音频转写失败后临时文件和目录也被删除。
20. 响应不包含文件路径、模型原始响应、内部 Prompt 或 API Key。
21. 日志不包含完整音频转写和敏感配置。

### 12.5 回归

22. 既有 capture/reflection/confirm Golden Path 全部继续通过。
23. 既有 `/experiences/search` 响应保持兼容。
24. 既有幂等确认、清理和 CORS 测试继续通过。

---

## 13. 实现顺序

严格按以下顺序：

### Phase 0：文档先行

- 更新后端规范、交接文档 planned 状态与 README 草案；
- 确认 API 和 Schema 与本文一致。

### Phase 1：文字路径与 Schema

- 新增公开 Schema；
- 新增路由和服务；
- 复用现有检索；
- 用 FakeAI 跑通文字请求；
- 覆盖数据不落库测试。

### Phase 2：确定性 fallback

- Provider 异常和非法输出测试；
- 用已有经验字段生成 fallback；
- 验证来源 ID。

### Phase 3：音频路径

- 复用同步 ASR；
- 接入临时文件清理；
- 覆盖成功和失败清理测试。

### Phase 4：真实 Provider

- DashScope 严格 JSON；
- 超时、一次重试和 Pydantic 校验；
- 默认测试不访问网络。

### Phase 5：全量验收

- 全量 `pytest -q`；
- `python -m pip check`；
- 手工走文字决策支持；
- 有真实密钥时再做一次真实语音与真实 Provider 冒烟测试。

### Phase 6：文档回写

- 交接文档改为真实完成状态；
- README 写入真实命令和示例；
- 记录最终测试数量、跳过项和限制。

---

## 14. 手工 Golden Path

先用文字路径验证：

```text
POST /api/v1/decision-support
activity_name=亲子共读活动
text=现场很热闹，但几个孩子一直站在门口，我不知道该继续围坐还是让他们自由选书

→ 返回 concern_transcript
→ 返回对困境的保守理解
→ 找回吴瑶儿的相似经验
→ 返回为什么相似
→ 返回最多 2 个有来源方向及代价
→ 返回 1 个仍需本人判断的问题
→ 数据库不新增任何记录
```

再验证无匹配：

```text
→ match = null
→ considerations = []
→ question_to_consider = null
→ 不调用无来源建议生成
```

最后才验证真实语音。

---

## 15. 完成标准

以下全部满足才算完成：

- [ ] 代码前已更新后端规范和交接文档 planned 状态；
- [ ] `/api/v1/decision-support` 出现在 OpenAPI；
- [ ] text/audio 二选一；
- [ ] activity_name 非空；
- [ ] 复用现有 ASR、音频安全和经验检索；
- [ ] 不创建 capture_session；
- [ ] 不写入 experience；
- [ ] 不新增数据库表；
- [ ] 只使用已确认经验；
- [ ] 最多 2 个 consideration；
- [ ] 每个方向绑定匹配经验 ID；
- [ ] 无匹配不生成建议；
- [ ] AI 失败有确定性 fallback；
- [ ] 音频成功或失败后均清理；
- [ ] FakeAI 文字路径完全离线；
- [ ] 既有测试全部通过；
- [ ] README、后端规范和交接文档与真实实现一致；
- [ ] 报告实际测试与真实 Provider 状态。

---

## 16. 完工回复格式

Codex 完成后必须按以下格式回复：

1. **文档先行结果**
   - 代码前更新了哪些文档；
   - 规范版本如何变化；
   - 交接文档的 Phase 7 状态如何变化。
2. **实现结果**
   - 决策支持文字、音频、检索、生成和 fallback 是否完成。
3. **主要文件**
   - 新增和修改的实际路径。
4. **API 契约**
   - 请求、响应和错误码。
5. **数据边界**
   - 证明没有新增表、capture_session 或 experience。
6. **AI 边界**
   - FakeAI、真实 Provider、来源校验和 fallback 状态。
7. **验证证据**
   - 实际运行命令；
   - 测试通过、失败和跳过数量；
   - `pip check` 结果；
   - 手工 Golden Path 结果。
8. **剩余限制**
   - 只列真实存在且影响 Demo 或部署的问题。

不得只回复“已完成”，也不得在没有运行测试时声称通过。
