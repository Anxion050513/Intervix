# AI 智能面试官系统 — MVP 实施方案

> **技术栈**：Python + FastAPI + MySQL + Redis + ChromaDB + LangChain + Vue 3 + pluggy + fastmcp + Docker  
> **工期**：约 16-20 天（业余时间）  
> **目标**：覆盖 AI 应用开发面试所需的 9 项核心技术

---

## 一、技术栈与覆盖

| 学长要求 | 本项目落地 | 深度 |
|----------|-----------|------|
| 后端 CRUD | FastAPI + MySQL + 5 表完整 CRUD | ⭐⭐⭐ |
| 大模型基础 | LLM API / Streaming / Token 管理 / Structured Output | ⭐⭐⭐ |
| Python | FastAPI + LangChain + ChromaDB（后端全 Python） | ⭐⭐⭐⭐ |
| LangChain/Dify | LangChain Chain + Parser + Chroma + 流式回调 | ⭐⭐⭐⭐ |
| Prompt 提示词 | 4 套 Prompt 模板 + Few-shot + CoT + 结构化 Schema | ⭐⭐⭐⭐⭐ |
| RAG 向量检索 | ChromaDB 3 集合 + 混合检索 + RRF 融合 | ⭐⭐⭐⭐ |
| Agent | LLM 自主决策：追问/跳模块/调难度/提前结束 | ⭐⭐⭐⭐ |
| Skills | pluggy 插件化 Skill 系统 + 5 个模块 | ⭐⭐⭐⭐ |
| MCP | fastmcp + Docker 沙箱 + 代码执行 | ⭐⭐⭐ |
| Safety Guardrails | 输入防注入+内容审核 / 输出 PII 脱敏+凭据防泄漏 | ⭐⭐⭐⭐ |
| Harness 工程 | pluggy Hook 规范 + 生命周期事件 + 4 个插件 | ⭐⭐⭐⭐ |
| LLM 可观测性 | LangFuse 全链路追踪 / Token 统计 / 自定义 CallbackHandler | ⭐⭐⭐⭐ |
| Prompt 评测 | Golden Dataset Eval / 量化对比 / 评分偏离度分析 | ⭐⭐⭐⭐ |

---

## 二、开发环境

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 后端主语言 |
| Node.js | 20+ | 前端构建 |
| MySQL | 8.0+ | 关系数据库 |
| Redis | 7.x | 会话缓存 |
| ChromaDB | 0.5.x | 向量数据库 |
| Docker | 24+ | 代码沙箱 + 开发服务 |
| LLM API | OpenAI-compatible | 可换任何供应商 |

---

## 三、项目结构

