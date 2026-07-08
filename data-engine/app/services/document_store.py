from pathlib import Path

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

    def put_text_local(self, ticker: str, category: str, filename: str, text: str) -> str:
        directory = self.local_root / ticker / category
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        path.write_text(text, encoding="utf-8")
        return str(path)

