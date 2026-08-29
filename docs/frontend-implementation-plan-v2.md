# 经验捕手｜前端实现阶段计划 v2

> **前置规格：**[`frontend-ui-interaction-spec-v2.md`](frontend-ui-interaction-spec-v2.md)  
> **目标：**将已确认的页面、交互和跳转实现为可演示的移动端 Web 前端。  
> **本阶段原则：**不修改后端接口、数据库、AI Provider 或 `.env`；现场真实链路只验收“一段语音”。

## 1. 本阶段交付边界

### 1.1 要交付的内容

```text
完整的页面结构与跳转
+ 四主题封面、主题详情、预置经验卡
+ 一段语音 / 一段文字的真实录入闭环
+ 转写检查、动态 AI 复盘、七字段经验卡确认
+ 我的记录与主题库中的真实展示
+ 决策支持底部抽屉
```

### 1.2 本阶段不做的内容

| 不做项 | 原因 |
|---|---|
| 修改数据库或创建 Activity / Marker 新模型 | 当前只做前端，不动后端基线 |
| 多段语音真实上传、替换、删除 | 是完整产品能力，不作为本次 Demo 的实现阻塞项 |
| 音频与文字补充同时写入同一会话 | 当前接口为二选一，不用前端假造能力 |
| 登录、多用户隔离、云端权限 | P0 使用单演示身份 |
| 主题库后端分类体系 | 四主题用前端演示数据展示；真实新经验默认归入儿童活动引导 |
| 新装框架或路由库 | 不需要；使用现有 React/Vite 和显式页面状态即可 |

## 2. 当前可复用基础

### 2.1 已有前端基础

| 位置 | 可复用内容 |
|---|---|
| `src/App.tsx` | 手机壳、一级底部导航 |
| `src/pages/CapturePage.tsx` | 浏览器录音、上传、轮询转写、AI 问答、草稿编辑的已有实现 |
| `src/pages/MyRecordsPage.tsx` | 待处理与已确认经验列表读取 |
| `src/pages/ExperienceLibraryPage.tsx` | 经验列表与决策支持请求 |
| `src/api/` | 统一 API Client、类型、错误对象和 capture 接口 |
| `src/imports/` | 已导出的图标、吉祥物和视觉素材 |

### 2.2 已有后端接口（只使用，不改动）

```text
POST  /capture-sessions
GET   /capture-sessions/{id}
PATCH /capture-sessions/{id}
POST  /capture-sessions/{id}/start-reflection
POST  /capture-sessions/{id}/turns
PATCH /capture-sessions/{id}/draft
POST  /capture-sessions/{id}/confirm

GET   /capture-sessions
GET   /experiences
POST  /decision-support
```

## 3. 前端架构决定

不增加 React Router。根组件维护显式页面状态，流程页只携带 `sessionId`。

```ts
type AppScreen =
  | { name: "capture" }
  | { name: "review"; sessionId: string }
  | { name: "reflection"; sessionId: string }
  | { name: "card"; sessionId: string }
  | { name: "success"; experienceId: string }
  | { name: "my" }
  | { name: "theme-home" }
  | { name: "theme-detail"; themeId: ThemeId }
  | { name: "experience-detail"; experienceId: string; origin: "my" | "theme" };
```

### 3.1 页面恢复规则

刷新或从“我的”恢复时：

```text
读取 sessionId
→ GET /capture-sessions/{id}
→ 根据后端 status 跳转：

marked              → review
reflecting          → reflection
needs_confirmation  → card
confirmed           → my / experience detail
failed              → my（显示失败与重试）
```

前端不能只根据内存推测流程状态。

### 3.2 推荐目录调整

```text
frontend/src/
├─ api/                         # 保留为唯一请求入口
├─ components/
│  ├─ AppShell.tsx
│  ├─ BottomNav.tsx
│  ├─ TopBar.tsx
│  ├─ ExperienceCardView.tsx
│  └─ VoiceRecordRow.tsx
├─ features/
│  ├─ capture/
│  │  ├─ CaptureHome.tsx
│  │  ├─ PendingReview.tsx
│  │  └─ useRecorder.ts
│  ├─ reflection/ReflectionPage.tsx
│  ├─ experience/
│  │  ├─ ExperienceCardEditor.tsx
│  │  └─ SaveSuccessPage.tsx
│  ├─ library/
│  │  ├─ ThemeHome.tsx
│  │  ├─ ThemeDetail.tsx
│  │  ├─ DecisionSupportSheet.tsx
│  │  └─ demoThemeData.ts
│  └─ mine/MyRecords.tsx
├─ lib/
│  ├─ experience.ts
│  ├─ navigation.ts
│  └─ format.ts
└─ App.tsx
```

这只是前端代码拆分，不改变任何 API 或后端模型。

## 4. 实施顺序

## Phase 0：建立前端实现基线

**目的：**明确新规格覆盖旧页面逻辑，避免继续在单个 `CapturePage.tsx` 上堆条件判断。

工作：

1. 以 `frontend-ui-interaction-spec-v2.md` 作为页面唯一事实来源；
2. 在代码中建立 `AppScreen` 与导航函数；
3. 明确一级页与流程页的导航显示规则；
4. 不删除现有页面，先迁移后再由用户决定清理旧代码。

完成条件：

```text
App 可以在所有目标页面之间进行静态跳转；
页面状态由一个集中位置管理；
流程页不显示底部导航。
```

## Phase 1：先完成静态页面与四主题展示

