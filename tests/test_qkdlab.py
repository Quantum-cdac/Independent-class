import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qkdlab.rounds import RoundSpec, make_rounds, save_manifest, load_manifest
from qkdlab.engine import round_probabilities, simulate_round, simulate_run
from qkdlab.protocol import sift, DETECTION_THRESHOLD
from qkdlab.emit_qasm import emit_qasm, split_batches, bits_from_counts_key
from qkdlab.parse_backend import parse_counts, rounds_from_counts

SEED = 20261114


class TestReproducibility(unittest.TestCase):
    def test_same_seed_same_rounds_across_processes(self):
        code = ("from qkdlab.rounds import make_rounds; "
                "print([tuple(vars(r).values()) for r in make_rounds(20, True, 7)])")
        outs = {subprocess.check_output([sys.executable, "-c", code], text=True)
                for _ in range(3)}
        self.assertEqual(len(outs), 1, "round specs must be identical across processes")

    def test_manifest_roundtrip(self):
        rounds = make_rounds(10, True, SEED)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            save_manifest(rounds, True, SEED, p)
            back, eve, seed = load_manifest(p)
        self.assertEqual(back, rounds)
        self.assertTrue(eve)
        self.assertEqual(seed, SEED)


class TestEngine(unittest.TestCase):
    def test_matching_z_bases_deliver_the_bit(self):
        spec = RoundSpec(alice_bit=1, alice_basis=0, bob_basis=0, eve_basis=None)
        probs = round_probabilities(spec)
        self.assertAlmostEqual(probs[0b01], 1.0)  # q=1, a=0

    def test_matching_x_bases_deliver_the_bit(self):
        for bit in (0, 1):
            spec = RoundSpec(alice_bit=bit, alice_basis=1, bob_basis=1, eve_basis=None)
            probs = round_probabilities(spec)
            self.assertAlmostEqual(probs[bit], 1.0, msg=f"alice bit {bit} in X basis")

    def test_mismatched_bases_are_random(self):
        spec = RoundSpec(alice_bit=0, alice_basis=0, bob_basis=1, eve_basis=None)
        probs = round_probabilities(spec)
        self.assertAlmostEqual(probs[0b00], 0.5)
        self.assertAlmostEqual(probs[0b01], 0.5)

    def test_no_eve_long_run_has_zero_qber(self):
        rounds = make_rounds(2000, False, SEED)
        bob, eve = simulate_run(rounds, SEED)
        res = sift(rounds, bob, eve)
        self.assertEqual(res.qber, 0.0)
        self.assertFalse(res.high_error_rate)
        self.assertGreater(res.wilson_high, 0.0,
                           "0 errors in n bits bounds risk, never proves it zero")

    def test_coherent_eve_gives_expected_25_percent_qber(self):
        rounds = make_rounds(4000, True, SEED)
        bob, eve = simulate_run(rounds, SEED)
        res = sift(rounds, bob, eve)
        self.assertTrue(0.20 <= res.qber <= 0.30,
                        f"expected ~25% QBER, got {res.qber:.3f}")
        self.assertTrue(res.high_error_rate)
        self.assertIsNotNone(res.eve_qber)
        self.assertTrue(0.15 <= res.eve_qber <= 0.35)

    def test_probabilities_normalise(self):
        for combo in [(a, b, c, d) for a in (0, 1) for b in (0, 1)
                      for c in (0, 1) for d in (0, 1, None)]:
            spec = RoundSpec(*combo)
            self.assertAlmostEqual(sum(round_probabilities(spec)), 1.0, msg=str(combo))


class TestProtocol(unittest.TestCase):
    def test_sift_keeps_only_matching_bases(self):
        rounds = [RoundSpec(1, 0, 0, None), RoundSpec(0, 1, 0, None),
                  RoundSpec(1, 1, 1, None)]
        res = sift(rounds, [1, 1, 0])
        self.assertEqual(res.sift_indices, [0, 2])
        self.assertEqual(res.alice_key, [1, 1])
        self.assertEqual(res.bob_key, [1, 0])
        self.assertEqual(res.qber, 0.5)

    def test_detection_threshold(self):
        rounds = make_rounds(400, True, SEED)
        bob, eve = simulate_run(rounds, SEED)
        res = sift(rounds, bob, eve)
        self.assertEqual(res.qber > DETECTION_THRESHOLD, res.high_error_rate)

    def test_paired_runs_share_alice_bob_choices(self):
        """Eve on/off with the same seed must change ONLY the Eve setting."""
        off = make_rounds(50, False, SEED)
        on = make_rounds(50, True, SEED)
        for a, b in zip(off, on):
            self.assertEqual((a.alice_bit, a.alice_basis, a.bob_basis),
                             (b.alice_bit, b.alice_basis, b.bob_basis))
        self.assertTrue(all(r.eve_basis is None for r in off))
        self.assertTrue(all(r.eve_basis is not None for r in on))

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            sift(make_rounds(3, False, 1), [0, 0])

    def test_no_sifted_bits_rejected(self):
        rounds = [RoundSpec(0, 0, 1, None), RoundSpec(1, 0, 1, None)]
        with self.assertRaises(ValueError):
            sift(rounds, [0, 0])


