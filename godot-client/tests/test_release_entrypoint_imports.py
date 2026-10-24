"""Fresh interpreter import order must not depend on the test collection order."""
from pathlib import Path
import os
import subprocess
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


@pytest.mark.parametrize("entry", ["package_client.py", "runner_release.py", "actions_release.py"])
def test_standalone_release_entrypoint_help_imports_without_engine_or_network(entry, tmp_path):
    environment = {**os.environ, "PYTHONPYCACHEPREFIX": str(tmp_path / "bytecode")}
    result = subprocess.run([sys.executable, str(TOOLS / entry), "--help"],
        cwd=tmp_path, capture_output=True, text=True, env=environment, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert not result.stderr
