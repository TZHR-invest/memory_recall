#!/bin/bash

# Memory Recall Web 前端启动脚本

echo "================================"
echo "  Memory Recall Web 前端"
echo "================================"
echo ""

# 检查 API 服务
echo "检查 API 服务状态..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ API 服务运行正常"
else
    echo "⚠️  API 服务未启动"
    echo "请先启动 API 服务："
    echo "  cd ../apps/api"
    echo "  source venv/bin/activate"
    echo "  python -m uvicorn main:app --host 127.0.0.1 --port 8000"
    echo ""
    read -p "是否继续启动前端？(y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "启动 HTTP 服务器..."
echo "前端地址: http://localhost:3000"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 启动 Python HTTP 服务器（端口与 docker-compose web 服务一致）
python3 -m http.server 3000
