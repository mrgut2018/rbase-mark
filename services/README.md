# 分类服务系统

这是一个完整的分类服务系统，由两个服务组成：

1. **任务分配服务** (`task_dispatcher.py`): 轮询auto_task并创建子任务和MNS消息
2. **分类执行服务** (`classify_service.py`): 多进程从MNS接收消息并执行文章分类

## 系统架构

```
[auto_task表] 
    ↓ (轮询)
[任务分配服务] → [创建auto_sub_task] → [发送MNS消息]
                                              ↓
[MNS队列] ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ┘
    ↓ (接收消息)
[分类执行服务 Worker1, Worker2, Worker3, Worker4...]
    ↓ (执行分类)
[更新auto_sub_task和auto_task状态]
```

---

## 任务分配服务 (Task Dispatcher)

### 功能特性

- **轮询机制**: 定期轮询auto_task表查找待处理任务
- **任务类型支持**:
  - `AI_GENERAL_CLASSIFY_RAW_ARTICLE`: 通用分类（base_id为NULL的分类器组）
  - `AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE`: 特定库分类（指定base_id的分类器组）
  - `AI_SINGLE_CLASSIFY_RAW_ARTICLE`: 单个分类器分类
- **自动创建子任务**: 根据任务类型自动创建对应的auto_sub_task
- **消息队列集成**: 为每个子任务发送MNS消息触发执行

### 工作流程

1. 轮询status=1的auto_task（特定类型）
2. 解析任务的input JSON字符串获取参数
3. 更新auto_task状态为执行中(2)
4. 根据任务类型创建子任务：
   - **AI_GENERAL_CLASSIFY_RAW_ARTICLE**: 查询所有base_id为NULL的classifier_group
   - **AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE**: 查询指定base_id的classifier_group
   - **AI_SINGLE_CLASSIFY_RAW_ARTICLE**: 验证classifier_id是否存在
5. 为每个auto_sub_task发送MNS消息

### 使用方法

#### 1. 直接运行

```bash
# 使用默认配置（5秒轮询间隔）
python3 services/task_dispatcher.py

# 指定轮询间隔
python3 services/task_dispatcher.py --interval 10

# 启用详细日志
python3 services/task_dispatcher.py --verbose

# 指定配置文件
python3 services/task_dispatcher.py --config /path/to/config.yaml
```

#### 2. 作为系统服务运行

```bash
# 编辑服务文件
sudo nano services/task-dispatcher.service

# 复制服务文件
sudo cp services/task-dispatcher.service /etc/systemd/system/

# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable task-dispatcher

# 启动服务
sudo systemctl start task-dispatcher

# 查看状态
sudo systemctl status task-dispatcher

# 查看日志
sudo journalctl -u task-dispatcher -f
```

### auto_task 输入格式

`auto_task` 表的 `input` 字段应为 JSON 字符串，包含以下内容：

#### AI_GENERAL_CLASSIFY_RAW_ARTICLE
```json
{
  "raw_article_id": 123,
  "base_id": 1
}
```

#### AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE
```json
{
  "raw_article_id": 123,
  "base_id": 2
}
```

#### AI_SINGLE_CLASSIFY_RAW_ARTICLE
```json
{
  "raw_article_id": 123,
  "base_id": 1,
  "classifier_id": 10
}
```

### auto_task 状态说明

- `0`: 无效
- `1`: 待执行（任务分配服务会处理）
- `2`: 执行中（已创建子任务）
- `10`: 已完成（所有子任务完成）
- `20`: 已失败

---

## 分类执行服务 (Classification Service)

这是一个多进程分类服务，用于从阿里云MNS消息队列接收任务并执行文章分类。

## 功能特性

- **多进程处理**: 支持配置多个工作进程并发处理消息
- **MNS集成**: 从阿里云MNS队列接收消息
- **智能分类**: 根据消息内容自动选择合适的分类器或分类器组
- **状态跟踪**: 自动更新auto_sub_task和auto_task的执行状态
- **错误处理**: 完善的异常处理和重试机制

## 依赖安装

```bash
pip install aliyun-mns
```

或者更新requirements.txt并安装：

```bash
pip install -r requirements.txt
```

## 配置

在 `config.rbase.yaml` 的 `rbase_settings` 部分添加MNS配置：

```yaml
rbase_settings:
  # ... 其他配置 ...
  
  # 阿里云MNS配置
  mns:
    endpoint: 'http://your-account-id.mns.cn-hangzhou.aliyuncs.com'
    access_id: 'YOUR_ACCESS_KEY_ID'
    access_key: 'YOUR_ACCESS_KEY_SECRET'
    queue_name: 'rbase-test'
    verify_ssl: false  # 是否验证SSL证书（开发环境建议设为false，生产环境建议设为true）
```

