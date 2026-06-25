from fastapi import APIRouter, HTTPException
from datetime import timedelta
import os
from minio import Minio
from minio.error import S3Error

router = APIRouter(prefix="/api", tags=["downloads"])

MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", "10.202.135.233:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
BUILT_BUCKET = os.getenv("MINIO_BUILT_BUCKET", "vm-images")


def _public_client() -> Minio:
    return Minio(
        MINIO_PUBLIC_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


@router.get("/downloads/{image_name}")
def get_download_url(image_name: str):
    object_name = image_name if image_name.endswith(".qcow2") else f"{image_name}.qcow2"
    client = _public_client()
    try:
        stat = client.stat_object(BUILT_BUCKET, object_name)
    except S3Error:
        raise HTTPException(status_code=404, detail=f"image not found: {object_name}")
    url = client.presigned_get_object(
        BUILT_BUCKET, object_name, expires=timedelta(hours=1)
    )
    return {
        "url": url,
        "object": object_name,
        "size_mb": round((stat.size or 0) / 1024 / 1024),
        "expires_hours": 1,
    }