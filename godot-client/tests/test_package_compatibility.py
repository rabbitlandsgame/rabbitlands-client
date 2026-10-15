import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package_client


@pytest.mark.parametrize("platform", ["windows", "linux"])
@pytest.mark.parametrize("updating", [False, True])
def test_compatibility_modes_keep_updates_and_engine_argument_order(tmp_path, platform, updating):
    if updating:
        (tmp_path / ("RabbitLands-updater.exe" if platform == "windows" else "RabbitLands-updater.x86_64")).touch()
    package_client.write_launchers(tmp_path, "play.example.org:2000", tmp_path, "test",
                                   package_client.PLATFORMS[platform])
    assert json.loads((tmp_path / "launcher-defaults.json").read_text())["args"] == [
        "--server=play.example.org", "--port=2000"]
    for safe in (False, True):
        label = "safe mode" if safe else "compatibility"
        slug = "safe-mode" if safe else "compatibility"
        name = f"RabbitLands ({label}).bat" if platform == "windows" else f"RabbitLands-{slug}.sh"
        text = (tmp_path / name).read_text()
        if updating:
            assert "RabbitLands-updater" in text
            assert ("--client-safe-mode" if safe else "--client-compatibility") in text
        else:
            assert text.index("--rendering-method gl_compatibility") < text.index(" -- --server")
            assert "--rendering-driver opengl3" in text
            assert f"eloria-{slug}.log" in text
            assert "--port=2000" in text
            if safe:
                for key in ("ELORIA_LOOK", "ELORIA_LOOK_QUALITY", "ELORIA_VRAM_TEXTURES", "ELORIA_NO_MAP_CACHE"):
                    assert key in text
        if platform == "windows":
            assert "setlocal" in text  # Environment overrides cannot affect later launches.
    readme = (tmp_path / "README.txt").read_text()
    assert "client.log" in readme and "eloria-safe-mode.log" in readme
