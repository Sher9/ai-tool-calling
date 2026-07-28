"""允许 `python -m embedding_service` 直接启动本地 Embedding 服务。"""
import os

import uvicorn

from embedding_service.main import app

if __name__ == "__main__":
    port = int(os.getenv("EMBEDDING_PORT", "7088"))
    uvicorn.run(app, host="0.0.0.0", port=port)
