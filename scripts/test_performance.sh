#!/bin/bash
# Phase 4 性能测试脚本
# 使用 curl 测试 API 端点

API_URL="http://192.168.0.206:8000"

echo "========================================="
echo "Phase 4 性能测试"
echo "========================================="
echo ""

# 测试用例
test_cases=(
    "今天和张三在咖啡店聊天"
    "今天和张三在咖啡店聊天，讨论了机器学习项目，决定下周开始实施"
    "今天和张三在咖啡店聊天，讨论了机器学习项目的进展，决定下周开始实施新的算法优化方案，预计可以提升模型准确率10%以上"
)

# 结果数组
declare -a elapsed_times

# 运行测试
for i in "${!test_cases[@]}"; do
    content="${test_cases[$i]}"
    echo "测试用例 $((i+1)): 长度 ${#content} 字符"
    
    start=$(date +%s.%N)
    
    response=$(curl -s -X POST "${API_URL}/api/v1/memories/with-graph" \
        -H "Content-Type: application/json" \
        -d "{
            \"content\": \"${content}\",
            \"user_id\": \"test_user\",
            \"enable_graph\": true
        }")
    
    end=$(date +%s.%N)
    elapsed=$(echo "$end - $start" | bc)
    elapsed_times+=($elapsed)
    
    # 检查响应
    if echo "$response" | grep -q '"success":true'; then
        memory_id=$(echo "$response" | grep -o '"memory_id":"[^"]*"' | cut -d'"' -f4)
        entity_count=$(echo "$response" | grep -o '"entity_count":[0-9]*' | cut -d':' -f2)
        relation_count=$(echo "$response" | grep -o '"relation_count":[0-9]*' | cut -d':' -f2)
        
        echo "  ✓ 耗时: ${elapsed}s"
        echo "  ✓ 记忆 ID: ${memory_id}"
        echo "  ✓ 实体数: ${entity_count}, 关系数: ${relation_count}"
    else
        echo "  ✗ 失败: $(echo "$response" | head -c 100)"
    fi
    
    echo ""
done

# 统计
echo "========================================="
echo "测试结果统计"
echo "========================================="

# 计算平均值和最大值
total=0
max=0
min=999

for time in "${elapsed_times[@]}"; do
    total=$(echo "$total + $time" | bc)
    
    if (( $(echo "$time > $max" | bc -l) )); then
        max=$time
    fi
    
    if (( $(echo "$time < $min" | bc -l) )); then
        min=$time
    fi
done

avg=$(echo "scale=2; $total / ${#elapsed_times[@]}" | bc)

echo "平均耗时: ${avg}s"
echo "最大耗时: ${max}s"
echo "最小耗时: ${min}s"
echo ""

# 验收标准
echo "验收标准检查:"
if (( $(echo "$max < 2.0" | bc -l) )); then
    echo "  [✓] 最大耗时 < 2s (实际: ${max}s)"
else
    echo "  [✗] 最大耗时 < 2s (实际: ${max}s)"
fi

if (( $(echo "$avg < 1.5" | bc -l) )); then
    echo "  [✓] 平均耗时 < 1.5s (实际: ${avg}s)"
else
    echo "  [✗] 平均耗时 < 1.5s (实际: ${avg}s)"
fi

echo ""
echo "========================================="

# 检查是否通过
if (( $(echo "$max < 2.0" | bc -l) )) && (( $(echo "$avg < 1.5" | bc -l) )); then
    echo "✓ 性能测试通过"
    exit 0
else
    echo "✗ 性能测试失败"
    exit 1
fi
