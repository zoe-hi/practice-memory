# 经验捕手｜前端 API 契约 v1

> **用途：**前端开发的接口与状态事实来源。当前工作分支为 `feat/frontend-golden-path`。运行后仍以
> `http://127.0.0.1:8000/openapi.json` 为准。

## 1. 通用约定

- API 前缀：`/api/v1`；本地完整地址：`http://127.0.0.1:8000/api/v1`。
- JSON 请求使用 `application/json`；文字/音频录入使用 `FormData`。
- 对 `FormData` 不手工设置 `Content-Type`，浏览器会自动附带 boundary。
- 成功时间字段为 UTC ISO 8601；前端只负责本地显示格式化。
- 统一错误：

```json
{"error":{"code":"AI_TIMEOUT","message":"AI 服务响应超时，请重试。","retryable":true}}
```

- `retryable: true` 可展示“重试”；`false` 展示说明并保留用户已输入文字。

## 2. 会话状态与页面状态

| 后端状态 | 页面应展示 | 主要动作 |
|---|---|---|
| `marked` | 已记录，等待开始复盘 | `start-reflection` |
| `reflecting` | AI 问题与输入框 | 提交 `turns` |
| `needs_confirmation` | 可编辑经验草稿 | `PATCH draft`、`confirm` |
| `confirmed` | 已存入经验库 | 查看经验详情 / 返回列表 |
| `failed` | 失败原因与重试入口 | 依错误码重试或改文字 |

刷新页面后：先调用 `GET /capture-sessions/{id}`，再根据 `status` 恢复页面；不能自行推断。

## 3. 快速记与复盘

### 3.1 创建快速记

`POST /capture-sessions`，返回 `201`。

`FormData` 字段：

| 字段 | 规则 |
|---|---|
| `text` | 与 `audio` 二选一；推荐先实现 |
| `audio` | 与 `text` 二选一；接受 `webm/mp4/m4a/mp3/wav`，最多 15 MiB |
| `activity_name` | 可选；P0 默认可预填“亲子共读活动” |
| `entry_mode` | 默认 `marker`；P0 页面不主动使用 `direct_reflection` |

成功后保存响应 `id` 并跳转会话详情。音频初始转写是后台任务：创建成功并不代表
`marker_transcript` 已立刻可用；页面应重新读取详情或提示“正在转写”。

### 3.2 列表、详情与初始转写修正

```text
GET   /capture-sessions?status=marked&limit=20
GET   /capture-sessions/{session_id}
PATCH /capture-sessions/{session_id}
```

会话详情的关键字段：`id`、`activity_name`、`marker_transcript`、`status`、
`conversation`、`draft`、`can_confirm`、时间字段。

`PATCH /capture-sessions/{id}` 使用 JSON；只提交发生变化的 `activity_name` 或
`marker_transcript`。它用于用户修正 ASR 初始转写，不用于改复盘回答。

### 3.3 开始复盘与回答

```text
POST /capture-sessions/{id}/start-reflection
POST /capture-sessions/{id}/turns
PATCH /capture-sessions/{id}/turns/{turn_id}
```

- 开始复盘不带请求体；响应包含 `status`、可空 `next_question`、可空 `draft`。
- 回答使用 `FormData`，仅传 `text` 或 `audio`；返回值额外包含 `answer_transcript`。
- `next_question` 有值时继续展示问题；`draft` 有值且状态为 `needs_confirmation` 时切换到草稿页。
- UI 不预设题目数量，完全根据响应切换；AI 仅针对缺失字段继续追问，通常三至五轮，后端硬上限为五问。
- 已提交的**文字**回答可通过 `PATCH /capture-sessions/{id}/turns/{turn_id}` 修正：
  请求体为 `{"text":"修正后的回答"}`。后端会保留修正前的上下文、删除该答案之后
  基于旧内容产生的追问/回答，并重新返回下一问或经验草稿。前端不能仅在本地改气泡文字。
- 语音回答如需修正，P0 采用“改用文字回答修正”的方式；不提供历史音频覆盖。

### 3.4 编辑与确认草稿

```text
PATCH /capture-sessions/{id}/draft
POST  /capture-sessions/{id}/confirm
```

草稿 JSON 可部分提交，字段仅限七个经验字段。确认请求：

```json
{"contributor_name":"当前演示贡献者","contributor_role":"乡村图书馆员"}
```

首次确认返回 `201`；重复点击确认返回同一经验和 `200`。前端确认按钮应在请求中禁用，
但即使网络重试也不应提示“重复创建”。

## 4. 经验库与检索

```text
GET  /experiences?activity_name=亲子共读活动&limit=20
GET  /experiences/{experience_id}
POST /experiences/search
```

搜索 JSON：

```json
{"activity_name":"亲子共读活动","concern":"孩子站在门口，没有进入活动"}
```

搜索结果为 `{ "match": null }` 或：

```text
match.experience       已确认经验的七字段、贡献者、时间、id
match.why_similar      匹配原因
```

前端不得在 `match` 为 `null` 时自行生成建议。

## 5. 有来源的决策支持

`POST /decision-support`，使用 `FormData`：

| 字段 | 规则 |
|---|---|
| `activity_name` | 必填、非空 |
| `text` / `audio` | 恰好一个 |

响应：

```text
concern_transcript     当前输入或 ASR 转写
understanding          当前输入的规范化文本，不是历史事实摘要
match                  null 或一条历史经验与 why_similar
considerations         最多 2 条 { direction, tradeoff, basis_experience_id }
question_to_consider   可空，留给用户本人判断
```

显示规则：

1. 当前困扰只显示 `concern_transcript` / `understanding`。
2. 历史经验在独立卡片显示，标注“来自过往经验”。
3. `considerations` 必须显示为“可参考的历史做法 / 已记录的限制”，不能写成 AI 指令。
4. `question_to_consider` 显示为开放问题，不展示为标准答案。
5. 无匹配时只显示“暂未找到相似经验”，不补充通用方案。

## 6. 错误处理最小映射

| code | 前端动作 |
|---|---|
| `INPUT_REQUIRED` / `INVALID_INPUT` | 保留输入，在表单旁提示修正 |
| `INVALID_STATE` | 刷新会话详情并按最新状态跳转 |
| `TRANSCRIPTION_FAILED` | 提示重试音频或改文字输入 |
| `AI_TIMEOUT` | 显示重试按钮，保留文字草稿 |
| `AI_INVALID_OUTPUT` | 显示“AI 暂未完成整理，请重试” |
| `AUDIO_TOO_LARGE` / `UNSUPPORTED_AUDIO_TYPE` | 在上传控件旁提示限制 |
| `SESSION_NOT_FOUND` / `EXPERIENCE_NOT_FOUND` | 跳回列表并提示记录不存在 |
| `TURN_NOT_FOUND` / `INVALID_TURN` | 刷新会话详情；提示该条回答已不再可修改 |

## 7. 前端不得依赖或展示的内容

- API Key、`.env`、服务器文件路径、`file://` URI；
- 模型原始输出、内部 Prompt、草稿 `source_turn_ids`、`warnings`；
- 未确认经验作为经验库内容；
- 由前端自行拼出的来源、AI 结论或状态转换。
