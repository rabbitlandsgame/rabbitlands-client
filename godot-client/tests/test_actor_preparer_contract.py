"""AW-04a: what the actor preparer's worker may call.

The preparer (src/actors/actor_resource_warmup.gd) parses an actor's asset closure on a worker
and reads the equipment pieces table from the unpacked root there. A worker call with a return
value into the RenderingServer waits for the main thread (avatar-worker plan section 2):
PackedScene.pack(), get_property_list(), surface_get_arrays(), Texture2D.get_image(). These
checks hold the worker's code to calls that wait for nothing; tests/test_actor_asset_preparer.gd
proves it with a blocked main thread:

* the file job is `GlbSceneCache.prepare_actor` plus `ReplicatedActor3D.equipment_pieces_from`,
  never a pack, an instantiate or a main-thread build;
* `equipment_pieces_from` reads CPU state only and never frees or packs what it is given;
* publication (install_actor_prepared, install_equipment_pieces) happens in `_publish`, which
  runs from `poll` on the main thread only;
* the creature job's queueing is unchanged (test_package_actor_worker_contract checks its guard).
"""
import re
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
WARMUP = CLIENT / "src/actors/actor_resource_warmup.gd"
ACTOR = CLIENT / "src/actors/replicated_actor_3d.gd"
CLOSURE = CLIENT / "src/actors/actor_asset_closure.gd"
DEFINITION = re.compile(r"^(static\s+)?func\s+(\w+)\s*\(")
TOP_LEVEL = re.compile(r"^(static\s+func|func|const|static\s+var|var|class|class_name|extends|signal|enum)\b")
WAITING_CALLS = (".pack(", "instantiate(", "get_property_list(", "surface_get_arrays(", "get_image(",
                 "_build(", "_build_raw(", "_pack_generated(", "_claim(", "GlbSceneCache.prepare(",
                 "install_actor_prepared(", "install_equipment_pieces(", "add_child(", ".free()")


def _body(path: Path, name: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        match = DEFINITION.match(line)
        if match and match.group(2) == name:
            body = []
            for following in lines[index + 1:]:
                if following and not following[0].isspace() and not following.startswith("#") \
                        and TOP_LEVEL.match(following):
                    break
                stripped = following.strip()
                if stripped and not stripped.startswith("#"):
                    body.append(stripped)
            return "\n".join(body)
    raise AssertionError(f"{path.name} defines no function {name}")


def test_the_file_job_parses_unpacked_and_reads_pieces_only():
    job = _body(WARMUP, "_prepare_file")
    assert "GlbSceneCache.prepare_actor(" in job and "ReplicatedActor3D.equipment_pieces_from(" in job
    for forbidden in WAITING_CALLS:
        assert forbidden not in job, f"the worker's file job must not call {forbidden}"
    assert re.search(r"^static func _prepare_file\(", WARMUP.read_text(encoding="utf-8"), re.M), \
        "the file job is static: it reads no preparer state on the worker"


def test_pieces_are_read_from_cpu_state_only():
    pieces = _body(ACTOR, "equipment_pieces_from")
    for forbidden in WAITING_CALLS + ("GlbSceneCache.", "_equipment_pieces_cache"):
        assert forbidden not in pieces, f"equipment_pieces_from runs on the worker: no {forbidden}"
    wrapper = _body(ACTOR, "_equipment_pieces")
    assert "equipment_pieces_from(" in wrapper and "imported.free()" in wrapper, \
        "the main-thread lookup reads pieces through the same function and frees its instance"


def test_publication_is_main_thread_only():
    poll = _body(WARMUP, "poll")
    assert poll.splitlines()[0].startswith("if OS.get_thread_caller_id() != OS.get_main_thread_id()"), \
        "poll (which publishes) returns at once off the main thread"
    publish = _body(WARMUP, "_publish")
    assert "GlbSceneCache.install_actor_prepared(" in publish
    assert "ReplicatedActor3D.install_equipment_pieces(" in publish
    finish = _body(WARMUP, "_finish_file")
    assert "discard_actor_prepared(" in finish, "a cleared or replaced job's root is freed, never published"


def test_the_closure_reads_no_cache_or_node():
    code = "\n".join(line for line in CLOSURE.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))
    for forbidden in ("GlbSceneCache.", "instantiate(", "ResourceLoader.", "get_node", "AppState."):
        assert forbidden not in code, f"actor_asset_closure.gd stays a pure lookup: no {forbidden}"
    assert not re.search(r"(?<!pre)load\(", code), "actor_asset_closure.gd loads nothing at run time"
