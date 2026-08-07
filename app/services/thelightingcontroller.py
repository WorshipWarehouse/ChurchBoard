from __future__ import annotations

import asyncio
from typing import Any
from xml.etree import ElementTree


class TheLightingControllerClient:
    """Client for TLC's External Application protocol (also used by ShowXpress)."""

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.get("enabled") and str(self.settings.get("host") or "").strip())

    async def buttons(self) -> list[dict[str, Any]]:
        reader, writer = await self._connect()
        try:
            await self._send(writer, "BUTTON_LIST")
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=3)
                if not line:
                    raise ConnectionError("The lighting controller closed the connection")
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if text.startswith("ERROR|"):
                    raise ValueError(text.split("|", 1)[1] or "The lighting controller rejected the request")
                if text.startswith("BUTTON_LIST|"):
                    return self._parse_buttons(text.split("|", 1)[1])
        finally:
            writer.close()
            await writer.wait_closed()

    async def trigger_button(self, name: str, mode: str = "toggle") -> None:
        if not name or any(character in name for character in "|\r\n"):
            raise ValueError("Invalid lighting button name")
        if mode not in {"press", "release", "toggle"}:
            raise ValueError("Lighting button mode must be press, release, or toggle")
        # Query first so ChurchBoard never becomes an arbitrary TCP command proxy.
        buttons = await self.buttons()
        button = next((item for item in buttons if item["name"] == name), None)
        if button is None:
            raise ValueError("That lighting button is no longer exposed by the controller")
        command = "BUTTON_PRESS" if mode == "press" or (mode == "toggle" and not button["pressed"]) else "BUTTON_RELEASE"
        reader, writer = await self._connect()
        del reader
        try:
            await self._send(writer, command, name)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        host = str(self.settings.get("host") or "").strip()
        port = int(self.settings.get("port") or 7348)
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
        await self._send(writer, "HELLO", "churchboard", str(self.settings.get("password") or ""))
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=3)
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
            for element in page.findall("button"):
                name = (element.text or "").strip()
                if not name:
                    continue
                buttons.append({
                    "name": name, "page": page_name, "column": int(element.get("column") or 0),
                    "line": int(element.get("line") or 0), "color": element.get("color") or "#4c6b8a",
                    "pressed": element.get("pressed") == "1", "flash": element.get("flash") == "1",
                })
        return sorted(buttons, key=lambda item: (item["page"].casefold(), item["line"], item["column"], item["name"].casefold()))
