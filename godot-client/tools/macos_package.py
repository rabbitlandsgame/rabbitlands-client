"""Native universal macOS bundles; no in-place update of signed app contents."""
from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

EXPORT_PRESET = '''
[preset.2]
name="macOS"
platform="macOS"
runnable=false
export_filter="all_resources"
include_filter="*.json,*.bin,assets/audio/*.txt,assets/audio/licenses/*.txt"
exclude_filter="Godot_v*.exe,docs/*,tests/*,tools/*,test-artifacts/*,world_authoring/*,*.md,*.editor-notes.json"
export_path=""
script_export_mode=2
[preset.2.options]
export/distribution_type=0
binary_format/architecture="universal"
debug/export_console_wrapper=0
application/icon="res://assets/branding/rabbitlands-icon.icns"
application/bundle_identifier="com.rabbitlandsgame.client"
application/short_version="0.1.0"
application/version="1"
texture_format/s3tc_bptc=true
texture_format/etc2_astc=true
codesign/codesign=1
notarization/notarization=0
'''


def native():
    if sys.platform != "darwin":
        raise ValueError("macOS bundles require a native macOS runner.")


def prepare_import(project: Path):
    config = project / "project.godot"
    text = config.read_text(encoding="utf-8")
    # Import both texture families for the universal PCK. Do this only in the
    # disposable worktree, leaving desktop/GitHub presets untouched.
    import re
    key = "textures/vram_compression/import_etc2_astc"
    if re.search(rf"(?m)^{re.escape(key)}=", text):
        text = re.sub(rf"(?m)^{re.escape(key)}=.*$", key + "=true", text)
    elif "[rendering]" in text:
        text = text.replace("[rendering]", "[rendering]\n" + key + "=true", 1)
    else:
        text += "\n[rendering]\n" + key + "=true\n"
    config.write_text(text, encoding="utf-8")


def bundle(stage: Path) -> Path:
    return stage / "Rabbit Lands.app"


def export(godot, project, app_dir, logs, run_godot):
    native()
    target = bundle(app_dir.parent)
    app_dir.mkdir(parents=True, exist_ok=True)
    run_godot(godot, ["--headless", "--path", str(project), "--export-release", "macOS", str(target)],
              logs / "export.log", timeout=3600)
    contents = target / "Contents"
    info = plistlib.loads((contents / "Info.plist").read_bytes())
    original = contents / "MacOS" / info["CFBundleExecutable"]
    helpers = contents / "Helpers"
    helpers.mkdir(exist_ok=True)
    original.rename(helpers / "RabbitLands")
    (helpers / "RabbitLands").chmod(0o755)
    packs = list((contents / "Resources").glob("*.pck"))
    if len(packs) != 1:
        raise ValueError("Expected exactly one macOS game PCK.")
    packs[0].rename(app_dir / "RabbitLands.pck")
    # Official 4.7 release templates prohibit --main-pack overrides. Their
    # executable-adjacent PCK discovery still works. Link it for pre-bundle
    # checks, then remove the redundant app-side name after those checks.
    os.link(app_dir / "RabbitLands.pck", helpers / "RabbitLands.pck")


def smoke(app_dir, logs, run_godot, failures):
    native()
    target = bundle(app_dir.parent) / "Contents/Helpers/RabbitLands"
    return smoke_binary(target, app_dir, logs / "smoke.log", run_godot, failures)


def smoke_binary(binary, cwd, log, run_godot, failures, extra=()):
    with tempfile.TemporaryDirectory(prefix="rabbitlands-mac-smoke-") as home:
        env = dict(os.environ, HOME=home)
        text = run_godot(binary, [*extra, "--headless", "--quit-after", "600"], log,
                         timeout=300, env=env, cwd=cwd)
    if any(failure in text for failure in failures):
        raise ValueError(f"macOS startup reported an error; see {log}")
    return text


def sign(target: Path, identity="-"):
    # Sign each Mach-O (including framework binaries and the Godot helper)
    # inside out, then seal the completed app. Never change files afterwards.
    magics = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}
    options = ["--force", "--sign", identity]
    if identity != "-":
        options += ["--timestamp", "--options", "runtime"]
    metadata = target / "Contents/Resources/game/app/client-release.json"
    steam = metadata.is_file() and json.loads(metadata.read_text()).get("distribution") == "steam"
    with tempfile.TemporaryDirectory(prefix="rabbitlands-entitlements-") as temp:
        entitlements = Path(temp) / "steam.plist"
        entitlements.write_bytes(plistlib.dumps({
            "com.apple.security.cs.disable-library-validation": True,
            "com.apple.security.cs.allow-dyld-environment-variables": True}))
        runtime_options = ["--entitlements", str(entitlements)] if steam else []
        for path in sorted(target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as handle:
                    magic = handle.read(4)
                if magic in magics:
                    executable = path.parent.name in {"MacOS", "Helpers"}
                    subprocess.run(["codesign", *options, *(runtime_options if executable else []), str(path)], check=True)
            if path.suffix == ".framework" and path.is_dir():
                subprocess.run(["codesign", *options, str(path)], check=True)
        subprocess.run(["codesign", *options, *runtime_options, str(target)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(target)], check=True)


def finish(stage, project, metadata):
    native()
    target = bundle(stage)
    contents = target / "Contents"
    game = contents / "Resources/game"
    game.mkdir()
    helper_pack = contents / "Helpers/RabbitLands.pck"
    helper_pack.parent.mkdir(exist_ok=True)
    if helper_pack.exists():
        (stage / "app/RabbitLands.pck").unlink()
    else:
        (stage / "app/RabbitLands.pck").rename(helper_pack)
    for name in ("app", "eloria-assets"):
        (stage / name).rename(game / name)  # Rename, never copy the full game.
    for path in list(stage.iterdir()):
        if path.is_file() and path.name != ".eloria-package":
            path.rename(game / path.name)
    info_path = contents / "Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info["CFBundleExecutable"] = "RabbitLands"
    info["CFBundleDisplayName"] = "Rabbit Lands"
    info["CFBundleVersion"] = str(len(metadata.get("ancestors", [])) or 1)
    info_path.write_bytes(plistlib.dumps(info))
    binary = contents / "MacOS/RabbitLands"
    subprocess.run(["xcrun", "clang", "-arch", "x86_64", "-arch", "arm64", "-Os",
                    "-mmacosx-version-min=11.0", str(Path(__file__).with_name("macos_launcher.c")),
                    "-o", str(binary)], check=True)
    binary.chmod(0o755)
    (game / "BUILD.json").write_text(json.dumps({"commit": metadata["commit"],
        "distribution": metadata["distribution"], "signing": "ad-hoc-test-only"}, indent=2) + "\n")
    sign(target)
    (stage / "README.txt").write_text(
        "Rabbit Lands macOS test build (Intel and Apple Silicon).\n"
        "Move Rabbit Lands.app to Applications; keep the bundle intact.\n"
        "This ad-hoc signed test build is not Developer ID signed or notarized.\n"
        "Public distribution requires Apple signing/notarization and hardware QA.\n"
        + ("Steam manages updates.\n" if metadata["distribution"] == "steam" else
           "To update, replace the whole app with the latest download. Player data stays in user storage.\n"),
        encoding="utf-8")


def archive(stage):
    native()
    output = stage.parent / (stage.name + ".zip")
    if output.exists():
        raise ValueError("Refusing to overwrite an existing macOS archive.")
    # ditto preserves bundle permissions, symlinks and signing metadata.
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(stage), str(output)], check=True)
    return output
