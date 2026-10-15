#!/usr/bin/env python3
"""Prove asking about an item on the ground against the genuine Eloria server.

`LOOK_AT_GROUND_ITEM(24)` had no encoder in the client and no handler in the
server, so a player could see a picture of something lying on the ground and
had no way to learn what it was: the bag packet carries an image id, a
quantity and a slot, and nothing else.

This probe drops a real item, opens the bag the server makes for it, and asks
about the item both as a client that advertises `item_detail_v1` and as one
that advertises nothing.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/ground_item_local.py <server-root>
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
DROP_ITEM = 22
INSPECT_BAG = 25
LOOK_AT_GROUND_ITEM = 24

RAW_TEXT = 0
HERE_YOUR_GROUND_ITEMS = 23
GET_NEW_BAG = 27
INVENTORY_ITEM_TEXT = 20
ELORIA_ITEM_DETAIL = 225

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


async def ask(writer, reader, text: str, seconds: float = 1.5):
    writer.write(packet(RAW_TEXT_C, text.encode("utf-8") + b"\0"))
    await writer.drain()
    return await drain(reader, seconds)


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


async def probe(port: int) -> None:
    name, password = disposable_credentials("bag")
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)
    try:
        await ask(writer, reader, "#clientcaps item_detail_v1")
        granted = texts(await ask(writer, reader, "#give Deep Coal 4"))
        check("the probe has something to drop", "Gave 4 Deep Coal" in granted,
              granted)

        # Drop whatever is in the first inventory slot. Which item that is
        # depends on the starting kit, so nothing below assumes it.
        writer.write(packet(DROP_ITEM, struct.pack("<BI", 0, 1)))
        await writer.drain()
        frames = await drain(reader, 2.0)
        bags = [payload for command, payload in frames if command == GET_NEW_BAG]
        check("dropping an item makes a bag on the ground", bool(bags),
              str([command for command, _ in frames]))
        if not bags:
            return
        bag_id = bags[0][4] if len(bags[0]) > 4 else 0

        writer.write(packet(INSPECT_BAG, bytes((bag_id,))))
        await writer.drain()
        frames = await drain(reader, 2.0)
        contents = [payload for command, payload in frames
                    if command == HERE_YOUR_GROUND_ITEMS]
        check("the bag opens with its contents", bool(contents)
              and contents[0][0] >= 1, str([command for command, _ in frames]))
        if not contents:
            return
        slot = contents[0][7]

        writer.write(packet(LOOK_AT_GROUND_ITEM, bytes((slot,))))
        await writer.drain()
        frames = await drain(reader, 2.0)
        details = [payload for command, payload in frames
                   if command == ELORIA_ITEM_DETAIL]
        # Whatever is lying there, the reply must describe that and not
        # something else: the bag row states the image and the quantity, and
        # the description has to agree with both and add the name.
        bag_image, bag_quantity = struct.unpack_from("<HI", contents[0], 1)
        described_name = (details[0][7:].split(b"\0", 1)[0].decode("utf-8")
                          if details else "")
        check("a capable client is told what is on the ground",
              bool(details) and bool(described_name)
              and struct.unpack_from("<H", details[0])[0] == bag_image,
              "%s for image %d" % (described_name, bag_image))
        check("the reply states the quantity lying there",
              bool(details)
              and struct.unpack_from("<I", details[0], 2)[0] == bag_quantity,
              "bag says %d" % bag_quantity)

        # The same question, asked by a second character that advertises
        # nothing. It drops its own item rather than reaching for this one:
        # the first character is standing on that tile, and the server refuses
        # to walk anyone onto an occupied tile.
        plain_name, plain_password = disposable_credentials("plai")
        await create_character(port, plain_name, plain_password)
        plain_reader, plain_writer, _ = await login(
            port, plain_name, plain_password)
        try:
            await drain(plain_reader, 2.0)
            plain_writer.write(packet(DROP_ITEM, struct.pack("<BI", 0, 1)))
            await plain_writer.drain()
            plain_frames = await drain(plain_reader, 2.0)
            plain_bags = [payload for command, payload in plain_frames
                          if command == GET_NEW_BAG]
            check("the second character drops a bag of its own",
                  bool(plain_bags), str([command for command, _ in plain_frames]))
            if plain_bags:
                plain_bag_id = plain_bags[0][4] if len(plain_bags[0]) > 4 else 0
                plain_writer.write(packet(INSPECT_BAG, bytes((plain_bag_id,))))
                await plain_writer.drain()
                plain_contents = [payload for command, payload
                                  in await drain(plain_reader, 3.0)
                                  if command == HERE_YOUR_GROUND_ITEMS]
                check("its bag opens", bool(plain_contents),
                      "bag %d" % plain_bag_id)
                if plain_contents:
                    plain_writer.write(packet(
                        LOOK_AT_GROUND_ITEM, bytes((plain_contents[0][7],))))
                    await plain_writer.drain()
                    plain_frames = await drain(plain_reader, 2.0)
                    check("a plain client is told in the legacy description"
                          " packet",
                          any(command == INVENTORY_ITEM_TEXT
                              for command, _ in plain_frames)
                          and not any(command == ELORIA_ITEM_DETAIL
                                      for command, _ in plain_frames),
                          str([command for command, _ in plain_frames]))
        finally:
            await close_client(plain_writer)

        await drain(reader, 1.0)
        writer.write(packet(LOOK_AT_GROUND_ITEM, bytes((200,))))
        await writer.drain()
        frames = await drain(reader, 1.0)
        check("a slot that is not in the bag is answered with nothing",
              not frames, str([command for command, _ in frames]))
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-ground-item-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
