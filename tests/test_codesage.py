import tempfile
import unittest
from importlib import resources
from pathlib import Path

from codesage.answer import ask, build_wiki, wiki_page
from codesage.entities import extract_entities
from codesage.guardrail import parse_diff, review, rule_alerts
from codesage.index import Index
from codesage.ingest import Chunk, Document, chunk_document, parse_front_matter
from codesage.retrieve import retrieve, rrf
from codesage.vectors import HashingEmbedder, cosine

DATA = Path(str(resources.files("codesage").joinpath("data")))


class IngestTests(unittest.TestCase):
    def test_front_matter(self):
        meta, body = parse_front_matter("---\ntype: incident\ntitle: X\n---\n# X\nbody")
        self.assertEqual(meta, {"type": "incident", "title": "X"})
        self.assertTrue(body.startswith("# X"))

    def test_code_chunks_split_at_definitions(self):
        doc = Document("a.py", "a.py", "code", "a.py", "import os\n\nclass A:\n    pass\n\ndef b():\n    return 1\n")
        chunks = chunk_document(doc)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[1].text.startswith("class A"))
        self.assertEqual(chunks[2].start_line, 6)


class EntityTests(unittest.TestCase):
    def test_extracts_typed_entities(self):
        c = Chunk("services/payments/x.py#0", "services/payments/x.py", "code", "x.py",
                  "class PaymentClient:\n    timeout = HTTP_TIMEOUT  # see INC-1001 and services/payments/settings.py\n", 1)
        ents = extract_entities(c)
        for e in ("symbol:PaymentClient", "symbol:HTTP_TIMEOUT", "incident:INC-1001", "tech:timeout",
                  "service:payments", "file:services/payments/settings.py"):
            self.assertIn(e, ents)


class VectorTests(unittest.TestCase):
    def test_hashing_embedder_is_normalised_and_similarity_tracks_overlap(self):
        e = HashingEmbedder(256)
        a, b, c = e.embed(["kafka consumer offsets commit", "commit kafka consumer offsets", "css button colour"])
        self.assertAlmostEqual(cosine(a, a), 1.0, places=6)
        self.assertGreater(cosine(a, b), cosine(a, c))

    def test_rrf_rewards_agreement(self):
        fused = rrf({"lexical": ["x", "y"], "vector": ["y", "z"]})
        self.assertEqual(max(fused, key=lambda k: fused[k][0]), "y")


class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = Index.build(DATA / "demo_corpus")

    def test_retrieval_finds_the_incident(self):
        hits = retrieve(self.idx, "payment timeouts after the timeout was lowered", kinds={"incident"})
        self.assertEqual(self.idx.chunks[hits[0].chunk_id].doc_id, "incidents/INC-1001.md")

    def test_answer_cites_sources(self):
        a = ask(self.idx, "when should kafka offsets be committed?")
        self.assertTrue(any("INC-1002" in s or "writer.py" in s for s in a.sources))
        self.assertIn("[1]", a.text)

    def test_graph_links_code_to_incidents(self):
        related = dict(self.idx.related_entities("symbol:PaymentClient"))
        self.assertIn("incident:INC-1001", related)

    def test_wiki(self):
        page = wiki_page(self.idx, "symbol:LedgerWriter")
        self.assertIn("# LedgerWriter", page)
        self.assertIn("services/ledger/writer.py", page)
        self.assertIn("INC-1002", page)
        with tempfile.TemporaryDirectory() as tmp:
            pages = build_wiki(self.idx, Path(tmp), k=5)
            self.assertEqual(len(pages), 5)
            self.assertTrue((Path(tmp) / "index.md").exists())

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.idx.save(Path(tmp))
            loaded = Index.load(Path(tmp))
            self.assertEqual(len(loaded.chunks), len(self.idx.chunks))
            self.assertEqual(loaded.graph.number_of_edges(), self.idx.graph.number_of_edges())
            self.assertEqual(retrieve(loaded, "connection pool")[0].chunk_id, retrieve(self.idx, "connection pool")[0].chunk_id)

    def test_guardrail_flags_the_risky_diff(self):
        alerts = review(self.idx, (DATA / "risky.diff").read_text())
        kinds = {(a.kind, a.severity) for a in alerts}
        self.assertIn(("error-handling-removed", "high"), kinds)
        self.assertIn(("config-change", "medium"), kinds)
        msgs = " ".join(a.message for a in alerts if a.kind == "similar-incident")
        self.assertIn("INC-1001", msgs)
        self.assertIn("RCA-1003", msgs)


class DiffTests(unittest.TestCase):
    def test_parse_and_rules(self):
        diff = "--- a/app/cfg.py\n+++ b/app/cfg.py\n-RETRIES = 3\n+RETRIES = 10\n-    except ValueError:\n"
        (change,) = parse_diff(diff)
        self.assertEqual(change.path, "app/cfg.py")
        kinds = {a.kind for a in rule_alerts(change)}
        self.assertEqual(kinds, {"config-change", "error-handling-removed"})


if __name__ == "__main__":
    unittest.main()
