# Resonant Vault — concept package

The ten-panel brief for one section of the Amethyst Barrens insides map. This
directory is the concept, not the build.

The built geometry lives at `../amethyst_barrens_insides/`, where the Vault is
one of four sections sharing a single map with blackspace between them, in the
Eternal Lands convention. The server map key `resonant_vault` now names that
whole insides map, and `eloria-server`'s `maps.txt` calls it "Amethyst Barrens
Insides" for that reason.

See `../AMETHYST_BARRENS_INTERIORS.md` for the four sections, the round trip and
what is not verified.

`concept.json` lists the ten subjects, all of which are built:
sealed approach, laboratory gallery, archive aisle, crystal brazier, experiment
table, lens room, containment cell, energy crossing, research hall, and the
material study.

The detail board in `references/` is truncated to 786,444 bytes and only its
first rows decode — the same cut that affects nine of the eleven region boards.
The intact board was supplied separately and is what the Vault was authored
from; it is not committed here because it was not supplied as a file in this
package.
