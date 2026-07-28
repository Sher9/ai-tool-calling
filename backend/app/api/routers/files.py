"""Serve locally-stored objects (MinIO fallback) and object-store redirects."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core.security import get_current_user
from app.core.storage import get_object_bytes
from app.db.models import User

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/local/{object_key}")
async def local_file(object_key: str, user: User = Depends(get_current_user)):
    # prevent path traversal
    if "/" in object_key or "\\" in object_key or ".." in object_key:
        raise HTTPException(status_code=400, detail="invalid key")
    data = await get_object_bytes(object_key)
    if data is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return Response(content=data, media_type="application/octet-stream")


@router.get("/object/{object_key}")
async def object_file(object_key: str, user: User = Depends(get_current_user)):
    # In production this would return a MinIO presigned URL redirect.
    data = await get_object_bytes(object_key)
    if data is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return Response(content=data, media_type="application/octet-stream")
