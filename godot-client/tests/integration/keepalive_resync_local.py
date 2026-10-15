#!/usr/bin/env python3
"""Keepalive, idle eviction and resync against a real server.

The client answered PING_REQUEST(60) but never initiated HEART_BEAT(14), and
had no resync path, so a parked session had nothing keeping it alive and a
recovered connection had no way to rebuild state.

The server now closes a logged-in connection that has gone silent, which is
what makes a heartbeat matter and what stops a half-open socket holding a
character hostage against its own owner's reconnect. This drives both sides of
that with a deliberately short idle timeout so the run takes seconds rather
than minutes.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (LocalServer, close_client, create_character,
                          disposable_credentials, login, packet, read_packet)

HEART_BEAT = 14
SEND_ME_MY_ACTORS = 8
SEND_MY_STATS = 17
SEND_MY_INVENTORY = 18
ADD_NEW_ENHANCED_ACTOR = 51
HERE_YOUR_STATS = 18
HERE_YOUR_INVENTORY = 19

IDLE_TIMEOUT_SECONDS = 4
# The shipped settings file with one value replaced, so everything else about
# the world stays exactly as configured.
SERVER_SETTINGS = None


async def drain(reader: asyncio.StreamReader, seconds: float) -> list:
    frames = []
    try:
        while True:
            frames.append(await read_packet(reader, seconds))
    except (asyncio.IncompleteReadError, TimeoutError):
        pass
    return frames


async def wait_for_close(reader: asyncio.StreamReader, limit: float) -> float:
    """Return how long it took the server to close the connection."""
    started = time.monotonic()
    while time.monotonic() - started < limit:
        try:
            await read_packet(reader, limit)
        except asyncio.IncompleteReadError:
            return time.monotonic() - started
        except TimeoutError:
            break
    return -1.0


async def scenario(port: int) -> None:
    # A client that heartbeats survives well past the idle timeout.
    name, password = disposable_credentials("Beat")
    await create_character(port, name, password)
    reader, writer, actor_id = await login(port, name, password)
    assert actor_id is not None
    await drain(reader, 1.0)
    deadline = time.monotonic() + IDLE_TIMEOUT_SECONDS * 2.5
    while time.monotonic() < deadline:
        writer.write(packet(HEART_BEAT))
        await writer.drain()
        await asyncio.sleep(IDLE_TIMEOUT_SECONDS / 3.0)
    # Still alive: the server answers a resync rather than having hung up.
    writer.write(packet(SEND_ME_MY_ACTORS))
    writer.write(packet(SEND_MY_STATS))
    writer.write(packet(SEND_MY_INVENTORY))
    await writer.drain()
    resync = await drain(reader, 3.0)
    commands = {command for command, _payload in resync}
    assert ADD_NEW_ENHANCED_ACTOR in commands, sorted(commands)
    assert HERE_YOUR_STATS in commands, sorted(commands)
    assert HERE_YOUR_INVENTORY in commands, sorted(commands)
    own = [payload for command, payload in resync
           if command == ADD_NEW_ENHANCED_ACTOR
           and struct.unpack_from("<H", payload)[0] == actor_id]
    assert own, "the resync did not include the player's own actor"

    # A client that goes silent is closed, and its character is released so it
    # can log in again immediately.
    silent_name, silent_password = disposable_credentials("Quiet")
    await create_character(port, silent_name, silent_password)
    silent_reader, silent_writer, _silent_id = await login(
        port, silent_name, silent_password)
    await drain(silent_reader, 1.0)
    closed_after = await wait_for_close(
        silent_reader, IDLE_TIMEOUT_SECONDS * 6.0)
    assert closed_after >= 0.0, (
        "a silent logged-in client was never closed by the server")
    await close_client(silent_writer)

    # The evicted character is immediately loginable again: the eviction
    # released it rather than leaving it stuck as already-logged-in.
    again_reader, again_writer, again_id = await login(
        port, silent_name, silent_password)
    assert again_id is not None
    await drain(again_reader, 1.0)

    print("local keepalive and resync integration: PASS")
    print("a heartbeating client survives %dx its idle timeout: PASS"
          % 2)
    print("SEND_ME_MY_ACTORS/SEND_MY_STATS/SEND_MY_INVENTORY each return their"
          " authoritative snapshot: PASS")
    print("a silent logged-in client is closed by the server after %.1fs: PASS"
          % closed_after)
    print("the evicted character can log in again immediately: PASS")
    print("credentials: REDACTED")
    await close_client(writer)
    await close_client(again_writer)


def settings_override(server_root: Path) -> str:
    text = (server_root / "config" / "eloria" / "server.txt").read_text(
        encoding="utf-8")
    kept = [line for line in text.splitlines()
            if not line.strip().startswith("client_idle_timeout_seconds")]
    kept.append("client_idle_timeout_seconds = %d" % IDLE_TIMEOUT_SECONDS)
    return "\n".join(kept) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.server_root.resolve()
    with LocalServer(root, prefix="eloria-beat-",
                     overrides={"--settings": settings_override(root)}) as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
