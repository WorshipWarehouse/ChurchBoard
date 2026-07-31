from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.models import Dashboard
from app.services.planning_center import PlanningCenterClient, calculate_timing, item_leader, position_key, selected_service_time, service_items
from app.services.shure import ShureClient, battery_percent, percent, transmitter_active
from app.services.propresenter import ProPresenterClient
from app.services.runtime import RuntimeService
from app.store import ConfigStore


class StoreTests(unittest.TestCase):
    def test_new_store_contains_destination_dashboards(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "state.json")
            self.assertEqual([item["slug"] for item in store.load()["dashboards"]], ["main", "green-room", "audio"])
            self.assertEqual(store.load()["dashboards"][0]["widgets"][3]["type"], "assignments")
            self.assertEqual(store.load()["dashboards"][2]["widgets"][3]["settings"]["display_mode"], "technical")
            self.assertFalse(store.load()["dashboards"][0]["widgets"][3]["settings"]["use_planning_center_icon"])
            self.assertEqual(store.load()["dashboards"][0]["widgets"][3]["settings"]["unassigned_media_title"], "Icon")
            self.assertEqual(store.load()["settings"]["planning_center"]["service_types"], [])

    def test_old_mic_widget_migrates_to_combined_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "state.json")
            data = store.load()
            data["dashboards"][0]["widgets"][3].update({"type": "mics", "title": "Microphones"})
            store.save(data)
            widget = store.load()["dashboards"][0]["widgets"][3]
            self.assertEqual(widget["type"], "assignments")
            self.assertEqual(widget["title"], "Scheduled Positions & Mics")

    def test_public_settings_never_returns_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "state.json")
            data = store.load()
            data["settings"]["planning_center"]["secret"] = "do-not-return"
            store.save(data)
            public = store.public_settings()["planning_center"]
            self.assertEqual(public["secret"], "")
            self.assertTrue(public["secret_configured"])


class DashboardTests(unittest.TestCase):
    def test_slug_is_normalized_and_validated(self):
        board = Dashboard(id="audio", name="Audio", slug="audio-board", widgets=[])
        self.assertEqual(board.slug, "audio-board")


class PlanningCenterTests(unittest.TestCase):
    def test_manual_plan_wins(self):
        client = PlanningCenterClient({"open_days_before": 0, "open_hours_before": 0, "close_hours_after": 0})
        plans = [{"id": "1", "service_type_id": "a", "starts_at": "2030-01-01T00:00:00+00:00"}, {"id": "2", "service_type_id": "b", "starts_at": "2030-01-02T00:00:00+00:00"}]
        self.assertEqual(client.select_plan(plans, {"id": "2", "service_type_id": "b"})["id"], "2")

    def test_service_time_tracks_active_or_next_service(self):
        plan = {"times": [
            {"id": "early", "starts_at": "2030-01-06T13:30:00+00:00", "ends_at": "2030-01-06T14:30:00+00:00"},
            {"id": "late", "starts_at": "2030-01-06T16:00:00+00:00", "ends_at": "2030-01-06T17:00:00+00:00"},
        ]}
        self.assertEqual(selected_service_time(plan, datetime(2030, 1, 6, 12, 0, tzinfo=timezone.utc))["id"], "early")
        self.assertEqual(selected_service_time(plan, datetime(2030, 1, 6, 14, 45, tzinfo=timezone.utc))["id"], "late")
        self.assertEqual(selected_service_time(plan, datetime(2030, 1, 6, 16, 15, tzinfo=timezone.utc))["id"], "late")

    def test_timing_uses_service_specific_exclusions_and_start(self):
        plan = {
            "starts_at": "2030-01-06T13:30:00+00:00",
            "times": [
                {"id": "early", "starts_at": "2030-01-06T13:30:00+00:00", "ends_at": "2030-01-06T14:30:00+00:00"},
                {"id": "late", "starts_at": "2030-01-06T16:00:00+00:00", "ends_at": "2030-01-06T17:00:00+00:00"},
            ],
            "items": [
                {"id": "one", "title": "First service only", "length": 60, "service_times": [{"plan_time_id": "late", "exclude": True}]},
                {"id": "two", "title": "Welcome", "length": 120, "service_times": [{"plan_time_id": "late", "exclude": False}]},
            ],
        }
        timing = calculate_timing(plan, datetime(2030, 1, 6, 16, 1, tzinfo=timezone.utc))
        self.assertEqual(timing["service_time_id"], "late")
        self.assertEqual([item["id"] for item in timing["service_items"]], ["two"])
        self.assertEqual(timing["current_item"]["id"], "two")
        self.assertEqual(timing["current_item"]["starts_after"], 0)

    def test_timing_finds_current_item(self):
        now = datetime.now(timezone.utc)
        plan = {"starts_at": (now - timedelta(seconds=90)).isoformat(), "planned_length": 180, "items": [{"id": "one", "title": "One", "starts_after": 0, "length": 60}, {"id": "two", "title": "Two", "starts_after": 60, "length": 120}]}
        timing = calculate_timing(plan, now)
        self.assertEqual(timing["current_item"]["id"], "two")
        self.assertEqual(timing["item_elapsed"], 30)

    def test_position_key_is_scoped_to_team(self):
        self.assertEqual(position_key("42", "  Vox 1 "), "42::vox 1")

    def test_item_leader_reads_direct_field_or_leader_note(self):
        self.assertEqual(item_leader({"song_leader": "Jordan Lee"}, []), "Jordan Lee")
        self.assertEqual(item_leader({}, [{"category_name": "Song Leader", "content": "Morgan Reed"}]), "Morgan Reed")
        self.assertEqual(item_leader({}, [{"category_name": "Item Leader", "content": "<p>Casey Rivers</p>"}]), "Casey Rivers")


class PlanningCenterCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_groups_positions_by_team(self):
        client = PlanningCenterClient({"enabled": True, "application_id": "id", "secret": "secret", "service_type_ids": ["st-1"]})

        async def fake_get(path, params=None):
            if path == "/service_types":
                return {"data": [{"id": "st-1", "attributes": {"name": "Sunday"}}]}
            return {
                "data": [{"type": "TeamPosition", "id": "position-1", "attributes": {"name": "Vox 1"}, "relationships": {"team": {"data": {"type": "Team", "id": "team-1"}}}}],
                "included": [{"type": "Team", "id": "team-1", "attributes": {"name": "Band"}}],
            }

        client._get = fake_get
        catalog = await client.position_catalog()
        self.assertEqual(catalog[0]["name"], "Band")
        self.assertEqual(catalog[0]["positions"][0]["key"], "team-1::vox 1")

    async def test_plan_detail_uses_item_assignments_for_song_leaders(self):
        client = PlanningCenterClient({"enabled": True, "application_id": "id", "secret": "secret"})

        async def fake_get(path, params=None):
            if path.endswith("/team_members"):
                return {
                    "data": [{
                        "type": "PlanPerson",
                        "id": "plan-person-1",
                        "attributes": {"name": "Jordan Lee", "team_position_name": "Vox 1", "status": "C"},
                        "relationships": {
                            "person": {"data": {"type": "Person", "id": "person-1"}},
                            "team": {"data": {"type": "Team", "id": "team-1"}},
                        },
                    }],
                    "included": [
                        {"type": "Person", "id": "person-1", "attributes": {"photo_url": "https://example.test/jordan.jpg"}},
                        {"type": "Team", "id": "team-1", "attributes": {"name": "Band"}},
                    ],
                }
            self.assertTrue(path.endswith("/items"))
            self.assertIn("item_assignments", params["include"])
            return {
                "data": [{
                    "type": "Item",
                    "id": "item-1",
                    "attributes": {"title": "Song One", "item_type": "song", "length": 240, "sequence": 1},
                    "relationships": {
                        "item_assignments": {"data": [{"type": "ItemAssignment", "id": "assignment-1"}]},
                        "item_notes": {"data": []},
                        "item_times": {"data": []},
                    },
                }],
                "included": [{
                    "type": "ItemAssignment",
                    "id": "assignment-1",
                    "relationships": {"assignable": {"data": {"type": "Person", "id": "person-1"}}},
                }],
            }

        client._get = fake_get
        detail = await client.plan_detail({"id": "plan-1", "service_type_id": "type-1"})
        self.assertEqual(detail["people"][0]["person_id"], "person-1")
        self.assertEqual(detail["items"][0]["leader"], "Jordan Lee")
        self.assertEqual(detail["items"][0]["leader_person_ids"], ["person-1"])

    async def test_media_by_title_returns_the_planning_center_image(self):
        client = PlanningCenterClient({"enabled": True, "application_id": "id", "secret": "secret"})

        async def fake_get(path, params=None):
            self.assertEqual(path, "/media")
            self.assertEqual(params["where[title]"], "Icon")
            self.assertEqual(params["include"], "attachments")
            return {
                "data": [{
                    "type": "Media",
                    "id": "media-1",
                    "attributes": {
                        "title": "Icon",
                        "media_type": "video",
                        "image_url": "https://example.test/icon.png",
                        "updated_at": "2030-01-01T12:00:00Z",
                    },
                    "relationships": {"attachments": {"data": [{"type": "Attachment", "id": "attachment-1"}]}},
                }],
                "included": [{
                    "type": "Attachment",
                    "id": "attachment-1",
                    "attributes": {"content_type": "image/png", "filename": "Icon-white.png"},
                }],
            }

        client._get = fake_get
        media = await client.media_by_title("Icon")
        self.assertEqual(media["id"], "media-1")
        self.assertEqual(media["image_url"], "https://example.test/icon.png")

    async def test_live_status_reads_controller_and_current_item_time(self):
        client = PlanningCenterClient({"enabled": True, "application_id": "id", "secret": "secret"})

        async def fake_get(path, params=None):
            self.assertIn("/live", path)
            return {
                "data": [{"type": "Live", "id": "live-1", "attributes": {"can_control": True, "can_take_control": False}, "relationships": {"current_item_time": {"data": {"type": "ItemTime", "id": "time-1"}}}}],
                "included": [{"type": "ItemTime", "id": "time-1", "attributes": {"live_start_at": "2030-01-01T12:00:00Z", "live_end_at": None}, "relationships": {"item": {"data": {"type": "Item", "id": "item-2"}}}}],
            }

        client._get = fake_get
        live = await client.live_status({"id": "plan-1", "service_type_id": "type-1", "series_id": "series-1"})
        self.assertTrue(live["can_control"])
        self.assertEqual(live["current_item_id"], "item-2")
        self.assertEqual(live["current_live_start_at"], "2030-01-01T12:00:00Z")