**目的：**先让完整产品结构、视觉与跳转可以被审阅，再接真实接口。

工作：

1. 实现 A–H 的页面外壳、顶部栏、底部导航和返回关系；
2. 在 `demoThemeData.ts` 写四个主题的数据；
3. 每个主题预置 2～3 张明确标记为演示用途的经验卡；
4. 实现主题首页 → 主题详情 → 经验详情；
5. 实现保存成功页的两个出口；
6. 实现决策支持底部抽屉的视觉与开关。

此阶段允许使用演示卡数据，但不得把它们当作刚刚录音生成的经验。

完成条件：

```text
四主题都有可点封面、详情和经验卡；
11 张原型截图所表达的主要页面可在本地完整走通；
保存成功页、我的、主题库的出口均正确。
```

## Phase 2：接入“记一下 → 待整理”的真实单段输入

**目的：**让 Demo 的开头不是假页面。

工作：

1. 复用 `MediaRecorder`，实现点击开始、再次点击停止；
2. 一段录音停止后，在前端显示本段时长和“语音记录 1”；
3. 点击“活动完成，去整理”时调用 `POST /capture-sessions`；
4. 语音上传后轮询 `GET /capture-sessions/{id}`；
5. 待整理页显示“正在转写”或可编辑转写；
6. 文字模式走同一待整理页面；
7. 保存 `sessionId`，使刷新后可以恢复。

本阶段 Demo 规则：

```text
页面结构可保留未来多段记录的视觉表达；
真实提交只创建一条语音记录；
不接删除、替换、第二段录音的真实接口。
```

完成条件：

```text
浏览器录一段 webm
→ 后端转写
→ 待整理页可编辑转写文本
→ 刷新页面后仍可继续。
```

## Phase 3：接入 AI 复盘与经验卡确认

**目的：**跑通产品最重要的“记录变经验”闭环。

工作：

1. 待整理页点击 AI 复盘，调用 `start-reflection`；
2. 根据 `next_question` 动态渲染问答流，不在 UI 写死题数；
3. 支持文字回答；语音回答复用现有录音工具；
4. 收到 `draft` 与 `needs_confirmation` 后跳转经验卡确认页；
5. 渲染 7 个可编辑字段；
6. 保存草稿、确认经验；
7. 确认成功进入保存成功页，并同步刷新“我的”与儿童活动引导主题。

完成条件：

```text
一段语音
→ 真实 AI 追问
→ 草稿
→ 编辑七字段
→ 确认
→ 我的和主题库都能看到新经验。
```

## Phase 4：接入我的记录与待处理恢复

**目的：**让用户能够中途退出，不丢失工作。

工作：

1. 调用会话列表，显示待整理、正在复盘、待确认经验卡；
2. 点击不同状态的记录，按 `status` 恢复到 B、C 或 D 页；
3. 调用经验列表，显示最近确认经验与详情；
4. 对失败、网络异常、AI 超时给出保留输入的错误提示。

完成条件：

```text
在待整理、复盘、经验卡任意阶段刷新或切至「我的」；
重新进入后仍回到正确步骤。
```

## Phase 5：接入决策支持与视觉收口

**目的：**完成“沉淀经验后，还能回到现场辅助判断”的第二条价值链。

工作：

1. 主题库浮标打开 / 关闭底部抽屉；
2. 用当前主题与用户困扰调用 `POST /decision-support`；
3. 显示当前困扰、历史经验、限制和开放判断问题；
4. 无匹配时只显示“暂未找到相似经验”；不生成通用建议；
5. 按原型对齐卡片间距、阴影、图标、固定按钮与小屏滚动。

完成条件：

```text
从儿童活动引导主题输入现场困扰
→ 得到有来源的历史经验参考
→ 关闭抽屉后仍停留在原主题页。
```

## 5. 验收清单

### 5.1 页面和跳转

- [ ] 记一下空状态、录音中、已录音状态完整；
- [ ] 待整理、AI 复盘、经验卡、保存成功均有明确返回关系；
- [ ] 我的可以恢复未完成会话；
- [ ] 四主题均有主题详情、演示经验列表和详情；
- [ ] 决策支持为底部抽屉，不跳独立页。

### 5.2 真实 Demo 主路径

- [ ] 浏览器麦克风录一段音频；
- [ ] 音频成功转写，并能手动修正；
- [ ] AI 问答根据后端返回继续或结束；
- [ ] 七字段经验卡可编辑；
- [ ] 确认后能在“我的”和儿童活动引导主题看到新卡。

### 5.3 失败与边界

- [ ] 拒绝麦克风权限时可以改用文字；
- [ ] 录音过大或类型不支持时显示明确提示；
- [ ] 转写、AI 或网络失败时不丢失输入；
- [ ] 未确认草稿不展示为正式经验；
- [ ] 决策支持无匹配时不编造建议。

## 6. 版本管理规则

1. 一个 Phase 完成后先本地构建和手工验收；
2. 查看 `git diff`，确认只包含本 Phase 文件；
3. 由用户决定是否 `git add`、`commit`、`push`；
4. 不把 `.env`、本地 SQLite、音频、缓存或运行目录加入版本控制。

## 7. 立即开始的工作

下一次编码从 **Phase 0 + Phase 1** 开始：

```text
先完成导航状态、流程页壳、四主题静态内容与所有页面跳转；
暂不接入录音和 AI。
```

这样可以先对照原型审阅完整体验，再接单段语音的真实接口，避免在业务流程未定时反复拆改。

