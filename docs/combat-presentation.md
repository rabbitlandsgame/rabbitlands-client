# Combat, spellcasting and archery presentation

Run `godot --path godot-client res://src/dev/combat_showcase.tscn` for an offline,
looping review on production player rigs. Space pauses and R restarts. The
showcase includes channeling, aggressive casting, a defensive ward, healing,
bow draw/hold/release, and alternating sword cuts.

## Animation and event integration

`data/animations/luminous.json` exposes `cast_channel_enter`, `cast_channel`,
`cast_aggressive`, `cast_defensive`, `heal`, `cast_exit`, `ranged_draw`,
`ranged_hold`, `ranged_attack`, `attack_primary`, `attack_secondary`, and `defend`.
The existing `cast` action remains an alias for aggressive casting.

`CombatAnimationLibrary` composes and retimes the existing native skeletal
poses into ten additional clips. Faster releases follow deliberate anticipation,
then recover to idle or combat idle. Channeling and bow hold loop. Draw enters
hold automatically; movement and death can interrupt. Spell result packets
start channeling while choosing a target, then release the appropriate action.
Remote casters use the existing special-effect ids; harvest effects do not
trigger casting. Damage, hit/miss decisions and cast timing remain server-owned.

The importer supplies a bone-rest RESET animation and deterministic blending.
This removes inherited root rotation during crossfades. Cache signatures include
bone rests so differently proportioned rigs do not share an incorrect reset.
Actor command sequences distinguish a new strike from a health/equipment update
that merely restates the previous command.

## Assets and visual effects

The original `amberwood_ranger_bow.glb`, `sunmane_ranger_bow.glb`, and
`ranger_arrow.glb` use faceted yew, leather wrapping, brass collars, antler tips,
a steel broadhead and teal fletching. Regenerate them with:

```sh
python eloria-assets/tools/build_ranger_assets.py
```

The bow grip is at its origin, limbs run along Y, and +Z points toward the
drawing hand. The arrow origin is the nock and its point is at -Z. Bow visuals
64–67 use the two-hand attachment mode; the existing Amberwood and Sunmane
equipment entries 164/165 use the animated bow presentation too. These bows
are outside the one-handed/off-hand visual bank.

Both hands drive the bow: the grip stays in the left palm, the string and arrow
nock follow the right fingers, limbs flex under tension and the string recoils
on release. Props load lazily. Projectile flight uses the same arrow mesh from
the nock, with a shallow arc, distance-dependent duration, and a tapered trail.
Ground shots land near the surface rather than at chest height.

Action effects follow animation time and posed hands. Sword trails follow the
actual equipped blade. Healing uses rising green/gold motes, wards use thin blue
seals, and offensive spells use hand sparks and contrasting impact particles.
World effects distinguish healing, wards, poison and offensive impacts using the
server's current effect mapping. Effects are world-depth-tested, cast no shadows,
and respect Graphics → particles; bow geometry remains visible when effects are
disabled. No additional textures or third-party assets are required.

### Caster-to-target spell exchanges

Targeted magic uses a moving luminous core and short, tapered trails instead of
the former straight cylinder spanning both actors. A soft procedural shader
provides radial cores and feathered ribbon edges in the Compatibility renderer.
Flights gather at the posed hands, release with the casting gesture, follow the
target's chest, then trigger the contact flash, particles and ground runes on
arrival. Flight lasts 0.22–0.62 seconds by distance; the trail dissolves over
0.24 seconds and the impact fades over 1.1 seconds. This is presentation timing;
server damage and spell outcomes are unchanged.

Effect 2 uses an ember core and a focused wake, effect 0 uses winding venom,
effect 1 uses arcing healing wisps, and effect 10 returns braided mana energy
from the target to the caster. The new spellbook gives Magic Bolt (83), Frost Bolt (84), Radiation Bolt (85)
and Life Drain (86) distinct trails; life drain returns from target to caster. Self
casts and events without a second actor keep their local effects.

Endpoints use weak actor references and retain their last valid positions if an
actor disappears. Once released, a trail does not drag behind a moving caster.
Flight geometry is analytic and bounded (28 segments per strand), so its shape
does not depend on frame rate or accumulate an unbounded particle history.

Run `godot --path godot-client res://src/dev/spell_exchange_showcase.tscn` to
review all four exchanges on player rigs. Space pauses and R restarts.
`tests/integration/rendered_spell_exchanges.gd` captures gathering, flight,
contact and dissolution. Set `ELORIA_RECORD_SPELLS=1` to also capture 30 fps
frames for a movie; `ELORIA_ARTIFACT_DIR` chooses the output directory.

