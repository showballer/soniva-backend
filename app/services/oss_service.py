"""
Aliyun OSS service.

Thin wrapper around oss2 used for uploading user-provided chat screenshots
(the 识Ta feature). Files are stored under `identify/<user_id>/<uuid>.<ext>`
and returned as a public https URL.
"""
from __future__ import annotations

import logging
import mimetypes
from pathlib import PurePosixPath
from typing import Optional
from uuid import uuid4

import oss2

from app.config import settings

logger = logging.getLogger(__name__)


class OSSServiceUnavailable(RuntimeError):
    """Raised when OSS is not configured but the app tries to upload."""


class OSSService:
    _bucket: Optional[oss2.Bucket] = None
    _public_host: str = ""

    @classmethod
    def _get_bucket(cls) -> oss2.Bucket:
        if cls._bucket is not None:
            return cls._bucket

        key_id = settings.OSS_KEY_ID
        key_secret = settings.OSS_KEY_SECRET
        bucket_name = settings.OSS_BUCKET
        endpoint = settings.OSS_ENDPOINT_URL

        if not (key_id and key_secret and bucket_name and endpoint):
            raise OSSServiceUnavailable(
                "OSS credentials are not configured. "
                "Set ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET / "
                "ALIYUN_OSS_REGION / ALIYUN_OSS_BUCKET in the backend .env."
            )

        auth = oss2.Auth(key_id, key_secret)
        cls._bucket = oss2.Bucket(auth, endpoint, bucket_name)
        cls._public_host = settings.OSS_PUBLIC_HOST
        return cls._bucket

    @classmethod
    def upload_identify_image(
        cls,
        *,
        user_id: str,
        file_bytes: bytes,
        filename: str,
    ) -> str:
        """Upload an image and return its public https URL."""
        bucket = cls._get_bucket()

        ext = PurePosixPath(filename).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".bmp"}:
            ext = ".jpg"

        key = f"identify/{user_id}/{uuid4().hex}{ext}"
        content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

        logger.info("OSS upload: bucket=%s key=%s size=%d", bucket.bucket_name, key, len(file_bytes))
        bucket.put_object(key, file_bytes, headers={"Content-Type": content_type})

        public_host = cls._public_host or settings.OSS_PUBLIC_HOST
        if not public_host:
            # Fallback construct from endpoint
            endpoint_host = settings.OSS_ENDPOINT_URL.replace("https://", "").replace("http://", "")
            public_host = f"https://{bucket.bucket_name}.{endpoint_host}"

        return f"{public_host}/{key}"


oss_service = OSSService()
