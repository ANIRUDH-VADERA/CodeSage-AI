"""Okapi BM25 for the lexical half of hybrid retrieval."""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "be", "how",
    "what", "why", "when", "do", "does", "it", "this", "that", "with", "by", "as", "at", "from",
})


def tokenize(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = [Counter(tokenize(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(1, len(docs))
        df = Counter(w for t in self.tf for w in t)
        self.idf = {w: math.log(1 + (len(docs) - n + 0.5) / (n + 0.5)) for w, n in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        res = []
        for tf, dl in zip(self.tf, self.len):
            s = 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avg or 1)))
            res.append(s)
        return res
