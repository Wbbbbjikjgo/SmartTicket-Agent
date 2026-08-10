# AGENTS.md — AI Agent 开发协作指南

> 本文件是 AI Agent 在本项目中工作的核心规范。每次对话开始时 Agent 应先阅读本文件，确保不丢失上下文、不违反项目约定。

---

## 1. 项目速览（防遗忘锚点）

**项目名称**：基于多场景的 Agent 智能工单系统（SmartTicket-Agent）

**核心目标**：通过大模型 + 多智能体 + 混合检索，实现工单自动创建/分类/派单/知识闭环，效率提升 5-10 倍。

**技术栈速查**：

| 组件 | 选型 | 备注 |
| --- | --- | --- |
| 大模型 | DeepSeek / Qwen | 国内 API 直连 |
| Embedding | DashScope `text-embedding-v3` | 1024维，替代 BGE-M3 |
| Rerank | DashScope `gte-rerank-v2` | 替代 bge-reranker |
| 框架 | LangChain + LangGraph | Agent 编排 |
| 搜索 | Elasticsearch 8.x + IK 分词 | 镜像 `infinifinity/elasticsearch:8.11.0-ik` |
| 队列 | Kafka 3.6 | 削峰 + 异步 |
| 前端 | Streamlit | 看板/检索/问答 |
| 部署 | Docker Compose | 国内镜像加速 |
| 模型下载 | ModelScope 魔搭 | 替代 HuggingFace |

**关键约束**：
- 所有模型/镜像/依赖**必须使用国内可获取的方案**，禁止依赖 HuggingFace、Docker Hub 官方源
- pip 安装走阿里云镜像：`pip install -i https://mirrors.aliyun.com/pypi/simple/`
- Docker 镜像走国内加速器（DaoCloud / 阿里云 ACR）

---

## 2. 功能模块与 Git 提交规范

### 2.1 Git Commit 类型约定

| 类型 | 含义 | 使用场景 |
| --- | --- | --- |
| `feat` | 新功能 | 新增功能模块或功能点 |
| `fix` | 修复缺陷 | 修复已有功能的 bug |
| `refactor` | 重构 | 不改变功能的代码优化 |
| `docs` | 文档 | 仅文档变更 |
| `style` | 格式 | 代码格式化、缩进等 |
| `test` | 测试 | 新增或修改测试 |
| `chore` | 构建/工具 | 依赖更新、配置变更 |
| `perf` | 性能 | 性能优化 |
| `ci` | CI/CD | 部署/流水线配置 |

### 2.2 Commit Message 格式

```
<type>(<scope>): <subject>

<body>
```

- `scope`：功能模块名（见下方模块列表）
- `subject`：简明描述，不超过 50 字
- `body`：可选，详细说明

### 2.3 各功能模块与提交计划

以下是每个功能模块的**开发顺序、涉及文件、建议 commit message**：

---

#### 模块 1：项目初始化与基础结构

**涉及文件**：项目根目录、`requirements.txt`、`.env.example`、`.gitignore`

```
chore(init): 初始化项目结构与依赖配置
feat(config): 添加配置文件 es_config / kafka_config / agent_config
```

---

#### 模块 2：工单数据清洗（大模型 + NLP 算法）

**涉及文件**：`preprocess/cleaner.py`、`preprocess/entity_extraction/extractor.py`、`preprocess/entity_extraction/prompt_templates.py`

```
feat(preprocess): 实现工单文本清洗模块（去噪/去特殊字符/格式化）
feat(preprocess): 实现基于 DeepSeek 的实体抽取（问题类型/设备/紧急程度）
feat(preprocess): 实现结构化转换与置信度判断（低置信度自动追问）
```

---

#### 模块 3：Elasticsearch 知识库搭建

**涉及文件**：`data/ingestion/ingest_docs.py`、ES 索引配置

```
feat(es): 创建 tickets / knowledge_base / faq 三个索引（IK分词+dense_vector）
feat(es): 实现 DashScope text-embedding-v3 向量化入库
feat(es): 实现历史工单批量导入脚本 ingest_docs.py
```

---

#### 模块 4：Kafka + 规则过滤

**涉及文件**：`preprocess/nlp_classifier.py`、Kafka 消费者/生产者

```
feat(kafka): 实现 Kafka 工单消息队列（ticket-raw topic）
feat(kafka): 实现规则引擎快速分流（关键词/正则/优先级匹配）
feat(kafka): 实现规则命中直连路由 vs 未命中走 LLM 清洗链路
```

---

