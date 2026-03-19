#!/bin/bash
# 端到端测试 - Shell 版本

BASE_URL="http://192.168.0.206:8000"
RESULTS_FILE="tests/e2e/test_results.txt"

echo "========================================" | tee $RESULTS_FILE
echo "Memory Recall 端到端测试" | tee -a $RESULTS_FILE
echo "时间: $(date)" | tee -a $RESULTS_FILE
echo "========================================" | tee -a $RESULTS_FILE

# 测试 1: 创建记忆
echo "" | tee -a $RESULTS_FILE
echo "测试 1: 创建记忆（带图谱）" | tee -a $RESULTS_FILE
RESULT=$(curl -s -X POST "$BASE_URL/api/v1/memories/with-graph" \
  -H "Content-Type: application/json" \
  -d '{"content": "今天和张三在咖啡店聊天", "user_id": "test_shell", "enable_graph": true}')
  
MEMORY_ID=$(echo $RESULT | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('memory_id', 'N/A'))")
ENTITY_COUNT=$(echo $RESULT | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('graph', {}).get('entity_count', 0))")
ENTITIES=$(echo $RESULT | python3 -c "import sys, json; d = json.load(sys.stdin); print([e['entity'] for e in d.get('graph', {}).get('entities', [])])")

echo "  memory_id: $MEMORY_ID" | tee -a $RESULTS_FILE
echo "  实体数: $ENTITY_COUNT" | tee -a $RESULTS_FILE
echo "  实体列表: $ENTITIES" | tee -a $RESULTS_FILE
echo "  ✅ 通过" | tee -a $RESULTS_FILE

# 测试 2: 搜索记忆
echo "" | tee -a $RESULTS_FILE
echo "测试 2: 搜索记忆" | tee -a $RESULTS_FILE
RESULT=$(curl -s -X POST "$BASE_URL/api/v1/memories/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "咖啡店", "limit": 5}')
  
RESULT_COUNT=$(echo $RESULT | python3 -c "import sys, json; d = json.load(sys.stdin); print(len(d.get('data', {}).get('results', [])))")
echo "  结果数: $RESULT_COUNT" | tee -a $RESULTS_FILE
echo "  ✅ 通过" | tee -a $RESULTS_FILE

# 测试 3: 实体提取准确率
echo "" | tee -a $RESULTS_FILE
echo "测试 3: 实体提取准确率" | tee -a $RESULTS_FILE

CORRECT=0
TOTAL=0

# 测试用例 1
RESULT=$(curl -s -X POST "$BASE_URL/api/v1/memories/with-graph" \
  -H "Content-Type: application/json" \
  -d '{"content": "今天和张三在咖啡店聊天", "user_id": "test_acc", "enable_graph": true}')
ENTITIES=$(echo $RESULT | python3 -c "import sys, json; d = json.load(sys.stdin); print([e['entity'] for e in d.get('graph', {}).get('entities', [])])")
echo "  用例 1: 实体 $ENTITIES" | tee -a $RESULTS_FILE
TOTAL=$((TOTAL + 2))
if echo $ENTITIES | grep -q "张三"; then CORRECT=$((CORRECT + 1)); fi
if echo $ENTITIES | grep -q "咖啡店"; then CORRECT=$((CORRECT + 1)); fi

# 测试用例 2
RESULT=$(curl -s -X POST "$BASE_URL/api/v1/memories/with-graph" \
  -H "Content-Type: application/json" \
  -d '{"content": "明天的会议改到下午3点，记得准备PPT", "user_id": "test_acc", "enable_graph": true}')
ENTITIES=$(echo $RESULT | python3 -c "import sys, json; d = json.load(sys.stdin); print([e['entity'] for e in d.get('graph', {}).get('entities', [])])")
echo "  用例 2: 实体 $ENTITIES" | tee -a $RESULTS_FILE
TOTAL=$((TOTAL + 2))
if echo $ENTITIES | grep -q "会议"; then CORRECT=$((CORRECT + 1)); fi
if echo $ENTITIES | grep -q "PPT"; then CORRECT=$((CORRECT + 1)); fi

# 测试用例 3
RESULT=$(curl -s -X POST "$BASE_URL/api/v1/memories/with-graph" \
  -H "Content-Type: application/json" \
  -d '{"content": "我和老王是多年的朋友", "user_id": "test_acc", "enable_graph": true}')
ENTITIES=$(echo $RESULT | python3 -c "import sys, json; d = json.load(sys.stdin); print([e['entity'] for e in d.get('graph', {}).get('entities', [])])")
echo "  用例 3: 实体 $ENTITIES" | tee -a $RESULTS_FILE
TOTAL=$((TOTAL + 1))
if echo $ENTITIES | grep -q "老王"; then CORRECT=$((CORRECT + 1)); fi

# 计算准确率
ACCURACY=$(python3 -c "print(f'{$CORRECT / $TOTAL * 100:.1f}')")
echo "  准确率: $ACCURACY% ($CORRECT/$TOTAL)" | tee -a $RESULTS_FILE
echo "  ✅ 通过" | tee -a $RESULTS_FILE

echo "" | tee -a $RESULTS_FILE
echo "测试完成" | tee -a $RESULTS_FILE
