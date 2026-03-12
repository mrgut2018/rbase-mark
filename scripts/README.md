# Scripts 目录说明

本目录包含了 Deep Academic Research 项目的各种实用脚本，用于数据处理、数据库管理、向量数据库操作等功能。

## 📁 脚本列表

### 🔍 数据完整性检查

#### `check_vector_db_integrity.py`
**功能**: 检查 Milvus 向量数据库集合中的数据完整性

**作用**: 
- 验证向量数据库中的每条记录是否在 MySQL 的 `vector_db_data_log` 表中有对应的日志记录
- 检查数据是否满足完整性约束：`status=1` 且 `operation=1` 或 `operation=4`，且 `id_from <= ID <= id_to`
- 生成详细的完整性检查报告

**使用方法**:
```bash
# 基本用法
python scripts/check_vector_db_integrity.py --collection "dev_rbase_bge_base_en_v1_5_1" --output "integrity_check_result.csv"

# 指定批次大小
python scripts/check_vector_db_integrity.py -c "test_collection" -o "test_result.csv" --batch-size 500

# 仅显示统计信息
python scripts/check_vector_db_integrity.py -c "my_collection" --stats-only

# 不预加载缓存（适用于内存受限环境）
python scripts/check_vector_db_integrity.py -c "large_collection" -o "result.csv" --no-preload-cache

# 自动删除无效记录（谨慎使用）
python scripts/check_vector_db_integrity.py -c "my_collection" -o "result.csv" --delete
```

**输出**: CSV 文件包含所有无效记录的详细信息

**特殊功能**:
- `--delete`: 自动删除发现的无效记录（谨慎使用，此操作不可逆）

---

### 🔄 向量数据库查询

#### `query_vector_db_by_id.py`
**功能**: 根据 ID 查询向量数据库中的特定记录

**作用**:
- 通过记录 ID 直接查询向量数据库
- 支持批量 ID 查询
- 提供详细的记录信息展示

**使用方法**:
```bash
# 查询单个记录
python scripts/query_vector_db_by_id.py --collection "my_collection" --id 12345

# 批量查询
python scripts/query_vector_db_by_id.py --collection "my_collection" --ids 12345,12346,12347

# 从文件读取ID列表
python scripts/query_vector_db_by_id.py --collection "my_collection" --id-file "ids.txt"
```

---

### 📊 日志处理

#### `process_vector_db_log.py`
**功能**: 处理和分析向量数据库操作日志

**作用**:
- 分析 `vector_db_data_log` 表中的操作记录
- 统计各种操作类型的数量和状态
- 生成日志分析报告

**使用方法**:
```bash
# 分析指定集合的日志
python scripts/process_vector_db_log.py --collection "my_collection"

# 导出日志统计到CSV
python scripts/process_vector_db_log.py --collection "my_collection" --output "log_analysis.csv"

# 按时间范围分析
python scripts/process_vector_db_log.py --collection "my_collection" --start-date "2024-01-01" --end-date "2024-01-31"
```

---

### 🤖 AI 问题管理

#### `batch_refresh_ai_questions.py`
**功能**: 批量刷新和管理 AI 生成的问题

**作用**:
- 批量更新 AI 生成的问题内容
- 重新生成过期或质量不佳的问题
- 管理问题库的版本控制

**使用方法**:
```bash
# 刷新指定集合的问题
python scripts/batch_refresh_ai_questions.py --collection "my_collection"

# 指定刷新策略
python scripts/batch_refresh_ai_questions.py --collection "my_collection" --strategy "quality_based"

# 限制刷新数量
python scripts/batch_refresh_ai_questions.py --collection "my_collection" --limit 1000
```

---

### 🗄️ 向量数据库创建

#### `create_rbase_vector_db.py`
**功能**: 创建 RBase 专用的向量数据库集合

**作用**:
- 初始化 RBase 项目的向量数据库结构
- 创建必要的集合和索引
- 配置向量数据库参数

**使用方法**:
```bash
# 创建默认集合
python scripts/create_rbase_vector_db.py

# 指定集合名称
python scripts/create_rbase_vector_db.py --collection "my_rbase_collection"

# 指定向量维度
python scripts/create_rbase_vector_db.py --dimension 768
```

