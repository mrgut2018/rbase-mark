# 项目代码分类指南

## 代码结构总览

```
deepsearcher/
├── 🔵 业务代码 (Business Logic)
│   │
│   ├── agent/                      # 核心业务 Agent
│   │   ├── summary_rag.py          # 📌 文献摘要生成
│   │   ├── overview_rag.py         # 📌 研究综述生成
│   │   ├── persoanl_rag.py         # 📌 研究者成果分析
│   │   ├── discuss_agent.py        # 📌 学术问答对话
│   │   ├── classify_agent.py       # 📌 文献自动分类
│   │   ├── academic_translator.py  # 📌 学术术语翻译
│   │   ├── article_title_agent.py  # 📌 标题建议生成
│   │   ├── classifier_value_process.py  # 分类值处理
│   │   ├── sensitive_word_detection_agent.py  # 敏感词检测
│   │   └── prompts/                # 业务 Prompt 模板
│   │       ├── summary_prompts.py
│   │       ├── discuss_prompts.py
│   │       ├── classify_prompts.py
│   │       └── article_title_prompts.py
│   │
│   ├── api/routes/                 # API 业务路由
│   │   ├── summary.py              # 📌 摘要生成接口
│   │   ├── questions.py            # 📌 推荐问题接口
│   │   ├── discuss.py              # 📌 对话问答接口
│   │   ├── backend.py              # 📌 后台管理接口
│   │   └── metadata.py             # 元数据查询
│   │
│   ├── api/rbase_util/             # 业务数据操作
│   │   ├── ai_content.py           # AI 内容存取
│   │   ├── discuss.py              # 对话数据存取
│   │   ├── metadata.py             # 元数据查询
│   │   └── sync/                   # 同步操作
│   │       ├── classify.py
│   │       └── metadata.py
│   │
│   ├── rbase/                      # 业务数据模型
│   │   ├── ai_models.py            # 📌 分类器、任务等模型
│   │   ├── raw_article.py          # 📌 文献模型
│   │   ├── rbase_article.py        # 扩展文献模型
│   │   └── terms.py                # 术语模型
│   │
│   └── rbase_db_loading.py         # 📌 业务数据加载
│
├── 🟢 基础设施代码 (Infrastructure)
│   │
│   ├── llm/                        # LLM 提供商适配层
│   │   ├── base.py                 # 基类
│   │   ├── openai_llm.py
│   │   ├── deepseek.py
│   │   ├── anthropic_llm.py
│   │   ├── gemini.py
│   │   └── ...
│   │
│   ├── embedding/                  # Embedding 适配层
│   │   ├── base.py
│   │   ├── openai_embedding.py
│   │   └── ...
│   │
│   ├── vector_db/                  # 向量数据库适配层
│   │   ├── base.py
│   │   ├── milvus.py
│   │   ├── oracle.py
│   │   └── milvus_schema.py
│   │
│   ├── loader/                     # 数据加载器
│   │   ├── file_loader/            # 文件加载
│   │   ├── web_crawler/            # 网页爬取
│   │   └── splitter.py             # 文本切分
│   │
│   ├── db/                         # 数据库连接
│   │   ├── mysql_connection.py
│   │   └── async_mysql_connection.py
│   │
│   └── tools/                      # 工具类
│       ├── log.py
│       ├── json_util.py
│       └── milvus_query_builder.py
│
├── 🟡 通用 RAG Agent (可复用)
│   │
│   ├── agent/
│   │   ├── base.py                 # Agent 基类
│   │   ├── naive_rag.py            # 基础 RAG
│   │   ├── deep_search.py          # 深度搜索
│   │   ├── chain_of_rag.py         # 链式 RAG
│   │   ├── collection_router.py    # 集合路由
│   │   ├── rag_router.py           # RAG 路由
│   │   └── json_agent.py           # JSON 解析
│   │
│   └── api/
│       ├── main.py                 # FastAPI 入口
│       ├── models.py               # 请求/响应模型
│       └── routes/stream.py        # 流式响应工具
│
└── configuration.py                # 配置管理
```

---

## 核心业务代码一览

| 文件 | 业务功能 | 重要程度 |
|------|----------|----------|
| `agent/summary_rag.py` | 文献智能摘要 | ⭐⭐⭐ |
| `agent/overview_rag.py` | 研究综述生成 | ⭐⭐⭐ |
| `agent/classify_agent.py` | 文献自动分类 | ⭐⭐⭐ |
| `agent/discuss_agent.py` | 学术问答对话 | ⭐⭐⭐ |
| `agent/academic_translator.py` | 中英术语翻译 | ⭐⭐ |
| `api/routes/summary.py` | 摘要 API | ⭐⭐⭐ |
| `api/routes/discuss.py` | 对话 API | ⭐⭐⭐ |
| `rbase/ai_models.py` | 分类器数据模型 | ⭐⭐⭐ |
| `rbase/raw_article.py` | 文献数据模型 | ⭐⭐⭐ |
| `rbase_db_loading.py` | 数据库加载 | ⭐⭐ |

