from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@dataclass(slots=True)
class AppError(Exception):
    status_code: int
    code: str
    message: str
    retryable: bool = False


def error_payload(code: str, message: str, retryable: bool = False) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    }


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message, exc.retryable),
    )


async def validation_error_handler(
    request: Request, _: RequestValidationError
) -> JSONResponse:
    is_draft = request.url.path.endswith("/draft")
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "INVALID_DRAFT" if is_draft else "INVALID_INPUT",
            "草稿不符合要求。" if is_draft else "请求参数不符合要求。",
        ),
    )


async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content=error_payload("NOT_FOUND", "请求的资源不存在。"),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload("HTTP_ERROR", "请求无法完成。"),
    )
