#!/usr/bin/env python3
"""Prove looking at another player against the genuine Eloria server.

The Godot client had no encoder for `GET_PLAYER_INFO(5)` and no decoder for
`SEND_ACHIEVEMENTS(95)`, so a player could not be inspected at all. The legacy
reply is also unreadable on its own: a "You see: <name>" chat line plus a bare
160-bit set with no actor id and no names, which forces a client to pair the
bitset with a request it remembers making and to carry a second copy of the
server's achievement catalog.

This probe logs in two characters on the same map, has one look at the other,
and checks both replies: `ELORIA_PLAYER_INFO(228)` for the session that
advertises `player_info_v1`, and the legacy pair for the one that does not.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/player_info_local.py <server-root>
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
GET_PLAYER_INFO = 5

RAW_TEXT = 0
SEND_ACHIEVEMENTS = 95
ELORIA_PLAYER_INFO = 228

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


async def say(writer, text: str) -> None:
    writer.write(packet(RAW_TEXT_C, text.encode("utf-8") + b"\0"))
    await writer.drain()


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


def decode_player_info(payload: bytes) -> dict:
    actor_id, count = struct.unpack_from("<HH", payload)
    parts = payload[4:].split(b"\0")
    assert parts[-1] == b"", "every string is NUL terminated"
    fields = [part.decode("utf-8") for part in parts[:-1]]
    assert len(fields) == count + 1, "one name, then one row per achievement"
    return {"actor_id": actor_id, "name": fields[0], "achievements": fields[1:]}


async def probe(port: int) -> None:
    watcher_name, watcher_password = disposable_credentials("look")
    target_name, target_password = disposable_credentials("seen")
    legacy_name, legacy_password = disposable_credentials("lgcy")
    for name, password in ((watcher_name, watcher_password),
                           (target_name, target_password),
                           (legacy_name, legacy_password)):
        await create_character(port, name, password)

    target_reader, target_writer, target_id = await login(
        port, target_name, target_password)
    reader, writer, _ = await login(port, watcher_name, watcher_password)
    legacy_reader, legacy_writer, _ = await login(
        port, legacy_name, legacy_password)
    try:
        await say(writer, "#clientcaps player_info_v1")
        await drain(reader)
        await drain(target_reader)
        await drain(legacy_reader)

        writer.write(packet(GET_PLAYER_INFO, struct.pack("<I", target_id)))
        await writer.drain()
        frames = await drain(reader)
        described = [decode_player_info(payload) for command, payload in frames
                     if command == ELORIA_PLAYER_INFO]
        check("228 answers a client that advertises player_info_v1",
              len(described) == 1, str([command for command, _ in frames]))
        if described:
            check("the reply names the actor the client asked about",
                  described[0]["actor_id"] == target_id
                  and described[0]["name"] == target_name,
                  str(described[0] | {"name": "REDACTED"}))
            check("a fresh character has earned nothing, and is said to have"
                  " earned nothing",
                  described[0]["achievements"] == [], str(described[0]["achievements"]))
        check("the capable client is sent no chat line to parse",
              not texts(frames), texts(frames))

        legacy_writer.write(packet(GET_PLAYER_INFO, struct.pack("<I", target_id)))
        await legacy_writer.drain()
        frames = await drain(legacy_reader)
        commands = [command for command, _ in frames]
        check("a client that advertises nothing still gets the legacy pair",
              ELORIA_PLAYER_INFO not in commands
              and SEND_ACHIEVEMENTS in commands
              and "You see:" in texts(frames), str(commands))
    finally:
        for open_writer in (writer, legacy_writer, target_writer):
            await close_client(open_writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-player-info-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
