"""Replay appearance_options.gd fixtures through a local Eloria server checkout.

Uses the actual creation handler, an in-memory SQLite database, character load,
and enhanced actor serialization. No listener, live account or network is used.
Run appearance_options.gd again afterwards to check the returned actor packets.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace


async def verify(server_root, folder):
    sys.path.insert(0, str(server_root.resolve()))
    from eloria.server import GameServer
    from eloria.database import Database
    from eloria import protocol
    server = GameServer.__new__(GameServer)
    server.db = Database(':memory:')
    server.creation_limiter = SimpleNamespace(allow=lambda *args: True)
    server.world = SimpleNamespace(settings=SimpleNamespace(
        character_creations_per_hour=1000, allowed_player_actor_types=''))

    class Session:
        peer_ip = '127.0.0.1'

        async def send(self, packet):
            assert packet[0] == protocol.CREATE_CHAR_OK, packet

    responses = []
    try:
        for row in json.loads((folder/'hair-create.json').read_text()):
            packet = bytes.fromhex(row['packet'])
            await server._create(Session(), packet[3:])
            username = packet[3:].split(b' ', 1)[0].decode()
            character = server.db.load(username, 901)
            responses.append({'style': row['style'], 'color': row['color'],
                'packet': protocol.enhanced_actor_packet(character).hex()})
        assert len(responses) == 200
        (folder/'hair-server.json').write_text(json.dumps(responses, indent=2)+'\n')
        print(f'{len(responses)} creation/database/spawn round trips passed')
    finally:
        server.db.db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.server, args.artifacts))
