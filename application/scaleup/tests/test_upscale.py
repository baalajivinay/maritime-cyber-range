"""Offline tests for the upscale modules (Axis 1 generic + Axis 2 physics).
Pure, no sim/hardware -- run: python3 scaleup/tests/test_upscale.py
"""
import math
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from scaleup.backends import registry as backends
from scaleup.protocols import nmea0183 as nmea
from scaleup.protocols.nmea0183 import NMEASpoofer, NMEA0183Adapter
from scaleup.physics import sensors, seastate, tides
from scaleup.physics.acoustics_bellhop import AcousticChannel, transmission_loss_multipath
from scaleup.physics.bathymetry import BathymetrySource
from scaleup.physics.ingest import OceanProfile
from scaleup.physics.ais_feed import AISFeed
from scaleup.compliance import frameworks
from scaleup.twins import registry as twins


class TestBackends(unittest.TestCase):
    def test_both_firmwares_registered(self):
        self.assertSetEqual(set(backends.names()), {"ardupilot", "px4"})

    def test_gps_na_submerged_both_firmwares(self):
        for b in backends.all_backends():
            self.assertFalse(b.applies("gps_spoof", "underwater"))
            self.assertTrue(b.applies("c2_replay", "underwater"))
            self.assertTrue(b.applies("acoustic_spoof", "underwater"))
            self.assertFalse(b.applies("acoustic_spoof", "surface"))

    def test_px4_uses_standard_gps_message(self):
        px4 = backends.get("px4")
        self.assertIn("GPS_INPUT", px4.injection("gps_spoof").message)


class TestNMEA(unittest.TestCase):
    def test_checksum_and_roundtrip(self):
        s = nmea.encode_gga(9.9, 76.2)
        p = nmea.parse(s)
        self.assertTrue(p["valid"])
        self.assertAlmostEqual(p["lat"], 9.9, places=4)
        self.assertAlmostEqual(p["lon"], 76.2, places=4)

    def test_southern_western_hemisphere(self):
        p = nmea.parse(nmea.encode_rmc(-33.85, -70.6, 5.0, 90.0))
        self.assertAlmostEqual(p["lat"], -33.85, places=4)
        self.assertAlmostEqual(p["lon"], -70.6, places=4)

    def test_spoofer_walks_offset_east(self):
        sp = NMEASpoofer(9.9, 76.2, bearing_deg=90.0)
        sp.step(100.0)
        lat, lon = sp.current()
        # 100 m east ~ 0 north, +east; lat unchanged, lon increased
        self.assertAlmostEqual(lat, 9.9, places=4)
        self.assertGreater(lon, 76.2)
        d_east_m = (lon - 76.2) * 111320.0 * math.cos(math.radians(9.9))
        self.assertAlmostEqual(d_east_m, 100.0, delta=1.0)

    def test_adapter_decodes_to_believed_pos(self):
        evs = NMEA0183Adapter().decode(nmea.encode_gga(1.0, 2.0))
        self.assertEqual(evs[0]["type"], "believed_pos")


class TestSensors(unittest.TestCase):
    def test_gnss_error_bounded_and_reproducible(self):
        m1 = sensors.GnssErrorModel(seed=42)
        m2 = sensors.GnssErrorModel(seed=42)
        for _ in range(50):
            e1 = m1.error_m(1.0)
            e2 = m2.error_m(1.0)
            self.assertEqual(e1, e2)                 # same seed -> same stream
            self.assertLess(math.hypot(*e1), 30.0)   # bounded, no runaway

    def test_dvl_dropout_increases_with_altitude(self):
        dvl = sensors.DvlErrorModel(max_altitude_m=50.0, seed=1)
        lock_shallow = sum(dvl.locked(5.0) for _ in range(500))
        lock_deep = sum(dvl.locked(48.0) for _ in range(500))
        self.assertGreater(lock_shallow, lock_deep)


class TestSeaState(unittest.TestCase):
    def test_jonswap_recovers_hs(self):
        freqs, S, df = seastate.spectrum(hs=2.0, tp=8.0, n=400)
        self.assertAlmostEqual(seastate.significant_wave_height(freqs, S, df), 2.0, delta=0.15)

    def test_wavefield_elevation_scale(self):
        wf = seastate.WaveField(hs=2.0, tp=8.0, seed=3)
        peak = max(abs(wf.elevation(t * 0.2)) for t in range(400))
        self.assertGreater(peak, 0.5)
        self.assertLess(peak, 4.0)


class TestTides(unittest.TestCase):
    def test_m2_period_about_12p42h(self):
        w = tides._omega("M2")          # rad/s
        period_h = (2 * math.pi / w) / 3600.0
        self.assertAlmostEqual(period_h, 12.42, delta=0.02)

    def test_current_flips_with_flood_ebb(self):
        tm = tides.demo_mumbai()
        bearings = {tm.current(t)[1] for t in range(0, 12 * 3600, 600)}
        self.assertGreaterEqual(len(bearings), 2)   # reverses over a tidal cycle


