"""Two-job Qniverse validation plan and a source-labelled results importer.

Plan (kept deliberately small, 2 CPU jobs = 10 credits at the published
5 credits/job):

  job A  Eve OFF, 12 rounds, 12 qubits  - calibration. On an ideal simulator
         every basis-matching round is deterministic, so Bob's bits must equal
         Alice's. This checks the counts-key bit order before anything else is
         trusted.
  job B  Eve ON, 12 rounds, 24 qubits   - same Alice/Bob choices as the first
         12 rounds of job A, plus Eve's coherent intercept-resend ancilla.
         Only ~6 bits survive sifting, so this is a demonstration of the
         circuit on Qniverse, NOT a reliable eavesdropper detection.

Nothing here talks to Qniverse. It prepares circuits and decodes counts that a
person pasted back from a Qniverse job. Job B is refused until job A has
passed the calibration check.
"""
from __future__ import annotations

import json
import os

from .emit_qasm import bits_from_counts_key, emit_qasm, wires_per_round
from .engine import round_probabilities, simulate_run
from .parse_backend import parse_counts, rounds_from_counts, selfcheck, verify_against_manifest
from .protocol import DETECTION_THRESHOLD, sift
from .rounds import load_manifest, make_rounds, save_manifest

CREDITS_PER_JOB = 5          # Qniverse release notes: CPU simulation = 5 credits
JOB_A_ROUNDS = 12
JOB_B_ROUNDS = 12
JOBS = {
    "A": {"eve": False, "rounds": JOB_A_ROUNDS, "role": "calibration, Eve off"},
    "B": {"eve": True, "rounds": JOB_B_ROUNDS, "role": "Eve on (coherent intercept-resend)"},
}


def calibration_seed(start: int = 20261114, n: int = JOB_A_ROUNDS) -> int:
    """First seed >= start whose Eve-off batch has at least 8 basis-matching
    rounds carrying BOTH bit values, so verify_against_manifest can pass."""
    for seed in range(start, start + 10000):
        rounds = make_rounds(n, False, seed)
        matched = [r for r in rounds if r.alice_basis == r.bob_basis]
        if len(matched) >= 8 and len({r.alice_bit for r in matched}) == 2:
            return seed
    raise RuntimeError("no calibration seed found")


def measure_last(qasm: str) -> str:
    """Same circuit with every measure moved to the end. Each qubit is
    measured once and nothing acts on it afterwards, so the result is
    identical; some editors prefer measurements after all gates."""
    lines = qasm.splitlines()
    body = [l for l in lines if not l.startswith("measure")]
    return "\n".join(body + [l for l in lines if l.startswith("measure")]) + "\n"


def build_plan(out_dir: str, seed: int | None = None) -> dict:
    seed = calibration_seed() if seed is None else seed
    os.makedirs(out_dir, exist_ok=True)
    plan = {"seed": seed, "credits_per_job": CREDITS_PER_JOB,
            "total_credits": CREDITS_PER_JOB * len(JOBS), "jobs": {}}
    for name, spec in JOBS.items():
        rounds = make_rounds(spec["rounds"], spec["eve"], seed)
        mpath = os.path.join(out_dir, f"job-{name}-manifest.json")
        save_manifest(rounds, spec["eve"], seed, mpath)
        qpath = os.path.join(out_dir, f"job-{name}.qasm")
        with open(qpath, "w") as fh:
            fh.write(measure_last(emit_qasm(rounds, spec["eve"])))
        plan["jobs"][name] = {
            "role": spec["role"], "eve": spec["eve"], "rounds": spec["rounds"],
            "qubits": wires_per_round(spec["eve"]) * spec["rounds"],
            "shots": 1, "manifest": os.path.basename(mpath),
            "qasm": os.path.basename(qpath),
        }
    with open(os.path.join(out_dir, "plan.json"), "w") as fh:
        json.dump(plan, fh, indent=2)
    return plan


def load_plan(plan_dir: str) -> dict:
    with open(os.path.join(plan_dir, "plan.json")) as fh:
        return json.load(fh)


def expected_qber(rounds) -> float:
    """Exact expected error rate for THIS manifest on an ideal backend: the
    average over basis-matching rounds of P(Bob's bit != Alice's bit).
    With Eve on this is 0.5 for each sifted round where Eve guessed the
    wrong basis and 0 where she guessed right, so it is 25% only on average
    over random basis choices, not for one 12-round draw."""
    errs = []
    for spec in rounds:
        if spec.alice_basis != spec.bob_basis:
            continue
        probs = round_probabilities(spec)
        p_bob1 = probs[1] + probs[3]
        errs.append((1 - p_bob1) if spec.alice_bit else p_bob1)
    return round(sum(errs) / len(errs), 12) if errs else 0.0


def _result_path(results_dir: str, job: str) -> str:
    return os.path.join(results_dir, f"job-{job}-result.json")


def stored_results(results_dir: str) -> dict:
    out = {}
    for job in JOBS:
        p = _result_path(results_dir, job)
        if os.path.exists(p):
            with open(p) as fh:
                out[job] = json.load(fh)
    return out


