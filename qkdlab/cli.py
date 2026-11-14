"""Command line entry point.

  python -m qkdlab run --rounds 48 --seed 20261114 [--eve] [--out evidence/run1]
  python -m qkdlab emit-qasm --manifest M.json [--max-wires 24] --out batches/
  python -m qkdlab emit-qsdk --manifest M.json --out batch.py
  python -m qkdlab report --manifest M.json [--backend-output counts.txt ...] [--out report.html]
"""
import argparse
import json
import os

from .emit_qasm import emit_qasm, split_batches
from .emit_qsdk import emit_qsdk
from .engine import simulate_run
from .parse_backend import parse_counts, rounds_from_counts
from .protocol import sift
from .report import render
from .rounds import load_manifest, make_rounds, save_manifest


def _write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def cmd_run(a):
    rounds = make_rounds(a.rounds, a.eve, a.seed)
    bob, eve = simulate_run(rounds, a.seed)
    res = sift(rounds, bob, eve)
    os.makedirs(a.out, exist_ok=True)
    save_manifest(rounds, a.eve, a.seed, os.path.join(a.out, "manifest.json"))
    _write(os.path.join(a.out, "results.json"), json.dumps({
        "backend": "local-exact-engine",
        "bob_bits": bob, "eve_bits": eve,
        "sifted": len(res.sift_indices), "errors": res.errors, "qber": res.qber,
        "wilson95": [res.wilson_low, res.wilson_high],
        "eve_qber": res.eve_qber, "high_error_rate": res.high_error_rate,
        "scenario_eve": a.eve,
    }, indent=2))
    _write(os.path.join(a.out, "report.html"),
           render(rounds, res, eve=a.eve, seed=a.seed, backend="local-exact-engine"))
    verdict = ("HIGH ERROR RATE (possible eavesdropping or noise)"
               if res.high_error_rate else "error rate within expected range")
    print(f"rounds={a.rounds} sifted={len(res.sift_indices)} "
          f"errors={res.errors} QBER={res.qber:.2%} "
          f"wilson95=[{res.wilson_low:.2%},{res.wilson_high:.2%}] {verdict}")
    print(f"evidence written to {a.out}/ (manifest.json, results.json, report.html)")


def cmd_emit_qasm(a):
    rounds, eve, _ = load_manifest(a.manifest)
    os.makedirs(a.out, exist_ok=True)
    for n, (start, batch) in enumerate(split_batches(rounds, eve, a.max_wires)):
        path = os.path.join(a.out, f"batch-{n:02d}-rounds-{start}-{start + len(batch) - 1}.qasm")
        _write(path, emit_qasm(batch, eve))
        print(f"wrote {path} ({len(batch)} rounds, shots=1)")


def cmd_emit_qsdk(a):
    rounds, eve, _ = load_manifest(a.manifest)
    _write(a.out, emit_qsdk(rounds, eve, a.job_name))
    print(f"wrote {a.out} - paste the Qniverse API key, then run in the hosted notebook")


def cmd_report(a):
    rounds, eve, seed = load_manifest(a.manifest)
    if a.backend_output:
        from .parse_backend import selfcheck
        selfcheck()  # key-order convention must pass before trusting imports
        bob_all: list[int] = []
        eve_all: list[int | None] = []
        per = len(rounds) // len(a.backend_output) if not a.batch_size else a.batch_size
        start = 0
        job_ids = []
        for f in a.backend_output:
            counts = parse_counts(open(f).read())
            remaining = len(rounds) - start
            n = min(per, remaining)
            bob, ev = rounds_from_counts(counts, n, eve)
            bob_all += bob
            eve_all += ev
            start += n
        if not eve:
            from .parse_backend import verify_against_manifest
            verify_against_manifest(rounds, bob_all)
            print("venue known-pattern check passed (basis-matching rounds decode to Alice's bits)")
        else:
            print("NOTE: Eve-on manifests are statistical, so the key order is NOT "
                  "verified by this import; run an Eve-off batch first to verify it.")
        bob, eve_bits, backend = bob_all, eve_all, "qniverse"
    else:
        bob, eve_bits = simulate_run(rounds, seed)
        backend = "local-exact-engine"
    res = sift(rounds, bob, eve_bits)
    _write(a.out, render(rounds, res, eve=eve, seed=seed, backend=backend))
    print(f"QBER={res.qber:.2%} high_error_rate={res.high_error_rate} -> {a.out}")


def cmd_serve(a):
    from .webapp import serve
    serve(a.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="qkdlab", description=__doc__)
    sub = p.add_subparsers(required=True)
    r = sub.add_parser("run", help="run a full BB84 exchange on the local exact engine")
    r.add_argument("--rounds", type=int, default=48)
    r.add_argument("--seed", type=int, required=True)
    r.add_argument("--eve", action="store_true")
    r.add_argument("--out", default="evidence/run")
    r.set_defaults(fn=cmd_run)
    e = sub.add_parser("emit-qasm", help="emit OpenQASM 2.0 batches for the Qniverse composer")
    e.add_argument("--manifest", required=True)
    e.add_argument("--max-wires", type=int, default=24)
    e.add_argument("--out", default="batches")
    e.set_defaults(fn=cmd_emit_qasm)
    s = sub.add_parser("emit-qsdk", help="emit a Qniverse QSDK python program")
    s.add_argument("--manifest", required=True)
    s.add_argument("--job-name", default="qkd-lab")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_emit_qsdk)
    q = sub.add_parser("report", help="rebuild the report from a manifest (+ backend counts)")
    q.add_argument("--manifest", required=True)
    q.add_argument("--backend-output", nargs="*", default=None)
    q.add_argument("--batch-size", type=int, default=None)
    q.add_argument("--out", default="report.html")
    q.set_defaults(fn=cmd_report)
    w = sub.add_parser("serve", help="start the local interactive web dashboard (no credits)")
    w.add_argument("--port", type=int, default=8000)
    w.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
