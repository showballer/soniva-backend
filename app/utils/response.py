"""
Unified Response Utilities
"""
from typing import Any, Optional
from datetime import datetime
from fastapi.responses import JSONResponse


def success_response(data: Any = None, message: str = "success") -> dict:
    """
    Return a success response
    """
    return {
        "code": 200,
        "message": message,
        "data": data,
        "timestamp": int(datetime.now().timestamp())
    }


def error_response(code: int, message: str, error: Optional[str] = None) -> JSONResponse:
    """
    Return an error response
    """
    content = {
        "code": code,
        "message": message,
        "timestamp": int(datetime.now().timestamp())
    }
    if error:
        content["error"] = error
    return JSONResponse(status_code=code, content=content)


def paginated_response(
    items: list,
    total: int,
    page: int,
    page_size: int
) -> dict:
    """
    Return a paginated response
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        },
        "timestamp": int(datetime.now().timestamp())
    }
