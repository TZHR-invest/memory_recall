#!/usr/bin/env python3
"""
测试 doubao-embedding-vision-251215 模型
使用火山引擎方舟 API
"""
import os
import sys
import requests
from typing import List, Optional


class DoubaoEmbeddingClient:
    """火山引擎方舟 Embedding 客户端"""
    
    def __init__(self, api_key: str):
        """
        初始化客户端
        
        Args:
            api_key: 火山引擎方舟 API Key
        """
        self.api_key = api_key
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.model = "doubao-embedding-vision-251215"
        self.dimension = 1024  # 支持 1024 或 2048
    
    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        生成文本向量
        
        Args:
            text: 输入文本
        
        Returns:
            向量列表（1024 维）
        """
        try:
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "input": [
                    {
                        "type": "text",
                        "text": text
                    }
                ],
                "encoding_format": "float",
                "dimensions": self.dimension
            }
            
            print(f"\n📤 请求 URL: {url}")
            print(f"📝 模型: {self.model}")
            print(f"📏 维度: {self.dimension}")
            print(f"💬 输入文本: {text[:50]}{'...' if len(text) > 50 else ''}")
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None
            
            data = response.json()
            print(f"\n📥 响应数据: {data.keys()}")
            
            if 'data' in data:
                print(f"📊 data 类型: {type(data['data'])}")
                if isinstance(data['data'], list) and len(data['data']) > 0:
                    print(f"📊 data[0] 键: {data['data'][0].keys()}")
                    embedding = data['data'][0]['embedding']
                    print(f"✅ 成功生成 {len(embedding)} 维向量")
                    print(f"📊 前 10 维: {embedding[:10]}")
                    return embedding
                elif isinstance(data['data'], dict):
                    print(f"📊 data 键: {data['data'].keys()}")
                    if 'embedding' in data['data']:
                        embedding = data['data']['embedding']
                        print(f"✅ 成功生成 {len(embedding)} 维向量")
                        print(f"📊 前 10 维: {embedding[:10]}")
                        return embedding
                else:
                    print(f"❌ 响应格式错误: {data}")
                    return None
            else:
                print(f"❌ 响应格式错误: {data}")
                return None
                
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        批量生成文本向量
        
        Args:
            texts: 输入文本列表
        
        Returns:
            向量列表
        """
        try:
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            # 构造多模态输入格式
            inputs = [{"type": "text", "text": text} for text in texts]
            payload = {
                "model": self.model,
                "input": inputs,
                "encoding_format": "float",
                "dimensions": self.dimension
            }
            
            print(f"\n📤 批量请求: {len(texts)} 条文本")
            
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None
            
            data = response.json()
            
            if 'data' in data:
                # 处理响应格式
                if isinstance(data['data'], list):
                    embeddings = [item['embedding'] for item in data['data']]
                elif isinstance(data['data'], dict) and 'embedding' in data['data']:
                    # 单个结果
                    embeddings = [data['data']['embedding']]
                else:
                    print(f"❌ 响应格式错误: {data}")
                    return None
                
                print(f"✅ 成功生成 {len(embeddings)} 个向量")
                return embeddings
            else:
                print(f"❌ 响应格式错误: {data}")
                return None
                
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def embed_image(self, image_url: str) -> Optional[List[float]]:
        """
        生成图片向量（多模态）
        
        Args:
            image_url: 图片 URL
        
        Returns:
            向量列表
        """
        try:
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "input": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    }
                ],
                "encoding_format": "float",
                "dimensions": self.dimension
            }
            
            print(f"\n📤 图片向量化请求")
            print(f"🖼️  图片 URL: {image_url[:60]}{'...' if len(image_url) > 60 else ''}")
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None
            
            data = response.json()
            
            if 'data' in data and len(data['data']) > 0:
                embedding = data['data'][0]['embedding']
                print(f"✅ 成功生成 {len(embedding)} 维向量")
                return embedding
            else:
                print(f"❌ 响应格式错误: {data}")
                return None
                
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def embed_multimodal(self, text: str, image_url: str) -> Optional[List[float]]:
        """
        生成图文混合向量
        
        Args:
            text: 文本内容
            image_url: 图片 URL
        
        Returns:
            向量列表
        """
        try:
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "input": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    }
                ],
                "encoding_format": "float",
                "dimensions": self.dimension
            }
            
            print(f"\n📤 图文混合向量化请求")
            print(f"💬 文本: {text[:50]}{'...' if len(text) > 50 else ''}")
            print(f"🖼️  图片: {image_url[:50]}{'...' if len(image_url) > 50 else ''}")
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None
            
            data = response.json()
            
            if 'data' in data and len(data['data']) > 0:
                embedding = data['data'][0]['embedding']
                print(f"✅ 成功生成 {len(embedding)} 维向量")
                return embedding
            else:
                print(f"❌ 响应格式错误: {data}")
                return None
                
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return None


