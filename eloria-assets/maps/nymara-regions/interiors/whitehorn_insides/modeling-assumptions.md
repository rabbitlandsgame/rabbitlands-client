# Whitehorn Range insides modelling assumptions

Decisions taken where the concept package did not determine the answer.

1. **Four insides on one map, not four packages.** Eternal Lands puts every
   inside belonging to a region on one map with unwalkable void between them,
   and sends the player to a different arrival depending on the door used. This
   follows that, and follows the Amethyst Barrens build, which did it first
   here. It buys one GLB, one collision grid and one server map key instead of
   four, and one load instead of a load per doorway.

2. **The gutters are 20 m minimum, checked at build time.** The offsets are
   hand-chosen and a later edit that grows a section could silently join it to
   its neighbour; the first sign would be a player walking out of the mine into
   the barrow. `interiors._assert_gutters` measures the built footprints and
   fails the build instead.

3. **The temple lost its mine and its crevasse.** They were rooms inside the
   temple in the first version of this package. As separate sections with their
   own surface doors they are reachable directly from the adit on the region
   map, which is what the region's geometry already implied.

4. **The through-line is invented.** `concept.json` names ten subjects and
   nothing that connects them. "The glacier is eating the monastery" is this
   build's reading, chosen because it explains all ten in one idea and gives
   the plan a direction: intact masonry at the door, cracked masonry in the
   colonnade, a half-swallowed arch, then rooms cut in ice, then the workings.
   A reviewer may reasonably want a different story.

5. **Nine spaces for ten subjects in the temple.** "Prayer columns" and "ice granite silver
   materials" are not separate rooms: the first is what the colonnade *is*, and
   the second is a study bench in the sanctuary. Building ten rooms to match a
   ten-panel board would have produced a room whose only purpose was to hold
   three sample blocks.

6. **The interior's detail board could not be used.** It is truncated to
   786,446 bytes and does not decode. Player-scale reference comes from the
   parent region's intact board — its temple facade, shrine alcove, ice cave
   and mine panels — plus `concept.json`'s subject list.

7. **`whitehorn_silver` was added to the shared material table.** The concept
   names an ice/granite/silver study and the 56-material table had no white
   metal, only dark iron and warm brass. It is deliberately 0.45 metallic, not
   1.0: a fully metallic material with no reflection probe has nothing to
   reflect and renders black in both the offline rasteriser and Godot. The
   Amethyst build hit that on verdigris and brass.

8. **Passage widths are chosen against the collision quantisation**, not for
   looks. Half-widths in (1.75, 2.00) leave a gap between what the grid marks
   walkable and what the grounding ray can hit. See `validation-report.md`.

9. **The crevasse span is the exterior's `kit.rope_bridge`.** Reusing it rather
   than authoring an indoor variant is deliberate: the monks who bridged the
   gorge outside are the ones who bridged this, and the geometry says so.

10. **The mine and the crevasse are lit, and the ice is not.** Every lamp is a
   hung lantern or a votive cup at a place a person would have put one. Nothing
   in the ice chambers is lit except where people go, so the blue comes from
   ambient bounce rather than from emissive ice.

11. **The interior is region-local code.** `source/interiors.py` lives
   with Whitehorn rather than in `_toolkit/amberwood/interiors.py`, which holds
   Amberwood's four only because that is where they grew. An interior is region
   content; a fifth in the toolkit would put Whitehorn's rooms in every other
   region's import path.

12. **`export_glb` and `build_collision` are duplicated** from
   `amberwood/source/build_interiors.py`. They carry no region-specific data and
   belong in `_toolkit/`. They were not promoted because Amberwood's package was
   regenerated recently and must stay byte-reproducible; moving code out from
   under its build without re-verifying it is how a reproducibility claim
   quietly stops being true. Promoting them and re-verifying both regions in one
   commit is the right follow-up.

13. **Names are invented**, as with the region above, and expected to be
    replaced when authoritative region text exists.
