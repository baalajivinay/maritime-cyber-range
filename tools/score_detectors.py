#!/usr/bin/env python3
"""
WO-25: offline scoring harness. Replays a detector-alert log (produced live by
detection/run_detectors.py, which never saw ground truth) against the private
attack_logs/*.csv ground truth, and reports precision/recall/detection-latency
per attack type.

This is the ONLY component allowed to read attack_logs/*.csv (docs/ARCHITECTURE.md
isolation rule): the detectors run blind; scoring judges them after the fact.

Matching model:
  - Each ground-truth CSV's rows (wall_ts) are clustered into ATTACK WINDOWS
    (consecutive rows with gaps < merge_gap seconds -> one window, padded by a
    tolerance on each side).
  - An alert is a TRUE POSITIVE if its timestamp falls in a window of the SAME
    attack family; otherwise a FALSE POSITIVE.
  - A window with >=1 matching alert is DETECTED; a window with none is a MISS
    (false negative).
  precision = TP_alerts / (TP_alerts + FP_alerts)
  recall    = detected_windows / total_windows

Detection-latency model:
  - latency = (first matching alert's t) - (window's ACTION START).
  - For most attacks the ground truth is logged continuously throughout the
    action, so the raw (unpadded) window start IS the action start.
  - c2_replay's inject_rc_override is logged once, AFTER its multi-second
    override loop finishes (see attacks/c2_replay.py) -- its `description`
    field records the loop duration, so the action start is recovered as
    (wall_ts - duration) instead of the raw timestamp. This correction is
    used ONLY for latency; it never changes the padded windows used for
    precision/recall (those stay exactly as already validated).
  - A handful of latency samples can still land slightly negative (detector
    fired before the corrected start, e.g. clock/loop-timing slop); these are
    clamped to 0.0 rather than reported as a physically-impossible negative
    latency.

Usage:
  python3 tools/score_detectors.py --alerts evidence/detector_alerts_<profile>.jsonl
"""
import argparse
import csv
import json
import os
import re
import statistics

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(REPO, "attack_logs")

# ground-truth file -> attack family
GT_FILES = {
    "gps_spoof_ground_truth.csv": "gps_spoof",
    "ais_spoof_ground_truth.csv": "ais_spoof",
    "c2_replay_ground_truth.csv": "c2_replay",
    "acoustic_spoof_ground_truth.csv": "acoustic_spoof",
}

_RC_DURATION_RE = re.compile(r"([\d.]+)\s*s\b")


def _action_start(fname, row, wall_ts):
    """The true start of the logged action, correcting for attacks whose
    ground truth is written post-hoc (see module docstring)."""
    if fname == "c2_replay_ground_truth.csv" and row.get("attack_type") == "inject_rc_override":
        m = _RC_DURATION_RE.search(row.get("description", "") or "")
        if m:
            return wall_ts - float(m.group(1))
    return wall_ts


def load_windows(path, fname, merge_gap=8.0, pad=12.0):
    """Cluster a CSV's wall_ts column into windows. `pad` covers an attack's
    duration on each side -- several attacks in this project log a single
    ground-truth row at the END of a multi-second action (e.g.
    inject_forged_rc_override logs once after its ~6-10 s loop), while
    detectors alert DURING it, so the pad must exceed the longest attack
    action.

    Returns a list of dicts: {"padded": (a, b), "start": action_start} where
    `padded` is used for TP/FP/recall matching (unchanged behavior) and
    `start` is the (possibly corrected) action-start used only for latency.
    """
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                ts = float(row["wall_ts"])
            except (KeyError, ValueError):
                continue
            rows.append((ts, _action_start(fname, row, ts)))
    rows.sort(key=lambda r: r[0])
    clusters = []
    for ts, start in rows:
        if clusters and ts - clusters[-1][-1][0] <= merge_gap:
            clusters[-1].append((ts, start))
        else:
            clusters.append([(ts, start)])
    out = []
    for c in clusters:
        raw_a = min(ts for ts, _ in c)
        raw_b = max(ts for ts, _ in c)
        action_start = min(start for _, start in c)
        out.append({"padded": (raw_a - pad, raw_b + pad), "start": action_start})
    return out


def _pctile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _latency_stats(latencies):
    lat = sorted(latencies)
    return {
        "n": len(lat),
        "mean_s": round(statistics.mean(lat), 3) if lat else None,
        "median_s": round(statistics.median(lat), 3) if lat else None,
        "p95_s": round(_pctile(lat, 0.95), 3) if lat else None,
        "max_s": round(max(lat), 3) if lat else None,
    }


