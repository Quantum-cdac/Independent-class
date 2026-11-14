# Architecture

```
seed ──> rounds.py ──> circuit spec per round ──┬──> engine.py (local, exact)
               (manifest.json, hash-sealed)     ├──> emit_qasm.py ──> Qniverse composer
                                                └──> emit_qsdk.py ──> Qniverse hosted notebook
measurement bits ──> protocol.py (sift, QBER, verdict) ──> report.py (HTML)
```

## Quantum / classical boundary

- **Quantum (Qniverse):** state preparation (X, H), Eve's coupling (CX),
  basis rotation (H), measurement. Nothing else.
- **Classical (this repo):** random choice generation, sifting, QBER,
  detection flag, statistics, reports, tests.

## Batching rounds into Qniverse jobs

Qniverse executes **one circuit per job** and returns **aggregate counts**
(per-shot bitstrings are not part of the documented result). A multi-shot run
of one fixed circuit cannot represent BB84 rounds, because every round needs
fresh random choices. So rounds are packed as **independent qubits in one
circuit executed with `shots=1`**:

- Eve off: round r uses `q[r]` -> `c[r]`.
- Eve on: round r uses `q[2r]` (channel) and `q[2r+1]` (Eve's ancilla).

Bit order in the counts key: the **rightmost character is c[0]** (confirmed at
the venue on job 38024, for that job's shape). Because one observed case is
not a universal guarantee, `parse_backend.selfcheck()` re-verifies the
convention on an asymmetric known pattern every time before backend output is
trusted, and the venue notebook runs it before submission.

Batches are capped at 24 wires by default (`--max-wires`); a 48-round Eve run
is four jobs.

## Exact local engine

Rounds never share gates, so each round is its own 1- or 2-qubit system and a
full statevector of that system is exact. The engine applies the same gate
sequence the emitters produce and samples from the exact probabilities with a
seeded generator. It exists so the protocol logic, tests and offline demo run
anywhere with zero dependencies and zero credits; it is not a substitute for
the Qniverse evidence run.

## Coherent Eve model

Intercept-resend equals: rotate into Eve's basis (H for X), CNOT channel->
ancilla, rotate back. The ancilla holds Eve's measurement result; measuring it
shows the key Eve thinks she has. When bases mismatch the channel qubit is
left entangled with the ancilla, which is exactly the disturbance intercept-
resend causes. Verified two ways: seeded 4000-round runs land at ~25% QBER, and an
INDEPENDENT numpy density-matrix simulator (separate code, different state
representation) reproduces the statevector engine's exact probabilities for
all 32 choice combinations and for the exact emitted QASM gate sequences
(tests/test_independent.py).

## Credits and spend control

Qniverse release notes (v1.2.0): 150 registration credits, CPU simulation 5
credits/job, GPU 10, QPU 2. The CLI never submits jobs; job submission happens
only in the venue notebook after the operator pastes their API key and sees
the drawn circuit. `credit_balance(token)` can report the remaining balance.
