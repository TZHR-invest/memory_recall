"""
文件上传路由
支持长文本文件上传、智能分段、摘要生成、图谱构建
支持文件哈希去重，避免重复上传相同文件
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import os
import tempfile
from ..services.memory_service import memory_service as get_memory_service

router = APIRouter(prefix="/files", tags=["文件"])


@router.post(
    "/upload",
    response_model=dict,
    summary="上传长文本文件",
    description="支持 txt、md、log 格式，自动智能分段（最大 10MB），支持文件去重"
)
async def upload_file(
    file: UploadFile = File(..., description="文件"),
    user_id: str = Form(..., description="用户 ID"),
    auto_segment: bool = Form(True, description="自动分段"),
    segment_strategy: str = Form("auto", description="分段策略：auto/time/topic/size"),
    max_segment_size: int = Form(800, description="最大分段大小（字符）"),
    enable_dedup: bool = Form(True, description="是否启用文件去重检查")
):
    """
    上传长文本文件
    
    - **file**: 文件（txt/md/log，最大 10MB）
    - **user_id**: 用户 ID（必填）
    - **auto_segment**: 是否自动分段
    - **segment_strategy**: 分段策略
      - auto: 自动检测
      - time: 按时间分段
      - topic: 按话题分段
      - size: 按大小分段
    - **max_segment_size**: 最大分段大小
    - **enable_dedup**: 是否启用文件去重检查（默认 True）
    - **generate_summary**: 是否生成摘要
    """
    try:
        # 1. 检查文件类型
        allowed_types = ["txt", "md", "log", "text", ""]
        file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
        
        if file_ext and file_ext not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型：{file_ext}。支持：txt, md, log"
            )
        
        # 2. 读取文件内容
        content = await file.read()
        
        # ⚠️ 3. 检查文件大小（最大 10MB）
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE / 1024 / 1024}MB）"
            )
        
        # 4. 文件信息
        file_info = {
            "filename": file.filename,
            "file_type": file_ext or "txt",
            "file_size": len(content)
        }
        
        # 5. 调用带文件去重的上传方法
        result = await get_memory_service.create_memory_from_file(
            file_content=content,
            file_name=file.filename,
            user_id=user_id,
            enable_graph=True,
            enable_dedup=enable_dedup
        )
        
        # 6. 处理返回结果
        if result.get("status") == "duplicate":
            # 文件已存在
            return {
                "code": 200,
                "message": result.get("message", "文件已存在"),
                "data": {
                    "status": "duplicate",
                    "file_hash": result.get("file_hash"),
                    "existing_file": result.get("existing_file"),
                    "file_info": file_info,
                    "elapsed": result.get("elapsed")
                }
            }
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "文件处理失败")
            )
        
        # 7. 成功响应
        memory_id = result.get("memory_id")
        memory_ids = result.get("memory_ids", [])
        graph = result.get("graph", {})
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "status": "success",
                "memory_id": memory_id,
                "memory_ids": memory_ids,
                "memory_count": len(memory_ids),
                "file_info": {
                    **file_info,
                    "file_hash": result.get("file_hash"),
                    "file_id": result.get("file_id")
                },
                "graph": {
                    "entities": graph.get("entity_count", 0),
                    "relations": graph.get("relation_count", 0)
                } if graph else None,
                "elapsed": result.get("elapsed")
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)}")