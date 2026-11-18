#!/usr/bin/env python3
"""
Layman-terms report generator.

Turns a tools/test_target.py verdicts.json into a plain-English report a
non-specialist (a commander, a programme reviewer, a journalist) can read:
what vehicle was tested, in what water, what we tried, what happened, what it
means, and what to do about it. Writes a Markdown report next to the verdicts
file and prints a short summary to the terminal.

Usage:
    python3 tools/report.py target_runs/<twin>/<run>/verdicts.json
    python3 tools/report.py target_runs/<twin>/<run>/verdicts.json --out report.md
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- plain-English descriptions of each attack / sub-check -------------------
ATTACKS = {
    "gps_spoof": {
        "title": "GPS position spoofing",
        "plain": "feeding the vessel fake GPS so it believes it is somewhere it is not",
        "if_vuln": "an attacker could walk the vessel off its intended track -- toward a hazard, "
                   "out of a safe corridor, or into another vessel -- without touching the controls",
        "fix": "cross-check GPS against a second, independent position source in the navigation filter "
               "(e.g. dead-reckoning/INS consistency gating); alarm on sudden position jumps.",
    },
    "ais_spoof": {
        "title": "AIS identity / traffic spoofing",
        "plain": "injecting fake vessels, or a fake copy of this vessel's own identity, into the "
                 "traffic picture operators and collision-avoidance rely on",
        "if_vuln": "operators (or an autonomous collision-avoidance layer) could be made to see ships "
                   "that are not there, or lose track of ones that are",
        "fix": "validate AIS at the display/ECDIS layer (plausibility, cross-reference with radar); "
               "note: the autopilot itself does not act on AIS, so this is an operator-picture risk.",
    },
    "c2_replay/mode_change": {
        "title": "Remote mode hijack",
        "plain": "an outsider sending an unauthenticated command that forces the vessel to change its "
                 "operating mode (for example, stopping it, or switching it into a different behaviour)",
        "if_vuln": "an attacker on the control network could abort or alter the mission at will -- e.g. "
                   "force the vessel to hold, or drop out of its autonomous behaviour",
        "fix": "require authenticated command-and-control (MAVLink2 message signing) and restrict which "
               "ground station the autopilot will obey.",
    },
    "c2_replay/rc_override": {
        "title": "Remote control seizure",
        "plain": "an outsider taking over the throttle and steering directly, with no authentication",
        "if_vuln": "an attacker could drive the vessel -- full authority over where it goes and how fast",
        "fix": "lock the trusted ground-station ID (SYSID_MYGCS) and enable MAVLink2 signing so forged "
               "override commands are rejected.",
    },
    "acoustic_spoof": {
        "title": "Underwater position spoofing",
        "plain": "feeding a submerged vehicle a fake acoustic/undersea position so its belief of where "
                 "it is drifts away from where it actually is",
        "if_vuln": "an attacker could make the underwater vehicle steer itself off course while it still "
                   "'thinks' it is on track -- the underwater equivalent of GPS spoofing",
        "fix": "authenticate / plausibility-check the acoustic positioning feed; gate external-navigation "
               "updates against inertial dead-reckoning.",
    },
}

VERDICT_LAYMAN = {
    "VULNERABLE":   ("AT RISK",        "The vessel accepted the fake input."),
    "RESILIENT":    ("PROTECTED",      "The vessel rejected the fake input."),
    "N/A":          ("NOT APPLICABLE", "This attack cannot physically apply to this vessel here."),
    "INCONCLUSIVE": ("UNCLEAR",        "The test could not reach a clean result; it should be re-run."),
}
VERDICT_MARK = {"VULNERABLE": "[AT RISK]", "RESILIENT": "[PROTECTED]",
                "N/A": "[N/A]", "INCONCLUSIVE": "[UNCLEAR]"}


def _flatten(attacks):
    """verdicts.json 'attacks' block -> [(key, verdict, evidence), ...]."""
    rows = []
    for name, block in attacks.items():
        if name == "c2_replay" and ("mode_change" in block or "rc_override" in block):
            for sub in ("mode_change", "rc_override"):
                if sub in block:
                    rows.append((f"c2_replay/{sub}", block[sub].get("verdict"), block[sub].get("evidence", {})))
        elif "vulnerability" in block:
            rows.append((name, block["vulnerability"].get("verdict"), block["vulnerability"].get("evidence", {})))
        elif "verdict" in block:
            rows.append((name, block.get("verdict"), block.get("evidence", {})))
    return rows


def _site_environment(site_id):
    try:
        sys.path.insert(0, REPO)
        from scaleup.physics.environment import Environment
        return Environment.from_site(site_id).summary()
    except Exception:
        return None


def build_markdown(v):
    target = v.get("target", "unknown")
    domain = v.get("domain", "unknown")
    site = v.get("site", "kochi")
    rows = _flatten(v.get("attacks", {}))
    at_risk = [r for r in rows if r[1] == "VULNERABLE"]
    protected = [r for r in rows if r[1] == "RESILIENT"]
    na = [r for r in rows if r[1] == "N/A"]
    unclear = [r for r in rows if r[1] == "INCONCLUSIVE"]
    tested = at_risk + protected + unclear  # the ones actually exercised

    L = []
    L.append(f"# Security test report — {target}")
    L.append("")
    L.append(f"**Vehicle:** {target}  ·  **Type:** {'underwater (AUV)' if domain=='underwater' else 'surface (USV)'}  "
             f"·  **Test water:** {site.capitalize()}")
    if v.get("run_ts"):
        L.append(f"**Run:** {v['run_ts']}" + (f"  ·  code {v['git_sha']}" if v.get("git_sha") else ""))
    L.append("")

    # headline
    L.append("## In one line")
    if at_risk:
        L.append(f"> We ran **{len(tested)}** attacks the vessel could actually face. "
                 f"**{len(at_risk)}** of them succeeded — the vessel is **at risk** to those. "
                 f"{len(protected)} were resisted" + (f", {len(unclear)} were unclear" if unclear else "") + ".")
    elif tested:
        L.append(f"> We ran **{len(tested)}** applicable attacks and the vessel **resisted all of them**"
                 + (f" ({len(unclear)} unclear)" if unclear else "") + ".")
    else:
        L.append("> No applicable attacks were exercised in this run.")
    L.append("")

    # what we found
    L.append("## What we found")
    L.append("")
    L.append("| Attack | In plain terms | Result | Meaning |")
    L.append("|---|---|---|---|")
    for key, verdict, _ev in rows:
        meta = ATTACKS.get(key, {"title": key, "plain": key})
        label, _ = VERDICT_LAYMAN.get(verdict, (verdict, ""))
        mark = VERDICT_MARK.get(verdict, verdict)
        L.append(f"| {meta['title']} | {meta['plain']} | **{mark}** | {label} |")
    L.append("")

    # detail per at-risk finding
    if at_risk:
        L.append("## Why the at-risk findings matter")
        L.append("")
        for key, _verdict, _ev in at_risk:
            meta = ATTACKS.get(key, {})
            L.append(f"**{meta.get('title', key)}** — {meta.get('if_vuln','')}.")
            L.append("")
            L.append(f"- *What to do:* {meta.get('fix','')}")
            L.append("")

    # things that don't apply (so the reader knows they weren't missed)
    if na:
        L.append("## Not applicable (and why)")
        for key, _verdict, ev in na:
            meta = ATTACKS.get(key, {"title": key})
            reason = (ev or {}).get("reason", "does not physically apply to this vessel here")
            L.append(f"- **{meta['title']}** — {reason}")
        L.append("")

    if unclear:
        L.append("## Needs a re-run")
        for key, _verdict, ev in unclear:
            meta = ATTACKS.get(key, {"title": key})
            reason = (ev or {}).get("reason", "no clean result")
            L.append(f"- **{meta['title']}** — {reason}")
        L.append("")

    # the water it was tested in
    env = _site_environment(site)
    if env:
        L.append("## The water it was tested in")
        L.append(f"- Location: **{env.get('name', site)}**  (fidelity: {env.get('fidelity_tier','A')})")
        L.append(f"- Water density: {env.get('water_density_kg_m3')} kg/m³  ·  "
                 f"sound speed: {env.get('surface_sound_speed_mps')} m/s  ·  "
                 f"depth: {env.get('water_depth_m')} m")
        L.append(f"- Sea state: {env.get('sea_state_hs_m')} m waves, {env.get('sea_state_tp_s')} s period  ·  "
                 f"current: {env.get('current_speed_mps')} m/s")
        L.append("")
        L.append("*Changing the test water (Kochi / Mumbai / Visakhapatnam) changes the environment, "
                 "not the security result — a vessel that is at risk is at risk in every water body.*")
        L.append("")

    # monitoring
    det = v.get("detectability", {})
    if det:
        n = det.get("alerts_generated", 0)
        L.append("## Would a monitor have noticed?")
        by = det.get("by_attack_type", {})
        if n:
            fams = ", ".join(f"{k} ({c})" for k, c in by.items())
            L.append(f"Yes — the passive monitor raised **{n}** alert(s) during the test ({fams}). "
                     "A defender watching the same feeds would have seen the attack happening.")
        else:
            L.append("No alerts were raised in this run — worth checking the monitor's coverage.")
        L.append("")

    L.append("---")
    L.append("*Generated by tools/report.py from the machine-checked verdicts.json. "
             "Findings describe the autopilot/command layer tested in simulation with the real firmware; "
             "see the twin's README for how faithfully the physical hull and the physical signal layer are modelled.*")
    return "\n".join(L)


def terminal_summary(v):
    rows = _flatten(v.get("attacks", {}))
    at_risk = sum(1 for r in rows if r[1] == "VULNERABLE")
    out = [f"\n  {v.get('target','?')}  ({v.get('domain','?')}, {v.get('site','?')})"]
    for key, verdict, _ in rows:
        title = ATTACKS.get(key, {}).get("title", key)
        out.append(f"    {VERDICT_MARK.get(verdict, verdict):12} {title}")
    out.append(f"  => {at_risk} of {len([r for r in rows if r[1] in ('VULNERABLE','RESILIENT','INCONCLUSIVE')])} "
               f"applicable attacks succeeded.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verdicts", help="path to a verdicts.json")
    ap.add_argument("--out", default=None, help="markdown output path (default: report.md beside verdicts.json)")
    args = ap.parse_args()
    with open(args.verdicts) as f:
        v = json.load(f)
    md = build_markdown(v)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.verdicts)), "report.md")
    with open(out, "w") as f:
        f.write(md + "\n")
    print(terminal_summary(v))
    print(f"\n  layman report written: {out}\n")


if __name__ == "__main__":
    main()
