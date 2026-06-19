# 贴心小护士 — 多智能体个性化慢病管理助手

面向多慢病患者的生产级慢病管理平台，集成 LangGraph 多智能体协作、RAG 知识增强、实时风险预警与知识图谱可视化。

## 技术栈

- **前端**: React 18 + TypeScript + Vite + Tailwind CSS + ECharts
- **后端**: Python FastAPI + LangGraph
- **数据库**: PostgreSQL 16 + pgvector
- **缓存**: Redis 7
- **存储**: MinIO
- **大模型**: DeepSeek / OpenAI 兼容 API（可选，无 Key 时使用内置 Mock）

## 快速启动

### 1. 环境准备

```bash
cp .env.example .env
# 可选：在 .env 中配置 LLM_API_KEY
```

### 2. Docker 一键启动

```bash
docker compose up -d
```

服务地址：
- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs
- MinIO 控制台：http://localhost:9001

### 3. 初始化演示数据

```bash
docker compose exec backend python scripts/seed.py
```

演示账号：`demo@nurse.com` / `demo123`

### 本地开发（不使用 Docker）

**后端：**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# 确保 PostgreSQL、Redis 已启动
uvicorn app.main:app --reload --port 8000
python scripts/seed.py
```

**前端：**
```bash
cd frontend
npm install
npm run dev
```

## 功能模块

| 模块 | 说明 |
|------|------|
| 健康仪表盘 | 今日指标、趋势图、风险等级 |
| 数据录入 | 血压/血糖/体重/血脂/血氧 + 饮食运动作息 |
| 智能问诊 | 6 Agent 协作（路由/问诊/监测/方案/随访/预警） |
| 管理方案 | AI 生成的饮食/运动/监测计划 |
| 预警中心 | 规则引擎 + ML 模型分级预警 |
| 随访任务 | 问卷式随访与依从性评分 |
| 报告上传 | OCR 解析体检报告指标 |
| 知识图谱 | 四慢病疾病-症状-治疗-饮食关系可视化 |

## 多智能体架构

```
用户消息 → 路由Agent → 问诊/监测/方案/随访/预警 Agent
                ↓
         RAG知识检索 + 患者上下文 + 知识图谱
                ↓
         结构化回复 + Agent链路追踪
```

## 竞赛答辩 Demo 流程（5分钟）

1. 登录演示账号，查看仪表盘趋势
2. 录入超标血糖 → 触发橙色预警
3. 智能问诊："最近头晕怎么办？" → 展示 Agent 协作链路
4. 查看自动生成的管理方案
5. 完成随访问卷，展示依从性评分
6. 打开知识图谱页面展示多慢病知识关联

## 项目结构

```
nurse-assistant/
├── frontend/          # React 患者端
├── backend/           # FastAPI + LangGraph
│   ├── app/
│   │   ├── agents/    # (via graph/orchestrator)
│   │   ├── graph/     # LangGraph 编排
│   │   ├── services/  # RAG、预警、LLM
│   │   └── ml/        # 风险模型
│   ├── knowledge/     # 指南知识
│   └── scripts/       # 种子数据
├── docker-compose.yml
└── docs/
```

## 医疗合规

所有 AI 输出均标注免责声明，仅提供健康管理建议，不做医疗诊断。

## License

MIT
