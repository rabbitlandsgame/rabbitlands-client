"""Gauntlets: instanced event maps, one linear route per theme.

A gauntlet borrows a region's look and its creatures and lays them along a
single road: a staging hall, a run of legs each barred by a gate that opens
when the fight in front of it is done, a fork where the party chooses its
way, a boss court, and a vault with the reward cache and the way out. The
rooms come from `rooms.py`, the route from `designs.py`, the package from
`build.py`; the server's instance files, spawn groups and drops are written
from the same designs by the server's `tools/author_gauntlets.py`.
"""
