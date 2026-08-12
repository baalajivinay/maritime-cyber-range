# Attack Surface: Ground Station ↔ Vehicle

Scope: **only** the MAVLink link between the operator's GCS and the
vehicle's autopilot — command, mission, and position traffic. Out of
scope: AIS (vehicle-to-other-vessels broadcast), GPS satellites, and this
project's sim-only physics relay (doesn't exist on real hardware).

**Root cause, one line**: MAVLink has no default sender authentication.
`source_system` is a self-declared field, not a credential — anyone who
can reach the port can claim to be the trusted GCS (sysid 255). Peer-reviewed
research confirms this is not specific to our twins: MAVLink v1 has zero
authentication, and MAVLink v2's optional "signing" adds no encryption and
is often left disabled for performance reasons. [1]

**This is not theoretical — it's happening at scale, right now.** GPS
spoofing hit over **12,000 recorded incidents affecting 3,000+ vessels in
just 11 days** in June 2025. [2] The first confirmed real-world GPS spoofing
attack was a mass incident affecting 20+ ships in the Black Sea in 2017,
and Black Sea/Romanian-coast interference has continued escalating through
2024–2025. [3] AIS spoofing surged 400% in 2022–23 and remains elevated. [4]
The **U.S. Navy's own FY2024 defense budget names GPS-spoofing and
remote-hijack hardening as a specific funded priority** for its Medium
Unmanned Surface Vessel program. [5] A federal watchdog testing real DoD
weapon systems found a two-person red team needed **one hour to gain
access and one day to gain full control**. [6] And in August 2026, a
routine security sweep found real, currently-deployed Royal Navy USVs
(Project Beehive, ~20 K3 Scout vessels) had components quietly
"phoning home" to an address in China. [7]

**What's real vs. what we can't confirm**: the exact internal C2 protocol
used by the actual Textron CUSV or actual Navy REMUS-100 is not public —
that's expected for fielded military hardware and we make no claim about
it. What *is* independently, publicly documented: ArduPilot itself is a
real, massively-deployed stack (over 1 million vehicles, including boats
and submarines) [8], the Navy's own current unmanned surface fleet under
Task Force 59 leans on lower-cost, commercially-sourced platforms (Saildrone
Explorer, MARTAC Mantas/Devil Ray, L3Harris Arabian Fox) [9] — exactly the
class of vehicle most likely to run something MAVLink-adjacent rather than
a fully bespoke classified stack — and every attack class below has a real,
current, publicly-documented incident behind it, even where the specific
platform isn't named.

## Attacks, ranked by real-world risk

| # | Attack | What it does | Tested here? | Real-world evidence | Risk |
|---|---|---|---|---|---|
| 1 | Command injection / replay | Forge arm, mode-change, RC-override | ✅ Yes | GAO red-team: 1hr to access, 1 day to full control on real DoD weapon systems [6] | **Critical** unhardened → **Low** hardened |
| 2 | Mission redirect | Silently change the programmed route | ❌ No | Same unauthenticated-link root cause as #1; no incident tracks this specifically because it's stealthy by design (no obvious "seizure" moment) | **Critical, untested** |
| 3 | Position spoofing | Forge GPS / vision position fix | ✅ Yes | 12,000+ incidents / 3,000+ vessels in 11 days, June 2025 [2]; first documented in the wild, Black Sea 2017 [3] | **Critical** — largest real-world attack class that exists today |
| 4 | Parameter tampering | Flip the twin's own hardening off (`PARAM_SET`) | ❌ No | Same root cause as #1; untested here and not seen as a named incident, but structurally identical exposure | **Critical, untested** |
| 5 | Rogue-GCS impersonation | Flood fake heartbeats to confuse failsafe | ❌ No | No named incident found; plausible given #1's root cause | **Medium** |
| 6 | Eavesdropping | Passively read traffic (plaintext by default) | Implicit | Confirmed structurally by MAVLink's own spec — no encryption even with signing on [1] | **Medium** (confidentiality, not takeover) |
| 7 | Flooding / DoS | Overload the link | ❌ No | No named incident found | **Medium-High** |
| 8 | Signing bypass | Only relevant once MAVLink2 signing is enabled | N/A | Confirmed limited real-world adoption — "hardware and performance constraints" [1] | Future hardening step |
| 9 | Arm-race exploit | Sneak a command through ArduSub's known ~1s auto-disarm glitch | Adjacent | This project's own finding, not yet seen in the wild | **Low-Medium** |
| — | Supply-chain / component-level (different attack class, not GCS-link) | A trusted component itself leaks data | N/A | **Real, current**: Royal Navy K3 Scout USVs found phoning home to a Chinese IP, Aug 2026 [7] | Flagged for awareness — outside this table's scope but shows the pattern is live on fielded hardware today |

## Priority next steps

1. **#2, mission redirect** — likely works, cheapest to build (the upload
   mechanism already exists in `goto()`, just needs packaging as an attack).
2. **#4, parameter tampering** — the sharpest edge: if this isn't gated the
   same way command injection is, it could silently undo the resilient
   twin's own defense before the "real" attack even runs.
3. **#3, position spoofing** — already tested and already the single
   biggest real-world attack class in this whole table; worth featuring
   prominently in any presentation of this project given the June 2025
   scale data above.

## Sources

1. [MAVLink Protocol: A Survey of Security Threats and Countermeasures](https://www.researchgate.net/publication/385670293_MAVLink_Protocol_A_Survey_of_Security_Threats_and_Countermeasures)
2. [Navigating the Cybersecurity Waters: Protecting Connected Vessels in 2025](https://www.mdmarineelectric.com/post/cybersecurity-for-connected-vessels-protecting-against-digital-threats-at-sea)
3. [Suspected mass-spoofing of ships' GPS in the Black Sea — Sophos](https://news.sophos.com/en-us/2017/09/26/suspected-mass-spoofing-of-ships-gps-in-the-black-sea/)
4. [AIS Spoofing in the Maritime Industry: A Growing Risk and Compliance Challenge](https://www.marinetraffic.com/en/maritime-news/34/risk-and%20compliance/2025/11316/ais-spoofing-in-the-maritime-industry-a-growing-risk-and-com)
5. FY2024 NDAA — MUSV hull procurement funding tied to cybersecurity hardening against GPS spoofing/remote hijack (via search aggregation, see [UAS/UUV Threats launched from Ships](https://pressbooks.pub/maritimesecurity11/chapter/uas-uuv-threats-launched-from-ships-mumm-ghaffari/))
6. [GAO-19-128: Weapon Systems Cybersecurity](https://www.gao.gov/products/gao-19-128)
7. [Chinese Components In Royal Navy's New Drone Boat Raise Cyber Security Concerns — TWZ](https://www.twz.com/sea/chinese-components-in-royal-navys-new-drone-boat-raise-cyber-security-concerns)
8. [ArduPilot — Wikipedia](https://en.wikipedia.org/wiki/ArduPilot)
9. [Task Force 59 Unmanned Integration — Saildrone](https://www.saildrone.com/missions/task-force-59-unmanned-integration); [Commander: Navy's new Task Group 59.1 — Breaking Defense](https://breakingdefense.com/2024/01/commander-navys-new-task-group-59-1-to-usher-unmanned-systems-into-operational-realm/)
