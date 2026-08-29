# 经验捕手｜原型—页面—接口映射 v2

> **状态：**已根据 `prototype/` 源码逐页核对。后端联调基线为
> `integration/backend-ai-hardening` 的 `546df09`；运行时仍以
> `http://127.0.0.1:8000/openapi.json` 为准。
>
> **本文件解决的问题：**UI 原型描述“用户想怎样操作”，后端描述“系统现在真实能做什么”。
> 前端实现以二者交集为 P0，不能把原型中的假数据、假 AI 对话或未实现能力当成已可用功能。

## 1. 原型源码事实

原型目录：`prototype/`。它是 React + Vite + TypeScript + Tailwind 的静态交互原型，
主要页面为：

```text
App.tsx
├─ Capture.tsx   记一下：记录 → 待整理 → AI 复盘 → 卡片 → 成功
├─ Themes.tsx    主题库、卡片详情、决策支持抽屉
└─ Mine.tsx      我的：待整理、已整理、最近经验
```

当前源码全部使用 `useState`、`SEED_CARDS`、`DRAFT` 和写死文案模拟数据，**没有调用后端 API，
也没有浏览器真实录音**。它的职责是说明界面和跳转，不是可交付前端。

## 2. P0 的真实用户闭环

```text
文字快速记（先完成） / 单段浏览器录音（第二步）
  → 创建 capture session
  → 待整理：检查或修正转写
  → 开始 AI 复盘
  → 根据后端返回的问题逐轮回答
  → 得到可编辑的 7 字段草稿
  → 确认并存入经验库
  → 在“我的经验”查看已确认卡片
  → 输入当前困扰，获得有来源的历史经验参考
```

这是“不断更新的组织记忆”的最小闭环：新记录经确认后进入经验库，之后又可作为决策支持的历史来源。

## 3. 原型与后端的差异，以及 P0 处理决定

| 原型现状 | 后端事实 | P0 前端决定 |
|---|---|---|
| 一次活动可录多段语音，同时可写文字补充 | `POST /capture-sessions` 要求 `text` 与 `audio` **恰好一个**；一次会话只接收一份初始输入 | 首版只允许“文字记录”或“一段语音记录”二选一；录完可在上传前重新录制。多段录音合并后置。 |
| 复盘页写死三个问题 | `start-reflection` / `turns` 动态返回 `next_question`；通常三至五轮、硬上限五问 | 不在前端预设题目、进度或结束条件；以 `status`、`next_question`、`draft` 驱动页面。 |
| 卡片有 6 个字段，“反思与注意”合在一起 | 草稿与经验有 7 个独立字段 | 保留视觉风格，但卡片必须展示/编辑 7 项；拆为“反思与局限”“下次注意”。 |
| 主题库有 4 个主题、支持经验/反例/未知三类 | P0 后端只围绕儿童阅读活动；没有主题表、模块字段或聚合统计 | 底部“主题库”改名为“经验库”；只展示儿童阅读活动的确认经验。多主题与三类聚合后置。 |
| 决策支持是可连续聊天、页面自行写“2 条支持经验、1 条反例” | `/decision-support` 是一次请求：最多一条相似经验、最多两条有来源参考、一个开放问题 | 保留抽屉视觉；每次提交得到一张结果，不伪造多轮聊天、数量或反例标签。 |
| “我的”写死阿雅、个人网络和待整理 0 条 | 无登录/鉴权/真实用户隔离；能列会话和经验 | Demo 中显示“当前演示贡献者”，但不能声称账号个人化；待整理数和已整理列表接真实接口。 |
| `Login.tsx` 但 App 未接入 | 后端没有登录接口 | P0 隐藏登录页，不接入。 |

## 4. 页面、状态和接口映射

### 4.1 “记一下”｜`Capture.tsx`

| 用户动作 | 前端请求 | 成功后 | 必须有的状态 |
|---|---|---|---|
| 输入文字并提交 | `POST /capture-sessions`，`FormData{text, activity_name}` | 保存 `session_id`，进入待整理 | 输入为空、提交中、网络失败、可重试 |
| 点击开始录音、再次点击结束 | 浏览器 `MediaRecorder` 生成一个 `audio/webm`；`POST /capture-sessions`，`FormData{audio, activity_name}` | 进入待整理；后台转写完成前轮询会话详情 | 麦克风拒绝、录制中、上传中、转写中、转写失败、超 15 MiB |
| 修改活动名（可选） | 随创建请求提交或 `PATCH /capture-sessions/{id}` | 更新显示 | P0 默认：`亲子共读活动` |