```
ai-agent-first/                      # 项目根目录
├── docker-compose.yml               # MySQL + Redis
├── .env.example                     # 环境变量模板
├── .env                             # 实际环境变量
│
├── server/                          # FastAPI 后端
│   ├── main.py                      # 入口
│   ├── config.py                    # 配置
│   ├── database.py                  # SQLAlchemy async + MySQL
│   ├── dependencies.py              # FastAPI Depends
│   ├── models/                      # ORM: user, resume, interview, question, answer
│   ├── schemas/                     # Pydantic
│   ├── routers/                     # resume, interview, score, health
│   ├── services/                    # resume_service, interview_service, scoring_service, streaming_service
│   ├── ai/                          # AI 层
│   │   ├── llm.py
│   │   ├── prompts/                 # 4 套 Prompt 模板
│   │   ├── rag/                     # vector_store, embedder, retriever, ingestion
│   │   ├── skills/                  # base, registry, warmup, technical_qa, behavioral, system_design, coding_challenge
│   │   ├── agent/                   # decision_agent（LLM 自主决策下一步动作）
│   │   ├── guardrails/              # input_guard（防注入+审核）, output_guard（PII脱敏+防泄漏）
│   │   └── orchestrator.py         # Agent + 状态机混合编排器
│   ├── harness/                     # hooks, manager, events, plugins/（4 个内置插件）
│   ├── observability/               # LangFuse 可观测性 + Eval 评测框架
│   │   ├── langfuse_client.py       # LangFuse 客户端（未配置时自动禁用）
│   │   ├── callbacks.py             # LangChain 回调适配器（async-safe）
│   │   ├── eval_runner.py           # Golden Dataset 评测引擎
│   │   ├── eval_dataset.json        # 10 条基准 Q&A 对
│   │   └── router.py                # Admin API 路由
│   ├── mcp/                         # server, tools, sandbox
│   └── utils/                       # pdf.py
│
├── client/                          # Vue 3 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/                  # Vue Router
│   │   ├── stores/                  # Pinia 状态管理
│   │   ├── api/                     # axios 封装
│   │   ├── views/                   # 页面
│   │   │   ├── UploadResume.vue     # 简历上传
│   │   │   ├── Interview.vue        # 面试对话
│   │   │   └── ViewReport.vue       # 评分报告
│   │   ├── components/              # 公共组件
│   │   │   ├── ChatMessage.vue
│   │   │   ├── CodeEditor.vue       # Monaco Editor 封装
│   │   │   ├── ScoreRadar.vue       # ECharts 雷达图
│   │   │   └── InterviewSidebar.vue
│   │   └── styles/
│
├── data/                            # chroma/ + uploads/
├── scripts/                         # seed_questions.py
└── tests/                           # conftest, test_*
```

---

## 四、数据库设计（MySQL 8.0）

```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE resumes (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    original_filename VARCHAR(512) NOT NULL,
    file_path VARCHAR(1024) NOT NULL,
    parsed_data JSON NOT NULL,
    tech_stack JSON NOT NULL,
    years_experience INT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE interview_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    resume_id VARCHAR(36) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    skill_modules JSON NOT NULL,
    question_count INT NOT NULL DEFAULT 0,
    current_question_index INT NOT NULL DEFAULT 0,
    difficulty_level VARCHAR(20) NOT NULL DEFAULT 'medium',
    settings JSON NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (resume_id) REFERENCES resumes(id)
);

CREATE TABLE questions (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    skill_module VARCHAR(100) NOT NULL,
    question_text TEXT NOT NULL,
    question_type VARCHAR(50) NOT NULL,
    expected_topics JSON NOT NULL,
    reference_answer TEXT,
    difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
    order_index INT NOT NULL,
    metadata JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
);

CREATE TABLE answers (
    id VARCHAR(36) PRIMARY KEY,
    question_id VARCHAR(36) NOT NULL,
    user_answer TEXT NOT NULL,
    score DECIMAL(5,2),
    score_breakdown JSON,
    feedback TEXT,
    is_evaluated BOOLEAN NOT NULL DEFAULT FALSE,
    evaluated_at DATETIME,
    duration_seconds INT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);
```

---

## 五、API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 注册账号 |
| POST | `/api/v1/auth/login` | 登录获取 Token |
| GET | `/api/v1/auth/me` | 查看个人信息（含自动绑定简历） |
| POST | `/api/v1/resume/upload` | 上传 PDF，返回简历 ID |
| GET | `/api/v1/resume/my` | 获取当前用户已绑定的简历 |
| GET | `/api/v1/resume/{id}` | 获取简历状态+解析数据 |
| GET | `/api/v1/resume/{id}/analysis` | 获取完整解析结果 |
| POST | `/api/v1/interview/start` | 开始面试 `{resume_id, skill_modules}` |
| GET | `/api/v1/interview/history` | 获取当前用户历史会话列表 |
| GET | `/api/v1/interview/{id}` | 获取面试状态 |
| GET | `/api/v1/interview/{id}/questions` | 获取会话所有问题 |
| GET | `/api/v1/interview/{id}/stream` | SSE 流式获取问题 |
| POST | `/api/v1/interview/{id}/answer` | 提交答案 `{question_id, answer}` |
| POST | `/api/v1/interview/{id}/end` | 结束面试 |
| GET | `/api/v1/interview/{id}/report` | 查看评分报告 |
| GET | `/api/v1/interview/{id}/report/improvements` | 获取改进建议 |
| GET | `/api/v1/admin/traces` | 查询 LangFuse LLM 调用链 |
| POST | `/api/v1/admin/eval/run` | 运行 Prompt 评测（10 条基准数据集） |
| GET | `/api/v1/admin/eval/dataset` | 查看评测数据集 |
| GET | `/api/v1/health` | 健康检查 |

