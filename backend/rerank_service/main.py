"""本地 Rerank 服务（OpenAI 兼容 /rerank 接口）。

使用 BAAI/bge-reranker-v2-m3（跨语言重排模型，约 2.3GB）对检索候选做精排，
与 app/agent/rag.py 的 rerank() 调用契约一致：
    POST /rerank
    { "model": "bge-reranker-v2-m3", "query": "问题", "documents": ["片段1", "片段2"] }
    -> { "results": [ { "index": 0, "relevance_score": 0.91 }, ... ] }

启动：
    python -m rerank_service        # 监听 0.0.0.0:8089
    RERANK_PORT=9001 python -m rerank_service

依赖见同目录 requirements.txt（sentence-transformers + torch）。
"""
from __future__ import annotations

import logging
import os

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rerank_service")

MODEL_NAME = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
PORT = int(os.getenv("RERANK_PORT", "7089"))
# 模型权重缓存目录（默认与项目 data 同级，Docker 下挂载持久化）
CACHE_DIR = os.getenv("HF_HOME", os.path.join(os.path.dirname(__file__), "..", "data", "models"))

# 延迟加载，健康检查不依赖大模型
_MODEL = None


def load_model():
    global _MODEL
    if _MODEL is not None:
        return
    # 国内/离线环境：默认走 HF 镜像加速下载；完全无外网时仅在本地缓存命中时才可用。
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    # CrossEncoder 不支持 cache_folder，改用 HF_HOME 统一控制权重缓存目录
    os.environ["HF_HOME"] = os.path.abspath(CACHE_DIR)
    # 内存紧张时限制 torch 线程数，降低加载期的瞬时内存峰值（避免页面文件不足 1455）
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    from sentence_transformers import CrossEncoder

    logger.info("加载 rerank 模型 %s（缓存目录: %s）", MODEL_NAME, os.environ["HF_HOME"])
    try:
        # device="cpu"：明确走 CPU 加载，避免 CUDA 上下文额外占用；
        # torch_dtype="auto" 由 transformers 决定，默认 fp32。
        _MODEL = CrossEncoder(MODEL_NAME, device="cpu")
    except Exception as e:  # noqa: BLE001
        _MODEL = None
        raise RuntimeError(
            f"加载 rerank 模型失败：{e}\n"
            f"请将 bge-reranker-v2-m3 权重放置到 {os.environ['HF_HOME']}/BAAI/bge-reranker-v2-m3/ 后重试，"
            f"或确保网络可访问 HF 镜像（HF_ENDPOINT）。"
        ) from e
    logger.info("rerank 模型加载完成")


class RerankRequest(BaseModel):
    model: str = Field(default=MODEL_NAME)
    query: str
    documents: list[str]
    # 兼容可选字段
    top_n: int | None = None
    return_documents: bool = False


class RerankResponse(BaseModel):
    results: list[dict]
    model: str


app = FastAPI(title="Local Rerank Service (bge-reranker-v2-m3)")


@app.on_event("startup")
def _startup():
    try:
        load_model()
    except Exception as e:  # noqa: BLE001
        logger.warning("模型预加载失败（%s）。首次请求时再次尝试加载。", e)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "loaded": _MODEL is not None}


@app.post("/rerank", response_model=RerankResponse)
def rerank(req: RerankRequest) -> RerankResponse:
    load_model()
    if _MODEL is None:
        raise HTTPException(status_code=503, detail="rerank 模型未就绪")
    if not req.documents:
        return RerankResponse(results=[], model=req.model)

    pairs = [(req.query, doc) for doc in req.documents]
    scores = _MODEL.predict(pairs, convert_to_numpy=True)
    results = [
        {"index": i, "relevance_score": float(scores[i])}
        for i in range(len(req.documents))
    ]
    # 按相关性降序返回（与多数 rerank 服务一致）
    results.sort(key=lambda r: r["relevance_score"], reverse=True)
    return RerankResponse(results=results, model=req.model)


if __name__ == "__main__":
    uvicorn.run("rerank_service.main:app", host="0.0.0.0", port=PORT)
