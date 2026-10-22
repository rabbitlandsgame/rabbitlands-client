# Rabbit Lands bestiary

Open `creatures.html` directly in a browser. It is one self-contained file:
the creature data, portrait atlas, styles and interactions work offline.

The three sortable tables follow the comparison-table format of
[EL-DB's creature page](https://el-db.com/Creatures.html). The visual design,
game data and rendered portraits are Rabbit Lands content.

The guide includes every current definition, with searchable names and
habitats, family and A/D filters, named bosses, endgame creatures, summoning,
field aggression checks, full combat attributes, drops and filtered CSV export.
Numbers are native species stats; encounter scaling and equipment can modify
them. The special-encounter table includes creatures without ordinary field
placements, named bosses and tame livestock.

The October 21 wildlife revision ranks adult animals by size, defensive
anatomy, dangerous names and magical identity. Bison is passive. The A/D
average is an arithmetic mean of the authored stats, not a simulated measure
of player difficulty; the creature details show the supporting combat stats.
The owner's calibrated anchors are Crown Stag 30/30, Moss Boar 40/40 and
passive Golden Bison 80/80 A/D, with nearby family variants.

The October 22 revision makes Cave Spider and Nightweave Spider giant endgame
creatures at 205/200 and 220/210 A/D. Their detail entries include measured body
dimensions and server collision footprints. The engine-rendered size comparison
is `giant-spiders-20261022.png`; the player body provides the scale reference.

The further October 22 revision enlarges Giant Ant, Giant Wasp, Giant Leech,
Stag Beetle, Praying Mantis, Giant Centipede, Manymouth Crab and Giant Antlion.
Both Attack and Defense are between 125 and 175. Size comparisons beside a
player are `giant-creatures-20261022-1.png` and `giant-creatures-20261022-2.png`.

Amethyst Scorpion is enlarged to about 4.5 m long and 4.1 m tall with its
raised tail. It stays passive at 185/180 A/D and 1,200 health, between Giant
Centipede and Cave Spider. `giant-scorpion-20261022.png` compares all three
with a player at their transmitted in-game sizes.

Rebuild from the client root with the sibling server checkout available:

```powershell
python tools/build_creature_bestiary.py
```

The builder reads only public creature, map, spawn, recipe and drop definitions
from `../rabbitlands-server/config/eloria/`. It reads current models from the
client actor registry and refuses retired procedural paths. It never modifies
models or runtime assets. Portrait render caches stay in the ignored
`.local/asset-authoring/working/bestiary-20261021/` directory. The HTML template
is maintained at `tools/bestiary/template.html`.
