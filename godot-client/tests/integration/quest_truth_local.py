#!/usr/bin/env python3
"""Prove the server, not the client, is the record of what a player has done.

Eternal Lands' server tracked quest completions and had no packet to send
them, so the only record a player had was their own chat log - and a reinstall,
a new machine or a lost file took it with them. The forum asked for a
completed-quest list repeatedly and it was blocked on exactly that gap.

This drives the built version against a real server: a capable client is sent
the archive as a packet, a plain one is told the same thing in words, and
asking for the journal answers with both halves - what is open and what is
finished. A fresh character has finished nothing, which is itself the case
worth proving: the server states an empty archive rather than saying nothing,
because silence is what a player cannot tell apart from a broken feature.

The contents of a non-empty archive are pinned against the shipped profile in
the server's own tests/test_quest_archive.py; what needs a real socket is the
wire contract and the fallback, which is what this covers.

Credentials are generated per run, held only in memory, and never printed.

Usage: python tests/integration/quest_truth_local.py <server-root>
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

RAW_TEXT = 0
ELORIA_QUEST_JOURNAL_STATE = 224
ELORIA_QUEST_ARCHIVE_STATE = 241

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


def decode_archive(payload: bytes) -> list[tuple[str, str, str]]:
    count = struct.unpack_from("<H", payload, 0)[0]
    offset = 2
    rows = []
    for _ in range(count):
        fields = []
        for _field in range(3):
            value, _ = payload[offset:].split(b"\0", 1)
            offset += len(value) + 1
            fields.append(value.decode("utf-8"))
        rows.append(tuple(fields))
    return rows


async def say(writer, text: str) -> None:
    writer.write(packet(RAW_TEXT, text.encode("utf-8") + b"\0"))
    await writer.drain()


async def collect(reader, seconds: float = 4.0) -> list[tuple[int, bytes]]:
    """Everything that arrives in a window, so both halves can be checked."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    frames: list[tuple[int, bytes]] = []
    while loop.time() < deadline:
        try:
            frames.append(await read_packet(
                reader, timeout=max(0.1, deadline - loop.time())))
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            break
    return frames


async def drive(server: LocalServer) -> None:
    port = server.port

    name, password = disposable_credentials("QA_Quest_")
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)
    await say(writer, "#clientcaps quest_journal_v1,quest_archive_v1")

    await say(writer, "#quests done")
    frames = await collect(reader)
    archives = [payload for command, payload in frames
                if command == ELORIA_QUEST_ARCHIVE_STATE]
    check("241 answers #quests done for a capable client", bool(archives),
          str(sorted({command for command, _ in frames})))
    if archives:
        check("a character who has finished nothing is told so explicitly",
              decode_archive(archives[0]) == [],
              f"{len(decode_archive(archives[0]))} entries")

    await say(writer, "#quests")
    frames = await collect(reader)
    commands = {command for command, _ in frames}
    check("asking for the journal answers with both halves",
          ELORIA_QUEST_JOURNAL_STATE in commands
          and ELORIA_QUEST_ARCHIVE_STATE in commands,
          str(sorted(commands)))
    await close_client(writer)

    # A client that advertises nothing must still be able to find out.
    # The server caps a username at 20 characters, and the suffix is 8.
    plain_name, plain_password = disposable_credentials("QA_Plain_")
    await create_character(port, plain_name, plain_password)
    reader, writer, _ = await login(port, plain_name, plain_password)
    # Drain the login flood first: the answer is one line among dozens, and a
    # fixed window that starts before login finishes can close before it.
    await collect(reader, 2.0)
    await say(writer, "#quests done")
    frames = await collect(reader)
    said = " ".join(
        payload.decode("utf-8", "replace")
        for command, payload in frames if command == RAW_TEXT)
    check("a plain client is told the same thing in words",
          "not finished any quests" in said, said[-90:])
    check("and is not sent a packet it never claimed to decode",
          ELORIA_QUEST_ARCHIVE_STATE not in {c for c, _ in frames},
          str(sorted({c for c, _ in frames})))
    await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]).resolve(), prefix="eloria-quest-") as server:
        asyncio.run(drive(server))
        failures = [label for label, passed, _ in results if not passed]
        print()
        print(f"{len(results) - len(failures)}/{len(results)} checks passed")
        if failures:
            print("server log tail:")
            print(server.recent_log(25))
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
