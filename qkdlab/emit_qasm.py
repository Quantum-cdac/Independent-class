"""Emit one OpenQASM 2.0 circuit per execution batch.

Qniverse executes ONE circuit per job and returns aggregate counts, so a batch
packs many BB84 rounds as independent qubits in a single circuit and runs with
shots=1. Bit convention confirmed at the venue (job 38024): in the counts key
the RIGHTMOST character is classical bit 0.

Wire map
--------
Eve off: round r -> qubit q[r],  classical bit c[r]
Eve on:  round r -> qubit q[2r], ancilla q[2r+1], bits c[2r], c[2r+1]
"""
from .rounds import RoundSpec


def wires_per_round(eve: bool) -> int:
    return 2 if eve else 1


def emit_qasm(rounds: list[RoundSpec], eve: bool) -> str:
    w = wires_per_round(eve) * len(rounds)
    lines = [
        "OPENQASM 2.0;",
        'include "qelib1.inc";',
        f"qreg q[{w}];",
        f"creg c[{w}];",
    ]
    for r, spec in enumerate(rounds):
        q = r * wires_per_round(eve)
        a = q + 1 if eve else None
        if spec.alice_bit:
            lines.append(f"x q[{q}];")
        if spec.alice_basis:
            lines.append(f"h q[{q}];")
        if eve:
            assert spec.eve_basis is not None and a is not None
            if spec.eve_basis:
                lines.append(f"h q[{q}];")
            lines.append(f"cx q[{q}],q[{a}];")
            if spec.eve_basis:
                lines.append(f"h q[{q}];")
        if spec.bob_basis:
            lines.append(f"h q[{q}];")
        lines.append(f"measure q[{q}] -> c[{q}];")
        if eve:
            lines.append(f"measure q[{a}] -> c[{a}];")
    return "\n".join(lines) + "\n"


def split_batches(rounds: list[RoundSpec], eve: bool, max_wires: int):
    """Yield batches that fit within max_wires qubits each."""
    per = max(1, max_wires // wires_per_round(eve))
    for start in range(0, len(rounds), per):
        yield start, rounds[start:start + per]


def bits_from_counts_key(key: str, wire_count: int) -> list[int]:
    """Counts key -> classical bits. Rightmost character is c[0]."""
    key = key.strip().replace(" ", "")
    if len(key) > wire_count:
        raise ValueError(f"counts key '{key}' wider than {wire_count} classical bits")
    key = key.zfill(wire_count)
    return [int(ch) for ch in reversed(key)]
