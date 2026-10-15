# Creature production QA

The thirty-two native Nymara creatures were rebuilt from the concept art to
production anatomy. The previous pass assembled every creature from three
stacked ellipsoids and four straight cylinders on a shared twenty-one bone
rig, with no textures on thirty-two of the thirty-five creature GLBs, so a
fox, a toad and a tortoise differed only in colour and blob proportions.

Each creature is now authored from a body plan in
`eloria-assets/tools/creature_anatomy.py`: a swept elliptical torso with real
chest, waist and haunch shaping; a shaped skull with muzzle, hinged jaw, ears,
eyes and nose; limbs tapered through credible knee, hock and ankle pivots down
to grounded feet with claws or cloven hooves; tapering tail chains; and the
horns, antlers, tusks, shells, quills, dorsal scutes and wing membranes that
distinguish one archetype from the next. Ten body plans cover canid, felid,
sabre-cat, ursine, suid, cervid, sprawling reptile, mustelid, lagomorph,
anuran, chelonian and drake anatomy.

Skinning is smooth multi-bone rather than rigid one-bone binding: weights come
from an inverse-distance blend over a curated candidate set per body part, so
shoulders, hips and necks deform without a rear paw pulling on the jaw. The
rig grew to twenty-four bones, adding a chest bone and a four-segment tail.
Bone *names* are unchanged where the runtime depends on them —
`godot-client/data/actors/models.json` binds attachment points to `head`,
`body` and `neck`.

All seven clips named by `godot-client/data/animations/creature.json`
(`Idle_A`, `Walk`, `Jog`, `Fighting_Idle`, `Sword_Attack`, `Hit_Chest`,
`Death_A`) are authored per body plan, with walk and trot gaits, a coiled
lunge-and-bite attack whose contact lands near 55% of the clip, and a death
that topples onto the flank and stays there. Locomotion is in place: the root
never translates horizontally, because the client drives world position.

## Files

- `creature_concept_comparison.png` — bind-pose renders of the checked-in GLBs
  beside the concept-art cell each creature was authored against.
- `creature_concept_comparison.json` — machine-readable pairing of creature
  slug, GLB path, concept sheet and grid cell.

## Reproducing

```
python3 eloria-assets/tools/build_native_nymara_glbs.py
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py
python3 eloria-assets/tools/validate_creature_glbs.py \
    --catalog godot-client/data/actors/native_asset_catalog.json \
    --models godot-client/data/actors/models.json \
    --animations godot-client/data/animations/creature.json
python3 eloria-assets/tools/render_creature_qa.py <glb...> --output sheet.png
```

The build is deterministic: texture seeding uses `zlib.crc32`, not the
per-process-salted built-in `hash`, so rebuilding reproduces every GLB byte
for byte.


## The wider concept-art roster

A second pass added **139 creatures** covering every distinct design across the
sixteen concept sheets. Those sheets hold 192 cells, but they are not 192
subjects: `47a41963`/`4dc46727` are alternate renders of one Amethyst Barrens
roster, `93197c59`/`1e840e1e` likewise for Sunmane Steppe, and the three
Amberwood sheets repeat many of each other's subjects. `creature_roster.py`
records one model per distinct design and maps every duplicate cell onto the
model that already covers it, so all 192 cells resolve while nothing is built
twice.

Creatures not already named by the repository were named from their design and
the locale of their sheet - Amethyst Scorpion, Lanternwyrm, Barrow Sovereign,
Reedmask Stalker, Mirrorhold Siren, Bramble Stag and so on.

### Skeleton families

The quadruped rig cannot express most of the new roster, so seven further
families were added in `creature_families.py`, each with its own rest
skeleton, geometry and gaits:

| Family | Creatures | Notes |
| --- | --- | --- |
| quadruped | 72 | extended with bovine, equine, pinniped and gryphon plans |
| biped | 47 | warrior, knight, monarch, mage, revenant, golem, construct, brute, primate, treant, duelist |
| amorphous | 14 | wisps, shard swarms, sprites, vortices, tentacled horrors - these hover |
| serpent | 10 | nine-segment coil chain; snake, sea serpent, eel, wyrm, hydra, naga |
| avian | 10 | folded wings at rest; wader, seabird, songbird, raptor, owl, harpy |
| arachnid | 7 | eight legs on three segments; spider, scorpion, crab |
| insect | 6 | six legs, elytra or membrane wings; beetle, moth, mantis |
| fish | 5 | swimming gait; pike, billfish, ray, armoured, axolotl |

