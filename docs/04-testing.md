# Test plan and results

Suite: `python -m unittest discover -s tests` — 43 tests. Core is standard
library only; the independent cross-check additionally uses numpy and skips
cleanly without it.

Latest run (2026-11-14, Python 3.10):

```
Ran 43 tests in 0.7s

OK
```

## What is covered

**Exact local engine**
- Matching Z/Z and X/X bases deliver Alice's bit with probability 1
- Mismatched bases give 50/50 outcomes
- All 16 no-Eve + 16 Eve choice combinations produce normalised probabilities
- No-Eve 2000-round run: 0 errors, no high-error flag, Wilson bound reported
  (0 errors never means proven-zero risk)
- Coherent-Eve 4000-round run: QBER within [20%, 30%] (expected ~25%),
  high-error flag fires, Eve's copy quality in [15%, 35%]

**Independent verification (numpy density matrix, separate code)**
- All 32 choice combinations: density-matrix probabilities equal the
  statevector engine's to 12 decimal places
- The exact emitted QASM gate sequences re-executed on the density-matrix
  simulator match the engine for 25 seeded rounds, Eve on and off
- Analytic intercept-resend expectations hold exactly: sifted error 0 when
  Eve's basis matches, 1/2 when it differs (marginalised over the ancilla),
  1/4 on average

**Protocol (classical)**
- Sifting keeps only basis-matching rounds (hand-checked example)
- High-error flag follows the 11% illustrative threshold
- Paired runs: same seed with Eve on/off shares every Alice/Bob choice
- Length mismatches and zero-sifted-bit inputs raise clear errors

**Emitters and backend parsing**
- Exact QASM gate sequence for the hardest combination (all flags on)
- Wire map and measure count scale with rounds and Eve mode
- Batches respect the 24-wire limit (12/12/6 for 30 Eve rounds)
- Counts-key convention: rightmost character is c[0] (venue-confirmed on one
  job; re-verified by selfcheck before every trusted import)
- Counts parser accepts the common `= /`:` / JSON / quoted formats
- shots>1 backend output is rejected with an explanation
- A counts key round-trips back to the exact simulated bits

**Reproducibility and end-to-end**
- Same seed produces identical round specs in separate processes
- Manifest saves and reloads with integrity fields
- CLI `run` writes manifest + results + HTML report with calibrated wording
