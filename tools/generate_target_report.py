#!/usr/bin/env python3
"""
Resilience report: compiles every target_runs/<name>/<run_ts>/verdicts.json
into one self-contained HTML page with two axes per attack (per the tool's
whole premise, see tools/test_target.py's module docstring) PLUS the two
things a target_runs/ table alone doesn't give a reader:

  - a RECOMMENDATION next to every VULNERABLE finding and every
    detectability gap -- "what to improvise," not just a verdict, per the
    project's actual goal (a vehicle team should walk away with a punch
    list, not a label);
  - one synthesized top-line DEPLOYMENT-READINESS verdict per target --
    ready / conditionally ready / not ready -- not per-attack rows left for
    the reader to interpret and total up themselves.

Reuses tools/score_detectors.py's/tools/generate_report.py's rendering
where the shape matches (render_family_table for detectability -- a target
run's own verdicts.json already carries score()'s output, computed once by
test_target.py, never recomputed here) rather than forking it.

Usage:
  python3 tools/generate_target_report.py [--out target_runs/resilience_report.html]

Reads only target_runs/*/*/verdicts.json (already-computed, already
isolated from attack_logs/ and evidence/ per tools/test_target.py's own
isolation rule) -- never launches a test itself.
"""
import argparse
import csv
import glob
import html
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_RUNS = os.path.join(REPO, "target_runs")
sys.path.insert(0, os.path.join(REPO, "tools"))
from generate_report import render_family_table, _pct  # noqa: E402


def discover_target_runs():
    """Latest verdicts.json per target (run_ts is %Y%m%dT%H%M%S, so
    lexicographic sort is chronological)."""
    latest = {}
    for path in glob.glob(os.path.join(TARGET_RUNS, "*", "*", "verdicts.json")):
        target = os.path.basename(os.path.dirname(os.path.dirname(path)))
        if target not in latest or path > latest[target]:
            latest[target] = path
    return dict(sorted(latest.items()))


# --- recommendations: what to improvise, not just a label -------------------

_RECOMMENDATIONS = {
    ("c2_replay", "mode_change"): (
        "Enable MAVLink2 message signing (the SIGNING_KEY parameter) so an unsigned forged "
        "mode-change command is rejected outright. SYSID_MYGCS filtering alone is not "
        "sufficient -- it's a plain, unauthenticated header field, trivially spoofed by anyone "
        "who knows (or guesses) the expected system ID."
    ),
    ("c2_replay", "rc_override"): (
        "Enable MAVLink2 message signing so an unsigned RC-override is rejected outright, not "
        "just filtered by sender system ID (confirmed in this project's own testing: ArduPilot "
        "silently drops RC_CHANNELS_OVERRIDE from an unexpected SYSID_MYGCS with zero error -- "
        "a real but weak, spoofable control on its own)."
    ),
    ("gps_spoof", "vulnerability"): (
        "The autopilot's position estimate followed the forged input with no apparent "
        "rejection. Consider multi-GPS blending (GPS_BLEND) or an independent EKF "
        "innovation/consistency check (cross-referencing against IMU-based dead reckoning) so "
        "a sudden implausible jump is flagged and gated rather than trusted outright."
    ),
}

_DETECTABILITY_GAP_NOTES = {
    "c2_replay": ("The current rule-based monitor (detection/detectors.py's C2OverrideDetector) "
                   "only watches for RC-override signatures -- it does not catch mode-change "
                   "forgery at all. If mode-change hijacking matters for this vehicle's "
                   "operating profile, that's a real, separate monitoring gap to close."),
    "gps_spoof": ("A slow/gradual position drift can fall below a jump-speed-based detector's "
                   "threshold by design (confirmed in this project's own testing: a 0.5 m/s ramp "
                   "profile scored 0.0 recall against detection/detectors.py's GpsJumpDetector, "
                   "which is built to catch sudden discontinuities, not stealthy drift). If a "
                   "slow-drift attack is a realistic threat model here, that detector needs a "
                   "complementary slow-drift check, not just a jump check."),
    "ais_spoof": None,
}


