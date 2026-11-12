"""Reads a corpus of repositories and docs, then splits it into retrievable chunks."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CODE_EXT = {".py", ".java", ".scala", ".go", ".js", ".ts", ".kt", ".rb", ".sql"}
DOC_EXT = {".md", ".txt", ".rst"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", "target"}
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@dataclass
class Document:
    id: str
    path: str
    kind: str  # code | doc | incident | rca | runbook
    title: str
    text: str
    meta: dict = field(default_factory=dict)


@dataclass
class Chunk:
    id: str
    doc_id: str
    kind: str
    title: str
    text: str
    start_line: int


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def load_corpus(root: Path, max_bytes: int = 400_000) -> list[Document]:
    docs = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts) or path.stat().st_size > max_bytes:
            continue
        ext = path.suffix.lower()
        if ext not in CODE_EXT | DOC_EXT:
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(errors="ignore")
        if ext in CODE_EXT:
            docs.append(Document(rel, rel, "code", path.name, text))
            continue
        meta, body = parse_front_matter(text)
        title = meta.get("title") or next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("#")), path.stem)
        docs.append(Document(rel, rel, meta.get("type", "doc"), title, body, meta))
    return docs


_CODE_BOUNDARY = re.compile(r"^\s*(def |class |async def |public |private |protected |func |object |trait |case class )")


def chunk_document(doc: Document, max_lines: int = 60) -> list[Chunk]:
    """Code splits at function/class boundaries; prose splits at headings. Long pieces are split by length."""
    lines = doc.text.splitlines()

    def is_boundary(line: str) -> bool:
        return bool(_CODE_BOUNDARY.match(line)) if doc.kind == "code" else line.startswith("#")

    pieces, start = [], 0
    for i, line in enumerate(lines):
        if i > start and (is_boundary(line) or i - start >= max_lines):
            pieces.append((start, lines[start:i]))
            start = i
    pieces.append((start, lines[start:]))
    chunks = []
    for n, (s, body) in enumerate(p for p in pieces if "".join(p[1]).strip()):
        chunks.append(Chunk(f"{doc.id}#{n}", doc.id, doc.kind, doc.title, "\n".join(body).strip(), s + 1))
    return chunks
