#!/usr/bin/env python3
"""Shared harness for driving a real Eloria server over a local socket.

Every `*_local.py` integration script starts the genuine server against a
throwaway SQLite database and speaks the documented wire protocol at it, so a
codec can be proved against the authoritative implementation rather than a
mock. Two things here are load-bearing and were previously duplicated wrongly
in each script:

* the server must be started with `config/eloria/*`. The default `config/*.txt`
  set is the legacy Seridia content, which has no `four_gates` map, so every
  login raises `KeyError: 'four_gates'` inside `World.enter` and the client is
  dropped with no reply;
* the server's stdout must be drained continuously. It logs a per-packet
  diagnostic dump for every authenticated disconnect, which is large enough to
  fill an undrained `subprocess.PIPE`. `log.warning` then blocks on the pipe
  inside the connection handler, which blocks the event loop, and the server
  stops answering every subsequent connection - so the first client to log out
  wedged the whole run.
"""

from __future__ import annotations

import asyncio
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
from collections import deque
from pathlib import Path

# Client -> server
RAW_TEXT_C = 0
SEND_VERSION = 10
SEND_OPENING_SCREEN = 9
LOG_IN = 140
CREATE_CHAR = 141

# Server -> client
RAW_TEXT = 0
YOU_ARE = 3
CHANGE_MAP = 7
HERE_YOUR_INVENTORY = 19
LOG_IN_OK = 250
LOG_IN_NOT_OK = 251
CREATE_CHAR_OK = 252
CREATE_CHAR_NOT_OK = 253

# The independent Eloria world. See the module docstring.
ELORIA_CONFIG = (
    ("--creatures", "creatures.txt"), ("--drops", "drops.txt"),
    ("--maps", "maps.txt"), ("--items", "items.txt"),
    ("--harvesting", "harvesting.txt"), ("--recipes", "recipes.txt"),
    ("--spawns", "spawns.txt"), ("--npcs", "npcs.txt"),
    ("--spells", "spells.xml"), ("--settings", "server.txt"),
    ("--books", "books.txt"), ("--shops", "shops.txt"),
    ("--special-areas", "special_areas.txt"),
    ("--normal-spawns", "spawn_groups/normal"),
    ("--invasion-spawns", "spawn_groups/invasion"),
    ("--instances", "instances"), ("--rare-mixes", "rare_mixes.txt"),
    ("--spell-balance", "spell_balance.txt"),
)


def packet(command: int, payload: bytes = b"") -> bytes:
    return bytes((command,)) + struct.pack("<H", len(payload) + 1) + payload


