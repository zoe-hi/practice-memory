# 经验捕手实现交接文档

> 文档日期：2026-08-29  
> 实现基线：`integration/frontend-backend`
> 规范基线：`docs/backend-development-spec.md` v1.6
> 适用范围：黑客松 MVP、单演示身份、单实例部署

## 1. 当前结论

后端 Phase 1–6 已完成，文字版 Golden Path 可完全离线运行：

```text
创建记忆标记
→ 开始多轮复盘
→ 生成草稿
→ 用户修改草稿
→ 幂等确认经验
→ 查询经验详情
→ 搜索并找回相似经验
```

音频上传、临时存储、转写、失败重试和清理路径已经实现。默认使用
`FakeAIProvider`，不会访问网络；可切换到阿里云 DashScope Provider。默认测试不调用
真实服务；本地测试账号已额外验证真实 Provider、文字/手机 MP3 决策支持和两轮复盘链路。

仓库现已包含 `frontend/` React/TypeScript/Vite 移动端 Demo，覆盖文字/单段语音标记、
动态复盘、七字段草稿、确认、“我的”、经验库和文字/语音决策支持。整合阶段优先验证真实
DashScope 音频路径；FakeAI 继续用于离线回归和文字兜底。

Phase 7“有来源的决策支持”已经完成。文字路径可完全离线运行；音频路径使用同步 ASR
并在成功、失败或超时后清理。决策支持是一次无状态读取，不会创建捕捉会话或经验。

## 2. 已冻结的产品语义

后续开发必须继续保持以下不变量：

- 初始语音或文字只是一条记忆标记，不是完整经验，也不能直接等同于 `context`。
- 完整经验必须从初始标记和全部复盘问答共同整理。
- AI 可以转写、追问、结构化和排序，但不能补写用户没有表达的事实。
- 未知字段保持 `null`；个人经验不能被表述成组织规则或普遍结论。
- 决策支持的 `concern_transcript` 与公开 `understanding` 只表示当前输入；历史经验只在
  `match.experience` 中展示，不能被写成当前现场事实。
- 决策支持 `direction` 只能逐字取自历史经验的 `action_and_reason` 或 `things_to_note`；
  非空 `tradeoff` 只能逐字取自 `shortcomings` 或 `observed_result`。模型改写、拼接、伪造
  动作或声明无关来源时，服务层必须回退到确定性结果。
- 只有贡献者主动确认后的记录才进入 `experiences` 表和经验检索候选。
- 一个捕捉会话最多生成一条经验，重复确认必须返回同一经验。
- `experiences` 不保存 `capture_session_id`。
- 追问目标为两轮，服务层硬上限为三问。
- 服务器音频路径、API Key、模型原始响应和内部来源映射不得返回前端。

## 3. 已实现能力

| 阶段 | 已实现内容 | 状态 |
|---|---|---|
| Phase 1 | FastAPI 应用、Pydantic 配置、SQLite/SQLAlchemy、统一错误、健康检查、测试夹具 | 完成 |
| Phase 2 | 文字标记、列表/详情、转写修正、多轮 FakeAI 复盘、草稿修改、幂等确认 | 完成 |
| Phase 3 | 安全音频上传、后台初始转写、同步重试、音频回答、隐私优先清理 | 完成 |
| Phase 4 | DashScope Qwen-ASR、Qwen 结构化复盘、严格校验、超时/重试/错误映射 | 完成；默认不启用，已在本地测试账号实测 |
| Phase 5 | 6 条幂等种子经验、经验列表/详情、本地匹配、DashScope 候选排序与 fallback | 完成 |
| Phase 6 | 启动清理、清理 CLI、严格 CORS、安全日志、最终文档和验收 | 完成 |
| Phase 7 | 无状态决策支持：文字/音频困扰、单条已确认经验、最多两个逐字有来源方向与 fallback | 完成；默认不启用，已在本地测试账号实测 |