### Power tiers

Visual intensity follows the **invested spell power (P1–P10)** from the magic
system, including its existing Magic skill and nexus gates. It does not infer a
remote caster's investment from the local power selector or damage numbers.
P1 retains the base appearance. P1–P5 rise to the former maximum: 1.9× core
size, 1.63× rune radius, 2.08× particles and 1.27× color intensity. P6–P10
follow a steeper curve, reaching 4.2× core/trail/hand-spark size, 2.2× rune
radius, 4.5× particles (144 impact particles maximum) and 2.7× color intensity.
P10 more than doubles the former maximum's core size, brightness and particle
count. Spatial spread grows more slowly to keep the effect concentrated.
Actor size, skeletal animation speed, flight trajectory and arrival timing stay
constant. Power is retained when channel entry becomes its sustained loop and
reset for a different action.

The `spell_visuals_v1` capability adds the actual cast power to spell results and
world effects. The server sends each observer one version of the event; older
clients receive the original packet. Legacy events received by the new client
use P1. Both client and server changes must be installed for live power-aware
effects. The client preserves the selected power while targeting; the server validates
and spends it only after resolving the target,
even if preferences change before target selection. Command/hotkey casts use
the same presentation path, including self, target and ally delivery.

Run `res://src/dev/spell_power_showcase.tscn` for a P1/P5/P8/P10 comparison.
Set `ELORIA_COMPARE_SPELL_POWER=1` when running the rendered spell exchange test
to capture that comparison instead of the four spell families.

## Spell families and utility casting

`SpellAnimationLibrary` generates eleven casting variants from each player rig's
own aggressive, defensive and healing clips. Arm, forearm and hand rotations
shape the gestures while preserving grounded feet and the existing release
and recovery timing. The runtime installs these clips once per actor.

Individual wards use distinct magic shells, heat wisps, frost rays and radiation
orbits. Elemental Ward combines three colored arcs. Dispel sends cleansing
sparks outward; Transmute raises golden coin rings; Recall forms a layered
portal. Area spells add expanding waves at the selected ground location.
Power increases detail and intensity without changing the selected area.

The 86 spell variants use one shared catalogue. The spellbook filters by name,
effect, damage type and scope. `magic_selection.gd` captures the chosen power
and routes actor, area, inventory and portal selections through request 202.
Server state 212 supplies inventory conversion quotes, portal choices and area
pulses. Inventory casts include durable instance identity where applicable.
The encyclopedia generates its spell entries from this same catalogue.

Set `ELORIA_SPELL_FAMILY_PAGE=1` when rendering spell exchanges for the four new
combat trails, or `2` for Elemental Ward, Dispel, Transmute and Recall. The UI
integration test `tests/test_magic_book_ui.gd` exercises production packet
handling, power capture, utility choices, search filters and area effects.

## Verification

```sh
godot --headless --path godot-client --script res://tests/test_combat_presentation.gd
godot --headless --path godot-client --script res://tests/test_spell_flights.gd
godot --headless --path godot-client --script res://tests/test_animation_looping.gd
godot --headless --path godot-client --script res://tests/test_animation_gate.gd
python godot-client/tests/test_held_props.py -v
godot --path godot-client --rendering-method gl_compatibility --script res://tests/integration/rendered_combat_showcase.gd
godot --path godot-client --rendering-method gl_compatibility --script res://tests/integration/rendered_world_effects.gd
godot --path godot-client --rendering-method gl_compatibility --script res://tests/integration/rendered_spell_exchanges.gd
```

The combat test exercises all 16 creation rigs, transition recovery, interruption,
full-draw arrow clearance, bow alignment after crossfades, nock attachment,
command replay, spell-result and aim packets, and grounded projectile endpoints.
The showcase capture writes `godot-client/test-artifacts/combat/combat-showcase.png`.
The existing world-effects integration exercises the production main scene and
real reduced packet fixtures. CI runs the new headless combat test.

Local validation also found an existing failure in `test_protocol.gd`: its
locomotion assertion requires walk/run facing offsets above 15 degrees while
the existing checked-in map sets both to zero. This change preserves those
locomotion settings.

Power verification covers tier growth, bounded particle counts, unchanged
trajectories/timing, channel transitions, actual power in the production packet
path, and legacy decoding. Server checks in `tests/test_spell_visuals.py` cover
mixed-capability observers, self/ally casts, rejected casts and a preference
change during target selection. The focused server power/visual tests pass;
the broader existing protocol suite has unrelated equipment-catalog and
incomplete inventory/trade/food fixtures.
