#!/usr/bin/env python3
"""Write an RGBA PNG without a third-party imaging library.

This lived in `generate_bootstrap_pack.py`, which existed to build the
Eternal Lands format data pack the retired C client loaded. The pack is gone;
the PNG writer is not, because the tools that build the Godot client's own
textures never wanted anything else from that module.
"""

from __future__ import annotations

import binascii
from pathlib import Path
import struct
import zlib


def png(path: Path, width: int, height: int, pixel) -> None:
    """Write `width` x `height` RGBA pixels, `pixel(x, y)` per texel."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF))

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(pixel(x, y))
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(bytes(rows), 9))
    data += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