class TestEmittersAndParsing(unittest.TestCase):
    def test_qasm_gate_sequence_for_each_eve_combination(self):
        # alice_bit=1, alice_basis=1, eve_basis=1, bob_basis=1
        qasm = emit_qasm([RoundSpec(1, 1, 1, 1)], True)
        gates = [l for l in qasm.splitlines() if l.startswith(("x", "h", "cx"))]
        self.assertEqual(gates, ["x q[0];", "h q[0];", "h q[0];",
                                 "cx q[0],q[1];", "h q[0];", "h q[0];"])

    def test_qasm_wire_map(self):
        rounds = make_rounds(5, True, SEED)
        qasm = emit_qasm(rounds, True)
        self.assertIn("qreg q[10];", qasm)
        self.assertIn("creg c[10];", qasm)
        self.assertEqual(qasm.count("measure"), 10)

    def test_batches_respect_wire_limit(self):
        rounds = make_rounds(30, True, SEED)
        sizes = [len(b) for _, b in split_batches(rounds, True, 24)]
        self.assertEqual(sizes, [12, 12, 6])

    def test_counts_key_rightmost_is_c0(self):
        self.assertEqual(bits_from_counts_key("101100", 6), [0, 0, 1, 1, 0, 1])

    def test_parse_counts_formats(self):
        for text in ("{'101': 3}", '"101"=3', "101: 3", '{"101": 3}'):
            self.assertEqual(parse_counts(text), {"101": 3}, msg=text)

    def test_rounds_from_counts_requires_shots_1(self):
        with self.assertRaises(ValueError):
            rounds_from_counts({"00": 2}, 2, False)

    def test_rounds_from_counts_recovers_bits(self):
        rounds = make_rounds(4, True, SEED)
        rng = random.Random("fixed")
        bits = []
        for spec in rounds:
            b, e = simulate_round(rng, spec)
            bits += [b, e]
        key = "".join(str(b) for b in reversed(bits))
        bob, eve = rounds_from_counts({key: 1}, 4, True)
        self.assertEqual(bob, bits[0::2])
        self.assertEqual(eve, bits[1::2])


class TestCliEndToEnd(unittest.TestCase):
    def test_run_writes_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_call(
                [sys.executable, "-m", "qkdlab", "run", "--rounds", "48",
                 "--seed", str(SEED), "--eve", "--out", d],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            for name in ("manifest.json", "results.json", "report.html"):
                self.assertTrue(os.path.exists(os.path.join(d, name)), name)
            results = json.load(open(os.path.join(d, "results.json")))
            self.assertTrue(results["high_error_rate"])
            self.assertTrue(results["scenario_eve"])
            self.assertIn("HIGH ERROR RATE",
                          open(os.path.join(d, "report.html")).read())


class TestWebapp(unittest.TestCase):
    def test_run_experiment_matches_engine(self):
        from qkdlab.webapp import run_experiment
        d = run_experiment(48, SEED, False)
        self.assertEqual(d["rounds"], 48)
        self.assertEqual(d["errors"], 0)
        self.assertEqual(len(d["strip"]), 48)
        self.assertEqual(sum(1 for s in d["strip"] if s["matched"]), d["sifted"])
        self.assertFalse(d["high_error_rate"])

    def test_run_experiment_eve_paired(self):
        from qkdlab.webapp import run_experiment
        off = run_experiment(48, SEED, False)
        on = run_experiment(48, SEED, True)
        # Paired design: same sifted positions, only Eve's presence differs.
        self.assertEqual(off["sifted"], on["sifted"])
        self.assertGreater(on["qber"], 0.10)
        self.assertTrue(on["high_error_rate"])
        self.assertIn("eve_qber", on)

    def test_run_experiment_clamps_rounds(self):
        from qkdlab.webapp import run_experiment
        self.assertEqual(run_experiment(99999, SEED, False)["rounds"], 500)
        self.assertEqual(run_experiment(1, SEED, False)["rounds"], 8)

    def test_http_endpoints(self):
        import json, threading, urllib.request
        from http.server import HTTPServer
        from qkdlab.webapp import _Handler
        srv = HTTPServer(("127.0.0.1", 0), _Handler)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
            self.assertIn("interactive BB84 demo", page)
            d = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/run?rounds=48&seed={SEED}&eve=1").read())
            self.assertTrue(d["high_error_rate"])
            self.assertEqual(d["sifted"], 23)
            bad = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/run?rounds=abc",)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestVenueGate(unittest.TestCase):
    def test_correct_decode_passes(self):
        from qkdlab.parse_backend import verify_against_manifest
        rounds = make_rounds(40, False, SEED)
        bob, _ = simulate_run(rounds, SEED)
        verify_against_manifest(rounds, bob)  # must not raise

    def test_flipped_bits_fail_loudly(self):
        from qkdlab.parse_backend import verify_against_manifest
        rounds = make_rounds(40, False, SEED)
        bob, _ = simulate_run(rounds, SEED)
        with self.assertRaises(ValueError):
            verify_against_manifest(rounds, [1 - b for b in bob])

    def test_insufficient_asymmetry_fails_loudly(self):
        from qkdlab.parse_backend import verify_against_manifest
        # 6 rounds: too few basis-matching rounds to prove the decode.
        rounds = make_rounds(6, False, SEED)
        bob, _ = simulate_run(rounds, SEED)
        with self.assertRaises(ValueError):
            verify_against_manifest(rounds, bob)

    def test_eve_manifest_rejected_by_gate(self):
        from qkdlab.parse_backend import verify_against_manifest
        rounds = make_rounds(10, True, SEED)
        bob, _ = simulate_run(rounds, SEED)
        with self.assertRaises(ValueError):
            verify_against_manifest(rounds, bob)
