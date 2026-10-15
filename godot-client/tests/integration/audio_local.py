#!/usr/bin/env python3
"""Prove placed sound and map music against the real server.

A recorded gap: `PLAY_SOUND(14)` and `PLAY_MUSIC(54)` were unallocated, so all
of this client's audio was its own answer to state about the player. What was
missing was everything happening to somebody else, and what the map sounds
like.

Two clients log in together, because the rule that keeps this honest is that
the server does not send a sound to the client that caused it - that client
already knows, and would otherwise hear everything twice.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/audio_local.py <server-root>
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

PLAY_SOUND = 14
PLAY_MUSIC = 54
RAW_TEXT = 0

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


def sounds(frames) -> list[tuple[str, int, int, int]]:
    found = []
    for command, payload in frames:
        if command != PLAY_SOUND:
            continue
        x, y, gain = struct.unpack_from("<HHB", payload, 0)
        found.append((payload[5:].split(b"\0", 1)[0].decode("utf-8"),
                      x, y, gain))
    return found


def music(frames) -> list[str]:
    return [payload.split(b"\0", 1)[0].decode("utf-8")
            for command, payload in frames if command == PLAY_MUSIC]


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


async def probe(port: int) -> None:
    first_name, first_password = disposable_credentials("aud1")
    second_name, second_password = disposable_credentials("aud2")
    await create_character(port, first_name, first_password)
    await create_character(port, second_name, second_password)
    reader, writer, _ = await login(port, first_name, first_password)
    other_reader, other_writer, _ = await login(port, second_name, second_password)
    try:
        entry = await drain(reader, 2.0)
        await drain(other_reader, 2.0)
        check("the map states its music at login",
              music(entry) and music(entry)[0] in
              {"settlement", "wilds", "depths"}, str(music(entry)))

        # Stand both clients on a real harvest node and harvest it. Everyone
        # else hears it; the harvester does not, because it already knows.
        moved = await ask(writer, reader, "#tp 686 510", 2.0)
        await ask(other_writer, other_reader, "#tp 686 510", 2.0)
        await drain(reader, 0.5)
        await drain(other_reader, 0.5)
        check("the teleport did not itself make a sound",
              not sounds(moved), str(sounds(moved)))

        # The four_gates Reed node at 686, 510.
        writer.write(packet(HARVEST, struct.pack("<H", 496)))
        await writer.drain()
        mine = await drain(reader, 2.5)
        theirs = await drain(other_reader, 2.5)

        heard = sounds(theirs)
        check("somebody else's harvest is heard, at the node's own tile",
              heard == [("harvest_start", 686, 510, 100)],
              str(heard) + " " + texts(theirs)[:60])
        check("and the harvester is not sent a sound it already answers",
              not sounds(mine), str(sounds(mine)))

        # Changing map restates the music, including to silence.
        crossed = await ask(writer, reader, "#tp 58 64 mirrorhold", 3.0)
        played = music(crossed)
        check("crossing to another map restates its music",
              bool(played), str(played) + " " + texts(crossed)[:60])
    finally:
        await close_client(writer)
        await close_client(other_writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-audio-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
