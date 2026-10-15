#!/usr/bin/env python3
"""Prove the almanac against the genuine Eloria server.

The game date and the special day in force were both stated only as chat
lines - a `GET_DATE` reply and a broadcast announcement - so a client wanting
to show either had to parse prose off the chat stream. `ELORIA_ALMANAC_STATE`
(238) states them, and carries the catalogue of days the server can roll so
the client ships no copy of its own.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/almanac_local.py <server-root>
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
GET_DATE = 230

RAW_TEXT = 0
ELORIA_ALMANAC_STATE = 238

KINDS = ("ordinary", "good", "neutral", "bad")

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


def decode_almanac(payload: bytes) -> dict:
    day, month, year, kind, bonus = struct.unpack_from("<BBHBH", payload, 0)
    offset = 7

    def text() -> str:
        nonlocal offset
        end = payload.index(0, offset)
        value = payload[offset:end].decode("utf-8")
        offset = end + 1
        return value

    name, description = text(), text()
    effects = [text() for _ in range(payload[offset:offset + 1][0])
               ] if payload[offset] else []
    offset += 1
    if effects:
        pass
    multiplier_count = payload[offset]
    offset += 1
    multipliers = {}
    for _ in range(multiplier_count):
        skill = text()
        multipliers[skill] = struct.unpack_from("<H", payload, offset)[0] / 100
        offset += 2
    catalogue_count = struct.unpack_from("<H", payload, offset)[0]
    offset += 2
    catalogue = []
    for _ in range(catalogue_count):
        entry_kind = KINDS[payload[offset]]
        offset += 1
        catalogue.append((entry_kind, text(), text()))
    assert offset == len(payload), (offset, len(payload))
    return {"date": (day, month, year), "kind": KINDS[kind],
            "bonus": bonus / 100, "name": name, "description": description,
            "effects": effects, "multipliers": multipliers,
            "catalogue": catalogue}


def almanacs(frames) -> list[dict]:
    return [decode_almanac(payload) for command, payload in frames
            if command == ELORIA_ALMANAC_STATE]


def texts(frames) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


async def probe(port: int, name: str, password: str) -> None:
    await create_character(port, name, password)
    reader, writer, _actor_id = await login(port, name, password)
    try:
        # login() consumes the frames it needs; whatever is still queued is
        # the rest of the entry burst.
        login_frames = await drain(reader, 1.0)
        check("a client that has not advertised the capability is sent no"
              " almanac at login",
              not almanacs(login_frames), str(len(almanacs(login_frames))))

        stated = almanacs(await ask(writer, reader, "#clientcaps almanac_v1"))
        check("advertising the capability alone does not conjure one",
              not stated, "the state is sent when there is a reason to")

        # Asking for the date is a reason: the client gets the whole almanac.
        frames = await drain_date(writer, reader)
        stated = almanacs(frames)
        check("asking for the date states the almanac as well as the line",
              len(stated) == 1, str(len(stated)))
        if not stated:
            return
        almanac = stated[0]

        day, month, year = almanac["date"]
        check("the date arrives as numbers rather than only as prose",
              1 <= day <= 30 and 1 <= month <= 12 and year >= 1,
              f"{day}/{month}/{year}")
        line = texts(frames)
        check("and the same date is still in the chat line the legacy client"
              " reads",
              f"{day}/{month}/{year}" in line, line.strip()[:80])

        check("the catalogue of days travels with it, so the client ships"
              " none",
              len(almanac["catalogue"]) >= 20,
              f"{len(almanac['catalogue'])} days")
        check("every day in the catalogue explains itself",
              all(description for _kind, _name, description
                  in almanac["catalogue"]))
        check("and every kind is one the client knows how to render",
              {kind for kind, _n, _d in almanac["catalogue"]} <= set(KINDS))

        # Setting the day is the only deterministic way to see a special one
        # inside a run: the natural roll happens once per six-hour game day
        # and is uncommon by design. This login is named as an invasion master
        # in the settings file written for this run.
        frames = await ask(writer, reader, "#set_day Day of Sun Tzu", 2.5)
        stated = almanacs(frames)
        check("setting the day restates the almanac to everyone rather than"
              " only announcing it in chat",
              bool(stated), texts(frames).strip()[:90])
        if stated:
            today = stated[-1]
            check("the new day arrives with its name and kind",
                  today["name"] == "Day of Sun Tzu" and today["kind"] == "good",
                  f"{today['name']} / {today['kind']}")
            check("and its experience multipliers are stated rather than left"
                  " in the sentence",
                  today["multipliers"] == {"attack": 2.0, "defense": 2.0},
                  str(today["multipliers"]))
    finally:
        await close_client(writer)


async def drain_date(writer, reader):
    writer.write(packet(GET_DATE, b""))
    await writer.drain()
    return await drain(reader, 2.0)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve()
    name, password = disposable_credentials("alma")
    # Setting a day needs the character named as an invasion master, so this
    # run gets its own settings file naming its own throwaway login rather
    # than the shipped configuration being edited.
    settings = (root / "config" / "eloria" / "server.txt").read_text(
        encoding="utf-8")
    settings = chr(10).join(
        f"invasion_masters = {name}" if line.startswith("invasion_masters")
        else line for line in settings.splitlines()) + chr(10)
    with LocalServer(root, "eloria-almanac-",
                     overrides={"--settings": settings}) as server:
        asyncio.run(probe(server.port, name, password))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