---

## 六、核心架构设计

### 6.1 面试编排器（Agent + 状态机混合）

```
状态机骨架：IDLE → WARMUP → TECHNICAL_QA → BEHAVIORAL → SYSTEM_DESIGN → CODING → SCORING → COMPLETE
Agent 覆盖层：首题破冰后，每一步由 LLM Agent 根据得分/历史动态决定 follow_up / switch / skip / adjust / conclude
```

### 6.2 Skills 系统

```python
class BaseSkill(ABC):
    name: str
    display_name: str
    priority: int
    min_questions: int = 3
    max_questions: int = 7

    async def generate_question(self, ctx: SkillContext) -> GeneratedQuestion: ...
    async def evaluate_answer(self, question, user_answer, ctx) -> dict: ...
```

5 个 Skill：`warmup` / `technical_qa` / `behavioral` / `system_design` / `coding_challenge`

### 6.3 Agent 决策层

```python
class AgentAction(StrEnum):
    CONTINUE = "continue"         # 继续当前模块出题
    FOLLOW_UP = "follow_up"       # 追问上一题（得分<50 自动触发）
    SWITCH_SKILL = "switch_skill" # 切换到下一个技能模块
    SKIP_SKILL = "skip_skill"     # 跳过某模块（候选人已展示深度掌握）
    ADJUST_DIFFICULTY = "adjust"  # 仅调整难度
    CONCLUDE = "conclude"         # 提前结束面试
```

**决策原则**：
- 上一题得分 < 50 → `follow_up` 深入追问，确认是知识盲区还是紧张
- 连续 3 题 > 85 → `skip_skill` 或 `adjust` 提升难度
- 追问最多连续 1 次 → 避免死循环
- LLM 异常时自动降级到规则决策（fallback）

编排器改为 **Agent 优先 + 状态机兜底** 混合模式，首题必走 warmup 破冰，之后由 Agent 根据候选人实时表现动态决策。

### 6.4 Safety Guardrails

**Input Guard（3 层渐进式防御）**：

| 层 | 机制 | 检测内容 |
|---|------|---------|
| Layer 0 | 空输入/长度 | 空输入、超长 (>8000字)、重复字符滥用 |
| Layer 1 | 正则模式 | 提示注入、有害内容、偏题请求 |
| Layer 2 | LLM 分类 | 语义层歧义边界，上下文感知判断 |

**Output Guard**：
- PII 自动脱敏：邮箱/手机号/身份证/银行卡/IP 地址 → `[脱敏标记]`
- 敏感凭据检测：API Key / 密码泄露防护
- 幻觉标记检测：过度自信表述（"100%正确"等）
- 流式输出 chunk 级实时检查

### 6.5 Harness 事件系统（pluggy）

| Hook | 触发时机 |
|------|---------|
| `on_interview_start` | 面试开始 |
| `on_question_generated` | 题目生成 |
| `on_answer_submitted` | 用户提交答案 |
| `on_answer_scored` | 评分完成 |
| `on_difficulty_adjust` | 难度调整 |
| `on_input_blocked` | 输入护栏拦截 |
| `on_output_sanitized` | 输出护栏脱敏 |
| `on_interview_end` | 面试结束 |
| `on_error` | 异常处理 |

