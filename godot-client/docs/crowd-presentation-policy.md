# Crowd presentation policy

How the client keeps a crowd inside its frame budget once the server sends
crowds of a hundred or more actors: who gets a skinned body, when it is built
and given up, which bodies animate, and how many short-lived combat visuals are
alive at once. The policy lives in `src/world/crowd_presentation.gd` and
`src/world/live_effect_budget.gd`; `Main` (`src/app/main.gd`) owns the actor
nodes and applies it. The earlier studies of where a crowd's frame goes are in
[the native crowd study](native-crowd-study.md) and
[the engine profile](crowd-engine-profile.md).

## What it does

**Bodies only where they can be seen.** Every actor the server sends gets a
`ReplicatedActor3D` node, but an actor farther than `BUILD_RADIUS_METRES`
(88 m, a margin past the 80 m draw distance) from the player is configured
without its model: a *deferred* node. It keeps everything that is not the
body - identity, the picking capsule, the overhead block, the map dot, pacing
and every protocol state - so the minimap, the full map, targeting by id and
the packets that follow all work as before. It costs a handful of nodes instead
of the body's skeleton, skinned meshes, animation player, equipment and cape.

On each animation-gate pass (every 100 ms) `Main._update_animation_gate` ranks
the deferred actors inside the build radius by distance, and
`Main._update_model_builds` builds their bodies nearest first, at most
`BUILDS_PER_FRAME` (4, the old spawn budget) and `BUILD_BUDGET_USEC` of frame
time per frame. A build is a new node in the deferred one's place;
`ReplicatedActor3D.adopt_presentation_from` carries the step in progress, the
learned pace and any death time across, so the body continues where the
deferred node stood instead of snapping and relearning the server's cadence.

Arrivals are ranked the same way: in one `_sync_world` pass the nearest
arrivals inside the radius are built (`ACTOR_SPAWN_BUDGET`, 4) and every other
arrival gets a deferred node on the same pass, up to `DEFERRED_SPAWNS_PER_PASS`
(64). Before this, arrivals over the budget had no node at all until a later
pass, in dictionary order rather than nearest first.

A deferred actor inside the draw distance whose body is still queued shows a
**stand-in**: one shared plain capsule mesh in a dull brown, sized from its
footprint and scale, drawn by the gameplay camera only and casting no shadow. It is hidden
beyond the draw distance, for a corpse, and past the body cap.

A built body that has stayed beyond `RELEASE_RADIUS_METRES` (120 m) for
`RELEASE_AFTER_MSEC` (8 s) is given up again, farthest first and
`RELEASES_PER_PASS` (4) per gate pass, so a long session on a crowded map does
not keep every body it has ever passed. The player, their target and their
selection are never given up.

**Parking.** A body the server removes (REMOVE_ACTOR) is hidden, stopped and made
unpickable for `PARK_MSEC` (5 s) instead of freed, at most `PARK_LIMIT` (48) at a
time. If the same actor - same type, kind, name, name colour and guild tag -
comes back under its id in that time, it wears the parked body again: an actor
stepping out of the view radius and back, or crossing an interest-cap boundary,
is not rebuilt. A recycled id carrying someone else is built afresh. Every
other spawn field is reapplied to a revived body. Map changes clear the parking.

**Body cap (optional, off by default).** With `body_cap` above zero, only the
nearest `body_cap` actors in range have bodies, not counting the player, their
target and their selection. The cap's distance is that of the cap-th nearest
actor in range; deferred actors inside it are built, and a body is given up
only once it is `BODY_CAP_HYSTERESIS_METRES` (8 m) farther out than that, so an
actor on the boundary does not flip as the crowd mills. Past the cap an actor
keeps only its map dot: no stand-in, overhead block or picking shape - what the
server's own interest cap does to an actor it stops sending.

**Animation and skeleton gating.** The animation gate already paused bodies
outside the camera frustum and stepped those beyond 45 m at half rate. With
the gate part on:

- A body beyond the draw distance is paused even when the frustum would have
  kept it animating. Nothing of it is drawn.
- A paused body's model subtree is disabled (`ReplicatedActor3D._set_model_processing`),
  so its skeleton's modifiers and update stop too. The player was already
  stopped and the cape cloth asleep, but the skeleton itself still processed
  every frame for every paused body.
- A half-rate body's skeleton modifiers (cape cloth, weapon carry) are stepped
  with its player (`Skeleton3D.modifier_callback_mode_process` manual and
  `Skeleton3D.advance`), instead of every frame for a pose that changes every
  other one.
