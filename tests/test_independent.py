"""Independent cross-checks: a density-matrix simulator built on numpy,
written separately from qkdlab.engine's statevector code, must agree on every
choice combination and on the exact emitted QASM. The analytic intercept-
resend expectation (25% sifted QBER) must also hold exactly.

Skipped cleanly when numpy is unavailable: the core package stays zero-dep.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from qkdlab.rounds import RoundSpec, make_rounds
from qkdlab.engine import round_probabilities
from qkdlab.emit_qasm import emit_qasm


def _dm_probabilities(ops):
    """Execute a gate list on the density matrix |00><00| and return the
    diagonal. ops: ('x'|'h', qubit) or ('cx', control, target)."""
    I = np.eye(2)
    X = np.array([[0, 1], [1, 0]], dtype=complex)
    H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)

    def one(q, g):  # gate g on qubit q (q=0 is the LOW tensor factor)
        return np.kron(g, I) if q == 1 else np.kron(I, g)

    rho = np.zeros((4, 4), dtype=complex)
    rho[0, 0] = 1.0
    for op in ops:
        if op[0] in ("x", "h"):
            U = one(op[1], X if op[0] == "x" else H)
        else:  # cx: |ab> -> |a, b xor a> with a=control(q0), b=target(q1)
            U = np.zeros((4, 4), dtype=complex)
            for a_ in (0, 1):
                for b_ in (0, 1):
                    src = a_ + 2 * b_      # index = q0 + 2*q1
                    tgt = a_ + 2 * (b_ ^ a_)
                    U[tgt, src] = 1.0
            if op[1] == 1:                 # control is q1: swap roles
                S = np.array([[1, 0, 0, 0], [0, 0, 1, 0],
                              [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex)
                U = S @ U @ S
        rho = U @ rho @ U.conj().T
    return [float(np.real(rho[i, i])) for i in range(4)]


def _spec_to_ops(spec):
    ops = []
    if spec.alice_bit:
        ops.append(("x", 0))
    if spec.alice_basis:
        ops.append(("h", 0))
    if spec.eve_basis is not None:
        if spec.eve_basis:
            ops.append(("h", 0))
        ops.append(("cx", 0, 1))
        if spec.eve_basis:
            ops.append(("h", 0))
    if spec.bob_basis:
        ops.append(("h", 0))
    return ops


def _qasm_to_ops(qasm):
    ops = []
    for line in qasm.splitlines():
        line = line.strip()
        if line.startswith(("x ", "h ")):
            ops.append((line[0], int(line.split("[")[1].split("]")[0])))
        elif line.startswith("cx "):
            a, b = line[3:].rstrip(";").split(",")
            ops.append(("cx", int(a.split("[")[1].split("]")[0]),
                        int(b.split("[")[1].split("]")[0])))
    return ops


@unittest.skipUnless(np is not None, "numpy not installed")
class TestIndependentDensityMatrix(unittest.TestCase):
    def test_all_32_combinations_match(self):
        for a in (0, 1):
            for ab in (0, 1):
                for bb in (0, 1):
                    for eb in (0, 1, None):
                        spec = RoundSpec(a, ab, bb, eb)
                        sv = round_probabilities(spec)
                        dm = _dm_probabilities(_spec_to_ops(spec))
                        for x, y in zip(sv, dm):
                            self.assertAlmostEqual(x, y, places=12, msg=str(spec))

    def test_emitted_qasm_matches_engine_math(self):
        for eve in (False, True):
            rounds = make_rounds(25, eve, 424242)
            ops = _qasm_to_ops(emit_qasm(rounds, eve))
            # group ops per round by wire and compare each round
            w = 2 if eve else 1
            for r, spec in enumerate(rounds):
                round_ops = [op for op in ops
                             if all((idx // w) == r for idx in op[1:])]
                round_ops = [(op[0], *[i % w for i in op[1:]]) for op in round_ops]
                dm = _dm_probabilities(round_ops)
                sv = round_probabilities(spec)
                for x, y in zip(sv, dm):
                    self.assertAlmostEqual(x, y, places=12,
                                           msg=f"round {r} {spec}")

    def test_analytic_sifted_error_rates(self):
        # sifted rounds (a_bas == b_bas): no Eve -> 0; Eve -> 1/2 when Eve's
        # basis differs, 0 when it matches; average over Eve's random basis
        # is exactly 1/4.
        for ab in (0, 1):
            spec_clean = RoundSpec(1, ab, ab, None)
            p_clean = _dm_probabilities(_spec_to_ops(spec_clean))
            self.assertAlmostEqual(p_clean[0b01], 1.0)
            for eb in (0, 1):
                spec = RoundSpec(1, ab, ab, eb)
                p = _dm_probabilities(_spec_to_ops(spec))
                # Bob's bit is q0 (low bit); marginalise over Eve's ancilla
                p_bob0 = p[0b00] + p[0b10]
                expected_err = 0.0 if eb == ab else 0.5
                self.assertAlmostEqual(p_bob0, expected_err, places=12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
