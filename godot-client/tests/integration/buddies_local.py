#!/usr/bin/env python3
"""Prove the buddy list against the real server.

A recorded gap, and one recorded as a design question rather than a missing
packet: this server had no buddy or friend concept at all. Guilds were the only
social structure, and a guild is not a substitute - a guild is who you belong
with, and a buddy list is who you want to know is around.

Two clients log in and one leaves, because the point of the list is being told
when somebody arrives or goes.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/buddies_local.py <server-root>
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (  # noqa: E402
    LocalServer, close_client, create_character, disposable_credentials,
    login, packet, read_packet)

RAW_TEXT_C = 0
RAW_TEXT = 0
BUDDY_EVENT = 59
EVENTS = ("offline", "online", "added", "removed")

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


def buddy_events(frames) -> list[tuple[str, str]]:
    return [(EVENTS[payload[0]],
             payload[1:].split(b"\0", 1)[0].decode("utf-8"))
            for command, payload in frames if command == BUDDY_EVENT]


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


async def probe(port: int) -> None:
    watcher_name, watcher_password = disposable_credentials("wat")
    friend_name, friend_password = disposable_credentials("frn")
    await create_character(port, watcher_name, watcher_password)
    await create_character(port, friend_name, friend_password)
    reader, writer, _ = await login(port, watcher_name, watcher_password)
    friend_reader, friend_writer, _ = await login(
        port, friend_name, friend_password)
    try:
        entry = await drain(reader, 2.0)
        await drain(friend_reader, 2.0)
        check("a player with an empty list is sent no buddy events at login",
              not buddy_events(entry), str(buddy_events(entry)))

        frames = await ask(writer, reader, f"#add_buddy {friend_name}", 2.0)
        seen = buddy_events(frames)
        check("adding somebody who is here says both that they are listed and"
              " that they are here",
              [event for event, _name in seen] == ["added", "online"],
              str(seen))

        theirs = await drain(friend_reader, 1.0)
        check("and the person added is not told, because a list is a bookmark"
              " rather than a friendship",
              not buddy_events(theirs) and not texts(theirs),
              str(buddy_events(theirs)) + texts(theirs)[:60])

        frames = await ask(writer, reader, f"#add_buddy {friend_name}", 2.0)
        check("adding the same name twice is refused rather than listing it"
              " twice",
              not buddy_events(frames) and "already" in texts(frames),
              texts(frames)[:70])

        frames = await ask(writer, reader, "#buddies", 2.0)
        check("the list can be read back, with who is here",
              friend_name in texts(frames) and "here now" in texts(frames),
              texts(frames)[:90])

        # The whole point: being told when somebody goes.
        await close_client(friend_writer)
        left = await drain(reader, 3.0)
        check("somebody leaving reaches the person watching for them",
              ("offline", friend_name) in buddy_events(left),
              str(buddy_events(left)))

        frames = await ask(writer, reader, f"#remove_buddy {friend_name}", 2.0)
        check("and a name can be taken off again",
              [event for event, _name in buddy_events(frames)] == ["removed"],
              str(buddy_events(frames)))

        frames = await ask(writer, reader, "#buddies", 2.0)
        check("leaving the list empty", "empty" in texts(frames),
              texts(frames)[:60])
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-buddies-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
