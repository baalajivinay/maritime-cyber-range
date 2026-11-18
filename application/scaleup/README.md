# Scale-up work — isolation contract + scenario engine

This tree holds **additive, default-off** scale-up modules. The rule that
protects the shipped Ubuntu/Windows package:

> **Nothing here is imported or called by the shipped package's default flow.**
> The release image (`mcr:latest`) is built only from the `release/app-v1` tag
> via `deploy/Dockerfile`. Scale-up runs in a *separate* image, `mcr:dev`, built
> from `deploy/Dockerfile.dev`, which layers this code **on top of** the frozen
> release image and never rebuilds it.

### The five-rule contract
1. Release baseline is tagged **`release/app-v1`** and frozen.
2. All scale-up work lands on the **`scaleup`** branch, never on `master`'s release path.
3. New dependencies go in **`deploy/Dockerfile.dev` → `mcr:dev`**, never in `deploy/Dockerfile`.
4. Everything is **additive** (new files) and **default-off** (no edits to `run_sim.sh` / `test_target.py` / the boot path).
5. **`tools/test_all_4.py`** is the regression gate before anything merges toward release.

Build the dev image (release image must exist first):
```bash
docker build -f deploy/Dockerfile      -t mcr:latest .   # frozen package (from release/app-v1)
docker build -f deploy/Dockerfile.dev  -t mcr:dev    .   # + scale-up code
```

## Scenario engine (first scale-up module)

Composes the project's existing attacks into a **timed mission** and grades it by
**operational consequence** — then maps findings to IACS UR E26/E27 & IMO
MSC.428(98). This is the step that turns "position diverged 50 m" into evidence a
naval / class-society evaluator can act on.

```bash
# sim mode: synthetic model, no live sim / Docker / hardware needed
python3 tools/run_scenario.py scenarios/harbor_transit_gps_walkoff.json
python3 tools/run_scenario.py scenarios/<x>.json --out target_runs/scenario_x
python3 tools/run_scenario.py scenarios/<x>.json --mode live   # needs a booted twin (scaffolded)

# offline unit tests
python3 scaleup/tests/test_scenario.py
```

### Layout
| File | Role |
|---|---|
| `scenario/model.py` | Scenario schema + JSON loader |
| `scenario/executors.py` | `SimExecutor` (synthetic, default) + `LiveExecutor` (scaffold for the real stack) |
| `scenario/consequences.py` | Operational consequence evaluators (divergence / no-go / grounding / CPA) |
| `scenario/standards.py` | Finding → IACS E26/E27 & IMO MSC.428(98) mapping |
| `scenario/engine.py` | Orchestration |
| `scenario/report.py` | Markdown (evaluator-facing) + JSON (machine) output |
| `scenarios/*.json` | Example missions |

### Extending (the plugin convention)
- **New attack** → add a timeline `action` string + handle it in `LiveExecutor`
  (and, if it moves position, in `SimExecutor._offset_ne_at`).
- **New consequence** → add an evaluator in `consequences.py` + a dispatch arm in
  `evaluate()`; map it in `standards.py`.
- **New executor / vehicle backend** → subclass `Executor`.

Each is purely additive — no change to the shipped package.

## Upscale modules (generic + real-physics)

Additive, default-off packages that make the range firmware-/protocol-agnostic
and raise physics fidelity. See `docs/ROADMAP.md` for status per item. Tests:
`python3 scaleup/tests/test_upscale.py`.

- `backends/` — autopilot-agnostic `VehicleBackend` (ArduPilot + PX4), attack-
  vector applicability matrix, `registry`.
- `protocols/` — `ProtocolAdapter` seam: `mavlink_adapter`, and a real stdlib
  `nmea0183` codec + `NMEASpoofer` (the serial-bus analog of the GPS relay; same
  wire format the ESP32 NMEA injector emits).
- `twins/` — `registry.discover()`/`conformance()` and a `twin init` scaffolder.
- `compliance/` — multi-framework mapping (IACS UR E26/E27, IMO MSC.428(98),
  IEC 62443-3-3, NIST SP 800-82r3, MITRE ATT&CK for ICS, DNV-CG-0325).
- `physics/` — `sensors` (GNSS/IMU/DVL/mag error), `seastate` (JONSWAP),
  `tides` (harmonic flood/ebb), `acoustics_bellhop` (image-method multipath +
  Bellhop adapter), `ingest` (CTD/WOA profile → exact eqns), `bathymetry`
  (CSV/GEBCO + grounding), `ais_feed` (real AIS traffic).
- `platform/api.py` — range-as-a-service REST API over the existing tools.

Live hardware-in-the-loop firmware is under `hardware/` (ESP32 C2 node + NMEA
injector).