def _walk_subchecks(attacks):
    """attacks: verdicts.json's "attacks" dict. c2_replay carries two named
    sub-checks directly (mode_change, rc_override); gps_spoof/ais_spoof each
    carry exactly one, always named "vulnerability". Yields
    (attack, subcheck_name, verdict, evidence) uniformly across both shapes."""
    for attack, subchecks in attacks.items():
        for subname, result in subchecks.items():
            yield attack, subname, result["verdict"], result.get("evidence", {})


def _deployment_verdict(verdicts):
    vulnerable, inconclusive = [], []
    for attack, subname, verdict, _ in _walk_subchecks(verdicts.get("attacks", {})):
        if verdict == "VULNERABLE":
            vulnerable.append((attack, subname))
        elif verdict == "INCONCLUSIVE":
            inconclusive.append((attack, subname))
    if vulnerable:
        return "NOT READY TO DEPLOY", "not-ready", vulnerable, inconclusive
    if inconclusive:
        return "CONDITIONALLY READY -- retest needed", "conditional", vulnerable, inconclusive
    return "READY (against the attacks tested)", "ready", vulnerable, inconclusive


def render_vulnerability_panel(verdicts):
    rows = []
    for attack, subname, verdict, evidence in _walk_subchecks(verdicts.get("attacks", {})):
        cls = {"VULNERABLE": "v-bad", "RESILIENT": "v-good", "N/A": "v-na", "INCONCLUSIVE": "v-warn"}.get(verdict, "")
        reason = evidence.get("reason") or evidence.get("caveat") or ""
        evidence_str = ", ".join(f"{k}={v}" for k, v in evidence.items() if k not in ("reason", "caveat") and v is not None)
        rec = _RECOMMENDATIONS.get((attack, subname), "") if verdict == "VULNERABLE" else ""
        rows.append(f"""
        <tr>
          <td>{html.escape(attack)}</td>
          <td>{html.escape(subname)}</td>
          <td class="{cls}"><b>{html.escape(verdict)}</b></td>
          <td class="ev">{html.escape(evidence_str)}{'<br><i>' + html.escape(reason) + '</i>' if reason else ''}</td>
          <td class="rec">{html.escape(rec)}</td>
        </tr>""")
    if not rows:
        return '<p class="missing">No attacks were run against this target.</p>'
    return f"""
    <table class="detail">
      <thead><tr><th>Attack</th><th>Sub-check</th><th>Verdict</th><th>Evidence</th><th>Recommendation</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


def render_detectability_gaps(verdicts):
    families = verdicts.get("detectability", {}).get("families", {})
    notes = []
    for fam, r in families.items():
        if r.get("windows", 0) > 0 and (r.get("recall") or 0) < 1.0:
            note = _DETECTABILITY_GAP_NOTES.get(fam)
            if note:
                notes.append(f"<li><b>{html.escape(fam)}</b> (recall {_pct(r['recall'])}): {html.escape(note)}</li>")
    if not notes:
        return ""
    return f'<div class="gaps"><h4>Detectability gaps</h4><ul>{"".join(notes)}</ul></div>'


# --- timeline: merge each run's own injection log + detection alerts -------
# Both already exist per-run (test_target.py writes *_ground_truth.csv via
# _log_ground_truth, and alerts.jsonl via the same DetectorSuite tap used for
# scoring) -- this reads them back, never recomputes anything, so a
# regenerated report can never disagree with the verdict it's explaining.

def _load_timeline(run_dir):
    """Every (wall_ts, kind, text) event in a run directory, sorted. `kind`
    is "inject" (from a *_ground_truth.csv) or "detect" (from alerts.jsonl)."""
    events = []
    for csv_path in glob.glob(os.path.join(run_dir, "*_ground_truth.csv")):
        try:
            with open(csv_path, newline="") as f:
                for row in csv.DictReader(f):
                    events.append((float(row["wall_ts"]), "inject",
                                   f"{row.get('attack_type', '?')}: {row.get('description', '')}"))
        except (OSError, ValueError, KeyError):
            continue
    alerts_path = os.path.join(run_dir, "alerts.jsonl")
    if os.path.isfile(alerts_path):
        with open(alerts_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                    events.append((float(a["t"]), "detect", f"{a.get('detector', '?')}: {a.get('detail', '')}"))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    events.sort(key=lambda e: e[0])
    return events


def render_timeline(run_dir):
    events = _load_timeline(run_dir)
    if not events:
        return ""
    t0 = events[0][0]
    rows = []
    for t, kind, text in events:
        label = "INJECTED" if kind == "inject" else "DETECTED"
        cls = "tl-inject" if kind == "inject" else "tl-detect"
        rows.append(f'<tr class="{cls}"><td>t+{t - t0:.2f}s</td><td>{label}</td>'
                     f'<td>{html.escape(text)}</td></tr>')
    return f"""
    <h3>Timeline (raw evidence)</h3>
    <table class="detail timeline">
      <thead><tr><th>Elapsed</th><th>Event</th><th>Detail</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


