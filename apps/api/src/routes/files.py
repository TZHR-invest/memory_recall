"""
文件上传路由
支持长文本文件上传、智能分段、摘要生成
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, List, Dict, Any
import os
import tempfile
from ..services.segment_service import get_segment_service
from ..services.summary_service import get_summary_service
from ..services.memory_service import memory_service as get_memory_service

router = APIRouter(prefix="/files", tags=["文件"])


@router.post(
    "/upload",
    response_model=dict,
    summary="上传长文本文件",
    description="支持 txt、md、log 格式，自动智能分段和摘要生成"
)
async def upload_file(
    file: UploadFile = File(..., description="文件"),
    auto_segment: bool = Form(True, description="自动分段"),
    segment_strategy: str = Form("auto", description="分段策略：auto/time/topic/size"),
    max_segment_size: int = Form(5000, description="最大分段大小（字符）"),
    generate_summary: bool = Form(True, description="生成摘要")
):
    """
    上传长文本文件
    
    - **file**: 文件（txt/md/log）
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
        
        # 4. 智能分段
        segment_service = get_segment_service()
        
        if auto_segment:
            segments = await segment_service.segment(
                text_content,
                strategy=segment_strategy,
                max_size=max_segment_size
            )
        else:
            # 不分段，整体作为一个分段
            segments = [{
                "content": text_content,
                "index": 0
            }]
        
        # 5. 生成摘要
        summary_service = get_summary_service()
        overall_summary = None
        key_events = []
        
        if generate_summary:
            # 为每个分段生成摘要
            for segment in segments:
                segment["summary"] = await summary_service.generate_segment_summary(
                    segment["content"][:2000]  # 限制长度
                )
            
            # 生成整体摘要
            overall_summary = await summary_service.generate_overall_summary(segments)
            
            # 提取关键事件
            key_events = await summary_service.extract_key_events(segments)
        
        # 6. 存储记忆
        memory_service = get_memory_service()
        memory_id = await memory_service.create_from_file(
            content=text_content,
            file_info=file_info,
            segments=segments,
            overall_summary=overall_summary,
            key_events=key_events
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "memory_id": memory_id,
                "file_info": file_info,
                "segment_count": len(segments),
                "overall_summary": overall_summary,
                "key_events": key_events,
                "segments": [
                    {
                        "index": s.get("index"),
                        "summary": s.get("summary"),
                        "time_range": s.get("time_range"),
                        "line_count": s.get("content", "").count("\n") + 1
                    }
                    for s in segments[:10]  # 只返回前10个分段的信息
                ]
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)}")