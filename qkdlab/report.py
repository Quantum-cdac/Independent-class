"""Self-contained HTML report for one run: no external assets, inline SVG."""
import html
import json

from .protocol import SiftResult
from .rounds import RoundSpec


def _gauge(qber: float, threshold: float) -> str:
    pct = min(100.0, qber * 100 * 2.2)  # scale so 45% fills the bar
    tpct = min(100.0, threshold * 100 * 2.2)
    color = "#c0392b" if qber > threshold else "#27ae60"  # red = above demo rule
    return f"""
<svg width="560" height="46" role="img" aria-label="QBER gauge">
  <rect x="0" y="12" width="560" height="22" fill="#ecf0f1" rx="4"/>
  <rect x="0" y="12" width="{pct * 5.6:.1f}" height="22" fill="{color}" rx="4"/>
  <line x1="{tpct * 5.6:.1f}" y1="6" x2="{tpct * 5.6:.1f}" y2="40" stroke="#2c3e50" stroke-width="2"/>
  <text x="{tpct * 5.6 + 6:.1f}" y="10" font-size="11" fill="#2c3e50">illustrative demo rule {threshold:.0%}</text>
</svg>"""


def _sift_table(rounds: list[RoundSpec], res: SiftResult, limit: int = 32) -> str:
    rows = []
    pos = {idx: k for k, idx in enumerate(res.sift_indices)}
    for i in range(min(limit, len(rounds))):
        r = rounds[i]
        kept = i in pos
        cells = [
            str(i), str(r.alice_bit),
            "X" if r.alice_basis else "Z",
            "X" if r.bob_basis else "Z",
        ]
        if r.eve_basis is not None:
            cells.append("X" if r.eve_basis else "Z")
        if kept:
            k = pos[i]
            match = res.alice_key[k] == res.bob_key[k]
            cells += [str(res.bob_key[k]), "keep", "ok" if match else "ERR"]
            cls = "ok" if match else "err"
        else:
            cells += ["-", "drop", "-"]
            cls = "drop"
        rows.append(f'<tr class="{cls}"><td>' + "</td><td>".join(cells) + "</td></tr>")
    eve_h = "<th>Eve basis</th>" if rounds and rounds[0].eve_basis is not None else ""
    return f"""<table>
<tr><th>#</th><th>Alice bit</th><th>Alice basis</th><th>Bob basis</th>{eve_h}<th>Bob got</th><th>sift</th><th>check</th></tr>
{''.join(rows)}
</table>
<p class="muted">Showing first {min(limit, len(rounds))} rounds. Bases: Z = rectilinear, X = diagonal. Rounds where the bases differ are dropped.</p>"""


def render(rounds: list[RoundSpec], res: SiftResult, *, eve: bool, seed: int,
           backend: str, job_ids: list[str] | None = None) -> str:
    if res.high_error_rate:
        verdict = ("HIGH ERROR RATE: possible eavesdropping or channel noise", "bad")
    else:
        verdict = ("ERROR RATE WITHIN EXPECTED RANGE", "good")
    n = len(rounds)
    sifted = len(res.sift_indices)
    jobs = ", ".join(job_ids) if job_ids else "n/a (local exact engine)"
    eve_block = ""
    if res.eve_qber is not None:
        eve_block = f"""
<h2>What Eve learned</h2>
<p>Eve's own sifted copy disagrees with Alice on {res.eve_qber:.1%} of bits - her interference is exactly what Bob's error rate reveals.</p>"""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QKD-Lab run report</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 780px; color: #2c3e50; padding: 0 1rem; }}
 .banner {{ padding: 1rem 1.2rem; border-radius: 8px; font-size: 1.25rem; font-weight: 700; }}
 .good {{ background: #eafaf1; color: #1e8449; border: 1px solid #27ae60; }}
 .bad {{ background: #fdedec; color: #c0392b; border: 1px solid #c0392b; }}
 table {{ border-collapse: collapse; font-size: 0.85rem; }}
 td, th {{ border: 1px solid #d5dbdb; padding: 2px 8px; text-align: center; }}
 tr.err td {{ background: #fdedec; }} tr.ok td {{ background: #eafaf1; }} tr.drop td {{ color: #95a5a6; }}
 .muted {{ color: #7f8c8d; font-size: 0.85rem; }}
 dl {{ display: grid; grid-template-columns: 220px 1fr; row-gap: 4px; }}
 dt {{ font-weight: 600; }} dd {{ margin: 0; }}
</style></head><body>
<h1>QKD-Lab &mdash; BB84 run report</h1>
<div class="banner {verdict[1]}">{verdict[0]}</div>
<h2>Quantum bit error rate (QBER)</h2>
{_gauge(res.qber, res.threshold)}
<dl>
 <dt>Observed errors</dt><dd>{res.errors} of {sifted} sifted bits ({res.qber:.2%})</dd>
 <dt>True error rate (95% Wilson interval)</dt><dd>[{res.wilson_low:.2%}, {res.wilson_high:.2%}]</dd>
 <dt>Rounds executed</dt><dd>{n}</dd>
 <dt>Sifted key length</dt><dd>{sifted} bits</dd>
 <dt>Scenario configured</dt><dd>{'eavesdropper simulation ON (intercept-resend, coherent model) - the detector only sees the error rate, not this setting' if eve else 'eavesdropper simulation OFF'}</dd>
 <dt>Seed</dt><dd>{seed}</dd>
 <dt>Backend</dt><dd>{html.escape(backend)}</dd>
 <dt>Job IDs</dt><dd>{html.escape(jobs)}</dd>
</dl>
<h2>Round-by-round sifting</h2>
{_sift_table(rounds, res)}
{eve_block}
<p class="muted">QKD-Lab is an educational BB84 simulation. The {res.threshold:.0%} rule is an
illustrative classroom threshold, not a security certificate: a high error rate can come
from an eavesdropper or from noise, and a clean run bounds risk rather than proving it
absent. This tool does not provide production key distribution, error correction,
privacy amplification or a security proof.</p>
</body></html>"""
