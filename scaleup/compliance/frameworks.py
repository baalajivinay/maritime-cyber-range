"""Pluggable compliance mapping (Axis 1.5). scaleup/scenario/standards.py maps a
finding to IACS UR E26/E27 + IMO MSC.428(98). This generalises that to a
multi-framework mapper so one finding can be reported against whichever regime a
given buyer/evaluator recognises -- class society, flag state, or ICS security.

Data-driven: add a framework by adding a column to _MAP. References are to named
documents, not fabricated sub-clauses (same honesty rule as standards.py).
"""

# finding kind (consequence type OR attack family) -> {framework: (control, reference)}
_MAP = {
    "position_divergence": {
        "IACS UR E26": ("Position/navigation data integrity; detection of anomalous sensor input", "E26"),
        "IACS UR E27": ("Integrity of data at the navigation/position sensor interface", "E27"),
        "IEC 62443-3-3": ("SR 3.5 Input validation; SR 3.8 Session integrity of control data", "3-3"),
        "NIST SP 800-82r3": ("SI-10 Information input validation; SI-4 OT monitoring", "800-82r3"),
        "MITRE ATT&CK ICS": ("T0830 Man-in-the-Middle; T0856 Spoof Reporting Message", "ICS"),
        "DNV-CG-0325": ("Navigation system data integrity under compromised sensor input", "CG-0325"),
    },
    "grounding": {
        "IACS UR E26": ("Safety-critical navigation resilience; failure must not cause loss of the ship", "E26"),
        "IMO MSC.428(98)": ("Risk management: highest-consequence cyber event handling in the SMS", "MSC.428(98)"),
        "IEC 62443-3-3": ("SR 3.6 Deterministic output; safety-related function integrity", "3-3"),
        "MITRE ATT&CK ICS": ("T0880 Loss of Safety; T0831 Manipulation of Control", "ICS"),
    },
    "nogo_breach": {
        "IACS UR E26": ("Operational boundary protection under compromised inputs", "E26"),
        "IMO MSC.428(98)": ("Risk management: safety consequence of a cyber event in the SMS", "MSC.428(98)"),
        "NIST SP 800-82r3": ("AC-4 Information flow / geofence enforcement", "800-82r3"),
    },
    "cpa_violation": {
        "IACS UR E26": ("Collision-avoidance integrity under manipulated inputs (COLREG-relevant)", "E26"),
        "IMO MSC.428(98)": ("Risk management: collision risk from a cyber event", "MSC.428(98)"),
        "MITRE ATT&CK ICS": ("T0856 Spoof Reporting Message (AIS)", "ICS"),
    },
    "gps_spoof": {
        "IACS UR E26": ("GNSS input integrity", "E26"),
        "IACS UR E27": ("Sensor-interface integrity", "E27"),
        "IEC 62443-3-3": ("SR 3.5 Input validation", "3-3"),
        "MITRE ATT&CK ICS": ("T0856 Spoof Reporting Message", "ICS"),
    },
    "acoustic_spoof": {
        "IACS UR E27": ("External-navigation (acoustic/USBL) input integrity", "E27"),
        "IEC 62443-3-3": ("SR 3.5 Input validation at the ExternalNav interface", "3-3"),
        "MITRE ATT&CK ICS": ("T0830 Man-in-the-Middle", "ICS"),
    },
    "c2_replay": {
        "IACS UR E26": ("Authenticated command & control", "E26"),
        "IACS UR E27": ("Command-interface authentication/authorisation", "E27"),
        "IEC 62443-3-3": ("SR 1.1/1.2 Identification & authentication; SR 2.1 Authorization enforcement", "3-3"),
        "NIST SP 800-82r3": ("AC-3 Access enforcement; IA-2 Identification & authentication", "800-82r3"),
        "MITRE ATT&CK ICS": ("T0855 Unauthorized Command Message; T0831 Manipulation of Control", "ICS"),
    },
    "ais_spoof": {
        "IACS UR E26": ("AIS data integrity and plausibility checking", "E26"),
        "IMO MSC.428(98)": ("Risk management: integrity of situational-awareness data", "MSC.428(98)"),
        "MITRE ATT&CK ICS": ("T0856 Spoof Reporting Message", "ICS"),
    },
}

ALL_FRAMEWORKS = sorted({fw for m in _MAP.values() for fw in m})


def controls_for(kind, frameworks=None):
    """Return [(framework, control, reference), ...] for a finding kind, limited
    to `frameworks` if given (else all mapped)."""
    m = _MAP.get(kind, {})
    want = set(frameworks) if frameworks else None
    return [(fw, ctrl, ref) for fw, (ctrl, ref) in m.items() if want is None or fw in want]


def map_verdicts(verdicts, frameworks=None):
    """Given {attack_family: verdict}, return the compliance controls implicated
    by every VULNERABLE finding -- the procurement-facing output."""
    out = {}
    for family, verdict in verdicts.items():
        if str(verdict).upper() == "VULNERABLE":
            out[family] = controls_for(family, frameworks)
    return out
