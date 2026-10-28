"""Raw creature staging by default, plus the optional legacy lossless codec.

RLCZ0001 | uint64 decoded bytes | uint64 encoded bytes | SHA-256 decoded | zstd
All integers are little endian. Authored GLBs remain ordinary glTF files.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import tempfile

MAGIC = b"RLCZ0001"
HEADER = struct.Struct("<8sQQ32s")
MAX_BYTES = 512 * 1024 * 1024
MAX_ENCODED_BYTES = MAX_BYTES + MAX_BYTES // 128 + 1024
CREATURE_ROOT = "godot-client/assets/actors/native/creatures/"


class PayloadError(ValueError):
    pass


def _zstd():
    try:
        import zstandard
    except ImportError as error:
        raise PayloadError("Creature compression requires the pinned zstandard build dependency") from error
    return zstandard


def _validate_glb(raw: bytes) -> None:
    if len(raw) < 20 or raw[:4] != b"glTF" or struct.unpack_from("<II", raw, 4) != (2, len(raw)):
        raise PayloadError("Creature payload does not contain a complete glTF 2 GLB")


def encode(raw: bytes) -> bytes:
    if not 20 <= len(raw) <= MAX_BYTES:
        raise PayloadError("Creature source exceeds the supported size bound")
    _validate_glb(raw)
    packed = _zstd().ZstdCompressor(level=3).compress(raw)
    return HEADER.pack(MAGIC, len(raw), len(packed), hashlib.sha256(raw).digest()) + packed


def decode(payload: bytes) -> bytes:
    if len(payload) < HEADER.size or len(payload) > MAX_ENCODED_BYTES + HEADER.size:
        raise PayloadError("Creature payload has an invalid file length")
    magic, size, encoded_size, digest = HEADER.unpack_from(payload)
    if magic != MAGIC or not 20 <= size <= MAX_BYTES or not 0 < encoded_size <= MAX_ENCODED_BYTES \
            or encoded_size != len(payload) - HEADER.size:
        raise PayloadError("Creature payload has an invalid header or size")
    zstd = _zstd()
    try:
        frame_size = zstd.frame_content_size(payload[HEADER.size:])
        if frame_size != size:
            raise PayloadError("Creature payload frame size differs from its header")
        raw = zstd.ZstdDecompressor().decompress(payload[HEADER.size:], max_output_size=size,
                                               allow_extra_data=False)
    except zstd.ZstdError as error:
        raise PayloadError("Creature payload decompression failed") from error
    if len(raw) != size or hashlib.sha256(raw).digest() != digest:
        raise PayloadError("Creature payload decoded SHA-256 mismatch")
    _validate_glb(raw)
    return raw


def read_bytes(path: Path) -> bytes:
    """Decode a staged creature envelope; ordinary files pass through unchanged."""
    with path.open("rb") as stream:
        magic = stream.read(8)
        if magic.startswith(MAGIC[:4]):
            if path.stat().st_size > MAX_ENCODED_BYTES + HEADER.size:
                raise PayloadError("Creature payload exceeds the supported size bound")
            return decode(magic + stream.read())
        return magic + stream.read()


def source_digest(path: Path) -> str:
    """Prepared-source identity is the verified decoded GLB, never a header claim."""
    if path.suffix.lower() == ".glb":
        with path.open("rb") as stream:
            compressed = stream.read(8).startswith(MAGIC[:4])
        if compressed:
            return hashlib.sha256(read_bytes(path)).hexdigest()
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage(build: Path, app: Path, loose: set[str], *, compress: bool = False) -> dict:
    """Verify ordinary GLBs, optionally encode packaging-owned staged copies.

    The production policy keeps GLBs raw to avoid runtime decompression. Legacy
    encoding is explicit and breaks hardlinks atomically before replacing bytes.
    """
    rows = []
    for relative in sorted(loose):
        if not relative.startswith(CREATURE_ROOT) or not relative.endswith(".glb"):
            continue
        inside = relative.removeprefix("godot-client/")
        source, target = build / relative, app / inside
        # Only packaging-owned copies/links at the expected staging location.
        if (not target.resolve().is_relative_to(app.resolve()) or target.is_symlink()
                or source.is_symlink() or not source.resolve().is_relative_to(build.resolve())
                or target.resolve() == source.resolve()):
            raise PayloadError("Creature staging path escaped the package")
        raw = source.read_bytes()
        _validate_glb(raw)
        if target.read_bytes() != raw:
            raise PayloadError(f"Staged creature differs from authored input: {inside}")
        encoded = encode(raw) if compress else None
        compressed = encoded is not None and len(encoded) < len(raw)
        if compressed:
            if decode(encoded) != raw:
                raise PayloadError(f"Creature round-trip failed: {inside}")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".creature-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(encoded)
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        if read_bytes(target) != raw:
            raise PayloadError(f"Written creature round-trip failed: {inside}")
        rows.append({"path": inside, "source_sha256": hashlib.sha256(raw).hexdigest(),
                     "source_bytes": len(raw), "installed_bytes": target.stat().st_size,
                     "compressed": compressed})
    return {"format": MAGIC.decode() if compress else "glTF-2.0",
            "compression_requested": compress, "files": rows,
            "source_bytes": sum(row["source_bytes"] for row in rows),
            "installed_bytes": sum(row["installed_bytes"] for row in rows)}