class LocalServer:
    """A real `eloria.server` process on a free loopback port."""

    def __init__(self, server_root: Path, prefix: str = "eloria-local-",
                 overrides: dict[str, str] | None = None,
                 extra_arguments: list[str] | None = None,
                 secure_port: int | None = None):
        """`overrides` maps a config flag to replacement file text.

        A probe that needs one creature standing next to the player writes its
        own spawn table rather than editing the shipped configuration, so the
        real server is still driving the real content everywhere else.

        `extra_arguments` are appended to the command line verbatim, for flags
        a probe needs and the shipped profile has no opinion about - the TLS
        certificate is the first of them. `secure_port` names the port the
        readiness check should wait on when the cleartext listener is not the
        one under test.
        """
        self.server_root = Path(server_root).resolve()
        self._prefix = prefix
        self._overrides = dict(overrides or {})
        self._extra_arguments = list(extra_arguments or [])
        self._process: subprocess.Popen | None = None
        self._workdir: tempfile.TemporaryDirectory | None = None
        self._log: deque[str] = deque(maxlen=400)
        self._reader_thread: threading.Thread | None = None
        self.port = 0
        self.secure_port = secure_port or 0

    def __enter__(self) -> "LocalServer":
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self._workdir = tempfile.TemporaryDirectory(prefix=self._prefix)
        arguments = [
            sys.executable, "-m", "eloria.server", "--host", "127.0.0.1",
            "--port", str(self.port), "--database",
            str(Path(self._workdir.name) / "eloria.sqlite3")]
        config_root = self._prepare_config()
        for flag, name in ELORIA_CONFIG:
            arguments += [flag, str(config_root / name)]
        arguments += self._extra_arguments
        self._process = subprocess.Popen(
            arguments, cwd=self.server_root, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        self._reader_thread = threading.Thread(
            target=self._drain_output, daemon=True)
        self._reader_thread.start()
        asyncio.run(self._wait_for_listener())
        return self

    def __exit__(self, *_exception) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=5)
        if self._workdir is not None:
            try:
                self._workdir.cleanup()
            except OSError:
                # The server may still hold the SQLite file on Windows. The
                # temporary directory is disposable either way.
                pass

    def _prepare_config(self) -> Path:
        """Return a config directory for this run.

        Without an override the shipped `config/eloria` is used directly. With
        one, the whole directory is copied and the override written over the
        top, because the server derives sibling paths from the ones it is
        given: `interactives.txt` and `rare_harvest.txt` are resolved from the
        *harvesting* path's directory, so pointing one flag at a lone temporary
        file silently loses the others and falls back to a legacy config that
        names items the Eloria profile does not have.
        """
        shipped = self.server_root / "config" / "eloria"
        if not self._overrides:
            return Path("config") / "eloria"
        assert self._workdir is not None
        copied = Path(self._workdir.name) / "config"
        shutil.copytree(shipped, copied)
        for flag, text in self._overrides.items():
            name = dict(ELORIA_CONFIG)[flag]
            (copied / name).write_text(text, encoding="utf-8")
        return copied

    def _drain_output(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            self._log.append(line.rstrip())

    def recent_log(self, lines: int = 40) -> str:
        return "\n".join(list(self._log)[-lines:])

    async def _wait_for_listener(self) -> None:
        # A TLS-only server never opens the cleartext port, so waiting on it
        # would time out against a server that started perfectly. The TCP
        # connection alone is enough either way: this only needs to know that
        # something is accepting, not to complete a handshake.
        port = self.secure_port or self.port
        for _ in range(200):
            try:
                _reader, writer = await asyncio.open_connection(
                    "127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.05)
        raise RuntimeError("local server did not start:\n" + self.recent_log())


async def read_packet(reader: asyncio.StreamReader, timeout: float = 8.0):
    header = await asyncio.wait_for(reader.readexactly(3), timeout)
    wire_length = struct.unpack_from("<H", header, 1)[0]
    payload = await asyncio.wait_for(
        reader.readexactly(wire_length - 1), timeout)
    return header[0], payload


async def collect_command(reader: asyncio.StreamReader, wanted: int,
                          timeout: float = 8.0) -> bytes:
    while True:
        command, payload = await read_packet(reader, timeout)
        if command == wanted:
            return payload


async def open_client(port: int, ssl_context=None, server_hostname: str = "localhost"):
    """Open a protocol session, in the clear or inside TLS.

    Everything above the socket is identical either way, which is the point:
    a probe proves the protocol survives encryption by running the same
    exchange through both.
    """
    reader, writer = await asyncio.open_connection(
        "127.0.0.1", port, ssl=ssl_context,
        server_hostname=server_hostname if ssl_context else None)
    version = (struct.pack("<HH4B", 10, 31, 1, 9, 7, 0) + bytes(4)
               + struct.pack(">H", port))
    writer.write(packet(SEND_VERSION, version) + packet(SEND_OPENING_SCREEN))
    await writer.drain()
    return reader, writer


def disposable_credentials(prefix: str) -> tuple[str, str]:
    """A name and password held only in memory; neither is ever printed."""
    return prefix + secrets.token_hex(4), secrets.token_urlsafe(28)


async def create_character(port: int, name: str, password: str,
                           ssl_context=None) -> None:
    reader, writer = await open_client(port, ssl_context)
    writer.write(packet(
        CREATE_CHAR,
        (name + " " + password).encode("ascii") + b"\0" + bytes(8)))
    await writer.drain()
    while True:
        command, payload = await read_packet(reader)
        if command == CREATE_CHAR_OK:
            break
        if command == CREATE_CHAR_NOT_OK:
            raise RuntimeError("character creation refused: "
                               + payload.split(b"\0", 1)[0].decode("utf-8", "replace"))
    writer.close()
    await writer.wait_closed()


async def login(port: int, name: str, password: str, ssl_context=None):
    """Log in and return (reader, writer, actor_id) once the world is sent."""
    reader, writer = await open_client(port, ssl_context)
    writer.write(packet(LOG_IN, (name + " " + password).encode("ascii") + b"\0"))
    await writer.drain()
    actor_id = None
    required = {LOG_IN_OK, YOU_ARE, CHANGE_MAP, HERE_YOUR_INVENTORY}
    while required:
        command, payload = await read_packet(reader)
        if command == LOG_IN_NOT_OK:
            raise RuntimeError("login refused: "
                               + payload.split(b"\0", 1)[0].decode("utf-8", "replace"))
        if command == YOU_ARE:
            actor_id = struct.unpack_from("<H", payload)[0]
        required.discard(command)
    return reader, writer, actor_id


async def close_client(writer) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except (ConnectionError, OSError):
        pass


def clean_text(payload: bytes) -> tuple[int, str]:
    """Split a RAW_TEXT payload into (channel, text) without colour bytes."""
    channel = payload[0]
    body = payload[1:].split(b"\0", 1)[0]
    return channel, bytes(
        value for value in body if not 0x7F <= value <= 0x9F).decode(
            "utf-8", "replace")