#### 模块 5：Query 改写与语义增强

**涉及文件**：`retrieval/query_rewriter.py`

```
feat(retrieval): 实现 Query 改写模块（LLM改写+同义词扩展+结构化查询）
```

---

#### 模块 6：混合检索 + 重排序

**涉及文件**：`retrieval/hybrid_retriever/bm25_retriever.py`、`retrieval/hybrid_retriever/vector_retriever.py`、`retrieval/hybrid_retriever/fusion.py`、`retrieval/reranker/reranker.py`

```
feat(retrieval): 实现 BM25 全文检索器（IK分词）
feat(retrieval): 实现向量语义检索器（DashScope embedding + ES knn）
feat(retrieval): 实现 RRF 融合排序算法
feat(retrieval): 实现 DashScope gte-rerank-v2 重排序
```

---

#### 模块 7：意图识别 + 槽位填充

**涉及文件**：`agents/intent_agent.py`、`agents/slot_filling_agent.py`

```
feat(agents): 实现意图识别 Agent（create_ticket/query/search_knowledge/assign/chitchat）
feat(agents): 实现槽位填充 Agent（工单号/产品/问题类型/描述/紧急程度）
feat(agents): 实现槽位缺失时自动追问补全逻辑
```

---

#### 模块 8：MCP + FunctionCall 工具调用

**涉及文件**：`tools/mcp_ticket_server.py`、`tools/create_ticket.py`、`tools/query_ticket.py`、`tools/search_knowledge.py`、`tools/assign_engineer.py`

```
feat(tools): 定义 FunctionCall 工具集（create_ticket/query_ticket/search_knowledge/assign_engineer）
feat(tools): 实现 MCP Server 封装工单系统 API
feat(agents): 通过 langchain-mcp-adapters 接入 MCP 工具
```

---

#### 模块 9：工单创建/查询 Agent + 智能派单 Agent

**涉及文件**：`agents/ticket_agent.py`、`agents/assign_agent.py`、`agents/graph.py`

```
feat(agents): 实现工单创建/查询 Agent
feat(agents): 实现智能派单 Agent（技能组匹配+优先级路由）
feat(agents): 实现 LangGraph 多 Agent 协同编排（条件路由+状态管理）
```

---

#### 模块 10：知识库实时迭代

**涉及文件**：`agents/knowledge_agent.py`

```
feat(agents): 实现知识沉淀 Agent（工单关闭→LLM摘要→向量去重→入库）
feat(agents): 实现知识质量评估（满意度/解决时长评分）
```

---

#### 模块 11：Streamlit 前端

**涉及文件**：`web/app.py`、`web/pages/dashboard.py`、`web/pages/knowledge.py`、`web/pages/chat.py`、`web/components/`

```
feat(web): 实现 Streamlit 主入口与导航
feat(web): 实现工单看板页面（统计/列表/详情）
feat(web): 实现知识检索页面（搜索+结果展示）
feat(web): 实现智能问答页面（对话式工单处理）
```

---

#### 模块 12：Docker 容器化部署

**涉及文件**：`deploy/docker-compose.yml`、`agent-service/Dockerfile`、`web/Dockerfile`、`.env.example`

```
feat(deploy): 编写 docker-compose.yml（ES+Kafka+Agent+Streamlit 四服务）
feat(deploy): 配置国内镜像加速（ES IK镜像/DaoCloud/阿里云PyPI）
feat(deploy): 编写 .env.example 与一键部署脚本
```

---

#### 模块 13：测试与文档

```
test(preprocess): 工单清洗模块单元测试
test(retrieval): 混合检索与重排序集成测试
test(agents): 多 Agent 协同流程测试
docs: 完善项目文档与 API 说明
```

---

## 3. Agent 防遗忘规则（防止 AI 变傻）

### 3.1 上下文锚定

每次新对话或任务开始时，Agent 必须：

1. **读取本文件**（AGENTS.md）确认项目上下文
2. **读取 `项目文档.md`** 确认技术架构与功能设计
3. **确认当前开发进度**：通过 `git log --oneline` 查看已完成的 commit
4. **确认待办事项**：通过 `git status` 和未提交变更了解当前状态

### 3.2 禁止事项

- ❌ 禁止引入 HuggingFace Hub 下载模型（用 ModelScope 或 DashScope API）
- ❌ 禁止使用 BGE-M3 / bge-reranker 本地模型（用 DashScope API）
- ❌ 禁止使用 Docker Hub 官方源直接拉取（必须配置国内镜像加速）
- ❌ 禁止使用 OpenAI / Claude API（用 DeepSeek 或 Qwen）
- ❌ 禁止在未确认已有代码的情况下重写整个文件
- ❌ 禁止修改不相关的代码（最小改动原则）
- ❌ 禁止跳过错误处理（所有 API 调用必须有 try-except + 重试）