#### `create_json_vector_db.py`
**功能**: 从 JSON 数据创建向量数据库

**作用**:
- 将 JSON 格式的数据转换为向量数据库记录
- 支持批量数据导入
- 自动生成向量嵌入

**使用方法**:
```bash
# 从JSON文件创建向量数据库
python scripts/create_json_vector_db.py --input "data.json" --collection "my_collection"

# 指定嵌入模型
python scripts/create_json_vector_db.py --input "data.json" --collection "my_collection" --embedding-model "bge-base-en"

# 批量处理多个文件
python scripts/create_json_vector_db.py --input-dir "data/" --collection "my_collection"
```

---

### 📝 内容合成

#### `compose_overview_with_rag.py`
**功能**: 使用 RAG 技术生成内容概览

**作用**:
- 基于检索增强生成技术创建内容概览
- 整合多个数据源的信息
- 生成结构化的概览文档

**使用方法**:
```bash
# 生成概览
python scripts/compose_overview_with_rag.py --collection "my_collection" --output "overview.md"

# 指定主题
python scripts/compose_overview_with_rag.py --collection "my_collection" --topic "机器学习" --output "ml_overview.md"

# 自定义生成参数
python scripts/compose_overview_with_rag.py --collection "my_collection" --max-length 2000 --output "detailed_overview.md"
```

#### `compose_personal_with_rag.py`
**功能**: 使用 RAG 技术生成个性化内容

**作用**:
- 根据用户偏好生成个性化内容
- 结合用户历史行为和兴趣
- 创建定制化的内容推荐

**使用方法**:
```bash
# 生成个性化内容
python scripts/compose_personal_with_rag.py --user-id "user123" --collection "my_collection" --output "personal_content.md"

# 指定兴趣标签
python scripts/compose_personal_with_rag.py --user-id "user123" --interests "AI,机器学习" --collection "my_collection"

# 设置内容长度
python scripts/compose_personal_with_rag.py --user-id "user123" --collection "my_collection" --max-length 1500
```

---

### 📋 数据处理

#### `process_json_data.py`
**功能**: 处理和转换 JSON 格式的数据

**作用**:
- 清洗和标准化 JSON 数据
- 数据格式转换
- 批量数据处理

**使用方法**:
```bash
# 处理单个JSON文件
python scripts/process_json_data.py --input "raw_data.json" --output "processed_data.json"

# 批量处理目录
python scripts/process_json_data.py --input-dir "raw_data/" --output-dir "processed_data/"

# 指定处理规则
python scripts/process_json_data.py --input "data.json" --rules "clean,normalize,validate"
```

---

### 📚 用户词典管理

#### `create_user_dict.py`
**功能**: 创建和管理用户自定义词典

**作用**:
- 生成用户特定的词汇表
- 支持领域专业术语
- 优化文本处理效果

**使用方法**:
```bash
# 从文本创建词典
python scripts/create_user_dict.py --input "texts.txt" --output "user_dict.txt"

# 指定词典大小
python scripts/create_user_dict.py --input "texts.txt" --output "user_dict.txt" --max-words 10000

# 合并多个词典
python scripts/create_user_dict.py --input "dict1.txt,dict2.txt" --output "merged_dict.txt"
```

---

### 🏷️ 分类器管理

#### `build_classifier_values.py`
**功能**: 根据指定的classifier_id自动构造classifier_value数据

**作用**:
- 从数据库中读取分类器信息并转换为强类型对象
- 验证term_tree_id和term_tree_node_id的有效性
- 自动获取子节点并为每个子节点创建对应的classifier_value记录
- 支持重复数据检测，避免重复创建
- 集成完善的日志系统和错误处理

**工作原理**:
1. **读取分类器数据**: 通过classifier_id从classifier表中读取分类器信息，转换为Classifier对象
2. **验证引用关系**: 检查分类器中的term_tree_id和term_tree_node_id是否存在且有效
3. **获取子节点**: 读取指定term_tree_node下的所有下一级子节点
4. **构造分类值**: 为每个子节点创建对应的ClassifierValue对象并插入数据库

**使用方法**:
```bash
# 基本用法 - 为分类器ID为1构建classifier_value
python scripts/build_classifier_values.py --classifier_id 1

# 详细模式 - 显示详细的执行信息
python scripts/build_classifier_values.py --classifier_id 1 --verbose

# 查看帮助信息
python scripts/build_classifier_values.py --help
```

