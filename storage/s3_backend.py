import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from storage.base import IStorage
from core.exceptions import StorageException


class S3Storage(IStorage):
    def __init__(self):
        kwargs = {
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "region_name": settings.AWS_S3_REGION_NAME,
        }
        if settings.AWS_S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
        self._client = boto3.client("s3", **kwargs)
        self._bucket = settings.AWS_STORAGE_BUCKET_NAME

        # Separate client for pre-signed URL generation using the browser-accessible host.
        # Without this, signed URLs embed the internal Kubernetes hostname (e.g. minio:9000)
        # which the browser cannot resolve.
        external_url = getattr(settings, "AWS_S3_EXTERNAL_ENDPOINT_URL", None)
        if external_url:
            public_kwargs = {**kwargs, "endpoint_url": external_url}
            self._public_client = boto3.client("s3", **public_kwargs)
        else:
            self._public_client = self._client

    def upload(self, path: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=path,
                Body=content,
                ContentType=content_type,
            )
            return path
        except ClientError as e:
            raise StorageException(f"Upload failed: {e}") from e

    def download(self, path: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=path)
            return response["Body"].read()
        except ClientError as e:
            raise StorageException(f"Download failed: {e}") from e

    def delete(self, path: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=path)
        except ClientError:
            pass  # No-op if not found

    def get_signed_url(self, path: str, expiry_seconds: int = 3600) -> str:
        try:
            return self._public_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": path},
                ExpiresIn=expiry_seconds,
            )
        except ClientError as e:
            raise StorageException(f"Failed to generate signed URL: {e}") from e

    def exists(self, path: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=path)
            return True
        except ClientError:
            return False

    def get_public_url(self, path: str) -> str:
        region = settings.AWS_S3_REGION_NAME
        bucket = self._bucket
        external_url = getattr(settings, "AWS_S3_EXTERNAL_ENDPOINT_URL", None)
        endpoint = external_url or settings.AWS_S3_ENDPOINT_URL
        if endpoint:
            return f"{endpoint}/{bucket}/{path}"
        return f"https://{bucket}.s3.{region}.amazonaws.com/{path}"
