"""Object storage abstraction over MinIO with a local-disk fallback.

Files (uploaded knowledge docs, generated reports, charts) are stored in MinIO
when available; in a dev environment without MinIO they fall back to a local
`data/` directory served via the /files/local route so the platform still runs.
"""
from __future__ import annotations

import base64
import logging
import os
import uuid

from app.config import settings

logger = logging.getLogger("storage")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "files")

_minio_client = None
_minio_ok = False
_minio_warned = False


def _ensure_minio() -> bool:
    global _minio_client, _minio_ok, _minio_warned
    if _minio_ok:
        return True
    if _minio_client is not None:
        return _minio_ok
    try:
        from minio import Minio

        _minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        if not _minio_client.bucket_exists(settings.MINIO_BUCKET):
            _minio_client.make_bucket(settings.MINIO_BUCKET)
        _minio_ok = True
        logger.info("MinIO 已连接：endpoint=%s, bucket=%s 就绪", settings.MINIO_ENDPOINT, settings.MINIO_BUCKET)
    except Exception as e:
        _minio_ok = False
        _minio_client = None
        if not _minio_warned:
            logger.warning("MinIO 不可用（%s），将回退到本地磁盘存储：%s", settings.MINIO_ENDPOINT, e)
            _minio_warned = True
    return _minio_ok


async def save_object(data: bytes, filename: str, content_type: str = "application/octet-stream") -> dict:
    """Store `data`; return dict(name, object_key, url, backend)."""
    object_key = f"{uuid.uuid4().hex}_{filename}"
    if _ensure_minio():
        try:
            from io import BytesIO

            _minio_client.put_object(
                settings.MINIO_BUCKET, object_key, BytesIO(data), length=len(data), content_type=content_type
            )
            url = f"/api/v1/files/object/{object_key}"
            return {"name": filename, "object_key": object_key, "url": url, "backend": "minio"}
        except Exception:
            pass
    # local fallback
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, object_key)
    with open(path, "wb") as f:
        f.write(data)
    return {
        "name": filename,
        "object_key": object_key,
        "url": f"/api/v1/files/local/{object_key}",
        "backend": "local",
    }


async def get_object_bytes(object_key: str) -> bytes | None:
    if _ensure_minio():
        try:
            resp = _minio_client.get_object(settings.MINIO_BUCKET, object_key)
            data = resp.read()
            resp.close()
            resp.release_conn()
            return data
        except Exception:
            pass
    path = os.path.join(DATA_DIR, object_key)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None


def b64_png(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
