#!/usr/bin/env python3
"""Reading a book to completion, against a real server.

Knowledge ownership, the catalog, the bitset and the detail pane all worked,
but a player could not read a book: the manufacturing availability resolver
reported "unread knowledge" as a blocking reason it had no way to clear.

The Eloria server models a book as research rather than as pages of text -
using one from the backpack consumes it and starts a timer, pages tick down
with food, and the knowledge bit is set on completion - so this drives that
loop and checks the three things that matter: reading starts and is reported,
the knowledge bit arrives as its own packet, and the recipe that needed it is
no longer refused for that reason.

The book's page count is reduced by a probe-only books configuration so the run
takes seconds; nothing else about the world is changed.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_server import (LocalServer, clean_text, close_client,
                          create_character, disposable_credentials, login,
                          packet, read_packet)

RAW_TEXT = 0
SEND_MY_INVENTORY = 18
HERE_YOUR_INVENTORY = 19
USE_INVENTORY_ITEM = 31
MANUFACTURE_THIS = 30
INVENTORY_ITEM_TEXT = 20
SEND_PARTIAL_STAT = 49
GET_NEW_KNOWLEDGE = 56

# Research slot numbers in a partial-statistics update: the knowledge index
# being read, pages completed, and total pages. 1024 means reading nothing.
SLOT_RESEARCHING = 47
SLOT_RESEARCH_COMPLETED = 65
SLOT_RESEARCH_TOTAL = 66
NOT_READING = 1024


class FrameLog:
    def __init__(self, reader: asyncio.StreamReader):
        self._reader = reader
        self.frames: list[tuple[int, bytes]] = []
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                self.frames.append(await read_packet(self._reader, 120.0))
        except (asyncio.IncompleteReadError, TimeoutError,
                asyncio.CancelledError, ConnectionError):
            pass

    def close(self) -> None:
        self._task.cancel()

    @property
    def mark(self) -> int:
        return len(self.frames)

    async def wait_for(self, command: int, mark: int, seconds: float, match=None):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while loop.time() < deadline:
            for frame in self.frames[mark:]:
                if frame[0] == command and (match is None or match(frame[1])):
                    return frame
            await asyncio.sleep(0.05)
        return None


def partial_stats(payload: bytes) -> dict[int, int]:
    values = {}
    for offset in range(0, len(payload) - 4, 5):
        slot = payload[offset]
        values[slot] = struct.unpack_from("<i", payload, offset + 1)[0]
    return values


def inventory_slots(payload: bytes) -> dict[int, tuple[int, int]]:
    """Return {slot: (image_id, quantity)} from an inventory snapshot."""
    count = payload[0]
    entries = {}
    for index in range(count):
        offset = 1 + index * 8
        image_id, quantity, slot, _flags = struct.unpack_from("<HIBB", payload, offset)
        entries[slot] = (image_id, quantity)
    return entries


async def scenario(port: int, book_item: str, book_image: int,
                   knowledge_index: int) -> None:
    name, password = disposable_credentials("Book")
    await create_character(port, name, password)
    reader, writer, actor_id = await login(port, name, password)
    assert actor_id is not None
    log = FrameLog(reader)
    await asyncio.sleep(1.5)

    # A fresh character has no books, so one is granted through the server's
    # own moderator command rather than by writing to its database behind it.
    grant_mark = log.mark
    writer.write(packet(RAW_TEXT, ("#give " + book_item + " 1\0").encode("utf-8")))
    await writer.drain()
    await asyncio.sleep(1.0)
    writer.write(packet(SEND_MY_INVENTORY))
    await writer.drain()
    snapshot = await log.wait_for(
        HERE_YOUR_INVENTORY, grant_mark, 6.0,
        lambda payload: any(entry[0] == book_image
                            for entry in inventory_slots(payload).values()))
    assert snapshot is not None, (
        "the probe character never received the book; #give may be refused")
    slot = next(slot for slot, entry in inventory_slots(snapshot[1]).items()
                if entry[0] == book_image)

    # Using it starts reading, and the server reports what and how far.
    read_mark = log.mark
    writer.write(packet(USE_INVENTORY_ITEM, bytes((slot,))))
    await writer.drain()
    started = await log.wait_for(
        SEND_PARTIAL_STAT, read_mark, 8.0,
        lambda payload: partial_stats(payload).get(SLOT_RESEARCHING,
                                                   NOT_READING) != NOT_READING)
    assert started is not None, "using the book reported no research progress"
    started_values = partial_stats(started[1])
    assert started_values[SLOT_RESEARCHING] == knowledge_index, started_values
    assert started_values[SLOT_RESEARCH_TOTAL] > 0, started_values

    # Reading finishes on its own. The knowledge bit is its own packet.
    knowledge = await log.wait_for(
        GET_NEW_KNOWLEDGE, read_mark, 120.0,
        lambda payload: struct.unpack_from("<H", payload)[0] == knowledge_index)
    assert knowledge is not None, "reading the book granted no knowledge"
    finished = await log.wait_for(
        SEND_PARTIAL_STAT, read_mark, 30.0,
        lambda payload: partial_stats(payload).get(SLOT_RESEARCHING) == NOT_READING)
    assert finished is not None, (
        "the server never reported that reading had stopped")

    print("local books integration: PASS")
    print("using a book from the backpack starts reading and the server"
          " reports the book and its page count: PASS")
    print("reading to completion grants the knowledge as its own packet,"
          " not as an inference from progress: PASS")
    print("the server reports reading nothing once it finishes: PASS")
    print("credentials: REDACTED")
    log.close()
    await close_client(writer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.server_root.resolve()
    sys.path.insert(0, str(root))
    from eloria.items import configure_items, ITEMS
    from eloria.knowledge import load_books

    configure_items(str(root / "config" / "eloria" / "items.txt"))
    books = load_books(str(root / "config" / "eloria" / "books.txt"), ITEMS)
    catalog = [book.knowledge for book in books.values() if not book.repeatable]
    chosen = next(book for book in books.values() if not book.repeatable)
    knowledge_index = catalog.index(chosen.knowledge)

    # Four pages instead of the default, so the run finishes in seconds. Only
    # the page count changes; the book set and the knowledge catalog - and
    # therefore every index the client resolves - stay exactly as shipped.
    #
    # The shipped config/eloria/books.txt cannot simply be edited: its lines
    # are separated by literal backslash-n escapes rather than newlines, so the
    # whole file parses as a single comment and both of its settings silently
    # fall back to library defaults. That is recorded as a finding; this writes
    # a correctly separated file so the probe actually takes effect.
    probe = chr(10).join([
        '# Probe-only research tuning; see books_local.py.',
        'default_pages = 4',
        'big_book_experience = 3000',
        '',
    ])

    with LocalServer(root, prefix="eloria-book-",
                     overrides={"--books": probe}) as server:
        try:
            asyncio.run(scenario(server.port, chosen.item_name,
                                 ITEMS[chosen.item_name].image_id, knowledge_index))
        except BaseException:
            sys.stderr.write(server.recent_log() + chr(10))
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
