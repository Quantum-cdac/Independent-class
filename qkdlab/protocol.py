"""Classical post-processing of a BB84 run: sifting, error rates, detection.

This is deliberately separate from everything quantum. Inputs are the round
specifications and the measured bits; outputs are the sifted keys and the
eavesdropper verdict.

Detection threshold: 11% QBER on the sifted key - an ILLUSTRATIVE demo rule
chosen from the textbook BB84 bound. It is not a security certificate: a high
error rate can come from an eavesdropper OR from channel noise, and this tool
does not distinguish causes.
"""
from dataclasses import dataclass

from .rounds import RoundSpec

DETECTION_THRESHOLD = 0.11


def wilson_interval(errors: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for the true error rate. Honest at p=0: observing
    0 errors in n bits does not mean zero risk, it bounds it."""
    if n == 0:
        return (0.0, 1.0)
    p = errors / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * ((p * (1 - p) / n) + z * z / (4 * n * n)) ** 0.5
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class SiftResult:
    sift_indices: list[int]
    alice_key: list[int]
    bob_key: list[int]
    eve_key: list[int] | None
    qber: float
    errors: int
    wilson_low: float
    wilson_high: float
    eve_qber: float | None
    high_error_rate: bool
    threshold: float


def sift(rounds: list[RoundSpec], bob_bits: list[int],
         eve_bits: list[int | None] | None = None) -> SiftResult:
    if len(rounds) != len(bob_bits):
        raise ValueError("rounds and measured bits have different lengths")
    idx = [i for i, r in enumerate(rounds) if r.alice_basis == r.bob_basis]
    alice_key = [rounds[i].alice_bit for i in idx]
    bob_key = [bob_bits[i] for i in idx]
    n = len(idx)
    if n == 0:
        raise ValueError("no sifted bits: Alice and Bob never chose the same basis")
    errors = sum(1 for a, b in zip(alice_key, bob_key) if a != b)
    qber = errors / n
    wilson_low, wilson_high = wilson_interval(errors, n)
    eve_key = None
    eve_qber = None
    if eve_bits is not None and any(e is not None for e in eve_bits):
        eve_key = [eve_bits[i] for i in idx]
        eve_qber = sum(1 for a, e in zip(alice_key, eve_key) if a != e) / n
    return SiftResult(
        sift_indices=idx,
        alice_key=alice_key,
        bob_key=bob_key,
        eve_key=eve_key,
        qber=qber,
        errors=errors,
        wilson_low=wilson_low,
        wilson_high=wilson_high,
        eve_qber=eve_qber,
        high_error_rate=qber > DETECTION_THRESHOLD,
        threshold=DETECTION_THRESHOLD,
    )