---

## 后台服务（业务代码）

```
services/
├── task_dispatcher.py      # 📌 任务调度服务
└── classify_service.py     # 📌 分类工作服务
```

---

## 代码分类说明

| 颜色 | 分类 | 说明 |
|------|------|------|
| 🔵 蓝色 | 业务代码 | 核心业务逻辑，需要重点关注和维护 |
| 🟢 绿色 | 基础设施 | 可插拔的适配层，换 LLM/数据库只改配置 |
| 🟡 黄色 | 通用能力 | 业务无关的通用 RAG 能力，可复用 |

---

## 业务代码详细说明

### 1. Agent 模块 (`deepsearcher/agent/`)

核心业务逻辑所在，每个 Agent 负责特定的学术研究功能：

| Agent | 文件 | 功能描述 |
|-------|------|----------|
| **SummaryRAG** | `summary_rag.py` | 基于 RAG 的文献智能摘要，支持流式输出 |
| **OverviewRAG** | `overview_rag.py` | 研究主题综述生成，整合多篇文献 |
| **PersonalRAG** | `persoanl_rag.py` | 研究者成果分析与总结 |
| **DiscussAgent** | `discuss_agent.py` | 学术问答对话，支持上下文 |
| **ClassifyAgent** | `classify_agent.py` | 文献自动分类，支持多种分类器类型 |
| **AcademicTranslator** | `academic_translator.py` | 中英学术术语翻译，结合 jieba 分词 |
| **ArticleTitleAgent** | `article_title_agent.py` | AI 生成文章标题建议 |

### 2. API 路由 (`deepsearcher/api/routes/`)

对外暴露的 REST API 接口：

| 路由文件 | 接口 | 功能 |
|----------|------|------|
| `summary.py` | `POST /api/generate/summary` | 生成文献摘要 |
| `questions.py` | `POST /api/generate/questions` | 生成推荐问题 |
| `discuss.py` | `POST /api/generate/discuss` | 学术对话问答 |
| `backend.py` | `POST /api/backend/*` | 后台管理接口 |
| `metadata.py` | - | 元数据查询辅助 |

### 3. 数据模型 (`deepsearcher/rbase/`)

业务数据结构定义：

| 文件 | 模型 | 说明 |
|------|------|------|
| `ai_models.py` | Classifier, ClassifierValue, AIContentRequest... | 分类器、AI 请求相关模型 |
| `raw_article.py` | RawArticle | 原始文献模型 |
| `rbase_article.py` | RbaseArticle | 扩展文献模型 |
| `terms.py` | Term, Concept, TermTree... | 术语系统模型 |

### 4. 后台服务 (`services/`)

异步任务处理服务：

| 服务 | 文件 | 功能 |
|------|------|------|
| 任务调度器 | `task_dispatcher.py` | 轮询 auto_task 表，创建子任务，发送 MNS 消息 |
| 分类工作服务 | `classify_service.py` | 多进程消费 MNS 消息，执行文献分类 |

---

## 基础设施代码说明

这些代码是可插拔的适配层，更换提供商只需修改配置文件：

### LLM 适配层 (`deepsearcher/llm/`)

支持的 LLM 提供商：
- OpenAI
- DeepSeek
- Anthropic (Claude)
- Google Gemini
- SiliconFlow
- TogetherAI
- XAI (Grok)
- Ollama (本地)
- Azure OpenAI

### Embedding 适配层 (`deepsearcher/embedding/`)

支持的 Embedding 提供商：
- OpenAI
- Voyage
- AWS Bedrock
- SiliconFlow
- Milvus 内置

### 向量数据库适配层 (`deepsearcher/vector_db/`)

支持的向量数据库：
- Milvus (含 Lite 模式)
- Oracle

---

## 如何阅读业务代码

1. **从 API 入口开始**：`deepsearcher/api/routes/` 下的路由文件
2. **追踪到 Agent**：每个路由调用对应的 Agent 处理业务逻辑
3. **查看 Prompt**：`agent/prompts/` 下的 Prompt 模板决定 LLM 输出
4. **理解数据模型**：`rbase/` 下的模型定义数据结构
5. **数据加载**：`rbase_db_loading.py` 负责从数据库加载业务数据
