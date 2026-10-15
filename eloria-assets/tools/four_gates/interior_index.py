"""Single source of truth for where each Four Gates interior meets the street.

Both builders read this: the city places a door and a trade sign at each entry
and writes the portal into its manifest, and the interior uses the same point as
the target its exit portal returns the player to. Keeping one list means the two
can never drift.
"""

from __future__ import annotations

import math
from typing import Dict, List

PLATEAU_Y = 31.0


def _at(angle_degrees: float, radius: float) -> List[float]:
    a = math.radians(angle_degrees)
    return [round(math.cos(a) * radius, 2), PLATEAU_Y,
            round(math.sin(a) * radius, 2)]


def _facing(angle_degrees: float) -> float:
    """Yaw that turns a door outward to face the nearest road."""
    return round(-math.radians(angle_degrees) + math.pi * 0.5, 4)


# tier 1 -- the six rooms a player enters every session
INTERIORS: List[Dict] = [
    {"id": "four-gates-lantern-row", "name": "Lantern Row",
     "quarter": "agricultural", "trade": "general goods",
     "angleDegrees": 102.0, "radius": 178.0, "signSlots": 3,
     "blurb": "Covered market hall; general goods and Nima Vey's counting desk."},
    {"id": "four-gates-reedworks", "name": "The Reedworks",
     "quarter": "agricultural", "trade": "tailoring",
     "angleDegrees": 68.0, "radius": 268.0, "signSlots": 2,
     "blurb": "Cordage, canvas and cloth from mirror reed; dye vats and looms."},
    {"id": "four-gates-stormglass-house", "name": "The Stormglass House",
     "quarter": "service", "trade": "alchemy and glass",
     "angleDegrees": 248.0, "radius": 186.0, "signSlots": 3,
     "blurb": "Glazier and alchemist; buys stormglass, sells lenses and reagents."},
    {"id": "four-gates-mirrorsmith-forge", "name": "Mirrorsmith's Forge",
     "quarter": "service", "trade": "smithing",
     "angleDegrees": 292.0, "radius": 274.0, "signSlots": 2,
     "blurb": "The smithy behind the civic equipment set; repair and reforge."},
    {"id": "four-gates-ferrymans-rest", "name": "The Ferryman's Rest",
     "quarter": "service", "trade": "inn and ferry office",
     "angleDegrees": 266.0, "radius": 302.0, "signSlots": 4,
     "blurb": "Inn, tavern and the Crownwater ferry office at the north dock."},
    {"id": "four-gates-deposit-four-keys", "name": "The Deposit of Four Keys",
     "quarter": "civic", "trade": "storage and banking",
     "angleDegrees": 172.0, "radius": 122.0, "signSlots": 4,
     "blurb": "Storage and banking; four keyed vault doors and a plastered fifth."},
]

for _entry in INTERIORS:
    _entry["door"] = _at(_entry["angleDegrees"], _entry["radius"])
    _entry["yaw"] = _facing(_entry["angleDegrees"])
    # the player is returned a short step clear of the threshold
    _outward = _at(_entry["angleDegrees"], _entry["radius"] + 5.0)
    _entry["arrival"] = _outward

# The compact city's authored parcels own the external street frame. This
# changes only where each complete interior returns its player, never its
# native room dimensions, lore, contents or identity.
from pathlib import Path as _Path
import importlib.util as _importlib_util
_plan_path = _Path(__file__).resolve().parents[2] / 'maps/four-gates/source/landscape_plan.py'
if _plan_path.is_file():
    _spec = _importlib_util.spec_from_file_location('_four_gates_landscape_plan', _plan_path)
    _plan = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_plan)
    for _identity, _label, _quarter, _trade, _x, _z, _yaw, _width, _depth in _plan.SHOPS:
        _entry = next(e for e in INTERIORS if e['id'] == _identity)
        _dx, _dz = math.sin(_yaw), math.cos(_yaw)
        _entry['door'] = [_x + _dx * (_depth / 2 + .55), 31.08,
                          _z + _dz * (_depth / 2 + .55)]
        _entry['arrival'] = [_entry['door'][0] + _dx * 5.6, 31.08,
                             _entry['door'][2] + _dz * 5.6]
        _entry['yaw'] = _yaw


# Two old exit coordinates were outside the guarded actor-centre floor. These
# posts stay in the visible doorway aisle with a separate three-metre arrival.
ROOM_DOOR_POSTS = {
    'four-gates-lantern-row': {'exit': [0.,0.,5.], 'arrival': [0.,0.,2.]},
    'four-gates-deposit-four-keys': {'exit': [0.,0.,5.], 'arrival': [0.,0.,2.]},
}

def by_id(ident: str) -> Dict:
    for entry in INTERIORS:
        if entry["id"] == ident:
            return entry
    raise KeyError(ident)
