from __future__ import annotations

import argparse
import sys
import tempfile
from importlib import resources
from pathlib import Path

from .answer import ask, build_wiki, wiki_page
from .guardrail import review
from .index import Index
from .llm import default_llm


def print_answer(index: Index, question: str) -> None:
    a = ask(index, question, default_llm())
    print(f"\nQ: {question}\n{a.text}")
    for n, (src, hit) in enumerate(zip(a.sources, a.hits), 1):
        print(f"  [{n}] {src}  (via {', '.join(hit.via)})")


def print_alerts(alerts) -> None:
    for a in alerts:
        print(f"  {a.severity.upper():<6} {a.kind:<22} {a.file}: {a.message}")
        for e in a.evidence:
            print(f"         {e}")


def cmd_index(args) -> int:
    idx = Index.build(Path(args.corpus))
    idx.save(Path(args.out))
    print(f"Indexed {len(idx.docs)} documents, {len(idx.chunks)} chunks, {idx.graph.number_of_nodes()} graph nodes -> {args.out}")
    return 0


def cmd_ask(args) -> int:
    print_answer(Index.load(Path(args.index)), args.question)
    return 0


def cmd_wiki(args) -> int:
    pages = build_wiki(Index.load(Path(args.index)), Path(args.out), args.top, default_llm())
    print(f"Wrote {len(pages)} pages to {args.out}")
    return 0


def cmd_guardrail(args) -> int:
    alerts = review(Index.load(Path(args.index)), Path(args.diff).read_text())
    print_alerts(alerts)
    return 1 if any(a.severity == "high" for a in alerts) else 0


def cmd_demo(_args) -> int:
    data = resources.files("codesage").joinpath("data")
    with resources.as_file(data) as d:
        idx = Index.build(Path(d) / "demo_corpus")
        diff = (Path(d) / "risky.diff").read_text()
    print(f"Indexed {len(idx.docs)} documents -> {len(idx.chunks)} chunks, "
          f"{idx.graph.number_of_nodes()} graph nodes, {idx.graph.number_of_edges()} edges")
    print("Top entities:", ", ".join(e.split(":", 1)[1] for e in idx.top_entities(8)))

    print_answer(idx, "why did payments time out and what is the safe HTTP timeout?")
    print_answer(idx, "when should the ledger writer commit kafka offsets?")

    print("\n--- wiki page for PaymentClient ---")
    print(wiki_page(idx, "symbol:PaymentClient"))
    with tempfile.TemporaryDirectory() as tmp:
        print(f"(built {len(build_wiki(idx, Path(tmp)))} wiki pages)")

    print("\n--- GuardRail review of risky.diff ---")
    print_alerts(review(idx, diff))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="codesage")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("index", help="index a folder of repos and docs")
    s.add_argument("corpus")
    s.add_argument("--out", default=".codesage")
    s.set_defaults(fn=cmd_index)
    s = sub.add_parser("ask")
    s.add_argument("question")
    s.add_argument("--index", default=".codesage")
    s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("wiki", help="generate cited wiki pages for the most connected entities")
    s.add_argument("--index", default=".codesage")
    s.add_argument("--out", default="wiki")
    s.add_argument("--top", type=int, default=15)
    s.set_defaults(fn=cmd_wiki)
    s = sub.add_parser("guardrail", help="review a unified diff against incident history (exit 1 on high severity)")
    s.add_argument("diff")
    s.add_argument("--index", default=".codesage")
    s.set_defaults(fn=cmd_guardrail)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
