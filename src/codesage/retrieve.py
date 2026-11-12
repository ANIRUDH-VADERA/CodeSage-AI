"""Hybrid retrieval: BM25 + vectors fused with Reciprocal Rank Fusion, then expanded through the entity graph."""
from __future__ import annotations

from dataclasses import dataclass, field

from .index import Index

RRF_K = 60


@dataclass
class Hit:
    chunk_id: str
    score: float
    via: list[str] = field(default_factory=list)  # lexical / vector / graph:<entity>


def rrf(rankings: dict[str, list[str]]) -> dict[str, tuple[float, list[str]]]:
    fused: dict[str, tuple[float, list[str]]] = {}
    for name, ids in rankings.items():
        for rank, cid in enumerate(ids):
            score, via = fused.get(cid, (0.0, []))
            fused[cid] = (score + 1 / (RRF_K + rank + 1), via + [name])
    return fused


def retrieve(index: Index, query: str, k: int = 6, kinds: set[str] | None = None, graph_hops: bool = True) -> list[Hit]:
    allowed = {cid for cid, c in index.chunks.items() if kinds is None or c.kind in kinds}
    lexical = [cid for cid, _ in index.lexical(query) if cid in allowed][:30]
    vector = [cid for cid, s in index.vectors.search(index.embedder.embed([query])[0], 30, allowed) if s > 0.05]
    fused = rrf({"lexical": lexical, "vector": vector})

    if graph_hops and fused:
        # Pull in chunks that share specific entities (symbols, incidents, files) with the best seeds.
        seeds = sorted(fused, key=lambda c: fused[c][0], reverse=True)[:3]
        for seed in seeds:
            for ent in index.entities_of(seed):
                if ent.split(":", 1)[0] not in {"symbol", "incident", "file"}:
                    continue
                for cid in index.chunks_of(ent):
                    if cid in allowed and cid not in fused:
                        fused[cid] = (0.5 * fused[seed][0], [f"graph:{ent}"])

    ranked = sorted(fused.items(), key=lambda x: x[1][0], reverse=True)[:k]
    return [Hit(cid, round(score, 5), via) for cid, (score, via) in ranked]
