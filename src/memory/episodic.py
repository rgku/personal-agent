import uuid
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..config import settings

CHROMA_DIR = str(Path(settings.data_dir) / "chromadb")


class EpisodicMemory:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._coll = None
        self._failed = False

    def _ensure(self):
        if self._coll is not None:
            return True
        if self._failed:
            return False
        try:
            self._client = chromadb.PersistentClient(
                path=CHROMA_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._coll = self._client.get_or_create_collection(
                name="episodic_memory",
                metadata={"hnsw:space": "cosine"},
            )
            return True
        except Exception:
            self._coll = None
            self._failed = True
            return False

    def store(self, text: str, memory_type: str = "interaction", tags: str = ""):
        if not self._ensure():
            return
        try:
            self._coll.add(
                ids=[str(uuid.uuid4())],
                documents=[text],
                metadatas=[
                    {
                        "user_id": self.user_id,
                        "type": memory_type,
                        "tags": tags,
                    }
                ],
            )
        except Exception:
            pass

    def search(self, query: str, n: int = 5) -> list[str]:
        if not self._ensure():
            return []
        try:
            if self._coll.count() == 0:
                return []
            results = self._coll.query(
                query_texts=[query],
                n_results=min(n, self._coll.count()),
                where={"user_id": self.user_id},
            )
            return results.get("documents", [[]])[0]
        except Exception:
            return []

    def recent(self, n: int = 3, memory_type: str = "interaction") -> list[str]:
        if not self._ensure():
            return []
        try:
            if self._coll.count() == 0:
                return []
            results = self._coll.get(
                where={
                    "$and": [
                        {"user_id": self.user_id},
                        {"type": memory_type},
                    ]
                },
                limit=n,
            )
            return results.get("documents", [])
        except Exception:
            return []
