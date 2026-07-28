"""本地 Embedding 服务（OpenAI 兼容 /v1/embeddings）。

使用 BAAI/bge-small-zh-v1.5（中文轻量嵌入模型，512 维，约 90MB）提供向量化能力，
让 Agent 平台的 RAG 流程在完全私有化、无需外网的环境下跑通。

接口与 app/agent/rag.py 的 embed_text 调用一致：
    POST /v1/embeddings
    { "model": "bge-small-zh-v1.5", "input": "文本" 或 ["文本1", "文本2"] }
    -> { "data": [ { "embedding": [...] }, ... ] }

启动：
    python -m embedding_service        # 监听 0.0.0.0:7088
    EMBEDDING_PORT=9000 python -m embedding_service

依赖见同目录 requirements.txt（sentence-transformers + torch）。
"""
from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("embedding_service")

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
PORT = int(os.getenv("EMBEDDING_PORT", "7088"))
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
    from sentence_transformers import SentenceTransformer

    logger.info("加载 embedding 模型 %s（缓存目录: %s）", MODEL_NAME, CACHE_DIR)
    try:
        _MODEL = SentenceTransformer(MODEL_NAME, cache_folder=CACHE_DIR)
    except Exception as e:  # noqa: BLE001
        _MODEL = None
        raise RuntimeError(
            f"加载 embedding 模型失败：{e}\n"
            f"请将 bge-small-zh-v1.5 权重放置到 {CACHE_DIR}/BAAI/bge-small-zh-v1.5/ 后重试，"
            f"或确保网络可访问 HF 镜像（HF_ENDPOINT）。"
        ) from e
    logger.info("embedding 模型加载完成，维度=%d", _MODEL.get_sentence_embedding_dimension())


class EmbedRequest(BaseModel):
    model: str = Field(default=MODEL_NAME)
    input: str | list[str]
    # bge 不需要 instruction，但兼容 OpenAI 字段，忽略即可
    encoding_format: str | None = None
    dimensions: int | None = None


class EmbedResponse(BaseModel):
    object: str = "list"
    data: list[dict]
    model: str


app = FastAPI(title="Local Embedding Service (bge-small-zh-v1.5)")


@app.on_event("startup")
def _startup():
    # 后台预加载，避免首个请求过慢；失败仅告警，健康检查仍可用
    try:
        load_model()
    except Exception as e:  # noqa: BLE001
        logger.warning("模型预加载失败（%s）。首次请求时再次尝试加载。", e)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "loaded": _MODEL is not None}


@app.post("/v1/embeddings", response_model=EmbedResponse)
def embeddings(req: EmbedRequest) -> EmbedResponse:
    load_model()
    if _MODEL is None:
        raise HTTPException(status_code=503, detail="embedding 模型未就绪")

    texts = req.input if isinstance(req.input, list) else [req.input]
    # bge 推荐对检索查询加指令前缀；此处统一对单句做基础编码
    vectors = _MODEL.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    data = [{"object": "embedding", "index": i, "embedding": v.tolist()} for i, v in enumerate(vectors)]
    return EmbedResponse(data=data, model=req.model)


if __name__ == "__main__":
    uvicorn.run("embedding_service.main:app", host="0.0.0.0", port=PORT)
