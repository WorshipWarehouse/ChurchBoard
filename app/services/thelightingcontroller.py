from __future__ import annotations

import asyncio
from typing import Any
from xml.etree import ElementTree


class TheLightingControllerClient:
    """Client for TLC's External Application protocol (also used by ShowXpress)."""

    # TLC/ShowXpress recognises this client identifier from its official Live
    # Mobile/Companion-compatible External App protocol implementation.
    APP_NAME = "thelightingcontrollerclient"

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.get("enabled") and str(self.settings.get("host") or "").strip())

    async def buttons(self) -> list[dict[str, Any]]:
        reader, writer = await self._connect()
        try:
            return await self._button_list(reader, writer)
        finally:
            writer.close()
            await writer.wait_closed()

    async def trigger_button(self, name: str, mode: str = "toggle") -> None:
        if not name or any(character in name for character in "|\r\n"):
            raise ValueError("Invalid lighting button name")
        if mode not in {"press", "release", "toggle"}:
            raise ValueError("Lighting button mode must be press, release, or toggle")
        reader, writer = await self._connect()
        try:
            if mode == "press":
                # A cue click is an unambiguous press.  Do not require the
                # command name to appear in BUTTON_LIST: some TLC versions
                # expose one-based captions while accepting zero-based cue
                # identifiers (for example, displayed "1" accepts "0").
                await self._send(writer, "BUTTON_PRESS", name)
                return
            # Keep discovery and the command in the same authenticated session.
            # TLC installations commonly accept only one External App client.
            buttons = await self._button_list(reader, writer)
            button = next((item for item in buttons if item["name"] == name), None)
            if button is None:
                raise ValueError("That lighting button is no longer exposed by the controller")
            if mode == "toggle" and button["flash"]:
                # Flash buttons are momentary scenes; a click must not leave
                # one held down after ChurchBoard's request finishes.
                await self._send(writer, "BUTTON_PRESS", name)
                await self._send(writer, "BUTTON_RELEASE", name)
            else:
                command = "BUTTON_PRESS" if mode == "press" or (mode == "toggle" and not button["pressed"]) else "BUTTON_RELEASE"
                await self._send(writer, command, name)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _button_list(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> list[dict[str, Any]]:
        await self._send(writer, "BUTTON_LIST")
        while True:
            line = await self._read_line(reader, "the exposed button list")
            if not line:
                raise ConnectionError("The lighting controller closed the connection")
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if text.startswith("ERROR|"):
                raise ValueError(text.split("|", 1)[1] or "The lighting controller rejected the request")
            if text.startswith("BUTTON_LIST|"):
                return self._parse_buttons(text.split("|", 1)[1])

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        host = str(self.settings.get("host") or "").strip()
        try:
            port = int(self.settings.get("port") or 7348)
        except (TypeError, ValueError) as exc:
            raise ValueError("Enter a valid External App port number") from exc
        if not 1 <= port <= 65535:
            raise ValueError("External App port must be between 1 and 65535")
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
        except asyncio.TimeoutError as exc:
            raise ConnectionError(f"Timed out connecting to {host}:{port}. Verify the computer address, port, and firewall.") from exc
        except OSError as exc:
            detail = exc.strerror or str(exc) or exc.__class__.__name__
            raise ConnectionError(f"Could not connect to {host}:{port}: {detail}") from exc
        await self._send(writer, "HELLO", self.APP_NAME, str(self.settings.get("password") or ""))
        while True:
            line = await self._read_line(reader, "the ShowXpress/TLC sign-in reply")
            if not line:
                writer.close()
                await writer.wait_closed()
                raise ConnectionError("The lighting controller closed the connection during sign-in")
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if text == "HELLO":
                return reader, writer
            if text.startswith("ERROR|"):
                writer.close()
                await writer.wait_closed()
                raise ValueError(text.split("|", 1)[1] or "The lighting controller rejected the password")

    @staticmethod
    async def _read_line(reader: asyncio.StreamReader, waiting_for: str) -> bytes:
        try:
            return await asyncio.wait_for(reader.readline(), timeout=3)
        except asyncio.TimeoutError as exc:
            raise ConnectionError(f"Timed out waiting for {waiting_for}. Check that External App and External Control are enabled.") from exc

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, *parts: str) -> None:
        writer.write(("|".join(parts) + "\r\n").encode("ascii"))
        await writer.drain()

    @staticmethod
    def _parse_buttons(payload: str) -> list[dict[str, Any]]:
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise ValueError(f"The lighting controller returned invalid button data: {exc}") from exc
        buttons: list[dict[str, Any]] = []
        for page in root.findall("page"):
            page_name = page.get("name") or "Lighting"
            page_columns = int(page.get("columns") or 0)
            page_buttons = list(page.findall("button"))
            # TLC's external-app XML uses zero-based positions on some
            # releases, whereas CSS grid lines are one-based.  Treat a zero
            # in either coordinate as an unambiguous zero-based page so two
            # adjacent TLC buttons cannot be rendered on top of each other.
            zero_based = any(
                element.get(axis) == "0"
                for element in page_buttons
                for axis in ("column", "line")
            )
            coordinate_offset = 1 if zero_based else 0
            for element in page_buttons:
                name = (element.text or "").strip()
                if not name:
                    continue
                buttons.append({
                    "name": name, "page": page_name, "page_columns": page_columns,
                    "column": int(element.get("column") or 0) + coordinate_offset,
                    "line": int(element.get("line") or 0) + coordinate_offset,
                    "color": element.get("color") or "#4c6b8a",
                    "pressed": element.get("pressed") == "1", "flash": element.get("flash") == "1",
                })
        return sorted(buttons, key=lambda item: (item["page"].casefold(), item["line"], item["column"], item["name"].casefold()))
