"""FastAPI application entrypoint (层级 3 Agent 核心调度服务 + API 网关)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routers import admin, auth, chat, files, knowledge, tools
from app.config import settings
from app.db.base import async_session_maker, engine
from app.db.models import Base
from app.seed import seed_initial_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure pg_vector extension + all tables exist, then seed demo data.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        # pg_trgm 提供 similarity()（关键词召回相似度排序，RAG 初筛层依赖）
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        await seed_initial_data(session)
    yield
    await engine.dispose()


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = settings.API_V1_PREFIX
for r in (auth, chat, tools, admin, knowledge, files):
    app.include_router(r.router, prefix=API)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Optionally serve the built Vue frontend if present (production single-image deploy).
_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")


# Equivalent to: uvicorn app.main:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn

    # 热重载可用环境变量 RELOAD 控制（默认开启，方便开发）。
    # Windows 上 reload 会因 SQLAlchemy 导入触发 cmd /c ver，既慢又易在中断时打印
    # KeyboardInterrupt traceback；生产/稳定运行时设为 false： $env:RELOAD="false"
    reload_enabled = os.getenv("RELOAD", "true").lower() in ("1", "true", "yes")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=reload_enabled)