### 3.3 必须遵守

- ✅ 所有 LLM 调用使用 DeepSeek（`api.deepseek.com`）或 Qwen（DashScope）
- ✅ Embedding 统一使用 DashScope `text-embedding-v3`（1024 维）
- ✅ Rerank 统一使用 DashScope `gte-rerank-v2`
- ✅ ES 分词器使用 IK（`ik_max_word` 索引 / `ik_smart` 检索）
- ✅ 所有 commit 遵循 Conventional Commits 规范（见第 2 节）
- ✅ 每个功能模块完成后立即 git commit，不要堆积大量改动
- ✅ 新增文件必须与 `项目文档.md` 第 6 节目录结构一致
- ✅ 所有 API Key 从环境变量读取，不硬编码

### 3.4 代码风格

- Python 代码遵循 PEP 8
- 函数/类必须有 docstring 说明
- 关键逻辑必须有中文注释
- 配置项集中在 `configs/` 目录下的 YAML 文件中
- 日志使用 `logging` 模块，不使用 `print`

---

## 4. Token 使用优化规则（防止 token 过多）

### 4.1 文件读取原则

- **先查后读**：先用 `Grep` / `Glob` 定位目标，再精确读取文件
- **按需读取**：大文件使用行号范围读取，不要一次读整个文件
- **不重复读取**：已读过的文件在同一会话中不再重复读取

### 4.2 代码生成原则

- **最小改动**：只修改需要改的部分，不要输出整个文件
- **复用优先**：优先复用已有工具函数，不要重复造轮子
- **单次提交**：一个功能的所有改动在同一个 commit 中完成

### 4.3 对话效率原则

- **先规划后执行**：复杂任务先列出 TODO 计划，确认后再执行
- **批量操作**：多个文件修改尽量在一次回复中完成
- **避免试探**：不要反复尝试不同方案，先分析清楚再动手
- **结果导向**：直接给出解决方案，不要输出冗长的分析过程

### 4.4 上下文管理

- **长对话分段**：超过 20 轮对话后，主动总结进度并建议开启新会话
- **关键决策记录**：重要技术决策写入本文件或项目文档，避免下次重复讨论
- **代码即文档**：复杂逻辑通过代码注释说明，减少口头解释的 token 消耗

---

## 5. 开发工作流

### 5.1 标准开发流程

```
1. 阅读本文件 + 项目文档 → 确认任务范围
2. git pull → 同步最新代码
3. 分析需求 → 列出 TODO 计划
4. 逐模块开发 → 每完成一个功能点立即 commit
5. 开发完成 → 运行测试 → 修复问题
6. 更新文档（如有必要）
7. 最终 commit + 汇报进度
```

### 5.2 提交节奏

- 每完成一个**独立功能点**就提交一次
- commit message 必须清晰描述本次改动内容
- 不要一次提交大量不相关改动
- 不要提交包含 API Key 的文件

### 5.3 分支策略

- `main`：稳定版本
- `dev`：开发主线
- `feature/<module>`：功能分支（如 `feature/retrieval`、`feature/agents`）
- `fix/<issue>`：修复分支

---

## 6. 关键文件速查

| 文件 | 作用 |
| --- | --- |
| `AGENTS.md`（本文件） | AI Agent 开发协作规范 |
| `项目文档.md` | 完整项目设计文档 |
| `requirements.txt` | Python 依赖清单 |
| `.env.example` | 环境变量模板（API Key 等） |
| `configs/es_config.yaml` | Elasticsearch 配置 |
| `configs/kafka_config.yaml` | Kafka 配置 |
| `configs/agent_config.yaml` | Agent 系统配置 |
| `deploy/docker-compose.yml` | 容器编排 |

---

## 7. 快速启动命令

```bash
# 1. 安装依赖（国内源）
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY 和 DASHSCOPE_API_KEY

# 3. 启动基础设施
docker compose -f deploy/docker-compose.yml up -d

# 4. 初始化知识库
python data/ingestion/ingest_docs.py

# 5. 启动前端
streamlit run web/app.py
```

---

> **Agent 注意**：本文件是项目开发的"宪法"，任何代码变更不得违反本文件中的约定。如有疑问，先查阅本文件和 `项目文档.md`，再向用户确认。