Every family keeps the same runtime contract: bones named `root`, `body`,
`neck` and `head`, one root, at most four influences per vertex, and the seven
clip names in `data/animations/creature.json`.

### Actor types

The roster occupies **428-566**, one contiguous block after every range already
present in `models.json` (which ended at 427). Actor-type allocation belongs to
`eloria-server`; these ids are reserved client-side for the server to adopt.

### Grounding and hovering

Rest poses are settled so no creature starts below the floor, and every clip is
ground-clamped. Wisps, swarms and elementals are marked `hovers` in the
catalogue: they legitimately never touch `y = 0`, and the validator checks them
for floor penetration rather than contact.

### Files

- `roster_concept_comparison.png` / `.json` - each new creature beside the
  concept figure it was authored from. Concept crops use the true figure bounds
  found by `concept_sheet_index.py` rather than a uniform grid, because the
  subjects are not evenly sized or spaced and a fixed grid clips wings,
  antlers and tails.


## Surface fidelity

The first two passes shipped a single 256px **luminance** map per creature that
only modulated a flat base colour, so every fox, golem and serpent carried the
same grey grain and no surface relief at all.

`creature_surfaces.py` replaces that for the whole library - the original
thirty-two included - with, per creature:

* a **full-colour 256px albedo** that bakes the creature's own palette into the
  pattern, so `base` carries the body and `accent` tints markings, plates, moss
  and rime;
* a **192px tangent-space normal map** derived from the *same* height field, so
  the relief lines up with the pattern rather than fighting it;
* a **160px keratin pair** for horn, antler, hoof, quill and armour trim.

Twenty-six surface kinds are authored - fur, pelt, coat, fleece, bristle,
quill, hide, scale, fishscale, scute, shell, chitin, feather, warty, stone,
moss, barnacle, bark, metal, crystal, ice, cloth, slick, water, energy and dust
- each with its own height construction, plus per-creature markings (stripes,
rosettes, dapples, speckles, bands, blazes).

Because the albedo now carries the colour, the base-colour factor stays white
so the palette is not applied twice; the underside shares the grain and tints
with a factor instead of carrying a second map. The validator fails any
creature whose materials lack a colour texture or a normal map, and any
material that is magenta.

The ambient livestock were brought in line too: their generator previously
skipped normal maps on the grounds that livestock never cover enough screen to
pay for them, which left them the only untextured-relief creatures in the
library.

## Humanoid fidelity

The biped rig grew from 22 to 27 bones - a **waist** so the torso bends instead
of pivoting at the hips, **cloak** bones that carry capes and robes, and
**prop** bones in each hand so a staff or greatsword tracks the grip rather
than floating beside it.

Eleven shared body plans were not enough to tell forty-seven humanoids apart,
so `BIPED_DETAIL` overrides the plan per creature. Each one now carries what
the concept art gives it: crowns, helms with visors and crests, hoods, wide
duelling hats, tricorns, conical straw hats, masks, antlers, branch crowns,
thorn collars, crystal shards, orrery rings, cairn stacks, mill yokes and
waterwheels; and staves, sceptres, swords, greatswords, cutlasses, rapiers,
spears, tridents, halberds, axes, sickles, hooks, lantern staves, books, kite
and round shields. Geometry per humanoid roughly doubled, from about 1,950
triangles to about 4,100.


## Elementals

The fourteen amorphous creatures were the weakest group in the library: one
"core plus tendrils" rig gave every wisp, swarm, jellyfish and water nymph the
same silhouette - a ball standing on legs. None of them have a skeleton in the
concept art at all, so the family now carries **eight distinct forms**:

| Form | Creatures | Shape |
| --- | --- | --- |
| swarm | shardling, mirrorwing | no body; a cloud of angular shards or winged motes around a lit core |
| spectre | barrens, moorlight, ember wisps | a rising plume trailing streamers, with floating orbs |
| jelly | medusa tidepriest | a domed bell with a scalloped rim and a tentacle curtain |
| kraken | gilded devourer, mirefather leviathan | a heavy mass with a toothed maw and radial tentacles |
| nymph | springfly, verdant naiad, shardbound archivist | torso, head and arms dissolving into a turning skirt |
| ooze | lanternwake sprite | a settled translucent mound with salvage suspended inside |
| vortex | sluice elemental | curling arms sweeping out of a turning column |
| lance | tidelance construct | a ringed brass lance trailing a plume |

