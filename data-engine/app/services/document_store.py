from pathlib import Path
import re

from minio import Minio

from app.core.config import get_settings


class DocumentStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_root = Path("storage/raw")

    def _client(self) -> Minio:
        secure = self.settings.minio_endpoint.startswith("https://")
        endpoint = self.settings.minio_endpoint.replace("http://", "").replace("https://", "")
        return Minio(
            endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=secure,
        )

    def put_text_local(
        self,
        ticker: str,
        category: str,
        filename: str,
        text: str,
        tenant_id: int | None = None,
    ) -> str:
        directory = self._directory(ticker, category, tenant_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        path.write_text(text, encoding="utf-8")
        return str(path)

    def put_bytes_local(
        self,
        ticker: str,
        category: str,
        filename: str,
        content: bytes,
        tenant_id: int | None = None,
    ) -> str:
        directory = self._directory(ticker, category, tenant_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / self._safe_filename(filename)
        path.write_bytes(content)
        return str(path)

    def _directory(
        self, ticker: str, category: str, tenant_id: int | None
    ) -> Path:
        base = self.local_root
        if tenant_id is not None:
            base = base / self._safe_path_part(f"tenant-{tenant_id}")
        return (
            base
            / self._safe_path_part(ticker)
            / self._safe_path_part(category)
        )

    def _safe_path_part(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
        return cleaned[:120] or "unknown"

    def _safe_filename(self, value: str) -> str:
        cleaned = self._safe_path_part(value)
        if "." not in cleaned:
            return f"{cleaned}.bin"
        return cleaned
