# 向量数据库架构说明

本文档说明向量数据库在 Deep Academic Research 项目中的作用和使用方式。

## 一、核心定位

向量数据库是项目的**语义检索和知识匹配引擎**，支撑 RAG（检索增强生成）系统的核心能力。

---

## 二、支持的向量数据库

| 数据库 | 实现文件 | 说明 |
|-------|---------|------|
| **Milvus** | `deepsearcher/vector_db/milvus.py` | 主要使用，支持本地和远程部署 |
| **Oracle** | `deepsearcher/vector_db/oracle.py` | 可选，使用 Oracle 原生向量存储 |

### 配置示例

**Milvus 本地模式**:
```yaml
vector_db:
  provider: "Milvus"
  config:
    default_collection: "deepsearcher"
    uri: "./milvus.db"
    token: "root:Milvus"
    db: "default"
```

**Milvus 远程模式**:
```yaml
vector_db:
  provider: "Milvus"
  config:
    default_collection: "deepsearcher"
    uri: "http://milvus-server:19530"
    token: "root:Milvus"
```

---

## 三、数据模式（Schema）

### 1. ArticleEntitySchema（文章向量）

存储学术文章的分块数据，用于 RAG 检索。

| 字段 | 类型 | 说明 |
|-----|------|------|
| `id` | INT64 | 主键 |
| `embedding` | FLOAT_VECTOR | 文本向量（维度可配置） |
| `text` | VARCHAR(65535) | 块文本内容 |
| `reference` | VARCHAR(2048) | 文章标题/引用 |
| `reference_id` | INT64 | 关联 raw_article 表 |
| `keywords` | ARRAY<VARCHAR> | 关键词数组 |
| `authors` | ARRAY<VARCHAR> | 作者数组 |
| `author_ids` | ARRAY<INT64> | 作者 ID 数组 |
| `corresponding_authors` | ARRAY<VARCHAR> | 通讯作者 |
| `corresponding_author_ids` | ARRAY<INT64> | 通讯作者 ID |
| `base_ids` | ARRAY<INT64> | 基础库 ID |
| `impact_factor` | FLOAT | 影响因子 |
| `rbase_factor` | FLOAT | 自定义因子 |
| `pubdate` | INT64 | 发布日期（Unix 时间戳） |
| `metadata` | JSON | 额外元数据 |

**用途**: 语义搜索、相似度匹配、按日期/影响因子过滤

### 2. ClassifyValueEntitySchema（分类器值向量）

存储分类器取值及关联术语，用于命名实体匹配。

| 字段 | 类型 | 说明 |
|-----|------|------|
| `id` | INT64 | 主键 |
| `embedding` | FLOAT_VECTOR | 取值向量 |
| `text` | VARCHAR | 取值文本 |
| `classifier_id` | INT64 | 所属分类器 ID |
| `classifier_value_id` | INT64 | 分类器取值 ID |
| `metadata` | JSON | 包含 terms 列表 |

**用途**: 命名实体匹配分类中的候选值推荐

---

## 四、Collection 组织结构

### 命名规范

```
{env}_{project}_{model}_{version}
```

### 示例

| Collection 名称 | 说明 |
|----------------|------|
| `dev_rbase_text_embedding_ada_002_1` | 开发环境，OpenAI Embedding 模型 v1 |
| `prod_rbase_bge_m3_1` | 生产环境，BAAI BGE-M3 模型 v1 |

### Collection 类型

1. **文章 Collections**: 存储 chunked 学术文章数据
   - 用于 RAG 检索（NaiveRAG、DeepSearch、ChainOfRAG 等）
   - 支持多种过滤条件

2. **分类器值 Collections**: 存储分类器的所有取值
   - 用于命名实体匹配分类
   - 支持分类器 ID 过滤

---

## 五、主要使用场景

### 1. 语义搜索（Semantic Search）

**用于**: RAG 系统的文献检索

```python
# 基础检索
retrieval_res = vector_db.search_data(
    collection=collection,
    vector=embedding_model.embed_query(query),
    top_k=10
)
```

**相关模块**:
- `NaiveRAG.retrieve()`: 基础 RAG 检索
- `DeepSearch._search_chunks_from_vectordb()`: 多迭代深层搜索
- `ChainOfRAG.retrieve()`: 链式推理检索

### 2. 带条件的高级过滤检索

**支持的过滤条件**:

```python
# 时间过滤（Unix 时间戳）
filter="pubdate >= 1577836800"

# 影响因子过滤
filter="impact_factor >= 10"

# 组合条件
filter="pubdate >= 1577836800 AND impact_factor >= 10"

# 关键词过滤（数组）
filter='ARRAY_CONTAINS(keywords, "machine learning")'

# 多关键词过滤
filter='ARRAY_CONTAINS_ANY(keywords, ["AI", "deep learning"])'
```

### 3. 分类器值候选检索

**用于**: NAMED_ENTITY 分类方式下的值推荐

```python
# 单个候选
load_classifier_value_by_vector_db(
    vector_db, collection, embedding_model,
    entity_query, classifier_id, entity_name,
    top_k=10, confirm_score=0.5, valid_score=3
)

# 多个候选
load_classifier_values_by_vector_db(
    vector_db, collection, embedding_model,
    entity_query, classifier_id, entity_name,
    top_k=10, max_candidates=5, valid_score=3
)
```

### 4. Collection 路由

