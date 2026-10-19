"""Run the real game and server with a disposable local mount-test character.

The test server is loopback-only, uses current authored terrain, and shuts down
when the game exits. No installed account, production database or remote server
is changed. --probe checks the multiplayer wire without opening the game.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "godot-client/tests/integration"))
from local_server import LocalServer, create_character, disposable_credentials, login, packet, read_packet


async def frames(reader, seconds=.3):
    output = []
    stop = asyncio.get_running_loop().time() + seconds
    while (remaining := stop - asyncio.get_running_loop().time()) > 0:
        try:
            output.append(await read_packet(reader, remaining))
        except asyncio.TimeoutError:
            break
    return output


async def chat(writer, text):
    writer.write(packet(0, text.encode() + b"\0"))
    await writer.drain()


async def state(reader, actor_id, mode, seconds=5):
    stop = asyncio.get_running_loop().time() + seconds
    while (remaining := stop - asyncio.get_running_loop().time()) > 0:
        command, payload = await read_packet(reader, remaining)
        if command == 198:
            for row in json.loads(payload)["states"]:
                if row["actor_id"] == actor_id and row["mode"] == mode:
                    return row
    raise AssertionError(f"mount state {mode} never arrived")


def place_test_character(live, username):
    # Only this harness's newly created disposable database is writable here.
    path = Path(live._workdir.name) / "eloria.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("UPDATE characters SET map_id=?, x=?, y=?, quest_state=? WHERE username=?", (live.mount_map, *live.mount_spawn, json.dumps({"nymara_intro": 99, "nymara_intro_skipped": 1}), username))


def test_spawn(server, terrain, map_id="four_gates"):
    sys.path.insert(0, str(server))
    from eloria.collision import load_elm_collision
    collision = load_elm_collision(terrain / f"maps/nymara/{map_id}.elm")
    arrival = (309, 162)
    if map_id != "four_gates":
        publication = json.loads((server / "config/eloria/client_content_manifest.json").read_text())
        arrival = publication["continentV2"]["maps"][map_id]["arrival"]
    # An open flat patch beyond the arrival NPCs, found from current terrain.
    for radius in range(12, 100):
        for x, y in ((arrival[0] + dx, arrival[1] + dy) for dx in range(-radius, radius + 1)
                     for dy in (-radius, radius)):
            if all(collision.walkable(x + dx, y + dy)
                   and collision.can_step(x, y, x + dx, y + dy, 2)
                   for dx in range(-3, 4) for dy in range(-3, 4)):
                return x, y
    raise RuntimeError(f"No open mounted test area near {map_id} arrival")


async def probe(live):
    port = live.port
    users = [disposable_credentials(prefix) for prefix in ("ride", "watch", "legacy")]
    for user in users:
        await create_character(port, *user)
        place_test_character(live, user[0])
    peers = [await login(port, *user) for user in users]
    (reader, writer, actor_id), (watch, watch_writer, _), (legacy, _, _) = peers
    try:
        capabilities = ("mounts_v1,mount_selection_v1,crystalback_mount_v1,"
                        "rabbit_mount_v1,raptor_mount_v1,continent_v2_maps_v1")
        await chat(writer, "#clientcaps " + capabilities)
        await chat(watch_writer, "#clientcaps " + capabilities)
        ready = await state(reader, actor_id, "on_foot")
        assert ready["can_summon"], ready
        await chat(writer, "#mount ride " + live.mount_id)
        await state(reader, actor_id, "summoning")
        mounted = await state(reader, actor_id, "mounted")
        assert mounted["mount_id"] == live.mount_id
        await state(watch, actor_id, "mounted")
        assert all(command != 198 for command, _ in await frames(legacy)), "legacy client received mount extension"
        await chat(writer, "#gallop on")
        burst = await state(reader, actor_id, "mounted")
        assert burst["gait"] == "burst" and burst["step_us"] == 50000, burst
        # Sitting runs through ordinary dispatch and removes the mount first.
        writer.write(packet(7, bytes([1])))
        await writer.drain()
        await state(reader, actor_id, "on_foot")
        await state(watch, actor_id, "on_foot")
        await chat(writer, "#clientcaps " + capabilities)
        await state(reader, actor_id, "on_foot")
        print("PASS: real login, capability handshake, summon, observer replication, gallop, forced dismount, restatement and legacy client")
    finally:
        for _, peer, _ in peers:
            peer.close()
            await peer.wait_closed()


async def prepare_player(live):
    credentials = disposable_credentials("Pony")
    await create_character(live.port, *credentials)
    place_test_character(live, credentials[0])
    return credentials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-root", type=Path, default=ROOT.parent / "rabbitlands-server")
    parser.add_argument("--godot", type=Path)
    parser.add_argument("--mount-id", default="moor_pony", choices=["moor_pony",
        "golden_plains_horse", "crystalback_tortoise", "rabbit", "jadefeather_raptor"],
        help="Start with this mount selected; non-pony mounts use normal Landfall settings")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--landfall", action="store_true",
                        help="Test normal Landfall settings without --mount-prototype")
    args = parser.parse_args()
    if args.mount_id != "moor_pony":
        args.landfall = True
    server = args.server_root.resolve()
    work = ROOT / ".local/qa/moor-pony-game"
    work.mkdir(parents=True, exist_ok=True)
    # Keep all disposable files in the ignored workspace, including tempfile.
    for name in ("TMP", "TEMP", "TMPDIR"):
        os.environ[name] = str(work)
    import tempfile
    tempfile.tempdir = str(work)
    terrain = server / "build/mounts-game-test/terrain"
    subprocess.run([sys.executable, str(server / "tools/prepare_local_maps.py"), str(terrain)],
                   cwd=server, check=True, stdout=subprocess.DEVNULL)
    os.environ["RABBITLANDS_DATA_DIRECTORY"] = str(terrain)
    settings = (server / "config/eloria/server.txt").read_text()
    if not args.landfall:
        settings = re.sub(r"(?m)^home_map\s*=.*$", "home_map = four_gates", settings)
    with LocalServer(server, prefix="moor-pony-game-", overrides={"--settings": settings},
                     extra_arguments=[] if args.landfall else ["--mount-prototype"]) as live:
        live.mount_id = args.mount_id
        live.mount_map = "landfall" if args.landfall else "four_gates"
        live.mount_spawn = test_spawn(server, terrain, live.mount_map)
        if args.probe:
            asyncio.run(probe(live))
            return
        if not args.godot or not args.godot.is_file():
            parser.error("Pass --godot with the Godot 4.7.2 executable path")
        user, password = asyncio.run(prepare_player(live))
        session = Path(live._workdir.name) / "session.json"
        session.write_text(json.dumps({"host": "127.0.0.1", "port": live.port,
            "username": user, "password": password, "mount_id": args.mount_id}))
        try:
            game_log = work / (Path(live._workdir.name).name + "-game.log")
            print(f"Local Moor Pony test game log: {game_log}", flush=True)
            arguments = [str(args.godot), "--path", str(ROOT / "godot-client"),
                "--log-file", str(game_log), "--script", "res://prototypes/moor_pony_game_test.gd"]
            if args.headless:
                arguments += ["--headless"]
            arguments += ["--", "--dev-plain-tcp", "--server=127.0.0.1", f"--port={live.port}", f"--mount-session={session}"]
            if args.smoke:
                arguments.append("--mount-smoke")
            client_env = os.environ.copy()
            profile = Path(live._workdir.name) / "player-profile"
            profile.mkdir(exist_ok=True)
            client_env["APPDATA"] = str(profile)
            client_env["LOCALAPPDATA"] = str(profile)
            result = subprocess.run(arguments, cwd=ROOT, env=client_env)
            raise SystemExit(result.returncode)
        finally:
            session.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