Phase 7 实际边界：新增 `POST /api/v1/decision-support` multipart 接口；不复用或创建
`capture_sessions`，不写入 `experiences`，不新增数据库表。无匹配经验时不生成建议；
每个方向的公开来源 ID 由服务层绑定到返回的同一条经验；服务层还会验证方向、代价和
声明字段逐字对应，违规模型输出使用确定性 fallback。已新增 `DEMO_ORG_CONTEXT`，并复用
现有音频安全、同步 ASR、经验检索和统一错误能力。

## 4. 实际工程结构

```text
backend/
├── app/
│   ├── api/
│   │   ├── capture_sessions.py    # 捕捉/复盘/确认路由
│   │   ├── decision_support.py    # 无状态决策支持路由
│   │   ├── experiences.py         # 经验列表、详情、检索路由
│   │   └── health.py              # 健康检查
│   ├── core/
│   │   ├── config.py              # 环境变量与启动校验
│   │   ├── errors.py              # 统一错误响应
│   │   └── logging.py             # 安全应用日志
│   ├── db/
│   │   ├── base.py
│   │   └── session.py             # Engine、Session、SQLite 外键
│   ├── ai.py                      # Provider Protocol、FakeAI、通用异常
│   ├── audio.py                   # 音频存储与路径安全
│   ├── cleanup.py                 # 过期清理服务与 CLI
│   ├── dashscope_provider.py      # DashScope SDK 边界和真实 Provider
│   ├── decision_support.py        # 来源校验、编排和确定性 fallback
│   ├── experience_services.py     # 经验读取和检索服务
│   ├── main.py                    # 应用工厂、生命周期、CORS
│   ├── matching.py                # 确定性本地匹配
│   ├── models.py                  # 两张 SQLAlchemy 表
│   ├── repositories.py            # 数据访问
│   ├── schemas.py                 # 严格 Pydantic 契约
│   ├── seed.py                    # 6 条幂等种子经验
│   └── services.py                # 捕捉、复盘、草稿和确认业务
├── tests/                         # 90 个通过、1 个条件跳过
├── .env.example
└── requirements.txt
```

实际实现为了避免过多小文件，把模型、Schema 和主要业务分别合并在少数模块中；职责
边界仍然可以独立测试。

## 5. 公开 API

统一前缀：`/api/v1`。JSON 字段使用 `snake_case`，时间返回 UTC ISO 8601。
FastAPI 默认文档可通过 `/docs` 和 `/openapi.json` 查看。

| 方法 | 路径 | 实际用途 | 主要状态码 |
|---|---|---|---|
| GET | `/api/v1/health` | 健康检查 | 200 |
| POST | `/api/v1/capture-sessions` | 以 multipart `text` 或 `audio` 创建标记 | 201 |
| GET | `/api/v1/capture-sessions` | 可按 `status` 查询会话摘要，默认 20 条 | 200 |
| GET | `/api/v1/capture-sessions/{session_id}` | 获取会话、完整消息和公开草稿 | 200/404 |
| PATCH | `/api/v1/capture-sessions/{session_id}` | 修改活动名称或初始转写 | 200 |
| POST | `/api/v1/capture-sessions/{session_id}/start-reflection` | 开始复盘并获取下一问或草稿 | 200 |
| POST | `/api/v1/capture-sessions/{session_id}/turns` | 以 multipart `text` 或 `audio` 回答 | 200 |
| PATCH | `/api/v1/capture-sessions/{session_id}/draft` | 部分修改草稿正文 | 200 |
| POST | `/api/v1/capture-sessions/{session_id}/confirm` | 确认并创建经验 | 首次 201，重复 200 |
| GET | `/api/v1/experiences` | 经验列表；支持 `activity_name` 和 `limit` | 200 |
| GET | `/api/v1/experiences/{experience_id}` | 已确认经验详情 | 200/404 |
| POST | `/api/v1/experiences/search` | 按活动名称和困扰检索一条经验 | 200 |
| POST | `/api/v1/decision-support` | 以 multipart `text` 或 `audio` 获取一次有来源决策支持 | 200/400/502/504 |

