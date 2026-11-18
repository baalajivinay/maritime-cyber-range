#!/usr/bin/env python3
"""
End-to-end matrix test of the app.sh stack, driven exactly like the Godot front-end:
launches tools/godot_relay.py (the unified router) and talks to it over the same
JSON/UDP protocol (telemetry :14650, commands :14651). For every (site, vehicle)
it checks boot, home/fix, waves, ARM, a GUIDED destination (speed, heading,
progress, arrival) and every attack the HUD offers for that domain (effect + STOP).

  python3 tools/e2e_matrix.py [--sites kochi,mumbai] [--twins auv150,...] [--quick]
Writes /tmp/mcr_run/e2e_matrix.json and prints a verdict table.
"""
import argparse
import json
import math
import os
import socket
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DEG_M = 111320.0
TWINS = {"interceptor_usv": "surface", "survey_usv": "surface",
         "maya_auv": "underwater", "auv150": "underwater"}
SURFACE_ATTACKS = ["GPS spoof", "C2 mode", "C2 override", "AIS ghost"]
UNDERWATER_ATTACKS = ["Acoustic spoof", "C2 mode", "C2 override"]


def dist_m(a, b):
    return DEG_M * math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0])))


def bearing(a, b):
    dn = (b[0] - a[0]) * DEG_M
    de = (b[1] - a[1]) * DEG_M * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(de, dn)) % 360


class Godot:
    """Plays the role of the Godot app: receives telemetry, sends commands."""
    def __init__(self):
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rx.bind(("127.0.0.1", 14650))
        self.rx.settimeout(0.5)
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last = {}
        self.n = 0
        self.events = []          # distinct event strings seen
        self._stop = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop:
            try:
                data, _ = self.rx.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                d = json.loads(data.decode())
            except Exception:
                continue
            self.last = d
            self.n += 1
            ev = d.get("event")
            if ev and (not self.events or self.events[-1] != ev):
                self.events.append(ev)

    def send(self, d):
        self.tx.sendto(json.dumps(d).encode(), ("127.0.0.1", 14651))

    def pos(self):
        la, lo = self.last.get("lat"), self.last.get("lon")
        if la is None or lo is None:
            return None
        if la == 0 and lo == 0:
            return None  # ArduPilot's "no fix yet" sentinel, not a real position
        return (la, lo)

    def wait(self, cond, timeout, step=0.25):
        t = time.time()
        while time.time() - t < timeout:
            if cond(self.last):
                return True
            time.sleep(step)
        return False

    def close(self):
        self._stop = True


def start_relay(logpath):
    subprocess.run(["bash", os.path.join(REPO, "tools", "teardown_all.sh")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-x", "MCR"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-x", "ardusub"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "godot_rela[y]"], stderr=subprocess.DEVNULL)
    time.sleep(2)
    env = dict(os.environ, MCR_HEADLESS="1")
    return subprocess.Popen([sys.executable, "-u", os.path.join(REPO, "tools", "godot_relay.py")],
                            stdout=open(logpath, "w"), stderr=subprocess.STDOUT,
                            env=env, cwd=REPO, start_new_session=True)


def site_home(site):
    from scaleup.sites import load_site
    s = load_site(site)
    return tuple(s.position), s