- In a crowd, only the `FULL_RATE_BODIES` (16) remote bodies nearest the camera
  animate at full rate; the rest of those in view are stepped at half rate,
  which plays them at the same speed with half the updates, as bodies beyond
  45 m always were.
- The half-rate bodies take turns (`stagger`): each joins the emptier of two
  groups and the groups are stepped on alternate frames. Stepped all on the
  same frame, every other frame carried every half-rate body's pose, skeleton
  update and skinning, and the frame time see-sawed by that much.
- With the quarter tier (`quarter`), only the next `HALF_RATE_BODIES` (16)
  after the full-rate ones are stepped at half rate; every body ranked after
  them - the far end of a crowd in view, ranked by distance from the camera
  with the bodies beyond 45 m - is stepped every fourth frame, in four groups
  that take turns the same way, at the same speed. A quarter-rate body's cape
  hangs.
- A clip that does not loop is still played out on a body the gate would
  pause, but at half rate rather than full (quarter rate with the quarter
  tier): in a fight the bodies behind the camera strike every round, and each
  strike used to wake them to full rate.
- Cape cloth is simulated for at most `CLOTH_BODIES` (8) remote caped bodies,
  the nearest the camera. A simulating cape claims its place as if it were
  `CLOTH_HYSTERESIS` (4) places nearer than it is, so it keeps its cloth until
  a cape that much nearer needs the place or it falls that far past the limit,
  and capes on the boundary do not take turns as a crowd mills; the limit
  itself is never exceeded. The others hang as every non-local cape already
  does at Medium and Low graphics quality. The solver is the largest single
  per-body cost of an equipped crowd.
- The gate's walk over every actor is spread over `GATE_SWEEP_SLICES` (6)
  frames; the decisions that need the whole crowd (full-rate ranks, the cloth
  budget, build ranks, releases, the overhead declutter) are taken when a sweep
  ends. A fixture that sets `_animation_gate_refresh_msec` to 0 still gets one
  whole sweep at once.

**Live effects.** `live_effect_budget.gd` bounds the short-lived combat visuals
alive at once: spells, impacts, bursts and portal flashes (`spell`, 48), arrows
and bolts (`missile`, 48), melee technique visuals (`technique`, 32) and floating
health numbers (`number`, 24). A visual that involves the player, their target
or their selection is always drawn, over the limit if need be; the rest are
drawn while there is room and skipped while there is not. Nothing already drawn
is cut short, and the fight itself is unchanged: every packet is still applied.
Visuals whose actors are all beyond the draw distance are not drawn either,
since neither body is.

**Per-frame loops.** Three loops that visited every actor node on every frame
in which any actor changed now visit only the actors that frame changed:

- removing nodes of departed actors (REMOVE_ACTOR now marks the ids it removes;
  a bulk clear bumps `AppState.actor_roster_generation`, which still walks the
  table once);
- the overhead target and health-bar answers (`_sync_overhead_health_for`; the
  full `_sync_overhead_health` is kept for callers that need it);
- the selection ring (`_sync_selection` moves it from the old actor to the new).

The live-effect list is compacted when it doubles instead of filtered on every
new effect, the technique-effect limit no longer asks the scene tree for a
whole group per technique, the overhead declutter caches text widths instead of
measuring every name in view with the font ten times a second, and a deferred
actor out of draw range takes no ground ray per step.

## Switches

`RABBITLANDS_CROWD_PRESENTATION` selects the parts in use, for measuring each
against the client without it:

| Value | Meaning |
| --- | --- |
| empty or `all` | every part (the default) |
| `legacy`, `off`, `0` | none: every actor built at spawn, no parking, no effect budget, the old gate |
| `lazy,gate` | only the parts named (`lazy`, `gate`, `effects`, `park`, `stagger`, `quarter`) |
| `-park` | every part but the one named |

`stagger` and `quarter` refine the gate and are off without it.

`RABBITLANDS_CROWD_BODY_CAP` sets the body cap (default 0, off).
`RABBITLANDS_CROWD_TUNING` overrides the full-rate, half-rate and cloth
budgets for a measurement (`full=24,half=8,cloth=4`). The per-frame loop changes are not
switchable: they change no behaviour.

## Benchmark

`tests/integration/crowd_presentation_benchmark.gd` measures the client at the
crowd sizes the server's interest caps will send, in the shapes of the capacity
plan's hot spots. Run it through its launcher, which gives every run its own
user-data directory, alternates variants between repeats and prints a summary:

