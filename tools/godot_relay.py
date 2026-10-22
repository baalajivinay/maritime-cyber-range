#!/usr/bin/env python3
"""
Godot <-> cyber-range relay.

The Godot 4 front-end (godot_app/) renders the ocean and HUD but never touches
MAVLink. This relay owns the real side: it reuses nodes/app/mcr_app.py's Backend
(boot headless SITL+Gazebo, live MAVLink telemetry, GUIDED goto with robust arm,
attacks, the AUV USBL/ExternalNav feed) and speaks JSON/UDP to Godot:

  telemetry  relay --(JSON)--> 127.0.0.1:14650  (Godot listens)
  commands   Godot --(JSON)--> 127.0.0.1:14651  (relay listens)

Commands: {"cmd":"boot","site","twin","domain"} | {"cmd":"goto","lat","lon"}
          {"cmd":"arm"|"disarm"|"stop"|"quit"} | {"cmd":"attack","name"}

Sources (pick the physics engine Godot renders):
  --source gazebo     (default) boots a Gazebo world via mcr_app.Backend
  --source stonefish  attaches to a running tools/stonefish_bridge.sh stack, so
                      Godot renders Stonefish's high-fidelity physics (both
                      softwares combined).
"""
import json
import os
import socket
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "nodes", "app"))
import mcr_app as M
try:
    from scaleup.sites import load_site
except Exception:
    load_site = None

SOURCE = "stonefish" if "--source" in sys.argv and sys.argv[sys.argv.index("--source") + 1] == "stonefish" else "gazebo"


def make_backend():
    if SOURCE == "stonefish":
        from stonefish_source import StonefishSource
        return StonefishSource()
    return M.Backend()

TELE_ADDR = ("127.0.0.1", 14650)
CMD_PORT = 14651


def waves_for(site):
    if load_site:
        try:
            s = load_site(site)
            return {"hs": s.sea_state["sig_wave_height_m"], "tp": s.sea_state["period_s"],
                    "bearing": s.current.get("bearing_deg", 160.0)}
        except Exception:
            pass
    return {"hs": 1.2, "tp": 7.0, "bearing": 160.0}


def main():
    be = make_backend()
    print(f"[relay] physics source = {SOURCE}", flush=True)
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("127.0.0.1", CMD_PORT))
    rx.settimeout(0.05)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[relay] commands on :{CMD_PORT}  ->  telemetry to {TELE_ADDR}", flush=True)
    site = "kochi"
    last_tele = 0.0
    running = True
    while running:
        # --- commands from Godot ---
        try:
            data, _ = rx.recvfrom(2048)
            d = json.loads(data.decode("utf-8"))
            c = d.get("cmd")
            if c == "boot":
                site = d.get("site", "kochi")
                be.teardown()
                be = make_backend()
                be.boot(site, d["twin"], d.get("domain", "surface"))
                print(f"[relay] boot {d['twin']} @ {site} (source={SOURCE})", flush=True)
            elif c == "goto":
                be.goto(float(d["lat"]), float(d["lon"]))
            elif c == "arm":
                be.arm()
            elif c == "disarm":
                be.disarm()
            elif c == "attack":
                import threading
                threading.Thread(target=be.attack, args=(d["name"],), daemon=True).start()
            elif c == "stop":
                be.stop_attack()
            elif c == "quit":
                running = False
        except socket.timeout:
            pass
        except Exception as e:
            print(f"[relay] cmd error: {e}", flush=True)
        # --- telemetry to Godot (~15 Hz) ---
        now = time.time()
        if now - last_tele > 0.066:
            last_tele = now
            with be.lock:
                st = dict(be.state)
            ev = be.events[-1][1] if be.events else ""
            pkt = {
                "connected": be.connected, "booting": be.booting,
                "domain": be.domain, "twin": be.twin or "",
                "home": [be.home[0], be.home[1]],
                "waves": waves_for(site),
                "lat": st.get("lat"), "lon": st.get("lon"),
                "hdg": st.get("hdg", 0.0), "speed": st.get("speed", 0.0),
                "depth": st.get("depth", 0.0), "mode": st.get("mode", "--"),
                "armed": st.get("armed", False),
                "active_attack": be.active_attack or "",
                "event": ev,
            }
            try:
                tx.sendto(json.dumps(pkt).encode("utf-8"), TELE_ADDR)
            except OSError:
                pass
    be.teardown()
    print("[relay] stopped", flush=True)


if __name__ == "__main__":
    main()
