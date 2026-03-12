# MySQL 数据库写操作汇总

本文档整理了项目中所有涉及 MySQL 数据库更新操作（INSERT、UPDATE、DELETE）的服务和脚本。

## 一、服务层 (services/)

### 1. task_dispatcher.py
**功能**: 轮询 `auto_task` 表，创建子任务并发送 MNS 消息

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `auto_task` | UPDATE | 更新任务状态（2=进行中，10=成功，20=失败） |
| `auto_sub_task` | INSERT | 创建新的子任务记录 |

### 2. classify_service.py
**功能**: 多进程消费 MNS 消息，执行分类任务

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `auto_sub_task` | UPDATE | 更新子任务状态和参数 |
| `auto_task` | UPDATE | 所有子任务完成后更新父任务状态 |

---

## 二、脚本层 (scripts/)

### 1. classify_raw_article.py
**功能**: 单篇文章分类执行器

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `label_raw_article_task` | INSERT | 创建标注任务 |
| `label_raw_article_task_item` | INSERT, UPDATE | 创建/更新任务项 |
| `label_raw_article_task_result` | INSERT, UPDATE | 保存/取消分类结果 |

### 2. batch_classify_articles.py
**功能**: 批量文章分类

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| (同 classify_raw_article.py) | - | 委托给单篇分类逻辑 |

### 3. build_classifier_values.py
**功能**: 从术语树层次结构构建分类器值

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `classifier_value` | INSERT, UPDATE | 创建或更新分类器值 |
| `term_tree_node` | UPDATE | 递增 children_count |

### 4. import_term_tree_nodes.py
**功能**: 从 CSV 批量导入术语树节点

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `term` | INSERT, UPDATE | 创建术语，关联概念 |
| `concept` | INSERT, UPDATE | 创建或更新概念 |
| `term_tree_node` | INSERT, UPDATE | 创建树节点，更新父节点计数 |

### 5. import_classifiers.py
**功能**: 从 CSV 批量导入分类器定义

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `classifier` | INSERT | 创建分类器记录 |

### 6. fix_incomplete_concepts.py
**功能**: 修复不完整的概念记录

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `term` | INSERT, UPDATE | 创建缺失的术语 |
| `concept` | UPDATE | 更新概念字段 |

### 7. process_vector_db_log.py
**功能**: 管理向量数据库操作日志

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `vector_db_data_log` | INSERT, UPDATE | 记录向量数据库操作，标记失效条目 |

---

## 三、API 工具层 (deepsearcher/api/rbase_util/)

### 1. sync/classify.py
**功能**: 分类相关数据库操作工具

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `label_raw_article_task` | INSERT, UPDATE | 创建/更新分类任务 |
| `label_raw_article_task_item` | INSERT, UPDATE | 创建/更新任务项，含 token 使用统计 |
| `label_raw_article_task_result` | INSERT | 保存单个分类结果 |

### 2. ai_content.py
**功能**: AI 内容响应缓存和日志

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `ai_content_request` | INSERT, UPDATE | 创建/更新内容请求记录 |
| `ai_content_response` | INSERT, UPDATE | 创建/更新响应记录，含 token 统计 |
| `ai_log` | INSERT, UPDATE | 创建/更新操作日志 |

### 3. discuss.py
**功能**: 讨论线程和响应管理

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `discuss_thread` | INSERT, UPDATE | 创建/更新讨论线程，管理收藏和隐藏 |
| `discuss` | INSERT, UPDATE | 创建/更新讨论响应，管理状态 |

---

## 四、数据加载层 (deepsearcher/)

### rbase_db_loading.py
**功能**: 通用数据库加载与日志记录

| 表名 | 操作类型 | 说明 |
|------|---------|------|
| `vector_db_data_log` | INSERT, UPDATE | 记录向量数据库操作（INSERT/ABSTRACT） |

---

## 五、按表分类索引

| 表名 | 涉及的服务/脚本 |
|------|----------------|
| `auto_task` | task_dispatcher.py, classify_service.py |
| `auto_sub_task` | task_dispatcher.py, classify_service.py |
| `label_raw_article_task` | classify_raw_article.py, sync/classify.py |
| `label_raw_article_task_item` | classify_raw_article.py, sync/classify.py |
| `label_raw_article_task_result` | classify_raw_article.py, sync/classify.py |
| `classifier` | import_classifiers.py |
| `classifier_value` | build_classifier_values.py |
| `term` | import_term_tree_nodes.py, fix_incomplete_concepts.py |
| `concept` | import_term_tree_nodes.py, fix_incomplete_concepts.py |
| `term_tree_node` | import_term_tree_nodes.py, build_classifier_values.py |
| `vector_db_data_log` | process_vector_db_log.py, rbase_db_loading.py |
| `ai_content_request` | ai_content.py |
| `ai_content_response` | ai_content.py |
| `ai_log` | ai_content.py |
| `discuss_thread` | discuss.py |
| `discuss` | discuss.py |

---

## 六、关键写入流程

### 1. 异步分类流程
```
task_dispatcher.py
  → INSERT auto_sub_task
  → UPDATE auto_task (状态=进行中)
  → 发送 MNS 消息

classify_service.py (消费 MNS)
  → 执行分类
  → UPDATE auto_sub_task (状态更新)
  → UPDATE auto_task (完成状态)

RawArticleClassifier
  → INSERT label_raw_article_task
  → INSERT label_raw_article_task_item
  → INSERT label_raw_article_task_result
```

### 2. 批量数据导入流程
```
import_term_tree_nodes.py
  → INSERT term (创建术语)
  → INSERT concept (创建概念)
  → INSERT term_tree_node (创建节点)
  → UPDATE term_tree_node (更新父节点计数)

build_classifier_values.py
  → INSERT/UPDATE classifier_value
```

### 3. 内容缓存流程
```
ai_content.py
  → INSERT ai_content_request (请求记录)
  → INSERT ai_content_response (响应记录)
  → INSERT ai_log (操作日志)
  → UPDATE (状态和统计更新)
```

### 4. 讨论管理流程
```
discuss.py
  → INSERT discuss_thread (创建线程)
  → INSERT discuss (创建响应)
  → UPDATE (状态、标题、收藏管理)
```

---

## 七、注意事项

1. **软删除**: 系统不使用 DELETE 操作，而是通过 UPDATE 状态字段实现软删除
2. **事务管理**: 关键操作使用数据库事务保证一致性
3. **日志追踪**: `vector_db_data_log` 表记录所有向量数据库操作，便于审计
4. **服务依赖**: `task-dispatcher` 应在 `classify-service` 之前启动