class ShureTests(unittest.TestCase):
    def test_shure_levels_are_clamped(self):
        self.assertEqual(percent("5", 5), 100)
        self.assertEqual(percent("-1", 5), 0)
        self.assertEqual(percent("bad", 5), 0)

    def test_unknown_battery_sentinel_does_not_look_full(self):
        self.assertEqual(battery_percent("5"), 100)
        self.assertIsNone(battery_percent("255"))
        self.assertIsNone(battery_percent("UNKN"))

    def test_unknown_transmitter_is_off_even_with_idle_rf(self):
        state = {"receiver_online": True, "tx_type": "UNKN", "battery_percent": 0, "rf": 37, "_battery_valid": False}
        self.assertFalse(transmitter_active(state))
        state.update({"tx_type": "QLXD2", "battery_percent": 80, "_battery_valid": True})
        self.assertTrue(transmitter_active(state))

    def test_configured_mics_on_same_ip_share_receiver(self):
        client = ShureClient({"enabled": True, "mics": [
            {"id": "blue", "name": "Blue", "host": "192.168.1.60", "channel": 1},
            {"id": "red", "name": "Red", "host": "192.168.1.60", "channel": 2},
        ]})
        receivers = client._configured_receivers()
        self.assertEqual(len(receivers), 1)
        self.assertEqual([mic["id"] for mic in receivers[0]["channel_configs"]], ["blue", "red"])


class ShureStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_tx_and_battery_sentinel_report_transmitter_off(self):
        class Reader:
            def __init__(self):
                self.done = False

            async def read(self, _size):
                if self.done:
                    return b""
                self.done = True
                return b"< REP 1 CHAN_NAME {VOX_1} >< REP 1 BATT_BARS {255} >< REP 1 TX_TYPE {UNKN} >< SAMPLE 1 ALL {0 42 0} >"

        class Writer:
            def write(self, _data):
                pass

            async def drain(self):
                pass

            def close(self):
                pass

            async def wait_closed(self):
                pass

        client = ShureClient({"enabled": True})
        receiver = {"id": "rack-a", "name": "Rack A", "host": "192.0.2.1", "port": 2202, "channels": 1}
        with patch("app.services.shure.asyncio.open_connection", AsyncMock(return_value=(Reader(), Writer()))):
            mic = (await client._receiver(receiver))[0]
        self.assertFalse(mic["online"])
        self.assertTrue(mic["receiver_online"])
        self.assertEqual(mic["battery_percent"], 0)
        self.assertEqual(mic["errors"], ["Transmitter off"])


