# The Drowned Crown

The older palace beneath The Crown Basilica, half taken by the lagoon.

**This directory holds the concept only.** The Drowned Crown is now a *section*
of `../crownwater_insides/`, the single map Crownwater's four insides share with
unwalkable blackspace between them. There is no `world.glb` here; the built
geometry is in that package, and the server map is `drowned_crown.elm`.

`concept.json` is the authored brief and is the reason this is the only
Crownwater inside whose programme was given rather than invented. All ten of its
subjects - flooded vestibule, water galleries, submerged arch, shell altar,
statue court, water channel, collapsed dome, air pocket, objective hall, and the
limestone/shell/brass material study - are built as authored spaces.

| | |
|---|---|
| Walkable cells | 17,100, **0** without a surface under them |
| Section of | `crownwater_insides` |
| Entered by | the `basilica-undercroft` portal on the Crownwater map |
| Client frames | 8, in `../crownwater_insides/references/captures/` |

The water line is held flat at y = -6.05 and the floors step down beneath it, so
the wading deepens as you go in until the collapsed dome lets the light back.

**Its detail board is truncated** (786,446 bytes, the same defect as fifteen of
the seventeen region boards), so there is no panel comparison. The subjects were
worked from `concept.json`'s written list.

Its server portal, long contested between Crownwater and Mirrorhold, is resolved
in Crownwater's favour. See `../CROWNWATER_INTERIORS.md`.
