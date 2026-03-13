#!/bin/bash
cd /data0/htdocs/rbase-mark/code
.venv/bin/activate
mkdir -p logs
nohup python scripts/start_api_server.py --port 8868 --workers 4 --loop asyncio \
  > logs/api.log 2>&1 &
echo $! > logs/api.pid
echo "API server started, PID: $(cat logs/api.pid)"