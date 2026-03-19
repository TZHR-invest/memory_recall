"""
端到端测试 - 测试完整的记忆存储和召回流程
"""
import pytest
import httpx
import asyncio
import time
from typing import List, Dict

BASE_URL = "http://192.168.0.206:8000"


class TestFullFlow:
    """测试完整的记忆存储和召回流程"""
    
    @pytest.mark.asyncio
    async def test_create_memory_with_graph(self):
        """测试创建记忆（带图谱）"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/api/v1/memories/with-graph",
                json={
                    "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
                    "user_id": "test_user",
                    "enable_graph": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # 验证返回结果
            assert data["success"] == True
            assert data["memory_id"] is not None
            assert "graph" in data
            
            print(f"\n创建记忆成功：{data['memory_id']}")
            print(f"实体数：{data['graph']['entity_count']}")
            print(f"关系数：{data['graph']['relation_count']}")
            
            # 验证实体提取
            entities = data["graph"]["entities"]
            entity_names = [e["entity"] for e in entities]
            print(f"提取的实体：{entity_names}")
            
            # 至少应该提取到张三和咖啡店
            assert data["graph"]["entity_count"] >= 2
    
    @pytest.mark.asyncio
    async def test_recall_memory(self):
        """测试召回记忆（向量搜索）"""
        # 先创建一条记忆
        async with httpx.AsyncClient(timeout=30.0) as client:
            create_response = await client.post(
                f"{BASE_URL}/api/v1/memories/with-graph",
                json={
                    "content": "今天和李四在咖啡店讨论项目",
                    "user_id": "test_user_recall",
                    "enable_graph": True
                }
            )
            
            assert create_response.status_code == 200
            
            # 等待一下确保数据已存储
            await asyncio.sleep(1)
            
            # 搜索记忆
            search_response = await client.post(
                f"{BASE_URL}/api/v1/memories/search",
                json={
                    "query": "和朋友在咖啡店",
                    "user_id": "test_user_recall",
                    "limit": 5
                }
            )
            
            assert search_response.status_code == 200
            results = search_response.json()
            
            print(f"\n搜索结果数量：{len(results)}")
            
            # 验证召回结果
            if len(results) > 0:
                print(f"最相关的记忆：{results[0]['content'][:50]}...")
                assert any("咖啡店" in r["content"] for r in results)
            else:
                print("警告：未找到相关记忆")
    
    @pytest.mark.asyncio
    async def test_query_graph(self):
        """测试查询图谱（实体网络）"""
        # 先创建一条记忆
        async with httpx.AsyncClient(timeout=30.0) as client:
            create_response = await client.post(
                f"{BASE_URL}/api/v1/memories/with-graph",
                json={
                    "content": "今天和王五在公司开会",
                    "user_id": "test_user_graph",
                    "enable_graph": True
                }
            )
            
            assert create_response.status_code == 200
            data = create_response.json()
            
            # 查询图谱
            if data["graph"]["entity_count"] > 0:
                entity_name = data["graph"]["entities"][0]["entity"]
                
                graph_response = await client.get(
                    f"{BASE_URL}/api/v1/graph/entities",
                    params={
                        "user_id": "test_user_graph",
                        "entity_name": entity_name
                    }
                )
                
                assert graph_response.status_code == 200
                entity_network = graph_response.json()
                
                print(f"\n查询实体：{entity_name}")
                print(f"关系数量：{len(entity_network.get('relations', []))}")


class TestAccuracy:
    """测试实体提取和关系推理的准确率"""
    
    @pytest.mark.asyncio
    async def test_entity_extraction_accuracy(self):
        """测试实体提取准确率"""
        test_cases = [
            {
                "content": "今天和张三在咖啡店聊天",
                "expected_entities": ["张三", "咖啡店"]
            },
            {
                "content": "明天的会议改到下午3点，记得准备PPT",
                "expected_entities": ["会议", "PPT"]
            },
            {
                "content": "我和老王是多年的朋友",
                "expected_entities": ["老王"]
            },
            {
                "content": "今天在公司加班到很晚",
                "expected_entities": ["公司"]
            }
        ]
        
        correct_entities = 0
        total_entities = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for case in test_cases:
                response = await client.post(
                    f"{BASE_URL}/api/v1/memories/with-graph",
                    json={
                        "content": case["content"],
                        "user_id": "test_user_accuracy",
                        "enable_graph": True
                    }
                )
                
                if response.status_code != 200:
                    print(f"请求失败：{case['content']}")
                    continue
                
                data = response.json()
                entities = data["graph"]["entities"]
                
                # 检查实体
                entity_names = [e["entity"] for e in entities]
                print(f"\n内容：{case['content']}")
                print(f"期望实体：{case['expected_entities']}")
                print(f"实际实体：{entity_names}")
                
                for expected in case["expected_entities"]:
                    total_entities += 1
                    if any(expected in name for name in entity_names):
                        correct_entities += 1
        
        entity_accuracy = correct_entities / total_entities if total_entities > 0 else 0
        
        print(f"\n实体提取准确率: {entity_accuracy:.1%}")
        print(f"正确数：{correct_entities}/{total_entities}")
        
        # 验收标准
        assert entity_accuracy >= 0.90, f"实体提取准确率 {entity_accuracy:.1%} < 90%"
    
    @pytest.mark.asyncio
    async def test_relation_extraction_accuracy(self):
        """测试关系推理准确率"""
        test_cases = [
            {
                "content": "今天和张三在咖啡店见面",
                "expected_relations": ["met_at", "at"]
            },
            {
                "content": "我和老王是朋友",
                "expected_relations": ["friend", "is_friend"]
            },
            {
                "content": "在公司开会讨论项目",
                "expected_relations": []
            }
        ]
        
        correct_relations = 0
        total_relations = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for case in test_cases:
                response = await client.post(
                    f"{BASE_URL}/api/v1/memories/with-graph",
                    json={
                        "content": case["content"],
                        "user_id": "test_user_relation",
                        "enable_graph": True
                    }
                )
                
                if response.status_code != 200:
                    print(f"请求失败：{case['content']}")
                    continue
                
                data = response.json()
                relations = data["graph"]["relations"]
                
                # 检查关系
                relation_types = [r["relationship"] for r in relations]
                print(f"\n内容：{case['content']}")
                print(f"期望关系：{case['expected_relations']}")
                print(f"实际关系：{relation_types}")
                
                for expected in case["expected_relations"]:
                    total_relations += 1
                    if expected in relation_types:
                        correct_relations += 1
        
        relation_accuracy = correct_relations / total_relations if total_relations > 0 else 0
        
        print(f"\n关系推理准确率: {relation_accuracy:.1%}")
        print(f"正确数：{correct_relations}/{total_relations}")
        
        # 验收标准
        assert relation_accuracy >= 0.85, f"关系推理准确率 {relation_accuracy:.1%} < 85%"


class TestPerformance:
    """测试性能"""
    
    @pytest.mark.asyncio
    async def test_response_time(self):
        """测试响应时间"""
        response_times = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(5):
                start = time.time()
                
                response = await client.post(
                    f"{BASE_URL}/api/v1/memories/with-graph",
                    json={
                        "content": f"测试记忆 {i}：今天和某人做某事",
                        "user_id": "test_user_perf",
                        "enable_graph": True
                    }
                )
                
                elapsed = time.time() - start
                response_times.append(elapsed)
                
                assert response.status_code == 200
        
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        
        print(f"\n性能测试结果：")
        print(f"平均响应时间：{avg_time:.2f}s")
        print(f"最大响应时间：{max_time:.2f}s")
        print(f"最小响应时间：{min(response_times):.2f}s")
        
        # 验收标准
        assert avg_time < 2.0, f"平均响应时间 {avg_time:.2f}s >= 2s"
        assert max_time < 3.0, f"最大响应时间 {max_time:.2f}s >= 3s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
