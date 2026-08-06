#!/usr/bin/env python3
"""
Scenario evaluation report: compiles the per-vehicle detection results (from
tools/score_detectors.py) and the monitoring layer's system-overhead readings
(from detection/run_detectors.py) into one self-contained HTML file --
"a report comparing all attack scenarios" against the metrics the project's
objective document calls for: detection accuracy (precision/recall),
false-positive rate, detection latency, and system performance overhead.

Data sources (never touched, only read):
  - evidence/detector_alerts_<profile>.jsonl   -- blind live detector output
  - attack_logs/*.csv                          -- private ground truth
  - evidence/detector_overhead_<profile>.json  -- CPU/RAM/throughput sample
    written by detection/run_detectors.py at the end of a live run

Usage:
  python3 tools/generate_report.py [--out evidence/evaluation_report.html]

Re-run detection/run_detectors.py for a profile first if its overhead file
is missing or stale -- this script only compiles what's already on disk, it
does not launch the sim or the detectors itself.
"""
import argparse
import glob
import html
import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE = os.path.join(REPO, "evidence")
PROFILES_DIR = os.path.join(REPO, "profiles")
sys.path.insert(0, os.path.join(REPO, "tools"))
from score_detectors import score  # noqa: E402

ALERT_RE = re.compile(r"^detector_alerts_(.+?)(?:_run)?\.jsonl$")


def discover_profiles():
    """One alert file per profile. If both detector_alerts_<p>.jsonl and the
    legacy detector_alerts_<p>_run.jsonl exist, prefer the canonical
    (non-_run) name; otherwise fall back to whichever exists."""
    candidates = {}
    for path in glob.glob(os.path.join(EVIDENCE, "detector_alerts_*.jsonl")):
        fname = os.path.basename(path)
        m = ALERT_RE.match(fname)
        if not m:
            continue
        profile = m.group(1)
        is_canonical = not fname.endswith("_run.jsonl")
        if profile not in candidates or (is_canonical and candidates[profile][1] is False):
            candidates[profile] = (path, is_canonical)
    return {p: path for p, (path, _) in sorted(candidates.items())}


def load_profile_meta(profile):
    path = os.path.join(PROFILES_DIR, f"{profile}.json")
    if not os.path.exists(path):
        return {"domain": "unknown", "attacks": []}
    with open(path) as f:
        j = json.load(f)
    return {"domain": j.get("domain", "unknown"), "attacks": j.get("attacks", [])}


def load_overhead(profile):
    path = os.path.join(EVIDENCE, f"detector_overhead_{profile}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _fmt(v, suffix="", digits=2):
    if v is None:
        return "n/a"
    if isinstance(v, float) and v != v:  # NaN
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}{suffix}"
    return f"{v}{suffix}"


def _pct(v):
    if v is None or v != v:
        return "n/a"
    return f"{v * 100:.0f}%"


def render_family_table(families):
    rows = []
    for fam, r in families.items():
        lat = r["latency"]
        fp_rate = r["fp"] / (r["tp"] + r["fp"]) if (r["tp"] + r["fp"]) else float("nan")
        rows.append(f"""
        <tr>
          <td>{html.escape(fam)}</td>
          <td>{r['tp']}</td>
          <td>{r['fp']}</td>
          <td>{_pct(fp_rate)}</td>
          <td>{r['detected']}/{r['windows']}</td>
          <td>{_pct(r['precision'])}</td>
          <td>{_pct(r['recall'])}</td>
          <td>{_fmt(lat['mean_s'], 's')}</td>
          <td>{_fmt(lat['p95_s'], 's')}</td>
          <td>{_fmt(lat['max_s'], 's')}</td>
        </tr>""")
    return "\n".join(rows)


