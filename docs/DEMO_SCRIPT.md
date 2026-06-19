# 竞赛答辩 Demo 脚本

## 准备

1. 启动服务：`docker compose up -d`
2. 初始化数据：`docker compose exec backend python scripts/seed.py`
3. 浏览器打开 http://localhost:5173

## 演示流程（约5分钟）

### 第一幕：患者建档与监测（1分钟）

- 登录 `demo@nurse.com` / `demo123`
- 展示仪表盘：7天血糖/血压趋势图、风险等级
- 说明：平台支持糖尿病、高血压、高血脂、慢阻肺等多慢病

### 第二幕：异常预警触发（1分钟）

- 进入「数据录入」，录入空腹血糖 `11.5 mmol/L`
- 系统自动触发橙色预警
- 进入「预警中心」查看分级预警与干预建议
- 强调：规则引擎 + Isolation Forest ML 模型双重检测

### 第三幕：多智能体问诊（1.5分钟）

- 进入「智能问诊」
- 输入："最近头晕怎么办？"
- **重点展示**：Agent 协作链路侧栏
  - 路由Agent → 问诊Agent（RAG引用指南）→ 方案Agent
- 说明 RAG 引用了《中国高血压防治指南》

### 第四幕：管理方案与随访（1分钟）

- 查看「管理方案」页面的饮食/运动/监测建议
- 进入「随访任务」完成问卷
- 展示依从性评分

### 第五幕：知识图谱与技术架构（0.5分钟）

- 「我的」→「知识图谱」展示疾病关系网络
- 简述技术栈：React + FastAPI + LangGraph + PostgreSQL + Redis

## 答辩要点

1. **多模态数据融合**：时序指标 + 生活方式 + 报告 OCR
2. **领域大模型**：RAG + Prompt 工程（二期可微调）
3. **多智能体协同**：6 Agent LangGraph 状态机编排
4. **动态风险预警**：规则 + ML + Redis Stream + WebSocket
5. **知识图谱**：PostgreSQL 关系表 + ECharts 可视化
6. **生产级设计**：JWT 认证、免责声明、Docker 部署
