# IBKR Trade Journal

一个可运行的本地交易复盘系统第一版：
- 后端：Django + DRF + SQLite
- 前端：Vue 3 + Vite
- 数据源：本地 mock IBKR executions JSON（后续可替换成真实 IBKR/Flex/CSV）

## 功能
- 全量同步 mock IBKR executions
- 去重写入 SQLite
- 支持重复同步、同步中断后重跑的幂等逻辑
- 基于 fills 生成 trade groups
- 支持 open / partial / closed 状态
- Dashboard / Trades / Sync / Daily Review 页面

## 目录
- `backend/` Django API
- `frontend/` Vue 前端
- `docs/` 设计说明

## 后端启动
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 前端启动
```bash
cd frontend
npm install
npm run dev
```

前端默认访问：
- `http://127.0.0.1:5173`

后端默认访问：
- `http://127.0.0.1:8000`

## 同步测试
启动后访问前端 Sync 页面，点击 **Start Full Sync**。

后端也可直接调用：
```bash
curl -X POST http://127.0.0.1:8000/api/syncs/ibkr/start/
```

## 说明

真实同步使用 IBKR Flex Web Service。默认使用 Client Portal 中保存的 Flex Query
Period，只提交一次报告请求。请在 Portal 中把 Period 设置为所需的完整范围。

只有确实需要由后端覆盖日期时，才设置下面的可选环境变量。后端会按照 IBKR 单次
最多 365 天的限制分段请求、合并并按 execution 去重：

```bash
# 可选；不设置时使用 Portal Query Period
IBKR_FLEX_HISTORY_YEARS=4
IBKR_FLEX_USER_AGENT=IBKRTradeJournal/1.0
```

Flex Query 必须使用 XML 格式，并包含 `Trades` section 及后端解析所需字段。
如果 IBKR 返回 `ErrorCode 1025`，表示连续失败后 token 已被临时限制。请在
Client Portal 的 Flex Web Service Configuration 中停止重复请求，关闭后重新启用
Flex Web Service，确认状态为 Active；也可以等待 IBKR 的锁定窗口结束。1025 是
账户/服务级状态，即使使用最新 token 也可能继续出现。Token 和 Query ID 必须由
同一个 IBKR 登录用户创建，并且该 Query 应能在 Portal 中手动运行并导出 XML。
