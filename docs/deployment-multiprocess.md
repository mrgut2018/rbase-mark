# 多进程部署指南

本文档介绍如何配置 uvicorn 多进程部署来解决接口阻塞问题。

## 问题背景

在单进程模式下，当 `/questions` 接口在处理 LLM 调用时，会阻塞其他接口的调用。这是因为：

1. FastAPI 默认使用单线程同步执行模型
2. LLM 调用是 I/O 密集型操作，需要长时间等待
3. 单进程无法并发处理多个请求

## 解决方案

### 1. 多进程配置

#### 方法一：使用启动脚本（推荐）

```bash
# 使用自动计算的工作进程数
python scripts/start_api_server.py

# 指定工作进程数
python scripts/start_api_server.py --workers 4

# 开发模式（单进程 + 热重载）
python scripts/start_api_server.py --reload --verbose

# 生产模式（多进程）
python scripts/start_api_server.py --workers 4 --loop asyncio
```

#### 方法二：直接使用 uvicorn

```bash
# 多进程模式
uvicorn deepsearcher.api.main:app --host 0.0.0.0 --port 8000 --workers 4 --loop asyncio

# 单进程模式（开发）
uvicorn deepsearcher.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 工作进程数量建议

- **CPU 密集型应用**：工作进程数 = CPU 核心数
- **I/O 密集型应用**（如 LLM 调用）：工作进程数 = CPU 核心数 × 2-4
- **建议范围**：4-8 个工作进程

### 3. 系统服务配置

#### 安装 systemd 服务

```bash
# 复制服务文件
sudo cp scripts/rbase-api.service /etc/systemd/system/

# 修改配置（根据需要调整）
sudo nano /etc/systemd/system/rbase-api.service

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用服务
sudo systemctl enable rbase-api

# 启动服务
sudo systemctl start rbase-api

# 查看状态
sudo systemctl status rbase-api

# 查看日志
sudo journalctl -u rbase-api -f
```

### 4. Nginx 负载均衡配置

#### 安装 nginx 配置

```bash
# 复制 nginx 配置
sudo cp scripts/nginx-rbase-api.conf /etc/nginx/sites-available/rbase-api

# 启用站点
sudo ln -s /etc/nginx/sites-available/rbase-api /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重新加载 nginx
sudo systemctl reload nginx
```

#### 多实例部署

如果需要部署多个 API 实例，可以修改 nginx 配置：

```nginx
upstream rbase_api_backend {
    least_conn;
    
    # 多个 API 实例
    server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8001 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8002 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8003 max_fails=3 fail_timeout=30s;
    
    keepalive 32;
}
```

### 5. 性能优化建议

#### 数据库连接池

确保数据库连接池配置适合多进程：

```python
# 在配置文件中设置
database:
  pool_size: 20  # 每个进程的连接数
  max_overflow: 30
  pool_timeout: 30
  pool_recycle: 3600
```

#### 内存和资源限制

```bash
# 在 systemd 服务文件中设置
LimitNOFILE=65536
LimitNPROC=4096
```

#### 监控和日志

```bash
# 查看进程状态
ps aux | grep uvicorn

# 查看端口占用
netstat -tlnp | grep 8000

# 查看系统资源
htop
```

### 6. 故障排除

#### 常见问题

1. **端口冲突**
   ```bash
   # 检查端口占用
   lsof -i :8000
   
   # 杀死占用进程
   sudo kill -9 <PID>
   ```

2. **内存不足**
   ```bash
   # 查看内存使用
   free -h
   
   # 减少工作进程数
   python scripts/start_api_server.py --workers 2
   ```

3. **数据库连接问题**
   ```bash
   # 检查数据库连接
   mysql -u username -p -h hostname
   
   # 查看连接数
   SHOW PROCESSLIST;
   ```

#### 日志分析

```bash
# 查看应用日志
tail -f logs/api.log

# 查看 nginx 访问日志
tail -f /var/log/nginx/rbase_api_access.log

# 查看系统日志
sudo journalctl -u rbase-api -f
```

### 7. 性能测试

#### 使用 ab 进行压力测试

```bash
# 安装 ab
sudo apt-get install apache2-utils

# 测试并发性能
ab -n 1000 -c 10 http://localhost/api/health

# 测试 questions 接口
ab -n 100 -c 5 -p test_data.json -T application/json http://localhost/api/questions
```

#### 使用 wrk 进行更详细的测试

```bash
# 安装 wrk
sudo apt-get install wrk

# 测试
wrk -t12 -c400 -d30s http://localhost/api/health
```

## 配置示例

### 生产环境配置

```bash
# 启动命令
python scripts/start_api_server.py \
  --workers 4 \
  --loop asyncio \
  --host 0.0.0.0 \
  --port 8000

# 或使用 systemd
sudo systemctl start rbase-api
```

### 开发环境配置

```bash
# 开发模式
python scripts/start_api_server.py \
  --reload \
  --verbose \
  --workers 1
```

## 注意事项

1. **多进程模式下不支持热重载**：`reload=True` 与 `workers > 1` 不兼容
2. **共享状态**：多进程间不共享内存状态，需要外部存储（如 Redis）
3. **资源消耗**：多进程会增加内存和 CPU 消耗
4. **调试困难**：多进程调试比单进程复杂

## 监控指标

建议监控以下指标：

- CPU 使用率
- 内存使用率
- 网络 I/O
- 数据库连接数
- 请求响应时间
- 错误率
- 工作进程状态 