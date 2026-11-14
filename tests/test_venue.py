import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qkdlab import venue, webapp
from qkdlab.engine import simulate_run
from qkdlab.rounds import load_manifest


def fake_counts(plan_dir, job, flip_order=False):
    """Counts text as a correct Qniverse job would print it: one bitstring,
    rightmost character = classical bit 0."""
    plan = venue.load_plan(plan_dir)
    rounds, eve, seed = load_manifest(os.path.join(plan_dir, plan["jobs"][job]["manifest"]))
    bob, ev = simulate_run(rounds, seed)
    bits = []
    for b, e in zip(bob, ev):
        bits.append(b)
        if eve:
            bits.append(e)
    key = "".join(str(x) for x in (bits if flip_order else reversed(bits)))
    return f"{key}=1"


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan_dir = os.path.join(self.tmp.name, "plan")
        self.res_dir = os.path.join(self.tmp.name, "res")
        self.plan = venue.build_plan(self.plan_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_is_two_jobs_ten_credits(self):
        self.assertEqual(self.plan["total_credits"], 10)
        self.assertEqual(set(self.plan["jobs"]), {"A", "B"})
        for j in self.plan["jobs"].values():
            self.assertEqual(j["shots"], 1)
            self.assertLessEqual(j["qubits"], 24)

    def test_calibration_batch_can_pass_the_gate(self):
        rounds, _, _ = load_manifest(os.path.join(self.plan_dir, "job-A-manifest.json"))
        matched = [r for r in rounds if r.alice_basis == r.bob_basis]
        self.assertGreaterEqual(len(matched), 8)
        self.assertEqual({r.alice_bit for r in matched}, {0, 1})

    def test_job_b_pairs_with_first_rounds_of_job_a(self):
        a, _, _ = load_manifest(os.path.join(self.plan_dir, "job-A-manifest.json"))
        b, _, _ = load_manifest(os.path.join(self.plan_dir, "job-B-manifest.json"))
        for x, y in zip(a, b):
            self.assertEqual((x.alice_bit, x.alice_basis, x.bob_basis),
                             (y.alice_bit, y.alice_basis, y.bob_basis))

    def test_job_b_refused_before_calibration(self):
        with self.assertRaises(ValueError):
            venue.import_counts(self.plan_dir, self.res_dir, "B",
                                fake_counts(self.plan_dir, "B"))

    def test_import_a_then_b_labels_source(self):
        a = venue.import_counts(self.plan_dir, self.res_dir, "A",
                                fake_counts(self.plan_dir, "A"), "12345")
        self.assertEqual(a["source"], "qniverse")
        self.assertTrue(a["calibration_passed"])
        self.assertEqual(a["errors"], 0)
        b = venue.import_counts(self.plan_dir, self.res_dir, "B",
                                fake_counts(self.plan_dir, "B"), "12346")
        self.assertEqual(b["source"], "qniverse")
        self.assertEqual(b["local"]["source"], "local-exact-engine")
        self.assertFalse(b["reliable_detection"])  # only a handful of sifted bits
        self.assertEqual(set(venue.stored_results(self.res_dir)), {"A", "B"})

    def test_wrong_bit_order_fails_calibration_loudly(self):
        with self.assertRaises(ValueError):
            venue.import_counts(self.plan_dir, self.res_dir, "A",
                                fake_counts(self.plan_dir, "A", flip_order=True))
        self.assertEqual(venue.stored_results(self.res_dir), {})

    def test_wrong_shot_count_rejected(self):
        with self.assertRaises(ValueError):
            venue.import_counts(self.plan_dir, self.res_dir, "A", "000000000000000000000000=1024")


class TestHttpImport(unittest.TestCase):
    def test_post_import_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            plan_dir, res_dir = os.path.join(d, "p"), os.path.join(d, "r")
            venue.build_plan(plan_dir)
            old = (webapp.PLAN_DIR, webapp.RESULTS_DIR)
            webapp.PLAN_DIR, webapp.RESULTS_DIR = plan_dir, res_dir
            httpd = HTTPServer(("127.0.0.1", 0), webapp._Handler)
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                base = f"http://127.0.0.1:{port}"
                state = json.load(urllib.request.urlopen(base + "/api/qniverse"))
                self.assertEqual(set(state["plan"]["jobs"]), {"A", "B"})
                self.assertEqual(state["results"], {})
                req = urllib.request.Request(
                    base + "/api/import", method="POST",
                    data=json.dumps({"job": "A", "counts": fake_counts(plan_dir, "A"),
                                     "job_id": "999"}).encode(),
                    headers={"Content-Type": "application/json"})
                out = json.load(urllib.request.urlopen(req))
                self.assertEqual(out["source"], "qniverse")
                bad = urllib.request.Request(
                    base + "/api/import", method="POST",
                    data=json.dumps({"job": "A", "counts": "nonsense"}).encode(),
                    headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(bad)
                self.assertEqual(cm.exception.code, 400)
            finally:
                httpd.shutdown()
                webapp.PLAN_DIR, webapp.RESULTS_DIR = old


if __name__ == "__main__":
    unittest.main()


class TestMultiShot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan_dir = os.path.join(self.tmp.name, "p")
        self.res_dir = os.path.join(self.tmp.name, "r")
        venue.build_plan(self.plan_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def _counts(self, job, shots=1024, seed=5):
        """Sample `shots` full-register outcomes from the exact per-round probabilities."""
        import random
        from qkdlab.engine import round_probabilities
        plan = venue.load_plan(self.plan_dir)
        rounds, eve, _ = load_manifest(os.path.join(self.plan_dir, plan["jobs"][job]["manifest"]))
        rng = random.Random(seed)
        probs = [round_probabilities(r) for r in rounds]
        out = {}
        for _ in range(shots):
            bits = []
            for p in probs:
                x, acc, pick = 3, 0.0, rng.random()
                for i, pi in enumerate(p):
                    acc += pi
                    if pick <= acc:
                        x = i
                        break
                bits.append(x & 1)
                if eve:
                    bits.append((x >> 1) & 1)
            key = "".join(str(b) for b in reversed(bits))
            out[key] = out.get(key, 0) + 1
        return "\n".join(f"{k}={v}" for k, v in out.items())

    def test_multishot_a_calibrates_and_b_is_labelled(self):
        a = venue.import_counts(self.plan_dir, self.res_dir, "A", self._counts("A"), "1")
        self.assertTrue(a["calibration_passed"])
        self.assertEqual(a["qber"], 0.0)
        self.assertIn("multi-shot", a["mode"])
        b = venue.import_counts(self.plan_dir, self.res_dir, "B", self._counts("B"), "2")
        self.assertEqual(b["source"], "qniverse")
        self.assertFalse(b["reliable_detection"])
        self.assertGreaterEqual(b["qber"], 0.0)

    def test_multishot_wrong_order_fails_calibration(self):
        flipped = "\n".join(f"{k[::-1]}={v}" for k, v in
                            (line.split("=") for line in self._counts("A").splitlines()))
        with self.assertRaises(ValueError):
            venue.import_counts(self.plan_dir, self.res_dir, "A", flipped)


class TestMeasureLast(unittest.TestCase):
    def test_measure_last_is_same_circuit_and_ends_with_measures(self):
        from qkdlab.emit_qasm import emit_qasm
        from qkdlab.rounds import make_rounds
        q = emit_qasm(make_rounds(12, True, 3), True)
        m = venue.measure_last(q)
        a, b = q.splitlines(), m.splitlines()
        self.assertEqual(sorted(a), sorted(b))
        first = next(i for i, l in enumerate(b) if l.startswith("measure"))
        self.assertTrue(all(l.startswith("measure") for l in b[first:]))
        gates = [l for l in b if not l.startswith("measure")]
        self.assertEqual(gates, [l for l in a if not l.startswith("measure")])
