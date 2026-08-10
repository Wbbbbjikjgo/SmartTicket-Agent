# 🎫 SmartTicket-Agent 智能工单系统

基于 **大模型 + 多 Agent 编排 + 混合检索** 的智能工单系统，实现工单自动清洗、意图识别、自动派单、知识沉淀全流程闭环。全部采用**国产化方案**（DeepSeek / 阿里云 DashScope / 国内镜像源）。

## ✨ 核心功能

| 模块 | 能力 | 技术方案 |
|---|---|---|
| 数据清洗 | 去表情/URL/特殊字符、错误码/设备型号抽取 | 正则 + NLP 规则 + DeepSeek |
| 知识库 | ES 全文 + 向量双索引（tickets/knowledge_base/faq） | Elasticsearch 8 + IK 分词 |
| 消息队列 | 工单接入、规则过滤路由（5大类分发） | Kafka 3.7 (KRaft) |
| 混合检索 | Query改写 → BM25+向量召回 → RRF融合 → Rerank精排 | DashScope embedding-v3 + gte-rerank-v2 |
| 智能问答 | 意图识别 + 槽位填充 + FunctionCall + MCP | LangGraph 多 Agent 编排 |
| 智能派单 | 规则优先 + LLM 兜底，按类别/紧急度派单 | 规则引擎 + DeepSeek |
| 知识沉淀 | 工单解决后自动摘要去重入库 | LLM 摘要 + ES 去重 |
| 前端 | 工单看板 / 智能问答 / 知识检索 三页面 | Streamlit |

## 🏗️ 系统架构

```
用户提问 → 意图识别Agent → 槽位填充Agent
              ↓
    ┌─────────┼──────────┐
    ↓         ↓          ↓
 FunctionCall 混合检索    派单Agent
 (创建/查询工单) (Query改写→BM25+向量→RRF→Rerank) (规则+LLM)
    ↓         ↓          ↓
    └─────────┼──────────┘
              ↓
         生成回复 → 知识沉淀Agent（自动入库）
```

## 🛠️ 技术栈

- **大模型**：DeepSeek（`deepseek-chat`）
- **Embedding**：阿里云 DashScope `text-embedding-v3`（1024维）
- **Rerank**：阿里云 DashScope `gte-rerank-v2`
- **框架**：LangChain + LangGraph、Streamlit
- **基础设施**：Elasticsearch 8.11 + IK 分词、Kafka 3.7（KRaft，无 Zookeeper）
- **部署**：Docker Compose

## 📂 项目结构

```
SmartTicket-Agent/
├── agent-service/       # Agent 后端服务（FastAPI + MCP）
├── agents/              # 多Agent：意图/槽位/工单/派单/知识沉淀 + LangGraph编排
├── configs/             # 全局配置加载
├── data/
│   ├── ingestion/       # ES入库脚本 + Embedding服务 + Kafka队列
│   └── raw_data/        # 原始工单数据
├── deploy/              # Docker Compose + Dockerfile
├── preprocess/          # 数据清洗 + 实体抽取 + 规则分类引擎
├── retrieval/           # Query改写 + BM25/向量检索 + RRF融合 + Rerank
├── tools/               # FunctionCall工具 + MCP Server
├── web/                 # Streamlit 前端（看板/问答/检索）
├── .env                 # 环境变量（API Key）
├── AGENTS.md            # AI协作开发规范
└── 项目文档.md           # 完整设计文档
```

## 🚀 快速开始

### 1. 配置环境变量

编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-xxxx          # DeepSeek API Key
DASHSCOPE_API_KEY=sk-xxxx         # 阿里云百炼 API Key
ES_HOST=http://localhost:9200
KAFKA_BOOTSTRAP=localhost:9092
LLM_MODEL=deepseek-chat
EMBEDDING_MODEL=text-embedding-v3
RERANK_MODEL=gte-rerank-v2
VECTOR_DIMS=1024
```

### 2. 启动基础设施

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d
```

> 需要镜像：`elasticsearch:8.11.0`、`apache/kafka:3.7.0`、`python:3.11-slim`
> 国内拉取慢可加前缀：`docker pull docker.xuanyuan.me/library/elasticsearch:8.11.0` 再 `docker tag` 回原名

### 3. 安装依赖 + 初始化知识库

```bash
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
python data/ingestion/ingest_docs.py
```

### 4. 启动前端

```bash
python -m streamlit run web/app.py --server.port 8502
```

访问 http://localhost:8502

### 5. 停止服务

```bash
docker compose --env-file .env -f deploy/docker-compose.yml down
```

> 数据保存在 Docker 数据卷中，再次 `up` 会自动恢复。

## 🧪 测试示例

在「智能问答」页面输入：

- `我的服务器一直返回502错误，帮我创建工单` → 自动意图识别 + 槽位填充 + 创建工单 + 派单
- `查一下工单 GD20260810144419CBEB 的进度` → FunctionCall 调用查询工具
- `我想报修一个设备` → 槽位不全时 Agent 自动追问

在「知识检索」页面输入：

- `服务器502错误怎么处理` → 命中知识库，Rerank 精排展示结果

## 📝 Git 提交规范

```
feat(模块): 新功能    fix(模块): 修复    chore: 杂项
```

模块名：`preprocess` / `es` / `kafka` / `retrieval` / `agents` / `web` / `deploy`

详见 [AGENTS.md](AGENTS.md)
