import unittest
from scaleup.physics.acoustic_channel import (
    AcousticChannel,
    thorp_absorption_db_per_km,
    calculate_transmission_loss_db
)


class TestAcousticChannel(unittest.TestCase):
    def test_thorp_absorption_reasonable(self):
        # At 25 kHz, absorption in seawater is approx 4-6 dB/km
        alpha = thorp_absorption_db_per_km(25.0)
        self.assertGreater(alpha, 3.5)
        self.assertLess(alpha, 7.0)

    def test_transmission_loss_monotonic(self):
        tl_100 = calculate_transmission_loss_db(100.0)
        tl_1000 = calculate_transmission_loss_db(1000.0)
        self.assertGreater(tl_1000, tl_100)

    def test_acoustic_channel_latency_and_queue(self):
        channel = AcousticChannel(sound_speed_mps=1500.0, transceiver_pos=(0.0, 0.0, 0.0))
        # Target at (1500m North, 0, 0) -> slant range 1500m -> delay 1.0s
        t_send = 10.0
        dispatch_t = channel.send_position(t_send, 1500.0, 0.0, 0.0, "packet_1")
        self.assertIsNotNone(dispatch_t)
        self.assertAlmostEqual(dispatch_t, 11.0, places=3)

        # At t=10.5s, packet should NOT be ready yet
        ready = channel.receive_ready(10.5)
        self.assertEqual(len(ready), 0)

        # At t=11.1s, packet should arrive
        ready = channel.receive_ready(11.1)
        self.assertEqual(len(ready), 1)
        payload, r, tau = ready[0]
        self.assertEqual(payload, "packet_1")
        self.assertAlmostEqual(r, 1500.0, places=1)
        self.assertAlmostEqual(tau, 1.0, places=3)

    def test_excessive_range_packet_dropped(self):
        channel = AcousticChannel(max_loss_margin_db=70.0)
        # At 10 km range, TL > 80 dB -> dropped
        dispatch_t = channel.send_position(0.0, 10000.0, 0.0, 0.0, "packet_lost")
        self.assertIsNone(dispatch_t)


if __name__ == "__main__":
    unittest.main()
