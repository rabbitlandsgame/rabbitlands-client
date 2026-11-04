#!/usr/bin/env python3
"""Split the exported Godot PCK into a small core pack and stable content packs (W2-UD-06).

    python godot-client/tools/pck_split.py plan  app/RabbitLands.pck
    python godot-client/tools/pck_split.py split app/RabbitLands.pck app/ --core-out app/RabbitLands.core.pck
    python godot-client/tools/pck_split.py prove app/RabbitLands.pck app/RabbitLands.core.pck app/packs

A code-only release changed the one 886 MB PCK (release 4a57cea4), so every
player downloaded ~770 MB of compressed textures, audio and videos again. The
split moves the heavy, rarely changing import products into content packs that
keep their bytes from release to release (an update re-downloads only a pack
whose files changed) and leaves a small core pack for everything else:

  app/RabbitLands.pck (core)          project.binary, scripts, scenes, shaders, data, every
                                      .import and .remap, the UID and class caches, the boot
                                      closure (BOOT_CLOSURE) and data/content_packs.json
  app/packs/equipment-textures-N.pck  .godot/imported/canonical_*.ctex, sha256(path) mod 4
  app/packs/textures-N.pck            every other .godot/imported/*.ctex, sha256(path) mod 2
  app/packs/audio.pck                 .godot/imported/*.oggvorbisstr, *.sample, *.mp3str
  app/packs/video.pck                 *.ogv (the login backdrop opens them by path)

RULES is the table; the first rule an entry matches decides its pack, and an
entry no rule matches stays in the core. Prepared content (prepared-content/)
stays in the core until W2-UD-07a gives it a feature pack. An empty pack is not
written. The first autoload, src/boot/content_packs.gd (ContentPacks), mounts
the packs data/content_packs.json lists before any other autoload, scene or
preload can name what they hold.

Why not Godot's --export-patch: a patch pack mounts after project.binary, so it
can change neither project settings nor autoloads, and every build would need
the exact frozen base pack. Owner sign-off on this deviation: updates-downloads
design section 7.

The boot closure. The engine reads a few resources before the first autoload
runs: the ones project settings name (the window icon and the boot splash, the
translations, a custom theme or font, the default environment). Every entry such
a setting names, its import products and, for a resource file, every res://
path it names in turn stay in the core whatever the rules say. Autoload entries
and the main scene are left out of it: Godot loads both after the first
autoload's _init.

The output is deterministic: names sorted, data 16-byte aligned behind a
112-byte header (the 104-byte format 3/4 header with the 64 reserved bytes,
padded to 16), the directory at the end with names NUL-padded to 4 bytes, an
md5 per entry, and the input's pack format and engine version. The same input
gives byte-identical packs.

The partition proof (prove) re-reads every output: each monolith entry is in
exactly one output pack under its own name, with the monolith's size and md5
in the directory and bytes that hash to it; the core holds nothing else but
data/content_packs.json; the manifest lists exactly the pack files written,
with their byte size, entry count and sha256. Hashing every installed file is
the updater's job; ContentPacks checks only existence and byte size.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

MAGIC = b"GDPC"
# The release PCK (4.7.2) is format 4; format 3 has the same header and
# directory layout (pck_paths in package_client reads both the same way).
FORMATS = (3, 4)
HEADER = struct.Struct("<4sIIIIIQQ")  # magic, format, major, minor, patch, pack flags, file base, directory
HEADER_RESERVED = 16 * 4
PACK_DIR_ENCRYPTED = 1 << 0
PACK_REL_FILEBASE = 1 << 1
ALIGN = 16
FILE_BASE = (HEADER.size + HEADER_RESERVED + ALIGN - 1) // ALIGN * ALIGN  # 112
ENTRY_TAIL = struct.Struct("<QQ16sI")  # offset (from the file base), size, md5, file flags
COPY_BYTES = 8 * 1024 * 1024

MANIFEST = "data/content_packs.json"
MANIFEST_SCHEMA = 1
PACKS_DIRECTORY = "packs"
PACK_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
IMPORTED = ".godot/imported/"
PROJECT_BINARY = "project.binary"
PROJECT_TEXT = "project.godot"
UID_CACHE = ".godot/uid_cache.bin"


class SplitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Rule:
    pack: str
    buckets: int
    match: object  # callable(name) -> bool
    feature: str = ""  # "": required, mounted at every start (W2-UD-07a adds feature packs)


RULES = (
    Rule("equipment-textures", 4,
         lambda name: name.startswith(IMPORTED + "canonical_") and name.endswith(".ctex")),
    Rule("textures", 2, lambda name: name.startswith(IMPORTED) and name.endswith(".ctex")),
    Rule("audio", 1, lambda name: name.startswith(IMPORTED)
         and name.endswith((".oggvorbisstr", ".sample", ".mp3str"))),
    Rule("video", 1, lambda name: name.endswith(".ogv")),
)
# Project settings whose resources Godot loads after the first autoload (or never in a game).
BOOT_CLOSURE_SKIPPED = re.compile(r"^(autoload/|editor_plugins/|application/run/main_scene$)")


@dataclass(frozen=True)
class Entry:
    name: str  # without res://
    offset: int  # absolute, in its pack file
    size: int
    md5: bytes
    flags: int = 0


@dataclass
class Pack:
    path: Path
    format: int
    version: tuple[int, int, int]
    flags: int
    file_base: int
    directory: int
    entries: dict[str, Entry] = field(default_factory=dict)

    def read(self, name: str) -> bytes:
        entry = self.entries[name]
        with open(self.path, "rb") as handle:
            handle.seek(entry.offset)
            data = handle.read(entry.size)
        if len(data) != entry.size:
            raise SplitError(f"{self.path}: {name} is truncated")
        return data


# --- reading and writing ----------------------------------------------------

def read_pack(path: Path) -> Pack:
    """The directory of a Godot 4 PCK (format 3 or 4, relative file base, no encryption)."""
    path = Path(path)
    size = path.stat().st_size
    with open(path, "rb") as handle:
        head = handle.read(HEADER.size)
        if len(head) < HEADER.size:
            raise SplitError(f"{path} is not a Godot PCK")
        magic, fmt, major, minor, patch, flags, base, directory = HEADER.unpack(head)
        if magic != MAGIC:
            raise SplitError(f"{path} is not a Godot PCK")
        if fmt not in FORMATS:
            raise SplitError(f"{path}: PCK format {fmt} is not supported (only {FORMATS})")
        if flags & PACK_DIR_ENCRYPTED or flags != PACK_REL_FILEBASE:
            raise SplitError(f"{path}: pack flags {flags:#x} are not supported (an encrypted or "
                             "absolute-offset pack)")
        if not FILE_BASE <= base <= directory <= size - 4:
            raise SplitError(f"{path}: the file base or directory offset is outside the file")
        handle.seek(directory)
        count, = struct.unpack("<I", handle.read(4))
        pack = Pack(path, fmt, (major, minor, patch), flags, base, directory)
        for _ in range(count):
            raw_length = handle.read(4)
            if len(raw_length) != 4:
                raise SplitError(f"{path}: the directory is truncated")
            length, = struct.unpack("<I", raw_length)
            raw = handle.read(length)
            tail = handle.read(ENTRY_TAIL.size)
            if len(raw) != length or len(tail) != ENTRY_TAIL.size:
                raise SplitError(f"{path}: the directory is truncated")
            name = raw.rstrip(b"\0").decode("utf-8").removeprefix("res://")
            offset, entry_size, md5, entry_flags = ENTRY_TAIL.unpack(tail)
            if entry_flags:
                raise SplitError(f"{path}: {name} has file flags {entry_flags:#x} (encrypted or a removal)")
            if not name or name in pack.entries:
                raise SplitError(f"{path}: empty or repeated entry name {name!r}")
            start = base + offset
            if start + entry_size > directory:
                raise SplitError(f"{path}: {name} lies outside the data area")
            pack.entries[name] = Entry(name, start, entry_size, md5)
        if handle.read(1):
            raise SplitError(f"{path}: data after the directory")
    return pack


@dataclass(frozen=True)
class Source:
    """Where an output entry's bytes come from: a span of an input pack, or bytes."""
    path: Path | None = None
    offset: int = 0
    size: int = 0
    md5: bytes = b""
    data: bytes | None = None


