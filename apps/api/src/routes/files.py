from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from ..services.unified_memory_service import unified_memory_service
from ..database import db

router = APIRouter(prefix="/files", tags=["文件"])

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_TYPES = ["txt", "md", "log", "text", ""]


@router.post(
    "/upload",
    response_model=dict,
    summary="上传长文本文件（统一 DAG 架构）",
    description="支持 txt、md、log 格式，自动分段存储到 raw_messages，支持文件去重",
)
async def upload_file(
    file: UploadFile = File(..., description="文件"),
    user_id: str = Form(..., description="用户 ID"),
    max_chunk_size: int = Form(5000, description="最大分段大小（字符）"),
    enable_dedup: bool = Form(True, description="是否启用文件去重检查"),
):
    file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""

    if file_ext and file_ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400, detail=f"不支持的文件类型：{file_ext}。支持：txt, md, log"
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE / 1024 / 1024}MB）",
        )

    db.set_current_user(user_id)

    try:
        result = await unified_memory_service.store_file(
            user_id=user_id,
            content=content,
            file_name=file.filename,
            metadata={
                "tags": [],
            },
        )

        if result["status"] == "duplicate":
            return {
                "code": 200,
                "message": "文件已存在",
                "data": {
                    "status": "duplicate",
                    "document_id": result["document_id"],
                    "file_name": file.filename,
                    "file_size": result["file_size"],
                },
            }

        return {
            "code": 200,
            "message": "success",
            "data": {
                "status": "success",
                "document_id": result["document_id"],
                "chunk_count": result["chunk_count"],
                "file_name": result["file_name"],
                "file_size": result["file_size"],
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)}")


@router.get(
    "/{document_id}",
    response_model=dict,
    summary="获取文档分段",
)
async def get_document(
    document_id: str,
    user_id: str,
):
    db.set_current_user(user_id)

    chunks = await unified_memory_service.get_document_chunks(document_id, user_id)

    if not chunks:
        raise HTTPException(status_code=404, detail="文档不存在")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "document_id": document_id,
            "chunks": chunks,
            "total_chunks": len(chunks),
        },
    }
