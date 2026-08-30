# 迹忆

基层与公益组织真正难以交接的，不是正式流程，而是一线工作者在具体情境中形成的判断、调整、有效做法和失败教训。这些经验常停留在个人记忆、聊天记录和零散文档中，随着人员离开而消失。

**「迹忆」是一款面向基层公益组织的一线经验捕捉与决策支持工具。**

工作人员可以在经验刚刚发生时，用一句语音或文字留下轻量标记；活动结束后，AI 通过针对性追问帮助还原当时的情境、行动理由、结果与反思。经本人修改确认后，个人的做法、教训与提醒以经验卡片留存，逐渐生长为团队记忆。

当后来者遇到相似问题时，「迹忆」不会给出脱离现场的标准答案，而是带回有来源的历史经验、结果、代价与待判断问题，支持使用者结合当前情境作出决定。

## 核心流程

1. **现场留痕：**用一句语音或文字，捕捉即将消失的判断。
2. **活动后还原：**AI 针对性追问，帮助补齐情境、行动理由与结果。
3. **沉淀经验：**卡片留存，让个人的做法、教训与提醒生长为团队记忆。
4. **支持判断：**行动前找回相似经验，理解别人怎么做、为什么，以及结果和代价。

## 创新点

### 1. 捕捉经验即将消失的时刻

传统知识库依赖人们事后撰写完整文档，「迹忆」允许用户先留下一条轻量记忆标记，避免把忙碌的一线工作者变成文档员。

### 2. 提取隐性判断，而非摘要已有材料

AI 不只是整理一段文字，而是根据已有信息动态追问，帮助用户说出情境、行动理由、结果、做得好与不足、提醒和开放问题——这些通常正是正式报告中最容易缺失的内容。

### 3. 经验不等于“最佳实践”

「迹忆」不仅保存成功做法，也保留未奏效的尝试、付出的代价、具体情境和仍未解决的问题。个人经验不会被包装成普遍规律，更不会直接变成组织标准答案。

### 4. 从经验存档走向有来源的决策支持

经验不是被动躺在资料库中。当新的问题出现时，系统会从已确认的历史经验中找回相关做法、结果和代价，并标明来源，让过去的一线经验真正参与下一次判断。


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
