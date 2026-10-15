#!/usr/bin/env python3
"""Minimal local Eloria protocol server for offline client integration tests.

This is a *test fixture*, not a game server. It speaks just enough of the
documented wire protocol (see godot-client/src/network/protocol.gd) for the real
Godot client to connect, create a character, log in, be placed on a map, walk
under MOVE_TO/RUN_TO, chat and see other connected clients. It exists so map
work can be validated through the genuine login and gameplay flow without
touching a shared or production database.

Usage:
    python3 local_protocol_server.py --port 2000 --map four_gates \
        --spawn 384 266
"""

from __future__ import annotations

import argparse
import selectors
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --- client -> server -------------------------------------------------------
MOVE_TO = 1
SEND_PM = 2
RUN_TO = 6
SIT_DOWN = 7
SEND_ME_MY_ACTORS = 8
SEND_OPENING_SCREEN = 9
SEND_VERSION = 10
HEART_BEAT = 14
LOCATE_ME = 15
PING_RESPONSE = 60
SET_ACTIVE_CHANNEL = 61
LOG_IN = 140
CREATE_CHAR = 141
RAW_TEXT_C = 0

# --- server -> client -------------------------------------------------------
RAW_TEXT = 0
ADD_NEW_ACTOR = 1
ADD_ACTOR_COMMAND = 2
YOU_ARE = 3
SYNC_CLOCK = 4
NEW_MINUTE = 5
REMOVE_ACTOR = 6
CHANGE_MAP = 7
KILL_ALL_ACTORS = 9
PONG = 11
HERE_YOUR_STATS = 18
HERE_YOUR_INVENTORY = 19
ADD_NEW_ENHANCED_ACTOR = 51
GET_KNOWLEDGE_LIST = 74
PING_REQUEST = 60
LOG_IN_OK = 250
LOG_IN_NOT_OK = 251
CREATE_CHAR_OK = 252
CREATE_CHAR_NOT_OK = 253

