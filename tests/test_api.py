from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.services.osm import parse_osm_packet


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
        desktop = self.client.get("/desktop")
        self.assertEqual(desktop.status_code, 200)
        self.assertIn("churchboard-logo.png", desktop.text)
        self.assertEqual(self.client.get("/", follow_redirects=False).headers["location"], "/desktop")
        admin = self.client.get("/admin")
        self.assertEqual(admin.status_code, 200)
        self.assertIn("churchboard-icon.png", admin.text)
        self.assertIn('select name="timezone"', admin.text)
        self.assertNotIn('input name="timezone"', admin.text)
        for obs_field in ("obs_enabled", "obs_host", "obs_port", "obs_password", "obs_dropped_frames_threshold", "obs_preview_url"):
            self.assertIn(f'name="{obs_field}"', admin.text)
        self.assertIn('id="cancel-dashboard" type="button"', admin.text)
        admin_script = self.client.get("/static/admin.js").text
        self.assertIn('dialog.close("cancel")', admin_script)
        self.assertNotIn("pp_remote_control_enabled", admin_script)
        display = self.client.get("/display/main")
        self.assertEqual(display.status_code, 200)
        self.assertIn('class="menu-brand"', display.text)
        self.assertIn('aria-controls="display-menu"', display.text)
        self.assertIn('id="active-plan-status"', display.text)
        self.assertEqual(display.headers["cache-control"], "no-store")
        editor = self.client.get("/editor/main")
        self.assertEqual(editor.status_code, 200)
        self.assertIn("churchboard-icon.png", editor.text)
        self.assertIn('id="dashboard-background-color" type="color"', editor.text)
        self.assertIn('id="delete-dashboard"', editor.text)
        self.assertIn('input name="show_title" type="checkbox"', editor.text)
        self.assertIn('select name="slide_layout"', editor.text)
        self.assertNotIn('name="pp_remote_control_enabled"', admin.text)
        self.assertIn('ProPresenter playlist', self.client.get("/static/common.js").text)
        self.assertIn('input name="show_parts" type="checkbox"', editor.text)
        self.assertNotIn('id="dashboard-theme"', editor.text)
        self.assertNotIn('target="_blank"', editor.text)
        display_script = self.client.get("/static/display.js").text
        self.assertIn('class="board-menu-edit"', display_script)
        self.assertIn('/editor/${encodeURIComponent(item.slug)}', display_script)
        self.assertIn('planSelectionInFlight', display_script)
        self.assertIn('event.key==="Escape"', display_script)
        self.assertIn("fitDashboardToViewport", display_script)
        self.assertIn("--dashboard-scale", display_script)
        self.assertIn("resizeDashboardContent(document.querySelector(\"#dashboard\"))", display_script)
        common_script = self.client.get("/static/common.js").text
        self.assertIn('class="unassigned-board-icon"', common_script)
        self.assertIn('settings.slide_layout==="previews_only"', common_script)
        self.assertIn('settings.show_title===false', common_script)
        self.assertIn('full-service-order-list', common_script)
        self.assertIn('order_display_mode', self.client.get("/static/editor.js").text)
        self.assertIn('method:"DELETE"', self.client.get("/static/editor.js").text)
        self.assertIn('name="assignment_grouping"', self.client.get("/static/editor.js").text)
        self.assertIn('settings.card_grouping!=="position"', common_script)
        self.assertNotIn('talent-channel"><strong>', common_script)
        stylesheet = self.client.get("/static/style.css").text
        self.assertIn('mask:url("/static/churchboard-mark.svg")', stylesheet)
        mark = self.client.get("/static/churchboard-mark.svg")
        self.assertEqual(mark.status_code, 200)
        self.assertIn("<svg", mark.text)
        self.assertTrue(self.client.get("/api/app-info").json()["instance_id"])

    def test_desktop_control_lists_boards_and_requires_tray_to_quit(self):
        response = self.client.get("/api/dashboards")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["items"]), 1)
        stopped = self.client.post("/api/desktop/quit")
        self.assertEqual(stopped.status_code, 409)

    def test_timezone_catalog_contains_standard_choices(self):
        response = self.client.get("/api/timezones")
        self.assertEqual(response.status_code, 200)
        zones = response.json()["items"]
        self.assertIn("UTC", zones)
        self.assertIn("America/New_York", zones)
        self.assertEqual(zones, sorted(zones))

    def test_dashboard_round_trip(self):
        board = self.client.get("/api/dashboards/main").json()
        board["name"] = "Sanctuary"
        board["background_color"] = "#213a5c"
        board["widgets"][3]["settings"]["position_keys"] = ["band::vox 2", "band::vox 1"]
        board["widgets"][3]["settings"]["position_labels"] = {"band::vox 2": {"name": "Vox 2", "team_name": "Band"}}
        response = self.client.put("/api/dashboards/main", json=board)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/dashboards/main").json()["name"], "Sanctuary")
        self.assertEqual(self.client.get("/api/dashboards/main").json()["background_color"], "#213a5c")
        saved_settings = self.client.get("/api/dashboards/main").json()["widgets"][3]["settings"]
        self.assertEqual(saved_settings["position_keys"], ["band::vox 2", "band::vox 1"])
        self.assertEqual(saved_settings["position_labels"]["band::vox 2"]["name"], "Vox 2")

    def test_deleted_playlist_widget_stays_deleted(self):
        board = self.client.get("/api/dashboards/main").json()
        board["widgets"] = [widget for widget in board["widgets"] if widget["type"] != "playlist"]
        response = self.client.put("/api/dashboards/main", json=board)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(widget["type"] == "playlist" for widget in response.json()["widgets"]))
        reloaded = self.client.get("/api/dashboards/main").json()
        self.assertFalse(any(widget["type"] == "playlist" for widget in reloaded["widgets"]))

    def test_default_dashboards_include_a_configured_propresenter_playlist_widget(self):
        board = self.client.get("/api/dashboards/main").json()
        playlist = next(widget for widget in board["widgets"] if widget["type"] == "playlist")
        self.assertTrue(playlist["settings"]["allow_remote_trigger"])
        self.assertEqual(playlist["settings"]["slide_size"], 120)
        self.assertEqual(playlist["settings"]["item_size"], 48)
        self.assertEqual(playlist["settings"]["marker_size"], 10)
        self.assertEqual(playlist["settings"]["active_border_color"], "#f5c400")
        editor = self.client.get("/static/editor.js").text
        self.assertIn("playlist_slide_size", editor)
        self.assertIn("playlist_item_size", editor)
        self.assertIn("playlist_marker_size", editor)
        self.assertIn("playlist_active_border_color", editor)
        self.assertNotIn("playlist_keyboard_control", editor)
        self.assertNotIn("playlist_allow_remote_trigger", editor)
        display_script = self.client.get("/static/display.js").text
        self.assertIn("data-pp-keyboard-toggle", self.client.get("/static/common.js").text)
        self.assertIn("data-pp-controls-toggle", self.client.get("/static/common.js").text)
        self.assertIn('class="pp-switch-track"', self.client.get("/static/common.js").text)
        self.assertIn('role="switch"', self.client.get("/static/common.js").text)
        self.assertIn("/api/integrations/propresenter/navigate/", display_script)
        self.assertIn("keyboardStorageKey", display_script)
        self.assertFalse(playlist["settings"]["keyboard_control"])

    def test_runtime_and_manual_service_selection(self):
        runtime = self.client.get("/api/runtime").json()
        self.assertEqual(runtime["service"]["id"], "demo")
        self.assertTrue(all(person["photo"].startswith("/static/demo-people/") for person in runtime["people"]))
        for filename in ("jordan-lee.jpg", "morgan-reed.jpg", "taylor-brooks.jpg"):
            photo = self.client.get(f"/static/demo-people/{filename}")
            self.assertEqual(photo.status_code, 200)
            self.assertEqual(photo.headers["content-type"], "image/jpeg")
        response = self.client.put("/api/active-plan", json={"id": "demo", "service_type_id": "demo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["manual_plan"]["id"], "demo")

    def test_compact_runtime_omits_cached_planning_center_content(self):
        response = self.client.get("/api/runtime?compact=true")
        runtime = response.json()
        self.assertIn("propresenter", runtime)
        self.assertNotIn("playlist_presentations", runtime["propresenter"])
        self.assertNotIn("slides", runtime["propresenter"])
        self.assertIn("mics", runtime)
        self.assertIn("timing", runtime)
        self.assertNotIn("service_items", runtime["timing"])
        for cached_key in ("service", "people", "plans", "planning_center_media"):
            self.assertNotIn(cached_key, runtime)
        cached = self.client.get("/api/runtime?compact=true", headers={"If-None-Match": response.headers["etag"]})
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.content, b"")

    def test_propresenter_remote_trigger_requires_explicit_setting(self):
        response = self.client.post("/api/integrations/propresenter/active-slide", json={"index": 0})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/integrations/propresenter/navigate/next")
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/integrations/propresenter/navigate/next", json={"dashboard_slug": "main", "widget_id": "playlist"})
        self.assertEqual(response.status_code, 400)

    def test_propresenter_playlist_diagnostics_requires_connection(self):
        response = self.client.get("/api/integrations/propresenter/playlist-diagnostics")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/integrations/propresenter/active-playlist-item", json={"index": 0})
        self.assertEqual(response.status_code, 403)

    def test_osm_measurements_are_available_as_service_reports(self):
        accepted = self.client.post("/api/integrations/osm/measurement", json={"laeq": 78.4, "peak": 92.1, "timestamp": "2026-08-05T12:00:00+00:00"})
        self.assertEqual(accepted.status_code, 202)
        services = self.client.get("/api/reports/services").json()["items"]
        self.assertEqual(services[0]["id"], "demo")
        csv_report = self.client.get("/api/reports/services/demo/spl-averages.csv")
        self.assertEqual(csv_report.status_code, 200)
        self.assertIn("Worship", csv_report.text)
        graph = self.client.get("/api/reports/services/demo/spl-graph.html")
        self.assertEqual(graph.status_code, 200)
        self.assertIn("78.4", graph.text)

    def test_osm_remote_api_levels_packet_is_normalized(self):
        packet = b'{"api":"Open Sound Meter","host":"FOH-Mac","source":"source-123","objectName":"House SPL","message":"levels","data":{"A":{"Fast":-61.6,"Slow":-63.9},"C":{"Fast":-58.2,"Slow":-59.1},"Z":{"Fast":-55.8}}}'
        parsed = parse_osm_packet(packet)
        self.assertEqual(parsed["laeq"], 78.4)
        self.assertEqual(parsed["a_slow"], 76.1)
        self.assertEqual(parsed["z_fast"], 84.2)
        self.assertEqual(parsed["c_fast"], 81.8)
        self.assertEqual(parsed["c_slow"], 80.9)
        self.assertEqual(parsed["source_id"], "source-123")
        self.assertEqual(parsed["source_name"], "House SPL")
        self.assertEqual(parsed["source_host"], "FOH-Mac")

    def test_osm_remote_api_floor_is_zero_db_spl(self):
        packet = b'{"api":"Open Sound Meter","message":"levels","data":{"A":{"Fast":-140,"Slow":-160}}}'
        parsed = parse_osm_packet(packet)
        self.assertEqual(parsed["a_fast"], 0.0)
        self.assertEqual(parsed["a_slow"], 0.0)

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

    def test_restream_connect_requires_saved_client_credentials(self):
        response = self.client.get("/api/integrations/restream/connect", follow_redirects=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Client ID", response.json()["detail"])

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
