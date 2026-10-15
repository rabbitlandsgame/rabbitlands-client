#!/usr/bin/env python3
"""Prove emotes, actor animations and item-on-item against the real server.

Three recorded gaps, one mechanism. `ADD_ACTOR_ANIMATION(89)` was unallocated,
so nothing could ask an actor to play anything that was not already an actor
command. `DO_EMOTE(70)` and `ITEM_ON_ITEM(42)` had no dispatch branch and no
concept behind them.

Two clients log in together, because the point of an emote is that somebody
else sees it.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/emotes_local.py <server-root>
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
ITEM_ON_ITEM = 42
DO_EMOTE = 70

RAW_TEXT = 0
INVENTORY_ITEM_TEXT = 20
HERE_YOUR_INVENTORY = 19
ADD_ACTOR_ANIMATION = 89

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


def animations(frames) -> list[tuple[int, str]]:
    return [(struct.unpack_from("<H", payload)[0],
             payload[2:].split(b"\0", 1)[0].decode("utf-8"))
            for command, payload in frames if command == ADD_ACTOR_ANIMATION]


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


def descriptions(frames) -> str:
    """Item text carries a leading colour byte, like every other
    coloured line the server sends."""
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames
                      if command == INVENTORY_ITEM_TEXT)


def slots_of(frames) -> list[str]:
    """The server's authoritative inventory, as a slot-indexed name list."""
    for command, payload in frames:
        if command != HERE_YOUR_INVENTORY:
            continue
        count = payload[0]
        found = [""] * 44
        for index in range(count):
            base = 1 + index * 8
            quantity = struct.unpack_from("<I", payload, base + 2)[0]
            slot = payload[base + 6]
            if quantity:
                found[slot] = str(struct.unpack_from("<H", payload, base)[0])
        return found
    return []


async def probe(port: int) -> None:
    actor_name, actor_password = disposable_credentials("emot")
    watch_name, watch_password = disposable_credentials("wtch")
    await create_character(port, actor_name, actor_password)
    await create_character(port, watch_name, watch_password)
    reader, writer, actor_id = await login(port, actor_name, actor_password)
    watch_reader, watch_writer, _ = await login(port, watch_name, watch_password)
    try:
        await drain(reader, 1.0)
        await drain(watch_reader, 1.0)

        # The emote packet, not the chat command: this is the wire the client
        # actually uses.
        writer.write(packet(DO_EMOTE, b"bow\0"))
        await writer.drain()
        mine = await drain(reader, 2.0)
        theirs = await drain(watch_reader, 2.0)

        check("the emote packet animates the actor who sent it",
              animations(mine) == [(actor_id, "emote_bow")], str(animations(mine)))
        check("and everyone else on the map sees the same animation",
              animations(theirs) == [(actor_id, "emote_bow")],
              str(animations(theirs)))
        check("the player is told what they did",
              "You bow." in texts(mine), texts(mine)[:60])
        check("and everyone else is told who did it",
              " bows." in texts(theirs) and "You bow." not in texts(theirs),
              texts(theirs)[:60])

        writer.write(packet(DO_EMOTE, b"moonwalk\0"))
        await writer.drain()
        frames = await drain(reader, 2.0)
        check("an emote the server does not have lists the ones it does,"
              " rather than failing silently",
              not animations(frames) and "moonwalk" in texts(frames)
              and "bow" in texts(frames), texts(frames)[:90])

        # Item on item. The Torch is the one recipe on this profile that
        # takes exactly two items, so it is what "put this on that" means.
        for grant in ("Wood Plank 4", "Cloth Roll 4", "Hatchet 1", "Bread 4"):
            await ask(writer, reader, "#give " + grant, 1.0)

        # Ask the server what is in each slot rather than assuming an order.
        positions: dict[str, int] = {}
        for slot in range(16):
            writer.write(packet(19, bytes((slot,))))
            await writer.drain()
            described = descriptions(await drain(reader, 0.6)).strip()
            for wanted in ("Wood Plank", "Cloth Roll", "Bread", "Hatchet"):
                if described.startswith(wanted):
                    positions.setdefault(wanted, slot)
        check("the server names the item in each slot it filled",
              {"Wood Plank", "Cloth Roll", "Bread"} <= set(positions),
              str(positions))
        if {"Wood Plank", "Cloth Roll", "Bread"} <= set(positions):
            writer.write(packet(ITEM_ON_ITEM, bytes(
                (positions["Wood Plank"], positions["Bread"]))))
            await writer.drain()
            frames = await drain(reader, 2.0)
            check("two items no recipe takes together come to nothing, and"
                  " say so",
                  "Nothing comes of" in descriptions(frames),
                  descriptions(frames)[:90])

            writer.write(packet(ITEM_ON_ITEM, bytes(
                (positions["Wood Plank"], positions["Cloth Roll"]))))
            await writer.drain()
            frames = await drain(reader, 5.0)
            said = descriptions(frames)
            check("putting the plank on the cloth roll mixes the recipe that"
                  " takes both",
                  "Torch" in said, said[:110])

            writer.write(packet(ITEM_ON_ITEM, bytes(
                (positions["Bread"], positions["Bread"]))))
            await writer.drain()
            frames = await drain(reader, 1.5)
            check("an item put onto itself is refused",
                  "different item" in descriptions(frames),
                  descriptions(frames)[:80])
    finally:
        await close_client(writer)
        await close_client(watch_writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-emotes-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
