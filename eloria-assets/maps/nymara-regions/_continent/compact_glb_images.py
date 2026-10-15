"""Compact repeated buffer-view payloads in a self-contained GLB.

The continent terrain exporter gives every authored surface a stable image,
texture and material record.  Many of those records intentionally reference
the same PNG source, and exported meshes can contain byte-identical attribute
or index views.  Keep every JSON record and index, but let exact payloads
share one physical range.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct


MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


class GlbCompactionError(ValueError):
    pass


def _chunks(data: bytes) -> tuple[dict, bytes]:
    if len(data) < 28:
        raise GlbCompactionError("GLB is truncated")
    magic, version, total = struct.unpack_from("<III", data)
    if magic != MAGIC or version != 2 or total != len(data):
        raise GlbCompactionError("expected one complete GLB 2.0 document")
    offset = 12
    json_length, kind = struct.unpack_from("<II", data, offset)
    offset += 8
    if kind != JSON_CHUNK or offset + json_length + 8 > len(data):
        raise GlbCompactionError("expected JSON followed by one BIN chunk")
    try:
        document = json.loads(data[offset:offset + json_length].rstrip(b" ").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlbCompactionError("invalid GLB JSON") from error
    offset += json_length
    binary_length, kind = struct.unpack_from("<II", data, offset)
    offset += 8
    if kind != BIN_CHUNK or offset + binary_length != len(data):
        raise GlbCompactionError("expected exactly one terminal BIN chunk")
    return document, data[offset:]


def _align(buffer: bytearray) -> None:
    while len(buffer) % 4:
        buffer.append(0)


def _validated_views(document: dict, binary: bytes) -> tuple[list[dict], int]:
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or "uri" in buffers[0]:
        raise GlbCompactionError("only one embedded GLB buffer is supported")
    length = buffers[0].get("byteLength")
    if not isinstance(length, int) or length < 0 or length > len(binary):
        raise GlbCompactionError("invalid embedded buffer length")
    padding = binary[length:]
    if len(padding) > 3 or any(padding):
        raise GlbCompactionError("BIN padding is not canonical")
    views = document.get("bufferViews")
    if not isinstance(views, list):
        raise GlbCompactionError("bufferViews are required")
    ranges = []
    for index, view in enumerate(views):
        if not isinstance(view, dict) or view.get("buffer", 0) != 0:
            raise GlbCompactionError(f"bufferView {index} is not in the embedded buffer")
        start, size = view.get("byteOffset", 0), view.get("byteLength")
        if not isinstance(start, int) or not isinstance(size, int) or start < 0 or size < 0:
            raise GlbCompactionError(f"bufferView {index} has an invalid range")
        if start % 4 or start + size > length:
            raise GlbCompactionError(f"bufferView {index} is unaligned or out of range")
        ranges.append((start, start + size, index))
    # Existing exact aliases are safe and make the operation idempotent.  Any
    # partial overlap is ambiguous and must not be rewritten.
    ordered = sorted(ranges)
    for left, right in zip(ordered, ordered[1:]):
        if right[0] < left[1] and right[:2] != left[:2]:
            raise GlbCompactionError(
                f"bufferViews {left[2]} and {right[2]} partially overlap")
    covered = bytearray(length)
    for start, end, _ in ranges:
        covered[start:end] = b"\x01" * (end - start)
    if any(value and not mark for value, mark in zip(binary[:length], covered)):
        raise GlbCompactionError("embedded buffer has unreferenced non-padding bytes")
    return views, length


def compact_document(document: dict, binary: bytes) -> tuple[dict, bytes, dict]:
    """Return an equivalent document/BIN pair with exact view bytes shared."""
    views, logical_length = _validated_views(document, binary)
    images = document.get("images", [])
    if not isinstance(images, list):
        raise GlbCompactionError("images must be an array")
    image_mime_by_view: dict[int, str] = {}
    for index, image in enumerate(images):
        if not isinstance(image, dict) or "uri" in image:
            raise GlbCompactionError(f"image {index} is not embedded")
        view = image.get("bufferView")
        mime = image.get("mimeType")
        if not isinstance(view, int) or not 0 <= view < len(views) or not isinstance(mime, str):
            raise GlbCompactionError(f"image {index} lacks a valid bufferView and mimeType")
        previous = image_mime_by_view.setdefault(view, mime)
        if previous != mime:
            raise GlbCompactionError(f"bufferView {view} has conflicting image MIME types")
    for index, accessor in enumerate(document.get("accessors", [])):
        if not isinstance(accessor, dict) or "sparse" in accessor:
            raise GlbCompactionError(f"accessor {index} uses an unsupported structure")
        view = accessor.get("bufferView")
        if view is not None and (not isinstance(view, int) or not 0 <= view < len(views)):
            raise GlbCompactionError(f"accessor {index} has an invalid bufferView")
        if view in image_mime_by_view:
            raise GlbCompactionError(f"bufferView {view} is shared by image and accessor data")

    output = bytearray()
    # Keep image MIME identity as the image-only compactor did. Other views
    # can share a range only after both their digest and complete bytes match;
    # the latter makes hash collisions harmless.
    payloads_by_digest: dict[tuple[str, str, bytes], list[tuple[bytes, int]]] = {}
    unique_image_keys: set[tuple[str, bytes]] = set()
    duplicate_image_views = 0
    duplicate_views = 0
    saved_payload_bytes = 0
    for index, view in enumerate(views):
        start, size = view.get("byteOffset", 0), view["byteLength"]
        payload = bytes(binary[start:start + size])
        mime = image_mime_by_view.get(index)
        category = "bufferView" if mime is None else "image"
        identity = "" if mime is None else mime
        digest_key = (category, identity, hashlib.sha256(payload).digest())
        matches = payloads_by_digest.setdefault(digest_key, [])
        matching = next((offset for previous, offset in matches if previous == payload), None)
        if matching is not None:
            offset = matching
            duplicate_views += 1
            if mime is not None:
                duplicate_image_views += 1
            saved_payload_bytes += size
        else:
            _align(output)
            offset = len(output)
            output.extend(payload)
            matches.append((payload, offset))
        if mime is not None:
            unique_image_keys.add((mime, payload))
        view["byteOffset"] = offset
    _align(output)
    document["buffers"][0]["byteLength"] = len(output)
    report = {
        "schema": 2,
        "images": len(images),
        "uniqueImagePayloads": len(unique_image_keys),
        "aliasedImageBufferViews": duplicate_image_views,
        "bufferViews": len(views),
        "uniqueBufferViewPayloads": len(views) - duplicate_views,
        "aliasedBufferViews": duplicate_views,
        "beforeBinaryBytes": logical_length,
        "afterBinaryBytes": len(output),
        "savedPayloadBytes": saved_payload_bytes,
    }
    return document, bytes(output), report


def _encode(document: dict, binary: bytes) -> bytes:
    json_bytes = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    return (struct.pack("<III", MAGIC, 2, total)
            + struct.pack("<II", len(json_bytes), JSON_CHUNK) + json_bytes
            + struct.pack("<II", len(binary), BIN_CHUNK) + binary)


def compact_embedded_images(path: Path) -> dict:
    """Atomically compact one generated GLB and report the byte-level result."""
    path = Path(path)
    before = path.read_bytes()
    document, binary = _chunks(before)
    document, binary, report = compact_document(document, binary)
    after = _encode(document, binary)
    if len(after) > len(before):
        raise GlbCompactionError("image compaction increased the GLB size")
    temporary = path.with_name(path.name + ".compact.tmp")
    temporary.write_bytes(after)
    temporary.replace(path)
    return {
        **report,
        "beforeBytes": len(before),
        "afterBytes": len(after),
        "beforeSha256": hashlib.sha256(before).hexdigest(),
        "afterSha256": hashlib.sha256(after).hexdigest(),
    }
