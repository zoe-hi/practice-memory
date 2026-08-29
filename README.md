# Practice Memory / 经验捕手

当前后端已覆盖规范中的 Phase 1–6：文字/音频记忆标记、待复盘列表、
多轮复盘、音频回答、草稿修改、幂等确认，以及可选的阿里云 DashScope
真实 ASR/大模型 Provider，并支持经验列表、详情、带本地 fallback 的相似检索和
过期未确认会话清理。

## Windows 本地运行

```powershell
cd backend
$python311 = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
& $python311 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

健康检查：`GET http://localhost:8000/api/v1/health`。

## 测试

测试使用临时 SQLite 数据库、临时音频目录和离线 `FakeAIProvider`，不访问网络。

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

macOS/Linux 可将创建虚拟环境命令替换为 `python3.11 -m venv .venv`，并使用
`source .venv/bin/activate` 激活。

## Demo 路径

通过 multipart `text` 或 `audio` 字段创建 `/api/v1/capture-sessions`，随后调用
`start-reflection`、两次 `turns`、`draft` 和 `confirm` 接口即可完成复盘闭环。
`turns` 同样支持 `text` 或 `audio` 二选一。

允许的音频 MIME 为 `audio/webm`、`audio/mp4`、`audio/x-m4a`、`audio/mpeg`
和 `audio/wav`，默认大小上限为 15 MiB。初始音频在确认后清理，回答音频在转写后立即清理。

`.env.example` 默认使用 `AI_PROVIDER=fake`，不需要 API Key、不会访问网络，也不会
猜测未知音频内容；无真实 ASR 时请使用文字 fallback。

## 经验库与检索

在 `backend/` 中显式导入 6 条脱敏 Demo 经验：

```powershell
.\.venv\Scripts\python.exe -m app.seed
```

种子使用固定 UUID，重复运行只跳过已有记录，不覆盖用户数据。应用启动时不会自动
导入种子。经验库接口为：

```text
GET  /api/v1/experiences?activity_name=亲子共读活动&limit=20
GET  /api/v1/experiences/{experience_id}
POST /api/v1/experiences/search
```

搜索请求示例：

```json
{
  "activity_name": "亲子共读活动",
  "concern": "现场很热闹，但总有孩子站在门口"
}
```

FakeAI 使用确定性的文字重合评分。DashScope 只允许从后端提供的最多 20 条候选中
选择；真实排序超时、失败、输出非法或选择候选外 ID 时会自动使用相同本地评分，
不会中断 Demo。

## 过期会话清理

应用会在数据库建表完成后、开始接收请求前清理一次已过期且未确认的会话。清理顺序是
先删除对应音频目录，再删除数据库行；若音频清理失败，会话会保留并安全标记为
`failed` / `STORAGE_ERROR`，供下次重试。已确认经验与尚未过期的会话不会被删除。

运行期间需要再次清理时，在 `backend/` 显式执行：

```powershell
.\.venv\Scripts\python.exe -m app.cleanup
```

命令输出 `deleted`、`failed`、`skipped` 汇总；存在失败时退出码非零。MVP 不包含应用内
定时器，周期调用由部署环境负责。

## 配置与部署

`CORS_ORIGINS` 必须包含至少一个合法的 HTTP/HTTPS Origin，多个值用逗号分隔；生产
环境禁止 `*`。MVP 不使用 Cookie，CORS 仅允许 `GET`、`POST`、`PATCH`、`OPTIONS`
以及 `Accept`、`Content-Type` 请求头。`LOG_LEVEL` 可设为 `DEBUG`、`INFO`、
`WARNING`、`ERROR` 或 `CRITICAL`，默认 `INFO`。

部署保持单 FastAPI 实例、单 worker，并将 SQLite 数据库和 `storage/audio` 放在持久化
磁盘。应用日志只记录生命周期和清理汇总，不记录 API Key、完整转写、模型原文或音频路径。

## DashScope 真实 Provider

将 `.env` 中的配置改为：

```dotenv
AI_PROVIDER=dashscope
AI_API_KEY=你的服务端密钥
AI_BASE_URL=https://dashscope.aliyuncs.com/api/v1
AI_MODEL=qwen-plus
AI_ASR_MODEL=qwen3-asr-flash
AI_TIMEOUT_SECONDS=75
AI_MAX_RETRIES=1
```

API Key 与 Base URL 必须属于同一地域；使用 workspace 地址时用对应的 HTTPS
`/api/v1` 地址覆盖 `AI_BASE_URL`。真实 Provider 会把内部临时音频作为本地
`file://` URI 交给 Qwen-ASR，并要求 Qwen 返回严格 JSON；输出仍会经过 Pydantic
和会话 turn 来源校验。Provider 错误不会向 API 响应暴露密钥、文件路径或模型原文。

默认测试只使用离线适配器。只有显式设置 `RUN_REAL_AI_TESTS=1` 和 `AI_API_KEY`
时，才会运行会消耗真实额度的 DashScope 冒烟测试：

```powershell
$env:RUN_REAL_AI_TESTS = "1"
$env:AI_API_KEY = "你的测试密钥"
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashscope_provider.py -q
```
