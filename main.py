import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.db.mongo import connect_to_mongo, close_mongo_connection
from application.db.indexes import init_all_indexes
from application.api.default_routers.config_router import router as config_router
from application.api.default_routers.novel_router import router as novel_router
from application.api.default_routers.upload_router import router as upload_router
from application.api.default_routers.volume_router import router as volume_router
from application.api.llm_routers.create_novel_router import router as create_novel_router
from fastapi.staticfiles import StaticFiles
# FastAPI setup with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI应用的生命周期管理，在启动时连接数据库，在关闭时断开连接"""
    # Setup Mongo
    await connect_to_mongo()
    # Initialize DB Indexes
    await init_all_indexes()
    yield
    # Teardown
    await close_mongo_connection()

app = FastAPI(title="Novel Generator API", lifespan=lifespan)

# CORS — 允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
import os
os.makedirs("static/covers", exist_ok=True)
app.mount("/static/covers", StaticFiles(directory="static/covers"), name="static_covers")

app.include_router(novel_router)
app.include_router(volume_router)
app.include_router(config_router)
app.include_router(create_novel_router)
app.include_router(upload_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        reload_excludes=[
            "frontend/**",
            "frontend/.next/**",
            "frontend/node_modules/**",
        ],
    )