4 个内置插件：Logger / Metrics / DifficultyAdjuster / GuardPlugin

### 6.6 RAG 管道

- ChromaDB 3 个集合：`question_bank` / `knowledge_base` / `resume_chunks`
- 混合检索：Dense(70%) + BM25(30%) → RRF 融合

### 6.7 MCP 服务

- fastmcp + Docker 沙箱（`--network none --memory=256m`）
- 工具：`execute_code` / `run_tests`

### 6.8 Vue 前端架构

- **Vue 3** Composition API + `<script setup>`
- **Vite** 构建工具
- **Vue Router 4** 路由
- **Pinia** 状态管理（面试会话状态、用户信息）
- **Element Plus** UI 组件库
- **axios** HTTP 请求 + SSE 流式接收
- **Monaco Editor** 代码编辑（编程题）
- **ECharts** 评分雷达图

### 6.9 LLM 可观测性（LangFuse）

- **零侵入设计**：基于 contextvars 的 TraceContext + LangChain CallbackHandler，不改任何 Skill 文件
- **16 个 LLM 调用点**全部自动追踪，覆盖 generate / evaluate / decide / rephrase / extract / scoring / guard
- 每个 LLM 调用记录：模型名、token 消耗、延迟、prompt/response、session_id、skill_module、phase
- **优雅降级**：未配置 LangFuse 密钥时全系统零影响
- Admin API：`GET /admin/traces` 查询最近 trace 列表

### 6.10 Prompt 评测框架

- **Golden Dataset**：10 条手写基准 Q&A 对，覆盖 5 个 Skill 模块各 2 条
- 复用现有 Skill 的 `evaluate_answer()` 方法（无重复代码）
- 对比维度：**整体分偏离度** + **4 维评分子项偏离**（technical_accuracy / depth_breadth / clarity / practical_experience）
- 改 Prompt 前后各跑一次 → 量化对比 → Prompt Engineering 闭环
- Admin API：`POST /admin/eval/run` 执行评测，返回 pass/fail 和偏离度报告

---

## 七、实现步骤

### 第 1-3 天：地基
1. 项目目录创建 + `requirements.txt` + `.env`
2. `docker-compose.yml`（MySQL + Redis）
3. MySQL 建表 + SQLAlchemy 模型 + CRUD
4. FastAPI 骨架 + `/health`
5. LLM 工厂

### 第 4-5 天：简历处理
6. PDF 提取 + LLM 解析 Prompt + resume 路由/服务
7. ChromaDB 初始化 + 简历存储

### 第 6-8 天：面试核心
8. Skills 系统（base + registry + warmup + technical_qa）
9. Harness 事件系统
10. 面试编排器 + SSE 流式
11. 题库导入脚本

### 第 9-10 天：评分报告
12. 答案评分 + 报告生成

### 第 11-12 天：MCP + 编程题
13. fastmcp 服务 + Docker 沙箱 + CodingChallenge Skill

### 第 13-14 天：Vue 前端搭建
14. Vite 项目创建 + 路由 + Pinia + axios 封装
15. 简历上传页 + 面试对话页

### 第 15-17 天：Vue 前端完善
16. Monaco Editor 集成 + 编程题交互
17. ECharts 评分报告页 + 动画

### 第 18-20 天：收尾
18. 端到端测试 + 错误处理
19. LangFuse 可观测性接入 + 全链路追踪
20. Golden Dataset 评测框架搭建
21. README 文档
22. Demo 视频录制

---

## 八、环境变量（.env）

```env
# LLM
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=interview123
MYSQL_DATABASE=ai_interviewer

# Redis
REDIS_URL=redis://localhost:6379/0

# LangFuse Observability（可选，留空则禁用）
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# App
APP_ENV=development
UPLOAD_DIR=./data/uploads
CHROMA_PERSIST_DIR=./data/chroma
```
