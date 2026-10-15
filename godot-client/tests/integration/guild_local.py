#!/usr/bin/env python3
"""Prove the guild window against the genuine Eloria server, two clients at once.

Guilds have been in this server from early on and had no surface at all: the
roster was `#list_guild`, a column of chat that scrolled away, and joining one
meant somebody telling you its long name because no screen in the client would
say one. `ELORIA_GUILD_STATE(213)` is that surface, and this drives it end to
end: two real characters log in, one founds a guild and the other applies to
it, and the packets that come back are decoded and checked.

The interesting assertions are the ones a unit test cannot make. That the
founding fee is really charged and the window really changes. That the
applicant appears in the *owner's* packet and the guild appears in the
applicant's. That a member who is nowhere near you is marked online, and stops
being marked online when they disconnect - because a roster that shows the
person who just left as present is worse than no roster.

Credentials are generated per run, held only in memory, and never printed.

Usage: python tests/integration/guild_local.py <server-root>
"""

from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (  # noqa: E402
    LocalServer, clean_text, close_client, create_character,
    disposable_credentials, login, packet, read_packet)

RAW_TEXT = 0
ELORIA_GUILD_STATE = 213
GUILD_CHAT_CHANNEL = 2

CAPABILITIES = "guild_window_v1"

# The permission bits, as `eloria/protocol.py` numbers them.
GUILD_CAN_CHAT = 1 << 0
GUILD_CAN_ACCEPT = 1 << 4
GUILD_CAN_OWN = 1 << 7
GUILD_CAN_LEAVE = 1 << 8

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))
    print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


class Cursor:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def take(self, format_string: str):
        values = struct.unpack_from(format_string, self.payload, self.offset)
        self.offset += struct.calcsize(format_string)
        return values

    def text(self) -> str:
        end = self.payload.index(0, self.offset)
        value = self.payload[self.offset:end].decode("utf-8", "replace")
        self.offset = end + 1
        return value

    def section(self, read_row):
        return [read_row(self) for _ in range(self.take("<H")[0])]


def decode_guild(payload: bytes) -> dict:
    """A reference decoder, written from `docs/guild-window.md`."""
    cursor = Cursor(payload)
    (_version, flags, rank, permissions, create_cost, create_level,
     join_level) = cursor.take("<BBBHIBB")
    state = {
        "in_guild": bool(flags & 1), "rank": rank, "permissions": permissions,
        "create_cost": create_cost, "create_level": create_level,
        "join_level": join_level}
    for field in ("tag", "name", "owner", "motd", "description", "join_info",
                  "url"):
        state[field] = cursor.text()

    def member(inner: Cursor) -> dict:
        member_rank, member_flags = inner.take("<BB")
        return {"rank": member_rank, "online": bool(member_flags & 1),
                "self": bool(member_flags & 2),
                "owner": bool(member_flags & 4), "name": inner.text()}

    state["members"] = cursor.section(member)
    state["applicants"] = cursor.section(lambda inner: inner.text())
    state["allies"] = cursor.section(
        lambda inner: {"tag": inner.text(), "name": inner.text()})
    state["colours"] = cursor.section(
        lambda inner: {"colour": inner.take("<B")[0], "tag": inner.text()})
    state["pending"] = cursor.section(lambda inner: inner.text())
    state["directory"] = cursor.section(
        lambda inner: {"tag": inner.text(), "name": inner.text(),
                       "members": inner.take("<H")[0]})
    state["palette"] = cursor.section(
        lambda inner: {"colour": inner.take("<B")[0], "name": inner.text()})
    return state


async def say(writer, text: str) -> None:
    writer.write(packet(RAW_TEXT, text.encode("utf-8") + b"\0"))
    await writer.drain()


