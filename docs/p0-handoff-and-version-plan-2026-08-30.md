# 经验捕手｜P0 交接与版本管理清单（2026-08-30）

## 1. 当前交付状态

- 工作分支：`feat/frontend-golden-path`。
- P0 场景：儿童阅读活动；外部名称：经验捕手。
- 用户已完成并确认通过：
  1. 浏览器真实语音/文字快速记到待整理；
  2. 待整理的转写核对与编辑；
  3. AI 复盘、文字/语音回答、草稿生成；
  4. 经验卡确认、我的记录、主题库、决策支持。
- 当前阶段停止真实模型调用，避免继续消耗额度；后续日常页面开发使用 `AI_PROVIDER=fake`。

## 2. P0 用户闭环与状态

```text
记一下（文字或单段 WebM 语音）
  → 待整理（查看 / 修正转写）
  → AI 复盘（动态追问，最多五问）
  → 可编辑七字段经验卡
  → 确认保存
  → 我的 / 主题库 / 决策支持
```

后端状态：

```text
marked → reflecting → needs_confirmation → confirmed
```

关键恢复规则：

- `marked`：显示待整理，用户可开始复盘；
- `reflecting`：恢复问题、回答和输入区，不重新启动复盘；
- `needs_confirmation`：直接恢复可编辑经验卡；
- `confirmed`：显示在“我的”和儿童活动引导主题中；
- 本地保存的会话 ID 如已不存在，自动清除本地恢复标记并返回记录页。

## 3. 已完成的前后端契约

| 能力 | 接口 / 处理 |
|---|---|
| 创建快速记 | `POST /capture-sessions`，文字与语音二选一 |
| 修正初始转写 | `PATCH /capture-sessions/{id}` |
| 开始 / 恢复复盘 | `POST /start-reflection`；已在 reflecting 状态时先读取详情恢复 |
| 文字或语音回答 | `POST /turns` |
| 修正已提交文字回答 | `PATCH /turns/{turn_id}`；自动丢弃旧后续追问并重新生成 |
| 编辑草稿 / 确认 | `PATCH /draft`、`POST /confirm` |
| 我的记录与主题库 | `GET /experiences`、`GET /capture-sessions` |
| 决策支持 | `POST /decision-support`，仅显示有来源历史经验 |

## 4. 页面跳转约定

| 页面 | 主要返回 / 退出行为 |
|---|---|
| 待整理 | 返回“记一下”；会话已经在后端保存 |
| AI 复盘 | 返回待整理；再次进入时恢复当前问答，不重复创建 AI 会话 |
| 经验卡 | 返回“我的”前先保存七字段草稿 |
| 主题详情 | 返回主题库 |
| 经验详情 | 返回其来源页面：我的或主题详情 |
| 我的 | 待处理、已整理均可展开并点击具体记录 |

## 5. 本次提交应包含的文件

### 后端 AI 与回答修正

```text
backend/app/ai.py
backend/app/api/capture_sessions.py
backend/app/dashscope_provider.py
backend/app/schemas.py
backend/app/services.py
backend/tests/conftest.py
backend/tests/test_dashscope_provider.py
backend/tests/test_reflection.py
```

### 前端与接口文档

```text
frontend/src/App.tsx
frontend/src/api/capture.ts
frontend/src/pages/DemoFrontend.tsx
docs/frontend-api-contract.md
docs/frontend-prototype-mapping.md
docs/frontend-implementation-plan-v2.md
docs/frontend-ui-interaction-spec-v2.md
docs/p0-handoff-and-version-plan-2026-08-30.md
```

`AGENTS.md` 已在本地更新供 Codex 协作恢复，但受仓库 `.gitignore` 规则保护，不纳入 Git 提交。

## 6. 明确不纳入本次提交

```text
.env / SQLite 数据库 / storage 音频 / dist
backend/.acli/
backend/.tmp/
prototype/
跳转顺序与页面/
docs/开发交接说明-前后端联调-v1.md
```

`docs/activity-multi-marker-api-contract-v1.md` 与旧版交接材料保留为历史讨论，不应当作本次 P0 的多段录音实现承诺。

## 7. 后续建议（不在当前提交内）

1. 清理演示数据库中的重复、错误测试经验；执行前必须逐条确认删除清单。
2. 按原型做视觉收尾：卡片间距、插图、空态、错误态。
3. 如需部署，再补生产 CORS、静态前端地址、演示数据库和额度保护策略。

## 8. 已知约束

- 页面可以表达“活动中持续记录”的产品概念，但可运行 Demo 只上传一段音频；不要把多段音频上传扩展为当前阻塞项。
- P0 只对儿童阅读活动做真实数据闭环；四个主题卡仍保留为主题库界面结构。
- 未确认草稿不得进入决策支持或经验检索。
- 不提交、不推送，等待负责人审阅本清单和 Git diff 后再执行版本动作。
