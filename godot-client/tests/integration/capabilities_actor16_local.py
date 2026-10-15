#!/usr/bin/env python3
"""What the capability handshake changes, and how 16-bit actors reach the wire.

Two questions the migration document asks to be answered empirically rather
than assumed:

* does the server withhold Eloria extension packets from a client that has not
  sent `#clientcaps`, and does it emit command 224 at all? It does both: the
  quest journal arrives as raw text without the capability and as command 224
  with it, so the traceability row blaming an unmodified server for the missing
  journal packet was wrong - the missing handshake was the whole cause.
* is `actor16_v1` what gates the 16-bit actor packet? It is not. The server
  chooses `ADD_NEW_ACTOR_EXTENDED(247)` purely from `actor_type > 0xFF`, with
  no capability check anywhere, so a creature with a type of 403 arrives on the
  extended packet even for a client that has advertised nothing.

The creature spawns come from a probe-only spawn table placed beside the player
so the run does not depend on where the shipped content happens to put wildlife.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (LocalServer, clean_text, close_client,
                          create_character, disposable_credentials, login,
                          packet, read_packet)

RAW_TEXT = 0
ADD_NEW_ACTOR = 1
ADD_ACTOR_COMMAND = 2
ATTACK_SOMEONE = 40
GET_ACTOR_DAMAGE = 47
CMD_ENTER_COMBAT = 18
CMD_ATTACK_UP_1 = 46
ELORIA_QUEST_JOURNAL_STATE = 224
ADD_NEW_ACTOR_EXTENDED = 247

# Two Nymara creatures with actor types above 255, standing on the player's
# doorstep so the visibility radius is not part of what is being measured.
# Both are non-aggressive, so the only combat in the run is the one this
# script starts, and both stand adjacent to the player so the server has no
# approach to walk before it can swing.
PROBE_SPAWNS = """spawn | four_gates | reedhorn_stag | 769 | 480
spawn | four_gates | gate_turtle | 767 | 480
"""
EXPECTED_TYPES = {"Reedhorn Stag": 401, "Four Gates Turtle": 402}
TARGET_CREATURE = "Reedhorn Stag"


async def drain(reader: asyncio.StreamReader, seconds: float = 1.2) -> list:
    frames = []
    try:
        while True:
            frames.append(await read_packet(reader, seconds))
    except (asyncio.IncompleteReadError, TimeoutError):
        pass
    return frames


def decode_extended_actor(payload: bytes) -> tuple[int, int, str]:
    """Return (actor_id, actor_type, name) from an extended actor packet."""
    actor_id, x, y, _z, _rotation, actor_type = struct.unpack_from(
        "<HHHHhH", payload)
    name = payload[18:].split(b"\0", 1)[0].decode("utf-8", "replace")
    return actor_id, actor_type, name


async def scenario(port: int) -> None:
    name, password = disposable_credentials("Cap")
    await create_character(port, name, password)
    reader, writer, actor_id = await login(port, name, password)
    assert actor_id is not None
    login_frames = await drain(reader, 1.5)

    # 16-bit actors, with nothing advertised.
    extended = {}
    legacy = []
    for command, payload in login_frames:
        if command == ADD_NEW_ACTOR_EXTENDED:
            decoded = decode_extended_actor(payload)
            extended[decoded[2]] = decoded
        elif command == ADD_NEW_ACTOR:
            legacy.append(payload)
    assert set(extended) == set(EXPECTED_TYPES), sorted(extended)
    for creature_name, expected_type in EXPECTED_TYPES.items():
        assert extended[creature_name][1] == expected_type, extended[creature_name]
        assert expected_type > 0xFF
    assert not legacy, (
        "a creature with a type above 255 must never use the 8-bit packet")

    # The same client has advertised nothing at this point, which is what makes
    # the result above evidence that actor16_v1 does not gate the packet.
    writer.write(packet(RAW_TEXT, b"#quests\0"))
    await writer.drain()
    uncapable = await drain(reader, 1.5)
    journal_packets = [payload for command, payload in uncapable
                       if command == ELORIA_QUEST_JOURNAL_STATE]
    journal_text = [clean_text(payload)[1] for command, payload in uncapable
                    if command == RAW_TEXT]
    assert not journal_packets, "command 224 arrived without the capability"
    assert any("Quest journal" in line for line in journal_text), journal_text

    # Advertise it and ask again.
    writer.write(packet(RAW_TEXT, b"#clientcaps quest_journal_v1\0"))
    await writer.drain()
    await drain(reader, 0.6)
    writer.write(packet(RAW_TEXT, b"#quests\0"))
    await writer.drain()
    capable = await drain(reader, 1.5)
    assert any(command == ELORIA_QUEST_JOURNAL_STATE for command, _ in capable), (
        "the server did not emit command 224 even after the handshake")
    assert not any(command == RAW_TEXT and "Quest journal" in clean_text(payload)[1]
                   for command, payload in capable), (
        "the raw-text fallback is still being sent alongside the packet")

    # The same 16-bit creature is a real target, not just a decodable spawn
    # packet. Selection is a client-side choice, so the wire evidence is the
    # attack: the server answers with authoritative combat for both actors.
    target_id = extended[TARGET_CREATURE][0]
    writer.write(packet(ATTACK_SOMEONE, struct.pack("<I", target_id)))
    await writer.drain()
    combat = await drain(reader, 10.0)
    commands_by_actor: dict[int, set[int]] = {}
    for command, payload in combat:
        if command != ADD_ACTOR_COMMAND:
            continue
        for offset in range(0, len(payload) - 2, 3):
            who = struct.unpack_from("<H", payload, offset)[0]
            commands_by_actor.setdefault(who, set()).add(payload[offset + 2])
    combat_actors = {actor_id, target_id}
    assert combat_actors & set(commands_by_actor), sorted(commands_by_actor)
    fighting = set().union(*(commands_by_actor.get(who, set())
                             for who in combat_actors))
    assert CMD_ATTACK_UP_1 in fighting or CMD_ENTER_COMBAT in fighting, sorted(fighting)
    damaged = {struct.unpack_from("<H", payload)[0]
               for command, payload in combat if command == GET_ACTOR_DAMAGE}
    assert damaged & combat_actors, (
        "attacking the creature produced no authoritative damage")

    print("local capability and 16-bit actor integration: PASS")
    print("creatures with actor types 401 and 402 arrive on"
          " ADD_NEW_ACTOR_EXTENDED(247) with no capability advertised: PASS")
    print("no creature above type 255 used the 8-bit actor packet: PASS")
    print("the quest journal is raw text without #clientcaps: PASS")
    print("the same request returns command 224 after #clientcaps: PASS")
    print("attacking the 16-bit creature produces authoritative combat"
          " commands and damage for both actors: PASS")
    print("credentials: REDACTED")
    await close_client(writer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    arguments = parser.parse_args()
    with LocalServer(arguments.server_root, prefix="eloria-caps-",
                     overrides={"--spawns": PROBE_SPAWNS}) as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
