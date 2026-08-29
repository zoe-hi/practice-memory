# 经验捕手前端

## 运行

```powershell
cd frontend
pnpm install
Copy-Item .env.example .env
pnpm dev
```

本地前端地址为 `http://localhost:5173`；后端默认地址为
`http://127.0.0.1:8000/api/v1`。`.env` 仅存本地地址，不提交。

## 实现顺序

1. 文字快速记；
2. 动态 AI 复盘与七字段草稿；
3. 确认入库、我的记录、经验库；
4. 一次性决策支持；
5. 单段浏览器 WebM 录音。

接口、错误处理和状态机以 `../docs/frontend-api-contract.md` 为准；原型业务清洗以
`../docs/frontend-prototype-cleanup-spec.md` 为准。