**用于**: 自动选择合适的 collection 进行查询

```python
# LLM 分析查询，选择相关 collections
router = CollectionRouter(llm, vector_db)
selected_collections, tokens = router.invoke(query)
```

---

## 六、功能模块与向量库的关系

| 模块 | 文件 | Collection | 用途 |
|-----|------|-----------|------|
| **NaiveRAG** | `agent/naive_rag.py` | article_entity | 基础文献检索 |
| **DeepSearch** | `agent/deep_search.py` | article_entity | 多迭代深层查询 |
| **ChainOfRAG** | `agent/chain_of_rag.py` | article_entity | 链式推理检索 |
| **OverviewRAG** | `agent/overview_rag.py` | article_entity | 论文综述生成 |
| **PersonalRAG** | `agent/personal_rag.py` | article_entity | 研究者成就分析 |
| **ClassifyAgent** | `agent/classify_agent.py` | classify_value_entity | 分类器值推荐 |
| **CollectionRouter** | `agent/collection_router.py` | (所有) | LLM-guided 路由 |

---

## 七、核心接口

### BaseVectorDB 接口

```python
class BaseVectorDB:
    # 初始化/管理
    def init_collection(dim, collection, description, force_new_collection)
    def clear_db(collection)
    def delete_data(collection, ids=None, filter=None)
    def flush(collection_name)
    def close()

    # 数据操作
    def insert_data(collection, chunks, batch_size=256)
    def search_data(collection, vector, top_k=5, filter="")

    # 元数据
    def list_collections() -> List[CollectionInfo]
```

### RetrievalResult 结构

```python
class RetrievalResult:
    embedding: np.array   # 向量
    text: str             # 文本内容
    reference: str        # 引用信息
    metadata: dict        # 元数据（含 reference_id, pubdate 等）
    score: float          # 相似度分数
```

### Chunk 结构（数据插入）

```python
class Chunk:
    text: str             # 块文本
    embedding: list       # 向量
    reference: str        # 引用
    metadata: dict        # 元数据
```

---

## 八、数据流程

### 数据写入流程

```
MySQL raw_article
       │
       ▼
  加载全文/Markdown
       │
       ▼
  文本分块 (Splitter)
       │
       ▼
  计算 Embedding
       │
       ▼
  构建 Metadata
       │
       ▼
  批量写入向量库
       │
       ▼
  记录 vector_db_data_log
```

**相关脚本**:
- `scripts/create_rbase_vector_db.py`: 创建文章向量库
- `scripts/create_classifier_value_vector_db.py`: 创建分类器值向量库

### 数据查询流程

```
用户查询
    │
    ▼
计算 Embedding
    │
    ▼
向量相似度搜索 (+ 可选过滤条件)
    │
    ▼
返回 Top-K 结果
    │
    ▼
传给 LLM 生成回答 (RAG)
```

---

## 九、与 MySQL 的协作关系

| MySQL 表 | 向量数据库 Schema | 关联字段 |
|---------|------------------|---------|
| `raw_article` | ArticleEntity | `reference_id` |
| `classifier_value` | ClassifyValueEntity | `classifier_value_id` |
| `vector_db_data_log` | - | 记录向量库操作日志 |

**协作模式**:
- MySQL 存储结构化元数据
- 向量数据库存储语义向量
- 通过 ID 关联实现"精确查询 + 语义搜索"的混合检索

---

## 十、数据一致性维护

### 日志追踪

所有向量库操作记录到 `vector_db_data_log` 表：

| 字段 | 说明 |
|-----|------|
| `collection` | Collection 名称 |
| `reference_id` | 关联的文章 ID |
| `operation` | 操作类型（INSERT/DELETE/ABSTRACT） |
| `status` | 状态（1=有效，0=失效） |

### 一致性检查

```bash
# 检查向量库数据一致性
python scripts/check_vector_db_integrity.py
```

---

## 十一、性能优化

### 索引策略

- 使用 Milvus 的 metric_type（L2、COSINE 等）
- 为频繁过滤的字段建立索引：
  - `classifier_id` (classify_value_entity)
  - `keywords`, `authors`, `base_ids` 等

### 批处理

```python
# 写入时批量处理
insert_data(collection, chunks, batch_size=256)

# 查询时控制返回数量
search_data(collection, vector, top_k=5)
```

### 去重机制

```python
from deepsearcher.vector_db.base import deduplicate_results
deduplicated = deduplicate_results(results)  # 按 text 去重
```

---

## 十二、关键代码文件

| 文件 | 功能 |
|-----|------|
| `deepsearcher/vector_db/base.py` | 基础接口定义 |
| `deepsearcher/vector_db/milvus.py` | Milvus 实现 |
| `deepsearcher/vector_db/milvus_schema.py` | Schema 定义 |
| `deepsearcher/vector_db/oracle.py` | Oracle 实现 |
| `deepsearcher/agent/naive_rag.py` | 基础 RAG |
| `deepsearcher/agent/deep_search.py` | 深层搜索 |
| `deepsearcher/agent/collection_router.py` | Collection 路由 |
| `deepsearcher/agent/classify_agent.py` | 分类代理 |
| `deepsearcher/api/rbase_util/sync/classify.py` | 分类器值向量搜索 |
| `scripts/create_rbase_vector_db.py` | 创建文章向量库 |
| `scripts/check_vector_db_integrity.py` | 数据一致性检查 |
