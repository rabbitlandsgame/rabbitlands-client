#!/usr/bin/env python3
"""Prove TURN_LEFT(11)/TURN_RIGHT(12) are authoritative against a real server.

The Godot client used to rotate its own mesh and tell nobody, so no other
player ever saw a turn and the local view disagreed with authoritative state
until the next movement command. This drives the genuine server with two
connected clients and checks that one client's turn reaches the other as a
CMD_TURN_* actor command, and that the resulting facing is also what the actor
packet reports to a resyncing client.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (LocalServer, close_client, collect_command,
                          create_character, disposable_credentials, login,
                          packet)

TURN_LEFT = 11
TURN_RIGHT = 12
ADD_ACTOR_COMMAND = 2
SEND_ME_MY_ACTORS = 8
ADD_NEW_ENHANCED_ACTOR = 51
CMD_TURN_N = 38
CMD_TURN_NW = 45
ROTATION_PER_FACING = 8192


async def collect_turn_for(reader: asyncio.StreamReader, actor_id: int) -> int:
    """Return the next CMD_TURN_* command addressed to actor_id."""
    while True:
        payload = await collect_command(reader, ADD_ACTOR_COMMAND)
        for offset in range(0, len(payload) - 2, 3):
            who = struct.unpack_from("<H", payload, offset)[0]
            command = payload[offset + 2]
            if who == actor_id and CMD_TURN_N <= command <= CMD_TURN_NW:
                return command


async def actor_rotation(reader: asyncio.StreamReader, writer,
                         actor_id: int) -> int:
    """Ask for a resync and return the rotation field of that actor packet."""
    writer.write(packet(SEND_ME_MY_ACTORS))
    await writer.drain()
    while True:
        payload = await collect_command(reader, ADD_NEW_ENHANCED_ACTOR)
        if struct.unpack_from("<H", payload)[0] == actor_id:
            return struct.unpack_from("<h", payload, 8)[0]


def facing_index(rotation: int) -> int:
    return round((rotation % 65536) / ROTATION_PER_FACING) % 8


async def scenario(port: int) -> None:
    mover, mover_password = disposable_credentials("TurnA")
    watcher, watcher_password = disposable_credentials("TurnB")
    await create_character(port, mover, mover_password)
    await create_character(port, watcher, watcher_password)

    mover_reader, mover_writer, mover_id = await login(
        port, mover, mover_password)
    watcher_reader, watcher_writer, _watcher_id = await login(
        port, watcher, watcher_password)
    assert mover_id is not None

    start = await actor_rotation(mover_reader, mover_writer, mover_id)
    start_index = facing_index(start)

    # A right turn is one clockwise step, and the other client is told about it.
    mover_writer.write(packet(TURN_RIGHT))
    await mover_writer.drain()
    own, seen = await asyncio.gather(
        collect_turn_for(mover_reader, mover_id),
        collect_turn_for(watcher_reader, mover_id))
    expected = CMD_TURN_N + (start_index + 1) % 8
    assert own == expected, (own, expected)
    assert seen == expected, "the second client did not receive the turn"

    # Two left turns land one step counter-clockwise of the starting facing.
    for _ in range(2):
        mover_writer.write(packet(TURN_LEFT))
        await mover_writer.drain()
        await collect_turn_for(mover_reader, mover_id)
    final = await actor_rotation(mover_reader, mover_writer, mover_id)
    assert facing_index(final) == (start_index - 1) % 8, (final, start_index)

    # The stored facing is what any client is told when the actor is re-sent,
    # so a turn is not lost the moment somebody resyncs.
    watcher_writer.write(packet(SEND_ME_MY_ACTORS))
    await watcher_writer.drain()
    while True:
        payload = await collect_command(watcher_reader, ADD_NEW_ENHANCED_ACTOR)
        if struct.unpack_from("<H", payload)[0] == mover_id:
            assert struct.unpack_from("<h", payload, 8)[0] == final
            break

    print("local turn integration: PASS")
    print("TURN_RIGHT produced exactly one clockwise CMD_TURN_* step: PASS")
    print("a second real client received the same authoritative turn: PASS")
    print("two TURN_LEFT steps left the actor one step counter-clockwise: PASS")
    print("the actor packet reports the turned facing on resync: PASS")
    print("credentials: REDACTED")
    await close_client(mover_writer)
    await close_client(watcher_writer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    arguments = parser.parse_args()
    with LocalServer(arguments.server_root, prefix="eloria-turn-") as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + "\n")
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
