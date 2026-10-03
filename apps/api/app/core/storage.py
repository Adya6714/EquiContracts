"""Private, content-addressed document storage."""

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol, cast

import boto3  # type: ignore[import-untyped]

from .config import get_settings


@dataclass(frozen=True)
class StoredDocument:
    uri: str
    sha256: str


class S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> Any: ...

    def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str: ...


class DocumentStorage:
    def __init__(self, client: S3Client | None = None) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = client or cast(
            S3Client,
            boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
            ),
        )

    def put_document(self, content: bytes) -> StoredDocument:
        digest = hashlib.sha256(content).hexdigest()
        key = f"sha256/{digest[:2]}/{digest}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ServerSideEncryption="AES256",
        )
        return StoredDocument(uri=f"s3://{self.bucket}/{key}", sha256=digest)

    def signed_download_url(self, uri: str, expires_seconds: int = 300) -> str:
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix):
            raise ValueError("storage URI is outside the configured bucket")
        key = uri.removeprefix(prefix)
        if not key or ".." in key:
            raise ValueError("invalid storage URI")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
