# AI 智能面试官系统

基于大模型的智能面试模拟系统，支持简历解析、多轮技术面试、实时评分和评估报告。
内置 LLM 可观测性（LangFuse）和 Prompt 评测框架。

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python) |
| 数据库 | MySQL 8.0 + Redis 7 |
| 向量数据库 | ChromaDB |
| LLM 编排 | LangChain + OpenAI-compatible API |
| 事件系统 | pluggy (Harness) |
| LLM 可观测性 | LangFuse（全链路追踪 + token 统计） |
| 评测框架 | Golden Dataset Eval（10 条基准 Q&A） |
| 协议 | MCP (Model Context Protocol) |
| 前端 | Vue 3 + Element Plus + ECharts |
| 沙箱 | Docker |

## 快速开始

### 1. 环境准备

- Python 3.11+
- Node.js 20+
- Docker Desktop
- MySQL 8.0+ & Redis 7+ (可用 docker-compose)

### 2. 启动基础服务

```bash
docker-compose up -d
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key
```

### 4. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 5. 初始化数据库 & 导入题库

```bash
# 数据库表会自动创建（FastAPI lifespan）
python scripts/seed_questions.py
```

### 6. 启动后端

```bash
uvicorn server.main:app --reload --port 8000
```

### 7. 启动前端

```bash
cd client
npm install
npm run dev
```

### 8. 启动 MCP 服务（可选，编程题需要）

```bash
python -m server.mcp.server
```

### 9. （可选）开启 LangFuse 可观测性

在 `.env` 中配置：

```env
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

访问 http://localhost:5173 开始使用。

## 项目结构

```
ai-agent-first/
├── server/                        # FastAPI 后端
│   ├── main.py                    # 入口
│   ├── config.py                  # 配置
│   ├── database.py                # 数据库
│   ├── models/                    # ORM 模型 (5表)
│   ├── schemas/                   # Pydantic 模型
│   ├── routers/                   # API 路由
│   ├── services/                  # 业务逻辑
│   ├── ai/                        # AI 层
│   │   ├── llm.py                 # LLM 工厂
│   │   ├── prompts/               # Prompt 模板
│   │   ├── rag/                   # RAG 管道
│   │   ├── skills/                # 面试 Skill 模块 (5个)
│   │   ├── agent/                 # Agent 决策层
│   │   ├── guardrails/            # 安全护栏
│   │   └── orchestrator.py        # 面试编排器（Agent+状态机混合）
│   ├── harness/                   # Harness 事件系统
│   ├── observability/             # 可观测性 + 评测框架
│   │   ├── langfuse_client.py     # LangFuse 客户端（优雅降级）
│   │   ├── callbacks.py           # LangChain 回调适配器
│   │   ├── eval_runner.py         # Golden Dataset 评测引擎
│   │   ├── eval_dataset.json      # 10 条基准 Q&A 对
│   │   └── router.py              # Admin API (/admin/traces, /admin/eval/*)
│   ├── mcp/                       # MCP 代码沙箱
│   └── utils/                     # 工具
├── client/                        # Vue 3 前端
│   ├── src/
│   │   ├── views/                 # 3 个页面
│   │   ├── stores/                # Pinia 状态
│   │   ├── api/                   # axios 封装
│   │   └── router/               # Vue Router
├── scripts/                       # 工具脚本
├── data/                          # 数据文件
└── docker-compose.yml
```

## API 文档

启动后端后访问 http://localhost:8000/docs 查看 Swagger 文档。

### 业务接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 注册账号 |
| POST | `/api/v1/auth/login` | 登录获取 Token |
| GET | `/api/v1/auth/me` | 查看个人信息（含自动绑定简历） |
| POST | `/api/v1/resume/upload` | 上传简历 PDF（需登录） |
| GET | `/api/v1/resume/my` | 获取已绑定的简历 |
| GET | `/api/v1/resume/{id}` | 获取简历状态+解析数据 |
| GET | `/api/v1/resume/{id}/analysis` | 获取完整解析结果 |
| POST | `/api/v1/interview/start` | 开始面试 |
| GET | `/api/v1/interview/history` | 获取当前用户历史会话列表 |
| GET | `/api/v1/interview/{id}` | 获取面试状态 |
| GET | `/api/v1/interview/{id}/questions` | 获取会话所有问题 |
| GET | `/api/v1/interview/{id}/stream` | SSE 流式获取问题 |
| POST | `/api/v1/interview/{id}/answer` | 提交答案 |
| POST | `/api/v1/interview/{id}/end` | 结束面试 |
| GET | `/api/v1/interview/{id}/report` | 查看评分报告 |
| GET | `/api/v1/interview/{id}/report/improvements` | 获取改进建议 |

### 运营接口（Admin）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/traces` | 查询 LangFuse LLM 调用链 |
| POST | `/api/v1/admin/eval/run` | 运行 Prompt 评测（10 条 golden dataset） |
| GET | `/api/v1/admin/eval/dataset` | 查看评测数据集 |

## 核心技术亮点

1. **Prompt 工程**: 5 套结构化 Prompt 模板，Few-shot + CoT + JSON Mode
2. **RAG**: ChromaDB 3 集合混合检索，为出题和评分提供知识支撑
3. **Agent 决策**: LLM 自主决定追问/跳模块/调难度，状态机兜底
4. **Skills 系统**: pluggy 插件化架构，5 个可组合的面试模块
5. **Harness 事件系统**: 9 个生命周期 Hook + 4 个内置插件
6. **Safety Guardrails**: 3 层渐进式输入防御 + 流式输出 PII 脱敏
7. **MCP 代码沙箱**: Docker 隔离执行，安全的编程题评估
8. **SSE 流式出题**: 模拟真人面试官的逐字打字效果
9. **LLM 可观测性**: LangFuse 全链路追踪，16 个 LLM 调用点自动采集（token、延迟、phase 标签）
10. **Prompt 评测框架**: 10 条 Golden Dataset 基准测试，改 prompt 前后量化对比评分偏离度