def render_overhead_panel(overhead):
    if overhead is None:
        return '<p class="missing">No system-overhead sample for this profile yet -- ' \
               'run <code>detection/run_detectors.py</code> live to collect one.</p>'
    ept = overhead["event_proc_time_us"]
    return f"""
    <table class="kv">
      <tr><th>Wall-clock sampled</th><td>{_fmt(overhead['wall_s'], 's')}</td></tr>
      <tr><th>CPU time (user+sys)</th><td>{_fmt(overhead['cpu_s'], 's')} ({_fmt(overhead['cpu_pct_of_wall'], '%')} of wall)</td></tr>
      <tr><th>Peak resident memory</th><td>{_fmt(overhead['peak_rss_mb'], ' MB')}</td></tr>
      <tr><th>Events processed</th><td>{overhead['events_processed']} ({_fmt(overhead['events_per_sec'], '/s')})</td></tr>
      <tr><th>Alerts emitted</th><td>{overhead['alerts_emitted']}</td></tr>
      <tr><th>Per-event processing time</th>
          <td>mean {_fmt(ept['mean'], 'us')} / p95 {_fmt(ept['p95'], 'us')} / max {_fmt(ept['max'], 'us')}</td></tr>
    </table>"""


def build_report(profiles):
    generated = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    summary_rows = []
    detail_sections = []

    for profile, alerts_path in profiles.items():
        meta = load_profile_meta(profile)
        result = score(alerts_path)
        overhead = load_overhead(profile)
        o = result["overall"]
        fp_rate = o["fp"] / (o["tp"] + o["fp"]) if (o["tp"] + o["fp"]) else float("nan")
        cpu = _fmt(overhead["cpu_pct_of_wall"], "%") if overhead else "n/a"
        rss = _fmt(overhead["peak_rss_mb"], " MB") if overhead else "n/a"

        summary_rows.append(f"""
        <tr>
          <td>{html.escape(profile)}</td>
          <td>{html.escape(meta['domain'])}</td>
          <td>{_pct(o['precision'])}</td>
          <td>{_pct(o['recall'])}</td>
          <td>{_pct(fp_rate)}</td>
          <td>{_fmt(o['latency']['mean_s'], 's')}</td>
          <td>{_fmt(o['latency']['p95_s'], 's')}</td>
          <td>{cpu}</td>
          <td>{rss}</td>
        </tr>""")

        detail_sections.append(f"""
    <section class="profile">
      <h2>{html.escape(profile)} <span class="domain">({html.escape(meta['domain'])})</span></h2>
      <p class="src">Scored from <code>{html.escape(os.path.relpath(alerts_path, REPO))}</code>,
         window {time.strftime('%H:%M:%S', time.localtime(result['min_ts']))}
         &ndash; {time.strftime('%H:%M:%S', time.localtime(result['max_ts']))}.</p>
      <table class="detail">
        <thead>
          <tr>
            <th>Attack</th><th>TP</th><th>FP</th><th>FP rate</th><th>Windows detected</th>
            <th>Precision</th><th>Recall</th><th>Mean latency</th><th>p95 latency</th><th>Max latency</th>
          </tr>
        </thead>
        <tbody>
          {render_family_table(result['families'])}
        </tbody>
      </table>
      <h3>System performance overhead</h3>
      {render_overhead_panel(overhead)}
    </section>""")

    summary_table = f"""
    <table class="summary">
      <thead>
        <tr>
          <th>Vehicle profile</th><th>Domain</th><th>Precision</th><th>Recall</th>
          <th>FP rate</th><th>Mean latency</th><th>p95 latency</th><th>CPU (of wall)</th><th>Peak RSS</th>
        </tr>
      </thead>
      <tbody>
        {"".join(summary_rows)}
      </tbody>
    </table>""" if summary_rows else "<p class=\"missing\">No detector_alerts_*.jsonl found under evidence/.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Maritime Cyber Range -- Scenario Evaluation Report</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 980px;
          margin: 2rem auto; padding: 0 1.5rem; line-height: 1.5;
          color: #1a1a1a; background: #fff; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e6e6e6; background: #14161a; }}
    table {{ border-color: #3a3d44 !important; }}
    th {{ background: #1f2228 !important; }}
    tr:nth-child(even) td {{ background: #1a1d22 !important; }}
    code {{ background: #23262c !important; }}
    .missing {{ color: #f0a34a !important; }}
  }}
  h1 {{ margin-bottom: 0.2rem; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .methodology {{ background: rgba(120,120,120,0.08); border-radius: 8px; padding: 1rem 1.25rem;
                   font-size: 0.92rem; margin-bottom: 2rem; }}
  .methodology h2 {{ margin-top: 0; font-size: 1.05rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 1.5rem; font-size: 0.92rem; }}
  th, td {{ border: 1px solid #d0d3d8; padding: 0.4rem 0.6rem; text-align: right; }}
  th {{ background: #f4f5f7; text-align: right; }}
  td:first-child, th:first-child {{ text-align: left; }}
  tr:nth-child(even) td {{ background: #fafbfc; }}
  table.kv th {{ text-align: left; width: 40%; }}
  table.kv td {{ text-align: left; }}
  section.profile {{ margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #d0d3d8; }}
  .domain {{ font-weight: normal; color: #777; font-size: 1rem; }}
  .src {{ color: #666; font-size: 0.85rem; }}
  code {{ background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 4px; }}
  .missing {{ color: #a05a00; font-style: italic; }}
  footer {{ margin-top: 3rem; color: #888; font-size: 0.8rem; border-top: 1px solid #d0d3d8; padding-top: 1rem; }}
</style>
</head>
<body>
  <h1>Autonomous Maritime Cyber Range</h1>
  <div class="meta">Scenario evaluation report &middot; generated {generated}</div>

  <div class="methodology">
    <h2>Methodology</h2>
    <p><b>Detection accuracy</b> (precision/recall) and <b>false-positive rate</b> come from
    replaying each run's blind detector alerts (<code>detection/run_detectors.py</code>, which
    never sees attack ground truth) against the private ground-truth logs in
    <code>attack_logs/</code>, via <code>tools/score_detectors.py</code>. A ground-truth
    action is clustered into a time window; an alert is a true positive if it falls in a
    window of the same attack family and a false positive otherwise; a window with no
    matching alert is a miss.</p>
    <p><b>Detection latency</b> is the time from an attack's action start to the first
    matching alert. Most attacks log ground truth continuously, so the window's earliest
    timestamp is the action start. One exception: C2's forged RC-override is logged once,
    <em>after</em> its multi-second override loop -- its logged duration is used to recover
    the actual start. A small number of near-zero samples are clamped at 0s rather than
    reported as a physically-impossible negative latency.</p>
    <p><b>System performance overhead</b> is the CPU time, peak memory, and per-event
    processing time of the detection layer itself, sampled live via the stdlib
    <code>resource</code> module during <code>detection/run_detectors.py</code>. The
    detectors are a passive tap alongside the autopilot/dashboard (never inline with vessel
    control), so this figure is the whole resource cost the monitoring layer adds to the
    system.</p>
  </div>

  <h2>Cross-vehicle summary</h2>
  {summary_table}

  {"".join(detail_sections)}

  <footer>
    Data sources: <code>evidence/detector_alerts_*.jsonl</code>,
    <code>attack_logs/*.csv</code> (ground truth, read only by the offline scorer),
    <code>evidence/detector_overhead_*.json</code>.
    Regenerate with <code>python3 tools/generate_report.py</code>.
  </footer>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(EVIDENCE, "evaluation_report.html"))
    args = ap.parse_args()

    profiles = discover_profiles()
    if not profiles:
        print("No evidence/detector_alerts_*.jsonl files found -- nothing to report.")
    report = build_report(profiles)
    with open(args.out, "w") as f:
        f.write(report)
    print(f"Wrote {args.out} ({len(profiles)} profile(s): {', '.join(profiles) or 'none'})")


if __name__ == "__main__":
    main()
