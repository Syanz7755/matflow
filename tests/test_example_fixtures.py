"""Regression checks for deterministic, synthetic teaching fixtures."""

import csv
import statistics
import unittest
from pathlib import Path


DATA = Path(__file__).parents[1] / "examples" / "data"


class ExampleFixtureTests(unittest.TestCase):
    def test_eis_fixture_has_positive_frequencies_and_finite_impedance(self):
        with (DATA / "01_eis_basic_qc" / "eis_spectrum.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 13)
        self.assertTrue(all(float(row["frequency_hz"]) > 0 for row in rows))
        self.assertAlmostEqual(float(rows[0]["z_real_ohm"]), 5.0, delta=0.2)

    def test_pycnometer_fixture_has_known_specific_gravity(self):
        with (DATA / "04_pycnometer_specific_gravity" / "pycnometer_measurements.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        specific_gravities = []
        for row in rows:
            empty = float(row["empty_pycnometer_g"])
            water = float(row["pycnometer_plus_water_g"])
            sample = float(row["pycnometer_plus_sample_g"])
            sample_water = float(row["pycnometer_plus_sample_plus_water_g"])
            specific_gravities.append((sample - empty) / ((water - empty) - (sample_water - sample)))
        self.assertAlmostEqual(statistics.mean(specific_gravities), 2.600, delta=0.002)

    def test_tga_fixture_has_known_caco3_mass_fraction(self):
        with (DATA / "05_tga_caco3_content" / "tga_mass_loss.csv").open(encoding="utf-8") as handle:
            mass_percent = {int(row["temperature_c"]): float(row["mass_percent"]) for row in csv.DictReader(handle)}
        co2_loss = mass_percent[600] - mass_percent[850]
        caco3_mass_fraction = co2_loss * 100.09 / 44.01
        self.assertAlmostEqual(caco3_mass_fraction, 20.0, delta=0.5)
