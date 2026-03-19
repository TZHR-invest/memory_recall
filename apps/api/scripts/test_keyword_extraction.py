"""
关键词提取对比测试
对比 jieba 分词和 LLM 提取的效果
"""
import asyncio
import time
import requests
import jieba
import jieba.analyse

# 测试用例
TEST_CASES = [
    "上周在咖啡店和老同学见面",
    "最近在办公室开的重要会议",
    "昨天和女朋友去公园散步，心情很好",
    "今天完成了项目报告，老板很满意",
    "周末在家看了部电影，挺感人的",
]

# 停用词
STOP_WORDS = set([
    "的", "了", "在", "是", "我", "有", "和", "就",
    "不", "人", "都", "一", "一个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "什么", "怎么"
])

API_URL = "http://192.168.0.206:8000"

def extract_jieba_tfidf(text: str, top_k: int = 5) -> list:
    """使用 jieba TF-IDF 提取关键词"""
    return jieba.analyse.extract_tags(text, topK=top_k, withWeight=False)

def extract_jieba_cut(text: str) -> list:
    """使用 jieba 分词 + 过滤"""
    words = jieba.cut(text)
    keywords = [
        w for w in words
        if len(w) >= 2
        and w not in STOP_WORDS
        and not w.isdigit()
    ]
    return list(set(keywords))

def extract_llm_via_api(text: str) -> dict:
    """通过 API 使用 LLM 提取关键词"""
    start = time.time()
    response = requests.post(
        f"{API_URL}/api/v1/memories/recall",
        json={"query": text, "limit": 1},
        timeout=30
    )
    elapsed = (time.time() - start) * 1000
    
    if response.status_code == 200:
        data = response.json()
        parsed = data.get("data", {}).get("parsed_query", {})
        return {
            "keywords": parsed.get("keywords", []),
            "time": elapsed
        }
    return {"keywords": [], "time": elapsed}

def main():
    """主函数"""
    print("=" * 70)
    print("关键词提取对比测试")
    print("=" * 70)
    
    results = []
    
    for query in TEST_CASES:
        # Jieba TF-IDF
        start = time.time()
        jieba_tfidf = extract_jieba_tfidf(query)
        jieba_tfidf_time = (time.time() - start) * 1000
        
        # Jieba 分词
        start = time.time()
        jieba_cut = extract_jieba_cut(query)
        jieba_cut_time = (time.time() - start) * 1000
        
        # LLM 提取（通过 API）
        llm_result = extract_llm_via_api(query)
        llm_keywords = llm_result["keywords"]
        llm_time = llm_result["time"]
        
        results.append({
            "query": query,
            "jieba_tfidf": jieba_tfidf,
            "jieba_cut": jieba_cut,
            "llm": llm_keywords,
            "jieba_tfidf_time": jieba_tfidf_time,
            "jieba_cut_time": jieba_cut_time,
            "llm_time": llm_time,
        })
    
    # 输出对比表格
    print("\n### 关键词提取结果对比：\n")
    print("| 查询 | Jieba TF-IDF | Jieba 分词 | LLM 提取 |")
    print("|------|-------------|-----------|----------|")
    
    for r in results:
        query = r['query'][:15] + "..." if len(r['query']) > 15 else r['query']
        jieba_tfidf = ", ".join(r['jieba_tfidf'][:3]) if r['jieba_tfidf'] else "-"
        jieba_cut = ", ".join(r['jieba_cut'][:3]) if r['jieba_cut'] else "-"
        llm = ", ".join(r['llm'][:3]) if r['llm'] else "-"
        print(f"| {query} | {jieba_tfidf} | {jieba_cut} | {llm} |")
    
    # 输出时间对比
    print("\n### 处理时间对比（毫秒）：\n")
    print("| 查询 | Jieba TF-IDF | Jieba 分词 | LLM 提取 |")
    print("|------|-------------|-----------|----------|")
    
    for r in results:
        query = r['query'][:15] + "..." if len(r['query']) > 15 else r['query']
        print(f"| {query} | {r['jieba_tfidf_time']:.1f}ms | {r['jieba_cut_time']:.1f}ms | {r['llm_time']:.1f}ms |")
    
    # 平均时间
    avg_jieba_tfidf = sum(r['jieba_tfidf_time'] for r in results) / len(results)
    avg_jieba_cut = sum(r['jieba_cut_time'] for r in results) / len(results)
    avg_llm = sum(r['llm_time'] for r in results) / len(results)
    
    print(f"| **平均** | **{avg_jieba_tfidf:.1f}ms** | **{avg_jieba_cut:.1f}ms** | **{avg_llm:.1f}ms** |")
    
    # 分析
    print("\n### 分析结论：\n")
    print(f"- **速度**：Jieba 分词 ({avg_jieba_cut:.1f}ms) > Jieba TF-IDF ({avg_jieba_tfidf:.1f}ms) >>> LLM ({avg_llm:.0f}ms)")
    print(f"- **速度差异**：LLM 比 Jieba 慢 {avg_llm/avg_jieba_cut:.0f} 倍")
    print(f"- **成本**：Jieba 免费，LLM 需消耗 Token")
    print()
    print("**推荐**：")
    print("- 对速度要求高：使用 Jieba")
    print("- 对准确性要求高：使用 LLM")
    print("- 最佳方案：Jieba 快速分词 + LLM 智能提取（降级）")

if __name__ == "__main__":
    main()