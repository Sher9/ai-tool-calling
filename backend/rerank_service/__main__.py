"""允许 `python -m rerank_service` 直接启动本地 Rerank 服务。"""
import os

import uvicorn

from rerank_service.main import app

if __name__ == "__main__":
    port = int(os.getenv("RERANK_PORT", "7089"))
    uvicorn.run(app, host="0.0.0.0", port=port)