Streamers carry a travelling wave down each chain rather than swinging
rigidly, swarms and vortices turn on the spot, and the attack coils every
strand back before lashing them forward together.

Materials matter as much as shape here. Elementals are authored with
**alpha-blended translucency and an emissive glow** taken from the plan, and
their shards, orbs and props take the creature's own palette rather than the
bone-white keratin used for horn - which is what had turned every crystal
swarm grey. The lanternwake sprite's lantern, mill wheel and plank are only
visible because the slime around them is translucent.

`render_creature_qa.py` was taught to blend: opaque geometry draws first with
depth writes, then transparent surfaces back to front, and emissive is added
after shading. Without that these creatures could not be judged at all.


## Concept fidelity pass

Three systemic problems were keeping the library from reading like the
artwork, and none of them were fixable one creature at a time.

**Palettes were being invented, not sampled.** The first sampling pass kept
only the lit half of each concept figure, clustered it, and then pushed
saturation and value up independently per channel. Concept art is warm-lit, so
that pipeline drove almost every creature to the same handful of hues: a brown
bear and a grey-green troll both came out gold with one channel pinned at 238.
`extract_concept_palettes.py` now takes the median of the figure's *mid-tone*
band -- highlight and cast shadow both lie about a creature's own colour --
and lifts it toward an albedo value by a single factor across all three
channels, so the hue survives the lift. `apply_concept_palettes.py` bakes the
result into `creature_roster.py` and the legacy table, so a palette pass is
reproducible rather than hand-applied.

**Growth was scattered, not placed.** Moss, bramble, crystal and barnacles
were sampled with a world-space direction whose horizontal component was
always full magnitude. That works by accident on a quadruped, whose spine is
horizontal, and fails completely on a biped, whose spine is vertical: every
tuft pointed along the trunk axis and ended up inside the torso, which is why
moss trolls came out bald and mossy bears came out as uniform bushes. Growth
now rides the surface normal of the tube around the local spine direction,
biased toward its ridge; moss and vine hang with gravity, fungus caps turn to
face the sky, and only the mineral growths spike outward. Upright bodies also
expose their shoulders and arms to growth, and it stops at the collar so it
never buries the face.

**Creatures sharing a body plan were the same model twice.** Forty-seven
humanoids came from eleven plans and forty quadrupeds from twelve, so a wolf
and a hyena differed only in colour. `concept_proportions.py` measures each
segmented concept figure -- how lanky, how top-heavy, how solid, how tapered
it is *relative to the other creatures on its plan* -- and those four ratios
drive damped multipliers on the plan's heights, girths, shoulder and hip
widths, limb lengths and skull size. The silhouettes now diverge from the
artwork rather than from invention, and the ratios are clamped so a single odd
crop nudges a model without deforming it.

Alongside those: moth wings gained camber, veins and eyespots instead of
drawing as one flat plate; crystal growth erupts in a spread of unequal shards
rather than a tidy one-sided comb; bramble grows as a studded runner rather
than a fan of quills; and the wisps' plumes twist as they rise, throw flame
tongues, and let draped strands fall instead of stalling at the horizontal.

`build_creature_qa_sheets.py` regenerates all three comparison sheets and
their manifests, so the QA evidence in this directory can be rebuilt from the
checked-in GLBs rather than reconstructed by hand:

```
ELORIA_CONCEPT_DIR=/path/to/sheets \
    python3 eloria-assets/tools/concept_sheet_index.py
ELORIA_CONCEPT_DIR=/path/to/sheets \
    python3 eloria-assets/tools/extract_concept_palettes.py
ELORIA_CONCEPT_DIR=/path/to/sheets \
    python3 eloria-assets/tools/concept_proportions.py
python3 eloria-assets/tools/apply_concept_palettes.py
ELORIA_CONCEPT_DIR=/path/to/sheets \
    python3 eloria-assets/tools/build_creature_qa_sheets.py
```


## Second concept fidelity pass: geometry the generators could not express

The library validated and animated correctly, and its palettes and proportions
were measured rather than guessed, but many models still did not *read* as the
creature in the art. Rendering each GLB beside the artist's own cut figure and
naming the disagreement in words, the same answer came back over and over: the
missing thing was not a parameter, it was a kind of geometry the toolchain had
no way to make. A swept tube cannot have a hole in it, and a smooth-shaded
sphere cannot have a flat facet.

