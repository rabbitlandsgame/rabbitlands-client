"""Render a complete new-character greeting against a disposable real server."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from local_server import LocalServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-root', required=True, type=Path)
    parser.add_argument('--godot', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    client = Path(__file__).resolve().parents[2]
    args.output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ELORIA_ARTIFACT_DIR=str(args.output.resolve()))
    # This checkout's shipped settings point at the container's map volume.
    # Build only the test home's ELM from its existing authoritative grid.
    sys.path.insert(0, str(args.server_root.resolve() / 'tools'))
    from authored_collision import read_grid
    from generate_nymara_maps import write_served_map
    with tempfile.TemporaryDirectory(prefix='rabbitlands-arrival-maps-') as map_directory:
        map_root = Path(map_directory)
        write_served_map(map_root / 'maps/nymara/landfall.elm',
                         read_grid(args.server_root / 'tools/collision/landfall.escg.gz'), 'landfall')
        settings = (args.server_root / 'config/eloria/server.txt').read_text(encoding='utf-8')
        settings = '\n'.join('map_data_directory = ' + map_root.as_posix()
                             if line.startswith('map_data_directory =') else line
                             for line in settings.splitlines()) + '\n'
        run_client(args, client, env, settings)


def run_client(args, client, env, settings):
    with LocalServer(args.server_root, prefix='rabbitlands-arrival-',
                     overrides={'--settings': settings}) as server:
        command = [str(args.godot.resolve()), '--path', str(client), '--resolution', '1280x720',
                   '--position', '10000,10000', '--max-fps', '30', '--audio-driver', 'Dummy',
                   '--script', 'res://tests/integration/rendered_new_character_greeting.gd',
                   '--log-file', str(args.output.resolve() / 'greeting.log'), '--',
                   '--dev-plain-tcp', '--server=127.0.0.1', f'--port={server.port}']
        result = subprocess.run(command, cwd=client, env=env, timeout=180,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        log = (args.output / 'greeting.log').read_text(encoding='utf-8')
        for line in log.splitlines():
            if line.startswith(('PASS:', 'ERROR:', 'SCRIPT ERROR:', 'rendered new-character')):
                print(line)
        assert result.returncode == 0 and 'rendered new-character greeting: PASS' in log, server.recent_log()
        assert 'SCRIPT ERROR:' not in log and '\nERROR:' not in log


if __name__ == '__main__':
    main()
