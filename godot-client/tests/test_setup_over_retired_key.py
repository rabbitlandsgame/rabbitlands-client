"""Setup over a folder from before the 2026-11 key rotation (tools/install_client_payload.gd).

Every installation from before the rotation holds the retired release key in
app/client-release.json. The setup helper may overwrite such a folder, and only
such a folder: it recognises the retired key by hash, from that unsigned local
file. Everything it installs is still verified with its own embedded key.

These run the helper script headless against the shared updater fixture, with no
Inno Setup. They never touch a real installation; the folder and the user folder
are under pytest's tmp_path.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

import pytest

from test_asset_packages import CLIENT, assert_no_transaction, fixture, older_updater_source, tree  # noqa: F401
from test_setup_recovers_interrupted_update import HELPER, run_setup, setup_parts, setup_project

ROTATION_PARENT = "3ad70bb9~1"
FIELD_RELEASE = "945042f00d457e0655ef2b2ebfc11a06e5ee945c"
DESCRIPTOR = "app/client-release.json"
LOCK = ".eloria-launcher-lock"
REFUSAL = "This installation belongs to a different distribution or signing key."
ANOTHER_KEY = "-----BEGIN PUBLIC KEY-----\nQW5vdGhlciBwdWJsaXNoZXI=\n-----END PUBLIC KEY-----\n"
DROPPED = object()


def git_show(revision_path):
    return subprocess.run(["git", "-C", str(CLIENT.parent), "show", revision_path], check=True,
                          capture_output=True, timeout=60).stdout


def retired_pem():
    return git_show(f"{ROTATION_PARENT}:godot-client/data/update_public.pem").decode("ascii")


def set_descriptor(f, **changes):
    """The fixture's installed descriptor with some fields changed; DROPPED removes one."""
    path = f["installed"] / DESCRIPTOR
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    for name, value in changes.items():
        if value is DROPPED:
            descriptor.pop(name, None)
        else:
            descriptor[name] = value
    path.write_text(json.dumps(descriptor), encoding="utf-8")


def everything(root):
    """Every file and folder under `root`, hidden ones too, with bytes (None for a folder)."""
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
            for path in root.rglob("*")}


def cache_of(f):
    """A cache folder with one old download in it, as a player who updated before has."""
    cache = (f["tmp_path"] / "userdata/RabbitLandsSetupRecoveryTests/client-updates"
             / hashlib.sha256(f["installed"].as_posix().encode()).hexdigest()[:24])
    (cache / "packages").mkdir(parents=True)
    (cache / "packages/kept.zip").write_bytes(b"an earlier verified download")
    return cache


def assert_converted(f, code, log):
    assert "SCRIPT ERROR" not in log, log
    assert code == 0 and "Rabbit Lands installation verified." in log and "RL_ERROR" not in log, log
    installed = f["installed"]
    assert tree(installed) == tree(f["stage"])
    assert json.loads((installed / DESCRIPTOR).read_text())["public_key"] == f["newer"]["public_key"]
    assert_no_transaction(installed)
    assert not (installed / LOCK).exists()
    record = json.loads((installed / ".rabbitlands-release.json").read_text())
    assert record["commit"] == f["newer"]["commit"] and record["platform"] == "windows"
    marker = json.loads((installed / ".rabbitlands-install.json").read_text())
    assert marker["repository"] == f["newer"]["repository"] and marker["platform"] == "windows"


@pytest.mark.parametrize("form", ["published", "crlf", "stripped"])
def test_setup_converts_a_folder_holding_the_retired_key(fixture, form):
    f = fixture
    pem = retired_pem()
    key = {"published": pem, "crlf": pem.replace("\n", "\r\n"), "stripped": pem.strip()}[form]
    assert key != f["newer"]["public_key"]
    set_descriptor(f, public_key=key)
    code, log = run_setup(f, setup_project(f, f["payload"]), setup_parts(f, f["payload"]))
    assert_converted(f, code, log)


def test_setup_converts_a_folder_older_than_the_distribution_field(fixture):
    # A missing distribution is a GitHub installation (Release.update_owner).
    f = fixture
    set_descriptor(f, public_key=retired_pem(), distribution=DROPPED)
    code, log = run_setup(f, setup_project(f, f["payload"]), setup_parts(f, f["payload"]))
    assert_converted(f, code, log)


def test_setup_clears_the_whole_game_copy_older_updaters_left(fixture):
    # Updaters before T never removed .eloria-previous after a finished update.
    f = fixture
    set_descriptor(f, public_key=retired_pem())
    previous = f["installed"] / ".eloria-previous/app"
    previous.mkdir(parents=True)
    (previous / "RabbitLands.pck").write_bytes(b"the release before that")
    code, log = run_setup(f, setup_project(f, f["payload"]), setup_parts(f, f["payload"]))
    assert_converted(f, code, log)