`concept_figures.py` keys every creature slug to the artist's cut figure for
its cell, and `concept_compare.py` puts model and art side by side at matched
height. That pair is the instrument the whole pass was worked against, and it
is how each of these was found and each fix confirmed.

### New primitives

| Primitive | In `creature_anatomy.py` | What it makes possible |
| --- | --- | --- |
| `branch_system` | recursive forking limb, returning its tips | crowns, twig hands, antler racks; foliage hangs on branch ends rather than being scattered over the whole shape |
| `woven_trunk` | a trunk of separate twisting strands | daylight through a treant's bole -- the one thing surface detail cannot fake |
| `root_flare` | buttress roots off the foot of a trunk | treants stand on roots rather than on feet |
| `foliage_cluster` | leaf mass built from overlapping lobes | canopies that are not one smooth blob |
| `swirl_ribbon` | a band that coils around the line it follows | flame, spirit-hair, running water and kraken arms |
| `facet_shell` | flat-shaded plates over a lit inner shell | crystal carapaces with the glow leaking out of the seams |
| `plated_shell` | overlapping oriented slabs around a limb | golems and constructs built from discrete blocks, staggered like masonry |
| `orbit_plates` | curved armour plates floating in a ring | arcane constructs whose armour hangs off a lit core, nothing touching |
| `debris_field` | broken pieces hanging in the air | a body that has come apart and not finished falling |
| `metal_band` | a banding ring around a limb | the bronze trim the art puts at every wrist and ankle |
| `feather_row` | overlapping flight feathers along an edge | wings with a serrated outline instead of a coloured triangle |

`MAT_CORE`, a sixth material slot, carries whatever is lit from inside: a
treant's heart-hollow, the light in a geode carapace, the centre of a wisp, the
sockets of a spirit. It has to be its own material because the shell around it
stays dark, and that contrast is the entire effect -- a whole-body emissive
destroys it.

### What each group disagreed about

* **Treants, dryads and sprites** were smooth barrels with three bone-white
  spurs on top. They are now braided boles with gaps through them, forking bark
  crowns spreading wide and low, twig hands, root feet and a lit heart at the
  front of the chest where the art puts it.
* **Wisps and elementals** were cones with a ring of straight triangular spikes
  -- an upturned insect. The spikes are coiling ribbons now, the plume is a body
  rather than a spear rooted at the floor, and every one of them has the bright
  centre the art draws it around.
* **Crystal fauna** were smooth ellipsoids in a crystal colour, and the beetle's
  elytra were routed through the keratin material, so the one creature whose
  shell is made of amethyst had a bone-white back. They are faceted mosaics over
  a lit interior.
* **Moths** held their wings almost flat, so they vanished to a line in profile.
  `wing_lift` opens them, the hind pair follows the fore pair up, and the crystal
  moth's veins are drawn in the core material as leaded glass.
* **Humanoids** had ball heads, closed-egg hoods that sealed the face away, and
  robes that were one straight tube with a disc on the bottom. They now have
  brow, sockets, nose, cheekbone and mouth; open cowls with an overhanging peak;
  and robes that flare, fold and end in a shaped hem.
* **Quadrupeds** shared a silhouette because `ARCHETYPE_TWEAKS` is keyed by
  archetype and the roster names body plans, so none of it ever applied.
  `QUADRUPED_DETAIL` is where per-creature features from the art live now, and
  the mane was rebuilt as a mass of hanging locks rather than a smooth collar.
* **Krakens and oozes** were a table on stilts and a smooth green tent. The arms
  coil at varied lengths; the slime carries its mass high and hangs runnels with
  a bead on the end of each.

### A second sweep, after looking at the whole library at once

Rebuilding the roster comparison sheet and reading all 139 pairs together
turned up four more problems that only show at library scale.

* **Crabs were spiders.** The crab plan inherited the spider's narrow body and
  projecting head, so six crabs across four regions read as pale spiders. A
  crab's carapace is half again as wide as it is long, it has no projecting
  head at all, its abdomen folds flat underneath rather than trailing behind,
  and it holds its claws folded in front. All of that is in the plan now, with
  eyestalks, which are the one feature that reads as "crab" from any angle.
