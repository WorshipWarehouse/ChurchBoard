from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import re
import time
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.services.planning_center import PlanningCenterClient, calculate_timing, service_items
from app.services.propresenter import ProPresenterClient
from app.services.shure import ShureClient
from app.store import ConfigStore


class RuntimeService:
    def __init__(self, store: ConfigStore):
        self.store = store
        self.state: dict[str, Any] = self.demo_state()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_refresh = {"planning_center": 0.0, "planning_center_live": 0.0, "propresenter": 0.0, "shure": 0.0}
        self._service_control: dict[str, Any] = {"active": False}
        self._pp_live_candidate = ""
        self._pp_live_candidate_since = 0.0
        self._pp_live_handled = ""
        self._last_live: dict[str, Any] | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.refresh()
            try:
                await asyncio.wait_for(self._stop.wait(), 0.1)
            except asyncio.TimeoutError:
                pass

    async def refresh(self, force: bool = False) -> dict[str, Any]:
        stored_data = self.store.load()
        config = stored_data["settings"]
        configured_media_titles = self._configured_media_titles(stored_data)
        if config.get("demo_mode"):
            demo = deepcopy(self.state) if self.state.get("service", {}).get("id") == "demo" else self.demo_state()
            demo["organization_name"] = config.get("organization_name", "My Church")
            demo["timezone"] = config.get("timezone", "")
            demo["updated_at"] = datetime.now(timezone.utc).isoformat()
            demo["timing"] = calculate_timing(demo.get("service"))
            demo["manual_plan"] = config.get("manual_plan")
            demo["planning_center_live"] = {"enabled": bool((config.get("planning_center", {}).get("live_from_propresenter") or {}).get("enabled")), "state": "demo", "message": "Services LIVE automation is available when demonstration data is off"}
            self._apply_service_control(demo)
            self.state = demo
            return self.state
        next_state = deepcopy(self.state)
        next_state.update({"organization_name": config.get("organization_name", "ChurchBoard"), "timezone": config.get("timezone", ""), "updated_at": datetime.now(timezone.utc).isoformat(), "manual_plan": config.get("manual_plan")})
        live_config = config.get("planning_center", {}).get("live_from_propresenter") or {}
        if not live_config.get("enabled") or not self._apply_cached_live_timing(next_state):
            next_state["timing"] = calculate_timing(next_state.get("service"))
        clock = time.monotonic()
        propresenter = ProPresenterClient(config.get("propresenter", {}))
        configured_pp_interval = float(config.get("propresenter", {}).get("refresh_seconds", 0.2))
        pp_interval = max(0.1, min(configured_pp_interval, 0.2))
        pp_due = clock - self._last_refresh["propresenter"] >= pp_interval
        if propresenter.configured and (force or pp_due):
            self._last_refresh["propresenter"] = clock
            try:
                next_state["propresenter"] = await propresenter.status()
            except Exception as exc:
                next_state["propresenter"] = {"connected": False, "error": str(exc), "current": {}, "next": {}}
        # Publish slide changes before slower cloud integrations finish so a
        # Planning Center refresh cannot hold up the local ProPresenter view.
        self.state = deepcopy(next_state)
        pc = PlanningCenterClient(config.get("planning_center", {}))
        pc_due = clock - self._last_refresh["planning_center"] >= float(config.get("planning_center", {}).get("refresh_seconds", 60))
        if pc.configured and (force or pc_due):
            self._last_refresh["planning_center"] = clock
            try:
                candidates = await pc.candidate_plans()
                active = pc.select_plan(candidates, config.get("manual_plan"))
                detail = await pc.plan_detail(active) if active else None
                next_state.update({"plans": candidates, "service": detail, "people": detail.get("people", []) if detail else [], "planning_center": {"connected": True, "error": ""}})
                next_state["timing"] = calculate_timing(detail)
                media_by_title = {}
                media_errors = []
                for media_title in configured_media_titles:
                    try:
                        media = await pc.media_by_title(media_title)
                        if media and media.get("image_url"):
                            media_by_title[media_title.casefold()] = media
                    except Exception as media_exc:
                        media_errors.append(f"{media_title}: {media_exc}")
                next_state["planning_center_media"] = {
                    "by_title": media_by_title,
                    "icon": media_by_title.get("icon"),
                    "error": "; ".join(media_errors),
                }
            except Exception as exc:
                next_state["planning_center"] = {"connected": False, "error": str(exc)}
        if live_config.get("enabled"):
            self._apply_cached_live_timing(next_state)
        if live_config.get("enabled"):
            await self._sync_propresenter_live(next_state, pc, live_config, clock, force)
        else:
            next_state["planning_center_live"] = {"enabled": False, "state": "disabled", "message": "ProPresenter is not controlling Services LIVE"}
            self._pp_live_candidate = ""
            self._pp_live_handled = ""
            self._last_live = None
        shure = ShureClient(config.get("shure", {}))
        shure_due = clock - self._last_refresh["shure"] >= float(config.get("shure", {}).get("refresh_seconds", 0.5))
        if shure.configured and (force or shure_due):
            next_state["mics"] = await shure.status()
            self._last_refresh["shure"] = clock
        self._apply_assignments(next_state, config.get("position_mic_map", {}))
        self._apply_service_control(next_state)
        self.state = next_state
        return self.state

    async def _sync_propresenter_live(self, state: dict[str, Any], pc: PlanningCenterClient, settings: dict[str, Any], clock: float, force: bool = False) -> None:
        service, presentation = state.get("service") or {}, state.get("propresenter") or {}
        base_status = {"enabled": True, "state": "waiting", "message": "Waiting for an active Planning Center service and ProPresenter presentation"}
        if not pc.configured:
            state["planning_center_live"] = {**base_status, "state": "error", "message": "Planning Center is not connected"}
            return
        if not service.get("id") or not service.get("items"):
            state["planning_center_live"] = base_status
            return

        poll_due = clock - self._last_refresh["planning_center_live"] >= float(settings.get("refresh_seconds", 2))
        live = None
        if force or poll_due:
            self._last_refresh["planning_center_live"] = clock
            try:
                live = await pc.live_status(service)
                if live:
                    self._remember_live(service, live)
                    self._apply_live_timing(state, live)
                    state["planning_center_live"] = self._live_status_payload(live, state.get("planning_center_live"))
                else:
                    self._last_live = None
            except Exception as exc:
                state["planning_center_live"] = {**base_status, "state": "error", "message": f"Services LIVE status failed: {exc}"}

        title = str(presentation.get("title") or "").strip()
        service_item_title = str(presentation.get("service_item_title") or "").strip()
        service_item_index = presentation.get("service_item_index")
        is_pco_item = bool(presentation.get("service_item_is_pco"))
        match_title = service_item_title if is_pco_item and service_item_title else title
        if not presentation.get("connected") or not match_title:
            state["planning_center_live"] = {**base_status, "message": "Waiting for an active ProPresenter presentation"}
            return
        current_item_id = str((live or {}).get("current_item_id") or ((state.get("timing") or {}).get("current_item") or {}).get("id") or "")
        target = self._match_presentation_item(title, service.get("items") or [], current_item_id, settings, service_item_title=service_item_title, service_item_index=service_item_index, is_pco_item=is_pco_item)
        if target:
            presentation["planning_center_item_id"] = target.get("id")
            presentation["planning_center_item_title"] = target.get("title")
        signature = "|".join((str(service.get("id")), str(presentation.get("presentation_uuid") or ""), str(service_item_index if service_item_index is not None else ""), self._normalize_title(match_title)))
        if signature != self._pp_live_candidate:
            self._pp_live_candidate = signature
            self._pp_live_candidate_since = clock
            state["planning_center_live"] = {**base_status, "state": "stabilizing", "presentation_title": title, "service_item_title": service_item_title, "message": f"Waiting for “{match_title}” to remain active"}
            return
        stable_seconds = max(0.0, float(settings.get("stable_seconds", 2)))
        if clock - self._pp_live_candidate_since < stable_seconds:
            state["planning_center_live"] = {**base_status, "state": "stabilizing", "presentation_title": title, "service_item_title": service_item_title, "message": f"Waiting for “{match_title}” to remain active"}
            return
        if signature == self._pp_live_handled:
            return
        self._pp_live_handled = signature

        if not target:
            state["planning_center_live"] = {**base_status, "state": "no_match", "presentation_title": title, "service_item_title": service_item_title, "message": f"No Planning Center item matched “{match_title}”"}
            return
        try:
            live = live or await pc.live_status(service, create=bool(settings.get("auto_take_control", True)))
            if not live:
                state["planning_center_live"] = {**base_status, "state": "needs_live", "presentation_title": title, "target_item_id": target.get("id"), "target_item_title": target.get("title"), "message": "Open Services LIVE for this plan, then change to the presentation again"}
                return
            if not live.get("can_control"):
                if settings.get("auto_take_control", True) and live.get("can_take_control"):
                    live = await pc.live_action(service, live, "toggle_control") or live
                else:
                    reason = "This Planning Center token cannot take control" if not live.get("can_take_control") else "Take control in Services LIVE first"
                    state["planning_center_live"] = {**base_status, "state": "needs_control", "presentation_title": title, "target_item_id": target.get("id"), "target_item_title": target.get("title"), "message": reason}
                    return
            items = service.get("items") or []
            current_index = next((index for index, item in enumerate(items) if str(item.get("id")) == str(live.get("current_item_id"))), -1)
            target_index = next((index for index, item in enumerate(items) if str(item.get("id")) == str(target.get("id"))), -1)
            if target_index < 0:
                raise ValueError("The matching item is not in the active Planning Center plan")
            if current_index < 0:
                next_index = next((index for index, item in enumerate(items) if str(item.get("id")) == str(live.get("next_item_id"))), -1)
                if next_index < 0:
                    raise ValueError("Services LIVE did not report a current or next item")
                difference = target_index - next_index + 1
            else:
                difference = target_index - current_index
            if difference < 0 and not settings.get("allow_previous", False):
                state["planning_center_live"] = {**self._live_status_payload(live), "state": "behind", "presentation_title": title, "target_item_id": target.get("id"), "target_item_title": target.get("title"), "message": f"“{title}” is behind the current LIVE item; backward movement is disabled"}
                return
            if abs(difference) > 20:
                raise ValueError("The matching item is more than 20 service items away")
            action = "go_to_next_item" if difference > 0 else "go_to_previous_item"
            for _ in range(abs(difference)):
                live = await pc.live_action(service, live, action) or live
            self._service_control = {"active": False}
            self._remember_live(service, live)
            self._apply_live_timing(state, live)
            source = "Planning Center playlist" if is_pco_item and service_item_title else "presentation title"
            state["planning_center_live"] = {**self._live_status_payload(live), "state": "synced", "presentation_title": title, "service_item_title": service_item_title, "match_source": source, "target_item_id": target.get("id"), "target_item_title": target.get("title"), "message": f"Matched {target.get('title')} from the {source}"}
        except Exception as exc:
            state["planning_center_live"] = {**base_status, "state": "error", "presentation_title": title, "target_item_id": target.get("id"), "target_item_title": target.get("title"), "message": f"Services LIVE control failed: {exc}"}

    @staticmethod
    def _normalize_title(value: str) -> str:
        value = str(value).casefold().replace("&", " and ").replace("'", "").replace("’", "")
        value = unicodedata.normalize("NFKD", value)
        value = "".join(character if character.isalnum() else " " for character in value)
        value = value.encode("ascii", "ignore").decode("ascii")
        return " ".join(value.split())

    @classmethod
    def _title_variants(cls, value: str) -> set[str]:
        raw = str(value or "").strip()
        variants = {cls._normalize_title(raw)}
        for pattern in (r"\s+-\s+.*$", r"\s+\|\s+.*$", r"\s*\[[^]]+\]\s*$", r"\s*\([^)]*(?:pco|planning\s+center|acoustic|live|version)[^)]*\)\s*$"):
            shortened = re.sub(pattern, "", raw, flags=re.IGNORECASE).strip()
            if shortened:
                variants.add(cls._normalize_title(shortened))
        return {variant for variant in variants if variant}

    @classmethod
    def _title_score(cls, left: str, right: str) -> float:
        scores = []
        for first in cls._title_variants(left):
            for second in cls._title_variants(right):
                if first == second:
                    return 1.0
                if min(len(first), len(second)) >= 5 and (first in second or second in first):
                    scores.append(0.92)
                first_tokens, second_tokens = set(first.split()), set(second.split())
                overlap = len(first_tokens & second_tokens)
                token_score = (2 * overlap / (len(first_tokens) + len(second_tokens))) if first_tokens and second_tokens else 0
                scores.append(max(SequenceMatcher(None, first, second).ratio(), token_score))
        return max(scores, default=0.0)

    @classmethod
    def _match_presentation_item(cls, title: str, items: list[dict[str, Any]], current_item_id: str, settings: dict[str, Any], *, service_item_title: str = "", service_item_index: int | None = None, is_pco_item: bool = False) -> dict[str, Any] | None:
        candidates = list(items)
        song_candidates = [item for item in candidates if str(item.get("item_type") or "").casefold() == "song"]
        preferred = candidates if is_pco_item or not settings.get("songs_only", True) else song_candidates
        source_title = service_item_title if is_pco_item and service_item_title else title
        matches = [item for item in preferred if cls._title_score(source_title, item.get("title") or "") == 1]
        indexed_item = items[service_item_index] if is_pco_item and isinstance(service_item_index, int) and 0 <= service_item_index < len(items) else None
        if indexed_item:
            # ProPresenter's is_pco flag means this playlist was created from
            # the Planning Center plan. Its playlist index remains linked to
            # that plan item even when the local presentation has a completely
            # different filename (for example John 1_1-3 → Message).
            return indexed_item
        if not matches and preferred is not candidates:
            # A precise Planning Center item title is safe even when song
            # matching is preferred; this allows Message, Welcome, etc.
            matches = [item for item in candidates if cls._title_score(source_title, item.get("title") or "") == 1]
        if not matches:
            threshold = 0.74 if bool(is_pco_item and service_item_title) or settings.get("match_mode") == "flexible" else 0.9
            scored = [(cls._title_score(source_title, item.get("title") or ""), item) for item in candidates]
            best = max((score for score, _item in scored), default=0.0)
            if best >= threshold:
                matches = [item for score, item in scored if score >= best - 0.02]
        if not matches:
            return None
        current_index = next((index for index, item in enumerate(items) if str(item.get("id")) == str(current_item_id)), 0)
        indexed_matches = [(index, item) for index, item in enumerate(items) if item in matches]
        return min(indexed_matches, key=lambda pair: (pair[0] < current_index, abs(pair[0] - current_index)))[1]

    @staticmethod
    def _live_status_payload(live: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
        return {**(previous or {}), "enabled": True, "state": "live", "live_id": live.get("id"), "can_control": bool(live.get("can_control")), "can_take_control": bool(live.get("can_take_control")), "current_item_id": live.get("current_item_id"), "message": "Connected to Planning Center Services LIVE"}

    def _remember_live(self, service: dict[str, Any], live: dict[str, Any]) -> None:
        self._last_live = {**live, "_service_id": str(service.get("id") or "")}

    def _apply_cached_live_timing(self, state: dict[str, Any]) -> bool:
        service = state.get("service") or {}
        live = self._last_live or {}
        if not service.get("id") or str(live.get("_service_id") or "") != str(service.get("id")):
            return False
        self._apply_live_timing(state, live)
        return (state.get("timing") or {}).get("source") == "planning_center_live"

    @staticmethod
    def _apply_live_timing(state: dict[str, Any], live: dict[str, Any]) -> None:
        service, current_id = state.get("service") or {}, str(live.get("current_item_id") or "")
        if not service or not current_id:
            return
        current_start = live.get("current_live_start_at")
        for item in service.get("items") or []:
            if str(item.get("id")) == current_id:
                if current_start:
                    item["live_start_at"] = current_start
                item["live_end_at"] = live.get("current_live_end_at")
            elif item.get("live_start_at") and not item.get("live_end_at") and current_start:
                item["live_end_at"] = current_start
        timing = calculate_timing(service)
        visible_items = timing.get("service_items") or service.get("items") or []
        current_index = next((index for index, item in enumerate(visible_items) if str(item.get("id")) == current_id), -1)
        if current_index >= 0:
            timing["current_item"] = visible_items[current_index]
            timing["next_item"] = visible_items[current_index + 1] if current_index + 1 < len(visible_items) else None
        state["timing"] = {**timing, "state": "live", "source": "planning_center_live"}

    async def service_control(self, action: str) -> dict[str, Any]:
        config = self.store.load()["settings"]
        live_settings = config.get("planning_center", {}).get("live_from_propresenter") or {}
        service = self.state.get("service") or {}
        if live_settings.get("enabled") and not config.get("demo_mode") and service.get("id"):
            pc = PlanningCenterClient(config.get("planning_center", {}))
            try:
                live = await pc.live_status(service, create=action == "take")
                if not live:
                    raise ValueError("Open Services LIVE for the active plan first")
                if action == "take":
                    if not live.get("can_control"):
                        if not live.get("can_take_control"):
                            raise ValueError("This Planning Center token cannot take control of Services LIVE")
                        live = await pc.live_action(service, live, "toggle_control") or live
                elif action == "release":
                    if live.get("can_control"):
                        live = await pc.live_action(service, live, "toggle_control") or live
                elif action in {"next", "previous"}:
                    if not live.get("can_control"):
                        if not live_settings.get("auto_take_control", True) or not live.get("can_take_control"):
                            raise ValueError("Take control of Services LIVE first")
                        live = await pc.live_action(service, live, "toggle_control") or live
                    live = await pc.live_action(service, live, "go_to_next_item" if action == "next" else "go_to_previous_item") or live
                else:
                    raise ValueError("Unknown service control action")
                self._service_control = {"active": False}
                self._remember_live(service, live)
                self._apply_live_timing(self.state, live)
                self.state["planning_center_live"] = {**self._live_status_payload(live), "state": "live", "message": "Services LIVE was updated manually"}
                return self.state
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f"Planning Center Services LIVE control failed: {exc}") from exc

        return self._local_service_control(action)

    def _local_service_control(self, action: str) -> dict[str, Any]:
        service = self.state.get("service") or {}
        timing = self.state.get("timing") or {}
        items = timing.get("service_items") or service_items(service, timing.get("service_time_id"))
        if not items:
            raise ValueError("The active service has no items")
        current_item = (self.state.get("timing") or {}).get("current_item") or {}
        current_id = current_item.get("id")
        current_index = next((index for index, item in enumerate(items) if item.get("id") == current_id), 0)
        if action == "release":
            self._service_control = {"active": False}
        else:
            if not self._service_control.get("active") or self._service_control.get("service_id") != service.get("id"):
                self._service_control = {"active": True, "service_id": service.get("id"), "index": current_index, "started": time.monotonic()}
            if action == "next":
                self._service_control["index"] = min(len(items) - 1, int(self._service_control.get("index", 0)) + 1)
                self._service_control["started"] = time.monotonic()
            elif action == "previous":
                self._service_control["index"] = max(0, int(self._service_control.get("index", 0)) - 1)
                self._service_control["started"] = time.monotonic()
            elif action != "take":
                raise ValueError("Unknown service control action")
        self._apply_service_control(self.state)
        return self.state

    def _apply_service_control(self, state: dict[str, Any]) -> None:
        service = state.get("service") or {}
        timing = state.get("timing") or {}
        items = timing.get("service_items") or service_items(service, timing.get("service_time_id"))
        control = self._service_control
        if not control.get("active") or control.get("service_id") != service.get("id") or not items:
            state["service_control"] = {"active": False}
            if control.get("active") and control.get("service_id") != service.get("id"):
                self._service_control = {"active": False}
            return
        index = max(0, min(len(items) - 1, int(control.get("index", 0))))
        elapsed = max(0, int(time.monotonic() - float(control.get("started", time.monotonic()))))
        current = items[index]
        state["timing"] = {
            **(state.get("timing") or {}), "state": "controlled", "live": True,
            "current_item": current, "next_item": items[index + 1] if index + 1 < len(items) else None,
            "item_elapsed": elapsed, "item_delta": elapsed - int(current.get("length") or 0),
        }
        state["service_control"] = {"active": True, "index": index, "item_id": current.get("id"), "item_title": current.get("title")}

    @staticmethod
    def _apply_assignments(state: dict[str, Any], mapping: dict[str, str]) -> None:
        people: dict[str, dict[str, Any]] = {}
        for person in state.get("people", []):
            position = str(person.get("position") or "").strip().casefold()
            position_key = str(person.get("position_key") or "").strip()
            if position:
                people[position] = person
            if position_key:
                people[position_key] = person
        mic_by_id = {mic.get("id"): mic for mic in state.get("mics", [])}
        for position, mic_id in mapping.items():
            if mic_id in mic_by_id:
                lookup = str(position).strip()
                person = people.get(lookup) or people.get(lookup.casefold())
                fallback_position = lookup.split("::", 1)[-1] if "::" in lookup else lookup
                fallback_team = lookup.split("::", 1)[0] if "::" in lookup else ""
                person = person or {"name": "Unassigned", "photo": "", "position": fallback_position, "position_key": lookup, "team_id": fallback_team}
                mic_by_id[mic_id]["assignment"] = {"position": fallback_position, "position_key": lookup, **person}

    @staticmethod
    def _configured_media_titles(data: dict[str, Any]) -> list[str]:
        titles = {"Icon"}
        for dashboard in data.get("dashboards", []):
            for widget in dashboard.get("widgets", []):
                if widget.get("type") not in {"assignments", "mics"}:
                    continue
                settings = widget.get("settings") or {}
                if not settings.get("use_planning_center_icon"):
                    continue
                title = str(settings.get("unassigned_media_title") or "Icon").strip()
                if title:
                    titles.add(title)
        return sorted(titles, key=str.casefold)

    @staticmethod
    def demo_state(now: datetime | None = None) -> dict[str, Any]:
        people = [
            {"id": "1", "name": "Jordan Lee", "position": "Vox 1", "position_key": "band::vox 1", "team_id": "band", "team_name": "Band", "photo": "", "status": "Confirmed"},
            {"id": "2", "name": "Morgan Reed", "position": "Vox 2", "position_key": "band::vox 2", "team_id": "band", "team_name": "Band", "photo": "", "status": "Confirmed"},
            {"id": "3", "name": "Taylor Brooks", "position": "Worship Leader", "position_key": "band::worship leader", "team_id": "band", "team_name": "Band", "photo": "", "status": "Confirmed"},
        ]
        items = [
            {"id": "1", "title": "Welcome", "length": 180, "starts_after": 0, "notes": [], "leader": "Morgan Reed"},
            {"id": "2", "title": "Worship", "length": 1200, "starts_after": 180, "notes": [], "leader": "Jordan Lee"},
            {"id": "3", "title": "Message", "length": 2100, "starts_after": 1380, "notes": []},
            {"id": "4", "title": "Closing", "length": 300, "starts_after": 3480, "notes": []},
        ]
        now = now or datetime.now(timezone.utc)
        start = now.timestamp() - 450
        started_at = datetime.fromtimestamp(start, timezone.utc)
        demo_time = {"id": "demo-time", "starts_at": started_at.isoformat(), "ends_at": datetime.fromtimestamp(start + 3780, timezone.utc).isoformat(), "time_type": "service"}
        service = {"id": "demo", "service_type_id": "demo", "title": "Sunday Worship", "dates": now.strftime("%B %d").replace(" 0", " "), "starts_at": started_at.isoformat(), "planned_length": 3780, "times": [demo_time], "items": items, "people": people}
        mics = [
            {"id": "mic-1", "receiver": "QLX-D Rack A", "channel": 1, "name": "VOX 1", "battery_percent": 80, "rf": 91, "audio": 36, "online": True, "errors": [], "assignment": {"position": "Vox 1", **people[0]}},
            {"id": "mic-2", "receiver": "QLX-D Rack A", "channel": 2, "name": "VOX 2", "battery_percent": 40, "rf": 84, "audio": 58, "online": True, "errors": [], "assignment": {"position": "Vox 2", **people[1]}},
            {"id": "mic-3", "receiver": "ULX-D Rack B", "channel": 1, "name": "WL", "battery_percent": 20, "rf": 72, "audio": 15, "online": True, "errors": [], "assignment": {"position": "Worship Leader", **people[2]}},
            {"id": "mic-4", "receiver": "ULX-D Rack B", "channel": 2, "name": "PASTOR", "battery_percent": 0, "rf": 0, "audio": 0, "online": False, "errors": ["Transmitter offline"], "assignment": {"position": "Pastor", "position_key": "speaking::pastor", "team_id": "speaking", "team_name": "Speaking", "name": "Alex Morgan", "photo": ""}},
        ]
        return {
            "organization_name": "My Church", "timezone": "America/New_York", "updated_at": now.isoformat(), "service": service, "plans": [service], "people": people,
            "timing": calculate_timing(service, now), "mics": mics,
            "planning_center": {"connected": True, "demo": True, "error": ""},
            "propresenter": {"connected": True, "demo": True, "title": "Amazing Grace", "current": {"text": "Amazing grace, how sweet the sound", "notes": "Band: build into the chorus", "image_uuid": "", "image_url": "", "part": "Chorus", "color": "#9c6cff", "index": 3, "total": 8}, "next": {"text": "That saved a wretch like me", "notes": "", "image_uuid": "", "image_url": "", "part": "Verse 2", "color": "#45b7d1", "index": 4, "total": 8}},
        }