```sh
python tests/integration/run_crowd_presentation_benchmark.py --godot <Godot.exe> \
    --mode headless --variants all,legacy --cells phase4 --repeats 2 --affinity F
python tests/integration/run_crowd_presentation_benchmark.py --godot <Godot.exe> \
    --mode windowed --renderer forward_plus --variants all --cells s3-market-160
```

Pass the Godot executable itself, not the console wrapper, so the CPU affinity
reaches the process that does the work. Windowed runs use the GPU; on a shared
machine run one at a time.

| Cell | Crowd |
| --- | --- |
| `s3-market-N` | N actors (100, 160, 200, 300), nine in ten equipped players, within 40 tiles of the player, as in a crowded market |
| `s2-invasion-N` | N actors, six in seven creatures within 30 tiles (the creature view radius) and players within 50, as in an invasion |
| `combat-N` | N actors (100, 160), half players and half creatures within 25 tiles, every one of them fighting |
| `aoi-160` | 160 actors spread to the 88-tile edge of the player area of interest, so some are beyond the draw distance |
| `empty` | the map and the player alone, the floor every other cell is built on |

In the first two shapes a third of the actors other than the player are active:
half walk one tile east and back, half fight. Fighters act on a neighbour in
four roles - a spell, a drawn bow and two melee strikes - and every action costs
its target three health, so bars and floating numbers move as they do in play.
`--driver live` (the default) paces this as the game does: 50 ms server ticks,
a step every 600 ms per walker and an action every 2 s per fighter (one combat
round), each actor on its own phase. `--driver stress` is the earlier crowd
study's pace - every walker steps every 100 ms and every fighter acts every
400 ms, all on the same tick - kept for comparison with its numbers; it sends
about six times the steps and five times the combat of live play. `--map` (default `four_gates`) picks the map;
on `landfall` and `twinbrook` the player stands on the S3 market and S2 wave
centres, and `--centre x,y` names any other tile. `--quality low|medium|high`
sets the graphics quality through `ELORIA_LOOK_QUALITY`. `--diagnostics
no_animation,no_overhead,no_ground` freezes every AnimationPlayer, hides the
overhead blocks or skips the ground rays, for attribution only.

The frame rate is capped at 60 (`RABBITLANDS_CROWD_BENCH_FPS_CAP`), as a 60 Hz
display caps it, so the share of frames that carry a packet tick is what it is
in play; an uncapped headless loop thins those frames out and flatters p95. A
frame's *work* is timed from the first physics step of an engine iteration to
`frame_post_draw` (windowed) or, headless, to a deferred call the last node to
process queues after Main's own deferred world sync; the cap's sleep is not
counted. `wallMilliseconds` keeps the frame-to-frame time with the sleep.

Each cell reports `frameTime` (mean, p5, p50, p95, p99, max of the frame work),
`fpsP5` (1000 / p95, the frame rate 95% of frames reach), `tickFrameMilliseconds`
(frames that carried packets), the benchmark Main subclass's component timers,
the frame split into three phases - physics and node processing up to the last
node to process (`processPhaseMilliseconds`: Main, the animation players and
the gate's stepping of the half-rate players, `halfRateStepMilliseconds`), the
deferred flush up to the draw (`flushPhaseMilliseconds`: every skeleton's
update with its modifiers, `skeleton_updated` listeners and skins, and Main's
world sync) and the draw (`drawPhaseMilliseconds`, windowed) - the frame
series in order (`frameSeries`), render CPU and GPU time and draw calls when
windowed, memory before and after
the crowd, how long the crowd took to be fully presented, and a census: bodies
built and deferred, stand-ins, drawn and in-frustum actors, animation tiers,
skeletons processing, live effects and the effect budget's admitted and skipped
counts. Headless memory excludes GPU buffers; windowed runs add video memory.
`RABBITLANDS_CROWD_BENCH_ATTRIBUTION=1` also times every body's combat cue
(`update_pose`) and counts skeleton updates a frame; it adds a call to every
skeleton update, so it is for attribution, not for comparing variants.

Headless numbers are a scene-CPU proxy with no render work. Windowed numbers
include rendering on the machine they ran on. Neither certifies another
machine; compare variants on the same machine and treat differences under
about ten percent as noise on a shared host.

The older [native crowd benchmark](native-crowd-benchmarks.md) remains for its
fixtures; it builds every actor's body before measuring, and its range and LOD
band layouts describe the client before this policy.

## Tests

`tests/test_crowd_presentation.gd` covers the policy switches, the effect
budget, deferred and built arrivals, nearest-first builds, building on
approach, parking and revival, giving a far body up, the body cap, the paused
tier stopping a skeleton and bulk removal.
