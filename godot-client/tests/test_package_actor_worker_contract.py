"""AW-03: the contract between packaging and the worker-thread actor glTF parse.

A package reads actor glTFs loose and imports the textures equipment glTFs name by URI
(package_client.IMPORTED_URI_TEXTURE_FOLDERS). Plain GLTFDocument takes such a texture from
ResourceLoader and reads it back with get_image(), which on a worker waits for the main thread;
the actor image extension (src/actors/actor_images.gd) takes the same texture, resolved the way
GLTFDocument resolves it, without the read. PackedScene.pack() also waits for the main thread,
so the actor worker path returns an unpacked root and main packs it. These checks hold the
pieces together; tests/test_actor_worker_parse.gd proves the behaviour headless:

* GltfQuantization.ensure_registered() registers actor_images.gd with the other global
  extensions, before it reports readiness (main thread, before any worker parse).
* GlbSceneCache's one parse helper enables the extension for actor documents before the parse;
  _build_raw and prepare_actor both go through it; prepare_actor never packs or instantiates,
  install_actor_prepared packs on the main thread.
* The extension answers ERR_SKIP first thing for a foreign document and keeps no member state
  (4.7.2 does not carry a GDScript extension's fields into the import calls).
* The generic worker path GlbSceneCache.prepare() packs on its worker, so only its known callers
  use it and none is handed an equipment glTF: prepare_actor is the one actor worker path.
* The real tree: every URI an equipment glTF names resolves to a tracked image in the imported
  folder, and no URI has a '+' (uri_decode and uri_file_decode would read it differently).
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

import pytest


CLIENT = Path(__file__).resolve().parents[1]
SOURCE = CLIENT / "tools" / "package_client.py"
SPEC = importlib.util.spec_from_file_location("package_client_actor_worker_contract", SOURCE)
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)

CACHE = CLIENT / "src/actors/glb_scene_cache.gd"
IMAGES = CLIENT / "src/actors/actor_images.gd"
QUANTIZATION = CLIENT / "src/world/gltf_quantization.gd"
WARMUP = CLIENT / "src/actors/actor_resource_warmup.gd"
CACHE_SCRIPT = "res://src/actors/glb_scene_cache.gd"
# Callers of the generic worker path (it packs on the worker): map preloaders' visualScenes
# (world assets only, test_package_client_actor_lods), creature warmup (creatures only, below),
# the RL head library (embedded images only, below) and the scenery steppers (world assets).
PREPARE_CALLERS = {"src/actors/actor_resource_warmup.gd", "src/actors/rl_head/rl_head_library.gd",
                   "src/world/world_loader.gd", "src/world/underground_scenery.gd",
                   "src/world/interior_scenery_stepper.gd"}
DEFINITION = re.compile(r"^(static\s+)?func\s+(\w+)\s*\(")
TOP_LEVEL = re.compile(r"^(static\s+func|func|const|static\s+var|var|class|class_name|extends|signal|enum)\b")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _body(path: Path, name: str) -> str:
    """The statements of the GDScript function `name` (comments dropped)."""
    lines = _source(path).splitlines()
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


def test_quantization_registration_includes_the_actor_image_extension():
    source = _source(QUANTIZATION)
    assert 'preload("res://src/actors/actor_images.gd")' in source
    body = _body(QUANTIZATION, "ensure_registered")
    register = body.find("register_gltf_document_extension(actor_images)")
    ready = body.find("_registration_ready = true")
    assert register >= 0 and ready > register, \
        "actor_images.gd must be registered before GltfQuantization reports readiness"
    assert body.find("ActorImages.configure()") < register, "the switch is read on main, before registration"


def test_one_parse_helper_enables_the_extension_before_parsing():
    helper = _body(CACHE, "_parse_generate")
    enable = helper.find("ActorImages.enable(")
    assert enable >= 0
    for parse in ("CreaturePayload.append(", "append_from_buffer(", "append_from_file("):
        position = helper.find(parse)
        assert position < 0 or position > enable, f"{parse} runs before the actor flag is set"
    assert "generate_scene(" in helper and ".pack(" not in helper
    build_raw = _body(CACHE, "_build_raw")
    assert "_parse_generate(" in build_raw and "is_actor_document(" in build_raw


def test_prepare_actor_parses_unpacked_and_main_packs():
    prepare_actor = _body(CACHE, "prepare_actor")
    assert re.search(r"_parse_generate\([^)]*,\s*true\)", prepare_actor), "prepare_actor parses as an actor"
    for forbidden in (".pack(", "_pack_generated(", "_claim(", "instantiate(", "_build(", "_build_raw("):
        assert forbidden not in prepare_actor, f"prepare_actor must not call {forbidden} (main-thread waits)"
    registered = prepare_actor.find("GltfQuantization.ensure_registered()")
    assert 0 <= registered < prepare_actor.find("ActorImages.active()"), \
        "a worker reads the actor image switch only after main's registration published it"
    install = _body(CACHE, "install_actor_prepared")
    assert "get_main_thread_id()" in install and "_pack_generated(" in install


def test_actor_image_extension_skips_foreign_documents_and_keeps_no_member_state():
    preflight = _body(IMAGES, "_import_preflight").splitlines()
    head = "\n".join(preflight[:3])
    assert "get_additional_data(ENABLED)" in head and "return ERR_SKIP" in head, \
        "the first statements must answer ERR_SKIP for a document that is not an actor document"
    members = [line for line in _source(IMAGES).splitlines() if re.match(r"^var\s", line)]
    assert members == [], f"per-parse state belongs in GLTFState or statics, not fields: {members}"
    assert 'URI_MIME_PREFIX := "image/x-rl-actor-uri;"' in _source(IMAGES), \
        "AT-C2 skips these placeholders by this mimeType"


def _prepare_callers() -> dict[str, list[str]]:
    callers: dict[str, list[str]] = {}
    for path in sorted((CLIENT / "src").rglob("*.gd")):
        text = path.read_text(encoding="utf-8")
        names = ["GlbSceneCache"] + re.findall(
            r"const\s+(\w+)\s*:?=\s*preload\(\"" + re.escape(CACHE_SCRIPT) + r"\"\)", text)
        found = [name for name in names if re.search(r"\b" + re.escape(name) + r"\.prepare\(", text)]
        if found and path != CACHE:
            callers[path.relative_to(CLIENT).as_posix()] = found
    return callers


def test_the_generic_worker_path_keeps_its_known_callers():
    callers = _prepare_callers()
    unknown = sorted(set(callers) - PREPARE_CALLERS)
    assert unknown == [], ("a new caller of GlbSceneCache.prepare() packs on a worker; actor files go "
                           f"through prepare_actor/install_actor_prepared instead: {unknown}")
    request = _body(WARMUP, "request")
    guard = request.find('"res://assets/actors/native/creatures/"')
    assert 0 <= guard < request.find("_queue.append("), "creature warmup must queue creatures only"


def _repo_tracked(*specs: str) -> list[str]:
    try:
        return package.tracked(package.REPO, *specs)
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"git cannot list this checkout: {error}")


def _folder(relative: str) -> str:
    return PurePosixPath(relative).relative_to(package.ACTOR_ROOT).parts[0]


def test_real_actor_uris_resolve_where_the_extension_looks():
    files = _repo_tracked(package.ACTOR_ROOT)
    tracked = set(files)
    gltf = [f for f in files if f.lower().endswith(package.GLTF_SUFFIXES)]
    assert gltf
    named = outside = 0
    problems: list[str] = []
    for relative in gltf:
        path = package.REPO / relative
        if not path.is_file():
            continue
        for image in package.gltf_document(path).get("images", []):
            uri = image.get("uri") if isinstance(image, dict) else None
            if not isinstance(uri, str) or not uri or uri.startswith("data:"):
                continue
            named += 1
            if "+" in uri:
                problems.append(f"{relative}: '+' in {uri}")
            target = package._resolve(relative, unquote(uri))
            if _folder(relative) in package.IMPORTED_URI_TEXTURE_FOLDERS:
                if target not in tracked or not target.startswith(package.ACTOR_ROOT + "/") \
                        or _folder(target) != _folder(relative) \
                        or not target.lower().endswith(package.IMAGE_SUFFIXES):
                    problems.append(f"{relative} -> {uri}")
            else:
                outside += 1
    assert named > 0
    assert problems == [], f"{len(problems)} URI images break the actor parse contract: {problems[:10]}"
    # Those outside the imported folders stay loose: GLTFDocument reads their bytes, which needs
    # no RenderingServer read, so the extension leaves them alone.
    assert outside < named