* **Wings were coloured triangles.** A membrane stretched between two curves
  has no edge to catch light and no serration in its outline. `feather_row`
  lays overlapping flight feathers along the trailing edge, longest toward the
  tip, and the same primitive fans the tail.
* **`upright` was only tilting the neck.** Applied there alone, an owl and a
  heron kept a duck's horizontal teardrop with a tall neck stuck on the front.
  It tilts the body now, and the art stands both of them on their tails.
* **Growth was sized against the wrong thing.** Surface growth scaled with the
  creature's nominal `scale`, which is near 1 for a songbird and a bear alike,
  so an owl was wearing leaves a bear's size and vanished underneath them.
  Growth is sized against the local girth of the body it grows on. This is the
  change with the widest reach in the pass -- it moves every creature in the
  `GROWTH` table, and the mossy bear and mossy troll are the clearest wins.
* **Swarms were laid out on a lattice.** The regular helix the motes walked
  spaced them so evenly that a swarm read as confetti on a grid. They turn
  around the core now, tighter at the middle and ragged at the edge, jittered
  from the same seeded generator so the cloud stays reproducible.

Averaging every bright coloured pixel together blended the glow with whatever
metal trim shared the highlights, and the trim usually won on volume -- a river
stone golem came back gold when its core and its runes are plainly cyan.  The
bright band is clustered by hue now and the most *saturated* cluster is taken
rather than the largest, because emitted light is the purest colour on a figure
even when it is not the most abundant.

### Golems and constructs

Thirteen creatures across two body plans, and every one of them was a smooth
capsule in a stone colour with a small pad on each shoulder.  The art draws
them as *stacks of discrete blocks* -- you can count the boulders in a cairn
golem's forearm -- with a lit gem set in the chest and bronze banding at the
joints.  A swept limb with a rock texture on it is a sausage, and no normal map
fixes a silhouette.

`plated_shell` is the stone counterpart of `woven_trunk`: each plate is a short
oriented puck standing proud of the surface along its own outward normal, so it
catches its own highlight and casts its own shadow line, and rows are staggered
like masonry so the joints do not line up into stripes.  A scattering of plates
carries a lit glyph, which is what the art carves into them.  The smooth tube
stays underneath as the body the plates are bolted to, so the gaps read as
shadowed joints rather than as holes -- and the plates use the body's own stone
rather than the keratin material, because routing them through keratin made
them read as bones strapped on rather than as the creature itself.

The proportions moved with it: a small head clear of enormous shoulders, a
narrower pelvis than chest, and the plating held off the crotch so two legs
read as two legs.  Four numbers were wrong on the way and each was found by
measuring rather than squinting -- the socket ring was built at the gem's
radius scale and came out four times the width of the core it framed; widening
`hip_w` to part the legs also inflated the pelvis, because `hip_r` derives from
it, until the hips were wider than the chest; and `arm_splay` at .20 threw the
hands out to two-thirds of the figure's height on each side.

Two attachments in the same group were thin hoops where the art has machinery.
The orrery rings are an armillary now -- broad banded rings of unequal size,
each tilted off the others, with crystals set into the bands and a lit sphere
at the centre -- and the waterwheel has two rims, an axle, spokes and paddle
boards, mounted behind the shoulder rather than standing beside the head.

**Block size matters as much as block shape.** The first pass put six rows of
seven plates round a torso, and forty-two segments at that scale reads as
gravel rather than as masonry -- the art's cairn golem is built from perhaps a
dozen boulders you can count. Twelve round the torso and six down a limb,
each standing further proud and cut with fewer facets, gives the countable
stacked-stone silhouette the art has.

**The thirteen do not share a build.** `plate_shape` cuts the plates five
ways -- rounded boulders for the cairn and ivy golems, angular scale for the
frost and crownwater guardians, big flat slabs for the temple and tide
wardens, erupting shards for the amethyst golem, and smooth banded drums for
the river stone golem, whose limbs the art draws as stacked cylinders rather
than as rock at all. On top of that: the wheelwarden crouches on its knuckles
under the wheel on its back, the millstone golem carries a timber yoke with a
stone slung off each end, the shattered sentinel is coming apart with its
pieces still in the air, and the two arcane constructs are built round a core
with their armour floating off it -- the colossus has no legs the art shows at
all, so it wears a banner instead.

