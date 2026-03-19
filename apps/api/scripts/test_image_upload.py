#!/usr/bin/env python3
"""
图片上传功能测试脚本
测试 EXIF 提取、多模态 Embedding、图片内容理解
"""
import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime
from PIL import Image as PILImage
from PIL import ImageDraw
from PIL.ExifTags import TAGS
import tempfile

# API 基础 URL
API_BASE = "http://localhost:8000/api/v1"


def create_test_image():
    """创建测试图片（带 EXIF 信息）"""
    print("\n📸 创建测试图片...")
    
    # 创建一个简单的图片
    img = PILImage.new('RGB', (800, 600), color=(73, 109, 137))
    
    # 添加一些文字
    draw = ImageDraw.Draw(img)
    draw.text((100, 250), "Test Image for Memory Recall", fill=(255, 255, 255))
    draw.text((100, 300), f"Created at {datetime.now().isoformat()}", fill=(255, 255, 255))
    
    # 添加 EXIF 信息
    exif = img.getexif()
    exif[0x0132] = datetime.now().strftime("%Y:%m:%d %H:%M:%S")  # DateTime
    exif[0x010F] = "Test Camera"  # Make
    exif[0x0110] = "Test Model"  # Model
    
    # 保存图片
    temp_path = tempfile.mktemp(suffix=".jpg")
    img.save(temp_path, format="JPEG", exif=exif)
    
    print(f"✅ 测试图片创建成功: {temp_path}")
    print(f"   大小: {os.path.getsize(temp_path)} 字节")
    
    return temp_path


def test_health_check():
    """测试健康检查"""
    print("\n🔍 测试健康检查...")
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ API 服务正常运行")
            return True
        else:
            print(f"❌ API 服务异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到 API 服务: {e}")
        return False


def test_image_upload(image_path):
    """测试图片上传"""
    print("\n📤 测试图片上传...")
    
    url = f"{API_BASE}/memories/upload"
    
    # 准备上传数据
    files = {
        "file": ("test_image.jpg", open(image_path, "rb"), "image/jpeg")
    }
    data = {
        "content": "测试图片记忆",
        "extract_exif": "true",
        "generate_embedding": "true",
        "understand_content": "true"
    }
    
    try:
        print(f"   上传图片: {image_path}")
        response = requests.post(url, files=files, data=data, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 图片上传成功")
            print(f"\n📊 返回结果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # 检查关键字段
            if result.get("code") == 200:
                data = result.get("data", {})
                
                # 检查 ID
                memory_id = data.get("id")
                if memory_id:
                    print(f"\n✅ 记忆 ID: {memory_id}")
                
                # 检查 input_type
                if data.get("input_type") == "image":
                    print("✅ 输入类型正确: image")
                
                # 检查 EXIF
                exif = data.get("exif")
                if exif:
                    print(f"✅ EXIF 信息提取成功")
                    if exif.get("datetime"):
                        print(f"   - 拍摄时间: {exif['datetime']}")
                    if exif.get("camera"):
                        print(f"   - 相机: {exif['camera']}")
                else:
                    print("⚠️  未提取到 EXIF 信息")
                
                # 检查 Embedding
                embedding = data.get("embedding")
                if embedding:
                    print(f"✅ Embedding 生成成功，维度: {len(embedding)}")
                else:
                    print("⚠️  Embedding 生成失败")
                
                # 检查内容理解
                understanding = data.get("understanding")
                if understanding:
                    print("✅ 图片内容理解成功")
                    if understanding.get("scene"):
                        print(f"   - 场景: {understanding['scene']}")
                    if understanding.get("objects"):
                        print(f"   - 物体: {', '.join(understanding['objects'][:5])}")
                    if understanding.get("emotion"):
                        print(f"   - 情绪: {understanding['emotion']}")
                else:
                    print("⚠️  图片内容理解失败")
                
                return memory_id
            else:
                print(f"❌ 返回码错误: {result.get('code')}")
                return None
        else:
            print(f"❌ 上传失败: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"❌ 上传失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_get_image_memory(memory_id):
    """测试获取图片记忆"""
    print(f"\n📖 测试获取图片记忆: {memory_id}...")
    
    url = f"{API_BASE}/memories/image/{memory_id}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 获取成功")
            
            data = result.get("data", {})
            print(f"\n📊 记忆详情:")
            print(f"   ID: {data.get('id')}")
            print(f"   内容: {data.get('content')}")
            print(f"   输入类型: {data.get('input_type')}")
            print(f"   创建时间: {data.get('created_at')}")
            
            if data.get("image_path"):
                print(f"   图片路径: {data.get('image_path')}")
            
            return True
        else:
            print(f"❌ 获取失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 获取失败: {e}")
        return False


def test_search_with_image_embedding():
    """测试使用图片 Embedding 进行搜索"""
    print("\n🔍 测试图片 Embedding 搜索...")
    
    url = f"{API_BASE}/memories/search"
    
    data = {
        "query": "测试图片记忆",
        "limit": 5,
        "min_similarity": 0.3
    }
    
    try:
        response = requests.post(url, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 搜索成功")
            
            results = result.get("data", {}).get("results", [])
            print(f"   找到 {len(results)} 条相关记忆")
            
            for i, item in enumerate(results[:3]):
                print(f"   [{i+1}] {item.get('content', '')[:50]}... (相似度: {item.get('similarity', 0):.3f})")
            
            return True
        else:
            print(f"❌ 搜索失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        return False


def test_exif_extraction(image_path):
    """测试 EXIF 提取（独立测试）"""
    print("\n🔍 测试 EXIF 提取...")
    
    try:
        img = PILImage.open(image_path)
        exif_data = img._getexif()
        
        if exif_data:
            print("✅ EXIF 数据存在")
            
            for tag, value in exif_data.items():
                decoded = TAGS.get(tag, tag)
                print(f"   - {decoded}: {value}")
        else:
            print("⚠️  无 EXIF 数据")
        
        return True
        
    except Exception as e:
        print(f"❌ EXIF 提取失败: {e}")
        return False


def main():
    """主测试流程"""
    print("=" * 60)
    print("Memory Recall - 图片上传功能测试")
    print("=" * 60)
    
    # 1. 测试健康检查
    if not test_health_check():
        print("\n❌ API 服务未启动，请先运行: uvicorn main:app --reload")
        return
    
    # 2. 创建测试图片
    image_path = create_test_image()
    if not image_path or not os.path.exists(image_path):
        print("\n❌ 无法创建测试图片")
        return
    
    # 3. 测试 EXIF 提取
    test_exif_extraction(image_path)
    
    # 4. 测试图片上传
    memory_id = test_image_upload(image_path)
    
    if memory_id:
        # 5. 测试获取图片记忆
        test_get_image_memory(memory_id)
        
        # 6. 测试搜索
        test_search_with_image_embedding()
    
    # 清理临时文件
    try:
        os.unlink(image_path)
        print(f"\n🧹 清理临时文件: {image_path}")
    except:
        pass
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
