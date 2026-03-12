# Deep Academic Research 项目架构

## 系统概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Deep Academic Research                             │
│                        (基于 RAG 的学术研究辅助系统)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
          ▼                           ▼                           ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│    API 服务      │       │   任务调度服务    │       │   分类工作服务   │
│  (FastAPI)      │       │ (task_dispatcher)│       │(classify_service)│
│  Port: 8000     │       │                 │       │   多进程消费     │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                         │                         │
         │                         ▼                         │
         │              ┌─────────────────┐                  │
         │              │   阿里云 MNS     │◄─────────────────┘
         │              │   (消息队列)     │
         │              └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              核心模块层                                       │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│   Agent 模块    │    LLM 模块     │  Embedding 模块  │    Vector DB 模块     │
│                 │                 │                 │                       │
│ - SummaryRAG    │ - OpenAI       │ - OpenAI        │ - Milvus              │
│ - OverviewRAG   │ - DeepSeek     │ - Voyage        │ - Oracle              │
│ - PersonalRAG   │ - Anthropic    │ - Bedrock       │                       │
│ - DiscussAgent  │ - Gemini       │ - SiliconFlow   │                       │
│ - ClassifyAgent │ - SiliconFlow  │ - Milvus        │                       │
│ - DeepSearch    │ - TogetherAI   │                 │                       │
│ - ChainOfRAG    │ - XAI          │                 │                       │
│ - NaiveRAG      │ - Ollama       │                 │                       │
│ - Translator    │ - Azure OpenAI │                 │                       │
└─────────────────┴─────────────────┴─────────────────┴───────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据存储层                                       │
├─────────────────────────────────────┬───────────────────────────────────────┤
│            MySQL                    │           Milvus / Oracle              │
│         (元数据存储)                 │            (向量数据库)                 │
│                                     │                                       │
│ - 文献元数据 (raw_article)           │ - 文献向量嵌入                          │
│ - 分类器定义 (classifier)            │ - 语义检索                             │
│ - 术语树 (term_tree)                 │ - 相似度匹配                            │
│ - 任务管理 (auto_task)               │                                       │
└─────────────────────────────────────┴───────────────────────────────────────┘
```

---

## 服务架构详情

### 1. API 服务 (FastAPI)

**启动命令:**
```bash
python scripts/start_api_server.py
# 或
python -m deepsearcher.api.main
```

**路由结构:**
```
/api
├── /generate
│   ├── POST /summary      # AI 摘要生成 (支持流式)
│   ├── POST /questions    # 推荐问题生成
│   └── POST /discuss      # 对话问答 (支持流式)
│
├── /backend
│   ├── POST /ai_article_titles           # AI 生成文章标题建议
│   ├── POST /delete_article_vector_db    # 删除向量数据
│   └── POST /ai_translate                # AI 学术翻译
│
├── GET  /           # API 信息
└── GET  /health     # 健康检查
```

**依赖 Agent:**
| 路由 | Agent | 功能 |
|------|-------|------|
| `/summary` | SummaryRAG | 文献智能摘要 |
| `/questions` | SummaryRAG | 推荐问题生成 |
| `/discuss` | DiscussAgent | 学术对话问答 |
| `/ai_article_titles` | ArticleTitleAgent | 标题建议生成 |
| `/ai_translate` | AcademicTranslator | 中英学术翻译 |

---

### 2. 任务调度服务 (Task Dispatcher)

**启动命令:**
```bash
python services/task_dispatcher.py --interval 5 --verbose
```

**工作流程:**
```
┌─────────────┐     轮询      ┌─────────────┐    创建     ┌─────────────┐
│  auto_task  │ ────────────► │ Dispatcher  │ ─────────► │auto_sub_task│
│   (待处理)   │              │             │            │             │
└─────────────┘              └──────┬──────┘            └─────────────┘
                                    │
                                    │ 发送消息
                                    ▼
                             ┌─────────────┐
                             │  阿里云 MNS  │
                             │   消息队列   │
                             └─────────────┘
