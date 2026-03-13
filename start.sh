#!/bin/bash
cd /data0/htdocs/rbase-mark/code
. .venv/bin/activate
mkdir -p logs

# 停止旧进程
if [ -f logs/api.pid ]; then
    OLD_PID=$(cat logs/api.pid)
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping old process (PID: $OLD_PID)..."
        kill "$OLD_PID"
        sleep 2
        # 如果还没退出，强制杀掉
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID"
            echo "Force killed old process"
        fi
    fi
    rm -f logs/api.pid
fi
nohup python -u scripts/start_api_server.py --port 8868 --workers 4 --loop asyncio \
  > logs/api.log 2>&1 &
echo $! > logs/api.pid
echo "API server started, PID: $(cat logs/api.pid)"