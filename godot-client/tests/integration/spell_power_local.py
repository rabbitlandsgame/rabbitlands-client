#!/usr/bin/env python3
"""Prove spell power against the genuine Eloria server.

Power is entirely the server's: what a cast will use, and what the character's
Magic level and nexus allow. The only way to read either was `#sp`, which
answers in chat text - so a client had to either parse the chat stream or keep
its own copy of the progression rules. `ELORIA_SPELL_POWER(231)` states both,
and the legacy cast frame takes an optional trailing power byte the client now
sends.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/spell_power_local.py <server-root>
"""

from __future__ import annotations

import asyncio
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (  # noqa: E402
    LocalServer, close_client, create_character, disposable_credentials,
    login, packet, read_packet)

RAW_TEXT_C = 0
CAST_SPELL = 39

RAW_TEXT = 0
GET_ACTIVE_SPELL = 44
SPELL_CAST = 70
ELORIA_SPELL_POWER = 231

# The sigil sequence the client's own catalog lists for Shield: only its
# name on the wire now, since families are learned from tomes.
SHIELD_SIGILS = (19, 15, 21)

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


def decode_powers(payload: bytes) -> dict[str, tuple[int, int]]:
    count = struct.unpack_from("<H", payload)[0]
    offset, rows = 2, {}
    for _ in range(count):
        preferred, limit = struct.unpack_from("<BB", payload, offset)
        offset += 2
        end = payload.index(0, offset)
        rows[payload[offset:end].decode("utf-8")] = (preferred, limit)
        offset = end + 1
    assert offset == len(payload), "no trailing bytes"
    return rows


def powers(frames) -> dict[str, tuple[int, int]]:
    for command, payload in frames:
        if command == ELORIA_SPELL_POWER:
            return decode_powers(payload)
    return {}


async def probe(port: int) -> None:
    name, password = disposable_credentials("powr")
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)
    try:
        stated = powers(await ask(writer, reader, "#clientcaps spell_power_v1"))
        check("a client that advertises nothing is sent no power state",
              not stated, str(stated))

        # The capability only takes effect for state sent after it arrives.
        stated = powers(await ask(writer, reader, "#boost mag 40"))
        check("raising Magic restates what powers are reachable",
              "heal" in stated, str(sorted(stated)[:6]))
        check("an effect the character cannot reach at all is left out",
              "shield" not in stated,
              "shield needs a Magic nexus, which this character has none of")
        without_nexus = stated.get("shield", (0, 0))[1]

        stated = powers(await ask(writer, reader, "#boost magic_nexus 6"))
        check("a nexus raises the stated ceiling rather than the client"
              " deriving it",
              stated.get("shield", (0, 0))[1] > without_nexus,
              "%d -> %s" % (without_nexus, stated.get("shield")))
        ceiling = stated["shield"][1]

        stated = powers(await ask(writer, reader, "#sp shield 2"))
        check("setting a preference restates it",
              stated.get("shield", (0, 0))[0] == 2, str(stated.get("shield")))

        refused = texts(await ask(writer, reader, "#cast shield self"))
        missing = re.search(r"Missing reagents: (.+)$", refused)
        if missing:
            for requirement in missing.group(1).split(", "):
                quantity, _, reagent = requirement.partition(" ")
                await ask(writer, reader, f"#give {reagent} {int(quantity) * 8}")

        # The legacy CAST_SPELL route names a spell by its sigil sequence and
        # then meets the same gate as the spell book: this character has not
        # read the Tome of Shield, so it is refused whatever power is
        # attached. What the cast frame carries is pinned byte for byte in
        # the client's own tests/test_protocol.gd.
        payload = bytes((len(SHIELD_SIGILS),)) + bytes(SHIELD_SIGILS)
        writer.write(packet(CAST_SPELL, payload + bytes((3,))))
        await writer.drain()
        frames = await drain(reader, 3.0)
        refusal = [payload for command, payload in frames
                   if command == SPELL_CAST]
        check("the sigil-sequence route is refused for want of the tome, not of power",
              bool(refusal) and refusal[0][0] == 2,
              str([command for command, _ in frames]))

        over = await ask(writer, reader, "#sp shield %d" % (ceiling + 1))
        check("a preference above the stated ceiling is refused, and the"
              " refusal is not a new state",
              not powers(over) and bool(texts(over)),
              texts(over) or "nothing was said")
        stated = powers(await ask(writer, reader, "#boost mag 40"))
        check("the preference the server kept is the one it stated before",
              stated.get("shield", (0, 0))[0] == 2, str(stated.get("shield")))
    finally:
        await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-spell-power-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
