import os
import re
import logging
from datetime import datetime
from typing import List, Any, Optional, Dict
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
        try:
            db.delete_collection("obsidian_second_brain")
        except Exception:
            pass
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
            full_path = node.node.metadata.get("file_path", "")
            file_name = node.node.metadata.get("file_name", "") or node.node.metadata.get("filename", "")
            
            # Format relative vault path without extension for WikiLink target
            rel_path = ""
            if full_path and config.OBSIDIAN_VAULT_DIR in full_path:
                rel_path = os.path.relpath(full_path, config.OBSIDIAN_VAULT_DIR)
                if rel_path.endswith(".md"):
                    rel_path = rel_path[:-3]
            elif file_name:
                rel_path = file_name[:-3] if file_name.endswith(".md") else file_name
            else:
                rel_path = f"Catatan_{i}"

            text_snippet = node.node.get_content()[:400]
            results.append(f"Catatan Rujukan {i} (WikiLink Target: [[{rel_path}]]):\n{text_snippet}...")

        return "\n\n".join(results)

    except Exception as err:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) Kendala pada pencarian Obsidian Vector Engine: {err}")
        return ""

def find_parent_concept_note(concept_topic: str) -> Optional[Dict[str, str]]:
    """
    Use LlamaIndex vector retrieval to find an existing parent concept note in the vault
    that semantically matches concept_topic for Smart Note Merging.
    Returns dict with keys: 'folder', 'filename', 'title', 'rel_path' or None if no parent note found.
    """
    if not os.path.exists(config.OBSIDIAN_VAULT_DIR):
        return None

    try:
        reader = ObsidianReader(input_dir=config.OBSIDIAN_VAULT_DIR)
        documents = reader.load_data()
        if not documents:
            return None

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
        try:
            db.delete_collection("obsidian_second_brain")
        except Exception:
            pass
        chroma_collection = db.get_or_create_collection("obsidian_second_brain")
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=embed_model
        )
        retriever = index.as_retriever(similarity_top_k=3)
        nodes = retriever.retrieve(concept_topic)

        if not nodes:
            return None

        clean_query = concept_topic.strip().lower()
        for node in nodes:
            full_path = node.node.metadata.get("file_path", "")
            file_name = node.node.metadata.get("file_name", "") or node.node.metadata.get("filename", "")
            if not file_name and full_path:
                file_name = os.path.basename(full_path)

            if not file_name or file_name.startswith("2026-") or "User_Profile" in file_name:
                continue

            clean_file_title = file_name[:-3] if file_name.endswith(".md") else file_name
            query_words = set(re.findall(r"\w+", clean_query))
            file_words = set(re.findall(r"\w+", clean_file_title.lower()))
            overlap = query_words.intersection(file_words)

            if overlap or node.score is None or (isinstance(node.score, (int, float)) and node.score > 0.3):
                folder = "Kotak Masuk"
                if full_path and config.OBSIDIAN_VAULT_DIR in full_path:
                    rel_dir = os.path.dirname(os.path.relpath(full_path, config.OBSIDIAN_VAULT_DIR))
                    if rel_dir and rel_dir != ".":
                        folder = rel_dir

                return {
                    "folder": folder,
                    "filename": file_name if file_name.endswith(".md") else f"{file_name}.md",
                    "title": clean_file_title,
                    "rel_path": f"{folder}/{clean_file_title}"
                }

        return None
    except Exception as err:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"({now_str}) Error finding parent concept note via LlamaIndex: {err}")
        return None


