#!/usr/bin/env python3
"""Harvesting and world-object interaction against a real server.

`HARVEST(21)`, `USE_MAP_OBJECT(16)` and `LOOK_AT_MAP_OBJECT(27)` were enum
values in the client with no encoder, and there was no world-object pick path
at all, so none of the harvestable layer was reachable. The client also had no
way to know which rendered prop was a resource: the legacy client matched
object basenames against a lowercase harvestable list, a lookup that matched
nothing because the packs wrote relative paths.

The server now states which object ids exist on the map and reports harvesting
as explicit state rather than an English phrase in the chat stream. This drives
all of that against the genuine server, including the stop-on-move behaviour.

The harvest node is supplied by a probe-only harvesting table placed beside the
player. The shipped four_gates nodes are in a stale coordinate space - see the
finding recorded in TRACEABILITY.md - so depending on them here would test the
content bug rather than the mechanism.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (LocalServer, clean_text, close_client,
                          create_character, disposable_credentials, login,
                          packet, read_packet)

RAW_TEXT = 0
MOVE_TO = 1
USE_MAP_OBJECT = 16
HARVEST = 21
LOOK_AT_MAP_OBJECT = 27
HERE_YOUR_INVENTORY = 19
ELORIA_MAP_OBJECTS = 236
ELORIA_HARVEST_STATE = 237
MAP_OBJECT_HARVEST = 1
MAP_OBJECT_INTERACTIVE = 2

PROBE_NODE_ID = 9001
# "Sunleaf" is one of the shipped Eloria harvest resources, is also a real item
# (which the harvest loop needs before it can put anything in the backpack),
# and requires harvesting level 0 - a fresh character harvests it on the
# four-second base interval rather than the punitive under-level one. Only the
# node's *placement* is probe-specific: it is put on the tile beside the spawn
# point so the run measures the mechanism rather than where the shipped
# content happens to sit.
PROBE_RESOURCE = "Sunleaf"


class FrameLog:
    """Reads every frame continuously into a log.

    A window-based reader is wrong here: once the harvesting level rises the
    yield interval halves repeatedly, and a client that only reads in bursts
    lets the server's write buffer fill until its connection handler blocks in
    drain(). A real client reads every frame, so the harness does too.
    """

    def __init__(self, reader: asyncio.StreamReader):
        self._reader = reader
        self.frames: list[tuple[int, bytes]] = []
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                self.frames.append(await read_packet(self._reader, 60.0))
        except (asyncio.IncompleteReadError, TimeoutError,
                asyncio.CancelledError, ConnectionError):
            pass

    def close(self) -> None:
        self._task.cancel()

    def since(self, mark: int) -> list:
        return self.frames[mark:]

    @property
    def mark(self) -> int:
        return len(self.frames)

    async def wait_for(self, command: int, mark: int, seconds: float,
                       match=None):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while loop.time() < deadline:
            for frame in self.frames[mark:]:
                if frame[0] == command and (match is None or match(frame[1])):
                    return frame
            await asyncio.sleep(0.05)
        return None


def decode_map_objects(payload: bytes) -> tuple[bool, list[dict]]:
    """Decode one chunk. The leading flag says whether it starts a new list."""
    first, count = struct.unpack_from("<BH", payload)
    offset, objects = 3, []
    for _ in range(count):
        object_id, kind, x, y = struct.unpack_from("<HBHH", payload, offset)
        offset += 7
        texts = []
        for _field in range(2):
            end = payload.index(0, offset)
            texts.append(payload[offset:end].decode("utf-8"))
            offset = end + 1
        objects.append({"object_id": object_id, "kind": kind, "x": x, "y": y,
                        "label": texts[0], "detail": texts[1]})
    assert offset == len(payload), "map-object list has trailing bytes"
    return bool(first), objects


def decode_harvest_state(payload: bytes) -> dict:
    active, object_id = struct.unpack_from("<BH", payload)
    resource = payload[3:].split(b"\0", 1)[0].decode("utf-8")
    return {"active": bool(active), "object_id": object_id, "resource": resource}


async def scenario(port: int) -> None:
    name, password = disposable_credentials("Harv")
    await create_character(port, name, password)
    reader, writer, actor_id = await login(port, name, password)
    assert actor_id is not None
    log = FrameLog(reader)
    await asyncio.sleep(1.5)

    # The map's clickable objects arrive at login without being asked for.
    chunks = [decode_map_objects(payload) for command, payload in log.frames
              if command == ELORIA_MAP_OBJECTS]
    assert chunks, "the server published no map objects at login"
    assert chunks[0][0], "the first chunk starts the list"
    assert not any(first for first, _ in chunks[1:]), (
        "only one chunk may start the list")
    objects = [entry for _first, entries in chunks for entry in entries]
    harvest_nodes = [entry for entry in objects
                     if entry["kind"] == MAP_OBJECT_HARVEST]
    interactives = [entry for entry in objects
                    if entry["kind"] == MAP_OBJECT_INTERACTIVE]
    probe = next(entry for entry in harvest_nodes
                 if entry["object_id"] == PROBE_NODE_ID)
    assert probe["label"] == PROBE_RESOURCE, probe
    assert probe["detail"].startswith("Harvesting level"), probe
    assert probe["x"] == 769 and probe["y"] == 480, probe
    assert interactives, "the shipped four_gates interactives were not published"

    # Looking at an object answers with a description, not a maps.txt template.
    look_mark = log.mark
    writer.write(packet(LOOK_AT_MAP_OBJECT, struct.pack("<I", PROBE_NODE_ID)))
    await writer.drain()
    assert await log.wait_for(
        RAW_TEXT, look_mark, 4.0,
        lambda payload: PROBE_RESOURCE in clean_text(payload)[1]), (
        "looking at the node returned no description")
    assert not any("maps.txt entry" in clean_text(payload)[1]
                   for command, payload in log.since(look_mark)
                   if command == RAW_TEXT), "the developer template is still being sent"

    # Harvesting: explicit start state, real items, explicit stop state.
    harvest_mark = log.mark
    writer.write(packet(HARVEST, struct.pack("<H", PROBE_NODE_ID)))
    await writer.drain()
    started = await log.wait_for(ELORIA_HARVEST_STATE, harvest_mark, 5.0)
    assert started is not None, "harvesting reported no state at all"
    start_state = decode_harvest_state(started[1])
    assert start_state["active"], start_state
    assert start_state["object_id"] == PROBE_NODE_ID, start_state
    assert start_state["resource"] == PROBE_RESOURCE, start_state
    # The first yield lands one harvest interval after the start; for a level-0
    # resource at level 0 that is the four-second base interval.
    inventory_frame = await log.wait_for(HERE_YOUR_INVENTORY, harvest_mark, 12.0,
                                         lambda payload: payload[0] > 0)
    assert inventory_frame is not None, (
        "harvesting produced no authoritative inventory update")

    # Moving stops the run, and the server says so rather than going quiet.
    move_mark = log.mark
    writer.write(packet(MOVE_TO, struct.pack("<HH", 775, 486)))
    await writer.drain()
    stopped = await log.wait_for(
        ELORIA_HARVEST_STATE, move_mark, 12.0,
        lambda payload: not decode_harvest_state(payload)["active"])
    assert stopped is not None, "moving away produced no explicit harvest stop"

    # Using a real interactive reaches the server's interactive handler.
    storage = next((entry for entry in interactives
                    if entry["label"].casefold() == "storage"), None)
    if storage is not None:
        use_mark = log.mark
        writer.write(packet(USE_MAP_OBJECT, struct.pack("<I", storage["object_id"])))
        await writer.drain()
        used = await log.wait_for(
            RAW_TEXT, use_mark, 5.0,
            lambda payload: ("too far away" in clean_text(payload)[1].casefold()
                             or "cache" in clean_text(payload)[1].casefold()))
        assert used is not None, "using an interactive produced no server answer"

    print("local harvesting integration: PASS")
    print("the map's clickable objects arrive at login, harvest nodes and"
          " interactives together: PASS")
    print("looking at a node returns its resource and requirement: PASS")
    print("harvesting reports explicit start state and yields real items: PASS")
    print("moving away reports an explicit stop rather than going quiet: PASS")
    if storage is not None:
        print("using an interactive reaches the server's handler: PASS")
    print("credentials: REDACTED")
    log.close()
    await close_client(writer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    arguments = parser.parse_args()
    shipped = (arguments.server_root / "config" / "eloria"
               / "harvesting.txt").read_text(encoding="utf-8")
    probe_table = shipped + (
        chr(10) + 'node | four_gates | %d | 769 | 480 | %s'
        % (PROBE_NODE_ID, PROBE_RESOURCE) + chr(10))
    with LocalServer(arguments.server_root, prefix="eloria-harvest-",
                     overrides={"--harvesting": probe_table}) as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