```

**支持的任务类型:**
| 任务类型 | 说明 |
|----------|------|
| `AI_GENERAL_CLASSIFY_RAW_ARTICLE` | 通用分类任务 |
| `AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE` | 特定库分类任务 |
| `AI_SINGLE_CLASSIFY_RAW_ARTICLE` | 单篇文章分类 |

---

### 3. 分类工作服务 (Classify Service)

**启动命令:**
```bash
python services/classify_service.py --workers 4 --verbose
```

**工作流程:**
```
┌─────────────┐    消费消息    ┌─────────────┐   执行分类   ┌─────────────┐
│  阿里云 MNS  │ ────────────► │   Worker    │ ──────────► │ClassifyAgent│
│   消息队列   │              │  (多进程)    │            │             │
└─────────────┘              └──────┬──────┘            └──────┬──────┘
                                    │                          │
                                    │ 更新状态                  │ 保存结果
                                    ▼                          ▼
                             ┌─────────────┐           ┌──────────────────┐
                             │auto_sub_task│           │raw_article_      │
                             │  auto_task  │           │classifier_result │
                             └─────────────┘           └──────────────────┘
```

**分类器类型:**
| 类型 | 说明 |
|------|------|
| `GENERAL_VALUE` | 基于 LLM 的文本分类 |
| `NAMED_ENTITY` | 命名实体匹配 (可结合向量库) |
| `ROUTING` | 多级分类路由 |

---

## 项目目录结构

```
deep-academic-research/
├── deepsearcher/                # 核心包
│   ├── api/                     # API 服务
│   │   ├── main.py             # FastAPI 应用入口
│   │   ├── models.py           # Pydantic 模型定义
│   │   ├── routes/             # 路由定义
│   │   │   ├── summary.py      # 摘要生成路由
│   │   │   ├── questions.py    # 问题生成路由
│   │   │   ├── discuss.py      # 对话路由
│   │   │   ├── backend.py      # 后台管理路由
│   │   │   └── stream.py       # 流式响应工具
│   │   └── rbase_util/         # 数据库工具
│   │       ├── ai_content.py   # AI 内容存取
│   │       ├── discuss.py      # 对话存取
│   │       └── metadata.py     # 元数据查询
│   │
│   ├── agent/                   # RAG Agent 模块
│   │   ├── summary_rag.py      # 文献摘要 RAG
│   │   ├── overview_rag.py     # 研究综述 RAG
│   │   ├── persoanl_rag.py     # 研究者分析 RAG
│   │   ├── discuss_agent.py    # 对话问答 Agent
│   │   ├── classify_agent.py   # 文献分类 Agent
│   │   ├── deep_search.py      # 深度检索 Agent
│   │   ├── chain_of_rag.py     # 链式推理 RAG
│   │   ├── naive_rag.py        # 基础 RAG
│   │   ├── academic_translator.py  # 学术翻译器
│   │   ├── article_title_agent.py  # 标题生成 Agent
│   │   └── prompts/            # Prompt 模板
│   │
│   ├── llm/                     # LLM 提供商
│   │   ├── base.py             # 基类
│   │   ├── openai_llm.py       # OpenAI
│   │   ├── deepseek.py         # DeepSeek
│   │   ├── anthropic_llm.py    # Anthropic Claude
│   │   ├── gemini.py           # Google Gemini
│   │   ├── siliconflow.py      # SiliconFlow
│   │   ├── together_ai.py      # TogetherAI
│   │   ├── xai.py              # XAI (Grok)
│   │   ├── ollama.py           # Ollama (本地)
│   │   └── azure_openai.py     # Azure OpenAI
│   │
│   ├── embedding/               # Embedding 模型
│   │   ├── base.py             # 基类
│   │   ├── openai_embedding.py # OpenAI Embedding
│   │   ├── voyage_embedding.py # Voyage Embedding
│   │   ├── bedrock_embedding.py# AWS Bedrock
│   │   ├── siliconflow_embedding.py
│   │   └── milvus_embedding.py # Milvus 内置
│   │
│   ├── vector_db/               # 向量数据库
│   │   ├── milvus.py           # Milvus 实现
│   │   └── oracle.py           # Oracle 实现
│   │
│   ├── rbase/                   # 数据模型
│   │   ├── ai_models.py        # AI 相关模型
│   │   ├── raw_article.py      # 文献模型
│   │   ├── rbase_article.py    # 扩展文献模型
│   │   └── terms.py            # 术语模型
│   │
│   └── configuration.py         # 配置管理
│
├── services/                    # 后台服务
│   ├── task_dispatcher.py      # 任务调度服务
│   └── classify_service.py     # 分类工作服务
│
├── scripts/                     # 操作脚本
│   ├── start_api_server.py     # 启动 API 服务
│   ├── classify_raw_article.py # 单篇分类测试
│   ├── batch_classify_articles.py  # 批量分类
│   ├── create_rbase_vector_db.py   # 创建向量库
│   ├── check_vector_db_integrity.py # 数据完整性检查
│   ├── create_user_dict.py     # 生成术语词典
│   └── ...
│
├── database/                    # 数据库
│   └── mysql/
│       ├── migrations/         # 迁移脚本
│       └── schema/             # 表结构定义
│
├── config.yaml                  # 通用配置
├── config.rbase.yaml           # RBase 专用配置
└── pyproject.toml              # 项目配置
```

---

## 数据库表清单

### 核心业务表

| 表名 | 说明 | 主要用途 |
|------|------|----------|
| `base` | 文献库 | 管理不同的文献数据集/项目 |
| `raw_article` | 原始文献 | 存储文献元数据 (标题、DOI、摘要等) |
| `vector_db_data_log` | 向量操作日志 | 记录向量库的增删改操作 |

### 术语系统表

| 表名 | 说明 | 主要用途 |
|------|------|----------|
| `term_tree` | 术语树 | 定义分类词表结构 |
| `term_tree_node` | 术语树节点 | 词表中的具体节点 |
| `concept` | 词簇 | 概念聚合 (同义词归类) |
| `term` | 术语 | 具体的术语/词条 |

### 分类系统表

| 表名 | 说明 | 主要用途 |
|------|------|----------|
| `classifier` | 分类器 | 定义分类器规则和参数 |
| `classifier_value` | 分类器取值 | 分类器的可选值列表 |
| `classifier_group` | 分类器分组 | 分类器逻辑分组 |
| `classifier_group_relation` | 分组关联 | 分组与分类器的关联关系 |
| `raw_article_classifier_result` | 分类结果 | 文献的分类结果存储 |

### 任务管理表

| 表名 | 说明 | 主要用途 |
|------|------|----------|
| `auto_task` | 自动任务 | 主任务记录 |
| `auto_sub_task` | 子任务 | 具体执行的子任务 |

### 标注系统表

| 表名 | 说明 | 主要用途 |
|------|------|----------|
| `label_raw_article_task` | 标注任务 | 文献标注的主任务 |
| `label_raw_article_task_item` | 标注子项 | 标注任务的具体项目 |
| `label_raw_article_task_result` | 标注结果 | 标注的结果数据 |
| `label_check_task` | 审核任务 | 标注审核的主任务 |
| `label_check_task_item` | 审核子项 | 审核的具体项目 |
| `label_check_task_item_log` | 审核日志 | 审核操作记录 |

### AI 内容表

| 表名 | 说明 | 主要用途 |
|------|------|----------|
| `ai_content_request` | AI 请求 | 缓存 AI 生成请求 |
| `ai_content_response` | AI 响应 | 缓存 AI 生成结果 |
| `ai_log` | AI 日志 | AI 操作日志 |

### 对话系统表

| 表名 | 说明 | 主要用途 |
|------|------|----------|
| `discuss_thread` | 对话主题 | 对话会话管理 |
| `discuss` | 对话内容 | 具体的对话消息 |

---

## 配置文件说明

### config.yaml / config.rbase.yaml

```yaml
# LLM 配置
llm:
  provider: "DeepSeek"  # OpenAI, DeepSeek, Anthropic, etc.
  config:
    api_key: "sk-xxx"
    model: "deepseek-chat"

# Embedding 配置
embedding:
  provider: "OpenAIEmbedding"
  config:
    api_key: "sk-xxx"
    model: "text-embedding-3-small"

# 向量数据库配置
vector_db:
  provider: "Milvus"
  config:
    uri: "./milvus.db"  # Lite 模式
    # uri: "http://localhost:19530"  # Server 模式

# MySQL 配置
rbase_settings:
  database:
    config:
      host: "localhost"
      port: 3306
      database: "rbase"
      username: "root"
      password: "xxx"

# MNS 配置 (异步任务需要)
  mns:
    endpoint: "https://xxx.mns.cn-hangzhou.aliyuncs.com"
    access_id: "xxx"
    access_key: "xxx"
    queue_name: "classify-queue"
```

---

## 快速启动

```bash
# 1. 环境准备
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e .

# 2. 配置数据库
# 执行 database/mysql/migrations/*.sql

# 3. 启动 API 服务
python scripts/start_api_server.py

# 4. (可选) 启动异步分类服务
python services/task_dispatcher.py --interval 5 &
python services/classify_service.py --workers 4 &
```