Plating reaches the quadrupeds too, which is what the coral shell golem
needed: it was a plain bear where the art gives it a plated carapace and a lit
gem over the shoulder. The crystal-backed lizard, the geode tortoise and the
cairnback tortoise take the same treatment.

The halberd and the staff were rebuilt while they were in frame -- a dark
triangle a tenth of a scale unit across read as a small black flag tied to a
pole, and the wardens' staves ended in a plain ball. They are a crescent axe
head with a back hook and a spear point, and a ring finial holding a lit
stone.

The core measurement had to be fixed to serve them.  Sampling the top three per
cent of luminance caught mostly specular bloom, and on the golems the near-grey
average that came back had a hue that was pure noise, which the emissive
saturation then amplified into a confident acid yellow.  The band is the top
tenth now, with a higher saturation floor, and `_saturate` refuses to amplify a
colour that is already neutral.  The frost golem measures cyan and the amethyst
golem violet, which is what the art draws.

### Serpents, fish, and four that were on the wrong body

The serpent and fish families had not been touched at all, and between them
they are fifteen creatures.

**Ten serpents were ten lengths of hose.** The rig held the body at a constant
height in a shallow horizontal wiggle, which is not a pose any serpent in the
art holds: it coils all of them, the body looping up off the ground and the
head carried above it. The body is a spiral now, its radius set from its own
length so about one turn uses it up -- a serpent in the art occupies a compact
coil roughly as wide as it is tall. Getting it to the floor took care:
descending only as far as the rear height left the whole family hovering,
because the spine stops at body height while the tube around it has already
tapered to nothing. They also gained the two things the art gives every one of
them and the models had neither of -- a ridge of dorsal spines down the back,
which is what makes the coils read as coils from the side, and a head plainly
bigger than the body behind it with a crown of fins sweeping off the skull.

The naga was half a person with nothing in the person half, so a coral
priestess came out as a snowman on a coil. It has a ribcage, a shoulder
girdle, arms with hands and a face now, and no longer wears the serpent snout
over that face.

**Five fish were five torpedoes with a paddle on the back.** A rectangle on
the end of a tube is the most model-looking thing a fish can have. The caudal
fin is two swept lobes with a notch between them, the dorsal runs most of the
back with an anal fin to match, and the pectorals sweep back at half again
their old reach. The manta was not a manta -- at .42 girth against .70 length
it was a torpedo with a bulge, against an art figure half again as wide as it
is long -- so its wing is a swept diamond with the tip carried back and the
trailing edge cut concave, plus the cephalic lobes that say "manta" before
anything else does. The axolotl's external gills were three spikes that read
as whiskers; they are three stalks a side carrying a fan of filaments, which
is the biggest thing on its head in the art.

**Four were simply on the wrong body.** The Verdant Naiad was the worst pair
in the library: cell 11 of the Verdant Stair sheet is a river *naga*, and the
roster had it on the amorphous vortex plan, so it came out as a cloud of
acid-green shards with two floating orbs. The jungle gorilla's head sat a
tenth of a unit proud of its shoulders and was swallowed whole. The bronze
diving beetle wore its shell in the keratin material -- a white ribbed loaf --
over three segments far enough apart to read as three eggs. The hummingbird
was a finch, with a short bill and legs to stand on.

### Two kings, and a creature with no art

Cell 0,0 of the elemental-lords sheet is a *drowned lich king* -- teal and
gold, spiked crown, gemmed staff, an orb of cold light -- and the roster had
that cell keyed to an entry named "Verdant Crown King".  The name said forest
monarch while the art, and therefore the sampled palette, said drowned king.

`drowned_lich_king` is a new roster entry that takes the cell and the palette
that was always measured from it, and is built to what the figure shows: skull
face under a tall spiked crown, layered pauldrons, a lit core, the orb in the
off hand and a ragged robe stopping above the ankle.  `verdant_crown_king`
keeps its actor type and becomes what its name says -- a branch crown carrying
leaf mass, bark shoulders, a seed of green light at the breast.

The roster grows to 140 and the actor-type block to 428-567.  Nothing pinned
the old upper bound: the test derives the range from the roster's own length.

