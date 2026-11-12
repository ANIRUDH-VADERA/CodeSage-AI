"""The index: chunks, their vectors, and a NetworkX graph linking documents, chunks and entities."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import networkx as nx

from .bm25 import BM25
from .entities import extract_entities
from .ingest import Chunk, Document, chunk_document, load_corpus
from .vectors import Embedder, HashingEmbedder, InMemoryVectorStore


class Index:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or HashingEmbedder()
        self.docs: dict[str, Document] = {}
        self.chunks: dict[str, Chunk] = {}
        self.graph = nx.Graph()
        self.vectors = InMemoryVectorStore()
        self._bm25: BM25 | None = None
        self._order: list[str] = []

    # ---- build --------------------------------------------------------------
    @classmethod
    def build(cls, root: Path, embedder: Embedder | None = None) -> Index:
        idx = cls(embedder)
        idx.add_documents(load_corpus(root))
        return idx

    def add_documents(self, docs: list[Document]) -> None:
        new_chunks = []
        for doc in docs:
            self.docs[doc.id] = doc
            self.graph.add_node(f"doc:{doc.id}", type="doc", kind=doc.kind, title=doc.title)
            for ch in chunk_document(doc):
                self.chunks[ch.id] = ch
                new_chunks.append(ch)
                self.graph.add_node(f"chunk:{ch.id}", type="chunk")
                self.graph.add_edge(f"doc:{doc.id}", f"chunk:{ch.id}", rel="contains")
                for ent in extract_entities(ch):
                    self.graph.add_node(ent, type="entity", etype=ent.split(":", 1)[0])
                    self.graph.add_edge(f"chunk:{ch.id}", ent, rel="mentions")
        if new_chunks:
            self.vectors.add([c.id for c in new_chunks], self.embedder.embed([self.search_text(c) for c in new_chunks]))
        self._bm25 = None

    @staticmethod
    def search_text(c: Chunk) -> str:
        return f"{c.title}\n{c.doc_id}\n{c.text}"

    # ---- lookups ------------------------------------------------------------
    @property
    def bm25(self) -> BM25:
        if self._bm25 is None:
            self._order = list(self.chunks)
            self._bm25 = BM25([self.search_text(self.chunks[i]) for i in self._order])
        return self._bm25

    def lexical(self, query: str) -> list[tuple[str, float]]:
        scores = self.bm25.scores(query)
        return sorted(((i, s) for i, s in zip(self._order, scores) if s > 0), key=lambda x: x[1], reverse=True)

    def entities_of(self, chunk_id: str) -> set[str]:
        return {n for n in self.graph.neighbors(f"chunk:{chunk_id}") if self.graph.nodes[n].get("type") == "entity"}

    def chunks_of(self, entity: str) -> list[str]:
        if entity not in self.graph:
            return []
        return [n.split(":", 1)[1] for n in self.graph.neighbors(entity) if n.startswith("chunk:")]

    def related_entities(self, entity: str, k: int = 8) -> list[tuple[str, int]]:
        """Entities that co-occur with this one in the same chunks, by count."""
        counts: dict[str, int] = {}
        for cid in self.chunks_of(entity):
            for other in self.entities_of(cid):
                if other != entity:
                    counts[other] = counts.get(other, 0) + 1
        return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:k]

    def top_entities(self, k: int = 10, etypes: tuple[str, ...] = ("symbol", "service", "tech", "incident")) -> list[str]:
        ents = [n for n, d in self.graph.nodes(data=True) if d.get("type") == "entity" and d["etype"] in etypes]
        return sorted(ents, key=lambda n: (-self.graph.degree(n), n))[:k]

    # ---- persistence ---------------------------------------------------------
    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "index.json").write_text(json.dumps({
            "docs": [asdict(d) for d in self.docs.values()],
            "chunks": [asdict(c) for c in self.chunks.values()],
            "vectors": dict(zip(self.vectors.ids, self.vectors.vectors)),
            "graph": {"nodes": [[n, d] for n, d in self.graph.nodes(data=True)],
                      "edges": [[a, b, d] for a, b, d in self.graph.edges(data=True)]},
        }))

    @classmethod
    def load(cls, path: Path, embedder: Embedder | None = None) -> Index:
        data = json.loads((path / "index.json").read_text())
        idx = cls(embedder)
        idx.docs = {d["id"]: Document(**d) for d in data["docs"]}
        idx.chunks = {c["id"]: Chunk(**c) for c in data["chunks"]}
        idx.vectors.add(list(data["vectors"]), list(data["vectors"].values()))
        idx.graph.add_nodes_from((n, d) for n, d in data["graph"]["nodes"])
        idx.graph.add_edges_from((a, b, d) for a, b, d in data["graph"]["edges"])
        return idx