# actor command codes used by the client's animation resolver
CMD_WALK = {(0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4,
            (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}
CMD_TURN = {(0, -1): 24, (1, -1): 23, (1, 0): 22, (1, 1): 21,
            (0, 1): 20, (-1, 1): 27, (-1, 0): 26, (-1, -1): 25}
CMD_STAND = 14
CMD_SIT = 13


def frame(command: int, payload: bytes = b"") -> bytes:
    return bytes((command,)) + struct.pack("<H", len(payload) + 1) + payload


@dataclass
class Player:
    conn: socket.socket
    actor_id: int
    name: str = ""
    password: str = ""
    x: int = 384
    y: int = 266
    rotation: int = 0
    logged_in: bool = False
    sitting: bool = False
    buffer: bytearray = field(default_factory=bytearray)
    path: List[Tuple[int, int]] = field(default_factory=list)
    next_step: float = 0.0


class LocalServer:
    """Single-threaded selector loop; deterministic and easy to reason about."""

    def __init__(self, host: str, port: int, map_name: str,
                 spawn: Tuple[int, int], step_seconds: float = 0.22,
                 verbose: bool = False):
        self.map_name = map_name
        self.spawn = spawn
        self.step_seconds = step_seconds
        self.verbose = verbose
        self.selector = selectors.DefaultSelector()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((host, port))
        self.listener.listen(8)
        self.listener.setblocking(False)
        self.selector.register(self.listener, selectors.EVENT_READ, None)
        self.players: Dict[socket.socket, Player] = {}
        self._next_actor_id = 100
        self._accounts: Dict[str, str] = {}
        self.running = True
        self.port = self.listener.getsockname()[1]

    # ------------------------------------------------------------------ frames
    def send(self, player: Player, data: bytes) -> None:
        try:
            player.conn.sendall(data)
        except OSError:
            self.drop(player)

    def broadcast(self, data: bytes, skip: Optional[Player] = None) -> None:
        for player in list(self.players.values()):
            if player is skip or not player.logged_in:
                continue
            self.send(player, data)

    def log(self, *parts) -> None:
        if self.verbose:
            print("[local-server]", *parts, flush=True)

    # ----------------------------------------------------------------- payloads
    def enhanced_actor(self, player: Player) -> bytes:
        payload = bytearray(58)
        struct.pack_into("<H", payload, 0, player.actor_id)
        struct.pack_into("<H", payload, 2, player.x & 0x7FF)
        struct.pack_into("<H", payload, 4, player.y & 0x7FF)
        struct.pack_into("<h", payload, 8, player.rotation)
        payload[10] = 1                       # actor type: luminous male
        payload[11] = 0
        payload[12:22] = bytes((0, 0, 0, 0, 0, 0, 11, 11, 11, 11))
        payload[22] = CMD_SIT if player.sitting else CMD_STAND
        struct.pack_into("<H", payload, 23, 120)   # max health
        struct.pack_into("<H", payload, 25, 120)   # health
        payload[27] = 1                       # kind: human player
        name = player.name.encode("ascii", "ignore")[:29]
        payload[28:28 + len(name)] = name
        return frame(ADD_NEW_ENHANCED_ACTOR, bytes(payload))

    @staticmethod
    def stats() -> bytes:
        payload = bytearray(236)
        for index in range(12):                       # attributes: 8/8
            struct.pack_into("<h", payload, index * 4, 8)
            struct.pack_into("<h", payload, index * 4 + 2, 8)
        for slot in (24, 26, 28, 30, 32, 34, 36, 38, 83, 89, 95, 101, 107):
            struct.pack_into("<h", payload, slot * 2, 1)
            struct.pack_into("<h", payload, (slot + 1) * 2, 1)
        return frame(HERE_YOUR_STATS, bytes(payload))

    # -------------------------------------------------------------------- flow
    def place(self, player: Player) -> None:
        self.send(player, frame(YOU_ARE, struct.pack("<H", player.actor_id)))
        self.send(player, frame(CHANGE_MAP, self.map_name.encode() + b"\0"))
        self.send(player, frame(KILL_ALL_ACTORS))
        self.send(player, self.stats())
        self.send(player, frame(HERE_YOUR_INVENTORY, bytes(1)))
        self.send(player, frame(GET_KNOWLEDGE_LIST, bytes(32)))
        self.send(player, frame(SYNC_CLOCK, struct.pack("<I", int(time.time()))))
        self.send(player, frame(NEW_MINUTE, struct.pack("<H", 180)))
        for other in self.players.values():
            if other.logged_in:
                self.send(player, self.enhanced_actor(other))
        self.broadcast(self.enhanced_actor(player), skip=player)
        self.log(f"placed {player.name} id={player.actor_id} "
                 f"tile=({player.x},{player.y}) map={self.map_name}")

    def drop(self, player: Player) -> None:
        if player.conn in self.players:
            del self.players[player.conn]
        try:
            self.selector.unregister(player.conn)
        except (KeyError, ValueError):
            pass
        try:
            player.conn.close()
        except OSError:
            pass
        if player.logged_in:
            self.broadcast(frame(REMOVE_ACTOR, struct.pack("<H", player.actor_id)))
            self.log(f"removed {player.name} id={player.actor_id}")

    # ---------------------------------------------------------------- handlers
    def handle(self, player: Player, command: int, payload: bytes) -> None:
        if command == SEND_VERSION:
            return
        if command == SEND_OPENING_SCREEN:
            self.send(player, frame(RAW_TEXT, b"\x00Local test server\0"))
            return
        if command == CREATE_CHAR:
            text = payload.split(b"\0", 1)[0].decode("ascii", "ignore")
            parts = text.split(" ")
            if len(parts) < 2 or not parts[0]:
                self.send(player, frame(CREATE_CHAR_NOT_OK, b"bad name\0"))
                return
            self._accounts[parts[0].lower()] = parts[1]
            self.send(player, frame(CREATE_CHAR_OK))
            self.log("created character", parts[0])
            return
        if command == LOG_IN:
            text = payload.split(b"\0", 1)[0].decode("ascii", "ignore")
            parts = text.split(" ")
            if len(parts) < 2:
                self.send(player, frame(LOG_IN_NOT_OK, b"bad credentials\0"))
                return
            name, password = parts[0], parts[1]
            stored = self._accounts.get(name.lower())
            if stored is not None and stored != password:
                self.send(player, frame(LOG_IN_NOT_OK, b"wrong password\0"))
                return
            self._accounts.setdefault(name.lower(), password)
            player.name = name
            player.password = password
            player.logged_in = True
            player.x, player.y = self.spawn
            self.send(player, frame(LOG_IN_OK))
            self.place(player)
            return
        if not player.logged_in:
            return
        if command in (MOVE_TO, RUN_TO):
            if len(payload) >= 4:
                tx, ty = struct.unpack_from("<HH", payload, 0)
                player.path = self.route(player, tx, ty)
                player.next_step = 0.0
                self.log(f"{player.name} move_to ({tx},{ty}) steps={len(player.path)}")
            return
        if command == SIT_DOWN:
            player.sitting = bool(payload and payload[0])
            self.broadcast(frame(ADD_ACTOR_COMMAND, struct.pack(
                "<HB", player.actor_id, CMD_SIT if player.sitting else CMD_STAND)))
            return
        if command == LOCATE_ME:
            message = f"\x00You are at [{player.x},{player.y}] in {self.map_name}"
            self.send(player, frame(RAW_TEXT, message.encode() + b"\0"))
            return
        if command == RAW_TEXT_C:
            text = payload.split(b"\0", 1)[0].decode("utf-8", "ignore")
            if text.startswith("#goto "):
                # Test hook: move this player to another map the way a real
                # server does when a client walks into a portal.
                parts = text.split(" ", 2)
                target = parts[1]
                spawn = self.spawn
                if len(parts) > 2:
                    try:
                        sx, sy = parts[2].split(",")
                        spawn = (int(sx), int(sy))
                    except ValueError:
                        pass
                self.broadcast(frame(REMOVE_ACTOR,
                                     struct.pack("<H", player.actor_id)),
                               skip=player)
                player.path = []
                player.x, player.y = spawn
                self.send(player, frame(CHANGE_MAP, target.encode() + b"\0"))
                self.send(player, frame(KILL_ALL_ACTORS))
                self.send(player, self.enhanced_actor(player))
                self.log(f"{player.name} -> {target} at {spawn}")
                return
            line = f"\x01{player.name}: {text}"
            self.broadcast(frame(RAW_TEXT, line.encode() + b"\0"))
            return
        if command == SEND_ME_MY_ACTORS:
            for other in self.players.values():
                if other.logged_in:
                    self.send(player, self.enhanced_actor(other))
            return
        if command in (HEART_BEAT, PING_RESPONSE, SET_ACTIVE_CHANNEL, SEND_PM):
            return

    @staticmethod
    def route(player: Player, tx: int, ty: int) -> List[Tuple[int, int]]:
        """Straight Chebyshev walk; the map's own collision is not simulated."""
        path: List[Tuple[int, int]] = []
        cx, cy = player.x, player.y
        for _ in range(4000):
            if (cx, cy) == (tx, ty):
                break
            cx += (tx > cx) - (tx < cx)
            cy += (ty > cy) - (ty < cy)
            path.append((cx, cy))
        return path

    def step_movement(self, now: float) -> None:
        for player in list(self.players.values()):
            if not player.logged_in or not player.path:
                continue
            if now < player.next_step:
                continue
            nx, ny = player.path.pop(0)
            dx, dy = nx - player.x, ny - player.y
            player.x, player.y = nx, ny
            player.next_step = now + self.step_seconds
            code = CMD_WALK.get((dx, dy))
            if code is not None:
                self.broadcast(frame(ADD_ACTOR_COMMAND,
                                     struct.pack("<HB", player.actor_id, code)))
            # re-add so every client has the authoritative tile
            self.broadcast(self.enhanced_actor(player))

    # -------------------------------------------------------------------- loop
    def serve_forever(self) -> None:
        while self.running:
            for key, _mask in self.selector.select(timeout=0.05):
                if key.data is None:
                    self.accept()
                else:
                    self.read(key.data)
            self.step_movement(time.monotonic())

    def accept(self) -> None:
        conn, _addr = self.listener.accept()
        conn.setblocking(False)
        self._next_actor_id += 1
        player = Player(conn=conn, actor_id=self._next_actor_id,
                        x=self.spawn[0], y=self.spawn[1])
        self.players[conn] = player
        self.selector.register(conn, selectors.EVENT_READ, player)
        self.log("connection accepted, actor id", player.actor_id)

    def read(self, player: Player) -> None:
        try:
            chunk = player.conn.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self.drop(player)
            return
        if not chunk:
            self.drop(player)
            return
        player.buffer.extend(chunk)
        while len(player.buffer) >= 3:
            wire_length = struct.unpack_from("<H", player.buffer, 1)[0]
            total = wire_length + 2
            if wire_length < 1 or len(player.buffer) < total:
                break
            command = player.buffer[0]
            payload = bytes(player.buffer[3:total])
            del player.buffer[:total]
            self.handle(player, command, payload)

    def stop(self) -> None:
        self.running = False
        try:
            self.listener.close()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    # An Eloria map id. eloria-server still names its maps by the path of
    # an Eternal Lands map file; the client normalises either form, and
    # test_protocol.gd is what holds that compatibility.
    parser.add_argument("--map", default="four_gates")
    parser.add_argument("--spawn", nargs=2, type=int, default=[384, 266])
    parser.add_argument("--step-seconds", type=float, default=0.05,
                        help="server tick between walk steps")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    server = LocalServer(args.host, args.port, args.map,
                         (args.spawn[0], args.spawn[1]),
                         step_seconds=args.step_seconds, verbose=not args.quiet)
    print(f"local protocol server listening on {args.host}:{server.port} "
          f"map={args.map} spawn={tuple(args.spawn)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
