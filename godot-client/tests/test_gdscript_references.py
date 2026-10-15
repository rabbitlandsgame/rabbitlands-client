#!/usr/bin/env python3
"""Static reference checks across the GDScript sources.

Added 2026-08-28 for Eloria Client.

Godot only reports an unresolved call when the script is loaded, so a refactor
that deletes a method while leaving its call sites behind is invisible to the
Python asset suite and shows up as a script that will not compile at runtime.
These checks are deliberately narrow: they resolve private, unqualified calls
within one file, and pin the small set of methods other scripts reach across.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
SOURCE_DIRS = ("src", "tests")
NATIVE_SOURCE_DIR = CLIENT / "native" / "native_crowd" / "src"

DEFINITION = re.compile(r"^[ \t]*(?:static\s+)?func\s+(\w+)", re.M)
# An unqualified call: not preceded by a dot, so not a method on another object.
PRIVATE_CALL = re.compile(r"(?<![\w.$\"'])(_[a-z]\w*)\s*\(")
# A method passed as a Callable rather than called, which a plain call regex
# misses: connect(_x) and _x.bind(...). Only `bind` is matched here - `call` and
# `call_deferred` exist on Object too, so `_some_node.call(...)` would otherwise
# read as a Callable when it is an ordinary method on a member variable.
CALLABLE_REFERENCE = re.compile(r"(?<![\w.$\"'])(_[a-z]\w*)\s*\.\s*bind\s*\(")
# Member variables and constants share the naming convention, so they are
# subtracted before anything is reported as an unresolved call.
DECLARATION = re.compile(r"^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*(?:static\s+)?"
                         r"(?:var|const|signal)\s+(\w+)", re.M)
SIGNAL_CONNECT = re.compile(r"connect\(\s*(_[a-z]\w*)\b")
# A method reached by name on this script rather than by reference.
SELF_STRING_CALL = re.compile(
    r"(?<![\w.])(?:call|call_deferred|has_method)\(\s*\"(_[a-z]\w*)\"")
# A method reached by name on another object. The receiver's type cannot be
# inferred here, so these resolve against every method the project defines -
# enough to catch a deletion, which is what this file exists for.
FOREIGN_STRING_CALL = re.compile(
    r"\w\.call(?:_deferred)?\(\s*\"(\w+)\"|Callable\(\s*\w+\s*,\s*\"(\w+)\"")
# GDExtension methods are reached through Object.call() too. Read the names
# Godot actually exports rather than maintaining a second permissive allowlist.
NATIVE_BOUND_METHOD = re.compile(
    r"\bClassDB\s*::\s*bind_method\s*\(\s*D_METHOD\s*\(\s*\"([A-Za-z_]\w*)\"")
SCRIPT_EXTENDS = re.compile(r'''^extends\s+["']([^"']+)["']''', re.M)

# Engine callbacks are defined and never called, so nothing else pins them.
# Losing _physics_process silently removes all actor interpolation.
ENGINE_CALLBACKS = {
    "src/actors/replicated_actor_3d.gd": {"_physics_process"},
}

# Methods reached from another script or scene. Deleting one compiles fine in
# the owning file and breaks its caller, which is exactly what this pins.
CROSS_SCRIPT_API = {
    "src/actors/replicated_actor_3d.gd": {
        "configure", "apply_server_state", "apply_appearance_variants",
        "apply_equipment_visuals", "equipment_diagnostics", "render_diagnostics",
        "play_action", "predict_turn", "desired_facing_yaw",
        "clear_turn_prediction",
        "set_selected", "set_surface_height", "set_nameplate_visible",
        "target_yaw_for_state", "presentation_segment_duration",
        "rig_fit_scale",
    },
    "src/ui/item_atlas.gd": {"configure", "icon_for", "supports", "uses_substitute"},
}


def gdscript_files():
    for directory in SOURCE_DIRS:
        yield from sorted((CLIENT / directory).rglob("*.gd"))


def native_bound_methods_from_text(text: str) -> set[str]:
    return set(NATIVE_BOUND_METHOD.findall(text))


def native_bound_methods() -> set[str]:
    methods: set[str] = set()
    for path in sorted(NATIVE_SOURCE_DIR.rglob("*.cpp")):
        methods |= native_bound_methods_from_text(path.read_text(encoding="utf-8"))
    return methods


def inherited_script_members(path: Path, sources: dict[Path, str],
                             client_root: Path = CLIENT) -> set[str]:
    """Resolve explicit script inheritance without allowing unrelated methods."""
    members: set[str] = set()
    seen: set[Path] = set()
    while path in sources and path not in seen:
        seen.add(path)
        text = sources[path]
        members |= set(DEFINITION.findall(text)) | set(DECLARATION.findall(text))
        parent = SCRIPT_EXTENDS.search(text)
        if parent is None:
            break
        target = parent.group(1)
        path = ((client_root / target.removeprefix("res://"))
                if target.startswith("res://") else path.parent / target).resolve()
    return members


class GdScriptReferenceTest(unittest.TestCase):
    def test_explicit_script_inheritance(self) -> None:
        root = CLIENT.resolve()
        base, middle, child, unrelated = (
            root / name for name in ("base.gd", "middle.gd", "child.gd", "other.gd"))
        sources = {
            base: "extends Node\nvar _callback: Callable\nfunc _base():\n\tpass\n",
            middle: 'extends "res://base.gd"\nfunc _middle():\n\tpass\n',
            child: 'extends "middle.gd"\nfunc _child():\n\t_base()\n',
            unrelated: "func _unrelated():\n\tpass\n",
        }
        self.assertEqual({"_callback", "_base", "_middle", "_child"},
                         inherited_script_members(child, sources, root))
        self.assertNotIn("_missing", inherited_script_members(child, sources, root))
        sources[base] = 'extends "child.gd"\nfunc _base():\n\tpass\n'
        self.assertEqual({"_base", "_middle", "_child"},
                         inherited_script_members(child, sources, root))

    def test_native_bound_method_extraction(self) -> None:
        source = r'''
            const char *not_a_binding = "pretend";
            ClassDB::bind_method(
                D_METHOD("actual_method", "argument"), &Example::actual_method);
        '''
        self.assertEqual({"actual_method"},
                         native_bound_methods_from_text(source))

    def test_private_calls_resolve_in_their_own_file(self) -> None:
        sources = {path.resolve(): path.read_text(encoding="utf-8")
                   for path in gdscript_files()}
        for path, text in sources.items():
            defined = inherited_script_members(path, sources)
            called = (set(PRIVATE_CALL.findall(text))
                      | set(CALLABLE_REFERENCE.findall(text))
                      | set(SIGNAL_CONNECT.findall(text))
                      | set(SELF_STRING_CALL.findall(text)))
            # Engine callbacks are defined, never called by name.
            called -= defined
            called -= set(DECLARATION.findall(text))
            unresolved = sorted(name for name in called
                                if not name.startswith("__"))
            with self.subTest(script=str(path.relative_to(CLIENT))):
                self.assertEqual([], unresolved,
                                 f"{path.name} calls methods it does not define")

    def test_cross_script_api_is_intact(self) -> None:
        for relative, methods in CROSS_SCRIPT_API.items():
            text = (CLIENT / relative).read_text(encoding="utf-8")
            defined = set(DEFINITION.findall(text))
            with self.subTest(script=relative):
                self.assertEqual(set(), methods - defined,
                                 f"{relative} lost methods other scripts call")

    def test_engine_callbacks_are_present(self) -> None:
        for relative, callbacks in ENGINE_CALLBACKS.items():
            text = (CLIENT / relative).read_text(encoding="utf-8")
            defined = set(DEFINITION.findall(text))
            with self.subTest(script=relative):
                self.assertEqual(set(), callbacks - defined,
                                 f"{relative} lost an engine callback")

    def test_string_named_calls_resolve_somewhere(self) -> None:
        """The rendered tests drive main.gd and the actors by name."""
        defined: set[str] = native_bound_methods()
        for path in gdscript_files():
            defined |= set(DEFINITION.findall(path.read_text(encoding="utf-8")))
        for path in gdscript_files():
            text = path.read_text(encoding="utf-8")
            names = {first or second
                     for first, second in FOREIGN_STRING_CALL.findall(text)}
            unresolved = sorted(name for name in names if name not in defined)
            with self.subTest(script=str(path.relative_to(CLIENT))):
                self.assertEqual([], unresolved,
                                 f"{path.name} calls methods nothing defines")

    def test_scripts_use_tab_indentation(self) -> None:
        """Godot rejects a file that mixes tabs and spaces for indentation."""
        for path in gdscript_files():
            offenders = [number for number, line in
                         enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                         if line.startswith(" ") and line.strip()]
            with self.subTest(script=str(path.relative_to(CLIENT))):
                self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
