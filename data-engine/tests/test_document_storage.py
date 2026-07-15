from __future__ import annotations

from app.services.document_store import DocumentStore


class FakeMinio:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.objects: list[tuple[str, str, bytes, str]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return False

    def make_bucket(self, bucket: str) -> None:
        self.created.append(bucket)

    def put_object(self, bucket, object_name, stream, *, length, content_type):
        self.objects.append((bucket, object_name, stream.read(length), content_type))


def test_document_store_uses_tenant_scoped_minio_original(monkeypatch):
    store = DocumentStore()
    store.settings.app_env = "production"
    store.settings.document_storage_backend = "minio"
    fake = FakeMinio()
    monkeypatch.setattr(store, "_client", lambda: fake)

    uri = store.put_bytes(
        "msft",
        "filing",
        "../10-k.pdf",
        b"immutable-original",
        tenant_id=17,
        content_type="application/pdf",
    )

    assert uri == "minio://research/tenant-17/MSFT/filing/.._10-k.pdf"
    assert fake.created == ["research"]
    assert fake.objects == [
        ("research", "tenant-17/MSFT/filing/.._10-k.pdf", b"immutable-original", "application/pdf")
    ]


def test_document_store_rejects_unscoped_minio_write():
    store = DocumentStore()
    store.settings.app_env = "production"
    store.settings.document_storage_backend = "minio"

    try:
        store.put_bytes("MSFT", "filing", "10-k.pdf", b"raw")
    except ValueError as exc:
        assert "Tenant context" in str(exc)
    else:
        raise AssertionError("Unscoped document write should fail")


def test_document_store_rejects_local_originals_in_production():
    store = DocumentStore()
    store.settings.app_env = "production"
    store.settings.document_storage_backend = "local"

    try:
        store.put_bytes("MSFT", "filing", "10-k.pdf", b"raw", tenant_id=17)
    except RuntimeError as exc:
        assert "must use MinIO" in str(exc)
    else:
        raise AssertionError("Production must not accept local canonical originals")