创建标记和提交回答时，`text` 与 `audio` 必须恰好提供一个。`limit` 范围为
1–100。搜索请求的 `activity_name` 与 `concern` 必须为非空文字。决策支持要求
`activity_name` 非空且 `text`/`audio` 恰好一个；无匹配仍返回 200，但不生成方向。

统一错误格式：

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "当前会话不能执行此操作。",
    "retryable": false
  }
}
```

已覆盖的主要错误码包括 `INPUT_REQUIRED`、`INVALID_INPUT`、
`INVALID_DRAFT`、`SESSION_NOT_FOUND`、`EXPERIENCE_NOT_FOUND`、
`INVALID_STATE`、`AUDIO_TOO_LARGE`、`UNSUPPORTED_AUDIO_TYPE`、
`TRANSCRIPTION_FAILED`、`AI_INVALID_OUTPUT`、`AI_TIMEOUT` 和
`STORAGE_ERROR`。

## 6. 会话状态机

```text
marked → reflecting → needs_confirmation → confirmed
                  ↘
                   failed
```

- `marker` 模式创建后为 `marked`。
- `direct_reflection` 模式创建后为 `reflecting`，允许首次调用
  `start-reflection` 生成问题。
- 只有 `reflecting` 可以提交回答。
- 只有 `needs_confirmation` 可以首次确认。
- 已确认会话重复确认会返回原经验，不会重复插入。
- 初始音频缺失等不可恢复错误会进入 `failed`；临时 AI/ASR 失败通常保留原状态并允许重试。

每条会话消息包含：`turn_id`、`role`、`kind`、`text`、`source` 和
`created_at`。消息被完整保存在 `conversation_json`，草稿来源只允许引用合法 turn ID
或 `manual_edit`。

## 7. 数据持久化

应用使用 SQLite 和 SQLAlchemy 2.x。启动时调用 `create_all`，没有 Alembic。
SQLite 连接启用 `foreign_keys=ON` 和 `check_same_thread=False`。

### `capture_sessions`

保存临时捕捉和复盘状态，包括：

- 入口模式、活动名称、初始转写和内部音频路径；
- 状态、完整 `conversation_json` 和内部 `draft_json`；
- `confirmed_experience_id` 幂等关联；
- 安全错误码/信息；
- 创建、更新和过期时间。

### `experiences`

只保存已经确认的个人经验，包括：

- 活动和贡献者信息；
- `context`、`action_and_reason`、`observed_result`；
- `went_well`、`shortcomings`、`things_to_note`、`open_question`；
- 记录和更新时间。

表中没有 `capture_session_id`，也不保存音频、会话、来源映射或模型原文。

## 8. AI Provider 状态

### FakeAIProvider

- 默认启用，完全离线、确定性，适合测试和 Demo。
- 固定先询问结果，再询问做得好、不足和提醒，随后生成保守草稿。
- 只对测试 Golden Path 中明确识别的事实结构化，无法确认的信息保持 `null`。
- 使用中文双字片段和字母数字词重合进行本地经验排序。
- 默认不能猜测音频内容；没有注入测试转写时，音频 ASR 会安全失败，因此无真实
  Provider 时应使用文字 fallback。
- 决策支持会保守复述困扰，只从匹配经验的行动、结果、不足、提醒和问题生成最多两个
  方向；公开来源 ID 仍由服务层统一写入。

### DashScopeAIProvider

- ASR 默认模型：`qwen3-asr-flash`，通过官方
  `MultiModalConversation` 同步调用。
- 复盘和检索默认模型：`qwen-plus`，通过 `Generation` 请求严格 JSON。
- 本地音频先经过存储根目录校验，再转换为 `file://` URI。
- 复盘请求包含完整有序会话、当前草稿、问题数和合法 turn ID，不包含密钥或内部音频路径。
- 输出经过 JSON 解析、Pydantic `extra="forbid"`、来源 turn 和候选 ID 双重校验。
- 网络错误、429、5xx、超时和首次非法结构最多重试一次；确定性 4xx 不重试。
- 检索 Provider 失败或返回候选外 ID 时，服务层自动回退到本地排序；Provider 合法
  返回 `null` 时尊重“无匹配”。
