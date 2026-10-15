#!/usr/bin/env python3
"""Prove world effects against the genuine Eloria server.

`SEND_SPECIAL_EFFECT(79)` had no decoder in the client, so a swarm of bees
interrupting a harvest, a lucky find, or a spell landing all happened with
nothing on screen.

The server fires one of its two harvesting events on roughly one harvest in
125, so this probe harvests a real resource on a real map until one arrives.
Harvesting speed and carry capacity are raised with the development commands
rather than the interval being faked, so what is being read is the genuine
harvest loop.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/special_effects_local.py <server-root>
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
HARVEST = 21

RAW_TEXT = 0
ELORIA_MAP_OBJECTS = 236
ELORIA_HARVEST_STATE = 237
SEND_SPECIAL_EFFECT = 79

MAP_OBJECT_HARVEST = 1
# A level-0 resource, so the harvest interval is short from the first attempt.
PROBE_RESOURCE = "Sunleaf"
HARVEST_SECONDS = 150.0

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


async def drain(reader, seconds: float) -> list[tuple[int, bytes]]:
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


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


def decode_objects(frames) -> list[tuple[int, str]]:
    """Every harvestable object id and label the server listed."""
    objects: list[tuple[int, str]] = []
    for command, payload in frames:
        if command != ELORIA_MAP_OBJECTS:
            continue
        _first, count = struct.unpack_from("<BH", payload)
        offset = 3
        for _row in range(count):
            object_id, kind = struct.unpack_from("<HB", payload, offset)
            offset += 7
            fields = []
            for _text in range(2):
                end = payload.index(0, offset)
                fields.append(payload[offset:end].decode("utf-8"))
                offset = end + 1
            if kind == MAP_OBJECT_HARVEST:
                objects.append((object_id, fields[0]))
    return objects


async def probe(port: int) -> None:
    name, password = disposable_credentials("fx")
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)
    try:
        # The whole login burst carries the map's world objects.
        frames = await drain(reader, 2.5)
        harvestables = decode_objects(frames)
        check("the server listed harvestable objects on this map",
              bool(harvestables), "%d objects" % len(harvestables))
        wanted = [object_id for object_id, label in harvestables
                  if label == PROBE_RESOURCE]
        check("one of them is the level-0 resource this probe harvests",
              bool(wanted), PROBE_RESOURCE)
        if not wanted:
            return

        # Real harvesting, sped up and given room to carry, not faked.
        await ask(writer, reader, "#boost har 90")
        await ask(writer, reader, "#boost phy 1000")
        await ask(writer, reader, "#boost coo 1000")
        writer.write(packet(HARVEST, struct.pack("<H", wanted[0])))
        await writer.drain()

        started = False
        effects: list[bytes] = []
        harvests = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + HARVEST_SECONDS
        while loop.time() < deadline and not effects:
            for command, payload in await drain(reader, 5.0):
                if command == ELORIA_HARVEST_STATE and payload[0]:
                    started = True
                elif command == ELORIA_HARVEST_STATE and not payload[0]:
                    # The server stopped the run; ask again and keep going.
                    writer.write(packet(HARVEST, struct.pack("<H", wanted[0])))
                    await writer.drain()
                elif command in (19, 21):
                    # A harvested item arrives as a full inventory snapshot or
                    # a single-slot update, depending on what changed.
                    harvests += 1
                elif command == SEND_SPECIAL_EFFECT:
                    effects.append(payload)
        check("the server reported harvesting started", started,
              "%d inventory updates" % harvests)
        check("a world effect arrived from the real harvest loop",
              bool(effects), "after %d inventory updates" % harvests)
        if effects:
            check("the effect names an effect id and the actor it happened to",
                  len(effects[0]) in (3, 5)
                  and effects[0][0] in (14, 17)
                  and struct.unpack_from("<H", effects[0], 1)[0] > 0,
                  "effect %d for actor %d" % (
                      effects[0][0],
                      struct.unpack_from("<H", effects[0], 1)[0]))
    finally:
        await close_client(writer)


PROBE_NODE_ID = 9101


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    server_root = Path(sys.argv[1])
    # The shipped four_gates harvest nodes sit in an abandoned coordinate space
    # (recorded as a content defect in Phase 1), so this probe places its own
    # node beside the spawn exactly as the harvesting probe does.
    shipped = (server_root / "config" / "eloria"
               / "harvesting.txt").read_text(encoding="utf-8")
    probe_table = shipped + chr(10) + "node | four_gates | %d | 769 | 480 | %s" % (
        PROBE_NODE_ID, PROBE_RESOURCE) + chr(10)
    with LocalServer(server_root, "eloria-special-effects-",
                     {"--harvesting": probe_table}) as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