class TestAcoustics(unittest.TestCase):
    def test_multipath_differs_from_freespace(self):
        tl = transmission_loss_multipath(1000.0, 5.0, 10.0, 45.0, 25.0)
        free = 20 * math.log10(1000.0)
        self.assertNotAlmostEqual(tl, free, places=1)   # interference present
        self.assertTrue(10 < tl < 200)

    def test_channel_reports_engine_and_range(self):
        ch = AcousticChannel(water_depth_m=45.0, freq_khz=25.0)
        self.assertIn(ch.engine, ("bellhop", "images-multipath"))
        r = ch.detection_range_m(source_level_db=190.0, det_threshold_db=60.0, max_r=3000.0)
        self.assertGreater(r, 0.0)


class TestBathymetry(unittest.TestCase):
    def test_csv_ingest_and_grounding(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("# lon lat depth\n76.20 9.90 40\n76.21 9.90 3\n")
            path = f.name
        b = BathymetrySource.from_csv(path)
        os.unlink(path)
        self.assertAlmostEqual(b.depth_at(9.90, 76.20), 40.0, delta=0.1)
        self.assertTrue(b.grounding_risk(9.90, 76.21, draft_m=5.0))   # 3 m water, 5 m draft
        self.assertFalse(b.grounding_risk(9.90, 76.20, draft_m=5.0))


class TestIngest(unittest.TestCase):
    def test_representative_profile_sound_speed_sane(self):
        p = OceanProfile.representative(28.0, 35.0, max_depth_m=45.0)
        c = p.sound_speed(10.0)
        self.assertTrue(1500 < c < 1560)    # seawater sound speed band
        self.assertEqual(p.tier, "A")


class TestAIS(unittest.TestCase):
    def test_decode_sample_aivdm(self):
        # canonical AIS type-1 example sentence
        contacts = AISFeed.decode_lines(["!AIVDM,1,1,,A,15M67FC000G?ufbE`FepT@3n00Sa,0*5C"])
        self.assertTrue(contacts)
        self.assertIn("mmsi", contacts[0])
        self.assertIsInstance(contacts[0]["lat"], float)


class TestCompliance(unittest.TestCase):
    def test_multi_framework_mapping(self):
        ctrls = frameworks.controls_for("c2_replay")
        fws = {c[0] for c in ctrls}
        self.assertIn("IEC 62443-3-3", fws)
        self.assertIn("MITRE ATT&CK ICS", fws)
        self.assertIn("IACS UR E26", fws)

    def test_map_verdicts_only_vulnerable(self):
        out = frameworks.map_verdicts({"c2_replay": "VULNERABLE", "gps_spoof": "N/A"})
        self.assertIn("c2_replay", out)
        self.assertNotIn("gps_spoof", out)


class TestTwinRegistry(unittest.TestCase):
    def test_discovers_the_indian_twins(self):
        ids = {t["id"] for t in twins.discover()}
        for expected in ("maya_auv", "auv150", "interceptor_usv", "survey_usv"):
            self.assertIn(expected, ids)

    def test_conformance_passes_for_shipped_twins(self):
        for rec in twins.discover():
            ok, issues = twins.conformance(rec)
            self.assertTrue(ok, f"{rec['id']} non-conformant: {issues}")


class TestEnvironment(unittest.TestCase):
    """The site->physics dataset binding: sea state, acoustics, density and
    currents all come from the SAME site numbers."""
    def test_binding_consumes_site_dataset_per_site(self):
        from scaleup.physics.environment import Environment
        densities, sound = {}, {}
        for sid in ("kochi", "mumbai", "visakhapatnam"):
            env = Environment.from_site(sid)
            s = env.summary()
            self.assertEqual(s["site"], sid)
            self.assertTrue(1000 < s["water_density_kg_m3"] < 1040)
            self.assertTrue(1450 < s["surface_sound_speed_mps"] < 1560)
            self.assertIsNotNone(s["usbl_detection_range_m"])
            densities[sid] = s["water_density_kg_m3"]
            sound[sid] = s["surface_sound_speed_mps"]
        # sites must differ -- proof the binding reads per-site data, not a default
        self.assertGreater(len(set(densities.values())), 1)
        self.assertGreater(len(set(sound.values())), 1)

    def test_wave_field_recovers_site_hs(self):
        from scaleup.physics.environment import Environment
        from scaleup.physics.seastate import spectrum, significant_wave_height
        env = Environment.from_site("kochi")
        hs = env.site.sea_state["sig_wave_height_m"]
        freqs, S, df = spectrum(hs, env.site.sea_state["period_s"])
        self.assertAlmostEqual(significant_wave_height(freqs, S, df), hs, delta=0.15)

    def test_harbour_site_has_heavier_gnss_multipath(self):
        from scaleup.physics.environment import Environment
        self.assertGreater(Environment.from_site("mumbai").summary()["gnss_multipath_m"],
                           Environment.from_site("visakhapatnam").summary()["gnss_multipath_m"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