def _copy(handle, source: Source, digest) -> int:
    if source.data is not None:
        handle.write(source.data)
        digest.update(source.data)
        return len(source.data)
    written = 0
    with open(source.path, "rb") as reader:
        reader.seek(source.offset)
        while written < source.size:
            chunk = reader.read(min(COPY_BYTES, source.size - written))
            if not chunk:
                raise SplitError(f"{source.path} is truncated")
            handle.write(chunk)
            digest.update(chunk)
            written += len(chunk)
    return written


def write_pack(path: Path, entries: dict[str, Source], *, fmt: int, version: tuple[int, int, int]) -> dict:
    """Write a deterministic pack; returns {"bytes", "entries", "sha256"}. A copied entry
    whose bytes do not hash to its input md5 fails the write."""
    if fmt not in FORMATS:
        raise SplitError(f"PCK format {fmt} is not supported")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = []
    with open(path, "wb") as handle:
        handle.write(b"\0" * FILE_BASE)
        for name in sorted(entries):
            source = entries[name]
            position = handle.tell()
            padding = (-position) % ALIGN
            if padding:
                handle.write(b"\0" * padding)
                position += padding
            digest = hashlib.md5()
            size = _copy(handle, source, digest)
            md5 = digest.digest()
            if source.data is None and source.md5 and md5 != source.md5:
                raise SplitError(f"{name}: its bytes do not match the md5 the input pack records")
            table.append((name, position - FILE_BASE, size, md5))
        padding = (-handle.tell()) % ALIGN
        if padding:
            handle.write(b"\0" * padding)
        directory = handle.tell()
        handle.write(struct.pack("<I", len(table)))
        for name, offset, size, md5 in table:
            raw = name.encode("utf-8")
            raw += b"\0" * ((-len(raw)) % 4)  # Godot pads to 4 bytes, no extra NUL
            handle.write(struct.pack("<I", len(raw)) + raw + ENTRY_TAIL.pack(offset, size, md5, 0))
        handle.seek(0)
        handle.write(HEADER.pack(MAGIC, fmt, *version, PACK_REL_FILEBASE, FILE_BASE, directory)
                     + b"\0" * HEADER_RESERVED)
    return {"bytes": path.stat().st_size, "entries": len(table), "sha256": sha256(path)}


