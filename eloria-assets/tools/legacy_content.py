"""Keep the continent-v2 content overlay out of the legacy content tools (serve plan CV13).

From the landing-isle server on, the server's content loaders (eloria.maps.load_maps, eloria.spawns.load_spawns,
eloria.harvesting.load_harvesting, eloria.npcs.load_npcs, eloria.interactives.load_interactives,
eloria.questlines.load_questlines, and World.load_configured_npcs through load_npcs) read
config/eloria/continent-v2/<table> beside each base table and append the isle rows. The legacy tools read, check or
rewrite the twelve-territory content, so they must see exactly the base tables: an isle portal landing on a legacy
map (the sw_isle ferry arrives at Crownwater) would change their standable masks and arrivals, and a tool that loads
the maps base-only while another loader still reads the overlay refuses the overlay's NPCs and portals as naming
unknown maps. One process-wide switch keeps every loader consistent.

read_base_only(server) puts the server checkout on sys.path just long enough to import its eloria.content_overlay
and call configure(False). An older server checkout has no overlay module, so there is nothing to switch off; the
ImportError is the sign of that. An eloria package this process already imported from another checkout is left
alone (the tools refuse to mix checkouts anyway). The switch is per process: a tool that runs another legacy tool as
a subprocess relies on that tool switching itself off too.
"""
from __future__ import annotations

from pathlib import Path
import sys


def read_base_only(server) -> bool:
    """Switch the server checkout's content overlay off for this process. True when it was switched off, False when
    the checkout has no overlay (or no eloria package) to switch, or this process's eloria is another checkout's."""
    root = Path(server).resolve()
    path = str(root)
    sys.path.insert(0, path)
    try:
        from eloria import content_overlay
    except ImportError:
        return False
    finally:
        sys.path.remove(path)
    if not Path(content_overlay.__file__).resolve().is_relative_to(root):
        return False
    content_overlay.configure(False)
    return True
