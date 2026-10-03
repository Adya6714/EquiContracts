import pytest

from apps.api.app.core.storage import DocumentStorage


class FakeS3:
    def __init__(self) -> None:
        self.put: dict[str, object] | None = None

    def put_object(self, **kwargs):
        self.put = kwargs

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        return f"https://signed.invalid/{operation}/{Params['Key']}?ttl={ExpiresIn}"


def test_document_key_is_content_addressed_and_encrypted() -> None:
    fake = FakeS3()
    storage = DocumentStorage(client=fake)
    stored = storage.put_document(b"document bytes")

    assert stored.uri.endswith(stored.sha256)
    assert fake.put is not None
    assert fake.put["ServerSideEncryption"] == "AES256"


def test_refuses_to_sign_uri_from_another_bucket() -> None:
    storage = DocumentStorage(client=FakeS3())
    with pytest.raises(ValueError):
        storage.signed_download_url("s3://attacker-bucket/object")
