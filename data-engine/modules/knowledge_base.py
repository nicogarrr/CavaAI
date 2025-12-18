"""
Knowledge Base Module - RAG Value Investing Agent
Uses ChromaDB for vector storage and retrieval

SIMPLIFICADO: Una sola colección 'knowledge' para todo
"""

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional
import os
import hashlib
from datetime import datetime

# Configuración de ChromaDB
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge_base")

# Una sola colección unificada para todo el conocimiento
MAIN_COLLECTION = "knowledge"

class KnowledgeBase:
    """
    Base de conocimiento vectorial unificada para el agente de Value Investing.
    Todo el conocimiento se almacena en una sola colección y la IA
    recupera lo más relevante automáticamente.
    """
    
    def __init__(self):
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        
        self._embedding_model = None
        self._init_collection()
    
    @property
    def embedding_model(self):
        """Carga lazy del modelo de embeddings"""
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._embedding_model
    
    def _init_collection(self):
        """Inicializa la colección principal"""
        self.collection = self.client.get_or_create_collection(
            name=MAIN_COLLECTION,
            metadata={"description": "Base de conocimiento de Value Investing"}
        )
    
    def _generate_id(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Divide el texto en chunks con overlap"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            if end < len(text):
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                cut_point = max(last_period, last_newline)
                if cut_point > chunk_size * 0.5:
                    chunk = chunk[:cut_point + 1]
                    end = start + cut_point + 1
            
            chunks.append(chunk.strip())
            start = end - overlap
        
        return [c for c in chunks if c]
    
    def add_document(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        document_id: Optional[str] = None,
        collection_name: str = None  # Ignorado, solo para compatibilidad
    ) -> Dict:
        """
        Añade un documento a la base de conocimiento unificada
        """
        chunks = self._chunk_text(content)
        embeddings = self.embedding_model.encode(chunks).tolist()
        
        base_metadata = metadata or {}
        base_metadata["added_at"] = datetime.now().isoformat()
        base_metadata["total_chunks"] = len(chunks)
        
        base_id = document_id or self._generate_id(content)
        ids = [f"{base_id}_{i}" for i in range(len(chunks))]
        
        metadatas = []
        for i, chunk in enumerate(chunks):
            chunk_meta = base_metadata.copy()
            chunk_meta["chunk_index"] = i
            chunk_meta["chunk_preview"] = chunk[:100] + "..." if len(chunk) > 100 else chunk
            metadatas.append(chunk_meta)
        
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )
        
        return {
            "success": True,
            "document_id": base_id,
            "chunks_added": len(chunks),
            "collection": MAIN_COLLECTION
        }
    
    def search(
        self,
        query: str,
        n_results: int = 10,
        collection_names: List[str] = None  # Ignorado
    ) -> List[Dict]:
        """
        Búsqueda semántica en toda la base de conocimiento
        """
        query_embedding = self.embedding_model.encode([query])[0].tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        all_results = []
        if results and results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                all_results.append({
                    "content": doc,
                    "score": 1 - results['distances'][0][i] if results.get('distances') else 0,
                    "metadata": results['metadatas'][0][i] if results.get('metadatas') else {}
                })
        
        return all_results
    
    def get_context_for_analysis(self, symbol: str, company_name: str) -> str:
        """
        Obtiene contexto relevante de TODA la base de conocimiento
        para analizar una empresa
        """
        # Búsqueda amplia con múltiples queries
        queries = [
            f"{symbol} {company_name}",
            "criterios inversión valoración ROIC margen",
            f"análisis {company_name} value investing"
        ]
        
        all_context = []
        seen_content = set()
        
        for query in queries:
            results = self.search(query=query, n_results=5)
            for r in results:
                # Evitar duplicados
                content_key = r['content'][:100]
                if content_key not in seen_content:
                    seen_content.add(content_key)
                    all_context.append(r['content'])
        
        if all_context:
            return "## 📚 Mi Base de Conocimiento Personal:\n\n" + "\n\n---\n\n".join(all_context[:8])
        return ""
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas de la base de conocimiento"""
        count = self.collection.count()
        return {
            "total_chunks": count,
            "collection": MAIN_COLLECTION
        }
    
    def delete_document(self, document_id: str, collection_name: str = None) -> bool:
        """Elimina un documento y todos sus chunks"""
        try:
            # Buscar todos los chunks que empiezan con este document_id
            all_data = self.collection.get()
            ids_to_delete = [
                id for id in all_data['ids'] 
                if id.startswith(document_id)
            ]
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
            return True
        except Exception as e:
            print(f"Error eliminando documento: {e}")
            return False
    
    def list_documents(self, limit: int = 100, collection_name: str = None) -> List[Dict]:
        """Lista todos los documentos"""
        try:
            # Obtener TODOS los chunks para agrupar correctamente
            total = self.collection.count()
            results = self.collection.get(limit=max(total, 1000))
            
            # Agrupar por documento original
            docs = {}
            for i, id in enumerate(results.get('ids', [])):
                # El ID es "hash_chunkIndex" - extraer el hash base
                doc_id = id.rsplit('_', 1)[0]
                meta = results['metadatas'][i] if results.get('metadatas') else {}
                doc_content = results['documents'][i] if results.get('documents') else ""
                
                if doc_id not in docs:
                    docs[doc_id] = {
                        "id": doc_id,
                        "title": meta.get("title", "Sin título"),
                        "added_at": meta.get("added_at", ""),
                        "chunks": meta.get("total_chunks", 1),
                        "preview": doc_content[:200] if doc_content else meta.get("chunk_preview", "")[:200]
                    }
            
            # Ordenar por fecha y limitar
            sorted_docs = sorted(docs.values(), key=lambda x: x.get("added_at", ""), reverse=True)
            return sorted_docs[:limit]
        except Exception as e:
            print(f"Error listando documentos: {e}")
            return []
    
    def get_all_content(self, limit: int = 50) -> str:
        """Devuelve todo el contenido para visualización"""
        results = self.collection.get(limit=limit)
        if results and results['documents']:
            return "\n\n---\n\n".join(results['documents'])
        return ""


# Singleton global
_kb_instance: Optional[KnowledgeBase] = None

def get_knowledge_base() -> KnowledgeBase:
    """Obtiene la instancia singleton de la base de conocimiento"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance

def reset_knowledge_base():
    """Resetea el singleton para recargar configuración"""
    global _kb_instance
    _kb_instance = None