**录音交互采用“点击开始、点击结束”，不是长按。**后端只接收最终音频文件，不关心按钮形式。

### 4.2 “待整理”｜原型 `pending`

```text
GET /capture-sessions/{session_id}
  status=marked 且 marker_transcript 已有值 → 显示并允许修正
  status=marked 但音频尚未转写完 → 显示“正在转写”，轮询详情
  PATCH /capture-sessions/{session_id} → 保存修正后的 marker_transcript
  POST /capture-sessions/{session_id}/start-reflection → 进入复盘
```

原型的“多段语音列表”在 P0 改成“一条原始语音 / 一段原始文字”。原始音频不在前端保存，也不显示伪波形。

### 4.3 “AI 复盘”｜原型 `debrief`

```text
POST /capture-sessions/{id}/start-reflection
  → status=reflecting + next_question

POST /capture-sessions/{id}/turns
  FormData{text} 或 FormData{audio}，二选一
  → next_question 有值：继续复盘
  → status=needs_confirmation + draft 有值：进入经验草稿
```

页面保留已问问题和用户回答的对话记录，但问题文本、题数、结束提示均由后端响应决定。

### 4.4 “经验卡片”｜原型 `card`

| API 字段 | 前端标签 |
|---|---|
| `context` | 发生了什么 |
| `action_and_reason` | 我做了什么调整 |
| `observed_result` | 观察到的结果 |
| `went_well` | 似乎有效 |
| `shortcomings` | 反思与局限 |
| `things_to_note` | 下次注意 |
| `open_question` | 还不确定 |

```text
PATCH /capture-sessions/{id}/draft
POST  /capture-sessions/{id}/confirm
```

空字段显示“暂未记录”或折叠，不由前端补写。确认成功后以返回的经验对象渲染成功页。

### 4.5 “我的” → “我的记录”｜`Mine.tsx`

| 区块 | 真实数据来源 | P0 呈现 |
|---|---|---|
| 待整理 | `GET /capture-sessions?status=marked&limit=20` | 显示数量和可继续的会话；不再固定为 0。 |
| 已整理/最近经验 | `GET /experiences?activity_name=亲子共读活动&limit=20` | 显示已确认经验卡；点击取 `GET /experiences/{id}`。 |
| 个人头像、职业、实践网络 | 当前无 API | 用“演示身份”静态显示或暂时隐藏；不可宣传为真实账户体系。 |

### 4.6 “主题库” → “经验库”与决策支持｜`Themes.tsx`

P0 不实现 4 个主题、主题计数、新手任务、`support/counter/unknown` 标签或跨主题聚合；这些都没有对应后端事实。

保留原型中的卡片列表与“决策支持”抽屉：

```text
POST /decision-support
FormData{activity_name, text} 或 FormData{activity_name, audio}
```

结果固定分四层显示：

1. **当前困扰**：`concern_transcript` / `understanding`；
2. **来自过往经验**：`match.experience` 和 `match.why_similar`；无匹配时只显示“暂未找到相似经验”；
3. **可参考的已记录做法与限制**：`considerations`，每条显示 `basis_experience_id`；
4. **留给实践者的问题**：`question_to_consider`。

不得改写为“AI 建议你必须……”，不得虚构“相关经验有 2 条”或“有 1 条反例”。

## 5. 前端实现顺序（已按风险排序）

```text
1. 将原型页面拆为真实的路由/组件，先不接录音
2. 打通文字 Golden Path：快速记 → 复盘 → 草稿编辑 → 确认 → 我的记录
3. 打通真实经验库与一次性决策支持
4. 接入浏览器 MediaRecorder，验证 webm 上传、转写与失败状态
5. 补齐手机端加载、空、错误、重试、刷新恢复
6. 视觉细节与 Demo 固定数据收口
```

第 2 步完成前，不做多段录音合并、登录、主题系统或决策支持多轮聊天。

## 6. 需要与 UI 设计师确认的四个小改动

1. 将底部“主题库”在 P0 改名为“经验库”；
2. 将记录入口改为“文字 / 单段语音二选一”，删除或灰化“继续补充一段”；
3. 将经验卡从 6 块改为 7 块，新增“下次注意”；
4. 将 AI 复盘的固定 `1/3`、固定问题列表改为“AI 正在追问关键信息”的动态样式。

这些不是推翻视觉设计，而是让视觉设计与已验证的后端能力一致。多主题、多段录音和连续决策对话可作为下一轮产品路线，不进入本次 P0 的承诺范围。