- 决策支持 Prompt 只包含机构语境、当前困扰、唯一匹配经验和可引用非空字段；严格
  JSON 输出不能选择经验 ID，非法输出最终由服务层确定性 fallback。

真实服务冒烟测试只有同时设置 `RUN_REAL_AI_TESTS=1` 和 `AI_API_KEY` 才会执行。

## 9. 音频与隐私生命周期

- 允许 MIME：`audio/webm`、`audio/mp4`、`audio/x-m4a`、`audio/mpeg`、
  `audio/wav`。
- 默认上限 15 MiB，以 1 MiB 分块流式写入。
- 服务端生成 session UUID 和文件 UUID，不使用客户端文件名。
- 所有解析路径必须位于配置的音频根目录内。
- 初始音频先落盘和入库，再由 FastAPI `BackgroundTasks` 转写。
- 后台转写不会覆盖用户已经手工修正的转写。
- 开始复盘时若转写缺失但音频存在，会同步重试。
- 回答音频转写成功后立即删除；转写失败或超时也会尽力立即删除并要求重新上传。
- 决策支持音频保存在 `decision-support-{server_uuid}` 请求目录，使用同步转写，并在
  成功、失败或超时后清理；启动/CLI 会清理崩溃遗留目录。
- 确认事务成功后清理整个会话音频目录；清理失败不会回滚已确认经验。
- 过期未确认会话由启动清理或清理 CLI 删除；清理失败时保留数据库行并标记
  `failed/STORAGE_ERROR`，供下一次重试。

## 10. 经验库与检索

`python -m app.seed` 会写入 6 条固定 UUID、固定 UTC 时间的脱敏经验。脚本幂等，
重复运行只跳过已存在主键，不覆盖用户数据，应用启动时不会自动 seed。

检索流程：

1. 活动名称执行 Unicode NFKC、`casefold`、去首尾和合并空白。
2. 优先规范化精确匹配；无结果才进行双向包含匹配。
3. 候选按 `recorded_at DESC, id ASC` 排序，最多 20 条。
4. Provider 只能从候选中选择；服务层再次验证候选 ID。
5. AI 排序异常时使用确定性本地词汇重合评分。
6. 本地零重合返回 `match: null`，同分保留候选顺序。

未确认的 `capture_sessions` 永远不会成为搜索候选。

## 11. 配置

复制 `backend/.env.example` 为 `backend/.env`。主要变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `development` | `production` 时禁止 CORS `*` |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLite 数据库地址 |
| `AUDIO_STORAGE_DIR` | `./storage/audio` | 临时音频根目录 |
| `MAX_AUDIO_BYTES` | `15728640` | 音频上限，默认 15 MiB |
| `SESSION_TTL_HOURS` | `24` | 未确认会话过期时间 |
| `CORS_ORIGINS` | `http://localhost:5173` | 逗号分隔的 HTTP/HTTPS Origin |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `AI_PROVIDER` | `fake` | `fake` 或 `dashscope` |
| `AI_API_KEY` | 空 | DashScope 模式必填，只保存在后端 |
| `AI_BASE_URL` | DashScope 公共 API | DashScope 模式必须是合法 HTTPS URL |
| `AI_MODEL` | `qwen-plus` | 复盘和检索模型 |
| `AI_ASR_MODEL` | `qwen3-asr-flash` | 转写模型 |
| `AI_TIMEOUT_SECONDS` | `75` | Provider 超时 |
| `AI_MAX_RETRIES` | `1` | 仅允许 0 或 1 |
| `DEMO_CONTRIBUTOR_NAME` | `吴瑶儿` | 当前仅作为演示配置 |
| `DEMO_CONTRIBUTOR_ROLE` | `乡村图书馆员` | 当前仅作为演示配置 |
| `DEMO_ORG_CONTEXT` | 演示机构宗旨 | 仅由后端传给决策支持 Provider，不回传前端 |

