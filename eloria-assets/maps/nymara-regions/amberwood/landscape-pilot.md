# Amberwood: inhabited landscape pilot

The served exterior is now 384 × 384 metres (64 × 64 ELM tiles; 768 × 768
half-metre authored collision samples). Its authored survey remains in the older
576-metre space, then `source/compact_plan.py` compresses outdoor journeys while
preserving the village's principal X and Z bands at human scale. Buildings and
furniture retain their mesh dimensions. This is deliberately specific to this
settlement; other regions need their own landform and spacing decisions.

The design retains the Mother Tree, Moot Hall, Amber Hall, mill, harbour, great
arch, ash frontier and required regional/interior connections. Broad shoulders,
quieter ground, connected meadows and uneven habitat groves improve the view from
the gameplay camera. Household gardens, door paths and grouped market stock
connect dwellings to useful activity. Two stalls serve the harbour and quarry.

The river network follows its downhill survey with wider bank shoulders. Seven
bridges use surveyed landings. Walking collision is rasterised from deck
triangles instead of an inscribed circle. The mill crossing clears the full-size
mill house, and a work lane connects the coppice and Boar Run to the eastern bank
of the ridge crossing. Source entrance posts move with the ground and server
contracts.

## Borders

The Whitehorn approach opens through a graded saddle into increasing snow and
conifers. The eastern approach changes from ash to stone and alpine turf. The
southern road reaches wet pasture and heather. Each has an ordinary direction
sign and a road station, with dedicated march stones and repeated march furniture
removed. Beyond the served edge, a 140-metre static terrain view is sampled from
the corresponding neighbouring package; source hashes are in the manifest.

The client still loads another map on crossing. These views show terrain and do
not simulate neighbouring inhabitants. Reciprocal approaches and terrain views
should be designed in pairs during the next regional pass. The packet quay
retains its ferry identity.

The client registry opts Amberwood into `landscapeTransitions`. The server's
clickable crossing identity and map glyph remain, but the client adds no second
portal model or ring over the authored road scenery. Other regions retain their
current presentation until their own landscape pass.

The combined estate package now inherits bounds, walking surfaces, roof
cutaways, lights and spawn points from the four source interiors, and generates
its own floor-plan minimap. The old compositor omitted these runtime contracts.
The server collision compiler also preserves surveyed deck heights when its
legacy content-approach pass joins nearby posts; a low-bank approach must not
carve across a high bridge.

## Rebuild

From this package's `source` directory:

```
python rebuild_landscape.py --server <server-checkout> --data <generated-data>
```

The script keeps the change scoped to Amberwood and its associated interiors.
`--skip-build` starts at collision postprocessing; `--passes-only` stops before
server sync. The server migration checks its revision before changing coordinates.
Package digests are updated only for this pilot after marker metadata is final.
Other region sizes remain unchanged in this pilot. Most rollout targets are
300–400 metres, with a possible capital exception.

The accompanying review bundle contains untouched before/after client captures,
vector annotations, a revised minimap overview, a full regional diagnosis,
verification logs and the region-by-region rollout proposal. Capture harnesses
are in `godot-client/tests/integration/rendered_landscape_survey.gd` and
`rendered_landscape_walk.gd`. The former is an offline composition survey; the
latter uses authoritative movement against an isolated local server.


## Paired Whitehorn follow-up

The supporting giant at source (-12, -263) opens the old-growth camera view without moving the Mother Tree or its platforms. A worn grove walk connects the opening. The northern view now samples compact Whitehorn (396 m), including ordinary conifer silhouettes and its quieter snow material. The current shared-border, village and grove regression run passes. See [Whitehorn’s redesign](../whitehorn_range/landscape-redesign.md) and the workspace `work-output/inhabited-whitehorn` review.
