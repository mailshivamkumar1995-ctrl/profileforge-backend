from django.conf import settings
from storage.base import IStorage


def get_storage() -> IStorage:
    """Factory: returns the configured storage backend."""
    backend = getattr(settings, "STORAGE_BACKEND", "minio")
    if backend in ("s3", "minio"):
        from storage.s3_backend import S3Storage
        return S3Storage()
    elif backend == "gcs":
        from storage.gcs_backend import GCSStorage
        return GCSStorage()
    else:
        raise ValueError(f"Unknown storage backend: {backend}")


# Module-level singleton — initialized on first import
_storage_instance: IStorage | None = None


def storage() -> IStorage:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = get_storage()
    return _storage_instance
