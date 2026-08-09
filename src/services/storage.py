"""
Thin async wrapper around the MinIO (S3-compatible) client for wish
attachments (images/GIFs).

The `minio` SDK is synchronous, so every call is pushed through
`run_in_threadpool` to avoid blocking the event loop. Traffic here is a
handful of small-file uploads/downloads at a time — nowhere near enough to
justify the heavier aioboto3/aiobotocore stack.
"""

import io
import logging

from minio import Minio
from minio.error import S3Error
from starlette.concurrency import run_in_threadpool

from src.config import config

logger = logging.getLogger(__name__)

_client = Minio(
    config.MINIO_ENDPOINT,
    access_key=config.MINIO_ACCESS_KEY,
    secret_key=config.MINIO_SECRET_KEY,
    secure=config.MINIO_SECURE,
)


async def ensure_bucket() -> None:
    """Create the attachments bucket if it doesn't exist yet. Call once at startup."""

    def _ensure() -> None:
        if not _client.bucket_exists(config.MINIO_BUCKET):
            _client.make_bucket(config.MINIO_BUCKET)

    await run_in_threadpool(_ensure)


async def upload(key: str, data: bytes, content_type: str) -> None:
    def _put() -> None:
        _client.put_object(
            config.MINIO_BUCKET,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    await run_in_threadpool(_put)


async def download(key: str) -> tuple[bytes, str]:
    """Return (bytes, content_type). Raises FileNotFoundError if the key is missing."""

    def _get() -> tuple[bytes, str]:
        try:
            resp = _client.get_object(config.MINIO_BUCKET, key)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise FileNotFoundError(key) from exc
            raise
        try:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            return data, content_type
        finally:
            resp.close()
            resp.release_conn()

    return await run_in_threadpool(_get)


async def delete(key: str) -> None:
    """Best-effort delete — a failure here shouldn't block the caller's own operation."""

    def _del() -> None:
        _client.remove_object(config.MINIO_BUCKET, key)

    try:
        await run_in_threadpool(_del)
    except S3Error as exc:
        logger.warning("Failed to delete attachment %s: %s", key, exc)
