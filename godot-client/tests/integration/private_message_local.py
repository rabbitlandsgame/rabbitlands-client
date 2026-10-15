#!/usr/bin/env python3
"""Exercise legacy SEND_PM delivery and reply against a local server copy."""

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


async def collect_command(reader: asyncio.StreamReader, wanted: int):
    while True:
        command, payload = await read_packet(reader)
        if command == wanted:
            return payload


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
    await collect_command(reader, 252)
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


def clean_chat(payload: bytes) -> tuple[int, str]:
    channel = payload[0]
    # The audited server prepends one standalone EL color byte to PM text.
    text = bytes(value for value in payload[1:].split(b"\0", 1)[0]
                 if not 0x7F <= value <= 0x9F).decode("utf-8")
    return channel, text


async def collect_chat_matching(reader: asyncio.StreamReader, marker: str):
    while True:
        event = clean_chat(await collect_command(reader, 0))
        if marker in event[1]:
            return event


async def scenario(port: int):
    suffix = secrets.token_hex(4)
    first_name = "PmA" + suffix
    second_name = "PmB" + suffix
    first_password = secrets.token_urlsafe(28)
    second_password = secrets.token_urlsafe(28)
    await create_character(port, first_name, first_password)
    await create_character(port, second_name, second_password)

    # Prime fresh-character synchronization, then reconnect both stable clients.
    _reader, first_prime = await login(port, first_name, first_password)
    first_prime.close()
    await first_prime.wait_closed()
    _reader, second_prime = await login(port, second_name, second_password)
    second_prime.close()
    await second_prime.wait_closed()
    await asyncio.sleep(0.15)
    first_reader, first_writer = await login(port, first_name, first_password)
    second_reader, second_writer = await login(port, second_name, second_password)

    first_writer.write(packet(2, f"{second_name} hello\0".encode("utf-8")))
    await first_writer.drain()
    first_delivery, second_delivery = await asyncio.gather(
        collect_chat_matching(first_reader, f"PM to {second_name}"),
        collect_chat_matching(second_reader, f"PM from {first_name}")
    )
    first_channel, first_text = first_delivery
    second_channel, second_text = second_delivery
    assert first_channel == second_channel == 1
    assert first_text == f"[PM to {second_name}: hello]"
    assert second_text == f"[PM from {first_name}: hello]"

    # The client strips one slash from "// reply", so SEND_PM carries "/reply".
    second_writer.write(packet(2, b"/reply\0"))
    await second_writer.drain()
    reply_sender, reply_recipient = await asyncio.gather(
        collect_chat_matching(second_reader, f"PM to {first_name}"),
        collect_chat_matching(first_reader, f"PM from {second_name}")
    )
    assert reply_sender == (1, f"[PM to {first_name}: reply]")
    assert reply_recipient == (1, f"[PM from {second_name}: reply]")

    missing_name = "Offline" + secrets.token_hex(4)
    first_writer.write(packet(2, f"{missing_name} hello\0".encode("utf-8")))
    await first_writer.drain()
    rejection = await collect_chat_matching(first_reader, "is not online")
    assert rejection == (0, f"{missing_name} is not online.")

    print("local private-message integration: PASS")
    print("two-client SEND_PM delivery and sender acknowledgement: PASS")
    print("reply-to-last-sender shortcut: PASS")
    print("offline-recipient rejection: PASS")
    print("credentials: REDACTED")
    first_writer.close()
    second_writer.close()
    await first_writer.wait_closed()
    await second_writer.wait_closed()


async def wait_for_server(port: int):
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
    with LocalServer(arguments.server_root, prefix="eloria-pm-") as server:
        try:
            asyncio.run(scenario(server.port))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