**输出示例**:
```
开始为分类器 1 构建classifier_value数据...
数据库连接成功
找到分类器: 研究领域分类器 (ID: 1)
term_tree_id和term_tree_node_id验证通过
找到 5 个子节点
成功创建classifier_value: 人工智能 (节点ID: 101)
成功创建classifier_value: 机器学习 (节点ID: 102)
成功创建classifier_value: 深度学习 (节点ID: 103)
成功创建classifier_value: 自然语言处理 (节点ID: 104)
成功创建classifier_value: 计算机视觉 (节点ID: 105)

构建完成: 成功 5/5 个classifier_value

✅ classifier_value构建成功!
数据库连接已关闭
```

**数据结构**:
- **输入依赖**: classifier, term_tree, term_tree_node, concept 表
- **输出数据**: 在classifier_value表中创建新记录，包含value、value_i18n、value_clue等字段
- **模型支持**: 使用Classifier和ClassifierValue强类型模型，支持类型检查和自动验证

**特殊功能**:
- **重复检测**: 自动检测已存在的classifier_value，避免重复创建
- **国际化支持**: 自动构造多语言取值（中文、英文、缩写等）
- **概念关联**: 优先使用concept表中的信息丰富分类值内容
- **事务安全**: 支持事务回滚，确保数据一致性
- **详细日志**: 集成color_print和分级日志系统

**配置要求**:
- 使用`config.rbase.yaml`中的数据库配置
- 需要MySQL数据库连接权限
- 依赖pymysql和项目内部模块

**错误处理**:
- 分类器不存在或状态无效
- term_tree引用验证失败
- 无子节点情况处理
- 数据库操作异常和事务回滚

#### `import_term_tree_nodes.py`
**功能**: 批量导入term_tree_node数据

**作用**:
- 从CSV文件批量导入术语树节点数据
- 自动创建不存在的概念(concept)，包括英文翻译和缩写生成
- 支持交互式确认模式，确保数据准确性
- 维护父子节点关系和层级结构
- 完成后输出完整的树形结构

**工作原理**:
1. **验证基础数据**: 检查term_tree和根节点是否存在
2. **加载CSV数据**: 按level排序确保正确的插入顺序
3. **概念处理**: 查找已存在概念或自动创建新概念
4. **节点创建**: 根据parent_seq建立正确的父子关系
5. **树形输出**: 最终以树形结构显示所有节点

**CSV文件格式**:
```csv
seq,tree_id,value,intro,level,parent_seq,is_category_node
1,60,研究类型,按照原创性、研究方法、数据来源等进行区分,1,0,0
2,60,原创性研究,产生全新知识、概念或方法的研究...,2,1,0
3,60,非原创性研究,基于现有知识进行整合、总结或应用的研究...,2,1,0
```

**字段说明**:
- `seq`: 序号，用于标识节点和建立父子关系
- `tree_id`: 术语树ID，必须与参数中的term_tree_id一致
- `value`: 中文名称（节点概念名称）
- `intro`: 节点介绍说明
- `level`: 层级，脚本会按此字段排序
- `parent_seq`: 父节点序号，0表示根节点的子节点
- `is_category_node`: 是否为分类节点（0或1）

**使用方法**:
```bash
# 基本用法
python scripts/import_term_tree_nodes.py data.csv -t 60 -r 12345

# 交互式确认模式
python scripts/import_term_tree_nodes.py data.csv -t 60 -r 12345 -i

# 详细模式
python scripts/import_term_tree_nodes.py data.csv -t 60 -r 12345 -v

# 完整参数
python scripts/import_term_tree_nodes.py data.csv --term_tree_id 60 --root_node_id 12345 --interactive --verbose
```

**参数说明**:
- `csv_file`: CSV文件路径（必需）
- `-t, --term_tree_id`: 术语树ID（必需）
- `-r, --root_node_id`: 根节点ID（必需）
- `-i, --interactive`: 启用交互式确认模式
- `-v, --verbose`: 显示详细执行信息

**概念自动创建**:
- **中文名**: 使用CSV中的value字段
- **英文名**: 使用academic_translator自动翻译
- **缩写**: 使用LLM生成合适的学术缩写
- **状态**: 自动设置为虚拟概念(is_virtual=1, status=10)

