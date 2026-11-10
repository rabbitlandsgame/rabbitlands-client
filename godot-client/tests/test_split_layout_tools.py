"""--script tools run on a split release compile before ContentPacks mounts its packs.

package_client.check_split_pack_resources and full_optimization_package._check_final_package
run these tools with --main-pack on the core pack. Godot compiles a --script tool, with every
preload and every class_name or autoload it names, before the first autoload (ContentPacks)
mounts app/packs, so anything they name at compile time must not reach a texture, sound or
video the split moved into a content pack. Each tool loads project scripts at run time instead.
"""
from pathlib import Path
import re

CLIENT = Path(__file__).resolve().parents[1]
SPLIT_LAYOUT_TOOLS = ("tools/check_prepared_release.gd", "tools/check_split_pack_resources.gd")


def _code(path: Path) -> str:
    """The script without string literals and comments."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
        lines.append(line.split("#", 1)[0])
    return "\n".join(lines)


def _project_globals() -> set[str]:
    names = set()
    for script in (CLIENT / "src").rglob("*.gd"):
        names.update(re.findall(r"^class_name\s+([A-Za-z_]\w*)",
                                script.read_text(encoding="utf-8", errors="replace"), re.M))
    settings = (CLIENT / "project.godot").read_text(encoding="utf-8")
    section = re.search(r"(?ms)^\[autoload\]\s*\n(.*?)(?=^\[|\Z)", settings)
    names.update(re.findall(r"^([A-Za-z_]\w*)=", section.group(1) if section else "", re.M))
    return names


def test_split_layout_tools_name_no_project_script_at_compile_time():
    names = _project_globals()
    assert {"ContentPacks", "ReplicatedActor3D"} <= names
    for tool in SPLIT_LAYOUT_TOOLS:
        code = _code(CLIENT / tool)
        assert "preload(" not in code, f"{tool} preloads a project script"
        named = sorted(set(re.findall(r"\b[A-Za-z_]\w*\b", code)) & names)
        assert not named, f"{tool} names project globals at compile time: {named}"


def test_the_check_reads_through_the_stripped_code():
    sample = CLIENT / "tools/check_prepared_release.gd"
    assert "PROJECT_SCRIPTS" in _code(sample) and "res://src/world/prepared_content.gd" not in _code(sample)