def sha256(path: Path) -> str:
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


# --- what goes where --------------------------------------------------------

def bucket(name: str, buckets: int) -> int:
    return int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16) % buckets


def classify(name: str) -> tuple[str, str] | None:
    """(pack name, feature) for an entry the rules move, else None (the core)."""
    if name == MANIFEST:
        return None
    for rule in RULES:
        if rule.match(name):
            pack = rule.pack if rule.buckets == 1 else f"{rule.pack}-{bucket(name, rule.buckets)}"
            return pack, rule.feature
    return None


def _length_prefixed(data: bytes, prefix: bytes) -> list[str]:
    """The strings Godot's binary encodings store with a u32 length before them (Variant
    strings, PackedStringArray items with their NUL, binary-resource paths) that begin with
    `prefix`."""
    found = []
    for match in re.finditer(re.escape(prefix), data):
        start = match.start()
        if start < 4:
            continue
        length, = struct.unpack_from("<I", data, start - 4)
        if not len(prefix) <= length <= len(data) - start:
            continue
        raw = data[start:start + length].rstrip(b"\0")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if text.startswith(prefix.decode()) and not re.search(r"[\x00-\x1f]", text):
            found.append(text)
    return found


def project_settings(pack: Pack) -> dict[str, bytes]:
    """{setting: its encoded value} from project.binary (ECFG), or {setting: text} from a
    text project.godot."""
    if PROJECT_BINARY in pack.entries:
        data = pack.read(PROJECT_BINARY)
        if data[:4] != b"ECFG":
            raise SplitError(f"{PROJECT_BINARY} is not an ECFG file")
        count, = struct.unpack_from("<I", data, 4)
        position, settings = 8, {}
        for _ in range(count):
            if position + 4 > len(data):
                raise SplitError(f"{PROJECT_BINARY} is truncated")
            key_length, = struct.unpack_from("<I", data, position)
            key = data[position + 4:position + 4 + key_length].decode("utf-8")
            position += 4 + key_length
            value_length, = struct.unpack_from("<I", data, position)
            settings[key] = data[position + 4:position + 4 + value_length]
            position += 4 + value_length
            if position > len(data):
                raise SplitError(f"{PROJECT_BINARY} is truncated")
        return settings
    if PROJECT_TEXT in pack.entries:
        settings, section = {}, ""
        for line in pack.read(PROJECT_TEXT).decode("utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1]
            elif "=" in stripped and not stripped.startswith(";"):
                key, value = stripped.split("=", 1)
                settings[(section + "/" if section else "") + key.strip()] = value.encode("utf-8")
        return settings
    raise SplitError("the pack holds neither project.binary nor project.godot")


def uid_text(uid: int) -> str:
    """ResourceUID::id_to_text: base 34, a-y then 0-8, most significant first."""
    if uid < 0:
        return "uid://<invalid>"
    characters = []
    while True:
        digit = uid % 34
        characters.append(chr(ord("a") + digit) if digit < 25 else chr(ord("0") + digit - 25))
        uid //= 34
        if not uid:
            break
    return "uid://" + "".join(reversed(characters))


def uid_paths(pack: Pack) -> dict[str, str]:
    """{uid://...: entry name} from .godot/uid_cache.bin and the uid lines of .import files."""
    paths = {}
    if UID_CACHE in pack.entries:
        data = pack.read(UID_CACHE)
        count, = struct.unpack_from("<I", data, 0)
        position = 4
        for _ in range(count):
            uid, length = struct.unpack_from("<qI", data, position)
            position += 12
            path = data[position:position + length].rstrip(b"\0").decode("utf-8", "replace")
            position += length
            paths[uid_text(uid)] = path.removeprefix("res://")
    for name in pack.entries:
        if name.endswith(".import"):
            match = re.search(r'(?m)^uid="(uid://[a-z0-9]+)"', pack.read(name).decode("utf-8", "replace"))
            if match:
                paths.setdefault(match.group(1), name[:-len(".import")])
    return paths


QUOTED_PATH = re.compile(r'"((?:res|uid)://[^"\n]*)"')
TEXT_REFERENCES = (".import", ".remap", ".tres", ".tscn")
BINARY_REFERENCES = (".res", ".scn")


def _named_paths(pack: Pack, name: str) -> list[str]:
    """The res:// and uid:// paths a resource entry names: quoted in a text resource, remap
    or import file, length-prefixed in a binary resource. Other files (images, audio,
    scripts, data) name nothing the engine follows."""
    if name.endswith(TEXT_REFERENCES):
        return QUOTED_PATH.findall(pack.read(name).decode("utf-8", "replace"))
    if name.endswith(BINARY_REFERENCES):
        data = pack.read(name)
        return _length_prefixed(data, b"res://") + _length_prefixed(data, b"uid://")
    return []


def boot_closure(pack: Pack) -> dict[str, list[str]]:
    """{entry: [settings that reach it]}: what must stay in the core because the engine can
    read it before the first autoload mounts the content packs."""
    uids = None
    closure: dict[str, list[str]] = {}
    pending = []
    for key, value in sorted(project_settings(pack).items()):
        if BOOT_CLOSURE_SKIPPED.match(key):
            continue
        text = value.decode("utf-8", "replace") if PROJECT_BINARY not in pack.entries else None
        named = (QUOTED_PATH.findall(text) if text is not None
                 else _length_prefixed(value, b"res://") + _length_prefixed(value, b"uid://"))
        pending.extend((path, key) for path in named)
    while pending:
        path, why = pending.pop()
        if path.startswith("uid://"):
            if uids is None:
                uids = uid_paths(pack)
            if path not in uids:
                continue
            path = uids[path]
        name = path.removeprefix("res://").lstrip("*")
        for candidate in (name, name + ".import", name + ".remap"):
            if candidate not in pack.entries:
                continue
            if candidate in closure:
                if why not in closure[candidate]:
                    closure[candidate].append(why)
                continue
            closure[candidate] = [why]
            pending.extend((named, why) for named in _named_paths(pack, candidate))
    return closure


def plan(pack: Pack) -> dict:
    """{"core": [entries], "packs": {name: {"feature": f, "entries": [...]}}, "closure": {...}}."""
    closure = boot_closure(pack)
    core, packs = [], {}
    for name in sorted(pack.entries):
        target = None if name in closure else classify(name)
        if target is None:
            core.append(name)
            continue
        group = packs.setdefault(target[0], {"feature": target[1], "entries": []})
        group["entries"].append(name)
    for name in packs:
        if not PACK_NAME.match(name):
            raise SplitError(f"content pack name {name!r} is not a lowercase id")
    return {"core": core, "packs": packs, "closure": closure}


# --- split and proof --------------------------------------------------------

def manifest_bytes(rows: list[dict]) -> bytes:
    return (json.dumps({"schema": MANIFEST_SCHEMA, "packs": sorted(rows, key=lambda row: row["file"])},
                       sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def split(monolith: Path, app_dir: Path, core_out: Path) -> dict:
    """Write app_dir/packs/*.pck and the core pack at core_out from the exported monolith;
    the monolith is left as it is. Returns the receipt (prove() checks the result)."""
    started = time.monotonic()
    monolith, app_dir, core_out = Path(monolith), Path(app_dir), Path(core_out)
    source = read_pack(monolith)
    if MANIFEST in source.entries:
        raise SplitError(f"{monolith} already carries {MANIFEST}: it is a core pack, not a monolith")
    if any(name.startswith(PACKS_DIRECTORY + "/") for name in source.entries):
        raise SplitError(f"{monolith} has entries under {PACKS_DIRECTORY}/")
    packs_dir = app_dir / PACKS_DIRECTORY
    if packs_dir.exists() and any(packs_dir.iterdir()):
        raise SplitError(f"{packs_dir} is not empty; split into a fresh stage")
    if core_out.exists():
        raise SplitError(f"{core_out} already exists")
    layout = plan(source)

    def span(name: str) -> Source:
        entry = source.entries[name]
        return Source(source.path, entry.offset, entry.size, entry.md5)

    rows = []
    for name, group in sorted(layout["packs"].items()):
        file = f"{PACKS_DIRECTORY}/{name}.pck"
        written = write_pack(app_dir / file, {entry: span(entry) for entry in group["entries"]},
                             fmt=source.format, version=source.version)
        rows.append({"file": file, "bytes": written["bytes"], "entries": written["entries"],
                     "sha256": written["sha256"], "feature": group["feature"]})
    manifest = manifest_bytes(rows)
    core_entries = {name: span(name) for name in layout["core"]}
    core_entries[MANIFEST] = Source(data=manifest)
    core = write_pack(core_out, core_entries, fmt=source.format, version=source.version)
    return {"schema": 1, "monolith": {"file": monolith.name, "bytes": monolith.stat().st_size,
                                      "entries": len(source.entries), "format": source.format,
                                      "version": ".".join(map(str, source.version))},
            "core": {"file": core_out.name, **core,
                     "data_bytes": sum(source.entries[name].size for name in layout["core"])},
            "packs": rows, "closure": {name: why for name, why in sorted(layout["closure"].items())},
            "manifest": json.loads(manifest), "seconds": round(time.monotonic() - started, 2)}


def _verify_bytes(pack: Pack, entry: Entry) -> bool:
    digest = hashlib.md5()
    with open(pack.path, "rb") as handle:
        handle.seek(entry.offset)
        remaining = entry.size
        while remaining:
            chunk = handle.read(min(COPY_BYTES, remaining))
            if not chunk:
                return False
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.digest() == entry.md5


def prove(monolith: Path, core_path: Path, packs_dir: Path) -> dict:
    """The partition proof; raises SplitError listing what is wrong."""
    source = read_pack(monolith)
    core = read_pack(core_path)
    problems: list[str] = []
    if MANIFEST not in core.entries:
        raise SplitError(f"{core_path} has no {MANIFEST}")
    manifest = json.loads(core.read(MANIFEST))
    if manifest.get("schema") != MANIFEST_SCHEMA or not isinstance(manifest.get("packs"), list):
        raise SplitError(f"{MANIFEST} has an unknown schema")
    outputs = [("core", core)]
    listed = set()
    for row in manifest["packs"]:
        file = str(row.get("file", ""))
        if not re.fullmatch(PACKS_DIRECTORY + r"/[a-z0-9][a-z0-9-]*\.pck", file) or file in listed:
            problems.append(f"{MANIFEST}: bad or repeated pack file {file!r}")
            continue
        listed.add(file)
        path = Path(packs_dir) / file.removeprefix(PACKS_DIRECTORY + "/")
        if not path.is_file():
            problems.append(f"{file}: listed but not written")
            continue
        pack = read_pack(path)
        actual = {"bytes": path.stat().st_size, "entries": len(pack.entries), "sha256": sha256(path)}
        for key, value in actual.items():
            if row.get(key) != value:
                problems.append(f"{file}: {key} is {value}, the manifest says {row.get(key)}")
        if not isinstance(row.get("feature"), str):
            problems.append(f"{file}: no feature field")
        outputs.append((file, pack))
    folder = Path(packs_dir)
    written = {f"{PACKS_DIRECTORY}/{path.name}" for path in folder.glob("*")} if folder.is_dir() else set()
    problems.extend(f"{file}: written but not listed" for file in sorted(written - listed))
    for label, pack in outputs:
        if (pack.format, pack.version) != (source.format, source.version):
            problems.append(f"{label}: format/version {pack.format} {pack.version} differs from the monolith's")
    owner: dict[str, str] = {}
    for label, pack in outputs:
        for name, entry in pack.entries.items():
            if label == "core" and name == MANIFEST:
                continue
            if name in owner:
                problems.append(f"{name}: in {owner[name]} and in {label}")
                continue
            owner[name] = label
            original = source.entries.get(name)
            if original is None:
                problems.append(f"{name}: in {label} but not in the monolith")
            elif (entry.size, entry.md5) != (original.size, original.md5):
                problems.append(f"{name}: size/md5 in {label} differ from the monolith's")
            elif not _verify_bytes(pack, entry):
                problems.append(f"{name}: the bytes in {label} do not hash to their md5")
    problems.extend(f"{name}: in the monolith but in no output" for name in sorted(set(source.entries) - set(owner)))
    if problems:
        raise SplitError(f"{len(problems)} partition problems:\n  " + "\n  ".join(problems[:40]))
    return {"entries": len(source.entries), "outputs": len(outputs),
            "core_entries": len(core.entries), "manifest": manifest}


def summary(layout: dict, pack: Pack) -> list[str]:
    lines = [f"core: {len(layout['core'])} entries, "
             f"{sum(pack.entries[n].size for n in layout['core']) / 1e6:.1f} MB"]
    for name, group in sorted(layout["packs"].items()):
        lines.append(f"{PACKS_DIRECTORY}/{name}.pck: {len(group['entries'])} entries, "
                     f"{sum(pack.entries[n].size for n in group['entries']) / 1e6:.1f} MB"
                     + (f" (feature {group['feature']})" if group["feature"] else ""))
    lines.extend(f"boot closure: {name} <- {', '.join(why)}" for name, why in sorted(layout["closure"].items()))
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("plan", help="print what each pack would hold")
    show.add_argument("pck", type=Path)
    run = commands.add_parser("split", help="split a monolith and prove the partition")
    run.add_argument("pck", type=Path)
    run.add_argument("app_dir", type=Path, help="the folder that gets packs/")
    run.add_argument("--core-out", type=Path, required=True)
    run.add_argument("--receipt", type=Path)
    check = commands.add_parser("prove", help="prove an existing split")
    check.add_argument("pck", type=Path)
    check.add_argument("core", type=Path)
    check.add_argument("packs_dir", type=Path)
    options = parser.parse_args(argv)
    try:
        if options.command == "plan":
            pack = read_pack(options.pck)
            print("\n".join(summary(plan(pack), pack)))
        elif options.command == "split":
            receipt = split(options.pck, options.app_dir, options.core_out)
            receipt["proof"] = prove(options.pck, options.core_out, options.app_dir / PACKS_DIRECTORY)
            receipt["proof"].pop("manifest")
            if options.receipt:
                options.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            print(f"core {receipt['core']['bytes'] / 1e6:.1f} MB, {len(receipt['packs'])} content packs, "
                  f"{receipt['seconds']} s; partition proved")
        else:
            result = prove(options.pck, options.core, options.packs_dir)
            print(f"partition proved: {result['entries']} entries in {result['outputs']} packs")
    except (SplitError, OSError, ValueError) as error:
        print(f"pck_split: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
