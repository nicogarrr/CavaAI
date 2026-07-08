from contextlib import contextmanager
from typing import Any

from app.core.config import get_settings


class LangfuseTracer:
    def __init__(self) -> None:
        self.settings = get_settings()

    @contextmanager
    def workflow(self, name: str, metadata: dict[str, Any] | None = None):
        if not self.settings.langfuse_enabled:
            yield None
            return

        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
            )
            trace = client.trace(name=name, metadata=metadata or {})
            yield trace
            client.flush()
        except Exception:
            yield None

