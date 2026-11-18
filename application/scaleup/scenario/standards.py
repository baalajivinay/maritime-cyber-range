"""Map scenario findings to the maritime cyber standards a naval / class-society
evaluator recognises. This is the bridge from 'position diverged 50 m' to
'fails a recognised cyber-resilience control' -- the procurement-relevant output.

References are to the named standards documents (not fabricated sub-clauses):
  * IACS UR E26  -- Cyber resilience of ships (ship-level, incl. navigation/
                    position integrity, networks).
  * IACS UR E27  -- Cyber resilience of on-board systems and equipment
                    (component-level: the autopilot/CMS and its interfaces).
  * IMO Res. MSC.428(98) -- Maritime cyber risk management in the ship's Safety
                    Management System (operational/risk-management obligation).

Exact clause-level mapping is a Phase-II refinement to be done with the
controlling authority; this gives the evaluator the right documents and the
nature of the control each finding implicates.
"""

_MAP = {
    "position_divergence": [
        ("IACS UR E26", "Position/navigation data integrity; detection of anomalous sensor input"),
        ("IACS UR E27", "Integrity of data exchanged with navigation/position sensors at the equipment interface"),
    ],
    "nogo_breach": [
        ("IACS UR E26", "Safe navigation under compromised inputs; operational boundary protection"),
        ("IMO MSC.428(98)", "Risk management: safety consequence of a cyber event in the SMS"),
    ],
    "grounding": [
        ("IACS UR E26", "Safety-critical navigation resilience; failure must not cause loss of the ship"),
        ("IMO MSC.428(98)", "Risk management: highest-consequence scenario handling in the SMS"),
    ],
    "cpa_violation": [
        ("IACS UR E26", "Collision-avoidance integrity under manipulated inputs (COLREG-relevant)"),
        ("IMO MSC.428(98)", "Risk management: collision risk from a cyber event"),
    ],
    # attack-family level (used by the report's per-attack section)
    "gps_spoof": [("IACS UR E26", "GNSS input integrity"), ("IACS UR E27", "Sensor-interface integrity")],
    "acoustic_spoof": [("IACS UR E27", "External-navigation (acoustic/USBL) input integrity")],
    "c2_replay": [("IACS UR E26", "Authenticated command & control"), ("IACS UR E27", "Command-interface authentication/authorisation")],
    "ais_spoof": [("IACS UR E26", "AIS data integrity and plausibility checking")],
}


def controls_for(kind):
    """Return [(standard, control-description), ...] for a consequence type or
    attack family. Empty list if unmapped."""
    return _MAP.get(kind, [])
