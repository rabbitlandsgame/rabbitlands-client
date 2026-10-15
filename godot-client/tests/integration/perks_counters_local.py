#!/usr/bin/env python3
"""Prove perks and activity counters are server state against a real server.

The Godot client used to discover perks by sending `#list_perks` and
pattern-matching the chat reply against a hardcoded 33-name array inside an
eight-second window, and it counted lifetime activity when it *sent* a request
rather than when the server confirmed one - so a refused drop still counted.

This drives the genuine server and checks that the perks and counter packets
arrive unasked at login, that a refused action changes nothing, and that a
confirmed one moves exactly the counter it should.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (LocalServer, close_client, create_character,
                          disposable_credentials, login, packet, read_packet)

DROP_ITEM = 22
HERE_YOUR_INVENTORY = 19
ELORIA_PERKS = 234
ELORIA_ACTIVITY_COUNTERS = 235


def decode_perks(payload: bytes) -> list[tuple[str, str, int, bool]]:
    count = struct.unpack_from("<H", payload)[0]
    offset, rows = 2, []
    for _ in range(count):
        from_gear, pickpoints = struct.unpack_from("<Bh", payload, offset)
        offset += 3
        texts = []
        for _field in range(2):
            end = payload.index(0, offset)
            texts.append(payload[offset:end].decode("utf-8"))
            offset = end + 1
        rows.append((texts[0], texts[1], pickpoints, bool(from_gear)))
    assert offset == len(payload), "perk packet has trailing bytes"
    return rows


def decode_counters(payload: bytes) -> tuple[bool, dict[str, int]]:
    full, count = struct.unpack_from("<BB", payload)
    offset, totals = 2, {}
    for _ in range(count):
        total = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        end = payload.index(0, offset)
        totals[payload[offset:end].decode("utf-8")] = total
        offset = end + 1
    assert offset == len(payload), "counter packet has trailing bytes"
    return bool(full), totals


async def drain(reader: asyncio.StreamReader, seconds: float = 0.6) -> list:
    """Collect everything the server sends for a short window."""
    frames = []
    try:
        while True:
            frames.append(await read_packet(reader, seconds))
    except (asyncio.IncompleteReadError, TimeoutError):
        pass
    return frames


async def scenario(port: int) -> None:
    name, password = disposable_credentials("Cnt")
    await create_character(port, name, password)
    reader, writer, actor_id = await login(port, name, password)
    assert actor_id is not None

    # Both packets arrive at login without the client asking for anything.
    login_frames = await drain(reader, 1.2)
    perk_frames = [payload for command, payload in login_frames
                   if command == ELORIA_PERKS]
    counter_frames = [payload for command, payload in login_frames
                      if command == ELORIA_ACTIVITY_COUNTERS]
    assert perk_frames, "the server did not publish perks at login"
    assert counter_frames, "the server did not publish activity counters at login"
    assert decode_perks(perk_frames[0]) == [], (
        "a fresh character has no perks, and the packet says so explicitly "
        "rather than the client inferring it from silence")
    full, totals = decode_counters(counter_frames[0])
    assert full, "the login counter packet is a complete snapshot"
    assert len(totals) == 17, sorted(totals)
    assert set(totals.values()) == {0}, totals
    for expected in ("Kills", "Deaths", "Breakages", "Crit Fails", "Harvests",
                     "Spells", "Summons", "Drops", "Storage", "Used Items"):
        assert expected in totals, expected

    # A refused action must not move a counter. Dropping from an empty slot is
    # exactly the case the old client counted anyway.
    writer.write(packet(DROP_ITEM, struct.pack("<BI", 35, 1)))
    await writer.drain()
    refused = [payload for command, payload in await drain(reader, 0.8)
               if command == ELORIA_ACTIVITY_COUNTERS]
    assert refused == [], "a refused drop reported a counter change"

    # A confirmed action moves exactly one counter, by the amount actually
    # dropped, and the server states the new total.
    inventory = None
    writer.write(packet(18))  # SEND_MY_INVENTORY
    await writer.drain()
    for command, payload in await drain(reader, 1.0):
        if command == HERE_YOUR_INVENTORY:
            inventory = payload
    assert inventory and inventory[0] > 0, "the fresh character has no items to drop"
    slot = inventory[1 + 6]
    quantity = struct.unpack_from("<I", inventory, 1 + 2)[0]
    writer.write(packet(DROP_ITEM, struct.pack("<BI", slot, quantity)))
    await writer.drain()
    changes = [decode_counters(payload)
               for command, payload in await drain(reader, 1.5)
               if command == ELORIA_ACTIVITY_COUNTERS]
    assert len(changes) == 1, changes
    delta_full, delta_totals = changes[0]
    assert not delta_full, "a single confirmed event is a delta, not a snapshot"
    assert delta_totals == {"Drops": quantity}, delta_totals

    print("local perks and counters integration: PASS")
    print("perks and a 17-category counter snapshot arrive unasked at login: PASS")
    print("a fresh character reports no perks explicitly: PASS")
    print("a refused drop moves no counter: PASS")
    print("a confirmed drop moves only Drops, by the dropped quantity: PASS")
    print("credentials: REDACTED")
    await close_client(writer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    arguments = parser.parse_args()
    with LocalServer(arguments.server_root, prefix="eloria-counters-") as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
