"""Emit a Python program that builds and submits the same batch with the
Qniverse QSDK, for use inside the Qniverse hosted notebook.

Verified QSDK API shape (qniverse.in QSDK docs): QniverseCircuit with explicit
QuantumRegister/ClassicalRegister, qc.add_gate(h, q[i]),
qc.add_gate(measure, q[i], c[i]), Backend().processor("CPU").hpc("QACC_Cluster")
.simulator("qasm_simulator"), run(qc, backend, shots, token=token, job_name=...).
Gate names x/h/cx follow the documented universal basis; the notebook prints
the drawn circuit so the operator can confirm before spending credits.
"""
from .emit_qasm import wires_per_round
from .rounds import RoundSpec


def emit_qsdk(rounds: list[RoundSpec], eve: bool, job_name: str) -> str:
    w = wires_per_round(eve) * len(rounds)
    L = [
        "from Qniverse.gates import *",
        "from Qniverse.QniverseCircuit import *",
        "from Qniverse.backend import Backend",
        "from Qniverse.api import run, fetch_job_result",
        "",
        f"N_WIRES = {w}",
        "qc = QniverseCircuit()",
        "q = QuantumRegister(N_WIRES, 'q')",
        "c = ClassicalRegister(N_WIRES, 'c')",
        "qc.add_register(q)",
        "qc.add_register(c)",
    ]
    for r, spec in enumerate(rounds):
        q = r * wires_per_round(eve)
        a = q + 1 if eve else None
        if spec.alice_bit:
            L.append(f"qc.add_gate(x, q[{q}])")
        if spec.alice_basis:
            L.append(f"qc.add_gate(h, q[{q}])")
        if eve:
            if spec.eve_basis:
                L.append(f"qc.add_gate(h, q[{q}])")
            L.append(f"qc.add_gate(cx, q[{q}], q[{a}])")
            if spec.eve_basis:
                L.append(f"qc.add_gate(h, q[{q}])")
        if spec.bob_basis:
            L.append(f"qc.add_gate(h, q[{q}])")
        L.append(f"qc.add_gate(measure, q[{q}], c[{q}])")
        if eve:
            L.append(f"qc.add_gate(measure, q[{a}], c[{a}])")
    L += [
        "",
        "token = 'PASTE_QNIVERSE_API_KEY_HERE'",
        "backend = Backend()",
        "backend.processor('CPU')",
        "backend.hpc('QACC_Cluster')",
        "backend.simulator('qasm_simulator')",
        f"job = run(qc, backend, 1, token=token, job_name='{job_name}')  # shots=1",
        "print(fetch_job_result(token, job))",
    ]
    return "\n".join(L) + "\n"
