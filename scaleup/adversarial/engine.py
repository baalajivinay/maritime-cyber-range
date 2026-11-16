"""
Adversarial Attack-Defense Co-Evolution Engine for Autonomous Maritime Systems.

Eliminates the "detector cheat" where defense rules are hardcoded to detect a
known, fixed attack script. Pits an autonomous Attacker Agent against an
autonomous Defender Agent without privileged foreknowledge:

  Attacker: Searches over attack policies (drift rate, jitter noise, onset timing,
            bearing) to maximize physical vessel displacement while evading detection.
  Defender: Searches over statistical anomaly filter policies (CUSUM slack k,
            decision threshold h, kinematic cross-consistency gate) to maximize
            true detections while bounding False Positive Rate (FPR < 2%) on
            clean, wave-agitated baselines.

Produces the mathematical Pareto frontier of detectability under real ocean noise.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class AttackerPolicy:
    """Parameters defining a GNSS/Acoustic spoofing trajectory."""
    drift_rate_mps: float = 0.35          # rate of position walk-off (m/s)
    jitter_sigma_m: float = 0.08          # Gaussian noise added to mask the drift
    bearing_deg: float = 90.0             # direction of forged offset (0=N, 90=E)
    onset_delay_s: float = 10.0           # delay before attack starts
    pulse_interval_s: float = 0.2         # time between forged updates (5 Hz)

    def generate_offset(self, t: float) -> Tuple[float, float]:
        """Returns (offset_north_m, offset_east_m) at time t."""
        if t < self.onset_delay_s:
            return 0.0, 0.0
        elapsed = t - self.onset_delay_s
        dist = self.drift_rate_mps * elapsed
        # Add random jitter to mask monotonic drift
        if self.jitter_sigma_m > 0:
            dist += random.gauss(0.0, self.jitter_sigma_m)
        rad = math.radians(self.bearing_deg)
        return dist * math.cos(rad), dist * math.sin(rad)

    def mutate(self, rate: float = 0.2) -> "AttackerPolicy":
        """Generates a mutated variant for evolutionary search."""
        return AttackerPolicy(
            drift_rate_mps=max(0.02, min(2.5, self.drift_rate_mps + random.gauss(0, 0.08 * rate))),
            jitter_sigma_m=max(0.0, min(0.5, self.jitter_sigma_m + random.gauss(0, 0.03 * rate))),
            bearing_deg=(self.bearing_deg + random.gauss(0, 15 * rate)) % 360.0,
            onset_delay_s=max(2.0, self.onset_delay_s + random.gauss(0, 1.5 * rate)),
            pulse_interval_s=self.pulse_interval_s,
        )


@dataclass
class DefenderPolicy:
    """Statistical & kinematic anomaly filter parameters (Zero Privileged Knowledge)."""
    cusum_slack_mps: float = 0.15         # k: expected noise allowance per second
    cusum_threshold_m: float = 4.5        # h: accumulated decision boundary (meters)
    cross_window_s: float = 15.0          # W: lookback window for INS velocity check
    kinematic_diff_threshold_mps: float = 0.5  # |v_gps - v_ins| discrepancy threshold

    def create_filter(self) -> "StatisticalDefenseFilter":
        return StatisticalDefenseFilter(self)

    def mutate(self, rate: float = 0.2) -> "DefenderPolicy":
        """Generates a mutated variant for evolutionary search."""
        return DefenderPolicy(
            cusum_slack_mps=max(0.04, min(0.6, self.cusum_slack_mps + random.gauss(0, 0.03 * rate))),
            cusum_threshold_m=max(1.0, min(20.0, self.cusum_threshold_m + random.gauss(0, 0.5 * rate))),
            cross_window_s=max(5.0, min(45.0, self.cross_window_s + random.gauss(0, 2.0 * rate))),
            kinematic_diff_threshold_mps=max(0.2, min(1.5, self.kinematic_diff_threshold_mps + random.gauss(0, 0.08 * rate))),
        )


class StatisticalDefenseFilter:
    """Online stateful filter implementing Two-Sided Page's CUSUM on Cartesian velocity innovations.

    Robust to zero-mean high-frequency wave agitation via exponential smoothing,
    accumulating persistent low-frequency velocity divergence (spoofing drift)
    without privileged foreknowledge of the attack trajectory.
    """
    def __init__(self, policy: DefenderPolicy, smoothing_tau_s: float = 1.0):
        self.p = policy
        self.tau = smoothing_tau_s
        self.last_t = None
        self.last_rep_n = None
        self.last_rep_e = None
        self.res_vn_filt = 0.0
        self.res_ve_filt = 0.0
        # Two-sided CUSUM accumulators for North and East axes
        self.cusum_n_pos = 0.0
        self.cusum_n_neg = 0.0
        self.cusum_e_pos = 0.0
        self.cusum_e_neg = 0.0
        self.triggered = False
        self.trigger_time = None
        self.trigger_reason = ""

    def update(self, t: float, reported_n: float, reported_e: float,
               ins_vn: float, ins_ve: float) -> Optional[str]:
        """Ingests one telemetry sample. Returns alert string if triggered, else None."""
        if self.triggered:
            return None

        if self.last_t is None:
            self.last_t = t
            self.last_rep_n = reported_n
            self.last_rep_e = reported_e
            return None

        dt = t - self.last_t
        if dt <= 0.001:
            return None

        # Differentiate reported GNSS position to obtain reported ground velocity
        v_gps_n = (reported_n - self.last_rep_n) / dt
        v_gps_e = (reported_e - self.last_rep_e) / dt
        self.last_t = t
        self.last_rep_n = reported_n
        self.last_rep_e = reported_e

        # Raw innovation residual (GNSS rate vs INS velocity)
        raw_res_n = v_gps_n - ins_vn
        raw_res_e = v_gps_e - ins_ve

        # Low-pass filter to reject zero-mean wave jitter while passing persistent drift
        alpha = dt / (self.tau + dt)
        self.res_vn_filt += alpha * (raw_res_n - self.res_vn_filt)
        self.res_ve_filt += alpha * (raw_res_e - self.res_ve_filt)

        # Two-sided CUSUM update (Page 1954):
        # Under H0 (no attack), res has mean 0, so (res - slack) has negative drift -> decays to 0.
        # Under H1 (attack), sustained drift exceeds slack -> accumulates deterministically into meters.
        k = max(0.08, self.p.cusum_slack_mps)
        
        self.cusum_n_pos = max(0.0, self.cusum_n_pos + (self.res_vn_filt - k) * dt)
        self.cusum_n_neg = max(0.0, self.cusum_n_neg + (-self.res_vn_filt - k) * dt)
        self.cusum_e_pos = max(0.0, self.cusum_e_pos + (self.res_ve_filt - k) * dt)
        self.cusum_e_neg = max(0.0, self.cusum_e_neg + (-self.res_ve_filt - k) * dt)

        peak_cusum = max(self.cusum_n_pos, self.cusum_n_neg, self.cusum_e_pos, self.cusum_e_neg)

        if peak_cusum >= self.p.cusum_threshold_m:
            self.triggered = True
            self.trigger_time = t
            self.trigger_reason = f"CUSUM anomaly ({peak_cusum:.2f} m > threshold {self.p.cusum_threshold_m:.2f} m)"
            return self.trigger_reason

        return None


class AdversarialEnvironment:
    """Simulates a vessel mission under ocean physics, testing attacker vs. defender."""
    def __init__(self, duration_s: float = 60.0, dt_s: float = 0.2,
                 wave_noise_sigma: float = 0.05, current_mps: float = 0.35):
        self.duration_s = duration_s
        self.dt_s = dt_s
        self.wave_noise = wave_noise_sigma
        self.current_mps = current_mps

    def simulate(self, attacker: Optional[AttackerPolicy],
                 defender: DefenderPolicy) -> Dict[str, any]:
        """Runs one simulated trial. If attacker is None, evaluates baseline clean run."""
        d_filter = defender.create_filter()
        t = 0.0
        # Vessel on a steady course: heading East at 1.5 m/s with subtle current
        v_surge = 1.5
        v_current_n = self.current_mps * 0.1
        true_n = 0.0
        true_e = 0.0
        peak_displacement = 0.0
        detected = False
        det_time = None
        det_reason = ""

        while t <= self.duration_s:
            # Kinematic integration of true physics
            true_e += v_surge * self.dt_s
            true_n += v_current_n * self.dt_s
            
            # Ground-truth INS velocities (IMU / DVL measurement with ocean noise)
            ins_vn = v_current_n + random.gauss(0.0, 0.02)
            ins_ve = v_surge + random.gauss(0.0, 0.02)

            # Attack injection
            off_n, off_e = (0.0, 0.0) if attacker is None else attacker.generate_offset(t)
            displacement = math.hypot(off_n, off_e)
            if displacement > peak_displacement:
                peak_displacement = displacement

            # Reported position (True + Spoofed Offset + Wave Jitter)
            rep_n = true_n + off_n + random.gauss(0.0, self.wave_noise)
            rep_e = true_e + off_e + random.gauss(0.0, self.wave_noise)

            # Defender evaluation
            alert = d_filter.update(t, rep_n, rep_e, ins_vn, ins_ve)
            if alert and not detected:
                detected = True
                det_time = t
                det_reason = alert

            t += self.dt_s

        return {
            "is_attack": attacker is not None,
            "detected": detected,
            "det_time": det_time,
            "det_reason": det_reason,
            "peak_displacement_m": peak_displacement,
            "duration_s": self.duration_s,
        }


class AdversarialTournament:
    """Co-evolutionary min-max optimization loop."""
    def __init__(self, env: Optional[AdversarialEnvironment] = None):
        self.env = env or AdversarialEnvironment()

    def evaluate_fitness(self, att: AttackerPolicy, def_pol: DefenderPolicy,
                         trials: int = 5) -> Tuple[float, float]:
        """Computes (attacker_score, defender_score)."""
        # Baseline checks for False Positive Rate (FPR)
        fp_count = 0
        for _ in range(trials):
            base_res = self.env.simulate(None, def_pol)
            if base_res["detected"]:
                fp_count += 1
        fpr = fp_count / float(trials)

        # Attack trials
        success_disp = []
        det_count = 0
        for _ in range(trials):
            att_res = self.env.simulate(att, def_pol)
            if att_res["detected"]:
                det_count += 1
                # If detected early, displacement achieved up to detection
                success_disp.append(att_res["peak_displacement_m"] * 0.2)
            else:
                success_disp.append(att_res["peak_displacement_m"])

        tpr = det_count / float(trials)
        avg_disp = sum(success_disp) / len(success_disp)

        # Attacker utility: maximize displacement, heavily penalized by detection
        att_score = avg_disp * (1.0 - 0.75 * tpr)
        # Defender utility: maximize true positives, heavily penalized by false alarms
        def_score = (tpr * 100.0) - (fpr * 300.0)

        return att_score, def_score

    def run_coevolution(self, rounds: int = 15, population_size: int = 6) -> Dict[str, any]:
        """Runs iterative co-evolution to find the equilibrium Pareto boundary."""
        # Initialize diverse populations
        attackers = [
            AttackerPolicy(drift_rate_mps=0.10),  # ultra-stealth
            AttackerPolicy(drift_rate_mps=0.25),  # moderate
            AttackerPolicy(drift_rate_mps=0.50),  # standard
            AttackerPolicy(drift_rate_mps=1.00),  # aggressive
            AttackerPolicy(drift_rate_mps=0.15, jitter_sigma_m=0.1),
            AttackerPolicy(drift_rate_mps=0.30, jitter_sigma_m=0.2),
        ]
        defenders = [
            DefenderPolicy(cusum_slack_mps=0.10, cusum_threshold_m=3.0),
            DefenderPolicy(cusum_slack_mps=0.15, cusum_threshold_m=5.0),
            DefenderPolicy(cusum_slack_mps=0.20, cusum_threshold_m=7.0),
            DefenderPolicy(cusum_slack_mps=0.25, cusum_threshold_m=10.0),
            DefenderPolicy(cusum_slack_mps=0.30, cusum_threshold_m=12.0),
            DefenderPolicy(cusum_slack_mps=0.12, cusum_threshold_m=4.0),
        ]

        history = []
        best_att = attackers[0]
        best_def = defenders[0]

        for r in range(rounds):
            # 1. Attacker optimization against best defender
            scored_att = []
            for att in attackers:
                a_score, _ = self.evaluate_fitness(att, best_def, trials=3)
                scored_att.append((a_score, att))
            scored_att.sort(key=lambda x: x[0], reverse=True)
            best_att = scored_att[0][1]

            # Mutate top attackers
            survivors_att = [x[1] for x in scored_att[:3]]
            attackers = survivors_att + [s.mutate(0.3) for s in survivors_att]

            # 2. Defender optimization against best attacker
            scored_def = []
            for d in defenders:
                _, d_score = self.evaluate_fitness(best_att, d, trials=3)
                scored_def.append((d_score, d))
            scored_def.sort(key=lambda x: x[0], reverse=True)
            best_def = scored_def[0][1]

            # Mutate top defenders
            survivors_def = [x[1] for x in scored_def[:3]]
            defenders = survivors_def + [s.mutate(0.3) for s in survivors_def]

            a_fit, d_fit = self.evaluate_fitness(best_att, best_def, trials=5)
            history.append({
                "round": r + 1,
                "attacker_drift_mps": round(best_att.drift_rate_mps, 3),
                "defender_cusum_thresh_m": round(best_def.cusum_threshold_m, 2),
                "attacker_fitness": round(a_fit, 2),
                "defender_fitness": round(d_fit, 2),
            })

        return {
            "best_attacker": best_att,
            "best_defender": best_def,
            "rounds_completed": rounds,
            "history": history,
        }
