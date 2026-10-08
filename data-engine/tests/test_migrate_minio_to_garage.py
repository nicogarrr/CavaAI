from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from scripts.storage.migrate_minio_to_garage import migrate


class FakeS3:
    def __init__(self, objects: dict[str, bytes] | None = None, *, corrupt_put: bool = False):
        self.buckets = {"research": dict(objects or {})}
        self.corrupt_put = corrupt_put
        self.puts: list[str] = []

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets[bucket] = {}

    def list_objects(self, bucket, recursive=True):
        return [SimpleNamespace(object_name=k, size=len(v)) for k, v in self.buckets[bucket].items()]

    def stat_object(self, bucket, key):
        return SimpleNamespace(content_type="application/pdf")

    def get_object(self, bucket, key):
        data = self.buckets[bucket][key]
        return SimpleNamespace(read=lambda: data, close=lambda: None, release_conn=lambda: None)

    def put_object(self, bucket, key, stream, *, length, content_type):
        data = stream.read(length)
        self.puts.append(key)
        self.buckets[bucket][key] = data + b"x" if self.corrupt_put else data


SRC = {"tenant-1/MSFT/filing/a.pdf": b"AAA", "tenant-2/ASTS/filing/b.pdf": b"BBBB"}


def test_copies_and_verifies_all_objects():
    src, dst = FakeS3(SRC), FakeS3()
    dst.buckets.clear()
    report = migrate(src, dst, "research")
    assert report["ok"] and len(report["copied"]) == 2
    assert dst.buckets["research"] == SRC
    assert src.buckets["research"] == SRC  # origen intacto


def test_idempotent_second_run_skips_everything():
    src, dst = FakeS3(SRC), FakeS3(SRC)
    report = migrate(src, dst, "research")
    assert report["ok"] and not report["copied"] and len(report["skipped"]) == 2
    assert dst.puts == []


def test_corrupt_destination_is_reported_and_fails_closed():
    report = migrate(FakeS3(SRC), FakeS3(corrupt_put=True), "research")
    assert not report["ok"] and len(report["mismatch"]) == 2


def test_verify_only_reports_missing_without_writing():
    dst = FakeS3({"tenant-1/MSFT/filing/a.pdf": b"AAA"})
    report = migrate(FakeS3(SRC), dst, "research", verify_only=True)
    assert report["missing"] == ["tenant-2/ASTS/filing/b.pdf"] and not report["ok"]
    assert dst.puts == []


def test_dry_run_writes_nothing():
    dst = FakeS3()
    dst.buckets.clear()
    report = migrate(FakeS3(SRC), dst, "research", dry_run=True)
    assert len(report["copied"]) == 2 and dst.buckets == {}
