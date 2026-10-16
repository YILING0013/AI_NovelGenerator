"""后端应用装配、路由注册和启动过程。"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.storage import COVERS_DIR, USER_DATA_DIR
from backend.migrations import prepare_files, storage_lock
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.error_protocol import (
    ApiErrorResponse,
    DomainApiError,
    RequestIdMiddleware,
    domain_api_exception_handler,
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)

from backend.db.mongo import connect_to_mongo, close_mongo_connection
from backend.api.default_routers.config_router import router as config_router
from backend.api.default_routers.runtime_router import router as runtime_router
from backend.api.default_routers.task_flow_router import router as task_flow_router
from backend.api.default_routers.assistant_router import router as assistant_router
from backend.api.default_routers.novel_router import router as novel_router
from backend.api.default_routers.initialization_router import (
    router as initialization_router,
)
from backend.api.default_routers.volume_router import router as volume_router
from backend.api.default_routers.arc_router import router as arc_router
from backend.api.default_routers.scene_router import router as scene_router
from backend.api.default_routers.chapter_router import router as chapter_router
from backend.api.default_routers.writing_router import router as writing_router
from backend.api.default_routers.plot_router import router as plot_router
from backend.api.default_routers.faction_router import router as faction_router
from backend.api.default_routers.faction_fact_router import router as faction_fact_router
from backend.api.default_routers.faction_relation_router import router as faction_relation_router
from backend.api.default_routers.character_router import router as character_router
from backend.api.default_routers.character_fact_router import router as character_fact_router
from backend.api.default_routers.character_relation_router import router as character_relation_router
from backend.api.default_routers.character_relation_fact_router import router as character_relation_fact_router
from backend.api.default_routers.item_fact_router import router as item_fact_router
from backend.api.default_routers.character_faction_binding_router import (
    router as character_faction_binding_router,
)
from backend.api.default_routers.world_rule_router import router as world_rule_router
from backend.api.default_routers.location_router import router as location_router
from backend.api.default_routers.item_router import router as item_router
from backend.api.default_routers.foreshadowing_router import router as foreshadowing_router
from backend.api.default_routers.chapter_record_router import router as chapter_record_router
from backend.api.default_routers.character_volume_state_router import (
    router as character_volume_state_router,
    plan_router as character_volume_plan_router,
)
from backend.api.default_routers.faction_volume_state_router import (
    router as faction_volume_state_router,
)
from backend.api.llm_routers.create_novel_router import router as create_novel_router
from backend.api.llm_routers.character_generation_router import router as character_generation_router
from backend.api.llm_routers.world_rule_generation_router import (
    router as world_rule_generation_router,
)
from backend.api.llm_routers.volume_planning_router import (
    router as volume_planning_router,
)
from backend.api.llm_routers.volume_location_generation_router import (
    router as volume_location_generation_router,
)
from backend.api.llm_routers.volume_entity_generation_router import router as volume_entity_generation_router
from backend.api.llm_routers.item_generation_router import (
    router as item_generation_router,
)
from backend.services.task_flows import store as task_flow_store
from backend.services.task_flows.registry import TASKS
from backend.runtime import (
    apply_runtime_flags_from_argv,
    build_uvicorn_log_config,
    get_backend_port,
    get_frontend_port,
    is_backend_debug_enabled,
)

apply_runtime_flags_from_argv()

logger = logging.getLogger(__name__)
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = get_backend_port()
FRONTEND_PORT = get_frontend_port()
FRONTEND_ORIGINS = [
    f"http://127.0.0.1:{FRONTEND_PORT}",
    f"http://localhost:{FRONTEND_PORT}",
]


# FastAPI setup with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI应用的生命周期管理，在启动时完成配置校验与资源连接。

    Args:
        app: 当前 FastAPI 应用实例。

    Returns:
        异步生命周期上下文生成器。
    """
    logger.info(
        "Backend startup: debug=%s docs=http://%s:%s/docs",
        is_backend_debug_enabled(),
        BACKEND_HOST,
        BACKEND_PORT,
    )
    for notice in prepare_files():
        logger.warning(notice)
    with storage_lock(USER_DATA_DIR / "migrations/service.lock"):
        try:
            for task in TASKS:
                task_flow_store.flow_store().get_default(task)
            try:
                await connect_to_mongo()
            except Exception as exc:
                from backend.db import mongo
                from backend.migrations.database import database_setup_error
                issue = database_setup_error(exc)
                if issue is None: raise
                mongo.setup_error = issue
                logger.warning("%s 仅开放设置，业务功能仍不可用。", issue["message"])
            app.state.startup_checked = True
            logger.info("Backend startup completed.")
            yield
        finally:
            await close_mongo_connection()
    logger.info("Backend shutdown completed.")

