"""HTTP 与 SSE 共用的稳定、安全错误协议。"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.runtime import bind_log_context, log_context, log_exception

from backend.db.errors import DuplicateKeyError, InvalidIdError, NotFoundError, VersionConflictError
from backend.llm.exceptions import (
    LLMAuthError,
    LLMDuplicateKeyError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
)


logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")

HTTP_ERROR_STATUS_SEMANTICS: dict[int, str] = {
    400: "仅保留明确登记的旧 ObjectId 兼容边界或无法执行的请求语义",
    404: "资源不存在、已删除或属于其他小说",
    409: "版本、候选依据、唯一性、顺序或幂等冲突",
    422: "字段、枚举、组合、数量或引用规则不合法",
    502: "Provider、结构化输出、格式审校或模型结果无效",
    503: "数据库、配置或依赖服务不可用",
    504: "明确的 LLM 工作流步骤超时",
}


class ApiErrorDetail(BaseModel):
    """公开错误的稳定 detail 结构。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    message: str = Field(min_length=1, max_length=2000)
    field_errors: dict[str, list[str]] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ApiErrorResponse(BaseModel):
    """FastAPI 错误响应的顶层结构。"""

    model_config = ConfigDict(extra="forbid")

    detail: ApiErrorDetail


class DomainApiError(Exception):
    """携带稳定错误码、HTTP 状态和安全上下文的领域异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        field_errors: Mapping[str, Sequence[str] | str] | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """初始化可安全暴露的领域错误。

        Args:
            code: 前后端稳定判断使用的大写错误码。
            message: 可直接向用户展示的安全消息。
            status_code: 对应的 HTTP 状态码。
            field_errors: 可选字段路径到错误消息的映射。
            details: 不含敏感信息的附加诊断上下文。

        Returns:
            无。
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field_errors = normalize_field_errors(field_errors)
        self.details = dict(details or {})


def sanitize_json_value(value: Any, *, redact_input: bool = False) -> Any:
    """递归转换为安全 JSON 值，并可隐藏请求原始输入。

    Args:
        value: 待清洗的校验错误或公开上下文。
        redact_input: 是否将 ``input`` 字段替换为固定占位符。

    Returns:
        不含非法 Unicode、对象实例和可选原始输入的 JSON 安全结构。
    """
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace").decode("utf-8")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(sanitize_json_value(str(raw_key)))
            result[key] = (
                "<invalid input>"
                if redact_input and key == "input"
                else sanitize_json_value(child, redact_input=redact_input)
            )
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_json_value(item, redact_input=redact_input) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_json_value(str(value), redact_input=redact_input)


def normalize_field_errors(
    field_errors: Mapping[str, Sequence[str] | str] | None,
) -> dict[str, list[str]]:
    """把字段错误统一为点号路径到消息数组的映射。

    Args:
        field_errors: 领域层字段错误映射。

    Returns:
        已清洗、去空且消息列表去重的字段错误。
    """
    normalized: dict[str, list[str]] = {}
    for raw_field, raw_messages in (field_errors or {}).items():
        field = str(sanitize_json_value(str(raw_field))).strip()
        if not field:
            continue
        messages = [raw_messages] if isinstance(raw_messages, str) else raw_messages
        cleaned: list[str] = []
        for raw_message in messages:
            message = str(sanitize_json_value(str(raw_message))).strip()
            if message and message not in cleaned:
                cleaned.append(message)
        if cleaned:
            normalized[field] = cleaned
    return normalized


def validation_field_errors(exc: RequestValidationError) -> dict[str, list[str]]:
    """把 FastAPI/Pydantic 校验错误转换为公共字段错误格式。

    Args:
        exc: FastAPI 汇总的请求校验异常。

    Returns:
        去除 body/query/path 前缀后的点号字段路径映射。
    """
    result: dict[str, list[str]] = {}
    for error in exc.errors():
        raw_location = error.get("loc", ())
        location = [
            str(part)
            for part in raw_location
            if part not in {"body", "query", "path", "header", "cookie"}
        ]
        field = ".".join(location) or "$"
        message = str(sanitize_json_value(error.get("msg", "请求字段不合法"))).strip()
        if message and message not in result.setdefault(field, []):
            result[field].append(message)
    return result


def get_request_id(request: Request) -> str:
    """读取中间件写入的请求 ID，并在独立测试场景生成后备值。

    Args:
        request: 当前 FastAPI/Starlette 请求。

    Returns:
        可用于响应头、错误体和日志关联的请求 ID。
    """
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return uuid4().hex