def check(res, name, ok, detail=""):
    res["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"    [{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)


def run_combo(g, site, twin, quick):
    dom = TWINS[twin]
    res = {"site": site, "twin": twin, "domain": dom, "checks": []}
    home, s = site_home(site)
    print(f"\n=== {twin} @ {site} ({dom}) ===", flush=True)
    g.last = {}
    g.events.clear()
    g.send({"cmd": "boot", "site": site, "twin": twin, "domain": dom})

    # ---- boot ----
    t0 = time.time()
    ok = g.wait(lambda d: d.get("connected") and d.get("lat") is not None, 150)
    boot_s = time.time() - t0
    check(res, "boot: connected + position fix", ok, f"({boot_s:.0f}s)")
    if not ok:
        res["fatal"] = "no connect/fix"
        return res
    time.sleep(6)
    p = g.last
    check(res, "telemetry domain/twin", p.get("domain") == dom and p.get("twin") == twin,
          f"(got {p.get('domain')}/{p.get('twin')})")
    ph = tuple(p.get("home") or (0, 0))
    check(res, "relay home == site home", dist_m(ph, home) < 50,
          f"(relay {ph} vs site {home}, {dist_m(ph, home):.0f} m)")
    fix = g.pos()
    check(res, "vehicle fix near site home", dist_m(fix, home) < 300,
          f"(fix {fix[0]:.5f},{fix[1]:.5f} is {dist_m(fix, home):.0f} m from home)")
    w = p.get("waves") or {}
    exp_hs = s.sea_state["sig_wave_height_m"]
    check(res, "waves match site sea-state", abs(w.get("hs", -1) - exp_hs) < 0.05,
          f"(hs {w.get('hs')} vs site {exp_hs})")
    check(res, "idle speed ~0 before arm", abs(p.get("speed", 9)) < 0.6, f"(speed {p.get('speed')})")

    # ---- ARM ----
    g.send({"cmd": "arm"})
    ok = g.wait(lambda d: d.get("armed"), 25)
    check(res, "ARM -> armed", ok, f"(mode {g.last.get('mode')})")

    # ---- destination ----
    start = g.pos()
    DIST = 35.0 if quick else 70.0
    brg = 60.0
    tgt = (start[0] + DIST * math.cos(math.radians(brg)) / DEG_M,
           start[1] + DIST * math.sin(math.radians(brg)) / (DEG_M * math.cos(math.radians(start[0]))))
    d0 = dist_m(start, tgt)
    print(f"    goto {d0:.0f} m @ {brg:.0f}deg", flush=True)
    g.send({"cmd": "goto", "lat": tgt[0], "lon": tgt[1]})
    speeds, hdgs, depths, mind = [], [], [], d0
    t0 = time.time()
    first_move = None
    arrived = False
    # generous margin: these are slow Tier-A hulls (~0.3-1.0 m/s observed), not
    # the real vehicles' top speed -- size the wait off distance, not a guess.
    max_wait = max(60.0, (DIST / 0.3) * 1.4)
    while time.time() - t0 < max_wait:
        time.sleep(1.0)
        pp = g.pos()
        if pp is None:
            continue
        dd = dist_m(pp, tgt)
        mind = min(mind, dd)
        speeds.append(g.last.get("speed", 0.0))
        depths.append(g.last.get("depth", 0.0))
        if first_move is None and dist_m(pp, start) > 2.0:
            first_move = time.time() - t0
        if dd < 4.0:
            arrived = True
            break
    end = g.pos()
    moved = dist_m(end, start)
    vmax = max(speeds) if speeds else 0
    vavg = (sum(s_ for s_ in speeds if s_ > 0.2) / max(1, sum(1 for s_ in speeds if s_ > 0.2)))
    check(res, "destination: vehicle starts moving", first_move is not None,
          f"(first motion after {first_move:.0f}s)" if first_move else "(never moved)")
    check(res, "destination: closes on target", mind < d0 * 0.5,
          f"(start {d0:.0f} m -> closest {mind:.0f} m, moved {moved:.0f} m)")
    check(res, "destination: arrives (<4 m)", arrived, f"(closest {mind:.1f} m)")
    check(res, "speed sane (0.3..25 m/s)", 0.3 < vmax < 25, f"(max {vmax:.2f}, moving-avg {vavg:.2f} m/s)")
    res["speed_max"] = round(vmax, 2)
    res["speed_avg"] = round(vavg, 2)
    if moved > 10:
        mb = bearing(start, end)
        err = abs((mb - brg + 180) % 360 - 180)
        check(res, "track bearing toward target", err < 35, f"(moved on {mb:.0f}deg, wanted {brg:.0f}deg)")
        hd = g.last.get("hdg", 0.0)
    if dom == "underwater":
        dmax = max(depths) if depths else 0
        check(res, "AUV stays submerged while navigating", dmax > 0.5, f"(max depth {dmax:.1f} m)")
        res["depth_max"] = round(dmax, 1)

    # ---- attacks ----
    atk_list = UNDERWATER_ATTACKS if dom == "underwater" else SURFACE_ATTACKS
    hold = g.pos()
    for name in atk_list:
        base_pos, base_mode, base_arm = g.pos(), g.last.get("mode"), g.last.get("armed")
        g.send({"cmd": "attack", "name": name})
        time.sleep(1.0)
        check(res, f"{name}: HUD shows it active", g.last.get("active_attack") == name,
              f"(active_attack={g.last.get('active_attack')!r})")
        peak, modes, spd_peak = 0.0, set(), 0.0
        t0 = time.time()
        while time.time() - t0 < (14 if not quick else 9):
            time.sleep(0.5)
            pp = g.pos()
            if pp:
                peak = max(peak, dist_m(pp, base_pos))
            modes.add(g.last.get("mode"))
            spd_peak = max(spd_peak, g.last.get("speed", 0.0))
        if name in ("GPS spoof", "Acoustic spoof"):
            check(res, f"{name}: believed position walks off", peak > 5.0, f"(peak shift {peak:.1f} m)")
        elif name == "C2 mode":
            check(res, f"{name}: autopilot mode forced", len(modes - {base_mode}) > 0,
                  f"(was {base_mode}, saw {sorted(m for m in modes if m)})")
        elif name == "C2 override":
            check(res, f"{name}: vehicle commandeered", (spd_peak > 0.4) or (len(modes - {base_mode}) > 0),
                  f"(peak speed {spd_peak:.2f}, modes {sorted(m for m in modes if m)})")
        elif name == "AIS ghost":
            check(res, f"{name}: operator-layer event raised",
                  any("AIS" in e for e in g.events[-6:]), f"(events {g.events[-2:]})")
        g.send({"cmd": "stop"})
        time.sleep(2.5)
        check(res, f"{name}: STOP clears it", not g.last.get("active_attack"),
              f"(active_attack={g.last.get('active_attack')!r})")
        if name in ("GPS spoof", "Acoustic spoof"):
            # after STOP the believed position must settle back near the real track
            g.wait(lambda d: False, 12)
            back = dist_m(g.pos(), base_pos) if g.pos() else 999
            check(res, f"{name}: position recovers after STOP", back < max(15.0, peak * 0.5),
                  f"(offset now {back:.1f} m, peak was {peak:.1f} m)")
        # re-establish a calm baseline for the next attack
        g.send({"cmd": "goto", "lat": hold[0], "lon": hold[1]})
        time.sleep(3)

    g.send({"cmd": "disarm"})
    time.sleep(1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default="kochi,mumbai,visakhapatnam")
    ap.add_argument("--twins", default=",".join(TWINS))
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default="/tmp/mcr_run/e2e_matrix.json")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    g = Godot()
    relay = start_relay("/tmp/mcr_run/e2e_relay.log")
    time.sleep(4)
    results = []
    try:
        for site in a.sites.split(","):
            for twin in a.twins.split(","):
                try:
                    r = run_combo(g, site, twin, a.quick)
                except Exception as e:
                    r = {"site": site, "twin": twin, "fatal": f"harness exception: {e!r}", "checks": []}
                    print("    EXCEPTION", repr(e), flush=True)
                results.append(r)
                json.dump(results, open(a.out, "w"), indent=1)
    finally:
        g.send({"cmd": "quit"})
        time.sleep(2)
        try:
            os.killpg(relay.pid, 15)
        except Exception:
            pass
        subprocess.run(["bash", os.path.join(REPO, "tools", "teardown_all.sh")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-x", "MCR"], stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-x", "ardusub"], stderr=subprocess.DEVNULL)

    print("\n================ SUMMARY ================")
    bad = 0
    for r in results:
        fails = [c for c in r["checks"] if not c["ok"]]
        bad += len(fails) + (1 if r.get("fatal") else 0)
        tag = "FATAL " + r["fatal"] if r.get("fatal") else ("OK" if not fails else f"{len(fails)} FAIL")
        print(f"{r['twin']:16s} {r['site']:14s} {tag}  v_max={r.get('speed_max')} v_avg={r.get('speed_avg')}")
        for c in fails:
            print(f"      x {c['name']} {c['detail']}")
    print(f"\n{bad} failing checks")


if __name__ == "__main__":
    main()
