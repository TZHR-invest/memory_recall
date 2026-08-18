"""
crystal 统一响应信封与错误规范（api-contract §3）

- 成功响应统一 `{code: 0, message: "ok", data: {...}}`
- 错误统一 `{code, message, detail?}`，code 即 HTTP 状态码（与 v5 兼容风格）
- 由 main.py 注册异常 handler 统一渲染，端点只抛异常/返回 data
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class CrystalAPIError(HTTPException):
    """crystal 统一业务错误（api-contract §3.1 错误码表）"""

    def __init__(
        self,
        status_code: int,
        message: str,
        detail: Optional[Any] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.message = message
        self.detail = detail


def ok_response(data: Any = None, message: str = "ok", code: int = 0) -> Dict[str, Any]:
    """统一成功信封"""
    return {"code": code, "message": message, "data": data}


def error_response(
    status_code: int, message: str, detail: Optional[Any] = None
) -> Dict[str, Any]:
    """统一错误体（code = HTTP 状态码）"""
    body: Dict[str, Any] = {"code": status_code, "message": message}
    if detail is not None:
        body["detail"] = detail
    return body


def crystal_error_handler(request: Request, exc: CrystalAPIError):
    """CrystalAPIError → 统一错误信封（注册到 main.py）"""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.status_code, exc.message, exc.detail),
    )


def http_error_handler(request: Request, exc: HTTPException):
    """兜底 HTTPException（非 crystal 抛的）→ 统一错误信封"""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.status_code, str(exc.detail)),
    )


def crystal_validation_error_handler(request: Request, exc):
    """RequestValidationError → 统一错误信封（422，body 结构校验失败）"""
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "loc": [str(loc) for loc in error.get("loc", [])],
                "msg": str(error.get("msg", "")),
                "type": error.get("type", ""),
            }
        )
    return JSONResponse(
        status_code=422,
        content=error_response(422, "请求参数验证失败", errors),
    )


def crystal_internal_error_handler(request: Request, exc: Exception):
    """未处理异常 → 统一错误信封（500，detail 受 APP_DEBUG 控制）"""
    from src.config import settings

    return JSONResponse(
        status_code=500,
        content=error_response(
            500,
            "服务器内部错误",
            str(exc) if settings.APP_DEBUG else "Internal server error",
        ),
    )
