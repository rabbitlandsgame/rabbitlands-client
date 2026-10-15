#!/usr/bin/env python3
"""Prove the game protocol runs inside TLS against the genuine Eloria server.

The login packet carries a username and a password. Until this landed they
crossed the wire in the clear, along with every private message after them.
This probe starts a real `eloria.server` with a certificate, completes a real
handshake, and drives the same exchange a cleartext client drives - character
creation, login, chat, a private message - to show the protocol is unchanged
by the encryption underneath it.

Three things are worth proving separately, and this proves all three:

  1. A verifying client - one that checks the certificate against a trust
     anchor and checks the hostname - completes the handshake. A probe that
     turned verification off would pass against a server impersonating any
     other, which is the attack encryption exists to stop.
  2. The protocol survives. TLS record boundaries are not frame boundaries,
     so several frames written together must arrive as several frames.
  3. A client that does not verify, or connects in the clear, gets nothing.

Credentials are generated per run, held only in memory, and never printed;
the report records them as REDACTED.

Usage: python tests/integration/secure_login_local.py <server-root>
"""

from __future__ import annotations

import asyncio
import socket
import ssl
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (  # noqa: E402
    LocalServer, close_client, collect_command, create_character,
    disposable_credentials, login, open_client, packet, read_packet)

RAW_TEXT = 0
SEND_PM = 2
GET_ACTIVE_CHANNELS = 71
HEART_BEAT = 14
LOG_IN_OK = 250

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def verifying_context(certificate_path: Path) -> ssl.SSLContext:
    """A client that actually checks the certificate it is offered."""
    context = ssl.create_default_context(cafile=str(certificate_path))
    context.check_hostname = True
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


async def drive(server: LocalServer, certificate_path: Path) -> None:
    port = server.secure_port
    context = verifying_context(certificate_path)

    name, password = disposable_credentials("QA_TLS_")
    await create_character(port, name, password, ssl_context=context)
    check("a character is created over TLS", True, "credentials: REDACTED")

    reader, writer, actor_id = await login(
        port, name, password, ssl_context=context)
    check("the login handshake completes and the world arrives",
          actor_id is not None, f"actor {actor_id}")

    # Several frames in one write: a TLS record boundary must not be mistaken
    # for a protocol frame boundary at either end.
    writer.write(packet(HEART_BEAT) + packet(GET_ACTIVE_CHANNELS)
                 + packet(RAW_TEXT, b"#day\0"))
    await writer.drain()
    text = await collect_command(reader, RAW_TEXT)
    check("three frames written together are read as three frames",
          bool(text), text[:48].split(b"\0", 1)[0].decode("utf-8", "replace"))

    # A private message is the traffic most obviously worth encrypting. What
    # the server answers is not the point and varies (a message addressed to
    # yourself is refused); that an answer comes back through the tunnel at
    # all is, so several replies are collected rather than only the first.
    writer.write(packet(SEND_PM, f"{name} probe message\0".encode("utf-8")))
    await writer.drain()
    replies: list[str] = []
    for _ in range(6):
        try:
            payload = await asyncio.wait_for(
                collect_command(reader, RAW_TEXT), 3.0)
        except asyncio.TimeoutError:
            break
        replies.append(payload.split(b"\0", 1)[0].decode("utf-8", "replace"))
        if "probe message" in replies[-1]:
            break
    check("a private message is answered inside the tunnel", bool(replies),
          " | ".join(replies[-2:]))

    await close_client(writer)


async def refuse_unverified(server: LocalServer) -> None:
    """A self-signed certificate must fail a client that checks properly."""
    empty = ssl.create_default_context()
    empty.check_hostname = True
    try:
        await open_client(server.secure_port, empty)
        check("an untrusted certificate is refused", False,
              "the handshake succeeded, so nothing was verified")
    except ssl.SSLCertVerificationError as exc:
        check("an untrusted certificate is refused", True,
              type(exc).__name__)
    except (ssl.SSLError, OSError) as exc:
        check("an untrusted certificate is refused", True, type(exc).__name__)


async def refuse_cleartext(server: LocalServer) -> None:
    """The point of the exercise: no login may be accepted unencrypted."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", server.secure_port), 10)
        writer.write(packet(140, b"someone somepassword\0"))
        await writer.drain()
        try:
            command, _payload = await read_packet(reader, timeout=3.0)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError,
                ConnectionError, OSError):
            command = None
        await close_client(writer)
        check("a cleartext login on the TLS port is not accepted",
              command != LOG_IN_OK, f"first command back: {command}")
    except (ConnectionError, OSError) as exc:
        check("a cleartext login on the TLS port is not accepted", True,
              type(exc).__name__)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    server_root = Path(sys.argv[1]).resolve()

    sys.path.insert(0, str(server_root))
    try:
        from tools.make_dev_certificate import write_certificate
    except ImportError:
        print("SKIP the certificate tool needs the 'cryptography' package")
        return 0

    with tempfile.TemporaryDirectory(prefix="eloria-tls-") as certificate_dir:
        certificate_path, key_path = write_certificate(
            Path(certificate_dir), ["localhost", "127.0.0.1"])
        secure_port = free_port()
        extra = ["--tls-cert", str(certificate_path),
                 "--tls-key", str(key_path),
                 "--tls-port", str(secure_port)]
        with LocalServer(server_root, prefix="eloria-tls-",
                         extra_arguments=extra,
                         secure_port=secure_port) as server:
            server.secure_port = secure_port
            asyncio.run(drive(server, certificate_path))
            asyncio.run(refuse_unverified(server))
            asyncio.run(refuse_cleartext(server))
            failures = [label for label, passed, _ in results if not passed]
            print()
            print(f"{len(results) - len(failures)}/{len(results)} checks passed")
            if failures:
                print("server log tail:")
                print(server.recent_log(25))
            return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
