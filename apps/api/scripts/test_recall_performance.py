"""
智能召回性能分析
测量每个环节的时间
"""
import time
import requests

API_URL = "http://192.168.0.206:8000"
TEST_QUERY = "上周在咖啡店和老同学见面"

def test_recall_performance():
    """测试智能召回性能"""
    print("=" * 70)
    print("智能召回性能分析")
    print("=" * 70)
    print(f"\n测试查询: {TEST_QUERY}\n")
    
    # 1. 测试完整的智能召回（LLM 解析 + Embedding + 搜索）
    print("### 1. 完整智能召回（LLM 解析 + Embedding + 搜索）")
    start = time.time()
    response = requests.post(
        f"{API_URL}/api/v1/memories/recall",
        json={"query": TEST_QUERY, "limit": 5},
        timeout=60
    )
    total_time = (time.time() - start) * 1000
    print(f"时间: {total_time:.1f}ms ({total_time/1000:.1f}秒)")
    
    if response.status_code == 200:
        data = response.json()
        parsed = data.get("data", {}).get("parsed_query", {})
        print(f"解析来源: {parsed.get('source', 'unknown')}")
        print(f"关键词: {parsed.get('keywords', [])}")
    
    # 2. 测试单独的语义搜索（只有 Embedding + 搜索）
    print("\n### 2. 单独语义搜索（只有 Embedding + 搜索）")
    start = time.time()
    response = requests.post(
        f"{API_URL}/api/v1/memories/search",
        json={"query": TEST_QUERY, "limit": 5},
        timeout=60
    )
    search_time = (time.time() - start) * 1000
    print(f"时间: {search_time:.1f}ms ({search_time/1000:.1f}秒)")
    
    # 分析
    print("\n### 性能分解")
    print(f"- 完整召回: {total_time:.1f}ms")
    print(f"- 语义搜索: {search_time:.1f}ms")
    llm_time = total_time - search_time
    print(f"- LLM 解析: {llm_time:.1f}ms (完整 - 搜索)")
    
    print("\n### 时间占比")
    print(f"- LLM 解析: {llm_time/total_time*100:.1f}%")
    print(f"- 其他: {search_time/total_time*100:.1f}%")
    
    print("\n### 瓶颈分析")
    if llm_time > 10000:
        print(f"⚠️ **LLM 解析是主要瓶颈**")
        print(f"   - 占总时间的 {llm_time/total_time*100:.1f}%")
        print(f"   - 平均每次解析耗时 {llm_time/1000:.1f} 秒")
        print()
        print("### 优化建议")
        print("1. 使用缓存：相同查询缓存解析结果")
        print("2. 使用更快的模型：如 deepseek-v3")
        print("3. 使用 Jieba 分词替代 LLM 解析")
    else:
        print("✅ 性能正常")

if __name__ == "__main__":
    test_recall_performance()
