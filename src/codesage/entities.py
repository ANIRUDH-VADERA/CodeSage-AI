"""Entity extraction: the nodes that link code, docs and incidents together in the knowledge graph."""
from __future__ import annotations

import re

from .ingest import Chunk

TECH_TERMS = {
    "kafka", "postgres", "postgresql", "redis", "spark", "kubernetes", "helm", "docker", "grpc", "rest",
    "s3", "gcs", "bigquery", "pubsub", "elasticsearch", "mysql", "airflow", "terraform", "jwt", "oauth",
    "hikari", "connection pool", "retry", "timeout", "circuit breaker", "rate limit", "idempotency",
}
_TECH_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, TECH_TERMS), key=len, reverse=True)) + r")\b", re.I)
_SYMBOL_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class|func|object|trait|case class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_INCIDENT_RE = re.compile(r"\b(?:INC|RCA|SEV)-\d{2,6}\b")
_PATH_RE = re.compile(r"\b[\w-]+(?:/[\w.-]+)+\.(?:py|java|scala|go|ts|js|kt|sql|ya?ml)\b")
_SERVICE_RE = re.compile(r"\bservices/([\w-]+)/")
_CAMEL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
_CONST_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")  # config constants like HTTP_TIMEOUT


def extract_entities(chunk: Chunk) -> set[str]:
    """Typed entity ids like 'symbol:PaymentClient', 'tech:kafka', 'incident:INC-1001'."""
    text = chunk.text
    ents = {f"tech:{m.lower().replace('postgresql', 'postgres')}" for m in _TECH_RE.findall(text)}
    ents |= {f"symbol:{m}" for m in _SYMBOL_RE.findall(text) if not m.startswith("_")}
    ents |= {f"symbol:{m}" for m in _CAMEL_RE.findall(text)}
    ents |= {f"symbol:{m}" for m in _CONST_RE.findall(text)}
    ents |= {f"incident:{m}" for m in _INCIDENT_RE.findall(text)}
    ents |= {f"file:{m}" for m in _PATH_RE.findall(text)}
    for svc in _SERVICE_RE.findall(f"{chunk.doc_id}\n{text}"):
        ents.add(f"service:{svc}")
    if chunk.kind in {"incident", "rca"}:
        ents |= {f"incident:{m}" for m in _INCIDENT_RE.findall(chunk.title + " " + chunk.doc_id)}
    return ents
