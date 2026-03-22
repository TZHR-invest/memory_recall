"""
文件上传路由
支持长文本文件上传、智能分段、摘要生成、图谱构建
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
    description="支持 txt、md、log 格式，自动智能分段（最大 10MB）"
)
async def upload_file(
    file: UploadFile = File(..., description="文件"),
    user_id: str = Form(..., description="用户 ID"),
    auto_segment: bool = Form(True, description="自动分段"),
    segment_strategy: str = Form("auto", description="分段策略：auto/time/topic/size"),
    max_segment_size: int = Form(800, description="最大分段大小（字符）")
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
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = content.decode("gbk")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="无法解析文件编码，请使用 UTF-8 或 GBK 编码"
                )
        
        # 3. 文件信息
        file_info = {
            "filename": file.filename,
            "file_type": file_ext or "txt",
            "file_size": len(content),
            "line_count": text_content.count("\n") + 1
        }
        
        # 设置当前用户（确保存储到正确的 schema）
        from ..database import db
        db.set_current_user(user_id)
        
        # 4. 统一调用 create_memory_with_graph_v2（Function Calling 方式）
        result = await get_memory_service.create_memory_with_graph_v2(
            content=text_content,
            user_id=user_id,
            enable_graph=True
        )
        
        # 获取所有记忆 ID
        memory_ids = result.get("extracted", {}).get("memory_ids", [])
        memory_id = memory_ids[0] if memory_ids else None
        graph = result.get("graph", {})
        
        # 5. 更新所有记忆的文件元数据
        if memory_ids:
            # 更新所有记忆的文件信息
            await db.execute("""
                UPDATE memories 
                SET input_type = 'file',
                    file_name = $1,
                    file_size = $2
                WHERE id = ANY($3)
            """,
                file_info["filename"],
                file_info["file_size"],
                memory_ids
            )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "memory_id": memory_id,
                "file_info": file_info,
                "segment_count": graph.get("entity_count", 0) if graph else 0,
                "graph": {
                    "entities": graph.get("entity_count", 0),
                    "relations": graph.get("relation_count", 0)
                } if graph else None
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)}")