**注意**：
- 如果使用 `https://` endpoint，建议在开发环境设置 `verify_ssl: false` 以避免SSL证书验证问题
- 在生产环境，建议设置 `verify_ssl: true` 并正确配置SSL证书
- 也可以使用 `http://` endpoint（不加密）来避免SSL问题，但不推荐用于生产环境
```

## 消息格式

服务接收的消息应为JSON字符串，包含以下字段：

```json
{
  "auto_task_id": 123,           // 必需：任务ID
  "auto_sub_task_id": 456,       // 必需：子任务ID
  "raw_article_id": 789,         // 必需：文章ID
  "base_id": 1,                  // 必需：用户库ID
  "classifier_id": 10,           // 可选：分类器ID（与classifier_group_id二选一）
  "classifier_group_id": 2       // 可选：分类器组ID（与classifier_id二选一）
}
```

### 字段说明

- **auto_task_id**: auto_task表的主键ID
- **auto_sub_task_id**: auto_sub_task表的主键ID
- **raw_article_id**: 要分类的文章ID
- **base_id**: 用户库ID
- **classifier_id**: （可选）指定分类器ID
  - 与 `classifier_group_id` 至少提供其中之一
  - 如果提供：直接使用该分类器执行分类
  - 如果同时提供了 `classifier_group_id`，则此字段会被忽略
- **classifier_group_id**: （可选）指定分类器组ID
  - 与 `classifier_id` 至少提供其中之一
  - 如果提供：使用该分类器组执行批量分类
  - 优先级高于 `classifier_id`

**重要说明**：
- `classifier_id` 和 `classifier_group_id` 必须至少提供其中之一
- 如果同时提供两者，系统将优先使用 `classifier_group_id`，忽略 `classifier_id`
- 建议根据实际需求只提供其中一个字段

## 使用方法

### 1. 直接运行（开发/测试）

```bash
# 使用默认配置（4个工作进程）
python3 services/classify_service.py

# 指定工作进程数量
python3 services/classify_service.py --workers 8

# 启用详细日志
python3 services/classify_service.py --verbose

# 指定配置文件
python3 services/classify_service.py --config /path/to/config.yaml
```

### 2. 作为系统服务运行（生产环境）

#### 步骤1: 编辑服务文件

编辑 `services/classify-service.service`，修改以下路径：

```ini
WorkingDirectory=/path/to/deep-academic-research
ExecStart=/usr/bin/python3 /path/to/deep-academic-research/services/classify_service.py --config /path/to/deep-academic-research/config.rbase.yaml --workers 4
```

根据需要调整：
- `User` 和 `Group`: 运行服务的用户和组
- `--workers`: 工作进程数量
- Python解释器路径（如果使用虚拟环境）

#### 步骤2: 安装服务

```bash
# 复制服务文件到systemd目录
sudo cp services/classify-service.service /etc/systemd/system/

# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable classify-service

# 启动服务
sudo systemctl start classify-service
```

#### 步骤3: 管理服务

```bash
# 查看服务状态
sudo systemctl status classify-service

# 停止服务
sudo systemctl stop classify-service

# 重启服务
sudo systemctl restart classify-service

# 查看服务日志
sudo journalctl -u classify-service -f

# 查看最近的100行日志
sudo journalctl -u classify-service -n 100
```

## 工作流程

1. **接收消息**: 工作进程从MNS队列接收消息（长轮询）
2. **解析消息**: 解析JSON格式的消息内容
3. **更新状态**: 将auto_sub_task状态更新为"执行中"(status=2)
4. **执行分类**:
   - 如果提供了classifier_id: 使用指定分类器执行分类
   - 如果未提供classifier_id: 根据base_id查找所有classifier_group并执行
5. **保存结果**: 将分类结果保存到数据库
6. **更新子任务**: 根据执行结果更新auto_sub_task状态
   - 成功: status=10
   - 失败: status=20
7. **检查主任务**: 检查该auto_task下的所有子任务是否都完成
8. **更新主任务**: 如果所有子任务完成，更新auto_task的状态
9. **删除消息**: 从MNS队列删除已处理的消息

## 状态码

### auto_sub_task状态
- `0`: 无效
- `1`: 待执行
- `2`: 执行中
- `10`: 已完成
- `20`: 已失败

### auto_task状态
- `0`: 无效
- `1`: 待执行
- `2`: 执行中
- `10`: 已完成
- `20`: 已失败

## 监控和日志

### 日志位置

- **开发环境**: 标准输出/标准错误
- **生产环境**: systemd journal
  ```bash
  sudo journalctl -u classify-service
  ```

### 日志级别

- 普通模式: INFO级别
- 详细模式 (`--verbose`): DEBUG级别

### 日志内容

- 工作进程启动/停止
- 消息接收和处理
- 分类任务执行
- 数据库操作
- 错误和异常

## 性能调优

### 工作进程数量

根据以下因素确定合适的工作进程数：

- **CPU核心数**: 建议不超过CPU核心数
- **内存容量**: 每个进程约需要1-2GB内存（取决于分类器复杂度）
- **数据库连接数**: 确保数据库支持足够的并发连接
- **消息速率**: 根据消息到达速率调整

推荐配置：
- 开发/测试: 2-4个进程
- 生产环境: 4-8个进程

### 资源限制

在服务文件中已配置：
- 文件描述符限制: 65536
- 进程数限制: 4096

可根据实际需求调整。

## 故障排查

### 问题1: SSL证书验证失败

**错误信息**:
```
MNSClientNetworkException: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```

**可能原因**:
- macOS系统上Python的SSL证书未正确安装
- 使用了https endpoint但系统无法验证证书

**解决方法**:

**方案1（推荐）**：在配置文件中禁用SSL验证（开发环境）
```yaml
mns:
  verify_ssl: false
