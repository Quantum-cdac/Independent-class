"""Local interactive web dashboard for the BB84 demo (standard library only).

Run:  python -m qkdlab serve --port 8000
Then open http://localhost:8000

Everything is computed by the verified local engine on each Run click; the
page never talks to Qniverse and never spends credits.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import os

from .rounds import make_rounds
from . import venue
from .engine import simulate_run
from .protocol import sift

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QKD-Lab - interactive BB84 demo</title>
<style>
:root { --ink:#1c1a17; --muted:#6b675f; --line:#e3dfd8; --ok:#0d7a4f; --bad:#c03a2b; --accent:#2557d6; --bg:#f7f5f1; --card:#ffffff; }
* { box-sizing: border-box; }
body { margin:0; font:15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; background:var(--bg); color:var(--ink); }
.wrap { max-width:880px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:24px; margin:0 0 2px; }
.sub { color:var(--muted); margin:0 0 20px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px; margin-bottom:16px; }
.controls { display:flex; flex-wrap:wrap; gap:14px; align-items:flex-end; }
.field label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
.field input[type=number] { width:110px; padding:8px 10px; border:1px solid var(--line); border-radius:8px; font:inherit; }
.toggle { display:flex; align-items:center; gap:8px; padding:8px 12px; border:1px solid var(--line); border-radius:8px; cursor:pointer; user-select:none; }
.toggle input { accent-color:var(--bad); width:18px; height:18px; }
button.run { padding:10px 22px; font:inherit; font-weight:600; color:#fff; background:var(--accent); border:0; border-radius:8px; cursor:pointer; }
button.run:disabled { opacity:.5; cursor:wait; }
.banner { border-radius:10px; padding:12px 16px; font-weight:600; margin-bottom:14px; }
.banner.ok { background:#e7f5ee; color:var(--ok); border:1px solid #bfe4d2; }
.banner.bad { background:#fdecea; color:var(--bad); border:1px solid #f3c5be; }
.banner small { display:block; font-weight:400; margin-top:2px; }
.stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(130px,1fr)); gap:10px; margin-bottom:14px; }
.stat { border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
.stat b { display:block; font-size:20px; }
.stat span { font-size:12px; color:var(--muted); }
.strip { display:flex; flex-wrap:wrap; gap:3px; margin:8px 0 4px; }
.bit { width:14px; height:22px; border-radius:3px; background:#ddd8d0; }
.bit.keep { background:var(--ok); }
.bit.err { background:var(--bad); }
.legend { font-size:12px; color:var(--muted); display:flex; gap:16px; margin-bottom:6px; }
.sw { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
.gauge { position:relative; height:26px; background:#eee9e1; border-radius:13px; overflow:hidden; margin:6px 0 4px; }
.gauge .fill { position:absolute; inset:0 auto 0 0; background:var(--ok); border-radius:13px; transition:width .4s; }
.gauge.hot .fill { background:var(--bad); }
.gauge .mark { position:absolute; top:-2px; bottom:-2px; width:2px; background:var(--ink); }
.glabel { display:flex; justify-content:space-between; font-size:12px; color:var(--muted); }
.compare { font-size:13px; color:var(--muted); }
.notes { font-size:13px; color:var(--muted); }
.notes li { margin:4px 0; }
.evebox { border:1px dashed var(--bad); border-radius:10px; padding:10px 12px; margin-top:10px; font-size:13px; }
code { background:#f0ede7; padding:1px 5px; border-radius:4px; }
.qnjob { border:1px solid var(--line); border-radius:10px; padding:12px; margin-top:10px; }
.qnjob h3 { margin:0 0 6px; font-size:14px; }
.qnjob textarea { width:100%; min-height:54px; font:12px monospace; border:1px solid var(--line); border-radius:8px; padding:8px; }
.qnjob input[type=text] { width:100%; padding:7px 9px; border:1px solid var(--line); border-radius:8px; font:inherit; margin-bottom:6px; }
.tag { display:inline-block; font-size:11px; font-weight:700; padding:2px 8px; border-radius:99px; margin-right:6px; }
.tag.qn { background:#e8eefc; color:var(--accent); }
.tag.loc { background:#eee9e1; color:var(--muted); }
.qnerr { color:var(--bad); font-size:13px; margin-top:6px; }
.qnrow { display:flex; flex-wrap:wrap; gap:14px; font-size:13px; margin:6px 0; }
</style>
</head>
<body>
<div class="wrap">
  <h1>QKD-Lab: interactive BB84 demo</h1>
  <p class="sub">Alice and Bob build a shared key over a quantum channel. Flip the eavesdropper on and watch what happens to the error rate.</p>

  <div class="card">
    <div class="controls">
      <div class="field"><label for="rounds">Rounds</label><input id="rounds" type="number" min="8" max="500" value="48"></div>
      <div class="field"><label for="seed">Seed (same seed = same run)</label><input id="seed" type="number" min="0" value="20261114"></div>
      <label class="toggle"><input id="eve" type="checkbox"> Eve is listening</label>
      <button class="run" id="go">Run experiment</button>
    </div>
  </div>

  <div class="card" id="results" hidden>
    <div class="banner" id="banner"></div>
    <div class="stats">
      <div class="stat"><b id="s-rounds">-</b><span>rounds sent</span></div>
      <div class="stat"><b id="s-sift">-</b><span>sifted key bits</span></div>
      <div class="stat"><b id="s-err">-</b><span>mismatched bits</span></div>
      <div class="stat"><b id="s-qber">-</b><span>error rate (QBER)</span></div>
      <div class="stat"><b id="s-wil">-</b><span>95% Wilson interval</span></div>
    </div>
    <div class="glabel"><span>0%</span><span>QBER - marker: 11% demo rule</span><span>25%+</span></div>
    <div class="gauge" id="gauge"><div class="fill" id="fill"></div><div class="mark" style="left:44%"></div></div>
    <div class="legend"><span><i class="sw" style="background:var(--ok)"></i>sifted, bits agree</span><span><i class="sw" style="background:var(--bad)"></i>sifted, bits differ</span><span><i class="sw" style="background:#ddd8d0"></i>bases differ - discarded</span></div>
    <div class="strip" id="strip"></div>
    <div class="evebox" id="evebox" hidden></div>
    <p class="compare" id="compare"></p>
  </div>

  <div class="card" id="qn">
    <h2 style="margin:0 0 4px;font-size:17px">Qniverse results <span style="font-weight:400;color:var(--muted);font-size:13px">(real job output, labelled by source)</span></h2>
    <p class="compare" id="qn-intro">Nothing from Qniverse has been loaded yet. The experiment above is the local engine. After running the two planned jobs on Qniverse (10 credits total), paste each job's counts here to compare them with the local engine on the same rounds.</p>
    <div id="qn-jobs"></div>
  </div>

  <div class="card notes">
    <ul>
      <li>This is an <b>educational local simulation</b> of BB84 with an intercept-resend eavesdropper, computed by the project's verified engine on every run - nothing is pre-baked.</li>
      <li>The 11% marker is an <b>illustrative classroom rule</b>, not a security certificate. A noisy channel can also raise the error rate.</li>
      <li>Zero errors in a short run does not prove zero risk - the Wilson interval shows the uncertainty.</li>
      <li>The experiment at the top never calls Qniverse. The Qniverse card only decodes counts that a person pasted from a real Qniverse job, and it never submits jobs or spends credits.</li>
    </ul>
  </div>
</div>
<script>
const $ = id => document.getElementById(id);
let last = null;

async function run() {
  const rounds = Math.max(8, Math.min(500, +$("rounds").value || 48));
  const seed = +$("seed").value || 0;
  const eve = $("eve").checked;
  $("go").disabled = true;
  try {
    const r = await fetch(`/api/run?rounds=${rounds}&seed=${seed}&eve=${eve?1:0}`);
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    render(d);
  } catch (e) {
    alert("Run failed: " + e.message);
  } finally { $("go").disabled = false; }
}

function pct(x) { return (x*100).toFixed(2) + "%"; }

function render(d) {
  $("results").hidden = false;
  const b = $("banner");
  if (d.high_error_rate) {
    b.className = "banner bad";
    b.innerHTML = "HIGH ERROR RATE: possible eavesdropping or channel noise<small>Observed " + d.errors + " of " + d.sifted + " sifted bits differ - above the 11% illustrative demo rule. The scenario toggle says Eve is " + (d.eve ? "ON" : "OFF") + "; the detector itself cannot tell eavesdropping from noise.</small>";
  } else {
    b.className = "banner ok";
    b.innerHTML = "ERROR RATE WITHIN EXPECTED RANGE<small>Observed " + d.errors + " of " + d.sifted + " sifted bits differ. Eve is " + (d.eve ? "ON" : "OFF") + " in this scenario.</small>";
  }
  $("s-rounds").textContent = d.rounds;
  $("s-sift").textContent = d.sifted;
  $("s-err").textContent = d.errors;
  $("s-qber").textContent = pct(d.qber);
  $("s-wil").textContent = "[" + pct(d.wilson[0]) + ", " + pct(d.wilson[1]) + "]";
  const g = $("gauge");
  g.classList.toggle("hot", d.high_error_rate);
  $("fill").style.width = Math.min(100, d.qber / 0.25 * 100) + "%";
  const strip = $("strip");
  strip.innerHTML = "";
  d.strip.forEach((s, i) => {
    const el = document.createElement("div");
    el.className = "bit" + (!s.matched ? "" : s.error ? " err" : " keep");
    el.title = "round " + i + (s.matched ? (s.error ? ": sifted, bits differ" : ": sifted, bits agree") : ": bases differ, discarded");
    strip.appendChild(el);
  });
  if (d.eve) {
    $("evebox").hidden = false;
    $("evebox").innerHTML = "<b>Eve's view:</b> she guessed the basis correctly on " + d.eve_right + " of " + d.rounds + " rounds. Her copy of the sifted key disagrees with Alice's on " + pct(d.eve_qber) + " of bits - and her interference is what raised Bob's error rate.";
  } else { $("evebox").hidden = true; }
  if (last && (last.eve !== d.eve) && last.seed === d.seed && last.rounds === d.rounds) {
    $("compare").textContent = "Same seed and rounds as the previous run - only the Eve setting changed: error rate went from " + pct(last.qber) + " to " + pct(d.qber) + ".";
  } else { $("compare").textContent = ""; }
  last = d;
}

$("go").addEventListener("click", run);
const q = new URLSearchParams(location.search);
if (q.get("rounds")) $("rounds").value = q.get("rounds");
if (q.get("seed")) $("seed").value = q.get("seed");
if (q.get("eve")) $("eve").checked = q.get("eve") === "1";
run();

function esc(t) { const d = document.createElement("div"); d.textContent = String(t); return d.innerHTML; }
function jobStrip(strip) {
  return strip.map((x, i) => '<div class="bit' + (!x.matched ? '' : x.error ? ' err' : ' keep') + '" title="round ' + i + '"></div>').join("");
}
function jobCard(name, info, res) {
let h = '<div class="qnjob"><h3>Job ' + name + ': ' + esc(info.role) + ' (' + info.rounds + ' rounds, ' + info.qubits + ' qubits; ' + (res ? 'this result: ' + (res.shots ? res.shots + ' shots' : '1 shot') : 'plan: 1 shot, more is accepted') + ')</h3>';
  if (res) {
    const cal = res.calibration_passed ? ' Bit-order calibration passed.' : '';
    const qnTxt = res.wilson
      ? res.errors + ' of ' + res.sifted + ' sifted bits differ, QBER ' + pct(res.qber) + ', Wilson [' + pct(res.wilson[0]) + ', ' + pct(res.wilson[1]) + ']'
      : 'over ' + res.sifted + ' sifted rounds, the average mismatch probability between Alice and Bob is ' + pct(res.qber) + ' (measured from ' + res.shots + ' shots of the same ' + res.rounds + ' rounds, not ' + res.sifted + ' independent trials)';
    h += '<div class="qnrow"><span><span class="tag qn">QNIVERSE job ' + esc(res.qniverse_job_id || "id not given") + '</span>' + qnTxt + '</span></div>';
    if (res.provenance && res.provenance.backend) h += '<div class="qnrow"><span>Job page: ' + esc(res.provenance.resource) + ', backend ' + esc(res.provenance.backend) + ', noise used: ' + esc(res.provenance.noise_used) + ', status ' + esc(res.provenance.status) + ', created ' + esc(res.provenance.created) + ' (' + esc(res.provenance.source) + '). Credits charged: not shown.</span></div>';
    h += '<div class="qnrow"><span><span class="tag loc">LOCAL engine, one sample of the same rounds</span>' + res.local.errors + ' of ' + res.local.sifted + ' sifted bits differ, QBER ' + pct(res.local.qber) + '</span></div>';
    h += '<div class="strip">' + jobStrip(res.strip) + '</div>';
    h += '<p class="compare">' + (res.high_error_rate ? 'Above the 11% demo rule.' : 'Below the 11% demo rule.') + cal + (res.eve && !res.reliable_detection ? ' Only ' + res.sifted + ' bits survived sifting, so this run shows the circuit working on Qniverse but is not a reliable detection.' : '') + ' Expected QBER for this exact set of rounds on an ideal backend: ' + pct(res.expected_qber) + ' (Eve gives about 25% only on average over many random rounds; this draw has Eve guessing right or wrong on specific rounds).' + (res.shots ? ' The ' + res.shots + ' shots repeat the same ' + res.rounds + ' rounds, so they cut measurement noise but not the luck of the round choices.' : '') + '</p>';
  }
  h += '<input type="text" id="jid-' + name + '" placeholder="Qniverse job ID (optional)">';
  h += '<textarea id="cnt-' + name + '" placeholder="Paste the counts for job ' + name + ', for example 011010...=1 or {&quot;0110...&quot;: 1}"></textarea>';
  h += '<button class="run" style="margin-top:8px;padding:7px 16px" data-job="' + name + '">' + (res ? 'Replace result' : 'Decode counts') + '</button>';
  h += '<div class="qnerr" id="err-' + name + '"></div></div>';
  return h;
}
async function loadQn() {
  const r = await fetch("/api/qniverse"); const d = await r.json();
  if (!d.plan) { $("qn-jobs").innerHTML = '<p class="compare">No plan found. Run <code>python -m qkdlab plan</code> first.</p>'; return; }
  const got = Object.keys(d.results).length;
  if (got) {
    const a = d.results.A, b = d.results.B;
    const st = (a && a.calibration_passed ? "Job A (Eve off) calibration passed: bit order checked on this run. " : "") + (b ? "Job B (Eve on) result loaded." : "Job B (Eve on) is still pending, so no eavesdropper result from Qniverse yet.");
    $("qn-intro").textContent = st + " Counts were pasted by a person and decoded by the same sifting code as the local engine. Each line is tagged with its source.";
  }
  $("qn-jobs").innerHTML = Object.keys(d.plan.jobs).map(n => jobCard(n, d.plan.jobs[n], d.results[n])).join("");
  document.querySelectorAll("#qn-jobs button[data-job]").forEach(b => b.addEventListener("click", () => importJob(b.dataset.job)));
}
async function importJob(name) {
  $("err-" + name).textContent = "";
  const body = { job: name, counts: $("cnt-" + name).value, job_id: $("jid-" + name).value };
  const r = await fetch("/api/import", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
  const d = await r.json();
  if (d.error) { $("err-" + name).textContent = d.error; return; }
  loadQn();
}
loadQn();
</script>
</body>
</html>
"""

