"""BB84 round specifications: the random classical choices made before any
quantum circuit is built.

Every choice is derived from a single seed, so a whole run is reproducible from
its manifest file. Basis encoding: 0 = Z (rectilinear), 1 = X (diagonal).
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import random


@dataclass
class RoundSpec:
    alice_bit: int        # the key bit Alice wants to send
    alice_basis: int      # basis Alice prepares in
    bob_basis: int        # basis Bob measures in
    eve_basis: int | None # basis Eve intercepts in, or None when Eve is off


def make_rounds(n: int, eve: bool, seed: int) -> list[RoundSpec]:
    """Alice/Bob choices come from a stream that ignores the Eve flag, so a
    paired comparison with the same seed changes ONLY the eavesdropper
    setting. Eve's basis choices use their own stream.
    """
    if n < 1:
        raise ValueError("round count must be at least 1")
    ab = random.Random(f"qkdlab-alice-bob|{seed}")
    ev = random.Random(f"qkdlab-eve|{seed}")
    out = []
    for _ in range(n):
        out.append(RoundSpec(
            alice_bit=ab.randint(0, 1),
            alice_basis=ab.randint(0, 1),
            bob_basis=ab.randint(0, 1),
            eve_basis=ev.randint(0, 1) if eve else None,
        ))
    return out


def manifest_dict(rounds: list[RoundSpec], eve: bool, seed: int) -> dict:
    body = {
        "version": 1,
        "seed": seed,
        "eve": eve,
        "round_count": len(rounds),
        "rounds": [asdict(r) for r in rounds],
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return body


def save_manifest(rounds: list[RoundSpec], eve: bool, seed: int, path: str) -> dict:
    body = manifest_dict(rounds, eve, seed)
    with open(path, "w") as fh:
        json.dump(body, fh, indent=2)
    return body


def load_manifest(path: str) -> tuple[list[RoundSpec], bool, int]:
    with open(path) as fh:
        body = json.load(fh)
    rounds = [RoundSpec(**r) for r in body["rounds"]]
    if len(rounds) != body["round_count"]:
        raise ValueError("manifest round count mismatch")
    return rounds, bool(body["eve"]), int(body["seed"])