def score(alerts_path, min_ts=None, max_ts=None, gt_dir=None):
    """Score one alert-log file against ground truth. Returns a dict:
    {min_ts, max_ts, families: {fam: {...}}, overall: {...}}. This is the
    single source of truth for both the CLI table (main(), below) and
    tools/generate_report.py.

    gt_dir: directory holding the GT_FILES CSVs, defaults to attack_logs/
    (LOGS). Lets tools/test_target.py score a target run's own
    target_runs/<name>/<run_ts>/ ground truth through this exact same
    function, without touching the git-tracked reference-vehicle logs.
    """
    gt_dir = gt_dir or LOGS
    all_alerts = []
    with open(alerts_path) as f:
        for line in f:
            line = line.strip()
            if line:
                all_alerts.append(json.loads(line))

    # The attack_logs/*.csv ground truth is git-tracked and APPENDED every run, so
    # it accumulates windows from many past sessions. Scoring one run's alerts
    # against all of history yields a meaningless near-zero recall. So unless the
    # caller pins an explicit window, auto-scope to the span of THIS alert file
    # (padded), which is the run that produced these alerts.
    if all_alerts:
        ats = [a["t"] for a in all_alerts]
        if min_ts is None:
            min_ts = min(ats) - 60.0
        if max_ts is None:
            max_ts = max(ats) + 60.0
    else:
        min_ts = min_ts if min_ts is not None else 0.0
        max_ts = max_ts if max_ts is not None else float("inf")

    # ground-truth windows per family (overlapping the scored span)
    windows = {}
    for fname, fam in GT_FILES.items():
        w = [win for win in load_windows(os.path.join(gt_dir, fname), fname)
             if win["padded"][1] >= min_ts and win["padded"][0] <= max_ts]
        if w:
            windows[fam] = w

    # alerts within the scored span
    alerts = [a for a in all_alerts if min_ts <= a["t"] <= max_ts]

    families = sorted(set(list(windows.keys()) + [a["attack_type"] for a in alerts]))
    result = {"min_ts": min_ts, "max_ts": max_ts, "families": {}}
    tot_tp = tot_fp = tot_win = tot_det = 0
    all_latencies = []
    for fam in families:
        fam_alerts = sorted((a for a in alerts if a["attack_type"] == fam), key=lambda a: a["t"])
        fam_windows = windows.get(fam, [])
        detected = 0
        fam_latencies = []
        for win in fam_windows:
            a, b = win["padded"]
            matching = [al for al in fam_alerts if a <= al["t"] <= b]
            if matching:
                detected += 1
                latency = max(0.0, matching[0]["t"] - win["start"])
                fam_latencies.append(latency)
        tp = sum(1 for al in fam_alerts
                 if any(win["padded"][0] <= al["t"] <= win["padded"][1] for win in fam_windows))
        fp = len(fam_alerts) - tp
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = detected / len(fam_windows) if fam_windows else float("nan")
        tot_tp += tp; tot_fp += fp; tot_win += len(fam_windows); tot_det += detected
        all_latencies.extend(fam_latencies)
        result["families"][fam] = {
            "tp": tp, "fp": fp, "windows": len(fam_windows), "detected": detected,
            "precision": prec, "recall": recall, "latency": _latency_stats(fam_latencies),
        }
    op = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else float("nan")
    orc = tot_det / tot_win if tot_win else float("nan")
    result["overall"] = {
        "tp": tot_tp, "fp": tot_fp, "windows": tot_win, "detected": tot_det,
        "precision": op, "recall": orc, "latency": _latency_stats(all_latencies),
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alerts", required=True)
    ap.add_argument("--min-ts", type=float, default=None,
                    help="ignore ground-truth/alerts before this wall-clock (scope to one run). "
                         "Default: auto-scoped to the alert file's own time span.")
    ap.add_argument("--max-ts", type=float, default=None,
                    help="ignore ground-truth/alerts after this wall-clock. "
                         "Default: auto-scoped to the alert file's own time span.")
    args = ap.parse_args()

    result = score(args.alerts, args.min_ts, args.max_ts)

    print(f"{'attack':16} {'TP':>4} {'FP':>4} {'windows':>8} {'detected':>9} "
          f"{'prec':>6} {'recall':>7} {'mean_lat':>9} {'p95_lat':>8}")
    print("-" * 82)
    for fam, r in result["families"].items():
        lat = r["latency"]
        mean_lat = f"{lat['mean_s']:.2f}s" if lat["mean_s"] is not None else "n/a"
        p95_lat = f"{lat['p95_s']:.2f}s" if lat["p95_s"] is not None else "n/a"
        print(f"{fam:16} {r['tp']:>4} {r['fp']:>4} {r['windows']:>8} {r['detected']:>9} "
              f"{r['precision']:>6.2f} {r['recall']:>7.2f} {mean_lat:>9} {p95_lat:>8}")
    print("-" * 82)
    o = result["overall"]
    lat = o["latency"]
    mean_lat = f"{lat['mean_s']:.2f}s" if lat["mean_s"] is not None else "n/a"
    p95_lat = f"{lat['p95_s']:.2f}s" if lat["p95_s"] is not None else "n/a"
    print(f"{'OVERALL':16} {o['tp']:>4} {o['fp']:>4} {o['windows']:>8} {o['detected']:>9} "
          f"{o['precision']:>6.2f} {o['recall']:>7.2f} {mean_lat:>9} {p95_lat:>8}")


if __name__ == "__main__":
    main()
