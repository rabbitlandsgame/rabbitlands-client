"""Game/profile argument forwarding; no native tools or engine processes."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package_client


@pytest.mark.parametrize("platform", ["windows", "linux"])
@pytest.mark.parametrize("updating", [False, True])
@pytest.mark.parametrize("server", [None, "play.example.org:2000"])
def test_game_options_forward_after_user_separator_with_and_without_server(tmp_path, platform, updating, server):
    scene = tmp_path / "godot-client/src/app/main.tscn"
    scene.parent.mkdir(parents=True)
    scene.write_text('[node name="Host"]\ntext = "play.example.org"\n[node name="Port"]\nvalue = 2000.0\n')
    if updating:
        (tmp_path / ("RabbitLands-updater.exe" if platform == "windows" else "RabbitLands-updater.x86_64")).touch()
    package_client.write_launchers(tmp_path, server, tmp_path, "test", package_client.PLATFORMS[platform])
    normal = "RabbitLands.bat" if platform == "windows" else "RabbitLands.sh"
    debug = "RabbitLands (debug console).bat" if platform == "windows" else "RabbitLands-debug.sh"
    compatibility = "RabbitLands (compatibility).bat" if platform == "windows" else "RabbitLands-compatibility.sh"
    safe = "RabbitLands (safe mode).bat" if platform == "windows" else "RabbitLands-safe-mode.sh"
    forwarded = "%*" if platform == "windows" else '"$@"'
    for name in (normal, debug, compatibility, safe):
        text = (tmp_path / name).read_text(encoding="utf-8")
        commands = [line for line in text.splitlines() if forwarded in line]
        assert len(commands) == 1, name
        command = commands[0]
        assert command.endswith(forwarded), name
        # Profile selectors are consumed by get_cmdline_user_args(), including
        # the no-server case. Engine renderer/log options stay before this.
        assert " -- " in command, name
        separator = command.index(" -- ")
        assert separator < command.index(forwarded), name
        if not updating and name in (compatibility, safe):
            assert command.index("--rendering-method") < command.index(" -- ")
        if server and name in (normal, debug):
            assert separator < command.index("--server=play.example.org") < command.index(forwarded)
        if updating:
            assert "--launch-only" in command
