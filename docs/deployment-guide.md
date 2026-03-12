# Deep Academic Research 部署文档

## 目录

- [1. 环境要求](#1-环境要求)
- [2. 服务器准备](#2-服务器准备)
- [3. 项目部署](#3-项目部署)
- [4. 数据库初始化](#4-数据库初始化)
- [5. 配置文件](#5-配置文件)
- [6. 服务部署](#6-服务部署)
- [7. Nginx 反向代理](#7-nginx-反向代理)
- [8. 服务管理](#8-服务管理)
- [9. 数据库备份](#9-数据库备份)
- [10. 监控与日志](#10-监控与日志)
- [11. 故障排查](#11-故障排查)
- [12. 安全加固](#12-安全加固)

---

## 1. 环境要求

### 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 磁盘 | 50 GB SSD | 100 GB SSD |

### 软件要求

| 软件 | 版本要求 |
|------|---------|
| 操作系统 | Ubuntu 20.04+ / CentOS 7+ |
| Python | 3.10+ |
| MySQL | 5.7+ / 8.0 (推荐阿里云 RDS) |
| Milvus | 2.3+ |
| Nginx | 1.18+ |
| systemd | 已预装 |

### 外部服务依赖

| 服务 | 用途 | 必需 |
|------|------|------|
| 阿里云 DashScope | LLM (Qwen Plus/Max) | 是 |
| DeepSeek API | 推理模型 (DeepSeek Reasoner) | 是 |
| 阿里云 MNS | 异步任务消息队列 | 分类服务需要 |
| 阿里云绿网 | 敏感词检测 | 可选 |
| 阿里云 OSS | 文件存储 | 可选 |
| Milvus 向量数据库 | 语义检索 | 是 |

---

## 2. 服务器准备

### 2.1 创建服务用户

```bash
# 创建 rbase 用户（用于 API 服务）
sudo useradd -r -m -s /bin/bash rbase
sudo mkdir -p /opt/rbase
sudo chown rbase:rbase /opt/rbase
```

### 2.2 安装系统依赖

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip \
    nginx mysql-client git build-essential \
    libssl-dev libffi-dev python3-dev

# CentOS / RHEL
sudo yum install -y python310 python310-devel \
    nginx mysql git gcc openssl-devel libffi-devel
```

### 2.3 安装 Milvus（如果自建）

```bash
# 使用 Docker 部署 Milvus Standalone
wget https://github.com/milvus-io/milvus/releases/download/v2.3.0/milvus-standalone-docker-compose.yml -O docker-compose.yml
docker compose up -d
```

> 如使用远程 Milvus 实例，可跳过此步骤。

---

## 3. 项目部署

### 3.1 获取代码

```bash
sudo -u rbase bash
cd /opt/rbase

# 从 Git 仓库克隆
git clone <your-repo-url> deep-academic-research
cd deep-academic-research
```

### 3.2 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3.3 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 3.4 创建必要目录

```bash
mkdir -p logs data
```

### 3.5 验证安装

```bash
python -c "import deepsearcher; print('安装成功')"
```

---

## 4. 数据库初始化

### 4.1 创建数据库

```bash
mysql -h <DB_HOST> -P 3306 -u <DB_USER> -p -e "
CREATE DATABASE IF NOT EXISTS online_rbase
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
"
```

### 4.2 执行迁移脚本

按顺序执行迁移文件：

```bash
cd /opt/rbase/deep-academic-research

# 方式一：使用初始化脚本（推荐）
bash database/mysql/scripts/init_database.sh \
  --host <DB_HOST> \
  --port 3306 \
  --user <DB_USER> \
  --password <DB_PASSWORD> \
  --database online_rbase

# 方式二：手动执行
mysql -h <DB_HOST> -u <DB_USER> -p online_rbase < database/mysql/migrations/001_init_tables.sql
mysql -h <DB_HOST> -u <DB_USER> -p online_rbase < database/mysql/migrations/002_ai_log_article_count.sql
mysql -h <DB_HOST> -u <DB_USER> -p online_rbase < database/mysql/migrations/003_ai_classify.sql
mysql -h <DB_HOST> -u <DB_USER> -p online_rbase < database/mysql/migrations/004_update_classifier_group.sql
mysql -h <DB_HOST> -u <DB_USER> -p online_rbase < database/mysql/schema/term_related_tables.sql
```

### 4.3 验证数据库

```bash
mysql -h <DB_HOST> -u <DB_USER> -p online_rbase -e "SHOW TABLES;"
```

---

## 5. 配置文件

### 5.1 创建生产配置

复制模板并编辑生产配置：

```bash
cp config.rbase.yaml config.prod.yaml
```

编辑 `config.prod.yaml`，需要修改以下关键配置项：

```yaml
provide_settings:
  # --- LLM 配置 ---
  llm:
    provider: "OpenAI"
    config:
      host: "qwen"
      model: "qwen-plus"
      api_key: "<YOUR_QWEN_API_KEY>"          # ← 替换
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
      stream: false
      verbose: false                           # ← 生产环境建议关闭
      timeout: 120

  reasoning_llm:
    provider: "OpenAI"
    config:
      host: "deepseek"
      model: "deepseek-reasoner"
      api_key: "<YOUR_DEEPSEEK_API_KEY>"       # ← 替换
      base_url: "https://api.deepseek.com"
      stream: true
      enable_thinking: true
      verbose: false                           # ← 生产环境建议关闭
      timeout: 120

  writing_llm:
    provider: "OpenAI"
    config:
      host: "qwen"
      model: "qwen-max-latest"
      api_key: "<YOUR_QWEN_WRITING_API_KEY>"   # ← 替换
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
      stream: true
      verbose: false
      timeout: 120

  # --- 向量数据库 ---
  vector_db:
    provider: "Milvus"
    config:
      default_collection: "prod_rbase_bge_base_en_v1_5_1"
      uri: "<MILVUS_URI>"                      # ← 替换，如 http://x.x.x.x:19530
      token: "<MILVUS_TOKEN>"                  # ← 替换
      db: "default"

  # --- Embedding ---
  embedding:
    on_demand_initialize: false
    provider: "MilvusEmbedding"
    config:
      model: "default"

rbase_settings:
  verbose: false                               # ← 生产环境关闭
  env: "prod"                                  # ← 改为 prod

  # --- MySQL ---
  database:
    provider: "mysql"
    config:
      host: "<MYSQL_HOST>"                     # ← 替换
      port: 3306
      database: "online_rbase"
      username: "<MYSQL_USER>"                 # ← 替换
      password: "<MYSQL_PASSWORD>"             # ← 替换

  # --- 阿里云 OSS ---
  oss:
    host: "<OSS_ENDPOINT>"                     # ← 替换

  # --- 敏感词检测 ---
  sensitive_word_detection:
    access_key_id: "<ALIYUN_AK_ID>"            # ← 替换
    access_key_secret: "<ALIYUN_AK_SECRET>"    # ← 替换
    region: "cn-beijing"
    enabled: true

  # --- MNS 消息队列 ---
  mns:
    endpoint: "<MNS_ENDPOINT>"                 # ← 替换
    access_id: "<ALIYUN_AK_ID>"                # ← 替换
    access_key: "<ALIYUN_AK_SECRET>"           # ← 替换
    queue_name: "auto-task-prod"               # ← 生产队列名
    verify_ssl: true                           # ← 生产环境开启

  # --- API 设置 ---
  api:
    log_file: "logs/api.log"
    summary_cache_days: 5
    host: "0.0.0.0"
    port: 8000
```

> **安全提醒**：配置文件包含敏感凭证，请确保文件权限为 `600`，且不要提交到 Git 仓库。

```bash
chmod 600 config.prod.yaml
```

### 5.2 配置验证

```bash
source venv/bin/activate
python -c "
from deepsearcher.configuration import init_rbase_config
config = init_rbase_config('config.prod.yaml')
print('✓ 配置加载成功')
print(f'  LLM: {config.llm}')
print(f'  Vector DB: {config.vector_db}')
"
```

---

## 6. 服务部署

项目包含 3 个服务组件：

| 服务 | 功能 | 端口 |
|------|------|------|
| rbase-api | REST API 服务 | 8000 |
| task-dispatcher | 任务轮询与分发 | 无 |
| classify-service | 分类任务消费者 | 无 |

### 6.1 API 服务

#### 安装 systemd 服务文件

```bash
# 复制并修改服务文件
sudo cp scripts/rbase-api.service /etc/systemd/system/rbase-api.service
```

编辑 `/etc/systemd/system/rbase-api.service`，确认路径正确：

```ini
[Unit]
Description=Rbase API Server
After=network.target
Wants=network.target

[Service]
Type=exec
User=rbase
Group=rbase
WorkingDirectory=/opt/rbase/deep-academic-research
Environment=PYTHONPATH=/opt/rbase/deep-academic-research
ExecStart=/opt/rbase/deep-academic-research/venv/bin/python \
    /opt/rbase/deep-academic-research/scripts/start_api_server.py \
    --config config.prod.yaml \
    --workers 4 \
    --loop asyncio
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rbase-api

LimitNOFILE=65536
LimitNPROC=4096

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/rbase/deep-academic-research/logs /opt/rbase/deep-academic-research/data

[Install]
WantedBy=multi-user.target
```

#### 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable rbase-api
sudo systemctl start rbase-api
sudo systemctl status rbase-api
```

#### 验证 API

```bash
curl http://localhost:8000/health
# 预期返回: {"status": "ok"} 或类似响应
```

### 6.2 任务分发服务

```bash
# 复制并修改服务文件
sudo cp services/task-dispatcher.service /etc/systemd/system/task-dispatcher.service
```

编辑 `/etc/systemd/system/task-dispatcher.service`，替换路径：

```ini
[Service]
Type=simple
User=rbase
Group=rbase
WorkingDirectory=/opt/rbase/deep-academic-research
Environment="PATH=/opt/rbase/deep-academic-research/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/rbase/deep-academic-research"
ExecStart=/opt/rbase/deep-academic-research/venv/bin/python \
    /opt/rbase/deep-academic-research/services/task_dispatcher.py \
    --config /opt/rbase/deep-academic-research/config.prod.yaml \
    --interval 5
Restart=always
RestartSec=10
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable task-dispatcher
sudo systemctl start task-dispatcher
```

### 6.3 分类服务

```bash
# 复制并修改服务文件
sudo cp services/classify-service.service /etc/systemd/system/classify-service.service
```

编辑 `/etc/systemd/system/classify-service.service`，替换路径：

```ini
[Service]
Type=simple
User=rbase
Group=rbase
WorkingDirectory=/opt/rbase/deep-academic-research
Environment="PATH=/opt/rbase/deep-academic-research/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/rbase/deep-academic-research"
ExecStart=/opt/rbase/deep-academic-research/venv/bin/python \
    /opt/rbase/deep-academic-research/services/classify_service.py \
    --config /opt/rbase/deep-academic-research/config.prod.yaml \
    --workers 4
Restart=always
RestartSec=10
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable classify-service
sudo systemctl start classify-service
```

> **注意**：`task-dispatcher` 应在 `classify-service` 之前启动。

---

## 7. Nginx 反向代理

### 7.1 安装配置

```bash
# 复制 Nginx 配置
sudo cp scripts/nginx-rbase-api.conf /etc/nginx/sites-available/rbase-api

# 启用站点
sudo ln -s /etc/nginx/sites-available/rbase-api /etc/nginx/sites-enabled/

# 删除默认站点（如需要）
sudo rm -f /etc/nginx/sites-enabled/default
```

### 7.2 修改配置

编辑 `/etc/nginx/sites-available/rbase-api`：

```nginx
upstream rbase_api_backend {
    least_conn;

    # 单实例部署时只保留一个 server
    server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
    # 多实例部署时添加更多
    # server 127.0.0.1:8001 max_fails=3 fail_timeout=30s;

    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com;           # ← 替换为实际域名

    client_max_body_size 10M;

    # LLM 调用需要较长超时
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    location /health {
        proxy_pass http://rbase_api_backend;
        access_log off;
    }

    location /api/ {
        proxy_pass http://rbase_api_backend;

        gzip on;
        gzip_vary on;
        gzip_min_length 1024;
        gzip_types application/json text/plain;
    }

    access_log /var/log/nginx/rbase_api_access.log;
    error_log /var/log/nginx/rbase_api_error.log;
}
```

### 7.3 配置 HTTPS（推荐）

```bash
# 使用 Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

或手动配置 SSL 证书，参考 `scripts/nginx-rbase-api.conf` 中的 HTTPS 配置段。

### 7.4 启动 Nginx

```bash
sudo nginx -t                # 测试配置
sudo systemctl enable nginx
sudo systemctl restart nginx
```

---

## 8. 服务管理

### 8.1 常用命令

```bash
# 查看所有服务状态
sudo systemctl status rbase-api task-dispatcher classify-service

# 重启单个服务
sudo systemctl restart rbase-api

# 查看日志（实时）
sudo journalctl -u rbase-api -f
sudo journalctl -u task-dispatcher -f
sudo journalctl -u classify-service -f

# 查看最近 100 行日志
sudo journalctl -u rbase-api -n 100 --no-pager
```

### 8.2 启动顺序

正确的启动顺序：

```bash
# 1. 确保 MySQL 和 Milvus 已就绪
# 2. 启动 API 服务
sudo systemctl start rbase-api

# 3. 启动任务分发（先于分类服务）
sudo systemctl start task-dispatcher

# 4. 启动分类服务
sudo systemctl start classify-service

# 5. 启动 Nginx
sudo systemctl start nginx
```

### 8.3 停止服务

```bash
# 按逆序停止
sudo systemctl stop classify-service
sudo systemctl stop task-dispatcher
sudo systemctl stop rbase-api
```

### 8.4 批量操作脚本

可创建便捷管理脚本 `/opt/rbase/manage.sh`：

```bash
#!/bin/bash
SERVICES="rbase-api task-dispatcher classify-service"

case "$1" in
    start)
        for svc in $SERVICES; do
            sudo systemctl start $svc
            echo "$svc started"
        done
        ;;
    stop)
        for svc in $(echo $SERVICES | tr ' ' '\n' | tac); do
            sudo systemctl stop $svc
            echo "$svc stopped"
        done
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        sudo systemctl status $SERVICES --no-pager
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        ;;
esac
```

---

## 9. 数据库备份

### 9.1 手动备份

```bash
bash database/mysql/scripts/backup_database.sh \
    --host <DB_HOST> \
    --user <DB_USER> \
    --password <DB_PASSWORD> \
    --database online_rbase \
    --backup-dir /opt/rbase/backups
```

### 9.2 自动备份（Cron）

```bash
# 编辑 crontab
sudo crontab -e

# 每天凌晨 2 点执行备份
0 2 * * * /opt/rbase/deep-academic-research/database/mysql/scripts/backup_database.sh \
    --host <DB_HOST> --user <DB_USER> --password <DB_PASSWORD> \
    --database online_rbase --backup-dir /opt/rbase/backups \
    >> /opt/rbase/logs/backup.log 2>&1
```

---

## 10. 监控与日志

### 10.1 日志位置

| 日志 | 路径 |
|------|------|
| API 应用日志 | `/opt/rbase/deep-academic-research/logs/api.log` |
| API systemd 日志 | `journalctl -u rbase-api` |
| Task Dispatcher 日志 | `journalctl -u task-dispatcher` |
| Classify Service 日志 | `journalctl -u classify-service` |
| Nginx 访问日志 | `/var/log/nginx/rbase_api_access.log` |
| Nginx 错误日志 | `/var/log/nginx/rbase_api_error.log` |

### 10.2 日志轮转

创建 `/etc/logrotate.d/rbase`：

```
/opt/rbase/deep-academic-research/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
}
```

### 10.3 健康检查

```bash
# API 健康检查
curl -sf http://localhost:8000/health || echo "API 异常"

# 检查服务进程
systemctl is-active rbase-api task-dispatcher classify-service

# 检查端口监听
ss -tlnp | grep 8000
```

### 10.4 向量数据库完整性检查

```bash
cd /opt/rbase/deep-academic-research
source venv/bin/activate
python scripts/check_vector_db_integrity.py --config config.prod.yaml
```

---

## 11. 故障排查

### 11.1 API 服务无法启动

```bash
# 查看详细错误
sudo journalctl -u rbase-api -n 50 --no-pager

# 手动启动测试
cd /opt/rbase/deep-academic-research
source venv/bin/activate
python scripts/start_api_server.py --config config.prod.yaml --workers 1
```

### 11.2 数据库连接失败

```bash
# 测试 MySQL 连接
mysql -h <DB_HOST> -P 3306 -u <DB_USER> -p -e "SELECT 1;"

# 检查网络
telnet <DB_HOST> 3306
```

### 11.3 Milvus 连接失败

```bash
# 测试 Milvus 连接
python -c "
from pymilvus import connections
connections.connect(uri='<MILVUS_URI>', token='<MILVUS_TOKEN>')
print('Milvus 连接成功')
"
```

### 11.4 MNS 消息积压

```bash
# 查看分类服务日志
sudo journalctl -u classify-service -n 100 --no-pager | grep -i error

# 增加 worker 数量
# 编辑 /etc/systemd/system/classify-service.service
# 修改 --workers 4 为 --workers 8
sudo systemctl daemon-reload
sudo systemctl restart classify-service
```

### 11.5 SSL 证书问题

分类服务调用外部 API 时可能遇到 SSL 问题：

```bash
# 更新 CA 证书
sudo apt install ca-certificates
sudo update-ca-certificates

# 如开发环境临时禁用（不推荐生产使用）
# 在 config.prod.yaml 中设置 mns.verify_ssl: false
```

---

## 12. 安全加固

### 12.1 文件权限

```bash
# 配置文件仅 owner 可读
chmod 600 /opt/rbase/deep-academic-research/config.prod.yaml

# 项目目录权限
chown -R rbase:rbase /opt/rbase/deep-academic-research
chmod 750 /opt/rbase/deep-academic-research
```

### 12.2 防火墙

```bash
# 只开放必要端口
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable

# 不要对外暴露 8000 端口（通过 Nginx 代理访问）
```

### 12.3 配置检查清单

- [ ] `config.prod.yaml` 中 `verbose` 设为 `false`
- [ ] `config.prod.yaml` 中 `env` 设为 `"prod"`
- [ ] MNS `verify_ssl` 设为 `true`
- [ ] MNS `queue_name` 使用生产队列（非 test 队列）
- [ ] API key 不包含在 Git 仓库中
- [ ] MySQL 用户仅授予必要权限
- [ ] Milvus token 已修改（非默认 `root:Milvus`）
- [ ] Nginx 已配置 HTTPS
- [ ] 防火墙已启用

---

## 部署检查清单（Quick Checklist）

```
[ ] 1. 服务器准备：用户创建、系统依赖安装
[ ] 2. 代码部署：克隆代码、创建虚拟环境、安装依赖
[ ] 3. 数据库：创建数据库、执行迁移脚本、验证表结构
[ ] 4. 向量数据库：确认 Milvus 可连接、collection 已创建
[ ] 5. 配置文件：创建 config.prod.yaml、填写所有凭证、设置权限
[ ] 6. systemd 服务：安装 3 个服务文件、daemon-reload
[ ] 7. 启动服务：按顺序启动 rbase-api → task-dispatcher → classify-service
[ ] 8. Nginx：安装配置、测试、启动
[ ] 9. 验证：curl 健康检查、查看日志无错误
[ ] 10. 安全：文件权限、防火墙、HTTPS
[ ] 11. 备份：配置自动备份 cron
[ ] 12. 监控：日志轮转、健康检查
```
