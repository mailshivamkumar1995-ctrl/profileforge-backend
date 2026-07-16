from django.conf import settings
from storage.base import IStorage
from core.exceptions import StorageException


class GCSStorage(IStorage):
    """Google Cloud Storage backend."""

    def __init__(self):
        from google.cloud import storage as gcs
        self._client = gcs.Client()
        self._bucket_name = getattr(settings, "GCS_BUCKET_NAME", "profileforge-prod")
        self._bucket = self._client.bucket(self._bucket_name)

    def upload(self, path: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        try:
            blob = self._bucket.blob(path)
            blob.upload_from_string(content, content_type=content_type)
            return path
        except Exception as e:
            raise StorageException(f"GCS upload failed: {e}") from e

    def download(self, path: str) -> bytes:
        try:
            blob = self._bucket.blob(path)
            return blob.download_as_bytes()
        except Exception as e:
            raise StorageException(f"GCS download failed: {e}") from e

    def delete(self, path: str) -> None:
        try:
            blob = self._bucket.blob(path)
            blob.delete()
        except Exception:
            pass

    def get_signed_url(self, path: str, expiry_seconds: int = 3600) -> str:
        from datetime import timedelta
        try:
            blob = self._bucket.blob(path)
            return blob.generate_signed_url(
                expiration=timedelta(seconds=expiry_seconds),
                method="GET",
                version="v4",
            )
        except Exception as e:
            raise StorageException(f"GCS signed URL failed: {e}") from e

    def exists(self, path: str) -> bool:
        return self._bucket.blob(path).exists()

    def get_public_url(self, path: str) -> str:
        return f"https://storage.googleapis.com/{self._bucket_name}/{path}"
