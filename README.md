# Practice Memory｜经验捕手

一个面向一线实践者的经验沉淀工具：在活动现场快速留下一段语音或文字线索，活动后由 AI 引导复盘，经本人确认后成为可检索、可追溯的个人经验。

## 核心创新

- **把记录与复盘分开**：现场录音只是“记忆标记”，停止录音即保存，不要求使用者当场整理完整故事。
- **从完整对话还原经验**：AI 围绕标记继续追问，从整段复盘中整理情境、行动、结果与反思，而不是把一句录音直接包装成结论。
- **由人决定什么值得留下**：AI 只负责转写、澄清和结构化；只有贡献者修改并明确确认的内容，才会进入经验库。
- **让经验回到下一次判断中**：遇到相似困扰时，系统找回一条已确认经验，并展示有来源的做法、限制和开放问题，不生成“标准答案”。
- **保留不确定性**：没有被实践者表达的事实保持为空，个人经验不会被放大成组织规则。

## Demo 流程

```text
语音 / 文字记一下
→ AI 引导复盘
→ 生成经验草稿
→ 本人修改并确认
→ 存入经验库
→ 在相似现场中被重新找回
```

当前 Demo 聚焦儿童阅读活动，支持文字与浏览器录音。录音仅用于转写，并按后端清理策略删除。“我的”是演示视角，不代表已实现登录或用户隔离。

## 技术栈

- 前端：React、TypeScript、Vite
- 后端：FastAPI、SQLAlchemy、SQLite
- AI：离线 `FakeAIProvider`，或可选的阿里云 DashScope ASR / 大模型

## 本地运行

后端（Python 3.11+）：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

前端：

```powershell
cd frontend
corepack pnpm install --frozen-lockfile
Copy-Item .env.example .env
corepack pnpm dev
```

打开 `http://localhost:5173`。默认使用 FakeAI，可直接演示确定性的离线文字流程；真实语音转写需在 `backend/.env` 中配置 DashScope。

如需预置 Demo 经验：

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.seed
```

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
corepack pnpm typecheck
corepack pnpm build
```

详细产品与接口约束见 [`docs/backend-development-spec.md`](docs/backend-development-spec.md) 和 [`docs/frontend-api-contract.md`](docs/frontend-api-contract.md)。
