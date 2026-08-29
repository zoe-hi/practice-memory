# 经验捕手前端

## 运行

```powershell
cd frontend
corepack pnpm install --frozen-lockfile
Copy-Item .env.example .env
corepack pnpm dev
```

本地前端地址为 `http://localhost:5173`；后端默认地址为
`http://127.0.0.1:8000/api/v1`。`.env` 仅存本地地址，不提交。

## 验证

```powershell
corepack pnpm typecheck
corepack pnpm build
```

## 联调优先级

整合分支优先使用真实 DashScope 验证单段浏览器 WebM 录音、动态复盘和一次性决策支持。
后端仍默认保留 FakeAI，供离线测试、文字 Golden Path 和真实服务失败时兜底。

“我的”是 MVP 的演示页面名称；当前没有登录、鉴权或用户级数据隔离，不应把该页面解释
为已经实现真实账户能力。录音只用于转写，并按后端清理策略删除。

主页语音采用“点击开始、再次点击结束”：结束后立即创建记忆 marker，并自动进入“我的”
待处理列表；后台转写未完成时列表显示“正在转写”。经验库的决策支持支持文字或单段语音
输入，语音查询是一次性的，不会创建 capture session 或写入经验库。真实语音路径需要后端
配置 DashScope；默认 FakeAI 只支持可确定的离线文字演示。

接口、错误处理和状态机以 `../docs/frontend-api-contract.md` 为准；原型业务清洗以
`../docs/frontend-prototype-cleanup-spec.md` 为准。
