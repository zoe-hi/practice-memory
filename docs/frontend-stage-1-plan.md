# 经验捕手｜前端阶段 1 启动计划

> **分支：**`feat/frontend-golden-path`
> **起点：**`p0-backend-handoff-v1`
> **目的：**在写任何业务页面前，让新版原型、当前后端与团队协作规则一致。

## 1. 当前事实与不可改变的边界

| 项目 | 当前决定 |
|---|---|
| P0 场景 | 儿童阅读活动，默认活动名为“亲子共读活动” |
| 初始输入 | 文字或单段音频，二选一；当前后端不支持多段音频与文字补充同时提交 |
| AI 复盘 | 后端动态返回问题与结束状态；前端不得写死题目或题数 |
| 经验卡 | 七字段草稿，可编辑；确认后才进入经验库 |
| 经验库 | 普通经验卡列表，不做正例、反例、支持、不确定等分类 |
| 决策支持 | 一次性、有来源的结构化结果；不是连续聊天 |
| 用户体系 | 单演示身份；无登录、无个人隔离、无权限系统 |

## 2. 阶段 1 的交付物

1. 本文件：启动边界与任务顺序；
2. `docs/frontend-prototype-cleanup-spec.md`：原型遗留逻辑的逐页删除/替换清单；
3. 更新后的本地 `AGENTS.md`：开发约束、目录与验证命令；
4. 现有 `docs/frontend-api-contract.md` 作为唯一接口契约；
5. 前端目录设计确认，但**此阶段不创建 `frontend/` 业务代码**。

## 3. 分步执行

### 3.1 原型业务清洗

对 `prototype/` 做一次阅读和映射，不删除源文件、不改视觉素材。输出每一页保留什么、
删什么、最终接哪个接口。

完成条件：原型中不再有任何 P0 会误解为真实能力的旧概念。

### 3.2 确定前端目录与责任边界

后续创建 `frontend/` 时固定采用：

```text
frontend/
├─ src/api/          # API client、请求/响应类型、错误映射
├─ src/features/     # capture、reflection、experience、decision 四个领域
├─ src/pages/        # 页面组合与路由
├─ src/components/   # 复用 UI 组件
├─ src/lib/          # 日期格式、录音、纯工具
└─ README.md         # 启动、环境、联调与验收
```

规则：页面不能各自复制 `fetch`、接口类型或错误处理；所有 API 请求从 `src/api/` 发出。

### 3.3 前端实现拆分（阶段 1 后执行）

```text
A. 文字 Golden Path
   快速记 → 待整理 → 动态复盘 → 草稿编辑 → 确认 → 我的记录

B. 经验库与决策支持
   已确认经验列表/详情 → 一次性决策支持结果

C. 单段浏览器 WebM 录音
   MediaRecorder → audio/webm → 后端上传/转写 → 同一复盘链路
```

## 4. 每次开发前后的固定检查

开发前：

```powershell
git status --short --branch
git log --oneline -3
```

后端联调前：

```powershell
conda activate railway-rag
cd backend
python -m pytest -q
uvicorn app.main:app --reload --port 8000
```

前端开始后再补充其启动、构建与测试命令。`.env`、密钥、数据库、音频与运行缓存不加入 Git。

## 5. 阶段 1 完成定义

- [ ] 所有原型旧概念都有明确的保留、删除或替换决定；
- [ ] 前端只以当前后端 API 契约为准；
- [ ] 团队成员知道首个可联调目标是文字 Golden Path；
- [ ] 前端分支已从冻结标签创建；
- [ ] 未创建任何假接口、假 AI 返回或假录音功能。