DashScope 模式缺少密钥、模型名或合法 HTTPS Base URL 时，应用构造阶段会失败。
CORS 不允许用户信息、路径、查询和 fragment；应用不使用 Cookie，
`allow_credentials=False`，只允许 `GET/POST/PATCH/OPTIONS` 和
`Accept/Content-Type`。

## 12. 本地运行与运维命令

Windows：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

测试、种子和清理：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m app.seed
.\.venv\Scripts\python.exe -m app.cleanup
```

清理命令输出 `deleted`、`failed`、`skipped`。存在清理失败时退出码非零。应用只在
启动时自动清理一次，运行期间没有内置定时器。

部署必须保持单 FastAPI 实例、单 worker，并把 SQLite 和音频目录放在持久化磁盘。

## 13. 已验证内容

最近一次完整验收结果：

```text
python -m pytest -q
101 passed, 1 skipped, 2 warnings

python -m pip check
No broken requirements found.

TestClient GET /api/v1/health
200 {"status": "ok"}

python -m app.seed（临时数据库）
Seeded 6 new experiences.

python -m app.cleanup（临时数据库）
Cleanup deleted=0 failed=0 skipped=0.
```

默认跳过的 1 项是需要真实 DashScope 密钥和显式开关的网络冒烟测试。本次整合验收环境
未设置开关、进程密钥或 `backend/.env`，因此未调用真实服务；此前真实服务结果属于队友
报告的手工验证，仍需在当前整合分支复验。两条已知警告
来自 Starlette TestClient/httpx 兼容提示，以及 DashScope SDK 导入已弃用
Assistants API 的提示；当前实现未使用 Assistants API。

测试覆盖包括：

- 数据库初始化、健康检查和统一错误；
- 文字/音频标记、MIME/大小/路径、后台转写与失败重试；
- 完整会话、两轮 FakeAI 成稿、三问硬上限和来源映射；
- 手工草稿修改、确认事务、重复及并发确认幂等；
- 种子数据、经验列表/详情、候选筛选、本地/AI 检索 fallback；
- 启动/CLI 过期清理、清理失败重试；
- CORS 配置、预检和日志敏感信息不泄露。
- 决策支持文字/音频、零写入、无匹配、严格来源、Provider fallback 和临时音频清理。
- 真实 Provider 的 JSON 包装兼容、两轮成稿目标、第三问硬上限、空草稿拒绝和来源校验。

手工 TestClient 决策支持结果：健康检查 200，OpenAPI 包含新接口；文字困扰命中经验
`00000000-0000-4000-8000-000000000501` 并返回 2 个来源方向；无匹配返回 null/空列表，
且没有再次调用生成；数据库行数从 `(capture_sessions=0, experiences=6)` 到 `(0, 6)`。

队友报告的本地真实服务验收曾覆盖：DashScope Provider 冒烟、文字决策支持、手机 MP3
的 ASR→检索→决策支持→临时音频清理，以及“开始复盘→两轮回答→非空草稿”。当前整合
分支改变了第三问容错，必须重新执行真实验证；真实模型草稿仍属于待确认内容。

## 14. 前端整合状态

前端已位于仓库根目录 `frontend/`。当前整合规则：

1. 配置 API Base URL，例如开发环境 `http://localhost:8000/api/v1`。
2. 将前端开发 Origin 加入后端 `CORS_ORIGINS`。
3. 真实联调优先验证 DashScope WebM 转写、动态复盘和决策支持；FakeAI 文字链路保留兜底。
4. 创建标记和提交回答必须使用 `multipart/form-data`，不要手工设置 multipart boundary。
5. 页面刷新后通过会话列表/详情恢复状态，不依赖纯前端内存。
6. 根据 `status` 控制操作：`marked` 开始复盘，`reflecting` 回答，
   `needs_confirmation` 编辑/确认，`confirmed` 查看结果。
