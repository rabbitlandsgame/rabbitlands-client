"""Verify season login state, #day and clock requests against a local server.

Usage: python tests/integration/seasons_local.py <server-root>
Uses a disposable character and database; never touches a running server.
"""

import asyncio
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

from local_server import LocalServer, close_client, create_character, disposable_credentials, login, packet
from almanac_local import decode_almanac, drain, texts


async def probe(port):
    name, password = disposable_credentials("seas")
    await create_character(port, name, password)
    reader, writer, _actor = await login(port, name, password)
    try:
        await drain(reader, 0.2)
        writer.write(packet(0, b"#clientcaps almanac_v1,seasons_v1,weather_state_v1\0"))
        await writer.drain()
        frames = await drain(reader, 0.6)
        almanacs = [body for command, body in frames if command == 238]
        assert len(almanacs) == 1, "capability handshake must immediately state the season"
        payload = almanacs[0]
        decode_almanac(payload[:-5])  # The legacy part remains a complete almanac.
        index, boundary = struct.unpack("<BI", payload[-5:])
        now = datetime.now(timezone.utc)
        names = ("Winter", "Spring", "Summer", "Autumn")
        assert index == (now.month - 1) % 4
        expected_boundary = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1,
                                     tzinfo=timezone.utc)
        assert boundary == int(expected_boundary.timestamp())
        print("PASS season and next month arrive immediately after login")

        writer.write(packet(0, b"#day\0"))
        await writer.drain()
        line = texts(await drain(reader, 0.3))
        assert f"Season: {names[index]}." in line and "day" in line.lower()
        print("PASS #day includes the season alongside the day information")

        # These are the two requests sent by main.gd when the clock is clicked.
        writer.write(packet(230) + packet(231))
        await writer.drain()
        frames = await drain(reader, 0.3)
        line = texts(frames)
        assert "Game Date " in line and "Game time is " in line
        assert f"Season: {names[index]}." in line and "(UTC)" in line
        print("PASS clock click replies include date, time, season and next change")

        writer.write(packet(0, b"#clientcaps almanac_v1\0") + packet(230))
        await writer.drain()
        frames = await drain(reader, 0.3)
        almanacs = [decode_almanac(body) for command, body in frames if command == 238]
        assert len(almanacs) == 1
        print("PASS older clients retain the exact legacy almanac layout")
    finally:
        await close_client(writer)


if __name__ == "__main__":
    with LocalServer(Path(sys.argv[1]), "rabbitlands-seasons-") as server:
        asyncio.run(probe(server.port))
