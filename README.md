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
默认使用 SQLite，可直接本地启动：
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

如需使用 PostgreSQL，先启动数据库并显式设置 `DB_ENGINE=postgres`：
```bash
docker compose up -d db
cd backend
DB_ENGINE=postgres python manage.py migrate
DB_ENGINE=postgres python manage.py runserver
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
当前版本默认从：
- `backend/data/ibkr_sample_executions.json`
读取全量 executions。

后续接真实 IBKR 时，只需要替换：
- `apps/brokers/ibkr_client.py`