COMMON_ERROR_RESPONSES = {
    status_code: {"model": ApiErrorResponse}
    for status_code in (400, 404, 409, 422, 500, 502, 503, 504)
}

app = FastAPI(
    title="Novel Generator API",
    lifespan=lifespan,
    # 日志开关只控制输出，错误响应始终使用项目已有的错误格式。
    debug=False,
    responses=COMMON_ERROR_RESPONSES,
)

# 公共 handler 在应用边界兼容旧 Router 的字符串 detail，新 Router 应直接抛共享领域异常。
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
app.add_exception_handler(DomainApiError, domain_api_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

@app.middleware("http")
async def require_database(request: Request, call_next):
    """没有数据库时只开放设置及导出；业务接口不能绕过首次检查。"""
    from backend.db import mongo
    allowed = request.url.path in {"/api/startup", "/api/config", "/api/exports"} or request.url.path.startswith("/api/config/")
    if getattr(app.state, "startup_checked", False) and mongo.client is None and request.url.path.startswith("/api/") and not allowed and request.method != "OPTIONS":
        return JSONResponse(status_code=503, content={"error": {"code": "DATABASE_SETUP_REQUIRED", "message": "请先在设置中配置数据库。"}})
    return await call_next(request)


# CORS 与启动器选定的前端端口保持一致，同时兼容 localhost 与 IPv4 回环地址。
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)


@app.get("/api/startup")
async def startup_status():
    """告知界面是否需要设置，不返回连接凭据。Returns: 启动状态。"""
    from backend.db import mongo
    return {"setup_required": mongo.client is None, "setup_error": mongo.setup_error if mongo.client is None else None}


# Register routes
app.mount("/static/covers", StaticFiles(directory=str(COVERS_DIR), check_dir=False), name="static_covers")

app.include_router(novel_router)
app.include_router(initialization_router)
app.include_router(volume_router)
app.include_router(arc_router)
app.include_router(scene_router)
app.include_router(chapter_router)
app.include_router(writing_router)
app.include_router(plot_router)
app.include_router(faction_router)
app.include_router(faction_fact_router)
app.include_router(faction_relation_router)
app.include_router(character_router)
app.include_router(character_fact_router)
app.include_router(character_relation_router)
app.include_router(character_relation_fact_router)
app.include_router(item_fact_router)
app.include_router(character_faction_binding_router)
app.include_router(world_rule_router)
app.include_router(location_router)
app.include_router(item_router)
app.include_router(foreshadowing_router)
app.include_router(chapter_record_router)
app.include_router(character_volume_state_router)
app.include_router(character_volume_plan_router)
app.include_router(faction_volume_state_router)
from backend.api.default_routers.export_router import router as export_router
app.include_router(export_router)
app.include_router(config_router)
app.include_router(runtime_router)
app.include_router(task_flow_router)
app.include_router(assistant_router)
app.include_router(create_novel_router)
app.include_router(character_generation_router)
app.include_router(world_rule_generation_router)
app.include_router(volume_planning_router)
app.include_router(volume_location_generation_router)
app.include_router(volume_entity_generation_router)
app.include_router(item_generation_router)

def main() -> None:
    """按当前端口和日志设置启动后端。

    Args:
        无。

    Returns:
        无；服务停止后返回。
    """
    import uvicorn

    uvicorn.run(
        app,
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=False,
        log_config=build_uvicorn_log_config(),
    )
