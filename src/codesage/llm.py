"""Answer synthesis. The default is extractive and offline; an OpenAI-compatible model can be plugged in."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol

SYSTEM = ("You answer questions about a software organisation using ONLY the numbered context. "
          "Cite sources like [1]. If the context does not contain the answer, say so.")


class LLM(Protocol):
    def complete(self, question: str, context: list[tuple[str, str]]) -> str: ...


class ExtractiveLLM:
    """Stitches the most relevant lines from each source. Deterministic, which keeps tests and demos honest."""

    def complete(self, question: str, context: list[tuple[str, str]]) -> str:
        q = {w.strip("?.,!") for w in question.lower().split() if len(w) > 3}
        out = []
        for n, (_source, text) in enumerate(context, 1):
            lines = [ln.strip().strip('"').strip() for ln in text.splitlines()]
            lines = [ln for ln in lines if ln and not ln.startswith(("#", "from ", "import ", "@"))]
            scored = [(sum(w in ln.lower() for w in q), i, ln) for i, ln in enumerate(lines)]
            best = [ln for s, _, ln in sorted(scored, key=lambda x: (-x[0], x[1]))[:2] if s > 0]
            if best:
                out.append(f"{' '.join(best)[:300]} [{n}]")
        return "\n".join(out) if out else "The indexed sources don't answer this."


class OpenAICompatibleLLM:
    """Any /chat/completions endpoint (OpenAI, Azure-compatible gateways, local vLLM/Ollama)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("CODESAGE_MODEL", "gpt-4o-mini")
        self.base = os.environ.get("CODESAGE_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.key = os.environ["CODESAGE_API_KEY"]

    def complete(self, question: str, context: list[tuple[str, str]]) -> str:
        ctx = "\n\n".join(f"[{n}] {src}\n{text[:2000]}" for n, (src, text) in enumerate(context, 1))
        body = {"model": self.model, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {question}"}]}
        req = urllib.request.Request(f"{self.base}/chat/completions", json.dumps(body).encode(),
                                     headers={"authorization": f"Bearer {self.key}", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]


def default_llm() -> LLM:
    return OpenAICompatibleLLM() if os.environ.get("CODESAGE_API_KEY") else ExtractiveLLM()
