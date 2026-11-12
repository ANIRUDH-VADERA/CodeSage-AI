"""Question answering and wiki generation on top of the index."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .index import Index
from .llm import LLM, ExtractiveLLM
from .retrieve import Hit, retrieve


@dataclass
class Answer:
    question: str
    text: str
    sources: list[str]
    hits: list[Hit]


def cite(index: Index, hit: Hit) -> str:
    c = index.chunks[hit.chunk_id]
    return f"{c.doc_id}:{c.start_line}"


def ask(index: Index, question: str, llm: LLM | None = None, k: int = 5) -> Answer:
    hits = retrieve(index, question, k=k)
    context = [(cite(index, h), index.chunks[h.chunk_id].text) for h in hits]
    text = (llm or ExtractiveLLM()).complete(question, context) if hits else "Nothing in the index matches this question."
    return Answer(question, text, [c for c, _ in context], hits)


def slug(entity: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", entity.lower()).strip("-")


def wiki_page(index: Index, entity: str, llm: LLM | None = None) -> str:
    """One page per entity: definition, where it is used, related entities, and incidents, every line cited."""
    etype, name = entity.split(":", 1)
    chunk_ids = index.chunks_of(entity)
    by_kind: dict[str, list[str]] = {}
    for cid in chunk_ids:
        by_kind.setdefault(index.chunks[cid].kind, []).append(cid)

    lines = [f"# {name}", "", (f"*{etype}* · mentioned in {len(chunk_ids)} chunks across "
                                 f"{len({index.chunks[c].doc_id for c in chunk_ids})} documents"), ""]
    defining = [c for c in by_kind.get("code", []) if re.search(rf"(class|def|object|trait|func)\s+{re.escape(name)}\b",
                                                                 index.chunks[c].text)]
    overview_ids = (defining or chunk_ids)[:3]
    if overview_ids:
        ctx = [(f"{index.chunks[c].doc_id}:{index.chunks[c].start_line}", index.chunks[c].text) for c in overview_ids]
        lines += ["## Overview", (llm or ExtractiveLLM()).complete(f"What is {name}?", ctx), ""]
        lines += [f"[{n}]: {src}" for n, (src, _) in enumerate(ctx, 1)] + [""]
    used = sorted({index.chunks[c].doc_id for c in by_kind.get("code", [])})
    if used:
        lines += ["## Where it appears in code", *[f"- `{p}`" for p in used], ""]
    incidents = sorted({index.chunks[c].doc_id for k in ("incident", "rca") for c in by_kind.get(k, [])})
    if incidents:
        lines += ["## Incidents and RCAs", *[f"- {index.docs[d].title} (`{d}`)" for d in incidents], ""]
    related = index.related_entities(entity)
    if related:
        lines += ["## Related", *[f"- [{e.split(':', 1)[1]}]({slug(e)}.md) · {e.split(':', 1)[0]} · "
                                  f"{n} shared chunk{'s' if n > 1 else ''}" for e, n in related], ""]
    return "\n".join(lines)


def build_wiki(index: Index, out: Path, k: int = 15, llm: LLM | None = None) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    entities = index.top_entities(k)
    for ent in entities:
        p = out / f"{slug(ent)}.md"
        p.write_text(wiki_page(index, ent, llm))
        written.append(p)
    toc = ["# Engineering wiki", "", *[f"- [{e.split(':', 1)[1]}]({slug(e)}.md) · {e.split(':', 1)[0]}" for e in entities]]
    (out / "index.md").write_text("\n".join(toc) + "\n")
    return written