# --- executive summary: plain-language synthesis, no jargon ----------------

_ATTACK_PLAIN = {
    "gps_spoof": "GPS spoofing",
    "ais_spoof": "AIS (vessel identity) spoofing",
    "c2_replay": "command-and-control hijacking",
}
_SUBCHECK_PLAIN = {
    "mode_change": "forging a flight-mode change",
    "rc_override": "seizing direct throttle/steering control",
    "vulnerability": "",
}


def _plain_finding(attack, subname):
    a = _ATTACK_PLAIN.get(attack, attack)
    s = _SUBCHECK_PLAIN.get(subname, subname)
    return f"{a} via {s}" if s else a


def render_executive_summary(target, verdicts):
    headline, cls, vulnerable, inconclusive = _deployment_verdict(verdicts)
    domain = verdicts.get("domain", "vehicle")
    sentences = [f"<b>{html.escape(target)}</b> ({html.escape(domain)}) was tested against every "
                 f"attack this tool supports and the result is <b class=\"v-{cls}\">{html.escape(headline)}</b>."]
    if vulnerable:
        plain = "; ".join(_plain_finding(a, s) for a, s in vulnerable)
        sentences.append(f"An attacker on the same network could succeed at: {html.escape(plain)}. "
                          f"These are real, live-demonstrated findings, not theoretical -- see the "
                          f"timeline and raw evidence below for exactly what was sent and what the "
                          f"vehicle did in response.")
    else:
        sentences.append("No attack in this test suite corrupted the vehicle's own reported state.")
    if inconclusive:
        plain = "; ".join(_plain_finding(a, s) for a, s in inconclusive)
        sentences.append(f"{html.escape(plain)} could not be conclusively tested this run (see the "
                          f"evidence for why) -- treat as unproven, not as resilient, until retested.")
    det = verdicts.get("detectability", {}).get("overall", {})
    if det.get("windows"):
        sentences.append(f"A blind rule-based monitor watching the same traffic caught "
                          f"{det.get('detected', 0)} of {det.get('windows', 0)} attack windows "
                          f"(recall {_pct(det.get('recall'))}, precision {_pct(det.get('precision'))}) "
                          f"-- this is independent of whether the attack itself succeeded.")
    return f'<div class="execsum">{" ".join(sentences)}</div>'


