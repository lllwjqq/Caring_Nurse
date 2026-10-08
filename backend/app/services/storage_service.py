import io
import uuid

from minio import Minio

from app.config import settings


class StorageService:
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(settings.minio_bucket):
                self.client.make_bucket(settings.minio_bucket)
        except Exception:
            pass

    async def upload(self, filename: str, data: io.BytesIO) -> str:
        object_name = f"{uuid.uuid4().hex}_{filename}"
        try:
            data.seek(0)
            self.client.put_object(
                settings.minio_bucket,
                object_name,
                data,
                length=-1,
                part_size=10 * 1024 * 1024,
            )
            return f"{settings.minio_bucket}/{object_name}"
        except Exception:
            return f"local/{object_name}"
