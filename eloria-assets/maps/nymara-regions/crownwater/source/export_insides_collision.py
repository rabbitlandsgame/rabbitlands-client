#!/usr/bin/env python3
"""Write the server-side walk grid for the Crownwater insides map.

The composition of this map is known here and nowhere else, so this is where
the server's collision for it comes from. Everything but the region's own
parameters lives in `_toolkit/export_insides_collision.py`; see that module for
the format and for why `--downsample` is stated rather than assumed.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_toolkit"))

from export_insides_collision import cli

if __name__ == "__main__":
    sys.exit(cli(description=__doc__.splitlines()[0],
                 package="crownwater_insides",
                 out="drowned_crown",
                 tiles=64,
                 downsample="stride",
                 arrivals=False))
