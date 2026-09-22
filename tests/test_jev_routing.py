import json
import tempfile
import unittest
from pathlib import Path

from backend.jev_routing import JevDecisionRouter, load_jev_config


class JevRoutingConfigTests(unittest.TestCase):
    def test_checked_in_config_has_both_decision_models(self):
        config = load_jev_config()
        self.assertTrue(config.router.enabled)
        self.assertEqual(config.router.strategy, "consensus")
        self.assertEqual(config.router.minimum_calibrated_confidence, 0.7)
        self.assertEqual(config.profiles["laya"].kind, "jev_laya")
        self.assertEqual(config.profiles["semantic"].kind, "jev_semantic")

    def test_invalid_profile_reference_is_rejected_before_network_access(self):
        invalid = {"version": 1, "router": {"enabled": True, "profiles": ["missing"]}, "profiles": {}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jev.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown profile"):
                load_jev_config(path)

    def test_router_is_constructed_from_configuration(self):
        self.assertTrue(JevDecisionRouter(load_jev_config()).enabled)