REFUSALS = {"another key": lambda retired: {"public_key": ANOTHER_KEY},
            "the key inside other text": lambda retired: {"public_key": "x" + retired},
            "retired, another repository": lambda retired: {"public_key": retired, "repository": "someone/else"},
            "retired, repository not text": lambda retired: {"public_key": retired, "repository": 7},
            "retired, steam": lambda retired: {"public_key": retired, "distribution": "steam"},
            "retired, standalone": lambda retired: {"public_key": retired, "distribution": "standalone"},
            "retired, another platform": lambda retired: {"public_key": retired, "platform": "linux"},
            "retired, no platform": lambda retired: {"public_key": retired, "platform": DROPPED},
            "no key": lambda retired: {"public_key": DROPPED},
            "null key": lambda retired: {"public_key": None},
            "number key": lambda retired: {"public_key": 12345},
            "list key": lambda retired: {"public_key": [retired]},
            "object key": lambda retired: {"public_key": {"pem": retired}}}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_setup_refuses_every_other_folder_before_it_writes(fixture, case):
    # A key that is not text must end with this message too. A comparison Godot
    # refuses would abort _ready, and setup would wait forever for the helper.
    f = fixture
    set_descriptor(f, **REFUSALS[case](retired_pem()))
    cache = cache_of(f)
    parts = setup_parts(f, f["payload"])
    project = setup_project(f, f["payload"])
    before = everything(f["installed"]), everything(cache), everything(parts)
    code, log = run_setup(f, project, parts)
    assert "SCRIPT ERROR" not in log, log
    assert code == 1 and f"RL_ERROR|{REFUSAL}" in log, log
    assert (everything(f["installed"]), everything(cache), everything(parts)) == before
    assert not f["downloads"]


def test_the_retired_key_constant_is_the_key_before_the_rotation():
    source = (CLIENT / HELPER).read_text(encoding="utf-8")
    constant = re.search(r'^const RETIRED_KEY_SHA256 := "([0-9a-f]{64})"$', source, re.M).group(1)
    assert constant == hashlib.sha256(retired_pem().encode("ascii")).hexdigest()
    assert constant != hashlib.sha256((CLIENT / "data/update_public.pem").read_bytes()).hexdigest()


def test_the_retired_key_only_decides_whether_a_folder_may_be_replaced():
    # One declaration and one comparison, both in the helper. No signature path,
    # identity or updater script can reach the hash.
    source = (CLIENT / HELPER).read_text(encoding="utf-8")
    assert source.count("RETIRED_KEY_SHA256") == 2
    body = source[source.index("func _may_replace("):source.index("func _install_packages(")]
    assert "RETIRED_KEY_SHA256" in body and "verify" not in body
    # Called once, on the installed descriptor, before the first write.
    assert source.count("_may_replace(") == 2
    packages = source[source.index("func _install_packages("):source.index("func _install() ")]
    assert packages.index("_may_replace(current, identity)") < packages.index("make_dir_recursive_absolute")
    for script in (CLIENT / "src/updates").glob("*.gd"):
        text = script.read_text(encoding="utf-8")
        assert "RETIRED_KEY" not in text and "605e86c6" not in text, script.name


def half_converted(f):
    """What a setup killed between the helper's commit and Inno's root files leaves:
    the new release's complete tree and descriptor, with the old updater beside it."""
    installed = f["installed"]
    for name in ("app", "eloria-assets"):
        shutil.rmtree(installed / name)
        shutil.copytree(f["stage"] / name, installed / name)
    (installed / "RabbitLands-updater.exe").write_bytes(b"the old updater, which refuses this descriptor")
    (installed / ".rabbitlands-install.json").write_text(json.dumps(
        {"schema": 1, "repository": f["newer"]["repository"], "platform": "windows"}))


def test_setup_heals_a_half_converted_folder_without_downloading(fixture):
    f = fixture
    half_converted(f)
    parts = f["tmp_path"] / "no-parts"
    parts.mkdir()
    code, log = run_setup(f, setup_project(f, f["payload"]), parts)
    assert_converted(f, code, log)
    assert not f["downloads"] and not list(parts.iterdir())
    # Inno writes the root files after the helper, so the helper leaves this one alone.
    assert (f["installed"] / "RabbitLands-updater.exe").read_bytes().startswith(b"the old updater")


def test_the_original_setup_refuses_a_half_converted_folder(fixture):
    # Why the notes say to run this setup again. The shortcut's message names the
    # original installer, and that installer's own helper stops here.
    f = fixture
    older = older_updater_source(f, FIELD_RELEASE)
    if older is None:
        pytest.skip(f"The field release {FIELD_RELEASE} is not available here.")
    helper = git_show(f"{FIELD_RELEASE}:godot-client/{HELPER}").decode("utf-8")
    project = setup_project(f, f["payload"], helper_source=helper)
    shutil.rmtree(project / "src/updates")
    shutil.copytree(older / "src/updates", project / "src/updates")
    half_converted(f)
    # The original setup embeds another key than the one the folder now holds.
    set_descriptor(f, public_key=(CLIENT / "data/update_public.pem").read_text(encoding="ascii"))
    before = everything(f["installed"])
    code, log = run_setup(f, project, setup_parts(f, f["payload"]))
    assert code == 1 and f"RL_ERROR|{REFUSAL}" in log, log
    assert everything(f["installed"]) == before


def test_setup_leaves_a_folder_alone_while_a_live_guarded_lock_holds_it(fixture):
    # An updater or game that took the lock keeps owner.json open, and Windows
    # denies its deletion. The check runs before Download.prepare, so the player
    # keeps every file, and only this run's downloads are lost.
    f = fixture
    set_descriptor(f, public_key=retired_pem())
    lock = f["installed"] / LOCK
    lock.mkdir()
    owner = lock / "owner.json"
    owner.write_text(json.dumps({"pid": os.getpid(), "guarded": True}))
    cache = cache_of(f)
    parts = setup_parts(f, f["payload"])
    project = setup_project(f, f["payload"])
    before = everything(f["installed"]), everything(cache), everything(parts)
    with owner.open("r+b"):
        code, log = run_setup(f, project, parts)
    assert "SCRIPT ERROR" not in log, log
    assert code == 1, log
    assert ("RL_ERROR|Another Rabbit Lands installer or launcher is still working." in log
            or "RL_ERROR|Close Rabbit Lands and any other installer before continuing." in log), log
    assert (everything(f["installed"]), everything(cache), everything(parts)) == before
    assert not f["downloads"]