7. 对统一 `error.code` 和 `retryable` 做 UI 分支；ASR/AI 超时允许重试。
8. 前端不得请求或展示内部音频路径、草稿来源映射、warnings 或未确认经验。
9. 确认按钮允许安全重试；后端会返回相同经验。
10. 经验搜索只展示后端返回的已确认经验和 `why_similar`。
11. 决策支持使用 multipart `activity_name` 和 `text`/`audio` 二选一；只展示后端返回的
    匹配经验、来源方向、代价和本人判断问题，不把它呈现为组织标准答案。
12. 页面名称“我的”是明确的 MVP 演示决定；当前没有登录或用户级隔离，不得声称
    “仅自己可见”或真实账户归属。
13. 主页初始语音停止后直接创建 marker 并跳转“我的”；`marked` 且转写为空时展示
    “正在转写”，不等待后台 ASR，也不增加额外的“活动完成”确认动作。
14. 决策支持前端支持文字和单段浏览器录音；语音查询仍是一次性、无状态调用。

前端验证命令：

```powershell
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm typecheck
corepack pnpm build
```

## 15. 尚未实现和真实限制

以下内容不应在交接时误认为已经完成：

- 前端尚无自动化组件/E2E 测试；当前已通过 TypeScript 严格检查和生产构建。
- 没有登录、认证、用户隔离、权限模型或真实身份管理。
- 没有 Alembic；现有数据库 Schema 变更需要人工策略，不能依靠 `create_all` 升级旧表。
- 没有容器、CI/CD、部署清单、反向代理或 HTTPS 配置。
- 没有多实例、队列或分布式锁；SQLite 只支持当前单实例、单 worker 约束。
- 没有应用内周期调度；部署方需要定期执行 `python -m app.cleanup`。
- 没有经验编辑、删除、版本历史、游标分页或全文/向量数据库。
- 没有上传音频时长和真实媒体内容校验；当前只校验 MIME 与字节大小。
- 没有速率限制、配额、生产监控平台或完整结构化审计日志。
- 默认 FakeAI 无法转写真实音频；真实音频 Demo 需要 DashScope 配置。
- 默认自动化验收仍不调用真实 DashScope；部署前仍需在目标地域、额度和账号权限下复验。
- 决策支持不保存请求历史，也不支持多轮追问；这是当前冻结的无状态 MVP 边界。
- 后端依赖仍使用受控版本范围；前端已提交 pnpm lockfile 并固定 Corepack pnpm 版本。

## 16. 接手后的首轮检查清单

```text
[ ] 阅读 docs/backend-development-spec.md 和本文档
[ ] 从 backend/.env.example 创建本地 backend/.env
[ ] 确认 backend/.env、数据库、音频和虚拟环境未被 Git 跟踪
[ ] 安装依赖并运行 python -m pip check
[ ] 运行 python -m pytest -q
[ ] 启动 API 并访问 /api/v1/health 和 /docs
[ ] 运行 python -m app.seed 准备 Demo 数据
[ ] 用文字路径手工走一遍 Golden Path
[ ] 若启用 DashScope，先在测试账号验证 ASR、复盘和检索
[ ] 运行前端 typecheck/build，并用浏览器走一遍“停止录音→我的正在转写→复盘”的 Golden Path
[ ] 用浏览器验证决策支持语音输入的转写、匹配、结果展示和临时音频清理
[ ] 部署时确认单 worker、持久化磁盘、CORS 和 cleanup 调度
```

若后续实现改变 API、数据字段、状态机或产品语义，应同时更新
`docs/backend-development-spec.md`、本文档和对应测试。
