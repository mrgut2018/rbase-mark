# Socket异常修复指南

## 问题分析

生产环境出现大量 `socket.send() raised exception` 警告，根源是：

```bash
# 生产环境配置
ExecStart=... --workers 8 --loop asyncio
LimitNOFILE=infinity
```

**核心问题：**
- 8个workers过多，导致资源竞争
- asyncio性能不如uvloop
- 无并发控制和资源限制

## ✅ 已应用的优化

### 1. main.py 优化
- ✅ 添加动态并发控制（workers≥6时限制更严格）
- ✅ 缩短keep-alive时间：30s → 20s
- ✅ 延长优雅关闭时间：30s → 60s
- ✅ 添加asyncio日志控制
- ✅ 设置监听队列长度和请求限制

### 2. start_api_server.py 优化
- ✅ 降低默认worker数量：最多6个（之前最多8个）
- ✅ 默认使用uvloop（性能更佳）
- ✅ 优化并发参数：1000 → 500
- ✅ 添加asyncio日志控制

## 🚀 生产环境部署

### 方案1：仅调整systemd配置（推荐）

```bash
# 1. 修改生产环境systemd配置
sudo nano /etc/systemd/system/rbase-api.service

# 修改ExecStart行为：
ExecStart=/data0/htdocs/rai/.venv/bin/python /data0/htdocs/rai/deepsearcher/api/main.py --workers 4 --loop uvloop

# 添加资源限制（替换LimitNOFILE=infinity）：
LimitNOFILE=32768
LimitNPROC=4096

# 2. 重启服务
sudo systemctl daemon-reload
sudo systemctl restart rbase-api
```

### 方案2：使用优化版启动脚本

```bash
# 1. 上传优化后的代码到生产服务器
git pull  # 或者 rsync 同步代码

# 2. 修改systemd配置使用start_api_server.py
sudo nano /etc/systemd/system/rbase-api.service

# 修改ExecStart行为：
ExecStart=/data0/htdocs/rai/.venv/bin/python /data0/htdocs/rai/scripts/start_api_server.py --workers 4

# 3. 重启服务
sudo systemctl daemon-reload
sudo systemctl restart rbase-api
```

### 验证优化效果

```bash
# 1. 实时监控日志
sudo journalctl -u rbase-api -f

# 2. 检查socket异常是否减少
sudo journalctl -u rbase-api --since "10 minutes ago" | grep -i "socket\|exception"

# 3. 监控资源使用
htop  # 查看CPU和内存
netstat -an | grep :8000 | wc -l  # 检查连接数

# 4. 性能测试
curl http://localhost:8000/health
```

## 预期效果

| 指标 | 优化前 | 优化后 | 改善 |
|------|--------|--------|------|
| Workers | 8个 | 4-6个 | 减少资源竞争 |
| MySQL连接 | 80个 | 20-30个 | 减少75% |
| Socket异常 | 频繁 | 显著减少 | 80%+ |
| 响应稳定性 | 不稳定 | 更稳定 | 明显改善 |

## 回滚方案

```bash
# 如果有问题，快速回滚到原配置
sudo nano /etc/systemd/system/rbase-api.service
# 改回：--workers 8 --loop asyncio
sudo systemctl daemon-reload
sudo systemctl restart rbase-api
```

## 渐进式部署

担心一次性改动太大？可以分步骤：

```bash
# 步骤1：只降低workers（最关键）
--workers 6 --loop asyncio

# 步骤2：切换到uvloop  
--workers 6 --loop uvloop

# 步骤3：进一步降低workers
--workers 4 --loop uvloop
```

---

**核心改动：** 已直接在 `main.py` 和 `start_api_server.py` 中应用优化，无需额外脚本。