def build_report(target_paths):
    generated = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    summary_rows = []
    detail_sections = []

    for target, path in target_paths.items():
        with open(path) as f:
            verdicts = json.load(f)
        headline, cls, vulnerable, inconclusive = _deployment_verdict(verdicts)
        det = verdicts.get("detectability", {}).get("overall", {})

        summary_rows.append(f"""
        <tr>
          <td>{html.escape(target)}</td>
          <td>{html.escape(verdicts.get('domain', '?'))}</td>
          <td class="v-{cls}"><b>{html.escape(headline)}</b></td>
          <td>{len(vulnerable)}</td>
          <td>{len(inconclusive)}</td>
          <td>{_pct(det.get('recall'))}</td>
        </tr>""")

        run_dir = os.path.dirname(path)
        detail_sections.append(f"""
    <section class="profile">
      <h2>{html.escape(target)} <span class="domain">({html.escape(verdicts.get('domain', '?'))})</span></h2>
      <p class="src">Run {html.escape(verdicts.get('run_ts', '?'))}, from
         <code>{html.escape(os.path.relpath(path, REPO))}</code>.</p>
      <div class="headline v-{cls}">{html.escape(headline)}</div>
      {render_executive_summary(target, verdicts)}
      <h3>Vulnerability</h3>
      {render_vulnerability_panel(verdicts)}
      {render_timeline(run_dir)}
      <h3>Detectability</h3>
      <table class="detail">
        <thead>
          <tr>
            <th>Attack</th><th>TP</th><th>FP</th><th>FP rate</th><th>Windows detected</th>
            <th>Precision</th><th>Recall</th><th>Mean latency</th><th>p95 latency</th><th>Max latency</th>
          </tr>
        </thead>
        <tbody>{render_family_table(verdicts.get('detectability', {}).get('families', {}))}</tbody>
      </table>
      {render_detectability_gaps(verdicts)}
    </section>""")

    summary_table = f"""
    <table class="summary">
      <thead>
        <tr>
          <th>Target</th><th>Domain</th><th>Deployment readiness</th>
          <th>Vulnerable findings</th><th>Inconclusive</th><th>Detectability recall</th>
        </tr>
      </thead>
      <tbody>{"".join(summary_rows)}</tbody>
    </table>""" if summary_rows else '<p class="missing">No target_runs/*/*/verdicts.json found.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Maritime Cyber Range -- Resilience Report</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 1080px;
          margin: 2rem auto; padding: 0 1.5rem; line-height: 1.5;
          color: #1a1a1a; background: #fff; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e6e6e6; background: #14161a; }}
    table {{ border-color: #3a3d44 !important; }}
    th {{ background: #1f2228 !important; }}
    tr:nth-child(even) td {{ background: #1a1d22 !important; }}
    code {{ background: #23262c !important; }}
    .missing {{ color: #f0a34a !important; }}
    .gaps {{ background: rgba(255,255,255,0.05) !important; }}
  }}
  h1 {{ margin-bottom: 0.2rem; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .methodology {{ background: rgba(120,120,120,0.08); border-radius: 8px; padding: 1rem 1.25rem;
                   font-size: 0.92rem; margin-bottom: 2rem; }}
  .methodology h2 {{ margin-top: 0; font-size: 1.05rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 1.5rem; font-size: 0.9rem; }}
  th, td {{ border: 1px solid #d0d3d8; padding: 0.4rem 0.6rem; text-align: right; vertical-align: top; }}
  th {{ background: #f4f5f7; text-align: right; }}
  td:first-child, th:first-child {{ text-align: left; }}
  td.ev, td.rec {{ text-align: left; font-size: 0.85rem; }}
  tr:nth-child(even) td {{ background: #fafbfc; }}
  section.profile {{ margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #d0d3d8; }}
  .domain {{ font-weight: normal; color: #777; font-size: 1rem; }}
  .src {{ color: #666; font-size: 0.85rem; }}
  code {{ background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 4px; }}
  .missing {{ color: #a05a00; font-style: italic; }}
  .v-bad, .v-not-ready {{ color: #b91c1c; }}
  .v-good, .v-ready {{ color: #15803d; }}
  .v-warn, .v-conditional {{ color: #b45309; }}
  .v-na {{ color: #6b7280; }}
  .headline {{ font-size: 1.15rem; font-weight: 700; padding: 0.6rem 1rem; border-radius: 8px;
               background: rgba(120,120,120,0.1); display: inline-block; margin: 0.5rem 0 1rem; }}
  .gaps {{ background: rgba(180,83,9,0.08); border-radius: 8px; padding: 0.8rem 1.1rem; font-size: 0.88rem; }}
  .gaps h4 {{ margin-top: 0; }}
  .execsum {{ background: rgba(70,130,180,0.08); border-left: 3px solid #4682b4; border-radius: 4px;
              padding: 0.7rem 1rem; margin: 0.6rem 0 1.2rem; font-size: 0.95rem; }}
  table.timeline td {{ text-align: left; font-size: 0.85rem; }}
  table.timeline td:first-child {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
  tr.tl-inject td:nth-child(2) {{ color: #b91c1c; font-weight: 600; }}
  tr.tl-detect td:nth-child(2) {{ color: #1d4ed8; font-weight: 600; }}
  @media (prefers-color-scheme: dark) {{
    .execsum {{ background: rgba(70,130,180,0.15) !important; }}
    tr.tl-inject td:nth-child(2) {{ color: #f87171 !important; }}
    tr.tl-detect td:nth-child(2) {{ color: #60a5fa !important; }}
  }}
  footer {{ margin-top: 3rem; color: #888; font-size: 0.8rem; border-top: 1px solid #d0d3d8; padding-top: 1rem; }}
</style>
</head>
<body>
  <h1>Autonomous Maritime Cyber Range</h1>
  <div class="meta">Resilience report &middot; generated {generated}</div>

  <div class="methodology">
    <h2>Methodology</h2>
    <p><b>Vulnerability</b> asks: did the attack actually corrupt the target's own reported
    state (accept forged GPS, obey a forged command)? Four outcomes, never a bare pass/fail --
    <b>VULNERABLE</b> (it did), <b>RESILIENT</b> (evidence it resisted, e.g. raw ingestion
    confirmed but the fused belief didn't move), <b>N/A</b> (the attack vector doesn't apply to
    this vehicle/config), <b>INCONCLUSIVE</b> (preconditions weren't met, e.g. never armed --
    reported honestly rather than defaulting to a false RESILIENT).</p>
    <p><b>Detectability</b> asks a separate question: would a standard blind rule-based monitor
    (detection/detectors.py) have caught it, regardless of whether the attack succeeded against
    the vehicle itself? Same precision/recall/latency methodology as the rest of this project's
    scoring (tools/score_detectors.py).</p>
    <p><b>Deployment readiness</b> is a synthesis: any VULNERABLE finding means NOT READY;
    otherwise any INCONCLUSIVE finding means CONDITIONALLY READY (retest before trusting the
    result); only RESILIENT/N-A outcomes across the board means READY <i>against the attacks
    actually tested</i> -- not a general security clearance.</p>
    <p><b>No machine learning is used anywhere in this pipeline.</b> Detection is a set of
    hand-written rule-based state machines (<code>detection/detectors.py</code>) checking for
    physically/protocol-implausible events -- e.g. a believed-position jump faster than any real
    hull could move, or an <code>RC_CHANNELS_OVERRIDE</code> message appearing on the wire at
    all. "Precision/recall/latency" here is <i>not</i> a classifier's confusion matrix over
    labeled samples -- it's computed by <code>tools/score_detectors.py</code> matching each
    detector alert's timestamp against padded ground-truth attack windows (when the attack
    script itself logged an injection) that the detector never had access to while running, so
    the score can't be inflated by the detector having privileged knowledge of the attack.</p>
    <p><b>A mode-dependent caveat worth knowing before reading a RESILIENT verdict on
    <code>rc_override</code>:</b> ArduPilot only reads <code>RC_CHANNELS_OVERRIDE</code>'s
    throttle/steering as live control input in pilot-manual modes (MANUAL/ACRO/STEERING) --
    in an autonomous mode (AUTO/GUIDED/HOLD) the navigation controller owns the actuators and a
    throttle-seizing attack has no visible effect purely because of that mode, independent of
    any actual hardening. This test suite's own <code>rc_override</code> check forces MANUAL
    mode before injecting specifically to avoid this false negative -- confirmed live,
    2026-08-09, against this project's own CUSV twin.</p>
  </div>

  <h2>Cross-target summary</h2>
  {summary_table}

  {"".join(detail_sections)}

  <footer>
    Data source: <code>target_runs/*/*/verdicts.json</code>, each produced by
    <code>tools/test_target.py</code>. Regenerate with
    <code>python3 tools/generate_target_report.py</code>.
  </footer>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(TARGET_RUNS, "resilience_report.html"))
    args = ap.parse_args()

    targets = discover_target_runs()
    if not targets:
        print("No target_runs/*/*/verdicts.json found -- nothing to report.")
    report = build_report(targets)
    with open(args.out, "w") as f:
        f.write(report)
    print(f"Wrote {args.out} ({len(targets)} target(s): {', '.join(targets) or 'none'})")


if __name__ == "__main__":
    main()
