from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import quote

import httpx


class ProPresenterClient:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self._client: httpx.AsyncClient | None = None
        self._active_payload: dict[str, Any] = {}
        self._playlist_payload: dict[str, Any] = {}
        self._transport_payload: dict[str, Any] = {}
        self._active_refreshed = 0.0
        self._playlist_refreshed = 0.0
        self._transport_refreshed = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.settings.get("enabled") and self.settings.get("host"))

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=2)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def status(self) -> dict[str, Any]:
        base = f"http://{self.settings.get('host', '127.0.0.1')}:{int(self.settings.get('port', 50001))}"
        clock = time.monotonic()
        fetch_active = not self._active_payload or clock - self._active_refreshed >= 0.25
        fetch_playlist = not self._playlist_payload or clock - self._playlist_refreshed >= 0.5
        names = ["slide", "index"]
        requests = [
            self._http().get(f"{base}/v1/status/slide"),
            self._http().get(f"{base}/v1/presentation/slide_index"),
        ]
        if fetch_active:
            names.append("active")
            requests.append(self._http().get(f"{base}/v1/presentation/active"))
        if fetch_playlist:
            names.append("playlist")
            requests.append(self._http().get(f"{base}/v1/playlist/active"))
        responses = dict(zip(names, await asyncio.gather(*requests)))
        responses["slide"].raise_for_status()
        slide = responses["slide"].json()
        index_response = responses["index"]
        index_payload = index_response.json() if index_response.is_success else 0
        active_response = responses.get("active")
        if active_response is not None and active_response.is_success:
            self._active_payload = active_response.json()
            self._active_refreshed = clock
        playlist_response = responses.get("playlist")
        if playlist_response is not None and playlist_response.is_success:
            self._playlist_payload = playlist_response.json()
            self._playlist_refreshed = clock
        active = self._active_payload
        playlist_payload = self._playlist_payload
        current = slide.get("current") or {}
        next_slide = slide.get("next") or {}
        index = self._index(index_payload)
        presentation = active.get("presentation", active)
        cue_entries = self._presentation_cue_entries(presentation)
        cue_total = self._cue_total(index_payload, len(cue_entries))
        current_position, next_position = self._cue_positions(cue_entries, current, next_slide, index)
        current_entry = cue_entries[current_position] if 0 <= current_position < len(cue_entries) else {}
        next_entry = cue_entries[next_position] if 0 <= next_position < len(cue_entries) else {}
        current_details = current_entry.get("cue", {})
        next_details = next_entry.get("cue", {})
        current_result = self._slide(current)
        next_result = self._slide(next_slide)
        current_result["notes"] = current_result["notes"] or self._notes(current_details)
        next_result["notes"] = next_result["notes"] or self._notes(next_details)
        presentation_uuid = self._presentation_uuid(presentation)
        playlist_context = self._playlist_context(playlist_payload)
        if clock - self._transport_refreshed >= 0.5:
            transport_responses = await asyncio.gather(
                self._http().get(f"{base}/v1/transport/presentation/current"),
                self._http().get(f"{base}/v1/transport/presentation/time"),
                self._http().get(f"{base}/v1/timer/video_countdown"),
                return_exceptions=True,
            )
            self._transport_refreshed = clock
            self._transport_payload = self._transport_status(*transport_responses)
        media = self._transport_payload.get("media") or {}
        current_timer = self._countdown_text(current_result.get("text"))
        if not current_timer and media.get("is_playing") and not media.get("audio_only"):
            current_timer = self._countdown_text(self._transport_payload.get("video_countdown"))
        current_result.update({
            "part": current_entry.get("part", ""),
            "color": current_entry.get("color", ""),
            "index": index + 1,
            "total": cue_total,
            "image_url": self._thumbnail_url(presentation_uuid, current_position, current_result["image_uuid"])
            if current_result["image_uuid"] or current_details else "",
            "timer_text": current_timer,
            "media": media,
        })
        next_result.update({
            "part": next_entry.get("part", ""),
            "color": next_entry.get("color", ""),
            "index": index + 2 if index + 1 < cue_total else 0,
            "total": cue_total,
            "image_url": self._thumbnail_url(presentation_uuid, next_position, next_result["image_uuid"])
            if next_result["image_uuid"] or next_details else "",
            "timer_text": self._countdown_text(next_result.get("text")),
        })
        return {
            "connected": True,
            "title": self._presentation_title(presentation),
            "presentation_uuid": presentation_uuid,
            **playlist_context,
            "current": current_result,
            "next": next_result,
        }

    @staticmethod
    def _playlist_context(raw: Any) -> dict[str, Any]:
        destination = raw.get("presentation") if isinstance(raw, dict) else {}
        destination = destination if isinstance(destination, dict) else {}
        playlist = destination.get("playlist") if isinstance(destination.get("playlist"), dict) else {}
        item = destination.get("item") if isinstance(destination.get("item"), dict) else {}
        playlist_item = destination.get("playlist_item") if isinstance(destination.get("playlist_item"), dict) else {}
        identifier = playlist_item.get("id") if isinstance(playlist_item.get("id"), dict) else {}
        raw_index = item.get("index", identifier.get("index"))
        try:
            index = int(raw_index)
            if index < 0 or index >= 2**31:
                index = None
        except (TypeError, ValueError):
            index = None
        return {
            "service_item_title": str(item.get("name") or identifier.get("name") or "").strip(),
            "service_item_index": index,
            "service_item_is_pco": bool(playlist_item.get("is_pco")),
            "playlist_name": str(playlist.get("name") or "").strip(),
            "playlist_uuid": str(playlist.get("uuid") or "").strip(),
        }

    @staticmethod
    def _slide(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {"text": str(raw or ""), "notes": "", "image_uuid": ""}
        return {
            "text": raw.get("text") or raw.get("label") or raw.get("name") or "",
            "notes": raw.get("notes") or raw.get("slide_notes") or "",
            "image_uuid": raw.get("image_uuid") or raw.get("uuid") or "",
        }

    @staticmethod
    def _countdown_text(value: Any) -> str:
        pattern = r"-?\d{1,3}:\d{2}(?::\d{2})?(?:\.\d{1,2})?"
        lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
        return next((line for line in reversed(lines) if re.fullmatch(pattern, line)), "")

    @staticmethod
    def _transport_status(current: Any, position: Any, video_countdown: Any) -> dict[str, Any]:
        def payload(response: Any) -> Any:
            if isinstance(response, Exception) or not getattr(response, "is_success", False):
                return None
            try:
                return response.json()
            except Exception:
                return None

        media_raw = payload(current)
        position_raw = payload(position)
        countdown_raw = payload(video_countdown)
        media = {}
        if isinstance(media_raw, dict) and (media_raw.get("uuid") or media_raw.get("is_playing")):
            try:
                current_time = max(0.0, float(position_raw))
            except (TypeError, ValueError):
                current_time = 0.0
            try:
                duration = max(0.0, float(media_raw.get("duration") or media_raw.get("length") or 0))
            except (TypeError, ValueError):
                duration = 0.0
            media = {
                "is_playing": bool(media_raw.get("is_playing")),
                "uuid": str(media_raw.get("uuid") or ""),
                "name": str(media_raw.get("name") or ""),
                "audio_only": bool(media_raw.get("audio_only")),
                "position": current_time,
                "duration": duration,
            }
        return {"media": media, "video_countdown": str(countdown_raw or "")}

    @staticmethod
    def _index(raw: Any) -> int:
        if isinstance(raw, int):
            return raw
        if isinstance(raw, dict):
            for key in ("index", "slide_index", "presentation_index"):
                if key in raw:
                    value = raw[key]
                    if isinstance(value, dict):
                        nested = ProPresenterClient._index(value)
                        if nested >= 0:
                            return nested
                    else:
                        try:
                            return int(value)
                        except (TypeError, ValueError):
                            pass
        return 0

    @classmethod
    def _cue_total(cls, raw: Any, fallback: int) -> int:
        if isinstance(raw, dict):
            try:
                total = int(raw.get("total_cues") or 0)
                if total > 0:
                    return total
            except (TypeError, ValueError):
                pass
            for key in ("presentation_index", "presentation"):
                nested = raw.get(key)
                if isinstance(nested, dict):
                    total = cls._cue_total(nested, 0)
                    if total > 0:
                        return total
        return max(0, fallback)

    @classmethod
    def _presentation_cue_entries(cls, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, dict):
            return []
        groups = raw.get("groups") or []
        arrangements = raw.get("arrangements") or []
        if isinstance(groups, dict):
            groups = list(groups.values())
        if not isinstance(groups, list) or not isinstance(arrangements, list) or not arrangements:
            return cls._cue_entries(raw)

        def identifier(value: Any) -> str:
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                direct = value.get("uuid")
                if isinstance(direct, str):
                    return direct
                return identifier(value.get("id"))
            return ""

        current = raw.get("current_arrangement")
        current_id = identifier(current)
        current_name = cls._presentation_title(current) if isinstance(current, dict) else str(current or "").strip()
        arrangement = next((row for row in arrangements if isinstance(row, dict) and current_id and identifier(row.get("id")) == current_id), None)
        if arrangement is None and current_name:
            arrangement = next((row for row in arrangements if isinstance(row, dict) and cls._presentation_title(row.get("id")) == current_name), None)
        if arrangement is None:
            def arrangement_order(row: dict[str, Any]) -> int:
                try:
                    return int((row.get("id") or {}).get("index") or 0) if isinstance(row.get("id"), dict) else 0
                except (TypeError, ValueError):
                    return 0

            arrangement = min(
                (row for row in arrangements if isinstance(row, dict)),
                key=arrangement_order,
                default=None,
            )
        sequence = arrangement.get("groups") if isinstance(arrangement, dict) else None
        if not isinstance(sequence, list) or not sequence:
            return cls._cue_entries(raw)

        group_map = {identifier(group): group for group in groups if isinstance(group, dict) and identifier(group)}
        sequence_ids = [identifier(value) for value in sequence]
        sequence_ids = [value for value in sequence_ids if value in group_map]
        if not sequence_ids:
            return cls._cue_entries(raw)

        referenced = set(sequence_ids)
        first_arranged = next((index for index, group in enumerate(groups) if identifier(group) in referenced), 0)
        entries: list[dict[str, Any]] = []
        # Thumbnail indexes include leading media/background cues even though
        # presentation_index and the active arrangement do not.
        for group in groups[:first_arranged]:
            if isinstance(group, dict):
                entries.extend(cls._cue_entries(group))
        for group_id in sequence_ids:
            entries.extend(cls._cue_entries(group_map[group_id]))
        return entries

    @classmethod
    def _cue_positions(
        cls,
        entries: list[dict[str, Any]],
        current: Any,
        next_slide: Any,
        reported_index: int,
    ) -> tuple[int, int]:
        def identity(raw: Any) -> str:
            slide = cls._slide(raw)
            return " ".join(str(slide.get("text") or "").casefold().split())

        def resolve(raw: Any, fallback: int, minimum: int = 0) -> tuple[int, bool]:
            wanted = identity(raw)
            if wanted:
                candidates = [
                    position
                    for position, entry in enumerate(entries)
                    if position >= minimum and identity(entry.get("cue")) == wanted
                ]
                if candidates:
                    return min(candidates, key=lambda position: (abs(position - fallback), position < fallback, position)), True
            return fallback, False

        current_position, current_matched = resolve(current, reported_index)
        next_position, next_matched = resolve(next_slide, current_position + 1, current_position + 1)
        if not current_matched and next_matched:
            current_position = max(0, next_position - 1)
        if current_matched and not next_matched:
            next_position = current_position + 1
        return current_position, next_position

    @classmethod
    def _cues(cls, raw: Any) -> list[dict[str, Any]]:
        return [entry["cue"] for entry in cls._cue_entries(raw)]

    @classmethod
    def _cue_entries(
        cls,
        raw: Any,
        inherited_part: str = "",
        inherited_color: str = "",
    ) -> list[dict[str, Any]]:
        if not isinstance(raw, dict):
            return []

        part = cls._part_name(raw) or inherited_part
        color = cls._color(cls._raw_color(raw)) or inherited_color
        direct = raw.get("cues") or raw.get("slides")
        if isinstance(direct, list):
            entries: list[dict[str, Any]] = []
            for cue in direct:
                if not isinstance(cue, dict):
                    continue
                # A cue's `label` is a per-slide label, not its Verse/Chorus
                # group. Prefer explicit cue group data, then inherit the group.
                cue_part = cls._cue_part_name(cue) or part
                # ProPresenter also exposes a per-slide color. The part bug
                # should use the enclosing Verse/Chorus group color.
                cue_color = color or cls._color(cls._raw_color(cue))
                entries.append({"cue": cue, "part": cue_part, "color": cue_color})
            return entries

        entries = []
        groups = raw.get("groups") or []
        if isinstance(groups, dict):
            groups = list(groups.values())
        for group in groups:
            if isinstance(group, dict):
                entries.extend(cls._cue_entries(group, part, color))
        return entries

    @classmethod
    def _presentation_title(cls, raw: Any) -> str:
        if not isinstance(raw, dict):
            return ""
        for key in ("name", "title", "presentation_name", "presentationName"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("id", "presentation"):
            value = cls._presentation_title(raw.get(key))
            if value:
                return value
        return ""

    @classmethod
    def _cue_part_name(cls, raw: Any) -> str:
        if not isinstance(raw, dict):
            return ""
        for key in ("group_name", "groupName", "part"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        group = raw.get("group")
        if isinstance(group, str) and group.strip():
            return group.strip()
        if isinstance(group, dict):
            for key in ("name", "label"):
                value = group.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    @staticmethod
    def _presentation_uuid(raw: Any) -> str:
        if not isinstance(raw, dict):
            return ""
        value = raw.get("uuid")
        if isinstance(value, str):
            return value
        identifier = raw.get("id")
        if isinstance(identifier, dict) and isinstance(identifier.get("uuid"), str):
            return identifier["uuid"]
        return ""

    @staticmethod
    def _thumbnail_url(presentation_uuid: str, index: int, revision: str = "") -> str:
        if not presentation_uuid or index < 0 or not re.fullmatch(r"[A-Za-z0-9-]+", presentation_uuid):
            return ""
        url = f"/api/integrations/propresenter/thumbnail/{quote(presentation_uuid, safe='')}/{index}"
        if revision and re.fullmatch(r"[A-Za-z0-9-]+", revision):
            url += f"?revision={quote(revision, safe='')}"
        return url

    async def thumbnail(self, presentation_uuid: str, index: int) -> tuple[bytes, str]:
        if not re.fullmatch(r"[A-Za-z0-9-]+", presentation_uuid) or index < 0:
            raise ValueError("Invalid ProPresenter presentation or slide index")
        base = f"http://{self.settings.get('host', '127.0.0.1')}:{int(self.settings.get('port', 50001))}"
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{base}/v1/presentation/{quote(presentation_uuid, safe='')}/thumbnail/{index}",
                params={"quality": 960, "thumbnail_type": "jpeg"},
                headers={"Accept": "image/jpeg"},
            )
            response.raise_for_status()
        return response.content, response.headers.get("content-type", "image/jpeg")

    @classmethod
    def _part_name(cls, raw: Any) -> str:
        if not isinstance(raw, dict):
            return ""
        for key in ("group_name", "groupName", "part", "label"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        group = raw.get("group")
        if isinstance(group, str) and group.strip():
            return group.strip()
        for key in ("id", "group"):
            nested = raw.get(key)
            if isinstance(nested, dict):
                for nested_key in ("name", "label"):
                    value = nested.get(nested_key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        # Presentation group objects commonly use `name`; avoid interpreting cue
        # names as song parts unless the object also contains slides/cues.
        if any(key in raw for key in ("cues", "slides")):
            value = raw.get("name")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _raw_color(raw: Any) -> Any:
        if not isinstance(raw, dict):
            return None
        for key in ("group_color", "groupColor", "color"):
            if raw.get(key) is not None:
                return raw[key]
        for key in ("id", "group"):
            nested = raw.get(key)
            if isinstance(nested, dict):
                for color_key in ("group_color", "groupColor", "color"):
                    if nested.get(color_key) is not None:
                        return nested[color_key]
        return None

    @classmethod
    def _color(cls, raw: Any) -> str:
        if isinstance(raw, str):
            value = raw.strip()
            if re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value):
                return value
            if re.fullmatch(r"[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value):
                return f"#{value}"
            numbers = value.replace(",", " ").split()
            if len(numbers) in (3, 4):
                try:
                    return cls._rgba([float(number) for number in numbers])
                except ValueError:
                    return ""
            return ""
        if isinstance(raw, (list, tuple)) and len(raw) in (3, 4):
            try:
                return cls._rgba([float(number) for number in raw])
            except (TypeError, ValueError):
                return ""
        if isinstance(raw, dict):
            keys = ("red", "green", "blue", "alpha") if "red" in raw else ("r", "g", "b", "a")
            if all(key in raw for key in keys[:3]):
                try:
                    return cls._rgba([float(raw[key]) for key in keys if key in raw])
                except (TypeError, ValueError):
                    return ""
        return ""

    @staticmethod
    def _rgba(values: list[float]) -> str:
        normalized = max(values[:3], default=0) <= 1
        rgb = [round(max(0, min(1 if normalized else 255, value)) * (255 if normalized else 1)) for value in values[:3]]
        if len(values) == 4:
            alpha = max(0, min(1, values[3] if values[3] <= 1 else values[3] / 255))
            return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha:g})"
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    @classmethod
    def _notes(cls, raw: Any) -> str:
        if isinstance(raw, dict):
            for key in ("notes", "slide_notes"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for key in ("slide", "presentation", "action"):
                value = cls._notes(raw.get(key))
                if value:
                    return value
        return ""
