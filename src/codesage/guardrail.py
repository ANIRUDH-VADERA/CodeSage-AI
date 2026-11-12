"""GuardRail: reviews a diff against the organisation's incident history and a few risky-change rules."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .entities import extract_entities
from .index import Index
from .ingest import Chunk
from .retrieve import retrieve

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class FileChange:
    path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


@dataclass
class Alert:
    severity: str
    kind: str
    file: str
    message: str
    evidence: list[str] = field(default_factory=list)


def parse_diff(diff: str) -> list[FileChange]:
    files: list[FileChange] = []
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            files.append(FileChange(path[2:] if path.startswith("b/") else path))
        elif files and line.startswith("+") and not line.startswith("+++"):
            files[-1].added.append(line[1:])
        elif files and line.startswith("-") and not line.startswith("---"):
            files[-1].removed.append(line[1:])
    return [f for f in files if f.path != "/dev/null"]


_NUM_SETTING = re.compile(r"(?i)\b([\w.]*(timeout|retries|retry|pool[_.]?size|max[_.]?connections|ttl|batch[_.]?size)[\w.]*)\s*[=:]\s*([\d.]+)")
_DEP_FILES = re.compile(r"(requirements.*\.txt|pyproject\.toml|package\.json|build\.sbt|pom\.xml|go\.mod)$")
_ERROR_HANDLING = re.compile(r"^\s*(except\b|catch\b|\.recover|\.catch\(|rescue\b)")


def rule_alerts(change: FileChange) -> list[Alert]:
    alerts = []
    old = {m.group(1).lower(): m.group(3) for ln in change.removed for m in _NUM_SETTING.finditer(ln)}
    for ln in change.added:
        for m in _NUM_SETTING.finditer(ln):
            key, new = m.group(1).lower(), m.group(3)
            if key in old and old[key] != new:
                alerts.append(Alert("medium", "config-change", change.path, f"`{m.group(1)}` changed {old[key]} -> {new}", [ln.strip()]))
    if _DEP_FILES.search(change.path) and change.added:
        alerts.append(Alert("low", "dependency-change", change.path, "Dependency manifest changed; check release notes", change.added[:3]))
    dropped = [ln for ln in change.removed if _ERROR_HANDLING.match(ln)]
    if len(dropped) > sum(1 for ln in change.added if _ERROR_HANDLING.match(ln)):
        alerts.append(Alert("high", "error-handling-removed", change.path, "Error handling was removed", [d.strip() for d in dropped]))
    if change.path.endswith(".sql") and any(re.search(r"(?i)\b(drop|alter)\s+table", ln) for ln in change.added):
        alerts.append(Alert("high", "schema-change", change.path, "Destructive schema change", change.added[:3]))
    return alerts


def incident_alerts(index: Index, change: FileChange, min_shared: int = 1) -> list[Alert]:
    """Finds past incidents that look like this change: same code symbols or files, or similar text."""
    probe = Chunk("diff", change.path, "code", change.path, "\n".join(change.added + change.removed), 1)
    probe_ents = {e for e in extract_entities(probe) if e.split(":", 1)[0] in {"symbol", "tech", "file"}}
    probe_ents.add(f"file:{change.path}")
    query = f"{change.path} {' '.join(e.split(':', 1)[1] for e in probe_ents)} " + " ".join(change.added)[:1000]
    alerts = []
    for hit in retrieve(index, query, k=4, kinds={"incident", "rca"}):
        doc = index.docs[index.chunks[hit.chunk_id].doc_id]
        shared = sorted(e.split(":", 1)[1] for e in probe_ents & index.entities_of(hit.chunk_id))
        if len(shared) >= min_shared:
            sev = "high" if len(shared) >= 2 else "medium"
            alerts.append(Alert(sev, "similar-incident", change.path, f"Resembles {doc.title}",
                                [f"shared: {', '.join(shared[:6])}", f"source: {doc.path}"]))
    seen, unique = set(), []
    for a in alerts:
        if a.message not in seen:
            seen.add(a.message)
            unique.append(a)
    return unique


def review(index: Index, diff: str) -> list[Alert]:
    alerts = []
    for change in parse_diff(diff):
        alerts += rule_alerts(change) + incident_alerts(index, change)
    return sorted(alerts, key=lambda a: (SEVERITY_ORDER[a.severity], a.file))
