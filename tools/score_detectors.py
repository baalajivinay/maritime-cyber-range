#!/usr/bin/env python3
"""
WO-25: offline scoring harness. Replays a detector-alert log (produced live by
detection/run_detectors.py, which never saw ground truth) against the private
attack_logs/*.csv ground truth, and reports precision/recall per attack type.

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

Usage:
  python3 tools/score_detectors.py --alerts evidence/detector_alerts_<profile>.jsonl
"""
import argparse
import csv
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(REPO, "attack_logs")

# ground-truth file -> attack family
GT_FILES = {
    "gps_spoof_ground_truth.csv": "gps_spoof",
    "ais_spoof_ground_truth.csv": "ais_spoof",
    "c2_replay_ground_truth.csv": "c2_replay",
    "acoustic_spoof_ground_truth.csv": "acoustic_spoof",
}


def load_windows(path, merge_gap=8.0, pad=12.0):
    """Cluster a CSV's wall_ts column into padded [start,end] windows. `pad`
    covers an attack's duration on each side -- several attacks in this project
    log a single ground-truth row at the END of a multi-second action (e.g.
    inject_forged_rc_override logs once after its ~6-10 s loop), while detectors
    alert DURING it, so the pad must exceed the longest attack action."""
    if not os.path.exists(path):
        return []
    ts = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                ts.append(float(row["wall_ts"]))
            except (KeyError, ValueError):
                pass
    ts.sort()
    windows = []
    for t in ts:
        if windows and t - windows[-1][1] <= merge_gap:
            windows[-1][1] = t
        else:
            windows.append([t, t])
    return [(a - pad, b + pad) for a, b in windows]


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

    # load alerts first so we can auto-scope to their time span
    all_alerts = []
    with open(args.alerts) as f:
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
        if args.min_ts is None:
            args.min_ts = min(ats) - 60.0
        if args.max_ts is None:
            args.max_ts = max(ats) + 60.0
    else:
        args.min_ts = args.min_ts if args.min_ts is not None else 0.0
        args.max_ts = args.max_ts if args.max_ts is not None else float("inf")

    # ground-truth windows per family (overlapping the scored span)
    windows = {}
    for fname, fam in GT_FILES.items():
        w = [(a, b) for (a, b) in load_windows(os.path.join(LOGS, fname))
             if b >= args.min_ts and a <= args.max_ts]
        if w:
            windows[fam] = w

    # alerts within the scored span
    alerts = [a for a in all_alerts if args.min_ts <= a["t"] <= args.max_ts]

    families = sorted(set(list(windows.keys()) + [a["attack_type"] for a in alerts]))
    print(f"{'attack':16} {'TP':>4} {'FP':>4} {'windows':>8} {'detected':>9} {'prec':>6} {'recall':>7}")
    print("-" * 62)
    tot_tp = tot_fp = tot_win = tot_det = 0
    for fam in families:
        fam_alerts = [a for a in alerts if a["attack_type"] == fam]
        fam_windows = windows.get(fam, [])
        detected = 0
        for (a, b) in fam_windows:
            if any(a <= al["t"] <= b for al in fam_alerts):
                detected += 1
        tp = sum(1 for al in fam_alerts if any(a <= al["t"] <= b for (a, b) in fam_windows))
        fp = len(fam_alerts) - tp
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = detected / len(fam_windows) if fam_windows else float("nan")
        tot_tp += tp; tot_fp += fp; tot_win += len(fam_windows); tot_det += detected
        print(f"{fam:16} {tp:>4} {fp:>4} {len(fam_windows):>8} {detected:>9} "
              f"{prec:>6.2f} {recall:>7.2f}")
    print("-" * 62)
    op = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else float("nan")
    orc = tot_det / tot_win if tot_win else float("nan")
    print(f"{'OVERALL':16} {tot_tp:>4} {tot_fp:>4} {tot_win:>8} {tot_det:>9} {op:>6.2f} {orc:>7.2f}")


if __name__ == "__main__":
    main()
