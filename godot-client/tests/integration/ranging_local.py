#!/usr/bin/env python3
"""Prove ranged combat's missile packets against the genuine Eloria server.

`MISSILE_AIM_A_AT_B(84)` and `MISSILE_FIRE_A_TO_B(86)` were undecoded, so a
ranged fight was two actors standing still while damage numbers appeared -
nothing was ever drawn between them.

This probe equips a real bow and arrows from the shipped catalog, walks far
enough away from a real creature for the server to allow ranging, attacks it,
and reads the aim and the shot off the wire.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/ranging_local.py <server-root>
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
MOVE_INVENTORY_ITEM = 20
ATTACK_SOMEONE = 40

RAW_TEXT = 0
ADD_NEW_ENHANCED_ACTOR = 51
ADD_NEW_ACTOR = 1
ADD_NEW_ACTOR_EXTENDED = 247
HERE_YOUR_INVENTORY = 19
MISSILE_AIM_A_AT_B = 84
MISSILE_AIM_A_AT_XYZ = 85
MISSILE_FIRE_A_TO_XYZ = 87
FIRE_MISSILE_AT_OBJECT = 51
MISSILE_FIRE_A_TO_B = 86

BOW = "Hunting Bow"
AMMUNITION = "Arrow"
# The server refuses to range a target closer than this.
MIN_RANGING_DISTANCE = 4

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


def creatures(frames) -> list[tuple[int, int, int]]:
    """Every non-player actor the server put on screen: id, x, y."""
    found: list[tuple[int, int, int]] = []
    for command, payload in frames:
        if command == ADD_NEW_ENHANCED_ACTOR:
            actor_id, x, y = struct.unpack_from("<HHH", payload)
            kind = payload[27]
            if kind != 1:
                found.append((actor_id, x & 0x7FF, y & 0x7FF))
        elif command in (ADD_NEW_ACTOR, ADD_NEW_ACTOR_EXTENDED):
            actor_id, x, y = struct.unpack_from("<HHH", payload)
            found.append((actor_id, x & 0x7FF, y & 0x7FF))
    return found


def inventory_slots(frames) -> dict[int, int]:
    """Image id per inventory slot, from the authoritative snapshot."""
    for command, payload in frames:
        if command != HERE_YOUR_INVENTORY:
            continue
        slots: dict[int, int] = {}
        count = payload[0]
        for index in range(count):
            offset = 1 + index * 8
            image_id = struct.unpack_from("<H", payload, offset)[0]
            slots[payload[offset + 6]] = image_id
        return slots
    return {}


async def probe(port: int) -> None:
    name, password = disposable_credentials("bow")
    await create_character(port, name, password)
    reader, writer, actor_id = await login(port, name, password)
    try:
        await drain(reader, 2.5)
        # The player spawns away from the wildlife, and a creature is only
        # sent once it is within sight. Walk to one the shipped spawn table
        # names rather than waiting for one to wander past.
        burst = await ask(writer, reader, "#tp 160 168", 3.0)
        targets = creatures(burst)
        check("the server put creatures on the map", bool(targets),
              "%d actors" % len(targets))
        if not targets:
            return

        # Equip a real bow and real arrows from the shipped catalog.
        await ask(writer, reader, f"#give {BOW} 1")
        granted = await ask(writer, reader, f"#give {AMMUNITION} 20")
        slots = inventory_slots(granted)
        bow_slot = next((slot for slot, image in slots.items() if image == 44), -1)
        arrow_slot = next((slot for slot, image in slots.items() if image == 55), -1)
        check("both are in the backpack", bow_slot >= 0 and arrow_slot >= 0,
              "bow slot %d, arrow slot %d" % (bow_slot, arrow_slot))
        if bow_slot < 0 or arrow_slot < 0:
            return
        # Equipment slots are 36 upwards; the server validates the fit.
        writer.write(packet(MOVE_INVENTORY_ITEM, bytes((bow_slot, 36))))
        writer.write(packet(MOVE_INVENTORY_ITEM, bytes((arrow_slot, 37))))
        await writer.drain()
        equipped = await drain(reader, 2.0)
        check("the server accepted the loadout",
              not any("cannot" in line.casefold()
                      for line in texts(equipped).split(" | ")),
              texts(equipped)[:120] or "no refusal")

        # Stand far enough away for the server to allow a shot. The creature
        # wanders and may close the distance between the teleport and the
        # attack, so this backs off further and asks again rather than
        # assuming where it is.
        target_id, target_x, target_y = targets[0]
        aims: list[bytes] = []
        shots: list[bytes] = []
        for attempt in range(4):
            gap = MIN_RANGING_DISTANCE + 3 + attempt * 3
            await ask(writer, reader, f"#tp {target_x + gap} {target_y}", 2.0)
            await drain(reader, 0.5)
            writer.write(packet(ATTACK_SOMEONE, struct.pack("<I", target_id)))
            await writer.drain()
            frames = await drain(reader, 6.0)
            aims = [payload for command, payload in frames
                    if command == MISSILE_AIM_A_AT_B]
            shots = [payload for command, payload in frames
                     if command == MISSILE_FIRE_A_TO_B]
            strays = [payload for command, payload in frames
                      if command == MISSILE_FIRE_A_TO_XYZ]
            if aims and (shots or strays):
                break
        check("the server states an aim before the shot", bool(aims),
              str(sorted({command for command, _ in frames})) + " "
              + texts(frames)[:140])
        check("and states the shot itself", bool(shots or strays),
              "%d aim(s), %d hit(s), %d stray(s)"
              % (len(aims), len(shots), len(strays)))
        # A miss is drawn as an arrow landing on the ground rather than as a
        # shot at the target it missed. Which of the two arrives is a dice
        # roll, so both are accepted here and each is checked for what it is.
        if strays:
            stray_source, stray_x, stray_y = struct.unpack_from("<HHH", strays[0])
            check("a miss names the shooter and where the arrow landed",
                  stray_source == actor_id
                  and (stray_x, stray_y) != (target_x, target_y),
                  "%d -> (%d, %d), target was (%d, %d)"
                  % (stray_source, stray_x, stray_y, target_x, target_y))
        if aims and shots:
            aim_source, aim_target = struct.unpack_from("<HH", aims[0])
            fire_source, fire_target = struct.unpack_from("<HH", shots[0])
            check("both name the shooter and the target",
                  aim_source == actor_id and aim_target == target_id
                  and fire_source == actor_id and fire_target == target_id,
                  "aim %d->%d, fire %d->%d" % (aim_source, aim_target,
                                               fire_source, fire_target))
        # Shooting at a place rather than at somebody: the arrow is spent
        # and lands where it was aimed, and nothing is earned.
        await ask(writer, reader, "#tp 160 168", 2.0)
        await drain(reader, 0.5)
        writer.write(packet(FIRE_MISSILE_AT_OBJECT,
                            struct.pack("<HH", 160, 168 + 8)))
        await writer.drain()
        frames = await drain(reader, 3.0)
        ground_aims = [payload for command, payload in frames
                       if command == MISSILE_AIM_A_AT_XYZ]
        ground_shots = [payload for command, payload in frames
                        if command == MISSILE_FIRE_A_TO_XYZ]
        check("a shot at a place is aimed and loosed like any other",
              bool(ground_aims) and bool(ground_shots),
              "%d aim(s), %d shot(s)" % (len(ground_aims), len(ground_shots)))
        if ground_aims and ground_shots:
            aimed = struct.unpack_from("<HHH", ground_aims[0])
            loosed = struct.unpack_from("<HHH", ground_shots[0])
            check("both name the shooter and the tile that was aimed at",
                  aimed == (actor_id, 160, 176) and loosed == aimed,
                  "aim %s, shot %s" % (str(aimed), str(loosed)))

        writer.write(packet(FIRE_MISSILE_AT_OBJECT, struct.pack("<HH", 160, 169)))
        await writer.drain()
        frames = await drain(reader, 2.0)
        check("a place too close is refused the way a target is",
              not any(command == MISSILE_FIRE_A_TO_XYZ
                      for command, _payload in frames)
              and "too close" in texts(frames),
              texts(frames)[:90])
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-ranging-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
