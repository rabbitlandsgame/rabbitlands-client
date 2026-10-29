"""Compare physical Godot PCK entries without decoding resource payloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct


def inventory(path: Path) -> dict[str, dict]:
    with path.open("rb") as stream:
        if stream.read(4) != b"GDPC":
            raise ValueError("not a Godot PCK")
        version, *_engine = struct.unpack("<4I", stream.read(16))
        if version not in {2, 3, 4}:
            raise ValueError("unsupported PCK format")
        flags, _base = struct.unpack("<IQ", stream.read(12))
        directory = struct.unpack("<Q", stream.read(8))[0] if version >= 3 else None
        stream.read(64)
        if flags & 1:
            raise ValueError("encrypted PCK directory")
        if directory is not None:
            stream.seek(directory)
        count, = struct.unpack("<I", stream.read(4))
        if count > 1_000_000:
            raise ValueError("unreasonable PCK file count")
        entries = {}
        for _ in range(count):
            length, = struct.unpack("<I", stream.read(4))
            if length > 1_000_000:
                raise ValueError("unreasonable PCK path")
            name = stream.read(length).rstrip(b"\0").decode("utf-8").removeprefix("res://")
            _offset, size = struct.unpack("<QQ", stream.read(16))
            digest = stream.read(16).hex()
            item_flags, = struct.unpack("<I", stream.read(4))
            if name in entries:
                raise ValueError("duplicate PCK path")
            entries[name] = {"bytes": size, "md5": digest, "flags": item_flags}
        return entries


def compare(before: Path, after: Path) -> dict:
    old, new = inventory(before), inventory(after)
    removed = [{"path": path, **old[path]} for path in sorted(old.keys() - new.keys())]
    added = [{"path": path, **new[path]} for path in sorted(new.keys() - old.keys())]
    changed = [{"path": path, "before": old[path], "after": new[path]}
               for path in sorted(old.keys() & new.keys()) if old[path] != new[path]]
    return {"before": str(before.resolve()), "after": str(after.resolve()),
            "before_disk_bytes": before.stat().st_size, "after_disk_bytes": after.stat().st_size,
            "saved_disk_bytes": before.stat().st_size - after.stat().st_size,
            "before_entry_bytes": sum(row["bytes"] for row in old.values()),
            "after_entry_bytes": sum(row["bytes"] for row in new.values()),
            "before_count": len(old), "after_count": len(new),
            "removed": removed, "added": added, "changed": changed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.before, args.after)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in {"removed", "added", "changed"}}, indent=2))


if __name__ == "__main__":
    main()