def build_error_detail(
    *,
    code: str,
    message: str,
    field_errors: Mapping[str, Sequence[str] | str] | None = None,
    details: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """构建通过严格 Schema 校验的公共错误 detail。

    Args:
        code: 稳定错误码。
        message: 安全用户消息。
        field_errors: 可选字段错误。
        details: 可选安全附加信息。
        request_id: 当前请求关联 ID。

    Returns:
        可直接放入 HTTP ``detail`` 的 JSON 字典。
    """
    payload = ApiErrorDetail(
        code=code,
        message=str(sanitize_json_value(message)).strip() or "请求失败",
        field_errors=normalize_field_errors(field_errors),
        details=sanitize_json_value(dict(details or {}), redact_input=True),
        request_id=request_id,
    )
    return payload.model_dump(mode="json")


def api_http_exception(
    *,
    status_code: int,
    code: str,
    message: str,
    field_errors: Mapping[str, Sequence[str] | str] | None = None,
    details: Mapping[str, Any] | None = None,
) -> HTTPException:
    """创建遵循公共协议的 HTTPException。

    Args:
        status_code: HTTP 状态码。
        code: 稳定错误码。
        message: 安全用户消息。
        field_errors: 可选字段错误映射。
        details: 可选安全附加信息。

    Returns:
        可由 Router 直接抛出的 FastAPI HTTPException。
    """
    return HTTPException(
        status_code=status_code,
        detail=build_error_detail(
            code=code,
            message=message,
            field_errors=field_errors,
            details=details,
        ),
    )


def exception_to_error(
    exc: Exception,
    *,
    fallback_message: str = "请求处理失败",
) -> tuple[int, str, str, dict[str, list[str]], dict[str, Any]]:
    """把共享领域、数据库和 LLM 异常转换为稳定错误语义。

    Args:
        exc: 服务层、数据库层或 LLM 层抛出的异常。
        fallback_message: 未知异常对外展示的安全消息。

    Returns:
        状态码、错误码、消息、字段错误和附加信息组成的元组。
    """
    if isinstance(exc, DomainApiError):
        return (
            exc.status_code,
            exc.code,
            exc.message,
            exc.field_errors,
            exc.details,
        )
    # 兼容当前 GenerationDomainError，后续领域可逐步迁移为 DomainApiError。
    if all(hasattr(exc, field) for field in ("status_code", "code", "message")):
        return (
            int(getattr(exc, "status_code")),
            str(getattr(exc, "code")),
            str(getattr(exc, "message")),
            {},
            {},
        )
    if isinstance(exc, NotFoundError):
        return 404, "RESOURCE_NOT_FOUND", str(exc) or "资源不存在", {}, {}
    if isinstance(exc, InvalidIdError):
        return 422, "INVALID_OBJECT_ID", str(exc) or "ObjectId 不合法", {}, {}
    if isinstance(exc, DuplicateKeyError):
        return 409, "RESOURCE_CONFLICT", str(exc) or "资源冲突", {}, {}
    if isinstance(exc, LLMTimeoutError):
        return 504, "LLM_WORKFLOW_TIMEOUT", "模型请求超时，请重试", {}, {}
    if isinstance(exc, LLMDuplicateKeyError):
        # 只公开专用错误中的模型正文；不读取任意异常的响应、URL 或配置。
        return 502, "LLM_JSON_DUPLICATE_KEY", "模型 JSON 有重复字段，请查看原文并重新生成", {
            exc.duplicate_path: ["同一对象内的字段名重复，不能确定要保留哪一份内容"],
        }, {
            "duplicate_path": exc.duplicate_path,
            "duplicate_path_length": exc.duplicate_path_length,
            "duplicate_path_truncated": exc.duplicate_path_truncated,
            "raw_output": exc.raw_output,
            "raw_output_length": exc.raw_output_length,
            "raw_output_truncated": exc.raw_output_truncated,
            "raw_output_untrusted": True,
        }
    if isinstance(exc, LLMResponseError) and exc.partial_text is not None:
        return 502, "LLM_RESULT_INVALID", "模型输出达到长度上限，内容未完成，请增加输出上限后重新生成", {}, {
            "raw_output": exc.partial_text,
            "raw_output_length": exc.partial_text_length,
            "raw_output_truncated": exc.partial_text_truncated,
            "raw_output_untrusted": True,
        }
    if isinstance(exc, (LLMResponseError, LLMSchemaError)):
        return 502, "LLM_RESULT_INVALID", "模型返回结果无效，请重试", {}, {}
    if isinstance(exc, (LLMAuthError, LLMRateLimitError)):
        return 503, "LLM_PROVIDER_UNAVAILABLE", "模型服务暂时不可用，请稍后重试", {}, {}
    if isinstance(exc, LLMError):
        return 502, "LLM_PROVIDER_FAILED", "模型服务调用失败，请重试", {}, {}
    if isinstance(exc, (TypeError, ValueError)):
        return 422, "REQUEST_RULE_INVALID", str(exc) or "请求规则不合法", {}, {}
    return 500, "INTERNAL_ERROR", fallback_message, {}, {}


def relation_http_exception(exc: Exception) -> HTTPException:
    """把角色关系和阵营关系已捕获的异常转为相同的 HTTP 错误。

    Args:
        exc: 关系接口捕获的领域、仓储或字段校验异常。

    Returns:
        保留关系错误码、原始消息和完整字段路径的 HTTPException。
    """
    if isinstance(exc, ValidationError):
        field_errors: dict[str, list[str]] = {}
        for error in exc.errors():
            # 这里的 body 等名称属于模型字段，不能按 HTTP 请求位置裁剪。
            field = ".".join(str(part) for part in error.get("loc", ())) or "$"
            message = str(sanitize_json_value(error.get("msg", "请求字段不合法"))).strip()
            if message and message not in field_errors.setdefault(field, []):
                field_errors[field].append(message)
        return HTTPException(
            status_code=422,
            detail={
                "code": "REQUEST_VALIDATION_FAILED",
                "message": "请求字段校验失败",
                "field_errors": field_errors,
            },
        )
    message = str(exc)
    if isinstance(exc, NotFoundError):
        status_code, code = 404, "RELATION_NOT_FOUND"
    elif isinstance(exc, VersionConflictError):
        status_code, code = 409, "VERSION_CONFLICT"
    elif isinstance(exc, DuplicateKeyError):
        status_code, code = 409, "RELATION_CONFLICT"
    elif isinstance(exc, InvalidIdError):
        status_code, code = 422, "INVALID_OBJECT_ID"
    elif isinstance(exc, (TypeError, ValueError)):
        status_code, code = 422, "RELATION_VALIDATION_FAILED"
    else:
        # 关系接口捕获的 GenerationDomainError 沿用公共领域错误约定。
        status_code, code, message, _, _ = exception_to_error(exc)
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def sse_error_payload(
    exc: Exception,
    *,
    request_id: str | None = None,
    fallback_message: str = "生成失败",
) -> dict[str, Any]:
    """构建建连后唯一终态 ``error`` 事件的稳定载荷。

    Args:
        exc: 流式工作流中捕获的异常。
        request_id: 与 HTTP 请求及日志关联的请求 ID。
        fallback_message: 未知异常使用的安全消息。

    Returns:
        包含 code、message、status_code 和可选字段问题的事件数据。
    """
    request_id = request_id or log_context.get().get("request_id")
    log_exception(logger, f"[SSE 失败] request_id={request_id}", exc)
    status_code, code, message, field_errors, details = exception_to_error(
        exc,
        fallback_message=fallback_message,
    )
    detail = build_error_detail(
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
        request_id=request_id,
    )
    return {"success": False, "status_code": status_code, **detail}


def sse_event(event: str, data: Mapping[str, Any]) -> str:
    """序列化一条 UTF-8 JSON SSE 事件。

    Args:
        event: SSE 事件名称。
        data: 可 JSON 编码的事件载荷。

    Returns:
        以空行结尾的标准 SSE 文本。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _legacy_http_error_detail(status_code: int, detail: Any) -> dict[str, Any]:
    """将历史 Router 的字符串或局部字典 detail 归一为公共协议。

    Args:
        status_code: 原 HTTPException 状态码。
        detail: 历史 Router 提交的 detail。

    Returns:
        尚未补 request_id 的公共错误 detail。
    """
    if isinstance(detail, Mapping):
        raw_code = detail.get("code")
        raw_message = detail.get("message")
        if isinstance(raw_code, str) and isinstance(raw_message, str):
            return build_error_detail(
                code=raw_code,
                message=raw_message,
                field_errors=detail.get("field_errors"),
                details=detail.get("details"),
            )
    default_codes = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        409: "RESOURCE_CONFLICT",
        422: "REQUEST_VALIDATION_FAILED",
        502: "UPSTREAM_RESULT_INVALID",
        503: "DEPENDENCY_UNAVAILABLE",
        504: "WORKFLOW_TIMEOUT",
    }
    message = str(sanitize_json_value(detail)).strip() if detail is not None else ""
    if status_code >= 500:
        # 遗留 5xx 常直接使用 str(exc)，应用边界不再把内部信息返回给调用方。
        message = "服务暂时不可用，请稍后重试" if status_code in {502, 503, 504} else "内部服务错误"
    return build_error_detail(
        code=default_codes.get(status_code, "HTTP_ERROR"),
        message=message or "请求失败",
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """将全部 HTTPException 统一为公共错误响应。

    Args:
        request: 当前 FastAPI 请求。
        exc: Router 或框架抛出的 HTTPException。

    Returns:
        保留原状态码和头部的 JSON 错误响应。
    """
    log_exception(logger, f"[HTTP 失败] method={request.method} path={request.url.path} status={exc.status_code} request_id={get_request_id(request)}", exc,
                  level=logging.ERROR if exc.status_code >= 500 else logging.WARNING)
    detail = _legacy_http_error_detail(exc.status_code, exc.detail)
    detail["request_id"] = get_request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """将 FastAPI 请求校验错误转换为公共 422 响应且不回显输入。

    Args:
        request: 当前 FastAPI 请求。
        exc: FastAPI 汇总的请求校验异常。

    Returns:
        包含字段路径映射和请求 ID 的安全 422 JSON 响应。
    """
    log_exception(logger, f"[请求校验失败] method={request.method} path={request.url.path} request_id={get_request_id(request)}", exc, level=logging.WARNING)
    return JSONResponse(
        status_code=422,
        content={
            "detail": build_error_detail(
                code="REQUEST_VALIDATION_FAILED",
                message="请求字段校验失败",
                field_errors=validation_field_errors(exc),
                request_id=get_request_id(request),
            )
        },
    )


async def domain_api_exception_handler(
    request: Request,
    exc: DomainApiError,
) -> JSONResponse:
    """把未在 Router 捕获的共享领域异常转换为公共响应。

    Args:
        request: 当前 FastAPI 请求。
        exc: 共享领域异常。

    Returns:
        使用异常状态码的公共 JSON 错误响应。
    """
    log_exception(logger, f"[API 失败] method={request.method} path={request.url.path} code={exc.code} request_id={get_request_id(request)} details={exc.details} fields={exc.field_errors}", exc,
                  level=logging.ERROR if exc.status_code >= 500 else logging.WARNING)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": build_error_detail(
                code=exc.code,
                message=exc.message,
                field_errors=exc.field_errors,
                details=exc.details,
                request_id=get_request_id(request),
            )
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """记录未知异常并只返回安全信息和 request_id。

    Args:
        request: 当前 FastAPI 请求。
        exc: 未被领域或 Router 处理的异常。

    Returns:
        不泄露异常文本和堆栈的公共 500 响应。
    """
    request_id = get_request_id(request)
    log_exception(logger, f"[API 未处理异常] method={request.method} path={request.url.path} request_id={request_id}", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": build_error_detail(
                code="INTERNAL_ERROR",
                message="内部服务错误",
                request_id=request_id,
            )
        },
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求提供可验证且可回传的关联 ID。"""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """写入请求上下文并将相同 ID 放入响应头。

        Args:
            request: 当前 Starlette 请求。
            call_next: 下一个中间件或路由处理器。

        Returns:
            带 ``X-Request-ID`` 响应头的原响应。
        """
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid4().hex
        request.state.request_id = request_id
        with bind_log_context(request_id=request_id):
            logger.info("[HTTP 请求] method=%s path=%s", request.method, request.url.path)
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = [
    "ApiErrorDetail",
    "ApiErrorResponse",
    "DomainApiError",
    "HTTP_ERROR_STATUS_SEMANTICS",
    "REQUEST_ID_HEADER",
    "RequestIdMiddleware",
    "api_http_exception",
    "build_error_detail",
    "domain_api_exception_handler",
    "exception_to_error",
    "http_exception_handler",
    "normalize_field_errors",
    "relation_http_exception",
    "request_validation_exception_handler",
    "sanitize_json_value",
    "sse_error_payload",
    "sse_event",
    "unhandled_exception_handler",
    "validation_field_errors",
]
