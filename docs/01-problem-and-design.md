# QC-NI1 problem-and-design note

## Problem and users

Quantum cryptography is usually taught as pure theory: students read that "an
eavesdropper disturbs the qubits and gets caught", but never *see* the
mechanism. QKD-Lab makes eavesdropper detection observable and measurable for
learners and for developers prototyping quantum-safe systems.

Use case: in a classroom or workshop, the instructor runs the no-Eve exchange
(keys match), then switches Eve on and the error rate jumps to ~25% - the
class watches the detector fire and inspects Eve's corrupted copy of the key.

## Inputs and outputs

- Input: number of rounds, a seed, and an eavesdropper on/off flag.
- Quantum output: measurement bits from prepare-and-measure circuits executed
  on Qniverse (or the bundled exact local engine for offline runs).
- Classical output: sifted keys, QBER with sampling error, a detection verdict
  against an 11% threshold, and a self-contained HTML report.

## Quantum component

BB84 prepare-and-measure circuits built and executed with Qniverse
capabilities (circuit construction, simulation/execution, measurement). Each
round is one qubit (plus one ancilla per round when Eve is active). Rounds are
independent, so a batch packs one round per qubit into a single circuit
executed with `shots=1` - Qniverse runs one circuit per job and returns
aggregate counts, so shots cannot carry per-round randomness.

Eve's intercept-resend attack is modelled coherently: a CNOT from Alice's
qubit to Eve's ancilla in Eve's random basis (H-CNOT-H for the X basis). This
is the standard purified equivalent of measure-and-resend and reproduces its
statistics exactly, while needing only X, H, CX and final measurements.

## Success measure

- Paired comparison: one seed produces identical Alice/Bob choices with Eve on
  and off, so the two runs differ ONLY in the eavesdropper setting.
- Eve off: 0 errors expected in the sifted key, reported with a Wilson 95%
  upper bound (bounded risk, never a claim of proven-zero risk).
- Eve on: sifted-key QBER consistent with the ~25% intercept-resend
  expectation; the report flags a high error rate above an 11% ILLUSTRATIVE
  classroom rule - it cannot and does not distinguish eavesdropping from noise.
- Reproducible: same seed, same manifest, same circuits, re-runnable tests.
- Edge cases tested: zero rounds, no sifted bits, mismatched inputs, shots > 1
  on the Qniverse path rejected with a clear error, and a key-order self-check
  that must pass before any backend output is trusted.

## Limitations

- Educational simulation on classical simulators; not production QKD. No
  error correction, privacy amplification or security proof.
- QBER figures are statistical estimates; small runs vary around expectations.
- Qniverse jobs consume account credits; batch size is capped by the
  simulator's qubit limit (24 wires assumed, adjustable).
- Only the intercept-resend attack is modelled; stronger attacks are future work.
