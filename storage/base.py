from abc import ABC, abstractmethod


class IStorage(ABC):
    """Storage provider abstraction. All implementations must satisfy this interface."""

    @abstractmethod
    def upload(self, path: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload content to storage. Returns the storage path."""
        ...

    @abstractmethod
    def download(self, path: str) -> bytes:
        """Download content from storage. Raises StorageException if not found."""
        ...

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete object at path. No-ops if not found."""
        ...

    @abstractmethod
    def get_signed_url(self, path: str, expiry_seconds: int = 3600) -> str:
        """Generate a time-limited signed download URL."""
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if an object exists at path."""
        ...

    @abstractmethod
    def get_public_url(self, path: str) -> str:
        """Get the permanent public URL for a publicly accessible object."""
        ...
