# 部署文档

## 生产环境建议

### 环境变量

| 变量 | 说明 |
|------|------|
| `JWT_SECRET_KEY` | 必须更换为随机强密钥 |
| `LLM_API_KEY` | DeepSeek 或通义千问 API Key |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `REDIS_URL` | Redis 连接串 |
| `CORS_ORIGINS` | 前端域名 |

### Docker Compose 部署

```bash
docker compose up -d --build
docker compose exec backend python scripts/seed.py
```

### 健康检查

- `GET /health` — 后端存活检查
- `GET /` — 服务信息

## API 概览

### 认证
- `POST /api/auth/register` — 注册
- `POST /api/auth/login` — 登录
- `GET /api/auth/me` — 当前用户

### 健康数据
- `POST /api/health/records` — 录入指标
- `GET /api/health/dashboard` — 仪表盘
- `POST /api/health/lifestyle` — 生活方式记录

### 多智能体
- `POST /api/agents/chat` — 智能问诊
- `GET /api/agents/traces/{session_id}` — Agent 链路

### 预警
- `GET /api/alerts` — 预警列表
- WebSocket `/api/ws/alerts/{patient_id}` — 实时推送

### 知识图谱
- `GET /api/knowledge/graph` — 图谱数据

## 二期扩展

- 医护端 Web（API 已预留 `role=doctor`）
- HIS 系统对接适配层
- LoRA 模型微调流水线
- Neo4j 知识图谱迁移
