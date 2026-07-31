from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        os.environ["CHURCHBOARD_DATA_FILE"] = os.path.join(self.directory.name, "churchboard.json")
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.directory.cleanup()
        os.environ.pop("CHURCHBOARD_DATA_FILE", None)

    def test_setup_display_and_editor_pages_load(self):
        self.assertEqual(self.client.get("/admin").status_code, 200)
        display = self.client.get("/display/main")
        self.assertEqual(display.status_code, 200)
        self.assertEqual(display.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/editor/main").status_code, 200)
        self.assertTrue(self.client.get("/api/app-info").json()["instance_id"])

    def test_dashboard_round_trip(self):
        board = self.client.get("/api/dashboards/main").json()
        board["name"] = "Sanctuary"
        board["widgets"][3]["settings"]["position_keys"] = ["band::vox 2", "band::vox 1"]
        board["widgets"][3]["settings"]["position_labels"] = {"band::vox 2": {"name": "Vox 2", "team_name": "Band"}}
        response = self.client.put("/api/dashboards/main", json=board)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/dashboards/main").json()["name"], "Sanctuary")
        saved_settings = self.client.get("/api/dashboards/main").json()["widgets"][3]["settings"]
        self.assertEqual(saved_settings["position_keys"], ["band::vox 2", "band::vox 1"])
        self.assertEqual(saved_settings["position_labels"]["band::vox 2"]["name"], "Vox 2")

    def test_runtime_and_manual_service_selection(self):
        runtime = self.client.get("/api/runtime").json()
        self.assertEqual(runtime["service"]["id"], "demo")
        response = self.client.put("/api/active-plan", json={"id": "demo", "service_type_id": "demo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["manual_plan"]["id"], "demo")

    def test_service_control_endpoint_takes_and_advances_service(self):
        taken = self.client.post("/api/service-control/take")
        self.assertEqual(taken.status_code, 200)
        self.assertTrue(taken.json()["service_control"]["active"])
        advanced = self.client.post("/api/service-control/next")
        self.assertEqual(advanced.status_code, 200)
        self.assertTrue(advanced.json()["service_control"]["active"])
        released = self.client.post("/api/service-control/release")
        self.assertEqual(released.status_code, 200)
        self.assertFalse(released.json()["service_control"]["active"])

    def test_planning_center_test_requires_saved_credentials(self):
        response = self.client.post("/api/integrations/planning-center/test")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Application ID", response.json()["detail"])

    def test_demo_catalog_exposes_grouped_positions(self):
        response = self.client.get("/api/integrations/planning-center/catalog")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["demo"])
        self.assertEqual(response.json()["items"][0]["name"], "Band")

    def test_named_mic_configuration_can_be_added_mapped_and_deleted(self):
        settings = self.client.get("/api/settings").json()
        settings["shure"].update({"enabled": True, "mics": [{
            "id": "blue", "name": "Blue", "host": "192.168.1.60", "port": 2202, "channel": 1,
        }]})
        settings["position_mic_map"] = {"band::vox 1": "blue"}
        saved = self.client.put("/api/settings", json=settings)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["shure"]["mics"][0]["name"], "Blue")
        self.assertEqual(saved.json()["position_mic_map"]["band::vox 1"], "blue")

        settings = saved.json()
        settings["shure"]["mics"] = []
        settings["position_mic_map"] = {}
        deleted = self.client.put("/api/settings", json=settings)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["shure"]["mics"], [])

    def test_service_type_names_are_persisted_with_ids(self):
        settings = self.client.get("/api/settings").json()
        settings["planning_center"].update({"service_type_ids": ["123"], "service_types": [{"id": "123", "name": "Sunday Worship"}]})
        response = self.client.put("/api/settings", json=settings)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["planning_center"]["service_types"], [{"id": "123", "name": "Sunday Worship"}])


if __name__ == "__main__":
    unittest.main()