**交互式确认**:
- 发现已存在概念时会显示详情并询问是否使用
- `-i`模式下每次插入前都会确认节点信息
- 支持中途取消或跳过某些节点

**输出示例**:
```
批量导入term_tree_node...
数据库连接成功
找到术语树: Research Type / 研究类型
找到根节点: 研究类型
成功加载 12 条数据，按level排序完成
处理节点 1/12: 原创性研究
成功创建概念 '原创性研究' (ID: 1001)
成功创建节点 '原创性研究' (ID: 2001)
...

✅ 批量导入成功!

📊 完整树形结构:
============================================================
├─ 研究类型 (ID: 12345)
  ├─ 原创性研究 (ID: 2001)
    ├─ 基础研究 (ID: 2002)
    ├─ 应用研究 (ID: 2003)
  ├─ 非原创性研究 [分类] (ID: 2004)
    ├─ 综述研究 (ID: 2005)
    ├─ Meta分析 (ID: 2006)
============================================================
```

**特殊功能**:
- **概念复用**: 智能检测已存在概念，避免重复创建
- **层级验证**: 确保父子关系正确建立
- **事务安全**: 支持回滚，保证数据一致性
- **进度跟踪**: 实时显示处理进度和结果统计
- **树形可视化**: 完成后输出美观的树形结构

**错误处理**:
- term_tree或根节点不存在
- CSV格式错误或数据不一致
- 概念创建失败
- 父子关系建立失败
- 翻译或LLM服务异常

#### `classify_raw_article.py`
**功能**: 为指定的raw_article执行分类

**作用**:
- 从数据库加载指定的raw_article数据
- 初始化分类代理（ClassifyAgent）
- 使用指定的分类器对文章进行分类
- 输出详细的分类结果

**工作原理**:
1. **加载文章数据**: 从raw_article表中根据ID加载完整的文章信息
2. **初始化分类代理**: 配置LLM、嵌入模型、向量数据库等组件
3. **执行分类**: 调用分类器对文章进行分类处理
4. **输出结果**: 显示分类结果和执行状态

**使用方法**:
```bash
# 基本用法 - 使用分类器1对文章123进行分类
python scripts/classify_raw_article.py --classifier_id 1 --raw_article_id 123

# 使用分类器分组批量分类
python scripts/classify_raw_article.py --classifier_group_id 5 --raw_article_id 123

# 详细模式 - 显示详细的执行信息
python scripts/classify_raw_article.py -c 1 -a 123 --verbose

# 查看帮助信息
python scripts/classify_raw_article.py --help
```

**输出示例**:
```
开始为文章 123 执行分类器 1 的分类...
数据库连接成功
找到文章: Deep Learning Approaches for Natural Language Processing... (ID: 123)
分类代理初始化成功
开始执行分类...
分类完成！

============================================================
分类结果:
============================================================
人工智能

根据文章标题"Deep Learning Approaches for Natural Language Processing"
和摘要内容分析，该文章主要讨论深度学习在自然语言处理中的应用，
属于人工智能领域的研究范畴。

推荐分类：人工智能 > 机器学习 > 深度学习
============================================================

✅ 文章分类完成!
```

**配置要求**:
- 使用`config.rbase.yaml`中的LLM和数据库配置
- 需要完整的深度学习环境（LLM、嵌入模型、向量数据库）
- 依赖ClassifyAgent和相关组件

**支持的分类器类型**:
- **一般性分类器**: 基于LLM的文本分类
- **命名实体匹配**: 基于词汇匹配的分类
- **路由分类器**: 多级分类路由（开发中）

**错误处理**:
- 文章不存在或状态无效
- 分类器加载失败
- LLM服务连接异常
- 分类执行超时或错误

#### `export_label_task_result.py`
**功能**: 导出标注任务结果到Excel文件

**作用**:
- 根据label_raw_article_task_id导出完整的标注结果
- 生成包含文章基本信息和标注结果的Excel文件
- 自动计算并展示classifier_value的完整路径
- 提供清晰的数据展示格式

