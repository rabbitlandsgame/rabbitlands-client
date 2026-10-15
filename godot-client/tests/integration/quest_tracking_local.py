#!/usr/bin/env python3
"""Prove quest tracking against the real server.

A recorded gap: `NEXT_NPC_MESSAGE_IS_QUEST(92)`, `HERE_IS_QUEST_ID(93)`,
`QUEST_FINISHED(94)` and the `WHAT_QUEST_IS_THIS_ID(63)` request were all
unallocated. The journal already carried what a player was doing, but nothing
said which quest a line of dialogue belonged to, so quest dialogue could not be
told from small talk.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/quest_tracking_local.py <server-root>
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
TOUCH_PLAYER = 28
WHAT_QUEST_IS_THIS_ID = 63

RAW_TEXT = 0
NPC_TEXT = 30
ADD_NEW_ACTOR = 1
ADD_NEW_ENHANCED_ACTOR = 51
ADD_NEW_ACTOR_EXTENDED = 247
NEXT_NPC_MESSAGE_IS_QUEST = 92
HERE_IS_QUEST_ID = 93
QUEST_FINISHED = 94

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


def quest_ids(frames) -> list[int]:
    return [struct.unpack("<H", payload)[0]
            for command, payload in frames if command == HERE_IS_QUEST_ID]


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


async def probe(port: int) -> None:
    name, password = disposable_credentials("qst")
    await create_character(port, name, password)
    reader, writer, _actor_id = await login(port, name, password)
    try:
        await drain(reader, 2.0)

        # Asking about a quest by id, which had no command at all before.
        writer.write(packet(WHAT_QUEST_IS_THIS_ID, struct.pack("<H", 1)))
        await writer.drain()
        answered = await drain(reader, 2.0)
        check("asking what a quest is answers with its id and its name",
              quest_ids(answered) == [1] and "cout" in texts(answered),
              str(quest_ids(answered)) + " " + texts(answered)[:70])

        writer.write(packet(WHAT_QUEST_IS_THIS_ID, struct.pack("<H", 4242)))
        await writer.drain()
        unknown = await drain(reader, 2.0)
        check("an id this world does not know still gets a reply",
              quest_ids(unknown) == [4242] and "not a quest" in texts(unknown),
              texts(unknown)[:70])

        # Small talk is not flagged. The tutorial NPC on the starting map
        # answers before the player is in any quest.
        await ask(writer, reader, "#tp 30 30", 2.0)
        plain = await drain(reader, 1.0)
        check("nothing is flagged before the player is in a quest",
              not any(command == NEXT_NPC_MESSAGE_IS_QUEST
                      for command, _payload in plain))

        # Toran on Four Gates posts daily work. Everything he says is about
        # the assignment, which is a quest, so it is flagged as one.
        toran = None
        # The teleport is sent twice: the first arrival puts the player on the
        # map, and the second sends the actor list from a standing start, which
        # is where his id is read from.
        await ask(writer, reader, "#tp 704 721", 2.0)
        frames = await ask(writer, reader, "#tp 704 721", 2.5)
        for command, payload in frames:
            if command in (ADD_NEW_ACTOR, ADD_NEW_ENHANCED_ACTOR,
                           ADD_NEW_ACTOR_EXTENDED) and b"Toran" in payload:
                toran = struct.unpack_from("<H", payload, 0)[0]
        check("the daily-work NPC is on the map", toran is not None,
              str(toran))
        if toran is None:
            return
        writer.write(packet(TOUCH_PLAYER, struct.pack("<I", toran)))
        await writer.drain()
        frames = await drain(reader, 2.5)
        flagged = [index for index, (command, _payload) in enumerate(frames)
                   if command == NEXT_NPC_MESSAGE_IS_QUEST]
        said = [index for index, (command, _payload) in enumerate(frames)
                if command == NPC_TEXT]
        if flagged and said:
            check("the flag comes before the dialogue it describes",
                  flagged[0] < said[0], "%d then %d" % (flagged[0], said[0]))
            check("and names the quest the dialogue belongs to",
                  quest_ids(frames) and quest_ids(frames)[0] == 4,
                  str(quest_ids(frames)))
        else:
            check("the daily-work NPC flags its dialogue as a quest", False,
                  "no flag in " + str(sorted({c for c, _ in frames})) + " "
                  + texts(frames)[:110])
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-quests-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