**The forest king has no concept art, and is marked as having none.**  The
sentinel sheet stem `authored` means "no figure to be compared against", and
such a creature shows a placeholder in the comparison sheets rather than a
match.  It would have been easy to render the finished model into the concept
delivery and let the tool find it, and that would be worse than useless: the
whole method here is to put the model beside an *independent* picture of what
it should look like and read off the disagreement.  A model compared against a
picture of itself always agrees, which would turn these sheets from evidence
into decoration.  Its design brief is in
`eloria-assets/concepts/creatures/README.md` for a real concept pass to work
from, and its palette is the one number in the roster that is chosen rather
than sampled.

Finding this also turned up a real defect in the resolver: an unknown sheet
stem fell through to `root / ""` and globbed the delivery root, which matched
whatever stray file happened to share the cell index -- it had silently keyed
the forest king to a river otter merchant.  Unknown stems return no figure now.

### The four gaps left open by the golem pass

The waterwheel guardian has the stone arch in its chest with water falling
through it into a pool; the temple guardian carries a little pillared shrine on
its shoulder; the arcane colossus reaches with talon clusters below its halo
rather than having no hands at all.  And where a figure carries two bright inks
-- lit water and metal trim -- the core sampler picks the more saturated
cluster, which on the cascade golem and the wheelwarden is the brass rather
than the water.  Both clusters are measured; `CORE_TINT_OVERRIDE` names the one
that is actually the light.

### Colour and value, measured

* `concept_growth_tints.py` samples what is *growing* on each creature from its
  own figure. Deriving it from the kind alone made every leaf green, which is
  right for the Verdant Stair and wrong for the Amberwood, an autumn wood whose
  foliage measures amber (127, 92, 41), and badly wrong for the thornwood dryad,
  whose canopy is crimson. Only vegetation is corrected; mineral crusts already
  take the creature's own palette.
* The same tool reports the hue of each figure's brightest lit feature, which is
  where the treant's amber heart and the barrens wisp's blue centre come from.
* `concept_value_gains.py` found the systemic colour problem. The sampled *hues*
  are good -- the median hue error against the concept figures is about two
  degrees -- but the *values* were compressed: a whitehorn yak and a coastal
  gull, both painted nearly white, rendered within a few points of a black iron
  death knight. Gains only lift, and lifting blends toward white rather than
  multiplying, because multiplying clips and the creatures that needed it most
  were exactly the ones that could not move.

  The correction is capped at 1.55 and deliberately does not close the whole
  gap. It cannot: the shading falloff in `render_creature_qa.py` puts even a
  pure white albedo near 90 against the 128 a pale concept figure measures, so
  the remainder is only reachable by washing every pale creature out to white.
  What is left is a renderer exposure question rather than a palette one.

### Fixed on the way

The builders wrote backslash paths into the asset catalogue on Windows, which
Godot does not resolve and which made the catalogue completeness test fail on
Windows builds alone. Paths are POSIX-form on every platform now, in both
`build_native_nymara_glbs.py` and `sunmane/creatures.py`, and the test compares
in that form rather than the host's.

### Budget

171 creatures, mean 6,287 triangles, 84 MB on disk, with the woody and plated
hero creatures between 12,000 and 30,000 -- up from a mean of 4,945 and 74 MB. The
mean is well under the ceiling this pass was allowed, because the triangles
went into features the art shows and the models lacked rather than into
tessellating smooth shapes more finely; most creatures simply did not need
more geometry than they had.

### Reproducing this pass

`ELORIA_CONCEPT_FIGURES` points at the directory of per-creature cut figures;
the tools fall back to segmenting whole sheets from `ELORIA_CONCEPT_DIR` when
only those are available.

```
ELORIA_CONCEPT_FIGURES=/path/to/figures \
    python3 eloria-assets/tools/concept_growth_tints.py --table
ELORIA_CONCEPT_FIGURES=/path/to/figures \
    python3 eloria-assets/tools/concept_growth_tints.py --core
ELORIA_CONCEPT_FIGURES=/path/to/figures \
    python3 eloria-assets/tools/concept_value_gains.py --table
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py
python3 eloria-assets/tools/build_native_nymara_glbs.py
ELORIA_CONCEPT_FIGURES=/path/to/figures \
    python3 eloria-assets/tools/concept_compare.py <slug...>
ELORIA_CONCEPT_FIGURES=/path/to/figures \
    python3 eloria-assets/tools/build_creature_qa_sheets.py
```

Run `sunmane/creatures.py` before `build_native_nymara_glbs.py`: the ambient
livestock GLBs come from the former and are catalogued by the latter.