**工作原理**:
1. **加载任务信息**: 从label_raw_article_task表中加载任务基本信息
2. **加载文章信息**: 获取raw_article的ID、标题、DOI等基本信息
3. **加载标注结果**: 从label_raw_article_task_result表中获取所有标注记录
4. **计算value路径**: 通过classifier_value_route获取完整的分类路径
5. **生成Excel**: 创建格式化的Excel文件并保存

**Excel文件结构**:
- **上半部分**: 文章基本信息（raw_article_id, title, doi）
- **下半部分**: 标注结果列表（id, label_item_key, label_item_value, concept_id, term_tree_node_id, value路径）

**使用方法**:
```bash
# 基本用法 - 导出任务ID为100的标注结果
python scripts/export_label_task_result.py --task_id 100

# 指定输出文件路径
python scripts/export_label_task_result.py -t 100 -o /path/to/output.xls

# 详细模式 - 显示详细的执行信息
python scripts/export_label_task_result.py -t 100 --verbose

# 查看帮助信息
python scripts/export_label_task_result.py --help
```

**输出示例**:
```
开始时间: 2025-10-28 14:30:00
任务ID: 100
----------------------------------------------------
数据库连接成功
找到任务: 文章123的分类器组5(研究类型分类)批量任务 (ID: 100)
找到文章: Deep Learning Approaches for Natural Lang... (ID: 123)
找到 15 条标注结果
✅ Excel文件已成功导出到: database/excel/label_raw_article_task_123_100_20251028_143001.xls
共导出 15 条标注结果

✅ 导出成功!
结束时间: 2025-10-28 14:30:02
```

**默认输出路径**:
- 如未指定输出文件，默认保存到：`database/excel/label_raw_article_task_{raw_article_id}_{task_id}_{datetime}.xls`
- 文件名包含文章ID、任务ID和导出时间戳，便于管理和追溯

**value路径说明**:
- 如果term_tree_node_id为空，路径显示为空字符串
- 如果存在term_tree_node_id，会自动查询完整的分类路径
- 路径格式：父级 -> 子级 -> 当前级，例如：`研究类型 -> 原创性研究 -> 基础研究`

**配置要求**:
- 使用`config.rbase.yaml`中的数据库配置
- 需要安装xlwt库（用于Excel文件生成）
- 依赖deepsearcher.api.rbase_util模块

**数据表依赖**:
- label_raw_article_task（任务信息）
- raw_article（文章信息）
- label_raw_article_task_result（标注结果）
- label_raw_article_task_item（任务项信息）
- classifier_value（分类器值和路径）

**错误处理**:
- 任务ID不存在
- 文章数据加载失败
- 路径计算异常
- 文件写入权限问题

---

### 🚀 初始化脚本

#### `init_rbase_vector_db.py`
**功能**: 初始化 RBase 向量数据库环境

**作用**:
- 设置向量数据库连接
- 创建基础集合结构
- 配置默认参数

**使用方法**:
```bash
# 初始化默认环境
python scripts/init_rbase_vector_db.py

# 指定配置文件
python scripts/init_rbase_vector_db.py --config "custom_config.yaml"

# 仅检查环境
python scripts/init_rbase_vector_db.py --check-only
```

---

## 🔧 通用参数

大多数脚本支持以下通用参数：

- `--config`: 指定配置文件路径（默认: `config.rbase.yaml`）
- `--verbose` 或 `-v`: 启用详细输出
- `--help` 或 `-h`: 显示帮助信息

## 📋 使用建议

1. **首次使用**: 建议先运行 `init_rbase_vector_db.py` 初始化环境
2. **数据检查**: 定期使用 `check_vector_db_integrity.py` 检查数据完整性
3. **批量操作**: 对于大量数据，建议使用批处理脚本并设置合适的批次大小
4. **日志分析**: 使用 `process_vector_db_log.py` 监控系统运行状态
5. **内容生成**: 根据需要选择 `compose_overview_with_rag.py` 或 `compose_personal_with_rag.py`

## 🚨 注意事项

- 运行脚本前请确保配置文件正确设置
- 大数据量操作时注意内存使用情况
- 建议在测试环境中先验证脚本功能
- 定期备份重要数据
- 注意数据库连接池的管理

## 📞 技术支持

如遇到问题，请检查：
1. 配置文件是否正确
2. 数据库连接是否正常
3. 相关依赖是否已安装
4. 日志输出中的错误信息 