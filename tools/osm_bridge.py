#!/usr/bin/env python3
"""Relay Open Sound Meter UDP multicast measurements to WebSocket clients.

OSM's Remote API packet shape varies by release and is not yet formally
documented.  The bridge therefore accepts JSON packets and common
``key=value`` packets, normalizes known level fields, and can log unknown
packets with ``--debug`` to make field mapping safe and repeatable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import socket
from datetime import datetime, timezone
from typing import Any

import httpx
from websockets.asyncio.server import broadcast, serve

MULTICAST_GROUP = "239.255.42.42"
MULTICAST_PORT = 49007
LEVEL_ALIASES = {
    "laeq": ("laeq", "laeq_db", "laeqdb", "la_eq"),
    "lceq": ("lceq", "lceq_db", "lceqdb", "lc_eq"),
    "lzeq": ("lzeq", "lzeq_db", "lzeqdb", "lz_eq"),
    "peak": ("peak", "peak_db", "lpeak", "lpk"),
    "fast": ("fast", "fast_db", "laf", "lafmax"),
    "slow": ("slow", "slow_db", "las", "lasmax"),
}
SPL_OFFSET = 140.0


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if -200 <= result <= 200 else None


def parse_packet(packet: bytes) -> dict[str, Any] | None:
    """Normalize one OSM Remote API packet without guessing invalid values."""
    text = packet.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raw = {key.casefold(): value for key, value in re.findall(r"([A-Za-z_][\w.-]*)\s*[=:]\s*(-?\d+(?:\.\d+)?)", text)}
    if not isinstance(raw, dict):
        return None
    if raw.get("api") == "Open Sound Meter" and raw.get("message") == "levels" and isinstance(raw.get("data"), dict):
        data = raw["data"]
        def level(weighting: str, response: str) -> float | None:
            raw_level = _number((data.get(weighting) or {}).get(response))
            return max(0.0, raw_level + SPL_OFFSET) if raw_level is not None else None
        a_fast, a_slow = level("A", "Fast"), level("A", "Slow")
        result = {"type": "osm-level", "timestamp": datetime.now(timezone.utc).isoformat()}
        for key, value in {"laeq": a_fast, "a_fast": a_fast, "a_slow": a_slow, "b_fast": level("B", "Fast"), "b_slow": level("B", "Slow"), "c_fast": level("C", "Fast"), "c_slow": level("C", "Slow"), "z_fast": level("Z", "Fast"), "z_slow": level("Z", "Slow")}.items():
            if value is not None:
                result[key] = value
        return result if len(result) > 2 else None
    flattened = {str(key).casefold().replace("-", "_"): value for key, value in raw.items()}
    result: dict[str, Any] = {"type": "osm-level", "timestamp": datetime.now(timezone.utc).isoformat()}
    for name, aliases in LEVEL_ALIASES.items():
        value = next((_number(flattened.get(alias)) for alias in aliases if _number(flattened.get(alias)) is not None), None)
        if value is not None:
            result[name] = value
    return result if len(result) > 2 else None


class OSMProtocol(asyncio.DatagramProtocol):
    def __init__(self, clients: set, debug: bool, churchboard_url: str) -> None:
        self.clients, self.debug, self.churchboard_url = clients, debug, churchboard_url

    def datagram_received(self, data: bytes, address: tuple[str, int]) -> None:
        message = parse_packet(data)
        if message:
            broadcast(self.clients, json.dumps(message, separators=(",", ":")))
            if self.churchboard_url:
                asyncio.create_task(self.publish_to_churchboard(message))
        elif self.debug:
            logging.info("Unrecognized packet from %s: %r", address[0], data[:1000])

    async def publish_to_churchboard(self, message: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                await client.post(self.churchboard_url, json=message)
        except httpx.HTTPError as exc:
            if self.debug:
                logging.info("Could not publish to ChurchBoard: %s", exc)


async def run(args: argparse.Namespace) -> None:
    clients: set = set()
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", args.multicast_port))
    interface = socket.inet_aton(args.interface)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(args.multicast_group) + interface)
    transport, _ = await loop.create_datagram_endpoint(lambda: OSMProtocol(clients, args.debug, args.churchboard_url), sock=sock)

    async def connected(websocket) -> None:
        clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            clients.discard(websocket)

    logging.info("Listening for OSM multicast on %s:%d; WebSocket at ws://%s:%d", args.multicast_group, args.multicast_port, args.host, args.port)
    try:
        async with serve(connected, args.host, args.port):
            await asyncio.Future()
    finally:
        transport.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge Open Sound Meter multicast to WebSocket")
    parser.add_argument("--host", default="0.0.0.0", help="WebSocket bind address (default: all interfaces)")
    parser.add_argument("--port", type=int, default=8041, help="WebSocket port (default: 8041)")
    parser.add_argument("--multicast-group", default=MULTICAST_GROUP)
    parser.add_argument("--multicast-port", type=int, default=MULTICAST_PORT)
    parser.add_argument("--interface", default="0.0.0.0", help="IPv4 interface address used to join multicast")
    parser.add_argument("--churchboard-url", default="", help="Optional ChurchBoard ingest URL for reports, e.g. http://127.0.0.1:8040/api/integrations/osm/measurement")
    parser.add_argument("--debug", action="store_true", help="Log unrecognized packets for protocol mapping")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.debug else logging.WARNING, format="%(message)s")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