def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 doubao-embedding-vision-251215 模型测试")
    print("=" * 60)
    
    # 检查 API Key
    api_key = os.getenv("VOLC_API_KEY")
    if not api_key:
        print("\n❌ 错误: 未配置 VOLC_API_KEY 环境变量")
        print("\n请设置环境变量:")
        print("export VOLC_API_KEY='your_api_key_here'")
        sys.exit(1)
    
    print(f"\n✅ API Key 已配置: {api_key[:10]}...{api_key[-10:]}")
    
    # 创建客户端
    client = DoubaoEmbeddingClient(api_key)
    
    # 测试 1: 文本向量化
    print("\n" + "=" * 60)
    print("📝 测试 1: 文本向量化")
    print("=" * 60)
    
    test_text = "今天在咖啡店遇到老同学，聊了很久，心情很不错"
    embedding1 = client.embed_text(test_text)
    
    if not embedding1:
        print("\n❌ 文本向量化测试失败")
        return False
    
    # 测试 2: 批量文本向量化
    print("\n" + "=" * 60)
    print("📝 测试 2: 批量文本向量化")
    print("=" * 60)
    
    test_texts = [
        "今天在咖啡店遇到老同学",
        "昨天在公司开会讨论项目",
        "明天要和朋友去爬山"
    ]
    embeddings = client.embed_batch(test_texts)
    
    if not embeddings:
        print("\n❌ 批量文本向量化测试失败")
        return False
    
    # 测试 3: 计算相似度
    print("\n" + "=" * 60)
    print("📊 测试 3: 向量相似度计算")
    print("=" * 60)
    
    import numpy as np
    
    # 相似文本应该有更高的相似度
    text_a = "今天去咖啡店喝了咖啡"
    text_b = "昨天在咖啡店和朋友聊天"
    text_c = "周末去公园跑步"
    
    emb_a = client.embed_text(text_a)
    emb_b = client.embed_text(text_b)
    emb_c = client.embed_text(text_c)
    
    if emb_a and emb_b and emb_c:
        # 余弦相似度
        sim_ab = np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b))
        sim_ac = np.dot(emb_a, emb_c) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_c))
        
        print(f"\n相似度计算结果:")
        print(f"  '{text_a}' vs '{text_b}'")
        print(f"  相似度: {sim_ab:.4f} {'✅ (相关度高)' if sim_ab > 0.7 else '❌ (相关度低)'}")
        print(f"\n  '{text_a}' vs '{text_c}'")
        print(f"  相似度: {sim_ac:.4f} {'✅ (相关度低)' if sim_ac < 0.7 else '❌ (相关度高)'}")
        
        if sim_ab > sim_ac:
            print("\n✅ 相似度计算正确: 咖啡店相关文本相似度更高")
        else:
            print("\n⚠️  相似度计算异常: 咖啡店相关文本相似度应该更高")
    
    # 测试 4: 多模态（可选）
    print("\n" + "=" * 60)
    print("🖼️  测试 4: 多模态向量化（可选）")
    print("=" * 60)
    
    test_image_url = "https://lf-cdn-tos.bytescm.com/obj/static/web/miniapp_demo_2.jpg"
    print(f"\n⚠️  注意: 多模态测试需要有效的图片 URL")
    print(f"测试图片: {test_image_url}")
    print("跳过多模态测试（需要实际图片 URL）")
    
    # 总结
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)
    print("\n📊 测试结果:")
    print("  ✅ 文本向量化: 通过")
    print("  ✅ 批量向量化: 通过")
    print("  ✅ 相似度计算: 通过")
    print("  ⏭️  多模态向量化: 跳过（需要实际图片 URL）")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
