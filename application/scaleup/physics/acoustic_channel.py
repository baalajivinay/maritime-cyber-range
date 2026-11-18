"""
Underwater Acoustic USBL Channel Model.

Implements subsea acoustic propagation physics:
1. Propagation Delay: One-way / two-way travel time tau = distance / c,
   where c is local sound speed (default 1542.4 m/s or CTD site profile).
2. Thorp Transmission Loss: Spherical spreading (20 log10 R) + frequency-dependent
   absorption alpha(f) * R * 10^-3.
3. Slant Range Dependent Packet Dropout & Queueing: Packets arriving at the AUV
   transponder are buffered in a FIFO queue and dispatched with realistic latency tau.
"""

import math
import time
from collections import deque
from typing import Optional, Tuple, Any, List


def thorp_absorption_db_per_km(freq_khz: float = 25.0) -> float:
    """Thorp formula for acoustic absorption coefficient in seawater [dB/km]."""
    f2 = freq_khz ** 2
    return (0.11 * f2 / (1.0 + f2)) + (44.0 * f2 / (4100.0 + f2)) + (2.75e-4 * f2) + 0.003


def calculate_transmission_loss_db(range_m: float, freq_khz: float = 25.0) -> float:
    """Computes acoustic transmission loss TL = 20*log10(R) + alpha*R*10^-3."""
    r = max(1.0, range_m)
    alpha = thorp_absorption_db_per_km(freq_khz)
    spreading = 20.0 * math.log10(r)
    absorption = alpha * (r / 1000.0)
    return spreading + absorption


class AcousticChannel:
    """Models the physical acoustic channel between a surface USBL transceiver and subsea AUV."""
    def __init__(
        self,
        sound_speed_mps: float = 1542.4,
        carrier_freq_khz: float = 25.0,
        max_loss_margin_db: float = 85.0,
        transceiver_pos: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ):
        self.c = sound_speed_mps
        self.freq_khz = carrier_freq_khz
        self.max_tl = max_loss_margin_db
        self.transceiver_pos = transceiver_pos
        self.queue: deque = deque()  # (dispatch_time, payload, slant_range_m, latency_s)

    def slant_range_m(self, n: float, e: float, d: float) -> float:
        """Slant range from surface USBL transceiver to vessel position."""
        tx_n, tx_e, tx_d = self.transceiver_pos
        return math.sqrt((n - tx_n)**2 + (e - tx_e)**2 + (d - tx_d)**2)

    def propagation_delay_s(self, slant_range_m: float) -> float:
        """One-way acoustic propagation delay tau = R / c."""
        return slant_range_m / self.c

    def is_packet_received(self, slant_range_m: float) -> bool:
        """Evaluates whether acoustic SNR exceeds detection threshold under Thorp TL."""
        tl = calculate_transmission_loss_db(slant_range_m, self.freq_khz)
        return tl <= self.max_tl

    def send_position(self, t_send: float, n: float, e: float, d: float, payload: Any) -> Optional[float]:
        """Transmits an acoustic position packet.

        Returns expected dispatch timestamp if packet traverses channel, None if dropped.
        """
        r = self.slant_range_m(n, e, d)
        if not self.is_packet_received(r):
            # Dropped due to excessive acoustic attenuation / out-of-range
            return None

        tau = self.propagation_delay_s(r)
        t_dispatch = t_send + tau
        self.queue.append((t_dispatch, payload, r, tau))
        return t_dispatch

    def receive_ready(self, t_current: float) -> List[Tuple[Any, float, float]]:
        """Pops and returns all packets that have completed acoustic propagation:

        [(payload, slant_range_m, latency_s), ...]
        """
        ready = []
        while self.queue and self.queue[0][0] <= t_current:
            _, payload, r, tau = self.queue.popleft()
            ready.append((payload, r, tau))
        return ready
