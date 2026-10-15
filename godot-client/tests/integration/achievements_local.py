#!/usr/bin/env python3
"""Prove the achievement catalogue and titles against the genuine Eloria server.

The server kept nineteen tallies and had one achievement behind them. It now
carries an authored catalogue in `config/eloria/achievements.txt`, publishes it
on `ELORIA_ACHIEVEMENTS_CATALOG(219)` with this character's progress on it, and
puts the title a player wears on `ELORIA_ACTOR_TITLES(211)`.

This drives the real server and checks the parts a unit test cannot: that the
catalogue arrives unasked at login for a client that declared the capability
and not for one that did not, that walking to a map the character has never
seen unlocks an exploration achievement and restates the catalogue, and that a
title the character has not earned is refused.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/achievements_local.py --server-root <path>
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (  # noqa: E402
    LocalServer, close_client, create_character, disposable_credentials,
    login, packet, read_packet)

RAW_TEXT_C = 0
RAW_TEXT = 0
ELORIA_ACTOR_TITLES = 211
ELORIA_ACHIEVEMENTS_CATALOG = 219

CAPABILITIES = "achievements_catalog_v1,actor_titles_v1"

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


async def ask(writer, reader, text: str, seconds: float = 2.0):
    writer.write(packet(RAW_TEXT_C, text.encode("utf-8") + b"\0"))
    await writer.drain()
    return await drain(reader, seconds)


def decode_catalog(payload: bytes) -> tuple[str, list[dict]]:
    """Reference decoder, written from the wire rather than from the encoder."""
    worn, _, rest = payload.partition(b"\0")
    count = struct.unpack_from("<H", rest, 0)[0]
    offset = 2
    entries: list[dict] = []
    for _index in range(count):
        progress, threshold, done = struct.unpack_from("<IIB", rest, offset)
        offset += 9
        fields: list[str] = []
        for _field in range(5):
            end = rest.index(0, offset)
            fields.append(rest[offset:end].decode("utf-8"))
            offset = end + 1
        entries.append({"key": fields[0], "name": fields[1],
                        "category": fields[2], "description": fields[3],
                        "title": fields[4], "progress": progress,
                        "threshold": threshold, "done": bool(done)})
    assert offset == len(rest), "the catalogue packet has trailing bytes"
    return worn.decode("utf-8"), entries


def decode_titles(payload: bytes) -> list[tuple[int, str]]:
    count = struct.unpack_from("<H", payload, 0)[0]
    offset, rows = 2, []
    for _index in range(count):
        actor_id = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        end = payload.index(0, offset)
        rows.append((actor_id, payload[offset:end].decode("utf-8")))
        offset = end + 1
    assert offset == len(payload), "the titles packet has trailing bytes"
    return rows


def catalogues(frames) -> list[tuple[str, list[dict]]]:
    return [decode_catalog(payload) for command, payload in frames
            if command == ELORIA_ACHIEVEMENTS_CATALOG]


def texts(frames) -> str:
    """Every chat line, with the colour markers taken out.

    A coloured line carries its colour as one raw byte above the ASCII range
    in front of the text, which is not UTF-8 and is not part of what was said.
    The stock client strips it and so does this, or the unlock announcement -
    which is green, and so carries one - reads as a replacement character.
    """
    lines = []
    for command, payload in frames:
        if command != RAW_TEXT:
            continue
        body = payload[1:].split(b"\0", 1)[0]
        lines.append(bytes(byte for byte in body if byte < 128).decode(
            "utf-8", "replace"))
    return " | ".join(lines)


def entry_of(entries: list[dict], key: str) -> dict:
    return next((row for row in entries if row["key"] == key), {})


async def probe(port: int, name: str, password: str) -> None:
    await create_character(port, name, password)
    reader, writer, _actor_id = await login(port, name, password)
    try:
        # A client that has said nothing is sent nothing. The whole extension
        # convention rests on this, and it is the half a unit test proves by
        # inspecting a capability set rather than by watching a socket.
        quiet = await drain(reader, 1.0)
        check("a client that has not advertised the capability is sent no"
              " catalogue at login",
              not catalogues(quiet), f"{len(catalogues(quiet))} frames")

        frames = await ask(writer, reader, "#clientcaps " + CAPABILITIES)
        stated = catalogues(frames)
        check("declaring the capability publishes the catalogue at once",
              len(stated) == 1, f"{len(stated)} frames")
        if not stated:
            return
        worn, entries = stated[0]
        check("a fresh character wears no title", worn == "", repr(worn))
        check("the catalogue is the authored one, not a placeholder ladder",
              len(entries) > 60, f"{len(entries)} entries")
        check("every entry explains itself, so the list can be browsed before"
              " any of it is earned",
              all(row["name"] and row["description"] and row["category"]
                  for row in entries))
        check("and every threshold is a real target",
              all(row["threshold"] >= 1 for row in entries))
        check("the catalogue is divided into pages a window can draw",
              len({row["category"] for row in entries}) >= 5,
              str(sorted({row["category"] for row in entries})))
        check("some of them grant a title",
              len({row["title"] for row in entries if row["title"]}) > 15,
              str(len({row["title"] for row in entries if row["title"]})))

        # Exploration. The character's own map was recorded at login, so this
        # stands at one of two before going anywhere.
        gates = entry_of(entries, "out_of_the_gates")
        check("an exploration achievement is on the catalogue, part done",
              gates.get("progress") == 1 and gates.get("threshold") == 2
              and not gates.get("done"), str(gates))

        # Walking somewhere new. This is the whole point of the probe: the
        # hook is in `World.change_map`, and no unit test proves the arrival
        # actually reaches a socket.
        frames = await ask(writer, reader, "#tp 58 58 mirrorhold", 3.0)
        line = texts(frames)
        check("the arrival happened", "Mirrorhold" in line, line.strip()[:100])
        check("the unlock is announced in words",
              "Achievement unlocked: Out of the Gates" in line,
              line.strip()[:160])
        arrived = catalogues(frames)
        check("and the catalogue is restated with it", bool(arrived),
              f"{len(arrived)} frames")
        if arrived:
            _worn, after = arrived[-1]
            unlocked = entry_of(after, "out_of_the_gates")
            check("the exploration achievement is now finished",
                  unlocked.get("done") and unlocked.get("progress") == 2,
                  str(unlocked))
            check("and the region rollup counted the region it was in",
                  entry_of(after, "every_region").get("progress") == 2,
                  str(entry_of(after, "every_region")))

        # Titles. Only an earned one may be worn: a title anybody could type
        # would be worth nothing at all, which is why the check is the
        # server's and not the window's.
        line = texts(await ask(writer, reader, "#title the Culler"))
        check("a title that has not been earned is refused",
              "not earned" in line, line.strip()[:120])
        line = texts(await ask(writer, reader, "#titles"))
        check("and the player is told they have none yet",
              "earned no titles" in line, line.strip()[:120])

        # The text catalogue, for a client that cannot decode the packet. This
        # login declared the capability, so it gets the packet instead - which
        # is the branch worth proving, because getting both would be the bug.
        frames = await ask(writer, reader, "#achievements")
        check("#achievements answers a declared client with the packet, not"
              " with a wall of chat",
              len(catalogues(frames)) == 1 and "Achievements:" not in texts(frames),
              f"{len(catalogues(frames))} frames")
    finally:
        await close_client(writer)


async def probe_chatty(port: int, name: str, password: str) -> None:
    """The other branch: a client that declared nothing reads it as text."""
    await create_character(port, name, password)
    reader, writer, _actor_id = await login(port, name, password)
    try:
        await drain(reader, 1.0)
        frames = await ask(writer, reader, "#achievements", 3.0)
        line = texts(frames)
        check("a client with no capability gets the catalogue as chat",
              "Achievements: 0 of " in line, line.strip()[:80])
        check("grouped by category and marked",
              "[ ] First Blood" in line, line.strip()[:200])
        check("and no catalogue packet is sent to it",
              not catalogues(frames), f"{len(catalogues(frames))} frames")
    finally:
        await close_client(writer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    root = parser.parse_args().server_root.resolve()
    name, password = disposable_credentials("achv")
    chatty_name, chatty_password = disposable_credentials("chat")
    with LocalServer(root, "eloria-achievements-") as server:
        asyncio.run(probe(server.port, name, password))
        asyncio.run(probe_chatty(server.port, chatty_name, chatty_password))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
