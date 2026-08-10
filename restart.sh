#!/bin/bash
# Memory Recall 一键服务管理脚本
# 用法: ./restart.sh [start|stop|restart|status|logs]
# 统一管理 4 个容器: api (8000) / postgres (5432) / adminer (8888) / web (3000)

set -euo pipefail
cd "$(dirname "$0")/apps/api"

ACTION="${1:-start}"
COMPOSE="docker compose -f docker-compose.yml"

case "$ACTION" in
  start)
    echo "启动 Memory Recall 全部服务..."
    $COMPOSE up -d
    ;;
  stop)
    echo "停止 Memory Recall 全部服务..."
    $COMPOSE down
    ;;
  restart)
    echo "重启 Memory Recall 全部服务..."
    $COMPOSE up -d --force-recreate
    ;;
  status)
    $COMPOSE ps
    ;;
  logs)
    $COMPOSE logs -f "$2"
    ;;
  *)
    echo "用法: $0 [start|stop|restart|status|logs <service>]"
    echo "服务: api / postgres / adminer / web"
    exit 1
    ;;
esac

if [[ "$ACTION" == "start" || "$ACTION" == "restart" ]]; then
  echo ""
  echo "等待服务就绪..."
  for i in $(seq 1 20); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
      VERSION=$(curl -s http://localhost:8000/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))")
      echo "✅ API 就绪 (v$VERSION, 端口 8000)"
      break
    fi
    sleep 1
  done
  for p in "web:3000"; do
    NAME="${p%%:*}"; PORT="${p##*:}"
    if curl -sf -o /dev/null "http://localhost:${PORT}/"; then
      echo "✅ ${NAME} 就绪 (端口 ${PORT})"
    else
      echo "⚠️  ${NAME} 未就绪 (端口 ${PORT})"
    fi
  done
  echo ""
  echo "服务地址:"
  echo "  API:     http://localhost:8000/docs"
  echo "  Trace:   http://localhost:3000/debug.html"
  echo "  仪表盘:  http://localhost:3000/dashboard.html"
  echo "  Adminer: http://localhost:8888"
fi
