"""Exact local execution of one BB84 round.

Rounds never share gates, so each round is its own 1- or 2-qubit system and a
full statevector of that small system is exact - not an approximation.

Eve's intercept-resend attack is modelled coherently: she couples the qubit to
her ancilla with a CNOT in her chosen basis (H-CNOT-H for the X basis). This is
the standard purified equivalent of "measure and resend" and reproduces its
statistics exactly, using only final measurements. That keeps the same circuit
runnable on backends without mid-circuit measurement or reset.
"""
import cmath
import random

from .rounds import RoundSpec


def _x(state, q):
    out = state[:]
    for i in range(4):
        j = i ^ (1 << q)
        out[j] = state[i]
    return out


def _h(state, q):
    out = [0j] * 4
    s = 1 / 2 ** 0.5
    for i in range(4):
        bit = (i >> q) & 1
        for b in (0, 1):
            j = (i & ~(1 << q)) | (b << q)
            sign = -1 if (bit and b) else 1
            out[j] += state[i] * s * sign
    return out


def _cnot(state, control, target):
    out = state[:]
    for i in range(4):
        if (i >> control) & 1:
            out[i] = 0j
    for i in range(4):
        if (i >> control) & 1:
            out[i ^ (1 << target)] = state[i]
    return out


def round_probabilities(spec: RoundSpec) -> list[float]:
    """Exact probabilities over the four outcomes |q a> = 00, 01, 10, 11.

    q is Alice/Bob's qubit, a is Eve's ancilla (stays |0> when Eve is off).
    """
    state = [1 + 0j, 0j, 0j, 0j]  # |00>
    if spec.alice_bit:
        state = _x(state, 0)
    if spec.alice_basis:
        state = _h(state, 0)
    if spec.eve_basis is not None:
        if spec.eve_basis:
            state = _h(state, 0)
        state = _cnot(state, 0, 1)
        if spec.eve_basis:
            state = _h(state, 0)
    if spec.bob_basis:
        state = _h(state, 0)
    return [abs(a) ** 2 for a in state]


def simulate_round(rng: random.Random, spec: RoundSpec) -> tuple[int, int | None]:
    probs = round_probabilities(spec)
    pick = rng.random()
    acc = 0.0
    outcome = 3
    for i, p in enumerate(probs):
        acc += p
        if pick <= acc:
            outcome = i
            break
    bob_bit = (outcome >> 0) & 1
    eve_bit = ((outcome >> 1) & 1) if spec.eve_basis is not None else None
    return bob_bit, eve_bit


def simulate_run(rounds: list[RoundSpec], seed: int) -> tuple[list[int], list[int | None]]:
    rng = random.Random(f"qkdlab-engine|{seed}")
    bob, eve = [], []
    for spec in rounds:
        b, e = simulate_round(rng, spec)
        bob.append(b)
        eve.append(e)
    return bob, eve
