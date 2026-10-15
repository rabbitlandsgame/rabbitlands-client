#!/usr/bin/env python3
"""Prove server-placed map markers against the genuine Eloria server.

`SEND_MAP_MARKER(90)` and `REMOVE_MAP_MARKER(91)` were enumerated in the client
and decoded by nothing, so every marker the server placed - waypoints, quest
targets, tutorial pointers - arrived and vanished. This probe drives the real
server's own waypoint command and checks both directions on the wire.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/map_markers_local.py <server-root>
"""

from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (  # noqa: E402
    LocalServer, close_client, create_character, disposable_credentials,
    login, packet, read_packet)

RAW_TEXT_C = 0
SEND_MAP_MARKER = 90
REMOVE_MAP_MARKER = 91

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


async def drain(reader, seconds: float = 1.5) -> list[tuple[int, bytes]]:
    frames: list[tuple[int, bytes]] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return frames
        try:
            frames.append(await read_packet(reader, remaining))
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return frames


async def ask(writer, reader, text: str):
    writer.write(packet(RAW_TEXT_C, text.encode("utf-8") + b"\0"))
    await writer.drain()
    return await drain(reader)


def decode_marker(payload: bytes) -> dict:
    marker_id, x, y = struct.unpack_from("<HHH", payload)
    reference, label, tail = payload[6:].split(b"\0", 2)
    assert tail == b"", "no trailing bytes after the label"
    return {"marker_id": marker_id, "x": x, "y": y,
            "map_reference": reference.decode("utf-8"),
            "label": label.decode("utf-8")}


async def probe(port: int) -> None:
    name, password = disposable_credentials("mark")
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)
    try:
        await ask(writer, reader, "#clientcaps navigation_hud_v1")

        frames = await ask(writer, reader, "#waypoint 780 490 Reed bank")
        placed = [decode_marker(payload) for command, payload in frames
                  if command == SEND_MAP_MARKER]
        check("the server places a marker when a waypoint is set",
              len(placed) == 1, str([command for command, _ in frames]))
        if placed:
            check("the marker carries the tile, the map and the label",
                  placed[0]["x"] == 780 and placed[0]["y"] == 490
                  and placed[0]["map_reference"].endswith(".elm")
                  and placed[0]["label"] == "Reed bank", str(placed[0]))

        frames = await ask(writer, reader, "#waypoint clear")
        removed = [struct.unpack_from("<H", payload)[0]
                   for command, payload in frames
                   if command == REMOVE_MAP_MARKER]
        check("clearing the waypoint removes the marker by id",
              bool(placed) and removed == [placed[0]["marker_id"]],
              str(removed))
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-map-markers-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
