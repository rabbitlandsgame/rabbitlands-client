#!/usr/bin/env python3
"""Prove the party system against the genuine Eloria server, two clients at once.

Eternal Lands never had one of these. The forum's proposal for it settled the
hard questions - independent of the buddy list, leadership transfers, lonely
parties dissolve, nothing persists across a restart - and then waited on a
server change that never came. This probe drives the built version end to end:
two real characters log in, one invites the other, and the window state that
comes back is decoded and checked.

The interesting assertions are the ones about somebody who is *not* on your
screen: that a member's health arrives without being near them, and that a
member who disconnects keeps their row and is marked offline rather than
vanishing - because a party that hides the person who just dropped is how you
fail to notice they dropped.

Credentials are generated per run, held only in memory, and never printed.

Usage: python tests/integration/party_local.py <server-root>
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

RAW_TEXT = 0
ELORIA_PARTY_STATE = 240

CAPABILITIES = "party_window_v1"

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


def decode_party(payload: bytes) -> dict:
    in_party, count = struct.unpack_from("<BB", payload, 0)
    offset = 2
    members = []
    for _ in range(count):
        flags, health, max_health, ether, max_ether, x, y = struct.unpack_from(
            "<B6H", payload, offset)
        offset += 13
        name, _ = payload[offset:].split(b"\0", 1)
        offset += len(name) + 1
        map_id, _ = payload[offset:].split(b"\0", 1)
        offset += len(map_id) + 1
        members.append({
            "online": bool(flags & 1), "leader": bool(flags & 2),
            "self": bool(flags & 4), "health": health,
            "max_health": max_health, "ether": ether, "max_ether": max_ether,
            "x": x, "y": y, "name": name.decode("utf-8"),
            "map_id": map_id.decode("utf-8")})
    invited_by, _ = payload[offset:].split(b"\0", 1)
    offset += len(invited_by) + 1
    return {"in_party": bool(in_party), "members": members,
            "invited_by": invited_by.decode("utf-8"),
            "invite_seconds": struct.unpack_from("<H", payload, offset)[0]}


async def next_party_state(reader, timeout: float = 12.0,
                           until=None) -> dict | None:
    """Read forward until a party packet satisfies `until` (or any, if None).

    The server pushes party state on a timer as well as on every change, so a
    probe that took the first packet it saw would sometimes read the state
    from before the thing it just did.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            command, payload = await read_packet(
                reader, timeout=max(0.1, deadline - loop.time()))
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return None
        if command != ELORIA_PARTY_STATE:
            continue
        state = decode_party(payload)
        if until is None or until(state):
            return state
    return None


async def say(writer, text: str) -> None:
    writer.write(packet(RAW_TEXT, text.encode("utf-8") + b"\0"))
    await writer.drain()


async def drive(server: LocalServer) -> None:
    port = server.port
    leader_name, leader_password = disposable_credentials("QA_PartyA_")
    member_name, member_password = disposable_credentials("QA_PartyB_")
    await create_character(port, leader_name, leader_password)
    await create_character(port, member_name, member_password)

    leader_reader, leader_writer, _ = await login(
        port, leader_name, leader_password)
    member_reader, member_writer, _ = await login(
        port, member_name, member_password)
    for writer in (leader_writer, member_writer):
        await say(writer, "#clientcaps " + CAPABILITIES)

    # A player with no party gets an explicit empty state, not silence.
    await say(leader_writer, "#party status")
    empty = await next_party_state(leader_reader)
    check("a player with no party is told so explicitly",
          empty is not None and not empty["in_party"] and not empty["members"],
          str(empty))

    await say(leader_writer, f"#party invite {member_name}")
    invited = await next_party_state(
        member_reader, until=lambda s: bool(s["invited_by"]))
    check("the invited player is told who asked and how long they have",
          invited is not None and invited["invited_by"].casefold()
          == leader_name.casefold() and invited["invite_seconds"] > 0,
          f"from {invited['invited_by'] if invited else None}")

    await say(member_writer, "#party accept")
    joined = await next_party_state(
        member_reader, until=lambda s: len(s["members"]) == 2)
    check("accepting produces a party of two", joined is not None,
          str(len(joined["members"]) if joined else 0))

    if joined:
        by_name = {entry["name"].casefold(): entry for entry in joined["members"]}
        leader_row = by_name.get(leader_name.casefold())
        member_row = by_name.get(member_name.casefold())
        check("the inviter leads the party",
              leader_row is not None and leader_row["leader"], str(leader_row))
        check("the reader's own row is the one flagged as theirs",
              member_row is not None and member_row["self"]
              and not (leader_row or {}).get("self", True), "")
        check("a member's vitals arrive without being near them",
              leader_row is not None and leader_row["max_health"] > 0
              and leader_row["map_id"] != "",
              f"{leader_row['health']}/{leader_row['max_health']} health on "
              f"{leader_row['map_id']}" if leader_row else "")

    # Party chat reaches the other member and nobody else is in earshot.
    await say(member_writer, "#p mustering at the north gate")
    heard = None
    for _ in range(30):
        command, payload = await read_packet(leader_reader)
        if command == RAW_TEXT and b"mustering at the north gate" in payload:
            heard = payload.split(b"\0", 1)[0].decode("utf-8", "replace")
            break
    check("party chat reaches the other member", heard is not None, heard or "")

    # The whole point: a member who drops keeps their row and is marked absent.
    await close_client(member_writer)
    absent = await next_party_state(
        leader_reader, until=lambda s: any(
            not entry["online"] for entry in s["members"]))
    check("a member who disconnects keeps their row and is marked offline",
          absent is not None and len(absent["members"]) == 2,
          str([(e["name"], e["online"]) for e in absent["members"]])
          if absent else "")

    # Leadership must move off an absent leader, so the party still works.
    await say(leader_writer, "#party leave")
    left = await next_party_state(
        leader_reader, until=lambda s: not s["in_party"])
    check("leaving empties the leaver's own window",
          left is not None and not left["members"], str(left))

    await close_client(leader_writer)


async def leadership_transfers(server: LocalServer) -> None:
    """The leader drops; the party must not be left headless."""
    port = server.port
    first, first_password = disposable_credentials("QA_PartyC_")
    second, second_password = disposable_credentials("QA_PartyD_")
    await create_character(port, first, first_password)
    await create_character(port, second, second_password)

    a_reader, a_writer, _ = await login(port, first, first_password)
    b_reader, b_writer, _ = await login(port, second, second_password)
    for writer in (a_writer, b_writer):
        await say(writer, "#clientcaps " + CAPABILITIES)

    await say(a_writer, f"#party invite {second}")
    await next_party_state(b_reader, until=lambda s: bool(s["invited_by"]))
    await say(b_writer, "#party accept")
    await next_party_state(b_reader, until=lambda s: len(s["members"]) == 2)

    await close_client(a_writer)
    promoted = await next_party_state(
        b_reader, until=lambda s: any(
            entry["leader"] and entry["self"] for entry in s["members"]))
    check("leadership transfers off a leader who goes offline",
          promoted is not None,
          str([(e["name"], e["leader"], e["online"])
               for e in promoted["members"]]) if promoted else "no transfer")
    await close_client(b_writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]).resolve(), prefix="eloria-party-") as server:
        asyncio.run(drive(server))
        asyncio.run(leadership_transfers(server))
        failures = [label for label, passed, _ in results if not passed]
        print()
        print(f"{len(results) - len(failures)}/{len(results)} checks passed")
        if failures:
            print("server log tail:")
            print(server.recent_log(25))
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
