"""财务 ERP 仿真业务系统入口。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, async_session_maker, engine
from app.router import router
from app.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(30):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except Exception as e:  # noqa: BLE001
            logging.warning("财务 数据库未就绪，第 %d 次重试: %s", attempt + 1, e)
            await asyncio.sleep(2)
    async with async_session_maker() as s:
        await seed(s)
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
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
