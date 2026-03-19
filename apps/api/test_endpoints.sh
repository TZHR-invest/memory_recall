#!/bin/bash
# API 端点测试脚本
# 使用 curl 测试所有实现的端点

API_URL="http://localhost:8000"
API_V1="$API_URL/api/v1"

echo "========================================"
echo "Memory Recall API - 端点测试"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 测试函数
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4
    
    echo "测试: $description"
    echo "端点: $method $endpoint"
    
    if [ -z "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X $method "$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X $method "$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "${GREEN}✅ 成功 (HTTP $http_code)${NC}"
        echo "响应: $(echo $body | jq -C '.' 2>/dev/null || echo $body)"
    else
        echo -e "${RED}❌ 失败 (HTTP $http_code)${NC}"
        echo "响应: $body"
    fi
    
    echo ""
}

echo "1. 健康检查"
echo "----------------------------------------"
test_endpoint "GET" "$API_URL/health" "" "基本健康检查"
test_endpoint "GET" "$API_URL/health/db" "" "数据库健康检查"

echo ""
echo "2. 统计信息"
echo "----------------------------------------"
test_endpoint "GET" "$API_URL/api/stats" "" "统计概览"
test_endpoint "GET" "$API_URL/api/stats/timeline?days=7" "" "时间线统计"
test_endpoint "GET" "$API_URL/api/stats/tags?limit=10" "" "标签统计"

echo ""
echo "3. 创建记忆"
echo "----------------------------------------"
test_endpoint "POST" "$API_V1/memories" \
'{
    "content": "今天和老同学在咖啡店见面聊天，聊了很多以前的事情",
    "input_type": "text",
    "tags": ["社交", "老同学"]
}' \
"创建记忆"

echo ""
echo "4. 列出记忆"
echo "----------------------------------------"
test_endpoint "GET" "$API_V1/memories?limit=5" "" "列出记忆（分页）"

echo ""
echo "5. 语义搜索"
echo "----------------------------------------"
test_endpoint "POST" "$API_V1/memories/search" \
'{
    "query": "咖啡店见面",
    "limit": 5,
    "min_similarity": 0.3
}' \
"语义搜索"

echo ""
echo "6. 自然语言召回"
echo "----------------------------------------"
test_endpoint "POST" "$API_V1/memories/recall" \
'{
    "query": "最近见过的朋友",
    "limit": 5,
    "use_parser": true
}' \
"自然语言召回"

echo ""
echo "7. 按时间搜索"
echo "----------------------------------------"
test_endpoint "GET" "$API_V1/memories/search/time?start=2024-01-01T00:00:00Z&end=2026-12-31T23:59:59Z&limit=5" "" "按时间搜索"

echo ""
echo "========================================"
echo "测试完成"
echo "========================================"