MAX_ROUNDS = 500
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN_DIR = os.path.join(_ROOT, "evidence", "venue-plan")
RESULTS_DIR = os.path.join(_ROOT, "evidence", "qniverse")


def run_experiment(rounds: int, seed: int, eve: bool) -> dict:
    """Run the verified local engine and shape the JSON the page renders."""
    rounds = max(8, min(MAX_ROUNDS, int(rounds)))
    specs = make_rounds(rounds, eve, seed)
    bob, eve_bits = simulate_run(specs, seed)
    res = sift(specs, bob, eve_bits)
    strip = []
    for i, spec in enumerate(specs):
        matched = spec.alice_basis == spec.bob_basis
        strip.append({
            "matched": matched,
            "error": bool(matched and bob[i] != spec.alice_bit),
        })
    out = {
        "rounds": rounds,
        "seed": seed,
        "eve": eve,
        "sifted": len(res.sift_indices),
        "errors": res.errors,
        "qber": res.qber,
        "wilson": [res.wilson_low, res.wilson_high],
        "threshold": res.threshold,
        "high_error_rate": res.high_error_rate,
        "strip": strip,
    }
    if eve and res.eve_qber is not None:
        out["eve_qber"] = res.eve_qber
        out["eve_right"] = sum(1 for s in specs if s.eve_basis == s.alice_basis)
    return out


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep the console quiet
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlparse(self.path).path == "/api/import":
            out, code = _post_import(self)
            self._send(json.dumps(out).encode(), "application/json", code)
        else:
            self._send(b'{"error":"not found"}', "application/json", 404)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/run":
            q = parse_qs(url.query)
            try:
                rounds = int(q.get("rounds", ["48"])[0])
                seed = int(q.get("seed", ["0"])[0])
                eve = q.get("eve", ["0"])[0] == "1"
                body = json.dumps(run_experiment(rounds, seed, eve)).encode()
            except (ValueError, IndexError) as e:
                body = json.dumps({"error": f"bad parameters: {e}"}).encode()
                self._send(body, "application/json", 400)
                return
            self._send(body, "application/json")
        elif url.path == "/api/qniverse":
            try:
                plan = venue.load_plan(PLAN_DIR)
            except OSError:
                plan = None
            body = json.dumps({"plan": plan, "results": venue.stored_results(RESULTS_DIR)
                               if plan else {}}).encode()
            self._send(body, "application/json")
        elif url.path in ("/", "/index.html"):
            self._send(PAGE.encode(), "text/html; charset=utf-8")
        else:
            self._send(b'{"error":"not found"}', "application/json", 404)


def _post_import(handler):
    try:
        n = int(handler.headers.get("Content-Length", "0"))
        req = json.loads(handler.rfile.read(min(n, 200000)) or b"{}")
        out = venue.import_counts(PLAN_DIR, RESULTS_DIR, str(req.get("job", "")),
                                  str(req.get("counts", "")), str(req.get("job_id", ""))[:80])
        return out, 200
    except (ValueError, KeyError, OSError, AssertionError) as e:
        return {"error": str(e)}, 400


def serve(port: int = 8000) -> None:
    httpd = HTTPServer(("127.0.0.1", port), _Handler)
    print(f"QKD-Lab dashboard: open http://localhost:{port}  (Ctrl+C to stop)")
    httpd.serve_forever()
