import os
import logging
from typing import List, Any
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from pydantic import PrivateAttr

from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.embeddings import BaseEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.readers.obsidian import ObsidianReader

from app import config

logger = logging.getLogger(__name__)

CHROMA_PATH = os.path.join(config.WORKSPACE_DIR, ".chroma_db")

class ChromaONNXEmbedding(BaseEmbedding):
    """
    Lightweight local embedding model using Chroma's built-in ONNX MiniLM model.
    Runs 100% offline without PyTorch or external API keys.
    """
    _ef: Any = PrivateAttr()

    def __init__(self, **kwargs: Any):
        super().__init__(model_name="all-MiniLM-L6-v2", **kwargs)
        self._ef = ONNXMiniLM_L6_V2()

    def _get_query_embedding(self, query: str) -> List[float]:
        return [float(x) for x in self._ef([query])[0]]

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        return [float(x) for x in self._ef([text])[0]]

def search_obsidian_vault(query: str, top_k: int = 3) -> str:
    """
    Perform semantic vector search across Obsidian Vault markdown notes using local ONNX embedding.
    """
    if not os.path.exists(config.OBSIDIAN_VAULT_DIR):
        return "Vault Obsidian belum memiliki berkas catatan."

    try:
        reader = ObsidianReader(input_dir=config.OBSIDIAN_VAULT_DIR)
        documents = reader.load_data()
        
        if not documents:
            return "Belum ada catatan di Obsidian Vault untuk diambil konteksnya."

        # Sanitize metadata for ChromaDB compatibility (lists like wikilinks converted to strings)
        for doc in documents:
            clean_meta = {}
            for k, v in doc.metadata.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    clean_meta[k] = v
                elif isinstance(v, list):
                    clean_meta[k] = ", ".join(str(x) for x in v)
            doc.metadata = clean_meta

        embed_model = ChromaONNXEmbedding()

        db = chromadb.PersistentClient(path=CHROMA_PATH)
        chroma_collection = db.get_or_create_collection("obsidian_second_brain")
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=embed_model
        )
        retriever = index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)

        if not nodes:
            return ""

        results = []
        for i, node in enumerate(nodes, 1):
            text_snippet = node.node.get_content()[:400]
            results.append(f"Catatan Rujukan {i}:\n{text_snippet}...")

        return "\n\n".join(results)

    except Exception as err:
        logger.warning(f"Kendala pada pencarian Obsidian Vector Engine: {err}")
        return ""

