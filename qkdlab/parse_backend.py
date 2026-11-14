"""Parse a Qniverse job counts file back into per-round Bob (and Eve) bits.

Expected run shape: one circuit, shots=1, so the counts contain a single
bitstring. Tolerant of the common count formats: '01=143', '01: 143',
\"'01': 143\", '01 143', JSON objects.
"""
import json
import re

from .emit_qasm import bits_from_counts_key, wires_per_round

_PAIR = re.compile(r"[\"']?([01]+)[\"']?\s*[=: ]\s*(\d+)")


def parse_counts(text: str) -> dict[str, int]:
    text = text.strip()
    if text.startswith("{"):
        try:
            raw = json.loads(text)
            # Qniverse job export (output.txt): {"probability": {bits: n}, "shots": N}
            if isinstance(raw.get("probability"), dict):
                raw = raw["probability"]
            return {str(k).strip(): int(v) for k, v in raw.items()}
        except json.JSONDecodeError:
            pass  # fall through to the tolerant pair parser
    counts: dict[str, int] = {}
    for key, n in _PAIR.findall(text):
        counts[key] = counts.get(key, 0) + int(n)
    if not counts:
        raise ValueError("no measurement counts found in backend output")
    return counts


def rounds_from_counts(counts: dict[str, int], n_rounds: int, eve: bool):
    """Return (bob_bits, eve_bits) for a one-batch, shots=1 counts result."""
    w = wires_per_round(eve) * n_rounds
    total = sum(counts.values())
    if total != 1:
        raise ValueError(
            f"expected a shots=1 run (one observed bitstring), got {total} shots; "
            "BB84 rounds are batched as qubits, not as shots"
        )
    key = next(iter(counts))
    bits = bits_from_counts_key(key, w)
    bob, ev = [], []
    for r in range(n_rounds):
        q = r * wires_per_round(eve)
        bob.append(bits[q])
        ev.append(bits[q + 1] if eve else None)
    return bob, ev

def selfcheck() -> None:
    """Verify the key-order convention on an asymmetric known pattern before
    any venue import is trusted. '10' must decode to c[0]=0, c[1]=1 and, as a
    one-Eve-round key, to bob=0 / eve=1. Raises on violation."""
    bits = bits_from_counts_key("10", 2)
    assert bits == [0, 1], f"convention broken: {bits}"
    bob, eve = rounds_from_counts({"10": 1}, 1, True)
    assert bob == [0] and eve == [1], f"round decode broken: {bob} {eve}"
    zfilled = bits_from_counts_key("1", 4)  # short keys are zero-padded on the LEFT
    assert zfilled == [1, 0, 0, 0], f"zero-fill broken: {zfilled}"

def verify_against_manifest(rounds, bob_bits) -> None:
    """Gate LIVE venue imports: only valid for an Eve-off manifest, where every
    basis-matching round is deterministic on an ideal backend. Any mismatch
    means the decode (e.g. key order) or the backend result cannot be trusted.
    Raises ValueError listing the first mismatches."""
    for spec in rounds:
        if spec.eve_basis is not None:
            raise ValueError("verify_against_manifest requires an Eve-off manifest")
    # Only basis-matching rounds are deterministic on an ideal backend; the
    # rest are 50/50 and carry no decode information. The check also needs
    # enough matched rounds with BOTH bit values, or a wrong decode could
    # pass by luck.
    matched = [(i, spec) for i, spec in enumerate(rounds)
               if spec.alice_basis == spec.bob_basis]
    values = {spec.alice_bit for _, spec in matched}
    if len(matched) < 8 or len(values) < 2:
        raise ValueError(
            f"insufficient deterministic asymmetric rounds to verify the "
            f"decode ({len(matched)} basis-matching, bit values "
            f"{sorted(values)}); run a larger Eve-off calibration batch.")
    mismatches = [(i, spec.alice_bit, bob_bits[i]) for i, spec in matched
                  if bob_bits[i] != spec.alice_bit]
    if mismatches:
        sample = ", ".join(f"round {i}: alice={a} got={b}" for i, a, b in mismatches[:5])
        raise ValueError(
            f"backend decode failed the known-pattern check on {len(mismatches)} "
            f"basis-matching round(s): {sample}. Do NOT trust this import - the "
            "counts-key bit order or the batch alignment is wrong, or "
            "backend noise flipped a deterministic bit."
        )
