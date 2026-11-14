# QKD-Lab — BB84 eavesdropper detection on Qniverse

**QC-NI1 (Open-Ended Quantum Computing Innovation), C-DAC Quantum Computing Hackathon.**

QKD-Lab makes the core promise of quantum key distribution *visible*: two
parties (Alice and Bob) build a shared key one qubit at a time, and if an
eavesdropper (Eve) listens in, the error rate jumps and the tool calls it out.

Both runs use the same seed, so Alice's and Bob's choices are identical -
the ONLY thing that changes is the eavesdropper:

- **Run 1 (Eve off):** sifted keys match, 0 observed errors, report shows the
  error rate within the expected range (with an honest uncertainty bound).
- **Run 2 (Eve on):** the error rate jumps (expectation ~25%), the report
  flags **HIGH ERROR RATE: possible eavesdropping or channel noise** - the
  detector only sees the error rate - plus a panel showing Eve's own corrupted
  copy of the key.

The quantum part (prepare-and-measure circuits) runs on **Qniverse** through the
hosted notebook. A built-in exact local engine runs the same circuits with no
account or credits, so anyone can reproduce the full demo offline.

> Educational simulation. QBER values are statistical estimates over finite
> rounds, not per-run guarantees. This is not production key distribution:
> no error correction, privacy amplification or security proof.

## Quickstart (offline, no credits)

```bash
python -m qkdlab run --rounds 48 --seed 20261114 --out evidence/demo-no-eve
python -m qkdlab run --rounds 48 --seed 20261114 --eve --out evidence/demo-eve
```

Or explore it interactively in your browser (same engine, no credits):

```bash
python -m qkdlab serve --port 8000   # then open http://localhost:8000
```

The dashboard lets you toggle the eavesdropper, change rounds and seed, and
rerun - every click recomputes the full experiment with the verified engine.

Each run writes `manifest.json` (every random choice, hash-sealed),
`results.json` and a self-contained `report.html` you can open in any browser.

## Qniverse execution (venue path)

```bash
python -m qkdlab emit-qasm --manifest evidence/demo-eve/manifest.json --max-wires 24
```

This writes one OpenQASM 2.0 file per batch (rounds are packed as independent
qubits, `shots=1`). Upload each batch in the Qniverse composer and run it on a
CPU simulator, then rebuild the report from the downloaded counts:

```bash
python -m qkdlab report --manifest evidence/demo-eve/manifest.json \
  --backend-output counts-batch-00.txt counts-batch-01.txt ...
```

Qniverse jobs consume account credits (CPU simulation: 5 credits/job per the
Qniverse release notes). The venue notebook `venue/qkd-demo.ipynb` automates
the same flow through the QSDK once you paste your API key.

### Two-job validation plan (10 credits at the published price)

```bash
python -m qkdlab plan          # writes evidence/venue-plan/ (job A, job B, plan.json)
```

- **Job A** (`job-A.qasm`, Eve off, 12 qubits): calibration. Bob's bit must equal Alice's on every
  basis-matching round, which checks the counts bit order.
- **Job B** (`job-B.qasm`, Eve on, 24 qubits): same Alice/Bob choices plus Eve's coherent ancilla.
  About 9 sifted bits, so it shows the circuit running on Qniverse, not a reliable detection.

Paste each job's counts into the dashboard's "Qniverse results" card (or `python -m qkdlab serve`
and open the page). Results are tagged QNIVERSE or LOCAL. Job B is refused until job A passes.
The dashboard only decodes pasted counts; it never submits jobs or spends credits.

## Layout

- `qkdlab/rounds.py` - seeded per-round choices (Alice/Bob/Eve bits and bases)
- `qkdlab/engine.py` - exact 1-2 qubit execution per round; coherent Eve model
- `qkdlab/protocol.py` - sifting, QBER, detection threshold (classical only)
- `qkdlab/emit_qasm.py`, `emit_qsdk.py`, `parse_backend.py` - Qniverse I/O
- `qkdlab/report.py` - self-contained HTML report
- `qkdlab/webapp.py` - local interactive web dashboard (`serve`)
- `qkdlab/venue.py` - two-job Qniverse plan and counts importer
- `tests/` - 43 tests, `python -m unittest discover -s tests`
- `docs/` - problem/design, protocol, architecture, testing, AI disclosure
- `evidence/` - demo runs and reports
- `venue/` - Qniverse hosted-notebook demo

## How the demo tells the story

1. Show `evidence/demo-no-eve/report.html`: keys match, 0 errors in the
   sifted bits, with the Wilson 95% bound shown (bounded risk, not "proven zero").
2. Show `evidence/demo-eve/report.html`: SAME rounds, high error rate flagged,
   Eve's-key panel. The paired seed makes it obvious only Eve changed.
3. Re-run live with a new seed to prove nothing is canned.
4. Open the test suite: 43 tests covering the engine, protocol, emitters,
   parsing, reproducibility - and an independent numpy density-matrix
   cross-check of every choice combination and of the emitted QASM.

See `docs/03-architecture.md` for how BB84 rounds map onto Qniverse jobs and
why Eve is modelled with a CNOT to an ancilla (same statistics as
intercept-resend, no mid-circuit measurement needed).
