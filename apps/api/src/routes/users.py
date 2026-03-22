"""
用户管理 API 路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from pydantic import BaseModel, Field, field_validator

from ..database import db

router = APIRouter(prefix="/users", tags=["用户管理"])


# ==================== 请求模型 ====================

class UserInitRequest(BaseModel):
    """用户初始化请求"""
    user_id: str = Field(..., description="用户 ID（只能包含小写字母、数字和下划线）")
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v):
        """验证用户 ID 格式"""
        import re
        if not re.match(r'^[a-z0-9_]+$', v):
            raise ValueError('用户 ID 只能包含小写字母、数字和下划线')
        if len(v) < 1 or len(v) > 100:
            raise ValueError('用户 ID 长度必须在 1-100 个字符之间')
        return v


# ==================== API 端点 ====================

@router.post(
    "/init",
    response_model=dict,
    summary="初始化用户",
    description="初始化用户（创建用户 schema）",
    responses={
        200: {
            "description": "初始化成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "用户初始化成功",
                        "data": {
                            "user_id": "develop",
                            "schema_name": "user_develop",
                            "already_exists": False
                        }
                    }
                }
            }
        },
        400: {"description": "用户 ID 格式无效"},
        500: {"description": "服务器内部错误"}
    }
)
async def init_user(request: UserInitRequest):
    """
    初始化用户（创建用户 schema）
    
    - **user_id**: 用户 ID（只能包含小写字母、数字和下划线）
    
    如果用户已存在，返回已存在信息
    """
    try:
        result = await db.init_user(request.user_id)
        
        message = "用户已存在" if result["already_exists"] else "用户初始化成功"
        
        return {
            "code": 200,
            "message": message,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{user_id}",
    response_model=dict,
    summary="获取用户信息",
    description="获取用户信息（schema 名称、创建时间、最后活跃时间）",
    responses={
        200: {
            "description": "成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "user_id": "develop",
                            "schema_name": "user_develop",
                            "created_at": "2026-03-20T12:00:00",
                            "last_active_at": "2026-03-20T15:30:00"
                        }
                    }
                }
            }
        },
        404: {"description": "用户不存在"}
    }
)
async def get_user(user_id: str):
    """
    获取用户信息
    
    - **user_id**: 用户 ID
    """
    try:
        user = await db.fetchrow(
            "SELECT id, schema_name, created_at, last_active_at FROM users WHERE id = $1",
            user_id
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "user_id": user["id"],
                "schema_name": user["schema_name"],
                "created_at": user["created_at"].isoformat() if user["created_at"] else None,
                "last_active_at": user["last_active_at"].isoformat() if user["last_active_at"] else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=dict,
    summary="列出所有用户",
    description="列出所有已注册的用户",
    responses={
        200: {
            "description": "成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "users": [
                                {
                                    "user_id": "develop",
                                    "schema_name": "user_develop",
                                    "created_at": "2026-03-20T12:00:00",
                                    "last_active_at": "2026-03-20T15:30:00"
                                }
                            ],
                            "count": 1
                        }
                    }
                }
            }
        }
    }
)
async def list_users(
    limit: int = Query(50, ge=1, le=100, description="数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """
    列出所有用户
    
    - **limit**: 每页数量，1-100，默认 50
    - **offset**: 偏移量，默认 0
    """
    try:
        users = await db.fetch(
            """
            SELECT id, schema_name, created_at, last_active_at 
            FROM users 
            ORDER BY created_at DESC 
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset
        )
        
        total = await db.fetchval("SELECT COUNT(*) FROM users")
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "users": [
                    {
                        "user_id": user["id"],
                        "schema_name": user["schema_name"],
                        "created_at": user["created_at"].isoformat() if user["created_at"] else None,
                        "last_active_at": user["last_active_at"].isoformat() if user["last_active_at"] else None
                    }
                    for user in users
                ],
                "count": len(users),
                "total": total,
                "has_more": offset + limit < total
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/{user_id}",
    response_model=dict,
    summary="删除用户",
    description="删除用户及其所有数据（危险操作）",
    responses={
        200: {"description": "删除成功"},
        404: {"description": "用户不存在"}
    }
)
async def delete_user(user_id: str):
    """
    删除用户（危险操作）
    
    - **user_id**: 用户 ID
    
    注意：此操作会删除用户的所有数据，不可恢复
    """
    try:
        # 检查用户是否存在
        user = await db.fetchrow(
            "SELECT id FROM users WHERE id = $1",
            user_id
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 删除用户 schema（会级联删除所有数据）
        await db.execute(f"SELECT delete_user_schema('{user_id}')")
        
        return {
            "code": 200,
            "message": "用户删除成功",
            "data": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
