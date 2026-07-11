"""Storage-provider abstraction for local development and Alibaba OSS."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
from pathlib import Path
from urllib.parse import quote


class StorageError(RuntimeError):
    pass


class StorageProvider(ABC):
    name: str

    @abstractmethod
    def create_upload_url(self, key: str, mime_type: str, expires_in: int) -> tuple[str, dict[str, str]]: ...

    @abstractmethod
    def download_url(self, key: str, *, public: bool, expires_in: int) -> str: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def checksum(self, key: str) -> str: ...

    @abstractmethod
    def put(self, key: str, data: bytes) -> None: ...


class LocalStorageProvider(StorageProvider):
    name = "local"

    def __init__(self, root: str, public_base_url: str, signing_secret: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_base_url = public_base_url.rstrip("/")
        self.secret = signing_secret.encode()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("Invalid storage key")
        return path

    def create_upload_url(self, key: str, mime_type: str, expires_in: int) -> tuple[str, dict[str, str]]:
        return self._signed_url(key, "upload", expires_in), {"Content-Type": mime_type}

    def download_url(self, key: str, *, public: bool, expires_in: int) -> str:
        if public:
            return f"{self.public_base_url}/{quote(key)}"
        return self._signed_url(key, "download", expires_in)

    def _signed_url(self, key: str, operation: str, expires_in: int) -> str:
        expires = int((datetime.now(UTC) + timedelta(seconds=expires_in)).timestamp())
        signature = hmac.new(self.secret, f"{operation}:{key}:{expires}".encode(), sha256).hexdigest()
        return f"{self.public_base_url}/{operation}/{quote(key)}?expires={expires}&signature={signature}"

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def checksum(self, key: str) -> str:
        digest = sha256()
        with self._path(key).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class OSSStorageProvider(StorageProvider):
    name = "oss"

    def __init__(self, endpoint: str, bucket: str, access_key_id: str, access_key_secret: str) -> None:
        if not all((endpoint, bucket, access_key_id, access_key_secret)):
            raise StorageError("OSS configuration is incomplete")
        import oss2  # type: ignore[import-untyped]

        self.bucket = oss2.Bucket(oss2.Auth(access_key_id, access_key_secret), endpoint, bucket)

    def create_upload_url(self, key: str, mime_type: str, expires_in: int) -> tuple[str, dict[str, str]]:
        return str(self.bucket.sign_url("PUT", key, expires_in, headers={"Content-Type": mime_type})), {"Content-Type": mime_type}

    def download_url(self, key: str, *, public: bool, expires_in: int) -> str:
        del public
        return str(self.bucket.sign_url("GET", key, expires_in))

    def exists(self, key: str) -> bool:
        return bool(self.bucket.object_exists(key))

    def checksum(self, key: str) -> str:
        digest = sha256()
        result = self.bucket.get_object(key)
        for chunk in result:
            digest.update(chunk)
        return digest.hexdigest()

    def put(self, key: str, data: bytes) -> None:
        self.bucket.put_object(key, data)


__all__ = ["LocalStorageProvider", "OSSStorageProvider", "StorageError", "StorageProvider"]
