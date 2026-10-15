#!/usr/bin/env python3
"""Exercise real NPC replication and dialogue against an unmodified local server."""

from __future__ import annotations

import argparse
import asyncio
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import LocalServer


ADD_NEW_ENHANCED_ACTOR = 51
CLOSE_NPC_MENU = 32
CREATE_CHAR_OK = 252
NPC_OPTIONS_LIST = 31
NPC_TEXT = 30
SEND_NPC_INFO = 33
TOUCH_PLAYER = 28
RESPOND_TO_NPC = 29


def packet(command: int, payload: bytes = b"") -> bytes:
    return bytes((command,)) + struct.pack("<H", len(payload) + 1) + payload


async def read_packet(reader: asyncio.StreamReader, timeout: float = 8.0):
    header = await asyncio.wait_for(reader.readexactly(3), timeout)
    wire_length = struct.unpack_from("<H", header, 1)[0]
    payload = await asyncio.wait_for(reader.readexactly(wire_length - 1), timeout)
    return header[0], payload


async def open_client(port: int):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    version = (
        struct.pack("<HH4B", 10, 31, 1, 9, 7, 0)
        + bytes(4)
        + struct.pack(">H", port)
    )
    writer.write(packet(10, version) + packet(9))
    await writer.drain()
    return reader, writer


async def create_character(port: int, name: str, password: str) -> None:
    reader, writer = await open_client(port)
    credentials = (name + " " + password).encode("ascii") + b"\0"
    writer.write(packet(141, credentials + bytes(8)))
    await writer.drain()
    while True:
        command, _payload = await read_packet(reader)
        if command == CREATE_CHAR_OK:
            break
    writer.close()
    await writer.wait_closed()


def enhanced_actor(payload: bytes) -> dict[str, int | str]:
    assert len(payload) >= 30
    name = payload[28:].split(b"\0", 1)[0]
    name = bytes(value for value in name if not 0x7F <= value <= 0x9F)
    actor_id, x, y = struct.unpack_from("<HHH", payload)
    return {
        "actor_id": actor_id,
        "x": x & 0x7FF,
        "y": y & 0x7FF,
        "actor_type": payload[10],
        "kind": payload[27],
        "name": name.decode("latin-1"),
    }


async def login_and_find_tutorial(port: int, name: str, password: str):
    reader, writer = await open_client(port)
    credentials = (name + " " + password).encode("ascii") + b"\0"
    writer.write(packet(140, credentials))
    await writer.drain()
    required = {250, 3, 7, 19}
    tutorial = None
    while required or tutorial is None:
        command, payload = await read_packet(reader)
        required.discard(command)
        if command == ADD_NEW_ENHANCED_ACTOR:
            actor = enhanced_actor(payload)
            if actor["name"] == "Tutorial NPC":
                tutorial = actor
    return reader, writer, tutorial


def npc_name(payload: bytes) -> str:
    return payload[:20].split(b"\0", 1)[0].decode("latin-1")


def npc_text(payload: bytes) -> str:
    return payload.split(b"\0", 1)[0].decode("utf-8")


def npc_options(payload: bytes) -> list[tuple[int, int, str]]:
    options = []
    offset = 0
    while offset < len(payload):
        length = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        label = payload[offset:offset + length].rstrip(b"\0").decode("utf-8")
        offset += length
        response_id, actor_id = struct.unpack_from("<HH", payload, offset)
        offset += 4
        options.append((response_id, actor_id, label))
    return options


async def collect_dialogue(reader: asyncio.StreamReader):
    result = {"name": "", "text": "", "options": []}
    while not result["name"] or not result["text"] or not result["options"]:
        command, payload = await read_packet(reader)
        if command == SEND_NPC_INFO:
            result["name"] = npc_name(payload)
        elif command == NPC_TEXT:
            result["text"] = npc_text(payload)
        elif command == NPC_OPTIONS_LIST:
            result["options"] = npc_options(payload)
    return result


async def collect_text_and_options(reader: asyncio.StreamReader):
    text = ""
    options = []
    while not text or not options:
        command, payload = await read_packet(reader)
        if command == NPC_TEXT:
            text = npc_text(payload)
        elif command == NPC_OPTIONS_LIST:
            options = npc_options(payload)
    return text, options


async def scenario(port: int) -> None:
    name = "Npc" + secrets.token_hex(4)
    password = secrets.token_urlsafe(28)
    await create_character(port, name, password)

    # The current server records and broadcasts its first-login notification
    # after completing the normal synchronization sequence. Prime that lifecycle
    # once, matching the other unmodified-server integration slices, then test a
    # stable reconnect without changing server code or database state directly.
    _prime_reader, prime_writer, _prime_tutorial = await login_and_find_tutorial(
        port, name, password)
    prime_writer.close()
    await prime_writer.wait_closed()
    await asyncio.sleep(0.15)
    reader, writer, tutorial = await login_and_find_tutorial(port, name, password)

    assert tutorial["kind"] == 2
    assert tutorial["actor_type"] == 1
    assert (tutorial["x"], tutorial["y"]) == (161, 139)
    actor_id = int(tutorial["actor_id"])
    await asyncio.sleep(0.25)
    assert not writer.is_closing()
    touch_frame = packet(TOUCH_PLAYER, struct.pack("<I", actor_id))
    writer.write(touch_frame)
    await writer.drain()
    opened = await collect_dialogue(reader)
    assert opened["name"] == "Tutorial NPC"
    assert "tutorial NPC" in opened["text"]
    assert (1000, actor_id, "Who are you?") in opened["options"]
    assert (900, actor_id, "Bye") in opened["options"]

    response_frame = packet(RESPOND_TO_NPC, struct.pack("<HH", actor_id, 1000))
    writer.write(response_frame)
    await writer.drain()
    response_text, response_options = await collect_text_and_options(reader)
    assert response_text.startswith("I am the Tutorial NPC.")
    assert response_options == [(900, actor_id, "Close")]

    close_frame = packet(RESPOND_TO_NPC, struct.pack("<HH", actor_id, 900))
    writer.write(close_frame)
    await writer.drain()
    while True:
        command, _payload = await read_packet(reader)
        if command == CLOSE_NPC_MENU:
            break

    print("local NPC dialogue integration: PASS")
    print("enhanced kind-2 NPC replication: PASS")
    print("TOUCH_PLAYER safe bytes:", touch_frame.hex())
    print("RESPOND_TO_NPC safe bytes:", response_frame.hex())
    print("server dialogue text/options and close: PASS")
    print("credentials: REDACTED")
    writer.close()
    await writer.wait_closed()


async def wait_for_server(port: int) -> None:
    for _ in range(100):
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError("local server did not start")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    arguments = parser.parse_args()
    # LocalServer starts the server with config/eloria and drains its stdout.
    # Both matter: the default config set has no four_gates map, and an
    # undrained pipe blocks the server's own event loop on the packet
    # diagnostic dump it writes when an authenticated client disconnects.
    with LocalServer(arguments.server_root, prefix="eloria-npc-") as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
