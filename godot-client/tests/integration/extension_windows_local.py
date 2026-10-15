#!/usr/bin/env python3
"""Prove the nine extension windows against the genuine Eloria server.

The Godot client advertises ten capability strings and then renders whatever
the server pushes. This probe starts the real `eloria.server`, logs in twice -
once advertising the capabilities and once not - and checks that the server
answers the capable session with the extension packets the windows are built
on, and the plain session with the legacy text. The merchant case also proves
today's server change: selecting an item no longer draws the NPC dialogue that
used to cover the merchant window.

Credentials are generated per run, held only in memory, and never printed; the
report records them as REDACTED.

Usage: python tests/integration/extension_windows_local.py <server-root>
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
RESPOND_TO_NPC = 29

RAW_TEXT = 0
ADD_NEW_ENHANCED_ACTOR = 51
ADD_NEW_ACTOR_EXTENDED = 247  # what an actor16_v1 client is sent instead
NPC_TEXT = 30
NPC_OPTIONS_LIST = 31
SEND_NPC_INFO = 33
ELORIA_MARKETPLACE_STATE = 222
ELORIA_MERCHANT_STATE = 223
ELORIA_QUEST_JOURNAL_STATE = 224
ELORIA_INVENTORY_STATE = 226
ELORIA_MAIL_STATE = 229
ELORIA_NAVIGATION_STATE = 230

CAPABILITIES = (
    "actor16_v1,combat_hud_v1,inventory_window_v1,item_detail_v1,"
    "mail_window_v1,market_window_v1,merchant_window_v1,navigation_hud_v1,"
    "quest_journal_v1,special_events_v1,lantern_tutorial_v1")

SHOP_BUY_ITEM = 3100
SHOP_QUANTITY = 3300

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


async def say(writer, text: str) -> None:
    writer.write(packet(RAW_TEXT_C, text.encode("utf-8") + b"\0"))
    await writer.drain()


async def drain(reader, seconds: float = 1.2) -> list[tuple[int, bytes]]:
    """Collect every frame that arrives within a quiet window."""
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


def texts(frames: list[tuple[int, bytes]]) -> str:
    return " | ".join(payload[1:].split(b"\0", 1)[0].decode("utf-8", "replace")
                      for command, payload in frames if command == RAW_TEXT)


async def ask(writer, reader, text: str, seconds: float = 1.2):
    await say(writer, text)
    return await drain(reader, seconds)


def commands(frames) -> list[int]:
    return [command for command, _ in frames]


def find_actor(frames, name: str) -> int | None:
    """The actor id of a named NPC, read out of its add-actor packet."""
    for command, payload in frames:
        if command not in (ADD_NEW_ENHANCED_ACTOR, ADD_NEW_ACTOR_EXTENDED):
            continue
        actor_id = struct.unpack_from("<H", payload)[0]
        if name.encode("utf-8") in payload:
            return actor_id
    return None


async def probe(port: int) -> None:
    modern_name, modern_password = disposable_credentials("ext")
    plain_name, plain_password = disposable_credentials("leg")
    await create_character(port, modern_name, modern_password)
    await create_character(port, plain_name, plain_password)
    reader, writer, _ = await login(port, modern_name, modern_password)
    plain_reader, plain_writer, _ = await login(port, plain_name, plain_password)
    try:
        await ask(writer, reader, "#clientcaps " + CAPABILITIES)
        # The shop fixture is beyond the current opening tutorial.
        tutorial_frames = await ask(writer, reader, "#tutorial skip")
        for command, payload in tutorial_frames:
            if command == 83 and struct.unpack_from("<H", payload)[0] in (4100, 4150):
                # Confirm Skip on this disposable character's tutorial popup.
                writer.write(packet(50, payload[:2] + bytes((1, 1))))
                await writer.drain()
                await drain(reader)

        frames = await ask(writer, reader, "#inventory")
        check("226 inventory state answers an advertised inventory_window_v1",
              ELORIA_INVENTORY_STATE in commands(frames), str(commands(frames)))
        plain_frames = await ask(plain_writer, plain_reader, "#inventory")
        check("a client that advertises nothing is refused the organizer",
              ELORIA_INVENTORY_STATE not in commands(plain_frames)
              and "independent Eloria client" in texts(plain_frames),
              texts(plain_frames))

        frames = await ask(writer, reader, "#quests")
        check("224 quest journal answers #quests",
              ELORIA_QUEST_JOURNAL_STATE in commands(frames), str(commands(frames)))

        frames = await ask(writer, reader, "#auction browse")
        check("222 marketplace answers #auction browse",
              ELORIA_MARKETPLACE_STATE in commands(frames), str(commands(frames)))

        frames = await ask(writer, reader, "#mail inbox")
        check("229 mail answers #mail inbox",
              ELORIA_MAIL_STATE in commands(frames), str(commands(frames)))
        plain_frames = await ask(plain_writer, plain_reader, "#mail inbox")
        check("a plain client still gets its inbox as text",
              ELORIA_MAIL_STATE not in commands(plain_frames)
              and "Mail inbox" in texts(plain_frames), texts(plain_frames))

        frames = await ask(writer, reader, "#waypoint 780 490 Reed bank")
        navigation = [payload for command, payload in frames
                      if command == ELORIA_NAVIGATION_STATE]
        check("230 navigation state answers #waypoint",
              bool(navigation) and navigation[0][0] == 1
              and struct.unpack_from("<HH", navigation[0], 1) == (780, 490)
              and b"Reed bank\0" in navigation[0],
              str(commands(frames)))
        frames = await ask(writer, reader, "#waypoint clear")
        cleared = [payload for command, payload in frames
                   if command == ELORIA_NAVIGATION_STATE]
        check("clearing the waypoint is stated, not inferred",
              bool(cleared) and cleared[0][0] == 0, str(commands(frames)))

        # The merchant window, and the dialogue that must no longer appear.
        frames = await ask(writer, reader, "#tp 268 118 crownwater", 2.5)
        merchant_id = find_actor(frames, "Daro Pell")
        if merchant_id is None:
            check("the shop NPC is on the map after teleporting", False,
                  str(commands(frames)) + " " + texts(frames))
            return
        writer.write(packet(TOUCH_PLAYER, struct.pack("<I", merchant_id)))
        await writer.drain()
        frames = await drain(reader, 1.5)
        merchant = [payload for command, payload in frames
                    if command == ELORIA_MERCHANT_STATE]
        check("223 merchant state opens the shop for a capable client",
              bool(merchant) and b"Daro Pell\0" in merchant[0],
              repr(merchant[0][:48]) if merchant else str(commands(frames)))
        check("touching the merchant draws no NPC dialogue",
              NPC_TEXT not in commands(frames)
              and NPC_OPTIONS_LIST not in commands(frames), str(commands(frames)))

        funded = await ask(writer, reader, "#give Gold Coins 40")
        check("the probe can fund the purchase it is about to make",
              "Gave 40 Gold Coins" in texts(funded), texts(funded))
        writer.write(packet(RESPOND_TO_NPC, struct.pack("<HH", merchant_id, SHOP_BUY_ITEM)))
        writer.write(packet(RESPOND_TO_NPC, struct.pack("<HH", merchant_id, SHOP_QUANTITY)))
        await writer.drain()
        frames = await drain(reader, 2.0)
        check("a trade answers with a refreshed merchant window, not a menu",
              ELORIA_MERCHANT_STATE in commands(frames)
              and NPC_TEXT not in commands(frames)
              and NPC_OPTIONS_LIST not in commands(frames), str(commands(frames)))
        check("the server states the trade it performed",
              "bought 1 Bread" in texts(frames), texts(frames))

        await ask(writer, reader, "#give Gold Coins 500")
        frames = await ask(writer, reader, f"#shop buy {merchant_id} 0 3")
        check("an exact typed quantity buys three items in one request",
              "bought 3 Bread" in texts(frames)
              and ELORIA_MERCHANT_STATE in commands(frames)
              and NPC_TEXT not in commands(frames), texts(frames))
        frames = await ask(writer, reader, f"#shop sell {merchant_id} 0 3")
        check("an exact typed quantity sells three items in one request",
              "sold 3 Bread" in texts(frames)
              and ELORIA_MERCHANT_STATE in commands(frames)
              and NPC_TEXT not in commands(frames), texts(frames))
    finally:
        await close_client(writer)
        await close_client(plain_writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]), "eloria-extension-windows-") as server:
        asyncio.run(probe(server.port))
        failed = [label for label, passed, _ in results if not passed]
        print("\ncredentials: REDACTED")
        print(f"{len(results) - len(failed)}/{len(results)} checks passed")
        if failed:
            print("server log tail:\n" + server.recent_log(40))
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
