"""Embeddings and vector stores behind small interfaces, so the pipeline runs offline and swaps in real models."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9_]+")


def _split_identifiers(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)  # camelCase -> camel Case
    return _TOKEN.findall(text.lower().replace("_", " "))


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Deterministic feature-hashing embedder (unigrams + bigrams). No model download, good enough for tests and demos."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        toks = _split_identifiers(text)
        for feat in toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])]:
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class OpenAICompatibleEmbedder:
    """Any OpenAI-compatible /embeddings endpoint. Reads CODESAGE_API_KEY and CODESAGE_BASE_URL."""

    def __init__(self, model: str = "text-embedding-3-small", dim: int = 1536) -> None:
        self.model, self.dim = model, dim
        self.base = os.environ.get("CODESAGE_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.key = os.environ["CODESAGE_API_KEY"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i in range(0, len(texts), 64):
            req = urllib.request.Request(
                f"{self.base}/embeddings", json.dumps({"model": self.model, "input": texts[i:i + 64]}).encode(),
                headers={"authorization": f"Bearer {self.key}", "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                out += [d["embedding"] for d in json.loads(r.read())["data"]]
        return out


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalised


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.vectors: list[list[float]] = []

    def add(self, ids: list[str], vectors: list[list[float]]) -> None:
        self.ids += ids
        self.vectors += vectors

    def search(self, vector: list[float], k: int = 10, allowed: set[str] | None = None) -> list[tuple[str, float]]:
        scored = [(i, cosine(vector, v)) for i, v in zip(self.ids, self.vectors) if allowed is None or i in allowed]
        return sorted(scored, key=lambda x: x[1], reverse=True)[:k]


class ChromaVectorStore:
    """Persistent store backed by ChromaDB (pip install 'codesage[chroma]')."""

    def __init__(self, path: str, collection: str = "codesage") -> None:
        import chromadb  # noqa: PLC0415 - optional dependency

        self._col = chromadb.PersistentClient(path=path).get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})

    def add(self, ids: list[str], vectors: list[list[float]]) -> None:
        self._col.upsert(ids=ids, embeddings=vectors)

    def search(self, vector: list[float], k: int = 10, allowed: set[str] | None = None) -> list[tuple[str, float]]:
        res = self._col.query(query_embeddings=[vector], n_results=k * 3 if allowed else k)
        pairs = [(i, 1 - d) for i, d in zip(res["ids"][0], res["distances"][0])]
        return [p for p in pairs if allowed is None or p[0] in allowed][:k]
