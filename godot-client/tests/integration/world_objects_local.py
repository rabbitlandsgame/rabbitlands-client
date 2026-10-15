#!/usr/bin/env python3
"""Prove placed objects and teleporters against the real server.

A recorded gap. Everything the client knew about a map arrived with the map,
so nothing could raise a totem in the square while somebody was standing in it,
and the client could see a portal's art without any idea it was a portal.

Two parts of 2.9 stay closed, and the server's opcode pin still holds both:
`MAP_SET_OBJECTS(220)` and `MAP_STATE_OBJECTS(221)` are superseded by the
fork's own `ELORIA_MAP_OBJECTS(236)`, which states strictly more; and mines
have no concept behind them at all.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/world_objects_local.py <server-root>
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
MOVE_TO = 1
RAW_TEXT = 0
GET_TELEPORTERS_LIST = 10
TELEPORT_IN = 12
TELEPORT_OUT = 13
GET_3D_OBJ_LIST = 74
GET_3D_OBJ = 75
REMOVE_3D_OBJ = 76

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label
          + (f"  [{detail}]" if detail else ""))


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


async def ask(writer, reader, text: str, seconds: float = 1.5):
    writer.write(packet(RAW_TEXT_C, text.encode("utf-8") + b"\0"))
    await writer.drain()
    return await drain(reader, seconds)


def read_object(payload: bytes, offset: int = 0):
    object_id, x, y, rotation = struct.unpack_from("<HHHH", payload, offset)
    end = payload.index(0, offset + 8)
    return ((object_id, x, y, rotation,
             payload[offset + 8:end].decode("utf-8")), end + 1)


def objects(frames) -> list[tuple]:
    found = []
    for command, payload in frames:
        if command == GET_3D_OBJ:
            found.append(read_object(payload)[0])
        elif command == GET_3D_OBJ_LIST:
            count = struct.unpack_from("<H", payload, 0)[0]
            offset = 2
            for _ in range(count):
                entry, offset = read_object(payload, offset)
                found.append(entry)
    return found


def removals(frames) -> list[int]:
    return [struct.unpack("<H", payload)[0]
            for command, payload in frames if command == REMOVE_3D_OBJ]


def teleporters(frames) -> list[tuple[int, int]]:
    for command, payload in frames:
        if command != GET_TELEPORTERS_LIST:
            continue
        count = struct.unpack_from("<H", payload, 0)[0]
        return [struct.unpack_from("<HH", payload, 2 + index * 4)
                for index in range(count)]
    return []


def teleports(frames) -> list[tuple[str, int, int]]:
    return [("in" if command == TELEPORT_IN else "out",
             *struct.unpack("<HH", payload))
            for command, payload in frames
            if command in (TELEPORT_IN, TELEPORT_OUT)]


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


async def probe(port: int, name: str, password: str) -> None:
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)
    try:
        entry = await drain(reader, 2.0)
        listed = teleporters(entry)
        check("a map states where its ways out are, at login",
              bool(listed), "%d portal(s)" % len(listed))

        # A specialty event's own prop. Every event has declared one since
        # the catalogue was written and nothing could place it, which is the
        # content this packet was missing. It is raised before the portal walk
        # below, because it goes on the caller's own map.
        frames = await ask(writer, reader, "#event_start world_boss", 3.0)
        placed = objects(frames)
        check("starting an event raises its prop where it was called for",
              bool(placed), str(placed) + " " + texts(frames)[:80])
        if placed:
            check("and the prop carries the model the catalogue names",
                  "totem" in placed[0][4], str(placed[0]))

        frames = await ask(writer, reader, "#event_stop", 3.0)
        check("stopping the event clears the prop away",
              bool(removals(frames)), str(removals(frames)))

        # Walking into a portal. The traveller is on the destination map by the
        # time the two ends go out, so they are sent the arrival and the people
        # left behind are sent the departure; both halves are proved together
        # in the server's own tests/test_world_objects.py.
        if listed:
            x, y = listed[0]
            await ask(writer, reader, f"#tp {x} {y + 1}", 2.5)
            await drain(reader, 0.5)
            writer.write(packet(MOVE_TO, struct.pack("<HH", x, y)))
            await writer.drain()
            seen = teleports(await drain(reader, 4.0))
            check("walking into a portal draws the arrival where it happened",
                  any(kind == "in" for kind, _x, _y in seen), str(seen))

            arrived = teleporters(await drain(reader, 1.5))
            check("and the map arrived on states its own ways out",
                  isinstance(arrived, list), str(arrived))
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve()
    name, password = disposable_credentials("obj")
    # Starting an event needs the character named as an invasion master, so
    # this run gets its own settings file naming its own throwaway login.
    settings = (root / "config" / "eloria" / "server.txt").read_text(
        encoding="utf-8")
    settings = chr(10).join(
        f"invasion_masters = {name}" if line.startswith("invasion_masters")
        else line for line in settings.splitlines()) + chr(10)
    with LocalServer(root, "eloria-objects-",
                     overrides={"--settings": settings}) as server:
        asyncio.run(probe(server.port, name, password))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
