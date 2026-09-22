import json
import unittest
from pathlib import Path


class ModelServicesConfigTests(unittest.TestCase):
    def test_both_model_gateways_have_project_managed_startup_configuration(self):
        path = Path(__file__).parents[1] / "config" / "model_services.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        services = {service["id"]: service for service in config["services"]}

        self.assertEqual(config["version"], 1)
        self.assertEqual(services["litellm_gateway"]["mode"], "online_api")
        self.assertIn("config/litellm.yaml", services["litellm_gateway"]["arguments"])
        self.assertEqual(services["jev_decision_gateway"]["mode"], "local")
        self.assertEqual(services["jev_decision_gateway"]["health_url"], "http://127.0.0.1:4079/health")