class RuntimeAssignmentTests(unittest.TestCase):
    def test_position_key_maps_a_scheduled_person_to_named_mic(self):
        state = {
            "people": [{"name": "Jordan Lee", "position": "Vox 1", "position_key": "band::vox 1", "team_name": "Band"}],
            "mics": [{"id": "blue", "name": "Blue"}],
        }
        RuntimeService._apply_assignments(state, {"band::vox 1": "blue"})
        self.assertEqual(state["mics"][0]["assignment"]["name"], "Jordan Lee")

    def test_unfilled_mapped_position_keeps_its_filter_key(self):
        state = {"people": [], "mics": [{"id": "blue", "name": "Blue"}]}
        RuntimeService._apply_assignments(state, {"band::vox 1": "blue"})
        assignment = state["mics"][0]["assignment"]
        self.assertEqual(assignment["name"], "Unassigned")
        self.assertEqual(assignment["position_key"], "band::vox 1")
        self.assertEqual(assignment["team_id"], "band")

    def test_service_control_can_take_advance_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeService(ConfigStore(Path(directory) / "state.json"))
            runtime.state = runtime.demo_state()
            taken = asyncio.run(runtime.service_control("take"))
            first_index = taken["service_control"]["index"]
            advanced = asyncio.run(runtime.service_control("next"))
            self.assertTrue(advanced["service_control"]["active"])
            self.assertGreaterEqual(advanced["service_control"]["index"], first_index)
            released = asyncio.run(runtime.service_control("release"))
            self.assertFalse(released["service_control"]["active"])

    def test_cached_services_live_timing_does_not_fall_back_between_polls(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeService(ConfigStore(Path(directory) / "state.json"))
            service = {
                "id": "plan-1",
                "starts_at": "2030-01-01T12:00:00+00:00",
                "items": [
                    {"id": "one", "title": "Welcome", "length": 60, "starts_after": 0},
                    {"id": "two", "title": "Song", "length": 180, "starts_after": 60},
                ],
            }
            live = {"current_item_id": "two", "current_live_start_at": "2030-01-01T12:01:00+00:00"}
            runtime._remember_live(service, live)
            state = {"service": service, "timing": calculate_timing(service)}
            self.assertTrue(runtime._apply_cached_live_timing(state))
            self.assertEqual(state["timing"]["source"], "planning_center_live")
            self.assertEqual(state["timing"]["current_item"]["id"], "two")

    def test_configured_unassigned_media_titles_are_collected_per_widget(self):
        data = {"dashboards": [{"widgets": [
            {"type": "assignments", "settings": {"use_planning_center_icon": True, "unassigned_media_title": "Alternate Logo"}},
            {"type": "assignments", "settings": {"use_planning_center_icon": False, "unassigned_media_title": "Disabled Logo"}},
        ]}]}
        self.assertEqual(RuntimeService._configured_media_titles(data), ["Alternate Logo", "Icon"])

    def test_propresenter_title_matching_prefers_song_and_forward_duplicate(self):
        items = [
            {"id": "1", "title": "Welcome", "item_type": "item"},
            {"id": "2", "title": "Great I Am", "item_type": "song"},
            {"id": "3", "title": "Message", "item_type": "item"},
            {"id": "4", "title": "Great I Am", "item_type": "song"},
        ]
        matched = RuntimeService._match_presentation_item("GREAT—I AM!", items, "3", {"songs_only": True, "match_mode": "exact"})
        self.assertEqual(matched["id"], "4")


class ProPresenterLiveSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_stable_presentation_takes_control_and_advances_live(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeService(ConfigStore(Path(directory) / "state.json"))
            state = {
                "service": {"id": "plan", "service_type_id": "type", "series_id": "series", "starts_at": "2030-01-01T12:00:00+00:00", "items": [
                    {"id": "1", "title": "Welcome", "item_type": "item", "length": 60, "starts_after": 0},
                    {"id": "2", "title": "Song One", "item_type": "song", "length": 120, "starts_after": 60},
                    {"id": "3", "title": "Song Two", "item_type": "song", "length": 120, "starts_after": 180},
                ]},
                "propresenter": {"connected": True, "title": "Song Two", "presentation_uuid": "pp-3"},
                "timing": {"current_item": {"id": "1"}},
            }

            class FakeLiveClient:
                configured = True

                def __init__(self):
                    self.actions = []
                    self.current = "1"
                    self.control = False

                async def live_status(self, _plan, create=False):
                    return {"id": "live", "series_id": "series", "can_control": self.control, "can_take_control": True, "current_item_id": self.current, "current_live_start_at": "2030-01-01T12:00:00Z"}

                async def live_action(self, _plan, _live, action):
                    self.actions.append(action)
                    if action == "toggle_control":
                        self.control = True
                    elif action == "go_to_next_item":
                        self.current = str(int(self.current) + 1)
                    return await self.live_status(_plan)

            client = FakeLiveClient()
            settings = {"enabled": True, "auto_take_control": True, "songs_only": True, "allow_previous": False, "match_mode": "exact", "stable_seconds": 0, "refresh_seconds": 2}
            await runtime._sync_propresenter_live(state, client, settings, 10)
            await runtime._sync_propresenter_live(state, client, settings, 10.1)
            self.assertEqual(client.actions, ["toggle_control", "go_to_next_item", "go_to_next_item"])
            self.assertEqual(state["planning_center_live"]["state"], "synced")
            self.assertEqual(state["timing"]["current_item"]["id"], "3")
            self.assertEqual(state["timing"]["source"], "planning_center_live")

    async def test_manual_controls_use_services_live_when_automation_is_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "state.json")
            data = store.load()
            data["settings"]["demo_mode"] = False
            data["settings"]["planning_center"].update({"enabled": True, "application_id": "id", "secret": "secret"})
            data["settings"]["planning_center"]["live_from_propresenter"]["enabled"] = True
            store.save(data)
            runtime = RuntimeService(store)
            runtime.state = {"service": {"id": "plan", "service_type_id": "type", "starts_at": "2030-01-01T12:00:00+00:00", "items": [
                {"id": "1", "title": "First", "item_type": "item", "length": 60, "starts_after": 0},
                {"id": "2", "title": "Second", "item_type": "item", "length": 60, "starts_after": 60},
            ]}, "timing": {"current_item": {"id": "1"}}}

            class FakeClient:
                async def live_status(self, _plan, create=False):
                    return {"id": "live", "can_control": True, "can_take_control": True, "current_item_id": "1", "current_live_start_at": "2030-01-01T12:00:00Z"}

                async def live_action(self, _plan, _live, action):
                    self.action = action
                    return {**_live, "current_item_id": "2", "current_live_start_at": "2030-01-01T12:01:00Z"}

            client = FakeClient()
            with patch("app.services.runtime.PlanningCenterClient", return_value=client):
                state = await runtime.service_control("next")
            self.assertEqual(client.action, "go_to_next_item")
            self.assertEqual(state["timing"]["current_item"]["id"], "2")
            self.assertEqual(state["planning_center_live"]["message"], "Services LIVE was updated manually")


class ProPresenterTests(unittest.TestCase):
    def test_planning_center_playlist_context_reads_item_title_and_index(self):
        context = ProPresenterClient._playlist_context({"presentation": {
            "playlist": {"uuid": "playlist-1", "name": "August 2, 2026"},
            "item": {"uuid": "item-1", "name": "Good Grace", "index": 2},
            "playlist_item": {"id": {"name": "Good Grace - local file", "index": 2}, "is_pco": True},
        }})
        self.assertTrue(context["service_item_is_pco"])
        self.assertEqual(context["service_item_title"], "Good Grace")
        self.assertEqual(context["service_item_index"], 2)
        self.assertEqual(context["playlist_name"], "August 2, 2026")

    def test_pco_playlist_index_beats_different_local_presentation_name(self):
        items = [
            {"id": "1", "title": "Great I Am", "item_type": "song"},
            {"id": "2", "title": "Center", "item_type": "song"},
            {"id": "3", "title": "Good Grace", "item_type": "song"},
        ]
        match = RuntimeService._match_presentation_item(
            "Good Grace - Hillsong United arrangement",
            items,
            "1",
            {"songs_only": True, "match_mode": "exact"},
            service_item_title="Good Grace",
            service_item_index=2,
            is_pco_item=True,
        )
        self.assertEqual(match["id"], "3")

    def test_pco_playlist_index_matches_message_despite_scripture_filename(self):
        items = [
            {"id": "1", "title": "Good Grace", "item_type": "song"},
            {"id": "2", "title": "Message", "item_type": "item"},
        ]
        match = RuntimeService._match_presentation_item(
            "John 1_1-3 (ASB)",
            items,
            "1",
            {"songs_only": True, "match_mode": "exact"},
            service_item_title="John 1_1-3 (ASB)",
            service_item_index=1,
            is_pco_item=True,
        )
        self.assertEqual(match["id"], "2")

    def test_strong_title_fallback_can_match_a_non_song_item(self):
        items = [
            {"id": "1", "title": "Good Grace", "item_type": "song"},
            {"id": "2", "title": "Message", "item_type": "item"},
        ]
        match = RuntimeService._match_presentation_item(
            "Sunday Message",
            items,
            "1",
            {"songs_only": True, "match_mode": "exact"},
        )
        self.assertEqual(match["id"], "2")

    def test_exact_title_mode_ignores_common_presentation_suffix(self):
        items = [{"id": "1", "title": "Another In The Fire", "item_type": "song"}]
        match = RuntimeService._match_presentation_item(
            "Another In The Fire - Hillsong UNITED [PCO]",
            items,
            "",
            {"songs_only": True, "match_mode": "exact"},
        )
        self.assertEqual(match["id"], "1")

    def test_grouped_cues_and_slide_notes_are_read(self):
        presentation = {"groups": [{"cues": [{"slide": {"notes": "Watch the director"}}]}]}
        cues = ProPresenterClient._cues(presentation)
        self.assertEqual(ProPresenterClient._notes(cues[0]), "Watch the director")

    def test_group_names_and_colors_follow_each_cue(self):
        presentation = {
            "name": "Build My Life",
            "groups": [
                {
                    "name": "Verse 1",
                    "color": {"red": 1, "green": 0.2, "blue": 0.1, "alpha": 1},
                    "slides": [{"text": "Worthy of every song", "label": "Acoustic", "color": "#ffffff"}, {"text": "Worthy of all the praise"}],
                },
                {
                    "id": {"name": "Chorus", "color": "0.2 0.8 0.4 1"},
                    "cues": [{"text": "Holy, there is no one like You"}],
                },
            ],
        }
        entries = ProPresenterClient._cue_entries(presentation)
        self.assertEqual(ProPresenterClient._presentation_title(presentation), "Build My Life")
        self.assertEqual([entry["part"] for entry in entries], ["Verse 1", "Verse 1", "Chorus"])
        self.assertEqual(entries[0]["color"], "rgba(255, 51, 26, 1)")
        self.assertEqual(entries[2]["color"], "rgba(51, 204, 102, 1)")

    def test_nested_live_presentation_index_is_read(self):
        payload = {"presentation_index": {"index": 4, "presentation_id": {"uuid": "ABC-123"}}}
        self.assertEqual(ProPresenterClient._index(payload), 4)

    def test_thumbnail_url_uses_presentation_and_live_cue(self):
        presentation = {"id": {"uuid": "ABC-123", "name": "Welcome"}}
        uuid = ProPresenterClient._presentation_uuid(presentation)
        self.assertEqual(uuid, "ABC-123")
        self.assertEqual(
            ProPresenterClient._thumbnail_url(uuid, 3, "SLIDE-456"),
            "/api/integrations/propresenter/thumbnail/ABC-123/3?revision=SLIDE-456",
        )

    def test_presentation_title_and_hex_color_support_nested_ids(self):
        self.assertEqual(ProPresenterClient._presentation_title({"id": {"name": "Welcome"}}), "Welcome")
        self.assertEqual(ProPresenterClient._color("65a9ff"), "#65a9ff")
        self.assertEqual(ProPresenterClient._color("not-a-color"), "")


if __name__ == "__main__":
    unittest.main()
