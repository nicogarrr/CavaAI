from qdrant_client import QdrantClient

from app.core.config import get_settings


class RAGIndex:
    collection_name = "portfolio_research_documents"

    def __init__(self) -> None:
        self.settings = get_settings()

    def client(self) -> QdrantClient:
        return QdrantClient(url=self.settings.qdrant_url)

    def status(self) -> dict:
        try:
            collections = self.client().get_collections()
            return {"configured": True, "collections": [c.name for c in collections.collections]}
        except Exception as exc:
            return {"configured": False, "error": str(exc)}

