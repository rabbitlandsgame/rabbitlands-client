#!/usr/bin/env python3
"""Exercise MANUFACTURE_THIS against an unmodified local eloria-server."""

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


def packet(command: int, payload: bytes = b"") -> bytes:
    return bytes((command,)) + struct.pack("<H", len(payload) + 1) + payload


async def read_packet(reader: asyncio.StreamReader, timeout: float = 8.0):
    header = await asyncio.wait_for(reader.readexactly(3), timeout)
    wire_length = struct.unpack_from("<H", header, 1)[0]
    payload = await asyncio.wait_for(
        reader.readexactly(wire_length - 1), timeout
    )
    return header[0], payload


async def collect_until(reader, command: int, timeout: float = 10.0):
    events = []
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        event = await read_packet(reader, remaining)
        events.append(event)
        if event[0] == command:
            return events


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


async def create_character(port: int, name: str, password: str):
    reader, writer = await open_client(port)
    credentials = (name + " " + password).encode("ascii") + b"\0"
    writer.write(packet(141, credentials + bytes(8)))
    await writer.drain()
    await collect_until(reader, 252)
    writer.close()
    await writer.wait_closed()


async def login(port: int, name: str, password: str):
    reader, writer = await open_client(port)
    credentials = (name + " " + password).encode("ascii") + b"\0"
    writer.write(packet(140, credentials))
    await writer.drain()
    required = {250, 3, 7, 19}
    while required:
        command, _payload = await read_packet(reader)
        required.discard(command)
    return reader, writer


def inventory_entries(payload: bytes) -> dict[int, tuple[int, int]]:
    count = payload[0]
    assert len(payload) >= 1 + count * 8
    result = {}
    for offset in range(count):
        image_id, quantity, slot, _flags = struct.unpack_from(
            "<HIBB", payload, 1 + offset * 8
        )
        result[image_id] = (slot, quantity)
    return result


def item_text(payload: bytes) -> str:
    return payload[1:].rstrip(b"\0").decode("utf-8")


async def give(reader, writer, name: str, quantity: int):
    writer.write(packet(0, f"#give {name} {quantity}\0".encode("utf-8")))
    await writer.drain()
    events = await collect_until(reader, 19)
    return inventory_entries(events[-1][1])


async def scenario(port: int):
    suffix = secrets.token_hex(4)
    name = "Mix" + suffix
    password = secrets.token_urlsafe(28)
    await create_character(port, name, password)

    # Prime the fresh-character synchronization path, matching other local
    # integration slices, then reconnect to exercise a stable session.
    _reader, primed_writer = await login(port, name, password)
    primed_writer.close()
    await primed_writer.wait_closed()
    await asyncio.sleep(0.15)
    reader, writer = await login(port, name, password)

    inventory = await give(reader, writer, "Sulfur", 1)
    sulfur_slot = inventory[42][0]
    invalid_payload = bytes((1, sulfur_slot)) + struct.pack("<H", 1) + bytes((1,))
    writer.write(packet(30, invalid_payload))
    await writer.drain()
    rejected = await collect_until(reader, 20)
    rejection = item_text(rejected[-1][1])
    assert rejection == "No known recipe uses that exact selection of ingredients."

    success_events = []
    manufacturing_frame = b""
    for _attempt in range(12):
        await give(reader, writer, "Sulfur", 1)
        await give(reader, writer, "Red Rose", 1)
        inventory = await give(reader, writer, "Red Snapdragons", 1)
        ingredients = ((inventory[42][0], 1), (inventory[31][0], 1),
                       (inventory[35][0], 1))
        payload = bytes((len(ingredients),))
        for slot, quantity in ingredients:
            payload += bytes((slot,)) + struct.pack("<H", quantity)
        payload += bytes((1,))
        manufacturing_frame = packet(30, payload)
        writer.write(manufacturing_frame)
        await writer.drain()
        events = await collect_until(reader, 20, timeout=12.0)
        result = item_text(events[-1][1])
        if result.startswith("You made Fire Essence"):
            success_events = events
            break
    assert success_events, "mixing did not succeed within twelve server attempts"
    commands = {command for command, _payload in success_events}
    assert {0, 19, 20, 49}.issubset(commands)
    success_inventory = next(
        inventory_entries(payload)
        for command, payload in success_events
        if command == 19
    )
    assert success_inventory[50][1] >= 1

    print("local manufacturing integration: PASS")
    print("MANUFACTURE_THIS safe bytes:", manufacturing_frame.hex())
    print("invalid exact-selection rejection: PASS")
    print("successful Fire Essence mix: PASS")
    print("raw text, inventory, item text, and partial stats responses: PASS")
    print("credentials: REDACTED")
    writer.close()
    await writer.wait_closed()


async def wait_for_server(port: int):
    for _ in range(100):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
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
    with LocalServer(arguments.server_root, prefix="eloria-mix-") as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