def import_counts(plan_dir: str, results_dir: str, job: str, counts_text: str,
                  qniverse_job_id: str = "") -> dict:
    """Decode counts pasted from a Qniverse job into a source-labelled result,
    next to the local engine's answer for the very same manifest."""
    if job not in JOBS:
        raise ValueError("job must be A or B")
    plan = load_plan(plan_dir)
    info = plan["jobs"][job]
    rounds, eve, seed = load_manifest(os.path.join(plan_dir, info["manifest"]))
    if job == "B":
        a = stored_results(results_dir).get("A")
        if not a or not a.get("calibration_passed"):
            raise ValueError("import job A (Eve off) first: it must pass the "
                             "bit-order calibration before job B is trusted")
    selfcheck()
    counts = parse_counts(counts_text)
    shots = sum(counts.values())
    if shots > 1:
        return _import_multishot(plan_dir, results_dir, job, info, rounds, eve, seed,
                                 counts, shots, qniverse_job_id)
    bob, eve_bits = rounds_from_counts(counts, len(rounds), eve)
    calibration = None
    if job == "A":
        verify_against_manifest(rounds, bob)   # raises with details on failure
        calibration = True
    res = sift(rounds, bob, eve_bits)
    lbob, leve = simulate_run(rounds, seed)
    lres = sift(rounds, lbob, leve)
    strip = [{"matched": s.alice_basis == s.bob_basis,
              "error": bool(s.alice_basis == s.bob_basis and bob[i] != s.alice_bit)}
             for i, s in enumerate(rounds)]
    out = {
        "job": job, "source": "qniverse", "qniverse_job_id": qniverse_job_id.strip(),
        "role": info["role"], "eve": eve, "rounds": len(rounds), "seed": seed,
        "sifted": len(res.sift_indices), "errors": res.errors, "qber": res.qber,
        "wilson": [res.wilson_low, res.wilson_high],
        "high_error_rate": res.high_error_rate, "threshold": res.threshold,
        "strip": strip, "calibration_passed": calibration, "mode": "single-shot",
        "local": {"source": "local-exact-engine", "sifted": len(lres.sift_indices),
                  "errors": lres.errors, "qber": lres.qber,
                  "high_error_rate": lres.high_error_rate},
        "expected_qber": expected_qber(rounds),
        "reliable_detection": len(res.sift_indices) >= 20,
        "credits_spent_note": f"{CREDITS_PER_JOB} credits per job (published CPU price)",
    }
    if eve and res.eve_qber is not None:
        out["eve_qber"] = res.eve_qber
    os.makedirs(results_dir, exist_ok=True)
    with open(_result_path(results_dir, job), "w") as fh:
        json.dump(out, fh, indent=2)
    return out


def _import_multishot(plan_dir, results_dir, job, info, rounds, eve, seed,
                      counts, shots, qniverse_job_id):
    """The composer may run many shots instead of one. Each round is an
    independent qubit, so the per-qubit frequencies are exact estimates of
    Bob's bit probabilities. The error figure is then the average probability
    that Bob's bit differs from Alice's over basis-matching rounds. This is a
    different statistic from the single-shot count, and is labelled as such."""
    w = wires_per_round(eve) * len(rounds)
    ones = [0] * w
    for key, n in counts.items():
        bits = bits_from_counts_key(key, w)
        for i, b in enumerate(bits):
            if b:
                ones[i] += n
    step = wires_per_round(eve)
    p_bob1 = [ones[r * step] / shots for r in range(len(rounds))]
    matched = [i for i, s in enumerate(rounds) if s.alice_basis == s.bob_basis]
    if not matched:
        raise ValueError("no sifted bits: no basis-matching rounds in this batch")
    p_err = [(1 - p_bob1[i]) if rounds[i].alice_bit else p_bob1[i] for i in matched]
    calibration = None
    if job == "A":
        bob = [1 if p > 0.5 else 0 for p in p_bob1]
        verify_against_manifest(rounds, bob)
        worst = max(p_err)
        if worst > 0.05:
            raise ValueError(
                f"calibration failed: a basis-matching round differs from Alice with "
                f"probability {worst:.2f} on an Eve-off run; expected about 0 on an "
                "ideal simulator. Do not trust this import.")
        calibration = True
    qber = sum(p_err) / len(p_err)
    strip = [{"matched": i in set(matched),
              "error_prob": (p_err[matched.index(i)] if i in set(matched) else None),
              "error": bool(i in set(matched) and p_err[matched.index(i)] > 0.5)}
             for i in range(len(rounds))]
    lbob, leve = simulate_run(rounds, seed)
    lres = sift(rounds, lbob, leve)
    out = {
        "job": job, "source": "qniverse", "qniverse_job_id": qniverse_job_id.strip(),
        "role": info["role"], "eve": eve, "rounds": len(rounds), "seed": seed,
        "mode": f"multi-shot ({shots} shots on the same {len(rounds)} rounds): average per-round mismatch probability",
        "shots": shots, "sifted": len(matched),
        "errors": round(sum(p_err), 2), "qber": qber, "wilson": None,
        "high_error_rate": qber > DETECTION_THRESHOLD, "threshold": DETECTION_THRESHOLD,
        "strip": strip, "calibration_passed": calibration,
        "local": {"source": "local-exact-engine", "sifted": len(lres.sift_indices),
                  "errors": lres.errors, "qber": lres.qber,
                  "high_error_rate": lres.high_error_rate},
        "expected_qber": expected_qber(rounds),
        "reliable_detection": len(matched) >= 20,
        "credits_spent_note": f"{CREDITS_PER_JOB} credits per job (published CPU price)",
    }
    os.makedirs(results_dir, exist_ok=True)
    with open(_result_path(results_dir, job), "w") as fh:
        json.dump(out, fh, indent=2)
    return out
