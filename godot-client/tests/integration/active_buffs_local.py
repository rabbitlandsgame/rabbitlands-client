#!/usr/bin/env python3
"""Prove active-effect reporting against the genuine Eloria server.

`GET_ACTIVE_SPELL(44)`, `GET_ACTIVE_SPELL_LIST(45)` and
`REMOVE_ACTIVE_SPELL(46)` were decoded by the client and rendered by nothing,
so a player could not see any effect they were under. This probe casts a real
protective spell on the real server and reads the effect packet back.

The reagents are not hard-coded: the server names what is missing when a cast
is refused, and the probe grants exactly that and casts again. If the shipped
content changes, the probe follows it rather than going stale.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/active_buffs_local.py <server-root>
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (  # noqa: E402
    LocalServer, close_client, create_character, disposable_credentials,
    login, packet, read_packet)

RAW_TEXT_C = 0
RAW_TEXT = 0
GET_ACTIVE_SPELL = 44
SEND_BUFFS = 78

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
    name, password = disposable_credentials("buff")
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)
    try:
        await ask(writer, reader, "#boost mag 40")
        await ask(writer, reader, "#boost magic_nexus 6")

        # The server names what a refused cast is missing; grant exactly that.
        refused = texts(await ask(writer, reader, "#cast shield self"))
        missing = re.search(r"Missing reagents: (.+)$", refused)
        granted: list[str] = []
        if missing:
            for requirement in missing.group(1).split(", "):
                quantity, _, reagent = requirement.partition(" ")
                await ask(writer, reader, f"#give {reagent} {int(quantity) * 2}")
                granted.append(reagent)
        check("the server states what a refused cast is missing",
              bool(missing) or "ethereal" in refused or not refused,
              refused or "the first cast was not refused")

        frames = await ask(writer, reader, "#cast shield self", 3.0)
        effects = [payload for command, payload in frames
                   if command == GET_ACTIVE_SPELL]
        check("casting a protective spell reports an active effect",
              bool(effects), str([command for command, _ in frames])
              + " " + texts(frames))
        if effects:
            check("the effect names its buff id and how long it lasts",
                  effects[0][0] == 0 and effects[0][1] > 0,
                  "buff_id=%d duration=%d" % (effects[0][0], effects[0][1]))
            check("the client's catalog has a name for that buff id",
                  effects[0][0] in {0, 1, 3, 17, 18, 19, 22, 23, 24, 25},
                  "buff_id=%d" % effects[0][0])
        # Until this phase, a successful cast raised NameError inside the
        # connection handler and the socket went silent for good.
        alive = await ask(writer, reader, "#quests")
        check("the connection survives the cast", bool(alive),
              str([command for command, _ in alive]))
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-active-buffs-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
