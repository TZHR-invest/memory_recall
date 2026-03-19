"""
图片上传 API 路由
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from typing import Optional, Dict, Any
from datetime import datetime
import tempfile
import os
import logging

from ..models.memory import Memory, MemoryCreate
from ..services.memory_service import memory_service
from ..image.processor import get_image_processor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memories", tags=["图片上传"])


@router.post(
    "/upload",
    response_model=dict,
    summary="上传图片",
    description="上传图片并创建记忆记录",
    responses={
        200: {
            "description": "上传成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "id": "mem_abc123",
                            "content": "在咖啡店的照片",
                            "input_type": "image",
                            "image_path": "/data/storage/images/xxx.jpg",
                            "exif": {
                                "datetime": "2024-01-15T10:30:00",
                                "gps": {
                                    "latitude": 39.9042,
                                    "longitude": 116.4074
                                }
                            },
                            "understanding": {
                                "scene": "咖啡店内部",
                                "objects": ["咖啡杯", "桌子", "椅子"],
                                "emotion": "温馨"
                            },
                            "created_at": "2024-01-15T10:35:00"
                        }
                    }
                }
            }
        },
        400: {"description": "文件格式不支持或文件过大"},
        500: {"description": "服务器内部错误"}
    }
)
async def upload_image(
    file: UploadFile = File(..., description="图片文件"),
    content: Optional[str] = Form(None, description="图片描述（可选）"),
    user_id: Optional[str] = Form(None, description="用户 ID（可选）"),
    extract_exif: bool = Form(True, description="是否提取 EXIF 信息"),
    generate_embedding: bool = Form(True, description="是否生成 Embedding"),
    understand_content: bool = Form(True, description="是否理解图片内容")
):
    """
    上传图片并创建记忆
    
    - **file**: 图片文件（支持 jpg, png, webp 格式，最大 10MB）
    - **content**: 图片描述（可选）
    - **user_id**: 用户 ID（可选）
    - **extract_exif**: 是否提取 EXIF 信息（默认 True）
    - **generate_embedding**: 是否生成 Embedding（默认 True）
    - **understand_content**: 是否理解图片内容（默认 True）
    """
    try:
        # 验证文件类型
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名为空")
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        supported_formats = [".jpg", ".jpeg", ".png", ".webp"]
        
        if file_ext not in supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式，支持: {', '.join(supported_formats)}"
            )
        
        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            # 读取上传的文件
            content_bytes = await file.read()
            
            # 检查文件大小
            max_size = 10 * 1024 * 1024  # 10MB
            if len(content_bytes) > max_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"文件大小超过限制（最大 {max_size / 1024 / 1024}MB）"
                )
            
            # 写入临时文件
            tmp_file.write(content_bytes)
            tmp_path = tmp_file.name
        
        logger.info(f"图片已保存到临时文件: {tmp_path}")
        
        # 处理图片
        image_processor = get_image_processor()
        result = image_processor.process_image(
            file_path=tmp_path,
            user_id=user_id,
            extract_exif=extract_exif,
            generate_embedding=generate_embedding,
            understand_content=understand_content
        )
        
        # 删除临时文件
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "图片处理失败"))
        
        # 构造记忆内容
        memory_content = content
        if not memory_content and result.get("understanding"):
            # 使用图片理解结果作为内容
            understanding = result["understanding"]
            memory_content = understanding.get("scene", "图片记忆")
            if understanding.get("objects"):
                memory_content += f"，包含：{', '.join(understanding['objects'][:5])}"
        
        # 从 EXIF 提取时间和地点
        time_info = None
        location_info = None
        
        if result.get("exif"):
            exif = result["exif"]
            
            # 提取时间
            if exif.get("datetime"):
                time_info = {
                    "value": exif["datetime"],
                    "source": "metadata"
                }
            
            # 提取地点
            if exif.get("gps"):
                location_info = {
                    "latitude": exif["gps"]["latitude"],
                    "longitude": exif["gps"]["longitude"],
                    "need_confirm": True  # 需要用户确认具体地点名称
                }
        
        # 创建记忆记录
        memory_data = MemoryCreate(
            content=memory_content,
            input_type="image",
            time=time_info,
            location=location_info,
            embedding=result.get("embedding"),
            attachments=[
                {
                    "type": "image",
                    "path": result["image_path"],
                    "metadata": {
                        "exif": result.get("exif"),
                        "understanding": result.get("understanding")
                    }
                }
            ]
        )
        
        # 保存到数据库
        memory_id = await memory_service.create(memory_data)
        
        # 获取创建的记忆
        created_memory = await memory_service.get(memory_id)
        
        logger.info(f"图片记忆创建成功: {memory_id}")
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                **created_memory.model_dump(),
                "exif": result.get("exif"),
                "understanding": result.get("understanding")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图片上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/upload/batch",
    response_model=dict,
    summary="批量上传图片",
    description="批量上传多张图片并创建记忆记录"
)
async def batch_upload_images(
    files: list[UploadFile] = File(..., description="图片文件列表"),
    user_id: Optional[str] = Form(None, description="用户 ID（可选）"),
    extract_exif: bool = Form(True, description="是否提取 EXIF 信息"),
    generate_embedding: bool = Form(True, description="是否生成 Embedding"),
    understand_content: bool = Form(True, description="是否理解图片内容")
):
    """
    批量上传图片
    
    - **files**: 图片文件列表（最多 10 张）
    - **user_id**: 用户 ID（可选）
    - **extract_exif**: 是否提取 EXIF 信息
    - **generate_embedding**: 是否生成 Embedding
    - **understand_content**: 是否理解图片内容
    """
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="最多上传 10 张图片")
    
    results = []
    success_count = 0
    error_count = 0
    
    for file in files:
        try:
            # 复用单张上传逻辑
            result = await upload_image(
                file=file,
                content=None,
                user_id=user_id,
                extract_exif=extract_exif,
                generate_embedding=generate_embedding,
                understand_content=understand_content
            )
            
            results.append({
                "filename": file.filename,
                "success": True,
                "memory_id": result["data"]["id"]
            })
            success_count += 1
            
        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
            error_count += 1
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": len(files),
            "success_count": success_count,
            "error_count": error_count,
            "results": results
        }
    }


@router.get(
    "/image/{memory_id}",
    response_model=dict,
    summary="获取图片记忆",
    description="获取图片记忆的详细信息"
)
async def get_image_memory(memory_id: str):
    """
    获取图片记忆
    
    - **memory_id**: 记忆 ID
    """
    memory = await memory_service.get(memory_id)
    
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    
    if memory.input_type != "image":
        raise HTTPException(status_code=400, detail="不是图片类型的记忆")
    
    # 提取图片相关信息
    image_path = None
    exif = None
    understanding = None
    
    if memory.attachments:
        for attachment in memory.attachments:
            if attachment.type == "image":
                image_path = attachment.path
                metadata = attachment.metadata or {}
                exif = metadata.get("exif")
                understanding = metadata.get("understanding")
                break
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            **memory.model_dump(),
            "image_path": image_path,
            "exif": exif,
            "understanding": understanding
        }
    }