```

**方案2**：使用http endpoint而不是https
```yaml
mns:
  endpoint: 'http://1664987339199249.mns.cn-qingdao.aliyuncs.com'
```

**方案3**：安装Python SSL证书（macOS）
```bash
# 方法1：运行Python的证书安装脚本
/Applications/Python\ 3.11/Install\ Certificates.command

# 方法2：使用pip安装certifi
pip install --upgrade certifi
```

### 问题2: 服务无法启动

**可能原因**:
- 配置文件路径错误
- MNS配置不完整
- 数据库连接失败

**解决方法**:
```bash
# 查看详细错误信息
sudo journalctl -u classify-service -n 50

# 手动运行测试
python3 services/classify_service.py --verbose
```

### 问题3: 消息处理失败

**可能原因**:
- 消息格式错误
- 文章不存在
- 分类器配置问题
- 数据库写入失败

**解决方法**:
- 检查消息格式是否符合规范
- 验证文章和分类器是否存在
- 查看详细日志定位问题

### 问题3: 进程崩溃

**可能原因**:
- 内存不足
- 数据库连接超时
- 未处理的异常

**解决方法**:
- 检查系统资源使用情况
- 增加数据库连接超时时间
- 查看crash日志

## 安全建议

1. **配置文件安全**
   - 确保配置文件权限正确 (chmod 600)
   - 不要将配置文件提交到版本控制系统

2. **用户权限**
   - 使用专用的非root用户运行服务
   - 限制服务用户的文件系统访问权限

3. **网络安全**
   - 使用HTTPS/TLS连接MNS
   - 限制数据库访问来源

## 完整部署指南

### 步骤1: 启动两个服务

系统需要同时运行两个服务才能正常工作：

```bash
# 1. 启动任务分配服务
sudo systemctl start task-dispatcher
sudo systemctl status task-dispatcher

# 2. 启动分类执行服务
sudo systemctl start classify-service
sudo systemctl status classify-service
```

### 步骤2: 验证服务运行

```bash
# 查看任务分配服务日志
sudo journalctl -u task-dispatcher -f

# 查看分类执行服务日志
sudo journalctl -u classify-service -f
```

### 步骤3: 创建测试任务

```sql
-- 插入一个测试任务到auto_task表
INSERT INTO auto_task (base_id, foreign_key_id, type, input, priority, status, created, modified)
VALUES (
    1,  -- base_id
    123,  -- raw_article_id
    'AI_SINGLE_CLASSIFY_RAW_ARTICLE',  -- 任务类型
    '{"raw_article_id": 123, "base_id": 1, "classifier_id": 10}',  -- JSON格式的input
    0,  -- 优先级
    1,  -- 状态（1=待执行）
    NOW(),
    NOW()
);
```

### 步骤4: 观察任务执行

1. **任务分配服务** 会轮询到这个任务
2. 创建 `auto_sub_task` 记录
3. 发送消息到MNS队列
4. **分类执行服务** 接收消息并执行分类
5. 更新 `auto_sub_task` 和 `auto_task` 状态

### 服务启停顺序

**启动顺序**（推荐）：
1. 先启动 `task-dispatcher`
2. 再启动 `classify-service`

**停止顺序**（推荐）：
1. 先停止 `task-dispatcher`（停止创建新任务）
2. 等待 `classify-service` 处理完现有任务
3. 再停止 `classify-service`

```bash
# 优雅停止
sudo systemctl stop task-dispatcher
sleep 30  # 等待现有任务处理完
sudo systemctl stop classify-service
```

## 维护

### 日常维护

```bash
# 每天检查服务状态
sudo systemctl status classify-service

# 定期查看日志
sudo journalctl -u classify-service --since "1 day ago"

# 监控资源使用
top -p $(pgrep -f classify_service.py)
```

### 更新部署

```bash
# 1. 拉取最新代码
git pull

# 2. 重启服务
sudo systemctl restart classify-service

# 3. 验证服务运行正常
sudo systemctl status classify-service
```

## 开发和测试

### 本地测试

```bash
# 启动服务（单进程，详细日志）
python3 services/classify_service.py --workers 1 --verbose

# 发送测试消息到MNS队列
# (需要单独编写测试脚本)
```

### 单元测试

```bash
# 运行测试（如果有）
python3 -m pytest tests/test_classify_service.py
```

## 相关文档

- [分类器配置](../docs/classifier-config.md)
- [数据库Schema](../database/mysql/schema/)
- [API文档](../docs/api.md)

## 许可证

参见项目根目录的LICENSE文件。