async def next_guild_state(reader, timeout: float = 12.0,
                           until=None) -> dict | None:
    """Read forward until a guild packet satisfies `until` (or any, if None).

    The server pushes this on every change anybody in the guild makes, so a
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
        if command != ELORIA_GUILD_STATE:
            continue
        state = decode_guild(payload)
        if until is None or until(state):
            return state
    return None


async def heard(reader, needle: str, channel: int | None = None,
                limit: int = 60) -> str | None:
    for _ in range(limit):
        try:
            command, payload = await read_packet(reader, timeout=6.0)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return None
        if command != RAW_TEXT or needle.encode("utf-8") not in payload:
            continue
        # Colour bytes out. The line is printed, and a Windows console that
        # cannot encode one takes the whole probe down rather than the check.
        line_channel, line = clean_text(payload)
        if channel is not None and line_channel != channel:
            continue
        return line
    return None


async def drive(server: LocalServer) -> None:
    port = server.port
    owner_name, owner_password = disposable_credentials("QA_GuildA_")
    member_name, member_password = disposable_credentials("QA_GuildB_")
    await create_character(port, owner_name, owner_password)
    await create_character(port, member_name, member_password)

    owner_reader, owner_writer, _ = await login(port, owner_name, owner_password)
    member_reader, member_writer, _ = await login(
        port, member_name, member_password)
    for writer in (owner_writer, member_writer):
        await say(writer, "#clientcaps " + CAPABILITIES)

    # Declaring the capability is what makes the window exist at all: the
    # server sends the state from the handler that reads `#clientcaps`.
    opening = await next_guild_state(owner_reader)
    check("declaring the capability brings the window with it",
          opening is not None and not opening["in_guild"], str(opening is None))
    if opening:
        check("a player in no guild is told what founding one costs",
              opening["create_cost"] > 0 and opening["create_level"] > 0
              and opening["join_level"] > 0,
              f"{opening['create_cost']} gold, skill {opening['create_level']}")
        check("and the colour words #set_guild_color accepts",
              len(opening["palette"]) > 0 and all(
                  entry["name"] for entry in opening["palette"]),
              f"{len(opening['palette'])} colours")

    # Founding one for real, fee and level requirement included.
    await say(owner_writer, "#boost att 39")
    await say(owner_writer, "#give Gold Coins 30000")
    await say(owner_writer, "#make_guild QAG")
    founded = await next_guild_state(
        owner_reader, until=lambda state: state["in_guild"])
    check("a character who meets the requirements founds a guild",
          founded is not None and founded["tag"] == "QAG",
          str(founded["tag"] if founded else None))
    if founded:
        check("the founder owns it, and is told so rather than left to infer it",
              founded["rank"] == 20
              and bool(founded["permissions"] & GUILD_CAN_OWN)
              and not founded["permissions"] & GUILD_CAN_LEAVE,
              f"rank {founded['rank']}, permissions {founded['permissions']:#x}")
        check("the founder's own row is the one flagged as theirs",
              len(founded["members"]) == 1 and founded["members"][0]["self"]
              and founded["members"][0]["owner"], str(founded["members"]))

    long_name = "QA Guild " + owner_name[-6:]
    await say(owner_writer, "#set_name " + long_name)
    named = await next_guild_state(
        owner_reader, until=lambda state: state["name"] == long_name)
    check("the long name reaches the window", named is not None,
          str(named["name"] if named else None))

    # The other player has to be able to find the guild before they can ask to
    # join it: `#join_guild` takes the long name, and until the directory was
    # on the wire nothing in the client knew one.
    await say(member_writer, "#guild_info")
    listed = await next_guild_state(
        member_reader,
        until=lambda state: any(entry["name"] == long_name
                                for entry in state["directory"]))
    check("a guildless player can find the guild's long name in the directory",
          listed is not None,
          str([entry["tag"] for entry in listed["directory"]]) if listed else "")

    await say(member_writer, "#boost att 20")
    await say(member_writer, "#join_guild " + long_name)
    applied = await next_guild_state(
        member_reader, until=lambda state: state["pending"] == [long_name])
    check("applying tells the applicant which guild they applied to",
          applied is not None, str(applied["pending"] if applied else None))
    queued = await next_guild_state(
        owner_reader, until=lambda state: bool(state["applicants"]))
    check("and puts them in the queue of whoever may accept",
          queued is not None and queued["applicants"][0].casefold()
          == member_name.casefold(),
          str(queued["applicants"] if queued else None))
    if queued:
        check("who is told they may accept rather than having to guess",
              bool(queued["permissions"] & GUILD_CAN_ACCEPT), "")

    await say(owner_writer, "#accept " + member_name)
    joined = await next_guild_state(
        owner_reader, until=lambda state: len(state["members"]) == 2)
    check("accepting makes a guild of two", joined is not None,
          str(len(joined["members"]) if joined else 0))
    if joined:
        # The point of the roster: somebody who is not on your screen.
        check("a member who is nowhere near you is marked as online",
              all(entry["online"] for entry in joined["members"]),
              str([(entry["name"], entry["online"])
                   for entry in joined["members"]]))
        check("the roster puts the people who are here first",
              [entry["online"] for entry in joined["members"]]
              == sorted([entry["online"] for entry in joined["members"]],
                        reverse=True), "")
    accepted = await next_guild_state(
        member_reader, until=lambda state: state["in_guild"])
    check("and the new member's own window fills in",
          accepted is not None and accepted["tag"] == "QAG"
          and accepted["rank"] == 0
          and bool(accepted["permissions"] & GUILD_CAN_LEAVE),
          str(accepted["tag"] if accepted else None))

    await say(owner_writer, "#set_motd Muster at the north gate.")
    read_motd = await next_guild_state(
        member_reader, until=lambda state: bool(state["motd"]))
    check("the message of the day reaches the members it is for",
          read_motd is not None
          and read_motd["motd"] == "Muster at the north gate.",
          str(read_motd["motd"] if read_motd else None))

    await say(owner_writer, "#change_rank %s 5" % member_name)
    promoted = await next_guild_state(
        member_reader, until=lambda state: state["rank"] == 5)
    check("a promotion changes what the promoted member is offered",
          promoted is not None
          and bool(promoted["permissions"] & GUILD_CAN_CHAT),
          f"rank {promoted['rank'] if promoted else '?'}")

    # Guild chat, on the channel the client now has a tab for.
    await say(member_writer, "#gm mustering now")
    line = await heard(owner_reader, "mustering now", GUILD_CHAT_CHANNEL)
    check("guild chat reaches the guild on the channel the tab reads",
          line is not None, line or "")

    # The whole point of the online marks: they have to stop being true.
    await close_client(member_writer)
    absent = await next_guild_state(
        owner_reader, timeout=20.0,
        until=lambda state: any(not entry["online"]
                                for entry in state["members"]))
    check("a member who disconnects is marked offline rather than left present",
          absent is not None and len(absent["members"]) == 2,
          str([(entry["name"], entry["online"]) for entry in absent["members"]])
          if absent else "no push after the disconnect")

    await close_client(owner_writer)


async def the_gate(server: LocalServer) -> None:
    """A client that never declares the capability is sent no guild packet."""
    port = server.port
    name, password = disposable_credentials("QA_GuildC_")
    await create_character(port, name, password)
    reader, writer, _ = await login(port, name, password)

    # No `#clientcaps`. The chat the command always produced must be untouched,
    # and no 213 may arrive.
    await say(writer, "#guild_info")
    line = await heard(reader, "not in a guild")
    check("a client that cannot decode the packet still gets the chat",
          line is not None, line or "")
    state = await next_guild_state(reader, timeout=2.0)
    check("and is sent no guild packet at all", state is None,
          "a packet arrived" if state else "")
    await close_client(writer)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with LocalServer(Path(sys.argv[1]).resolve(), prefix="eloria-guild-") as server:
        asyncio.run(drive(server))
        asyncio.run(the_gate(server))
        failures = [label for label, passed, _ in results if not passed]
        print()
        print(f"{len(results) - len(failures)}/{len(results)} checks passed")
        if failures:
            print("server log tail:")
            print(server.recent_log(25))
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
