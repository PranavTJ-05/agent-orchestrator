from __future__ import annotations

import os
from typing import Any

import chromadb
from chromadb.config import Settings

from ..core.memory import Memory


class HashEmbeddingFunction(chromadb.EmbeddingFunction):
    """Offline bag-of-words hashing embedding; avoids Chroma's 79MB model download."""

    DIM = 256

    def __init__(self) -> None:
        pass

    def __call__(self, input: list[str]) -> list[list[float]]:
        import hashlib
        import math
        import re

        vectors = []
        for text in input:
            vec = [0.0] * self.DIM
            for token in re.findall(r"\w+", text.lower()):
                vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    @staticmethod
    def name() -> str:
        return "hash-embedding"


class ChromaMemory(Memory):
    def __init__(self, persist_dir: str | None = None) -> None:
        persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR") or "./chroma_db"
        self._client = chromadb.Client(Settings(
            persist_directory=persist_dir,
            anonymized_telemetry=False,
        ))
        # MEMORY_EMBEDDING=hash uses the offline embedding instead of Chroma's default model
        self._embedding_fn = (
            HashEmbeddingFunction() if os.getenv("MEMORY_EMBEDDING") == "hash" else None
        )
        self._collection = self._client.get_or_create_collection(
            name="agent_memory",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embedding_fn,
        )

    async def save(self, key: str, value: Any) -> None:
        import json
        text = json.dumps(value) if not isinstance(value, str) else value
        self._collection.add(
            ids=[key],
            documents=[text],
            metadatas=[{"key": key}],
        )

    async def load(self, key: str) -> Any | None:
        result = self._collection.get(ids=[key])
        if result and result["documents"]:
            return result["documents"][0]
        return None

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        result = self._collection.query(
            query_texts=[query],
            n_results=limit,
        )
        items = []
        if result["documents"]:
            for i, doc in enumerate(result["documents"][0]):
                items.append({
                    "key": result["ids"][0][i],
                    "value": doc,
                    "distance": result["distances"][0][i] if result.get("distances") else None,
                })
        return items

    async def delete(self, key: str) -> None:
        self._collection.delete(ids=[key])

    async def clear(self) -> None:
        self._client.delete_collection(name="agent_memory")
        self._collection = self._client.get_or_create_collection(
            name="agent_memory", embedding_function=self._embedding_fn
        )
