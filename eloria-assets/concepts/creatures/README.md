# Creatures authored without concept art

Every creature in `creature_roster.py` is keyed to a cell in the supplied
concept sheets, and `concept_compare.py` judges the model against that figure.
A creature with no figure has nothing to be judged against, so it is marked
with the sentinel sheet stem `authored` and carries a design brief here
instead.

**These briefs are specifications, not artwork.** They exist so that a real
concept pass has something to work from, and so that the roster records
honestly which creatures were measured from art and which were invented.

## Why there is no generated stand-in

It would be easy to render the finished model, drop the image into the concept
delivery beside the artist's sheets, and let the comparison tool find it. That
would be worse than useless. The whole method of the fidelity pass is to put
the model beside an *independent* picture of what it should look like and read
off the disagreement; comparing a model to a picture of itself always agrees,
and would quietly turn the QA sheets from evidence into decoration.

So an authored creature shows a placeholder in the comparison sheets, captioned
`no concept figure - authored, not measured`, until real art exists for it.

---

## verdant_crown_king - Verdant Crown King

**Why it exists.** Cell 0,0 of the elemental-lords sheet
(`cross-region_fantasy_enemies_bosses_sheet__01__drowned-lich-king.png`) is a
*drowned lich king*: a teal-and-gold crowned undead with a spiked crown, a
gemmed staff and an orb of cold light. The roster had that cell keyed to an
entry named "Verdant Crown King", so the name said forest monarch while the
art -- and therefore the sampled palette -- said drowned king. The lich now has
its own entry and keeps that cell and that palette. This entry keeps its actor
type (440) and becomes what its name says.

**Tier.** Elemental lord / regional boss, scale 1.72. Locale: the Verdant
Stair, though it is a cross-region boss.

**Silhouette.** An upright monarch, broad at the shoulder, whose crown is not
metal but a living rack of branches -- wider than the shoulders and carrying
leaf mass at the ends. That branch crown is the read: it should be recognisable
in black at gameplay distance and should not be confusable with the lich's
spiked metal crown or with the Amberwood dryad's antlers (the dryad's rack is
taller and narrower; this one is broader and lower).

**Build.**

| Feature | Intent |
| --- | --- |
| Crown | Forking branches, roughly 1.15x the treant crown scale, leaf clusters on the tips |
| Face | Flesh, heavy brow, full beard |
| Chest | A lit seed of green light set in a socket ring, as the golems carry |
| Shoulders | Bark plating, three overlapping slabs a side |
| Body | Robe reaching mid-shin with a ragged hem, long mantle, tabard |
| Hands | Scepter in the right |
| Growth | Leaf and vine over the shoulders and back |

**Palette.** Chosen, not measured, and this is the one number in the roster
that is not sampled from artwork: base `(54, 92, 58)` deep forest green, accent
`(198, 166, 84)` old gold. A concept pass should overwrite both.

**What art would settle.** Whether the crown is antler-like (branching from two
points) or a true circlet of many shoots; whether the figure is armoured under
the robe; what the scepter's head is; and whether the green light at the chest
is a seed, a gem or an open hollow.
