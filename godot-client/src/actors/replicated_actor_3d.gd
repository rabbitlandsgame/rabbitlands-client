class_name ReplicatedActor3D
extends CharacterBody3D

const RemotePresentationService = preload("res://src/runtime/remote_presentation.gd")
var _remote_generation := 0
var _remote_enrollment_ready := false
var _remote_pending_transfer := PackedFloat64Array()

const REBOUND_SKIN_POOL := preload("res://src/actors/rebound_skin_pool.gd")
const ACTOR_RENDER_QUALITY := preload("res://src/actors/actor_render_quality.gd")
const OLDCRAFT_ACTOR_STYLE := preload("res://src/actors/oldcraft_actor_style.gd")
const CapeEmblems := preload("res://src/actors/cape_emblems.gd")
const GLB_MESH_EXTRAS := preload("res://src/actors/glb_mesh_extras.gd")
const WARDROBE_SHIRT_FIT := preload("res://src/actors/wardrobe_shirt_fit.gd")
const QUIVER_STRAP_FIT := preload("res://src/actors/quiver_strap_fit.gd")
const WORLD_LABEL_STYLE := preload("res://src/ui/world_label_style.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const ARCHIVED_MODEL_POLICY := preload("res://src/actors/archived_model_policy.gd")
const STATUS_ICONS := preload("res://src/ui/status_effect_icons.gd")
const COMBAT_TARGET_MARKER := preload("res://src/actors/combat_target_marker_3d.gd")
const CREATURE_DISSOLVE := preload("res://src/actors/creature_dissolve.gd")
const CREATURE_DISSOLVE_DELAY_SECONDS := 2.0
const TARGET_MARKER_STYLE := preload("res://src/actors/target_marker_style.gd")
const ServerTimePacing := preload("res://src/actors/server_time_pacing.gd")
var _target_marker_style := TARGET_MARKER_STYLE.defaults()

@export var walk_presentation_speed := 6.0
@export var run_presentation_speed := 9.0
@export var turn_speed_radians := 12.0
## How long the server gives one *tile*, so the very first step of a session
## is paced correctly before any packet cadence has been observed. Every burst
## after that keeps the pace it last measured. Per tile rather than per step,
## because a diagonal step crosses 1.41 tiles and is held for 1.41 times as
## long: one pace covers both step shapes and any burst of them folded together.
@export var initial_server_interval := 0.6
## Running and haste must start at their own pace before any gaps are measured.
@export var initial_run_interval := 0.2
## How many recent per-tile intervals the pace is the median of. A median
## reads through the two shapes packet timing takes on a real link - a step
## held back by the network and the burst that follows it - where the old
## half-weight blend chased both and retimed the next step off each one.
const PACE_WINDOW := 12
## How fast the jitter allowance forgets a late packet, per step. Holds come
## in runs a second or two apart on a wireless link, so the allowance a hold
## earns has to outlive the next one; at 0.98 it halves in about 35 steps.
const JITTER_DECAY := 0.98
## A step later than this is a player who stood still, not a network hold,
## and earns the buffer nothing. Wireless holds run to a couple of hundred
## milliseconds; a pause between two clicks starts at about half a second.
const JITTER_PAUSE_SECONDS := 0.4
## How many steps a gait has to have measured before a gap is judged a pause
## against them, so one odd sample cannot make every real step look late.
const PACE_MINIMUM_REFERENCE := 3
## How many pause-length gaps in a row, agreeing within PACE_CONFIRM_SPREAD of
## each other, it takes to believe the pace itself has slowed.
## Network jitter on a one-second step is under a tenth of it; a player's
## looting pauses rarely line up that closely five times over.
const PACE_CONFIRM_STEPS := 5
const PACE_CONFIRM_SPREAD := 1.15
## How much longer than the observed server cadence one step is scheduled to
## take when nothing is late: the base of the playout buffer. At 1.05 any
## jitter finished the step before the next one arrived and the actor stopped
## and restarted on every tile; 1.25 covers a quarter of a step, which is
## enough for a wired link and not for a wireless one - the jitter allowance
## in `apply_server_state` adds what the link actually shows.
@export var arrival_margin := 1.25
## The most the body is held behind the newest tile to cover late packets, on
## top of the arrival margin. Every step is scheduled no earlier than the
## margin plus the worst lateness recently seen, so a jittery link buys itself
## a longer buffer and a clean one keeps the margin alone. The holds a home
## wireless link showed in a recording all sat under 350 ms.
@export var maximum_buffer_seconds := 0.35
## The most the body speeds up to trim a buffer that has grown past what the
## link needs. Anything faster reads as the lurch this exists to remove.
@export var catch_up_factor := 1.25
@export var minimum_segment_duration := 0.06
## Long enough to hold the longest walking step - a diagonal, 0.6 s a tile
## across 1.41 tiles, plus the arrival margin - so a walk is not driven faster
## than the server sends it.
@export var maximum_segment_duration := 1.1
## Kept walking for this long after a step lands before falling back to idle,
## again so a late packet does not flick the pose to idle and back.
@export var movement_coast_seconds := 0.12
## Crossfade between two clips. Playing them cold snapped the whole skeleton
## into the new pose, which is what a walk/idle flicker looked like.
@export var action_blend_seconds := 0.15
## How long, in seconds of real time, the crossfade into the current action
## takes: what play_action actually gave it, scaled by the playback speed the
## clip runs at, and zero for an explicit cold restart or no preceding pose.
## Anything that changes with the pose, like the held weapon's grip, follows this
## rather than action_blend_seconds, or it arrives after the pose it belongs to.
var action_crossfade_seconds := 0.15

var actor_id := -1
var server_target := Vector3.ZERO
## How many tiles this actor stands on, across by along. The server
## reserves that box around the tile the actor reports and measures reach
## from its edges, so the model is drawn in the middle of the box rather
## than on the anchor tile - they differ by half a tile whenever an extent
## is even. One tile, the overwhelming majority, is unaffected.
var footprint := Vector2i.ONE
## How large this actor is drawn, as a multiple of its model's own size.
## The species' scale from the server profile, times whatever an invasion
## boss or another per-actor effect asks for. One is the model as authored,
## which is every actor unless a packet says otherwise.
var server_scale := 1.0
## The client's own import scale for this model, kept so the two can be
## multiplied rather than one overwriting the other.
var _import_scale := 1.0
## Presentation boost for small creatures, chosen from the imported rest body
## before server effects are applied so bosses retain the species' boost.
var _small_creature_scale := 1.0
var _is_creature := false
const SMALL_CREATURE_MAX_SIZE := 1.0
const SMALL_CREATURE_SCALE := 2.0
const SMALL_CREATURE_MIN_SIZE := 0.7
## The ground marker, kept rather than looked up: it is counter-rotated
## every physics frame and a node path lookup per frame per actor is
## not what that should cost.
var _selection_ring: MeshInstance3D = null
var _selected := false
var _combat_target := false
var _combat_target_marker: Node3D
var _default_melee_clips: Dictionary = {}
## The marker as built, before the ground was laid under it. Draping reads
## this every time, so a marker walked over a hill and back is shaped by the
## ground it is on rather than by the ground it has crossed.
var _selection_ring_flat: ArrayMesh = null
## Where the marker was last draped, so walking re-drapes it and standing
## still does not.
var _selection_ring_draped_at := Vector3(NAN, NAN, NAN)
## Metres per tile on the map this actor is on, so the marker can be
## the size of the ground the server reserved rather than a guess.
var _metres_per_tile := 1.0
var resolver: AnimationResolver
var animation_player: AnimationPlayer
var _boss_rank := 0
var _boss_rank_label: Label3D
var combat_presentation: CombatPresentation3D
var _in_combat := false
var _ranged_aiming := false
var _last_command_sequence := -1
var _swing_index := 0
var _trail_weapon_mesh: MeshInstance3D
var _trail_weapon_tip := Vector3.ZERO
var current_action: StringName = &"idle"
var _death_elapsed := 0.0
var _death_finished := false
var _death_animation_seconds := 0.0
var _corpse_temporary := false
var _corpse_hold_seconds := 3.0
var _corpse_fade_seconds := 4.0
var _death_snapshot_msec := -1
var _corpse_transparency := -1.0
var _corpse_geometry: Array[GeometryInstance3D] = []
var _corpse_dissolve: RefCounted
var _cinematic_active := false
var _charge_leap: RefCounted
var _cinematic_position := Vector3.ZERO
var _cinematic_yaw := 0.0
var _cinematic_action: StringName = &"idle"
var _cinematic_speed := 0.0
var _snap_pending := true
var _target_yaw := 0.0
var _presentation_speed := 6.0
var _segment_start := Vector3.ZERO
var _segment_elapsed := 0.0
var _segment_duration := 0.0
var _last_movement_update_msec := -1
## Seconds the server spends on one tile, measured over whatever ground the
## last update actually covered rather than assumed to be one step's worth.
var _smoothed_server_interval := 0.6
## The per-tile intervals the pace is the median of, one history per gait (see
## `pace_gait`), each at most PACE_WINDOW long.
var _pace_histories := {}
## Gaps that read as pauses, in a row and all from one gait. Enough of them
## that agree are a pace that has really slowed; see `confirms_new_pace`.
var _unconfirmed_paces := PackedFloat32Array()
var _unconfirmed_gait := -1
## The gait of the step before this one, whose hold the gap before this
## packet is - the same off-by-one as `_previous_step_tiles`.
var _previous_step_gait := 0
## Seconds the body is held behind the newest tile, beyond the arrival
## margin, to cover the late packets this link has been showing.
var _jitter_allowance := 0.0
## When the step now being crossed is scheduled to finish, on the local clock
## in seconds, or -1 with no schedule. The next step continues from here at
## the same speed rather than restarting from wherever the body is, which is
## what made an early packet a lurch and a late one a stop.
var _schedule_due := -1.0
## How many tiles the step before this one crossed. The server holds a step
## for its own length *after* taking it - the gap before this packet is the
## previous step's, not this one's - so that is the length the gap is measured
## against. Dividing by the arriving step's length instead read a straight
## step after a diagonal one as 41% late and the reverse as early, on every
## path that zigzags between the two.
var _previous_step_tiles := 1.0
## The direction the body is actually crossing the ground in, which is not the
## tile direction the server named. See `_rendered_target_yaw`.
var _travel_yaw_active := false
var _travel_yaw := 0.0
## The body faces the direction of the step it is crossing on, taken fresh each
## step so a change of direction turns it at once. A straight click-path that is
## not one of the eight tile directions is walked as a zigzag of orthogonal and
## diagonal steps, so this can swing a little to either side of that line - the
## cost of committing to each step rather than averaging a window of them, which
## lagged every turn. The turn the body actually renders is rate-limited in
## `_physics_process`, which takes most of that swing back out.
## Whether the server says this actor is under the double-speed buff. The
## server paces a hastened actor at half the move interval but still names the
## ordinary walk commands, so the buff is the only thing that says an actor is
## covering ground fast enough to be running.
var _hastened := false
## Part 2 in the equipment registry: the cape, and the only part with cloth.
const CAPE_PART := 2
const QUIVER_PART := 8
## Part 5: the torso. The cape is draped over whatever is worn there, so the
## two parts are not independent the way every other pair is.
const BODY_PART := 5
## Parts 4 and 6, the legs and the boots: the cape's hem is kept off the shins
## they cover.
const LEGS_PART := 4
const BOOTS_PART := 6
## How many cut capes are kept before the cache is dropped and rebuilt.
const DRAPE_CACHE_LIMIT := 48
## The shade an undershirt takes while torso armour is worn over it.
##
## A generated cuirass is an open design of straps and plates, so the shirt
## underneath shows through it wherever the design is open.  Lit in its own
## colour that reads as the character wearing their clothes over the armour;
## darkened it reads as the padding a cuirass is buckled over, which is what
## the piece is drawn to sit on.  This is the value the shipped underlayer used
## before that layer was dropped -- the armour is better off covered by the
## body's own shirt than by a mesh of its own that wins the depth test against
## every plate seated within 8 mm of the skin.
##
## Races whose wardrobe is a MESH get this.  The rest paint their clothing into
## the body texture and have no shirt to recolour: see `_refresh_wardrobe_cover`.
const COVERED_SHIRT := Color8(56, 47, 40)

## The wardrobe surfaces torso armour is worn over.  Pants and boots are not
## here: their own slots cover them, and a cuirass has no business darkening a
## character's legs.
const SHIRT_SURFACES := ["wardrobe_shirt", "wardrobe_shirt_trim"]

## Race features ride on mesh nodes of their own, appended to the race body:
## `race_feature_head` (Votary horns, Stoneborn crown, Glasswarden crystals)
## and `race_feature_shoulders` (Mycelari growths). Being separate nodes they
## keep their imported horn, stone or glass material - the appearance pass has
## no branch for them, so the skin dye never reaches them - and equipment can
## switch them off the way it switches off hair.
const RACE_FEATURE_PREFIX := "race_feature_"
const RACE_FEATURE_HEAD := "race_feature_head"
const RACE_FEATURE_SHOULDERS := "race_feature_shoulders"

## Clearance for wardrobe assets that still need a material offset. Fitted
## shirts bake a continuous offset across UV/facet seams; growing those again
## would pull adjacent faces apart. Their model lists them in wardrobeBakedGrow.
const WARDROBE_GROW := {
	"wardrobe_shirt": 0.011, "wardrobe_shirt_trim": 0.013,
	"wardrobe_pants": 0.009, "wardrobe_pants_seam": 0.016,
	"wardrobe_boots": 0.014, "wardrobe_boots_seam": 0.017,
	"wardrobe_head_band": 0.006, "wardrobe_head_cap": 0.009,
}

## The one facing an actor renders that the server did not state: the single
## 45 degree step shown while the answer to TURN_LEFT/TURN_RIGHT is in flight.
var _predicted_turn_pending := false
var _predicted_turn_yaw := 0.0
var _movement_coast_remaining := 0.0
var _native_skeleton: Skeleton3D
## The imported visual root and the yaw the import gave it. Several library clips
## are authored with the body turned off the rig's forward: the locomotion ones
## carry the whole pelvis about 23 degrees round, so a walk or a run faces that
## far off the way it travels though the node points exactly right. The action
## map states a per-action yaw that cancels it, applied on top of the base import
## yaw here and eased in over the animation crossfade so starting or stopping a
## walk does not snap the body. Poses meant to face off - a bladed combat idle, a
## sword lunge - declare nothing and are left as authored.
var _native_model: Node3D
var _mount_visual: Node3D
var mount_state: Dictionary = {}
## Reuse Main's cached traversal ray normal. Only presentation tilts: the
## actor, picking capsule, labels and camera anchor retain their upright frame.
const SURFACE_MAX_TILT := PI / 4.0
const SURFACE_TURN_SPEED := PI
const SURFACE_FOOT_WEIGHT := 0.35
var _surface_up := Vector3.UP
var _surface_target_up := Vector3.UP
var _surface_applied_up := Vector3(NAN, NAN, NAN)
var _surface_applied_yaw := NAN
var _surface_native_rest := Transform3D.IDENTITY
var _surface_native_tilted := false
## Authored body bounds, cached before equipment or animation can move them.
var _native_body_bounds := AABB()
var _base_model_yaw := 0.0
var _facing_offset := 0.0
var _facing_offset_from := 0.0
var _facing_offset_to := 0.0
var _facing_offset_elapsed := 0.0
var _cape_cloth: SkeletonModifier3D = null
var _weapon_carry: SkeletonModifier3D = null
var _attachment_bones: Dictionary = {}
var _model_config: Dictionary = {}
var _appearance: Dictionary = {}
var _face_material: ShaderMaterial
var _face_group_materials: Dictionary = {}
var _skin_materials: Dictionary = {}
var _skin_choice := 0
var _equipment_config: Dictionary = {}
var _equipment_visuals: Dictionary = {}
var _equipment_nodes: Dictionary = {}
## Whether the main-hand model uses the separate two-hand bow presentation.
## Resolving a fitted equipment variant can clone a nested model dictionary, so
## retain this one boolean until the weapon, registry or wearer rig changes.
var _hand_prop_ranged_cache_valid := false
var _hand_prop_weapon_has_ranged_animation := false
## Whether this actor has been dressed once. Until it has, every wardrobe
## request is applied in full, however little it appears to change.
var _equipment_applied: bool = false
var _equipment_hides: Dictionary = {}
var _hidden_body_surfaces: Dictionary = {}
var _nameplate: Label3D
var _guild_nameplate: Label3D
var _name_dto: Dictionary = {}
var _overhead_crowded := false
var _status_effects: Array[String] = []
var _status_icons: Node3D
var _title_line: Label3D
## The occupation line under an NPC's name, and the occupation it shows
## without its brackets. Built on first use, like the title line.
var _occupation_line: Label3D
var _occupation := ""
var _quest_marker: Label3D
var _quest_marker_tween: Tween
var _speech_bubble: Label3D
var _speech_bubble_expiry_msec := 0
var _speech_color := Color.WHITE
var _health_bar_background: MeshInstance3D
var _overhead_background: MeshInstance3D
var _health_bar_fill: MeshInstance3D
var _health_label: Label3D
var _health_current := -1
var _health_maximum := -1
var _overhead_visible := true
var _banner_names := true
var _banner_health_bar := true
var _banner_health_numbers := true
var _banner_status_icons := true
var _banner_background := true
## How much of the name, title and health bar shows, from 0 to 1. The block is
## drawn at a fixed screen size, so distance alone never made a far name any
## less legible than a near one; main.gd fades it out past the player's name
## distance instead. See `set_overhead_fade`.
var _overhead_fade := 1.0
## Whether this actor's health is drawn over its head. main.gd's
## `_overhead_health_for` is what decides it.
var _health_shown := false
## Whether this actor is close enough to be drawn at all, and what was visible
## when it stopped being so - restored exactly, so coming back into range does
## not light up a selection ring nobody selected or a bar that was switched off.
var _drawn := true
var _hidden_by_range: Array[Node3D] = []
var _settled := false
var _silhouette: OccludedSilhouette
## Which of the animation gate's tiers this actor is in, and whether a cape
## is worn: the cloth solver runs off the skeleton on its own clock, so a
## paused body has to put it to sleep too and wake it with the body.
var _animation_tier: int = AnimationGate.Tier.FULL
var _animation_gate_owner: AnimationGate
var _cape_cloth_worn := false
var _cape_cloth_allowed := true
## The resolved graphics quality and whether this is the player's own actor.
## Main supplies both after configure; keeping them here makes appearance and
## equipment created later inherit the same policy without rebuilding either
## resource cache.
var _render_quality: int = ACTOR_RENDER_QUALITY.QUALITY_DEFAULT
var _render_quality_local_actor := false
## Configured without its body: identity, picking, the overhead block, the map
## dot and every protocol state are here, but no model, skeleton, animation or
## equipment. Main builds a full actor in this one's place once it comes near
## enough to be drawn (`Main._update_model_builds`), so an actor the server
## sends from across the map costs a handful of nodes until then. A crowd at the
## edge of view is still drawn meanwhile: `_stand_in` is a plain shape where the
## body will be, shown only inside the draw distance.
var _model_deferred := false
var _stand_in: MeshInstance3D
## Past the client's optional body cap: only the map dot is left - no stand-in,
## overhead block or picking - which is what the server's own cap does to an
## actor it no longer sends.
var _crowd_hidden := false
static var _stand_in_mesh: CapsuleMesh
static var _stand_in_material: StandardMaterial3D

# Visual layer 2. The gameplay camera renders layers 1 and 2; the full-map
# camera renders layers 1 and 3, and the minimap camera renders layer 1 alone.
const GAMEPLAY_ONLY_VISUAL_LAYER := 2
## Layer 3, which only the full-map camera renders. An actor's own body is a
## third of a pixel on a map that frames 1600 metres, so everyone standing on
## it needs a dot sized for the map rather than for the world. The minimap
## draws its own marks in pixels over its render, so that they hold their size
## through a zoom; see `minimap_marker_overlay.gd`.
const MAP_MARKER_LAYER := 4
const MAP_DOT_RADIUS := 6.0
## The light blue the full map's legend calls Player / NPC, written the way it
## writes it so a reader comparing the swatch to the map is comparing one
## colour to itself rather than to a rounding of it.
const MAP_DOT_COLOUR := Color("9fd2ff")
## An invasion creature's dot, and an ordinary creature's. Both are read off
## the map at a glance while something is coming for the player, so they are
## the two colours a map already means danger with: an invasion is the red one
## and the wildlife is the yellow one. Written the way the legend writes them,
## for the same reason MAP_DOT_COLOUR is.
const INVASION_MAP_DOT_COLOUR := Color("fa5a5a")
const CREATURE_MAP_DOT_COLOUR := Color("fcec38")
const CREATURE_NAME_COLOUR := Color("ffff00")
## The actor kind the server gives every creature - EL's
## PKABLE_COMPUTER_CONTROLLED. Players are HUMAN and scenery NPCs are NPC, so
## this is what separates the two creature dots from everybody else's.
const CREATURE_ACTOR_KIND := 5
## EL red3, the colour the server prefixes an invasion creature's name with.
## Nothing else on the wire says "invasion": the name's colour is how the
## legacy client knew to draw the banner red, and it is how this knows to draw
## the dot red. A summoned creature carries EL blue1 instead and is neither an
## invasion nor wildlife, so it keeps the ordinary actor dot.
const INVASION_NAME_COLOUR := 14
## EL blue1, the colour the server prefixes a summoned creature's name with.
## Like the invasion red above, the name's colour is the only thing on the
## wire that says what this creature is, and it is what tells a click on a
## summon apart from a click on wildlife.
const SUMMON_NAME_COLOUR := 4
const SETTLED_YAW_EPSILON := 0.0005

## Fallback height when no native body could be loaded. Native actors anchor
## the block above their imported body bounds, including both model scales.
const NAMEPLATE_HEIGHT := 2.15
const NAMEPLATE_CLEARANCE := 0.6

## The player's own name and health are a 2D panel projected over their head
## (`_update_actor_resource_overlay` in main.gd), so they are the same size to
## read wherever the player stands and however far the camera is pulled back.
## Everybody else's were a Label3D and a pair of quads, which shrank with
## distance and with every notch of the zoom until a name across the field was
## a smudge. A name is text, not scenery. So the block is drawn at a fixed
## screen size, in the same pixels - and at the same sizes - as the banner it
## is now a copy of: 12 for the name and 11 for the numbers, beside a 56 by 7
## bar. The reference uses plain letters over a translucent black backing.
##
## `fixed_size` is what holds the size: it scales a billboard by its own view
## depth, which cancels the perspective divide, so a local unit covers
## `render_height / (2 * tan(fov / 2))` device pixels at any depth at all. A
## pixel of the 2D layer covers `render_height / 720` of them - the content
## scale the layer is drawn through, from the design height in project.godot.
## The render height cancels between the two, which is why one number serves
## every window size: `2 * tan(25 degrees) / 720`, the camera's field being 50
## degrees. `rendered_overhead_banners.gd` recomputes it from the camera and
## from the banner rather than taking it on trust.
const OVERHEAD_PIXEL := 0.0012953
const NAMEPLATE_FONT_SIZE := 12
const HEALTH_NUMBER_FONT_SIZE := 11
const SPEECH_BUBBLE_FONT_SIZE := 15
const OVERHEAD_OUTLINE_SIZE := 4

# The rest of the block, in those same pixels, measured downwards from the
# name so the name, the bar and the numbers read as one thing. The bar is the
# banner's health bar; the drops are its rows, a line apart.
const HEALTH_BAR_WIDTH := 56.0
const HEALTH_BAR_THICKNESS := 7.0
const HEALTH_BAR_BORDER := 2.0
const HEALTH_BAR_BACKING := Color(0.05, 0.04, 0.03, 0.78)
const HEALTH_BAR_DROP := 16.0
const HEALTH_LABEL_DROP := HEALTH_BAR_DROP
const HEALTH_NUMBER_GAP := 5.0
const OVERHEAD_BACKING := Color(0.0, 0.0, 0.0, 0.45)
const NEGATIVE_STATUS_SIZE := 20.0
const NEGATIVE_STATUS_GAP := 3.0
const NEGATIVE_STATUS_RISE := 24.0
const STATUS_TEXTURES := STATUS_ICONS.TEXTURES
static var _health_gradient: GradientTexture2D
static var _wardrobe_texture_cache: Dictionary = {}

static func clear_wardrobe_texture_cache() -> void:
	_wardrobe_texture_cache.clear()
	NecklineSkin.clear()
## The speech bubble sits above the name instead, and wraps well short of the
## screen it is now measured against.
const SPEECH_BUBBLE_RISE := 28.0
const SPEECH_BUBBLE_WIDTH := 270.0
const SPEECH_BUBBLE_TEXT := Color(0.96, 0.91, 0.78, 1.0)
const SPEECH_BUBBLE_SURROUND := Color(0.035, 0.026, 0.018, 0.94)
## The worn title, a line above the name in the same pixels as the rest of the
## block. Above rather than below because below is where the health bar and
## its numbers already are, and smaller than the name because a title is what
## somebody calls themselves, not what they are called.
const TITLE_RISE := 12.0
const TITLE_FONT_SIZE := 10
## What an NPC does, a line under the name the way other MMORPGs draw
## "<Innkeeper>": smaller than the name and in a muted colour, so the name is
## still what reads first. Below rather than above because above is the worn
## title's place. A health bar, when this actor wears one, moves down a line
## to make room, so the name, the occupation and the bar never overlap.
const OCCUPATION_DROP := 12.0
const OCCUPATION_FONT_SIZE := 10
const OCCUPATION_COLOUR := Color(0.78, 0.76, 0.68, 1.0)

## Click target and selection ring for an actor standing on one tile.
## Both are scaled by the widest side of the footprint: a giant that can
## only be clicked on the middle tile of the nine it stands on is a giant
## players will keep missing, and a ring drawn around that one tile says
## the wrong thing about what is standing there.
const SELECTION_RADIUS := 0.45
## Width of the selection outline's border, in metres.
const RING_THICKNESS := 0.09
## How far a single-tile outline is inset from its tile's edges, so a
## rabbit's marker does not read as a solid square of floor.
const RING_INSET := 0.06
## How far the actor has to move before its marker is laid over the ground
## again. A step is a metre, so this re-drapes about twenty times across one,
## which is finer than the ground itself is authored.
const RING_REDRAPE_METRES := 0.05
## The longest piece of one side of the outline. The marker is draped over the
## ground it describes, and a piece has to be no longer than the ground stays
## straight for; the terrain heightfields are authored in half-metre cells.
const RING_SEGMENT_METRES := 0.5

func configure(dto: Dictionary, adapter: CoordinateAdapter,
		model_config: Dictionary, animation_config: Dictionary,
		equipment_config: Dictionary = {}, build_model := true) -> Array[String]:
	var remote = RemotePresentationService.current()
	if remote != null: remote.detach(self, "reconfigured")
	_remote_enrollment_ready = false
	actor_id = int(dto.actor_id)
	_is_creature = int(dto.get("kind", 0)) == CREATURE_ACTOR_KIND
	_small_creature_scale = 1.0
	_metres_per_tile = maxf(0.01, adapter.metres_per_tile)
	footprint = dto.get("footprint", Vector2i.ONE) as Vector2i
	server_scale = maxf(0.01, float(dto.get("scale", 1.0)))
	server_target = adapter.footprint_center(
		int(dto.x), int(dto.y), footprint)
	position = server_target
	_segment_start = position
	_smoothed_server_interval = initial_server_interval
	rotation.y = adapter.rotation_to_godot(int(dto.rotation))
	_target_yaw = rotation.y
	collision_layer = 2
	collision_mask = 0
	var selection_shape: CollisionShape3D = CollisionShape3D.new()
	selection_shape.name = "SelectionCollision"
	var capsule_shape: CapsuleShape3D = CapsuleShape3D.new()
	capsule_shape.radius = SELECTION_RADIUS
	capsule_shape.height = 1.9
	selection_shape.shape = capsule_shape
	selection_shape.position.y = 0.95
	add_child(selection_shape)
	var selection_ring: MeshInstance3D = MeshInstance3D.new()
	selection_ring.name = "SelectionRing"
	var ring_material: StandardMaterial3D = StandardMaterial3D.new()
	ring_material.vertex_color_use_as_albedo = true
	ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	# Both faces: this is a flat decal on the ground and the winding
	# it is built with should not decide whether it can be seen.
	ring_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	selection_ring.material_override = ring_material
	selection_ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	selection_ring.position.y = GroundDrape.CLEARANCE
	selection_ring.visible = false
	# Gameplay-only visual layer. The minimap and full-map cameras cull it, so
	# neither top-down viewport pays for selection rings or nameplates it never
	# shows at their scale.
	selection_ring.layers = GAMEPLAY_ONLY_VISUAL_LAYER
	add_child(selection_ring)
	_selection_ring = selection_ring
	_resize_selection()
	_add_nameplate(dto)
	_add_map_dot(dto)
	resolver = AnimationResolver.new(animation_config)
	for action: String in ["attack_primary", "attack_secondary"]:
		if resolver.action_to_clip.has(action):
			_default_melee_clips[action] = resolver.action_to_clip[action]
	_model_config = model_config.duplicate(true)
	_face_material = null
	_face_group_materials.clear()
	_skin_materials.clear()
	_attachment_bones = (model_config.get("attachments", {}) as Dictionary).duplicate(true)
	_equipment_config = preload(
		"res://src/actors/equipment_registry_snapshot_cache.gd").acquire(equipment_config)
	_invalidate_hand_prop_ranged_cache()
	if ARCHIVED_MODEL_POLICY.is_retired_actor_type(int(dto.get("actor_type", -1))) or bool(model_config.get("retired", false)):
		# Keep identity, picking, nameplate and protocol state without drawing
		# either the archived model or a replacement placeholder body.
		set_meta("retired_model", true)
		return []
	if not build_model:
		_model_deferred = true
		_add_stand_in()
		return []
	var source_path := _external_path(str(model_config.get("scene", "")))
	var errors := _load_native_scene(source_path)
	if not errors.is_empty():
		_add_fallback_visual(dto)
		# The native model never loaded, so the import adapter below will not
		# run and the scale would never be applied. A stand-in for a giant
		# should still be giant, and its nameplate still above it.
		_apply_model_scale()
	if errors.is_empty():
		_apply_import_adapter(model_config.get("import", {}))
		var visual_error: String = _validate_native_visual()
		if not visual_error.is_empty():
			errors.append(visual_error)
			_add_fallback_visual(dto)
		var skeleton: Skeleton3D = null
		for node in find_children("*", "Skeleton3D", true, false):
			skeleton = node as Skeleton3D
			break
		if skeleton == null:
			errors.append("Skeleton3D missing")
		else:
			_native_skeleton = skeleton
			if model_config.has("culture"):
				_weapon_carry = (load("res://src/actors/weapon_carry_pose.gd") as Script).new()
				_weapon_carry.name = "WeaponCarryPose"
				_weapon_carry.set("actor", self)
				_weapon_carry.active = false
				skeleton.add_child(_weapon_carry)
			_attach_cape_cloth(skeleton)
			apply_appearance_variants(dto.get("appearance", {}) as Dictionary)
			var animation_path := _external_path(str(model_config.get("animationLibrary", "")))
			var wanted_clips := resolver.required_clips()
			# Player techniques use the same immutable imported rig/library cache.
			if resolver.action_to_clip.has("cast_channel"):
				for technique_clip: String in preload("res://src/actors/technique_animation_library.gd").RECIPES:
					wanted_clips.append(technique_clip)
			if model_config.has("culture") and not wanted_clips.has("Rest_Pose"):
				wanted_clips.append("Rest_Pose")
			var imported := NativeAnimationImporter.import_library(self,
					animation_path, skeleton, model_config.get("boneAliases", {}),
					wanted_clips, resolver.looping_clips)
			animation_player = imported.player
			errors.append_array(Array(imported.errors))
			if animation_player != null:
				if not animation_player.animation_finished.is_connected(
						_on_animation_finished):
					animation_player.animation_finished.connect(_on_animation_finished)
				errors.append_array(resolver.validate(imported.clips))
				play_action(&"idle")
				if resolver.action_to_clip.has("cast_channel"):
					combat_presentation = CombatPresentation3D.new()
					add_child(combat_presentation)
					combat_presentation.configure(self)
	apply_equipment_visuals(dto.get("equipment_visuals", {}) as Dictionary,
		dto.get("equipment_fallback_parts", []) as Array)
	return errors

func apply_appearance_variants(appearance: Dictionary) -> void:
	_appearance = appearance.duplicate()
	if _native_skeleton == null:
		return
	var culture: String = str(_model_config.get("culture", "luminous"))
	_skin_choice = int(appearance.get("skin", 0))
	var skin_tint: Color = AppearanceVariants.skin_tint(int(appearance.get("skin", 0)))
	var hair_tint: Color = AppearanceVariants.hair_color(int(appearance.get("hair", 0)))
	var eye_tint: Color = AppearanceVariants.eye_color(int(appearance.get("eyes", 0)))
	var head_style: int = AppearanceVariants.head_style(int(appearance.get("head", 0)))
	var native_model: Node3D = get_node_or_null("NativeModel") as Node3D
	if native_model == null:
		return
	for node_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		var mesh_name: String = mesh_node.name.to_lower()
		if mesh_name.begins_with(RACE_FEATURE_PREFIX):
			# Horn, stone, glass and growth are not skin: a race feature keeps
			# its imported material under every skin, hair and eye choice. Keep
			# this guard ahead of any generic branch added below.
			continue
		if mesh_name == "eyes":
			_tint_mesh(mesh_node, eye_tint, true)
		elif mesh_name == "eyebrows":
			_tint_mesh(mesh_node, hair_tint)
		elif mesh_name == "body":
			_apply_skin_materials(mesh_node, skin_tint)
		elif mesh_name == "hair":
			_tint_mesh(mesh_node, hair_tint)
		elif mesh_name == "scalp":
			_apply_skin_materials(mesh_node, skin_tint)
		elif mesh_name in SHIRT_SURFACES:
			# Kept on the node so equipping and unequipping a cuirass can put
			# the character's own colour back without the appearance dictionary.
			var shirt_color: Color = AppearanceVariants.wardrobe_color(
				culture, AppearanceVariants.PART_SHIRT,
				int(appearance.get("shirt", 0)))
			if mesh_name == "wardrobe_shirt_trim":
				shirt_color = shirt_color.lightened(0.18)
			mesh_node.set_meta("wardrobe_color", shirt_color)
			_set_mesh_color(mesh_node, shirt_color)
		elif mesh_name == "wardrobe_pants":
			_set_mesh_color(mesh_node, AppearanceVariants.wardrobe_color(
				culture, AppearanceVariants.PART_PANTS, int(appearance.get("pants", 0))))
		elif mesh_name == "wardrobe_boots":
			_set_mesh_color(mesh_node, AppearanceVariants.wardrobe_color(
				culture, AppearanceVariants.PART_BOOTS, int(appearance.get("boots", 0))))
		elif mesh_name == "wardrobe_head_band":
			_set_appearance_visible(mesh_node, head_style == 1 or head_style == 3)
			_set_mesh_color(mesh_node, AppearanceVariants.wardrobe_color(
				culture, AppearanceVariants.PART_HEAD, int(appearance.get("head", 0))))
		elif mesh_name == "wardrobe_head_cap":
			_set_appearance_visible(mesh_node, head_style == 2 or head_style == 3)
			_set_mesh_color(mesh_node, AppearanceVariants.wardrobe_color(
				culture, AppearanceVariants.PART_HEAD, int(appearance.get("head", 0))))
		if WARDROBE_GROW.has(mesh_name):
			var baked: Array = _model_config.get("wardrobeBakedGrow", []) as Array
			if not baked.has(mesh_name):
				_grow_mesh(mesh_node, float(WARDROBE_GROW[mesh_name]))
	_apply_face_appearance(native_model, skin_tint, eye_tint, hair_tint)
	_add_hair_variant(AppearanceVariants.hair_style(
		int(appearance.get("hair", 0))), hair_tint)
	_refresh_body_surface_visibility()
	_refresh_wardrobe_cover()
	_apply_render_quality_to_visuals()
	OLDCRAFT_ACTOR_STYLE.apply_surface_finish(native_model)
	for nodes: Array in _equipment_nodes.values():
		for node: Node in nodes:
			if node is MeshInstance3D and node.has_meta("neck_source"):
				NecklineSkin.refresh_materials(node as MeshInstance3D)

func _set_appearance_visible(mesh_node: MeshInstance3D, visible_by_style: bool) -> void:
	# Appearance owns whether a wardrobe surface exists at all; equipment only
	# covers one that does. Recording the appearance choice keeps unequipping a
	# helmet from revealing a headband the character never chose.
	if visible_by_style:
		if mesh_node.has_meta("appearance_hidden"):
			mesh_node.remove_meta("appearance_hidden")
	else:
		mesh_node.set_meta("appearance_hidden", true)
	mesh_node.visible = visible_by_style

func _apply_face_appearance(native_model: Node3D, skin: Color, eyes: Color, hair: Color) -> void:
	var spec: Dictionary = _model_config.get("faceAppearance", {}) as Dictionary
	if spec.is_empty():
		return
	if spec.has("groups"):
		_apply_grouped_face_appearance(native_model, spec, skin, eyes, hair)
		return
	var body := native_model.find_child("body", true, false) as MeshInstance3D
	if body == null or body.mesh == null:
		return
	var surface := int(spec["sourceSurface"])
	var original := body.mesh.surface_get_material(surface) as StandardMaterial3D
	if original == null:
		return
	if _face_material == null:
		_face_material = ShaderMaterial.new()
		_face_material.shader = preload("res://src/actors/face_appearance.gdshader")
		_face_material.set_shader_parameter("base_texture", original.albedo_texture)
		_face_material.set_shader_parameter("region_texture", load(str(spec["mask"])))
		_face_material.set_shader_parameter("base_color", original.albedo_color)
		_face_material.set_shader_parameter("roughness", original.roughness)
		_face_material.set_shader_parameter("use_normal", original.normal_enabled)
		_face_material.set_shader_parameter("normal_texture", original.normal_texture)
		_face_material.set_shader_parameter("normal_scale", original.normal_scale)
	_face_material.set_shader_parameter("skin_tint", skin)
	_configure_skin_color(_face_material, "body", surface)
	_face_material.set_shader_parameter("eye_tint", eyes)
	_face_material.set_shader_parameter("hair_tint", hair)
	body.set_surface_override_material(surface, _face_material)
	if spec.has("neckTexture"):
		var neck := body.get_surface_override_material(int(spec["neckSurface"])) as StandardMaterial3D
		if neck != null:
			neck.albedo_texture = load(str(spec["neckTexture"])) as Texture2D
	# The old partitions contain eyelid/ear/brow skin as well as eye pixels.
	# Restore their original atlas and use the same UV mask on every partition.
	for mesh_name: String in ["eyes", "eyebrows", "scalp"]:
		var mesh := native_model.find_child(mesh_name, true, false) as MeshInstance3D
		if mesh != null:
			mesh.material_override = _face_material

func _apply_grouped_face_appearance(native_model: Node3D, spec: Dictionary,
		skin: Color, eyes: Color, hair: Color) -> void:
	var groups: Dictionary = spec["groups"]
	for part: String in groups:
		var mesh := native_model.find_child(part, true, false) as MeshInstance3D
		if mesh == null or mesh.mesh == null:
			continue
		var original := mesh.mesh.surface_get_material(0) as StandardMaterial3D
		if original == null:
			continue
		var face := _face_group_materials.get(part) as ShaderMaterial
		if face == null:
			face = ShaderMaterial.new()
			face.shader = preload("res://src/actors/face_appearance.gdshader")
			face.set_shader_parameter("base_texture", original.albedo_texture)
			face.set_shader_parameter("region_texture", load(str(spec["mask"])))
			face.set_shader_parameter("base_color", original.albedo_color)
			face.set_shader_parameter("roughness", original.roughness)
			face.set_shader_parameter("use_normal", original.normal_enabled)
			face.set_shader_parameter("normal_texture", original.normal_texture)
			face.set_shader_parameter("normal_scale", original.normal_scale)
			var crop: Dictionary = groups[part]
			var scale: Array = crop["uvScale"]
			var offset: Array = crop["uvOffset"]
			face.set_shader_parameter("mask_uv_scale", Vector2(float(scale[0]), float(scale[1])))
			face.set_shader_parameter("mask_uv_offset", Vector2(float(offset[0]), float(offset[1])))
			_face_group_materials[part] = face
		face.set_shader_parameter("skin_tint", skin)
		_configure_skin_color(face, part, 0)
		face.set_shader_parameter("eye_tint", eyes)
		face.set_shader_parameter("hair_tint", hair)
		mesh.material_override = face
		if part == "body":
			_face_material = face

func _configure_skin_color(material: ShaderMaterial, part: String, surface: int) -> void:
	var palette: Dictionary = _model_config.get("skinPalette", {})
	var refs: Array = palette.get("references", {}).get(part, [])
	var calibrated := surface < refs.size()
	material.set_shader_parameter("recolor_skin", calibrated and _skin_choice != 0)
	material.set_shader_parameter("skin_color", AppearanceVariants.skin_color(_skin_choice))
	if calibrated:
		var rgb: Array = refs[surface]
		material.set_shader_parameter("skin_reference", Color(float(rgb[0]), float(rgb[1]), float(rgb[2])))

func _apply_skin_materials(mesh: MeshInstance3D, tint: Color) -> void:
	if not _model_config.has("skinPalette"):
		_tint_mesh(mesh, tint)
		return
	mesh.material_override = null
	for surface in range(mesh.mesh.get_surface_count()):
		var key := str(mesh.name) + ":" + str(surface)
		var material := _skin_materials.get(key) as ShaderMaterial
		if material == null:
			var original := mesh.mesh.surface_get_material(surface) as StandardMaterial3D
			if original == null:
				continue
			material = ShaderMaterial.new()
			material.shader = preload("res://src/actors/face_appearance.gdshader")
			material.set_shader_parameter("base_texture", original.albedo_texture)
			material.set_shader_parameter("base_color", original.albedo_color)
			material.set_shader_parameter("roughness", original.roughness)
			material.set_shader_parameter("use_normal", original.normal_enabled)
			material.set_shader_parameter("normal_texture", original.normal_texture)
			material.set_shader_parameter("normal_scale", original.normal_scale)
			material.set_shader_parameter("use_regions", false)
			_skin_materials[key] = material
		material.set_shader_parameter("skin_tint", tint)
		_configure_skin_color(material, str(mesh.name), surface)
		mesh.set_surface_override_material(surface, material)

func _tint_mesh(mesh_node: MeshInstance3D, tint: Color,
		emissive: bool = false) -> void:
	if mesh_node.mesh == null or mesh_node.mesh.get_surface_count() == 0:
		return
	# A shared trunk and an original race head keep distinct source materials.
	# A node-wide override would repaint every primitive with the first atlas.
	if mesh_node.mesh.get_surface_count() > 1:
		for surface in range(mesh_node.mesh.get_surface_count()):
			var original := mesh_node.mesh.surface_get_material(surface) as StandardMaterial3D
			if original == null:
				continue
			var tinted := original.duplicate() as StandardMaterial3D
			tinted.albedo_color = original.albedo_color * tint
			var colours: Variant = mesh_node.mesh.surface_get_arrays(surface)[Mesh.ARRAY_COLOR]
			tinted.vertex_color_use_as_albedo = colours is PackedColorArray and not colours.is_empty()
			if emissive:
				tinted.emission_enabled = true
				tinted.emission = tint * 0.28
			mesh_node.set_surface_override_material(surface, tinted)
		return
	var source: Material = mesh_node.mesh.surface_get_material(0)
	if source is not StandardMaterial3D:
		return
	var material: StandardMaterial3D = (source as StandardMaterial3D).duplicate()
	material.albedo_color = (source as StandardMaterial3D).albedo_color * tint
	if emissive:
		material.emission_enabled = true
		material.emission = tint * 0.28
	mesh_node.material_override = material

func _set_mesh_color(mesh_node: MeshInstance3D, color: Color) -> void:
	if mesh_node.mesh == null or mesh_node.mesh.get_surface_count() == 0:
		return
	if mesh_node.mesh.get_surface_count() > 1:
		for surface in range(mesh_node.mesh.get_surface_count()):
			var original := mesh_node.mesh.surface_get_material(surface) as StandardMaterial3D
			if original == null:
				continue
			var coloured := original.duplicate() as StandardMaterial3D
			coloured.albedo_color = color
			coloured.albedo_texture = _wardrobe_dye_texture(original.albedo_texture)
			coloured.vertex_color_use_as_albedo = false
			mesh_node.set_surface_override_material(surface, coloured)
		return
	var source: Material = mesh_node.get_active_material(0)
	if source is not StandardMaterial3D:
		return
	var material: StandardMaterial3D = (source as StandardMaterial3D).duplicate()
	material.albedo_color = color
	material.albedo_texture = _wardrobe_dye_texture(material.albedo_texture)
	material.vertex_color_use_as_albedo = false
	mesh_node.material_override = material

## Remove the atlas's baked brown dye while retaining fabric grain and seams.
## Shared once per source texture; character and equipment textures stay intact.
static func _wardrobe_dye_texture(source: Texture2D) -> Texture2D:
	if source == null:
		return null
	var key := source.get_instance_id()
	if _wardrobe_texture_cache.has(key):
		return _wardrobe_texture_cache[key]
	var original := source.get_image()
	if original == null or original.is_empty():
		return source
	var neutral := original.duplicate() as Image
	if neutral.is_compressed():
		neutral.decompress()
	neutral.convert(Image.FORMAT_RGBA8)
	var reference := 0.0
	var count := 0
	for y: int in neutral.get_height():
		for x: int in neutral.get_width():
			var pixel := neutral.get_pixel(x, y)
			if pixel.a > 0.0:
				reference += pixel.get_luminance()
				count += 1
	reference = maxf(0.01, reference / maxi(1, count))
	for y: int in neutral.get_height():
		for x: int in neutral.get_width():
			var pixel := neutral.get_pixel(x, y)
			var value := clampf(pixel.get_luminance() / reference, 0.0, 1.0)
			neutral.set_pixel(x, y, Color(value, value, value, pixel.a))
	neutral.generate_mipmaps()
	var texture := ImageTexture.create_from_image(neutral)
	_wardrobe_texture_cache[key] = texture
	_wardrobe_texture_cache[texture.get_instance_id()] = texture
	return texture

## Lifts a garment off the skin it is fitted to. Reuses the override the tint
## pass already installed so a garment keeps its colour.
func _grow_mesh(mesh_node: MeshInstance3D, amount: float) -> void:
	if mesh_node.mesh == null or mesh_node.mesh.get_surface_count() == 0:
		return
	if mesh_node.mesh.get_surface_count() > 1:
		for surface in range(mesh_node.mesh.get_surface_count()):
			var grown := mesh_node.get_surface_override_material(surface) as StandardMaterial3D
			if grown == null:
				var original := mesh_node.mesh.surface_get_material(surface) as StandardMaterial3D
				if original == null:
					continue
				grown = original.duplicate() as StandardMaterial3D
				mesh_node.set_surface_override_material(surface, grown)
			grown.grow = true
			grown.grow_amount = amount
		return
	var material: StandardMaterial3D = (mesh_node.material_override
		as StandardMaterial3D)
	if material == null:
		var source: Material = mesh_node.get_active_material(0)
		if source is not StandardMaterial3D:
			return
		material = (source as StandardMaterial3D).duplicate()
		mesh_node.material_override = material
	material.grow = true
	material.grow_amount = amount

func _add_hair_variant(style: int, color: Color) -> void:
	for old_attachment: Node in _native_skeleton.get_children():
		if old_attachment.name.begins_with("AppearanceHair_"):
			_native_skeleton.remove_child(old_attachment)
			old_attachment.queue_free()
	# Zero is bald for every colour cycle. Also hide any legacy sculpted hair;
	# appearance metadata keeps helmet removal from revealing it again.
	for node_value: Node in find_children("hair", "MeshInstance3D", true, false):
		var mesh := node_value as MeshInstance3D
		mesh.set_meta("uncovered_head_visible", false)
		mesh.hide()
	if style == 0:
		return
	var styles_value: Variant = _model_config.get("hairStyles", [])
	if styles_value is not Array or (styles_value as Array).is_empty():
		return
	var styles: Array = styles_value as Array
	var path: String = str(styles[posmod(style, styles.size())])
	if bool(_model_config.get("hairSkinned", false)):
		var holder := Node3D.new()
		holder.name = "AppearanceHair_%d" % style
		_native_skeleton.add_child(holder)
		for piece: Dictionary in _equipment_pieces(path):
			var skin := _rebound_skin(piece.get("bones", PackedStringArray()) as PackedStringArray,
				piece.get("binds", [] as Array[Transform3D]) as Array[Transform3D], Transform3D.IDENTITY)
			if skin == null:
				push_warning("Fitted hairstyle has an incompatible skeleton: " + path)
				continue
			var mesh := MeshInstance3D.new()
			mesh.name = str(piece.get("name", "NativeHair"))
			mesh.mesh = piece.get("mesh") as Mesh
			mesh.skin = skin
			mesh.transform = piece.get("transform", Transform3D.IDENTITY)
			_restore_piece_render_state(mesh, piece)
			holder.add_child(mesh)
			mesh.skeleton = NodePath("../..")
			_tint_mesh(mesh, color)
		return
	var native_hair: Node3D = _equipment_instance(path)
	if native_hair == null:
		push_warning("Native hairstyle failed to load: " + path)
		return
	var attachment: BoneAttachment3D = _bone_attachment("Head", 9, style)
	if attachment == null:
		native_hair.queue_free()
		return
	attachment.name = "AppearanceHair_%d" % style
	native_hair.name = "NativeHair"
	# Skull proportions are baked into each body. Fit shared hairstyles in
	# Head-local space without changing the skeleton or its inverse binds.
	var hair_fit: Dictionary = _model_config.get("hairFit", {}) as Dictionary
	native_hair.scale = _vector3(hair_fit.get("scale", []), Vector3.ONE)
	native_hair.position = _vector3(hair_fit.get("offset", []), Vector3.ZERO)
	attachment.add_child(native_hair)
	for node_value: Node in native_hair.find_children("*", "MeshInstance3D", true, false):
		_tint_mesh(node_value as MeshInstance3D, color)

func render_diagnostics() -> Dictionary:
	var meshes: Array[Dictionary] = []
	for node_value: Node in find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		# Silhouette clones are copies of meshes already listed here; counting
		# them would double every surface the actor reports.
		if mesh_node.has_meta(OccludedSilhouette.CLONE_META):
			continue
		meshes.append({
			"path": str(mesh_node.get_path()),
			"visible": mesh_node.visible,
			"visible_in_tree": mesh_node.is_visible_in_tree(),
			"layers": mesh_node.layers,
			"aabb": mesh_node.get_aabb(),
			"material_override": mesh_node.material_override != null,
		})
	var native_model: Node3D = get_node_or_null("NativeModel") as Node3D
	return {
		"actor_id": actor_id,
		"server_target": server_target,
		"final_global_position": global_position,
		"native_model_transform": native_model.transform if native_model != null else Transform3D.IDENTITY,
		"meshes": meshes,
	}

## Applies the player-selected actor quality to body, hair, and equipment.
## Selection rings, map dots and overhead UI are siblings of NativeModel, so
## they are deliberately outside this walk. The missing-model capsule is the
## one body-level fallback and follows explicitly.
func apply_render_quality(level: int, is_local_actor: bool = false) -> void:
	_render_quality = ACTOR_RENDER_QUALITY.normalized_quality(level)
	_render_quality_local_actor = is_local_actor
	_apply_render_quality_to_visuals()
	_refresh_cape_cloth_activity(true)
	if is_instance_valid(_mount_visual):
		_mount_visual.call("apply_render_quality", _render_quality, _render_quality_local_actor)

func render_quality() -> int:
	return _render_quality

func render_quality_is_local() -> bool:
	return _render_quality_local_actor

func mounted_presentation_priority() -> bool:
	return _render_quality_local_actor or _selected or _combat_target

func _apply_render_quality_to_visuals() -> void:
	if is_instance_valid(_native_model):
		ACTOR_RENDER_QUALITY.apply_actor(_native_model, _render_quality)
	var fallback := get_node_or_null("MissingModelFallback") as MeshInstance3D
	if fallback != null:
		ACTOR_RENDER_QUALITY.apply_mesh(fallback, _render_quality)

func _add_fallback_visual(dto: Dictionary) -> void:
	var mesh_instance: MeshInstance3D = MeshInstance3D.new()
	mesh_instance.name = "MissingModelFallback"
	var capsule: CapsuleMesh = CapsuleMesh.new()
	capsule.radius = 0.32
	capsule.height = 1.7
	var material: StandardMaterial3D = StandardMaterial3D.new()
	var kind: int = int(dto.get("kind", 0))
	material.albedo_color = Color(0.92, 0.56, 0.18) if kind == 2 else Color(0.75, 0.18, 0.78)
	capsule.material = material
	mesh_instance.mesh = capsule
	mesh_instance.position.y = 0.85
	add_child(mesh_instance)

## The dot this actor shows on the minimap and the full map. Every actor gets
## one: a player standing somewhere is the same kind of thing to read off a map
## as an NPC is, and the local player already has its own white mark drawn over
## the top of this one. Creatures are the exception, because what a player
## wants off a map during an invasion is where the invasion is - so a creature
## takes a colour of its own, and an invasion creature a third.
func _add_map_dot(dto: Dictionary) -> void:
	var dot: MeshInstance3D = MapMarkerDisc.build(
		"MapDot", MAP_DOT_RADIUS, map_dot_colour(dto))
	dot.position.y = 3.0
	add_child(dot)

## The map-dot colour a spawn packet asks for. Static and public so the map
## legend and the tests can name the same three colours this does rather than
## copies of them.
static func map_dot_colour(dto: Dictionary) -> Color:
	if int(dto.get("kind", 0)) != CREATURE_ACTOR_KIND:
		return MAP_DOT_COLOUR
	var name_colour: int = int(dto.get("name_colour", 0))
	if name_colour == INVASION_NAME_COLOUR:
		return INVASION_MAP_DOT_COLOUR
	# Only an uncoloured creature is wildlife. A summon is a creature the
	# server coloured, and it stays on the ordinary dot.
	return CREATURE_MAP_DOT_COLOUR if name_colour == 0 else MAP_DOT_COLOUR

## Whether a spawn packet describes a summoned creature. Static and public for
## the same reason `map_dot_colour` is: the world input and the tests should
## ask one question rather than each re-deriving it from the colour byte.
##
## It says a summon, not *whose* summon: the packet carries no owner. The
## server owns that answer and refuses a summon that is not yours, so a click
## only has to get this far to be worth sending.
static func is_summon(dto: Dictionary) -> bool:
	return (int(dto.get("kind", 0)) == CREATURE_ACTOR_KIND
		and int(dto.get("name_colour", 0)) == SUMMON_NAME_COLOUR)

## The nameplate. A guild tag arrives as part of the display name in the actor
## packet - "Alice ELO" - so a client that takes the whole string as a
## name renders the colour byte as mojibake and the tag as part of the player's
## name. The decoder splits them; this draws the tag as a tag.
##
## Natural creatures use bright yellow. Other names keep the
## server's colour: a demigod's name is green, an invasion creature's red, a
## summon's light blue. The guild tag has its own label and color marker.
static func banner_name(dto: Dictionary, fallback := "Unknown actor") -> String:
	var guild_tag: String = str(dto.get("guild_tag", ""))
	return (str(dto.get("name", fallback))
		+ ("  [%s]" % guild_tag if not guild_tag.is_empty() else ""))

static func _nameplate_colour(dto: Dictionary) -> Color:
	var role := name_color_role(dto)
	var name_colour: int = int(dto.get("name_colour", 0))
	if name_colour > 0 and not TextColors.is_overridden(role):
		return EloriaProtocol.el_text_colour(name_colour)
	return TextColors.color(role)

static func name_color_role(dto: Dictionary) -> String:
	var kind := int(dto.get("kind", 0))
	if kind == 2:
		return "world_npc"
	if kind == 4 or (kind == 5 and bool(dto.get("enhanced", false))):
		return "world_pk"
	if kind == CREATURE_ACTOR_KIND:
		return "world_creature"
	return "world_special_map" if int(dto.get("map_type", 0)) == 2 else "world_player"

static func guild_tag_color(dto: Dictionary) -> Color:
	var index := int(dto.get("guild_colour", 0))
	return (EloriaProtocol.el_text_colour(index) if index > 0 and not TextColors.is_overridden("world_guild")
		else TextColors.color("world_guild"))

func _add_nameplate(dto: Dictionary) -> void:
	var label: Label3D = Label3D.new()
	label.name = "Nameplate"
	label.text = str(dto.get("name", "Unknown actor"))
	label.position.y = NAMEPLATE_HEIGHT
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.fixed_size = true
	WORLD_LABEL_STYLE.apply(label, NAMEPLATE_FONT_SIZE, OVERHEAD_PIXEL,
		0)
	label.modulate = _nameplate_colour(dto)
	label.outline_modulate = Color.BLACK
	label.layers = WORLD_LABEL_STYLE.RENDER_LAYER
	add_child(label)
	_nameplate = label
	set_boss_rank(int(dto.get("boss_rank", 0)))
	_name_dto = _name_info(dto)
	if not TextColors.events().changed.is_connected(_on_text_colors_changed):
		TextColors.events().changed.connect(_on_text_colors_changed)
	_sync_nameplate_text()
	_add_health_bar()
	_add_overhead_background()
	_layout_overhead()
	apply_vitals(int(dto.get("health", 0)), int(dto.get("max_health", 0)))
	set_status_effects(dto.get("status_effects", dto.get("negative_statuses", [])))

static func _name_info(dto: Dictionary) -> Dictionary:
	var result := {}
	for field: String in ["name", "kind", "name_colour", "guild_tag", "guild_colour", "enhanced", "map_type"]:
		if dto.has(field): result[field] = dto[field]
	return result

func _sync_nameplate_text() -> void:
	if not is_instance_valid(_nameplate):
		return
	_nameplate.text = str(_name_dto.get("name", "Unknown actor"))
	var name_color := _nameplate_colour(_name_dto)
	_nameplate.modulate = Color(name_color, name_color.a * _overhead_fade)
	var tag := str(_name_dto.get("guild_tag", ""))
	if not tag.is_empty() and not is_instance_valid(_guild_nameplate):
		_guild_nameplate = Label3D.new()
		_guild_nameplate.name = "GuildTag"
		_guild_nameplate.position = _nameplate.position
		_guild_nameplate.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		_guild_nameplate.no_depth_test = true
		_guild_nameplate.fixed_size = true
		WORLD_LABEL_STYLE.apply(_guild_nameplate, NAMEPLATE_FONT_SIZE, OVERHEAD_PIXEL, 0)
		_guild_nameplate.outline_modulate = Color.BLACK
		add_child(_guild_nameplate)
	var name_width := _nameplate.font.get_string_size(_nameplate.text, HORIZONTAL_ALIGNMENT_LEFT, -1, _nameplate.font_size).x
	var tag_width := 0.0
	if is_instance_valid(_guild_nameplate):
		_guild_nameplate.text = "  [%s]" % tag if not tag.is_empty() else ""
		tag_width = _guild_nameplate.font.get_string_size(_guild_nameplate.text, HORIZONTAL_ALIGNMENT_LEFT, -1, _guild_nameplate.font_size).x
		_guild_nameplate.offset.x = name_width * 0.5
		var guild_color := guild_tag_color(_name_dto)
		_guild_nameplate.modulate = Color(guild_color, guild_color.a * _overhead_fade)
		_guild_nameplate.visible = not tag.is_empty() and _overhead_shown() and _banner_names
	_nameplate.offset.x = -tag_width * 0.5

func _on_text_colors_changed(_role: String) -> void:
	if not _role.is_empty() and not _role.begins_with("world_"):
		return
	_sync_nameplate_text()
	if is_instance_valid(_title_line):
		_title_line.modulate = TextColors.color("world_title")
	if is_instance_valid(_occupation_line):
		_occupation_line.modulate = TextColors.color("world_occupation")
	if is_instance_valid(_speech_bubble):
		_speech_bubble.modulate = TextColors.color("world_speech") if TextColors.is_overridden("world_speech") else _speech_color
	if is_instance_valid(_quest_marker) and not _quest_marker.text.is_empty():
		set_quest_available(false)
		set_quest_available(true)
	var previous := _health_current
	_health_current = -1
	apply_vitals(previous, _health_maximum)
	_refresh_overhead()

## One icon per active effect, in a stable order. Only server status
## snapshots change this list; a spell animation cannot prove an effect landed.
func set_status_effects(effects: Array) -> void:
	var next: Array[String] = STATUS_ICONS.known(effects)
	if next == _status_effects:
		return
	_status_effects = next
	if not is_instance_valid(_status_icons):
		_status_icons = Node3D.new()
		_status_icons.name = "StatusIcons"
		_status_icons.position.y = _nameplate.position.y
		add_child(_status_icons)
	for child: Node in _status_icons.get_children():
		_status_icons.remove_child(child)
		child.queue_free()
	for index: int in range(next.size()):
		var icon := MeshInstance3D.new()
		icon.name = next[index]
		icon.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		icon.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var quad := QuadMesh.new()
		quad.size = Vector2.ONE * NEGATIVE_STATUS_SIZE * OVERHEAD_PIXEL
		var material := _overhead_material(Color.WHITE, 4)
		material.albedo_texture = STATUS_TEXTURES[next[index]]
		quad.material = material
		icon.mesh = quad
		_status_icons.add_child(icon)
	_layout_status_effects()
	_refresh_status_effects()

func status_effect_count() -> int:
	return _status_effects.size() if _health_current > 0 else 0

func set_negative_statuses(effects: Array) -> void:
	set_status_effects(effects.filter(func(effect: Variant) -> bool: return effect in STATUS_ICONS.NEGATIVE))

func negative_status_count() -> int:
	return _status_effects.filter(func(effect: String) -> bool: return effect in STATUS_ICONS.NEGATIVE).size() if _health_current > 0 else 0

func _layout_status_effects() -> void:
	if not is_instance_valid(_status_icons):
		return
	var rise := NEGATIVE_STATUS_RISE
	if _banner_names and is_instance_valid(_title_line) and not _title_line.text.is_empty():
		rise += TITLE_RISE
	for index: int in range(_status_icons.get_child_count()):
		var icon := _status_icons.get_child(index) as MeshInstance3D
		var row: int = index / STATUS_ICONS.COLUMNS
		var columns := mini(STATUS_ICONS.COLUMNS, _status_effects.size() - row * STATUS_ICONS.COLUMNS)
		(icon.mesh as QuadMesh).center_offset = Vector3(
			(index % STATUS_ICONS.COLUMNS - (columns - 1) * 0.5)
				* (NEGATIVE_STATUS_SIZE + NEGATIVE_STATUS_GAP),
			rise + row * (NEGATIVE_STATUS_SIZE + NEGATIVE_STATUS_GAP), 0.0) * OVERHEAD_PIXEL

func _refresh_status_effects() -> void:
	if not is_instance_valid(_status_icons):
		return
	_status_icons.visible = _overhead_shown() and _banner_status_icons and status_effect_count() > 0
	for child: Node in _status_icons.get_children():
		_fade_quad(child as MeshInstance3D, 1.0)

## The overhead health bar and its numbers. Not drawn for everyone: every
## actor packet carries a health pair, scenery included, and a full bar over
## every shopkeeper in a market is a row of bars that never move. main.gd's
## `_overhead_health_for` decides; `set_health_visible` is how it says so.
##
## All three pieces hang from the nameplate's height rather than from three
## world heights of their own, and their separation is spelled inside the
## block, so that the fixed-size scaling keeps the name, the bar and the
## numbers the same distance apart on screen as they are wide.
func _add_health_bar() -> void:
	var background: MeshInstance3D = MeshInstance3D.new()
	background.name = "HealthBarBackground"
	var background_quad: QuadMesh = QuadMesh.new()
	background_quad.size = Vector2(HEALTH_BAR_WIDTH + HEALTH_BAR_BORDER,
		HEALTH_BAR_THICKNESS + HEALTH_BAR_BORDER) * OVERHEAD_PIXEL
	background_quad.center_offset = Vector3(
		0.0, -HEALTH_BAR_DROP * OVERHEAD_PIXEL, 0.0)
	background_quad.material = _overhead_material(HEALTH_BAR_BACKING, 1)
	background.mesh = background_quad
	background.position.y = NAMEPLATE_HEIGHT
	background.layers = WORLD_LABEL_STYLE.RENDER_LAYER
	add_child(background)
	_health_bar_background = background
	var fill: MeshInstance3D = MeshInstance3D.new()
	fill.name = "HealthBarFill"
	var fill_quad: QuadMesh = QuadMesh.new()
	fill_quad.size = Vector2(HEALTH_BAR_WIDTH, HEALTH_BAR_THICKNESS) * OVERHEAD_PIXEL
	fill_quad.center_offset = Vector3(
		0.0, -HEALTH_BAR_DROP * OVERHEAD_PIXEL, 0.0)
	fill_quad.material = _overhead_material(Color.GREEN, 2)
	(fill_quad.material as StandardMaterial3D).albedo_texture = _health_bar_texture()
	fill.mesh = fill_quad
	fill.position.y = NAMEPLATE_HEIGHT
	fill.layers = WORLD_LABEL_STYLE.RENDER_LAYER
	add_child(fill)
	_health_bar_fill = fill
	var numbers: Label3D = Label3D.new()
	numbers.name = "HealthNumbers"
	numbers.position.y = NAMEPLATE_HEIGHT
	# Label3D lays its offset out in the same pixels, so the drop is the drop.
	numbers.offset = Vector2(0.0, -HEALTH_LABEL_DROP)
	numbers.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	numbers.no_depth_test = true
	numbers.fixed_size = true
	numbers.render_priority = 3
	numbers.outline_render_priority = 2
	WORLD_LABEL_STYLE.apply(numbers, HEALTH_NUMBER_FONT_SIZE, OVERHEAD_PIXEL,
		0)
	numbers.outline_modulate = Color.BLACK
	numbers.layers = WORLD_LABEL_STYLE.RENDER_LAYER
	add_child(numbers)
	_health_label = numbers

## The name and inline health row share one compact translucent rectangle.
func _add_overhead_background() -> void:
	var backing := MeshInstance3D.new()
	backing.name = "OverheadBackground"
	backing.mesh = QuadMesh.new()
	(backing.mesh as QuadMesh).material = _overhead_material(OVERHEAD_BACKING, 0)
	backing.position.y = NAMEPLATE_HEIGHT
	backing.layers = WORLD_LABEL_STYLE.RENDER_LAYER
	backing.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(backing)
	_overhead_background = backing

## Measure the actual numbers so long health pairs never run into the bar.
## Offsets live in billboard pixels; moving nodes would offset them in world space.
func _layout_overhead() -> void:
	if not is_instance_valid(_nameplate) or not is_instance_valid(_health_label):
		return
	var raster: float = float(WORLD_LABEL_STYLE.RASTER_SCALE)
	var name_width: float = _nameplate.font.get_string_size(_nameplate.text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, _nameplate.font_size).x / raster
	if is_instance_valid(_guild_nameplate):
		name_width += _guild_nameplate.font.get_string_size(_guild_nameplate.text,
			HORIZONTAL_ALIGNMENT_LEFT, -1, _guild_nameplate.font_size).x / raster
	if not _banner_names:
		name_width = 0.0
	var occupied: bool = _banner_names and _has_occupation()
	if occupied:
		name_width = maxf(name_width, _occupation_line.font.get_string_size(
			_occupation_line.text, HORIZONTAL_ALIGNMENT_LEFT, -1,
			_occupation_line.font_size).x / raster)
	var drop: float = health_drop()
	var number_width: float = _health_label.font.get_string_size(_health_label.text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, _health_label.font_size).x / raster
	# Reserve the full pair so taking damage across a digit boundary does not
	# make the bar slide sideways while the actor is standing still.
	var full_pair := "%d/%d" % [_health_maximum, _health_maximum]
	number_width = maxf(number_width, _health_label.font.get_string_size(full_pair,
		HORIZONTAL_ALIGNMENT_LEFT, -1, _health_label.font_size).x / raster)
	var row_width: float = (HEALTH_BAR_WIDTH if _banner_health_bar else 0.0) \
		+ (number_width if _banner_health_numbers else 0.0) \
		+ (HEALTH_NUMBER_GAP if _banner_health_bar and _banner_health_numbers else 0.0)
	var bar_center: float = -(HEALTH_NUMBER_GAP + number_width) * 0.5 if _banner_health_numbers else 0.0
	_health_label.offset = Vector2((HEALTH_BAR_WIDTH + HEALTH_NUMBER_GAP) * 0.5 if _banner_health_bar else 0.0,
		-(drop - HEALTH_BAR_DROP + HEALTH_LABEL_DROP)) * raster
	var background := _health_bar_background.mesh as QuadMesh
	background.center_offset.x = bar_center * OVERHEAD_PIXEL
	background.center_offset.y = -drop * OVERHEAD_PIXEL
	var fill := _health_bar_fill.mesh as QuadMesh
	fill.center_offset.x = (bar_center - (HEALTH_BAR_WIDTH
		- fill.size.x / OVERHEAD_PIXEL) * 0.5) * OVERHEAD_PIXEL
	fill.center_offset.y = -drop * OVERHEAD_PIXEL
	if is_instance_valid(_overhead_background):
		var quad := _overhead_background.mesh as QuadMesh
		var has_health: bool = _health_shown and _health_maximum > 0 \
			and (_banner_health_bar or _banner_health_numbers)
		var bottom: float = (drop + 8.0 if has_health
			else 10.0 + (OCCUPATION_DROP if occupied else 0.0))
		quad.size = Vector2(maxf(name_width, row_width if has_health else 0.0)
			+ 8.0, 10.0 + bottom) * OVERHEAD_PIXEL
		quad.center_offset = Vector3(0.0, (10.0 - bottom) * 0.5 * OVERHEAD_PIXEL, 0.0)

static func _health_bar_texture() -> GradientTexture2D:
	if _health_gradient == null:
		_health_gradient = GradientTexture2D.new()
		_health_gradient.width = 1
		_health_gradient.height = 16
		_health_gradient.fill_from = Vector2.ZERO
		_health_gradient.fill_to = Vector2(0.0, 1.0)
		_health_gradient.gradient = Gradient.new()
		_health_gradient.gradient.colors = PackedColorArray([
			Color.WHITE, Color(0.45, 0.45, 0.45)])
	return _health_gradient

## Billboarded, unshaded and depth-test free, so the bar reads the same against
## terrain, water and another actor standing in front of it. Draw order is the
## render priority rather than a depth offset: the quads share a plane and a
## z nudge would swap sides as the camera orbits.
func _overhead_material(colour: Color, priority: int) -> StandardMaterial3D:
	var material: StandardMaterial3D = StandardMaterial3D.new()
	material.albedo_color = colour
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	material.billboard_keep_scale = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.no_depth_test = true
	material.disable_receive_shadows = true
	material.render_priority = priority
	# Same fixed screen size as the two labels the bar sits between.
	material.fixed_size = true
	return material

## Redraws the bar for a health pair the server sent. An actor the server gives
## no maximum for - most scenery NPCs - has nothing to draw, so it keeps the
## bare name rather than an empty bar that would read as "about to die".
func apply_vitals(current: int, maximum: int) -> void:
	# Bodies remain visible while fading, but must not intercept a living target.
	# Fallen players keep their pick layer for targeted healing and revival.
	collision_layer = 0 if (_is_creature and current <= 0) or _crowd_hidden else 2
	if current == _health_current and maximum == _health_maximum:
		return
	_health_current = current
	_health_maximum = maximum
	if not is_instance_valid(_health_bar_background) or not is_instance_valid(_health_bar_fill) \
			or not is_instance_valid(_health_label):
		return
	if maximum <= 0:
		_layout_overhead()
		_refresh_overhead()
		return
	var clamped: int = clampi(current, 0, maximum)
	var ratio: float = float(clamped) / float(maximum)
	_health_label.text = "%d/%d" % [clamped, maximum]
	_health_label.modulate = (TextColors.color("world_health") if TextColors.is_overridden("world_health") else _health_colour(ratio))
	var fill_quad: QuadMesh = _health_bar_fill.mesh as QuadMesh
	if clamped > 0:
		var width: float = HEALTH_BAR_WIDTH * ratio
		fill_quad.size = Vector2(width, HEALTH_BAR_THICKNESS) * OVERHEAD_PIXEL
		# A QuadMesh is centred on its origin, so a shrinking bar would drain
		# from both ends. The offset pins the left edge instead, and it is a
		# mesh offset rather than a node position because the billboard shader
		# discards the node basis and would leave the nudge pointing at the
		# world axis the camera happened to start on. It carries the bar's
		# drop below the name for the same reason.
		fill_quad.center_offset = Vector3(
			-(HEALTH_BAR_WIDTH - width) * 0.5 * OVERHEAD_PIXEL,
			-health_drop() * OVERHEAD_PIXEL, 0.0)
		var material: StandardMaterial3D = fill_quad.material as StandardMaterial3D
		material.albedo_color = _health_colour(ratio)
	_layout_overhead()
	_refresh_overhead()

## Whether this actor's condition is worth the space over its head - which is
## main.gd's question, not this node's. See `_add_health_bar`.
func set_health_visible(enabled: bool) -> void:
	if enabled == _health_shown:
		return
	_health_shown = enabled
	_layout_overhead()
	_refresh_overhead_health()

## The bar and values have separate display switches. Both still obey the
## banner's visibility, range, crowd filtering and authoritative health.
func _refresh_overhead_health() -> void:
	_refresh_status_effects()
	var showing: bool = (_overhead_shown() and _health_shown
		and _health_maximum > 0)
	if is_instance_valid(_health_bar_background):
		_health_bar_background.visible = showing and _banner_health_bar
		_fade_quad(_health_bar_background, HEALTH_BAR_BACKING.a)
	if is_instance_valid(_health_bar_fill):
		_health_bar_fill.visible = showing and _banner_health_bar and _health_current > 0
		# `apply_vitals` repaints the fill opaque, and calls this straight after.
		_fade_quad(_health_bar_fill, 1.0)
	if is_instance_valid(_health_label):
		_health_label.visible = showing and _banner_health_numbers
		_fade_label(_health_label)
	if is_instance_valid(_overhead_background):
		_overhead_background.visible = _overhead_shown() and _banner_background \
			and (_banner_names or (showing and (_banner_health_bar or _banner_health_numbers)))
		_fade_quad(_overhead_background, OVERHEAD_BACKING.a)

## Whether the overhead block is drawn at all: the banner options allow it,
## the actor is inside the name distance, and it is inside the draw distance.
## The last matters because `set_drawn` hides these nodes itself, and a label
## switched back on while the actor is out of range would float over nothing.
func _overhead_shown() -> bool:
	return _overhead_visible and not _overhead_crowded and _overhead_fade > 0.0 and _drawn \
		and not _crowd_hidden and not (_is_creature and _health_current == 0)

func set_overhead_crowded(crowded: bool) -> void:
	if _overhead_crowded == crowded:
		return
	_overhead_crowded = crowded
	_refresh_overhead()

func _fade_label(label: Label3D) -> void:
	var alpha := 1.0
	if label == _nameplate: alpha = _nameplate_colour(_name_dto).a
	elif label == _guild_nameplate: alpha = guild_tag_color(_name_dto).a
	elif label == _title_line: alpha = TextColors.color("world_title").a
	elif label == _occupation_line: alpha = TextColors.color("world_occupation").a
	elif label == _health_label and TextColors.is_overridden("world_health"): alpha = TextColors.color("world_health").a
	label.modulate.a = alpha * _overhead_fade
	label.outline_modulate.a = alpha * _overhead_fade

func _fade_quad(quad: MeshInstance3D, opacity: float) -> void:
	var material := (quad.mesh as QuadMesh).material as StandardMaterial3D
	material.albedo_color.a = opacity * _overhead_fade

static func _health_colour(ratio: float) -> Color:
	var fraction := clampf(ratio, 0.0, 1.0)
	return Color(clampf((1.0 - fraction) * 2.0, 0.0, 1.0),
		clampf(fraction / 1.25 * 2.0, 0.0, 1.0), 0.0)

func set_nameplate_visible(enabled: bool) -> void:
	# Main restates this with every packet; every other input to the overhead
	# block refreshes it itself, so an unchanged answer has nothing to redo.
	if enabled == _overhead_visible:
		return
	_overhead_visible = enabled
	_refresh_overhead()

## Select the contents independently of the banner's overall visibility. The
## defaults preserve player/NPC banners and actors configured without Main.
func set_banner_parts(options: Dictionary) -> void:
	var names := bool(options.get("names", true))
	var health_bar := bool(options.get("health_bar", true))
	var health_numbers := bool(options.get("health_numbers", true))
	var status_icons := bool(options.get("status_icons", true))
	var background := bool(options.get("background", true))
	if names == _banner_names and health_bar == _banner_health_bar \
			and health_numbers == _banner_health_numbers and status_icons == _banner_status_icons \
			and background == _banner_background:
		return
	_banner_names = names
	_banner_health_bar = health_bar
	_banner_health_numbers = health_numbers
	_banner_status_icons = status_icons
	_banner_background = background
	_layout_overhead()
	_layout_status_effects()
	_refresh_overhead()

## Fades the name, title and health bar together: 1 draws them as they are,
## 0 hides them. main.gd works it out from how far this actor is from the
## player. The speech bubble is not part of it - what somebody said is worth
## seeing as long as they can be seen.
func set_overhead_fade(fade: float) -> void:
	var next: float = clampf(fade, 0.0, 1.0)
	if next == _overhead_fade:
		return
	_overhead_fade = next
	_refresh_overhead()

func overhead_fade() -> float:
	return _overhead_fade

func _refresh_overhead() -> void:
	if is_instance_valid(_boss_rank_label):
		_boss_rank_label.visible = _drawn and not _crowd_hidden and _overhead_fade > 0.0 and _boss_rank > 0
		_fade_label(_boss_rank_label)
	if is_instance_valid(_quest_marker):
		# Quest offers remain visible when nameplates are disabled or crowded.
		_quest_marker.visible = _drawn and not _crowd_hidden and _overhead_fade > 0.0 \
			and not _quest_marker.text.is_empty()
	if is_instance_valid(_nameplate):
		_nameplate.visible = _overhead_shown() and _banner_names
		_fade_label(_nameplate)
	if is_instance_valid(_guild_nameplate):
		_guild_nameplate.visible = _overhead_shown() and _banner_names and not _guild_nameplate.text.is_empty()
		_fade_label(_guild_nameplate)
	if is_instance_valid(_title_line):
		_title_line.visible = _overhead_shown() and _banner_names and not _title_line.text.is_empty()
		_fade_label(_title_line)
	if is_instance_valid(_occupation_line):
		_occupation_line.visible = _overhead_shown() and _banner_names and _has_occupation()
		_fade_label(_occupation_line)
	_refresh_overhead_health()

## The title a player chose from the achievements that grant one, drawn as its
## own line above the name.
##
## A label of its own rather than more text in the nameplate: the name carries
## the server's colour - a demigod's is green, a summon's light blue - and a
## Label3D tints as one piece, so a title sharing it would read as part of the
## name. It is built on first use, so the overwhelming majority of actors,
## which wear none, cost nothing for it.
func set_title(title: String) -> void:
	if title.is_empty():
		if is_instance_valid(_title_line):
			_title_line.text = ""
			_title_line.hide()
		_layout_status_effects()
		return
	if not is_instance_valid(_title_line):
		var label: Label3D = Label3D.new()
		label.name = "TitleLine"
		# The name's height, not the constant: a scaled actor has had the whole
		# overhead block lifted, and a label built afterwards would otherwise
		# hang at the unscaled height on its own.
		label.position.y = (_nameplate.position.y
			if is_instance_valid(_nameplate) else NAMEPLATE_HEIGHT)
		label.offset = Vector2(0.0, TITLE_RISE)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		# Fixed on screen like the name it sits over, or the two would drift
		# apart as the camera zoomed.
		label.fixed_size = true
		WORLD_LABEL_STYLE.apply(label, TITLE_FONT_SIZE, OVERHEAD_PIXEL,
			OVERHEAD_OUTLINE_SIZE)
		label.modulate = TextColors.color("world_title")
		label.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		add_child(label)
		_title_line = label
	_title_line.text = title
	_layout_status_effects()
	_title_line.visible = _overhead_shown() and _banner_names
	_fade_label(_title_line)

## What this NPC does, drawn as "<Grove-Keeper>" on a line of its own under the
## name. The server sends it on its own packet (ELORIA_ACTOR_OCCUPATIONS) for
## a client that declares actor_occupations_v1; "" takes the line off.
##
## A label of its own for the reason the title has one: a Label3D tints as one
## piece, so a second line inside the nameplate would take the name's colour
## and size. It fades, hides and declutters with the rest of the block, and
## the translucent backing grows to hold it.
func set_quest_available(available: bool) -> void:
	if not available:
		if is_instance_valid(_quest_marker):
			_quest_marker.text = ""
			_quest_marker.hide()
		if is_instance_valid(_quest_marker_tween):
			_quest_marker_tween.kill()
		return
	if is_instance_valid(_quest_marker) and not _quest_marker.text.is_empty():
		return
	if not is_instance_valid(_quest_marker):
		_quest_marker = Label3D.new()
		_quest_marker.name = "QuestOfferMarker"
		_quest_marker.position.y = _nameplate.position.y if is_instance_valid(_nameplate) else NAMEPLATE_HEIGHT
		_quest_marker.offset = Vector2(0.0, 36.0)
		_quest_marker.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		_quest_marker.no_depth_test = true
		_quest_marker.fixed_size = true
		_quest_marker.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		WORLD_LABEL_STYLE.apply(_quest_marker, 30, OVERHEAD_PIXEL, 2)
		_quest_marker.outline_modulate = Color(0.28, 0.13, 0.01)
		add_child(_quest_marker)
	_quest_marker.text = "!"
	var marker_color := TextColors.color("world_quest")
	_quest_marker.modulate = marker_color
	_quest_marker_tween = create_tween().set_loops()
	_quest_marker_tween.tween_property(_quest_marker, "modulate", marker_color.lightened(0.35), 0.8)
	_quest_marker_tween.parallel().tween_property(_quest_marker, "offset:y", 42.0 * WORLD_LABEL_STYLE.RASTER_SCALE, 0.8).set_trans(Tween.TRANS_SINE)
	_quest_marker_tween.tween_property(_quest_marker, "modulate", marker_color, 0.8)
	_quest_marker_tween.parallel().tween_property(_quest_marker, "offset:y", 36.0 * WORLD_LABEL_STYLE.RASTER_SCALE, 0.8).set_trans(Tween.TRANS_SINE)
	_refresh_overhead()

func set_occupation(occupation: String) -> void:
	var text: String = occupation.strip_edges()
	if text == _occupation and (text.is_empty() or is_instance_valid(_occupation_line)):
		return
	_occupation = text
	if text.is_empty():
		if is_instance_valid(_occupation_line):
			_occupation_line.text = ""
			_occupation_line.hide()
	else:
		if not is_instance_valid(_occupation_line):
			var label: Label3D = Label3D.new()
			label.name = "OccupationLine"
			# The name's height, not the constant, as for the title line.
			label.position.y = (_nameplate.position.y
				if is_instance_valid(_nameplate) else NAMEPLATE_HEIGHT)
			label.offset = Vector2(0.0, -OCCUPATION_DROP)
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.no_depth_test = true
			label.fixed_size = true
			# Plain letters over the block's backing, like the name above it.
			WORLD_LABEL_STYLE.apply(label, OCCUPATION_FONT_SIZE, OVERHEAD_PIXEL, 0)
			label.modulate = TextColors.color("world_occupation")
			label.outline_modulate = Color.BLACK
			label.layers = WORLD_LABEL_STYLE.RENDER_LAYER
			add_child(label)
			_occupation_line = label
		_occupation_line.text = "<%s>" % text
	_layout_overhead()
	_refresh_overhead()

## The occupation shown under the name, without its brackets; "" for none.
func occupation() -> String:
	return _occupation

func _has_occupation() -> bool:
	return is_instance_valid(_occupation_line) and not _occupation_line.text.is_empty()

## How far below the name the health bar and its numbers sit: a line further
## down when an occupation is drawn between them.
func health_drop() -> float:
	return HEALTH_BAR_DROP + (OCCUPATION_DROP if _has_occupation() else 0.0) if _banner_names else 0.0

## Eternal Lands repeats local chat over the speaker's head while "Show Speech
## Bubbles" is on (text.c check_chat_text_to_overtext), sitting above the
## banner rather than replacing it.
func show_speech_bubble(speech: String, duration_msec: int, color := Color.WHITE) -> void:
	_speech_color = color
	if not is_instance_valid(_speech_bubble):
		var label: Label3D = Label3D.new()
		label.name = "SpeechBubble"
		label.position.y = (_nameplate.position.y
			if is_instance_valid(_nameplate) else NAMEPLATE_HEIGHT)
		label.offset = Vector2(0.0, SPEECH_BUBBLE_RISE)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		# Fixed on screen like the name it sits above, or the two would drift
		# into one another as the camera zoomed.
		label.fixed_size = true
		# Oldcraft's ambient lines use cream lettering over a compact dark
		# translucent bubble. Label3D cannot draw a nine-patch panel without a
		# viewport per speaker, so the wider dark surround gives the same visual
		# separation for a fraction of the memory and draw-call cost.
		label.outline_modulate = SPEECH_BUBBLE_SURROUND
		label.width = SPEECH_BUBBLE_WIDTH
		WORLD_LABEL_STYLE.apply(label, SPEECH_BUBBLE_FONT_SIZE, OVERHEAD_PIXEL, 6)
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.modulate = TextColors.color("world_speech")
		label.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		add_child(label)
		_speech_bubble = label
	_speech_bubble.text = speech
	_speech_bubble.modulate = TextColors.color("world_speech") if TextColors.is_overridden("world_speech") else color
	_speech_bubble.show()
	_speech_bubble_expiry_msec = Time.get_ticks_msec() + duration_msec

func clear_speech_bubble() -> void:
	_speech_bubble_expiry_msec = 0
	if is_instance_valid(_speech_bubble):
		_speech_bubble.hide()

## Restate how large this actor is drawn. Separate from `configure` for the
## same reason the footprint's setter is: the size can change after the
## model is built - an ordinary creature is promoted to an invasion boss
## and is redrawn larger without being respawned.
func set_boss_rank(value: int) -> void:
	var rank := clampi(value, 0, 2)
	if rank == _boss_rank:
		return
	_boss_rank = rank
	if rank > 0 and not is_instance_valid(_boss_rank_label):
		_boss_rank_label = Label3D.new()
		_boss_rank_label.name = "BossRank"
		_boss_rank_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		_boss_rank_label.no_depth_test = true
		_boss_rank_label.fixed_size = true
		_boss_rank_label.offset = Vector2(0, 26)
		WORLD_LABEL_STYLE.apply(_boss_rank_label, 16, OVERHEAD_PIXEL, 2)
		_boss_rank_label.outline_modulate = Color.BLACK
		_boss_rank_label.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		add_child(_boss_rank_label)
	if is_instance_valid(_boss_rank_label):
		_boss_rank_label.text = "BOSS" if rank == 2 else ("MINIBOSS" if rank == 1 else "")
		_boss_rank_label.modulate = Color("ffd166") if rank == 2 else Color("ff9c66")
		_boss_rank_label.position.y = banner_head_height() + NAMEPLATE_CLEARANCE
	_refresh_overhead()

func set_server_scale(value: float) -> void:
	var next := maxf(0.01, value)
	if is_equal_approx(next, server_scale):
		return
	server_scale = next
	_apply_model_scale()

## The model's size combines its import scale, small-creature presentation
## boost, and what the server says this actor is. Applied to
## the model node rather than to the actor, so the nameplate, health bar,
## selection ring and map dot keep their own sizes - a giant's name should
## not be drawn in giant letters. Their heights do follow, below, or they
## would end up inside its head.
func _apply_model_scale() -> void:
	_clear_native_surface_tilt()
	# Legibility is based on the final authored size. A tiny source model
	# promoted to a giant must not keep its small-creature display boost.
	if _native_body_bounds.size != Vector3.ZERO:
		var body_size: Vector3 = _native_body_bounds.size * _import_scale * server_scale
		var longest: float = maxf(body_size.x, maxf(body_size.y, body_size.z))
		_small_creature_scale = (maxf(SMALL_CREATURE_SCALE, SMALL_CREATURE_MIN_SIZE / longest)
			if _is_creature and longest > 0.0 and longest < SMALL_CREATURE_MAX_SIZE else 1.0)
	var total: float = _import_scale * _small_creature_scale * server_scale
	for node_name: String in ["NativeModel", "MissingModelFallback"]:
		var model := get_node_or_null(node_name) as Node3D
		if model != null:
			model.scale = Vector3.ONE * total
			# Measured in gameplay metres after import scale. The logical tile,
			# picking capsule and ground markers retain their server positions.
			model.position.z = maxf(0.0, float((_model_config.get("import", {}) as Dictionary).get(
				"visualBacksetMetres", 0.0))) * _small_creature_scale * server_scale
	_apply_surface_orientation()
	_size_stand_in()
	_lift_overhead(server_scale)

## The top of the body as drawn, above this actor's foot point: the authored
## bounds through both model scales, or the fallback nameplate height less its
## clearance when no native body loaded.
func head_height() -> float:
	if is_instance_valid(_native_model) and _native_body_bounds.size.y > 0.0:
		return (_native_model.transform * _native_body_bounds).end.y
	return (NAMEPLATE_HEIGHT - NAMEPLATE_CLEARANCE) * server_scale

## Mounted banners follow the actor at a fixed seat-relative height, while
## the visible rider continues to follow the mount's animated saddle.
func banner_head_height() -> float:
	if is_instance_valid(_mount_visual):
		return float(_mount_visual.get("banner_head_height"))
	return head_height()

## Keep the overhead furniture above the model as it grows.
func _lift_overhead(factor: float) -> void:
	var height: float = NAMEPLATE_HEIGHT * factor
	if is_instance_valid(_native_model) and _native_body_bounds.size.y > 0.0:
		height = banner_head_height() + NAMEPLATE_CLEARANCE
	# One height for the lot: the bar, the numbers and the bubble sit above or
	# below the name inside the block rather than at world heights of their
	# own, so the gaps between them hold their size along with the text.
	for node_name: String in ["Nameplate", "GuildTag", "TitleLine", "OccupationLine", "QuestOfferMarker", "BossRank",
			"HealthBarBackground", "HealthBarFill", "HealthNumbers", "SpeechBubble",
			"OverheadBackground", "StatusIcons"]:
		var node := get_node_or_null(node_name) as Node3D
		if node != null:
			node.position.y = height
	_sync_combat_target_marker()

## Restate how much ground this actor stands on, resizing what depends on
## it. Separate from `configure` because the footprint table is a login
## packet: if it lands after an actor has already been built, that actor
## corrects itself on the next state update instead of staying the wrong
## size until it walks out of view.
func set_footprint(value: Vector2i) -> void:
	var next := Vector2i(maxi(1, value.x), maxi(1, value.y))
	if next == footprint:
		return
	footprint = next
	_resize_selection()

## Grow the click target and the ground marker to the actor's own size.
func _resize_selection() -> void:
	var span: float = float(maxi(footprint.x, footprint.y))
	var shape: CollisionShape3D = get_node_or_null(
		"SelectionCollision") as CollisionShape3D
	if shape != null and shape.shape is CapsuleShape3D:
		(shape.shape as CapsuleShape3D).radius = SELECTION_RADIUS * span
	if _selection_ring != null:
		_selection_ring_flat = COMBAT_TARGET_MARKER.outline(
			Vector2(footprint) * _metres_per_tile,
			_target_marker_style.square_size / 100.0,
			_target_marker_style.square_thickness / 100.0,
			_target_marker_style.square_color)
		_selection_ring.mesh = _selection_ring_flat
		_selection_ring_draped_at = Vector3(NAN, NAN, NAN)
	_size_stand_in()
	_sync_combat_target_marker()

## Tentative and confirmed target circles share footprint sizing, borders
## and terrain sampling. Hold the footprint axes level with the world when
## the actor turns, including rectangular footprints whose rings are oval.
## These visual preferences never resize the logical footprint or click shape.
func _level_selection_ring() -> void:
	if _selection_ring != null and _selection_ring.visible:
		_selection_ring.rotation.y = -rotation.y
		_drape_selection_ring()

## Lay the marker back onto the ground the actor is standing on now.
##
## The marker used to be one flat square a fixed five centimetres over the tile
## centre's height. Regions rise more than that inside a single tile almost
## everywhere, so its uphill side spent most of its time inside the hill, and
## the part of it the depth buffer kept changed with every step - a bright box
## under the player losing and regaining a quarter of itself, frame after
## frame, for as long as they were running.
func _drape_selection_ring() -> void:
	if _selection_ring_flat == null or not is_inside_tree():
		return
	var here: Vector3 = global_position
	if _selection_ring_draped_at.is_finite() and here.distance_to(
			_selection_ring_draped_at) < RING_REDRAPE_METRES:
		return
	var draped: ArrayMesh = GroundDrape.drape(_selection_ring,
		_selection_ring_flat)
	if draped == null:
		# No walk surface under the actor - a map still loading, or an actor
		# the server placed off the mesh. The flat marker is what there is,
		# and the next frame asks again rather than settling for it.
		if _selection_ring.mesh != _selection_ring_flat:
			_selection_ring.mesh = _selection_ring_flat
		return
	_selection_ring.mesh = draped
	_selection_ring_draped_at = here

static func footprint_outline(width_m: float, depth_m: float,
		size_scale := 1.0, thickness_scale := 1.0) -> ArrayMesh:
	var half_x: float = maxf(0.1, (width_m * 0.5 - RING_INSET) * size_scale)
	var half_z: float = maxf(0.1, (depth_m * 0.5 - RING_INSET) * size_scale)
	var thickness: float = minf(RING_THICKNESS * thickness_scale,
		minf(half_x, half_z) * 0.9)
	var outer: Array[Vector3] = [
		Vector3(-half_x, 0.0, -half_z), Vector3(half_x, 0.0, -half_z),
		Vector3(half_x, 0.0, half_z), Vector3(-half_x, 0.0, half_z)]
	var inner_x: float = half_x - thickness
	var inner_z: float = half_z - thickness
	var inner: Array[Vector3] = [
		Vector3(-inner_x, 0.0, -inner_z), Vector3(inner_x, 0.0, -inner_z),
		Vector3(inner_x, 0.0, inner_z), Vector3(-inner_x, 0.0, inner_z)]
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	for side: int in range(4):
		var next: int = (side + 1) % 4
		# A side is cut into lengths GroundDrape can follow the ground with. A
		# corner-to-corner quad crosses several terrain cells on a big
		# creature's marker, and a straight line drawn between two draped
		# corners dives through whatever the ground does in between.
		var steps: int = maxi(1, ceili(
			outer[side].distance_to(outer[next]) / RING_SEGMENT_METRES))
		for step: int in steps:
			var from: float = float(step) / float(steps)
			var to: float = float(step + 1) / float(steps)
			var outer_from: Vector3 = outer[side].lerp(outer[next], from)
			var outer_to: Vector3 = outer[side].lerp(outer[next], to)
			var inner_from: Vector3 = inner[side].lerp(inner[next], from)
			var inner_to: Vector3 = inner[side].lerp(inner[next], to)
			for point: Vector3 in [outer_from, outer_to, inner_to,
					outer_from, inner_to, inner_from]:
				vertices.append(point)
				normals.append(Vector3.UP)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh

func rebase_world(frame: Transform3D) -> void:
	if _charge_leap != null: _charge_leap.rebase(frame)
	global_position = frame * global_position
	server_target = frame * server_target
	_segment_start = frame * _segment_start
	var yaw := frame.basis.get_euler().y
	rotation.y += yaw
	_target_yaw += yaw
	_travel_yaw += yaw
	_surface_up = frame.basis * _surface_up
	_surface_target_up = frame.basis * _surface_target_up
	_surface_applied_up = Vector3(NAN, NAN, NAN)
	_apply_surface_orientation()
	_selection_ring_draped_at = Vector3(NAN, NAN, NAN)
	if _combat_target_marker != null:
		_combat_target_marker.call("invalidate_ground")

	var remote = RemotePresentationService.current()
	if remote != null: remote.sync_transfer(self)

func apply_server_state(dto: Dictionary, adapter: CoordinateAdapter, teleport := false) -> void:
	if not _remote_pending_transfer.is_empty():
		RemotePresentationService.restore_pending(self)
		if is_queued_for_deletion(): return
	set_boss_rank(int(dto.get("boss_rank", 0)))
	var remote = RemotePresentationService.current() if _remote_enrollment_ready else null
	if remote != null and remote._ready_native:
		if remote.is_local_actor(actor_id):
			remote.detach(self, "local_role")
		else:
			var started := Time.get_ticks_usec()
			_apply_server_state_native(dto, adapter, teleport)
			remote.record_boundary("full_server_apply_us", Time.get_ticks_usec() - started)
			return
	# A revived body starts a new movement stream at its respawn tile. Do
	# not interpolate from its corpse or retain the old step schedule.
	teleport = teleport or (current_action == &"death"
		and int(dto.get("health", 0)) > 0 and bool(dto.get("alive", true)))
	if teleport and _charge_leap != null: end_charge_leap()
	_sync_death_presentation(dto)
	# A guild refresh removes and re-adds the actor in one socket read. Main
	# coalesces that into an update of the existing body, including its label.
	if dto.has("name") and is_instance_valid(_nameplate):
		var next_name_info := _name_info(dto)
		if _name_dto != next_name_info:
			_name_dto = next_name_info
			_sync_nameplate_text()
			_layout_overhead()
	set_status_effects(dto.get("status_effects", dto.get("negative_statuses", [])))
	# The capability handshake can correct an actor already spawned from the
	# legacy clothing bytes. Update its dyes once, including under worn armour.
	if dto.has("appearance") and dto.appearance != _appearance:
		apply_appearance_variants(dto.appearance as Dictionary)
	if not is_equal_approx(_metres_per_tile, adapter.metres_per_tile):
		_metres_per_tile = maxf(0.01, adapter.metres_per_tile)
		_resize_selection()
	if dto.has("footprint"):
		set_footprint(dto.get("footprint") as Vector2i)
	if dto.has("scale"):
		set_server_scale(float(dto.get("scale")))
	var next_target: Vector3 = adapter.footprint_center(
		int(dto.x), int(dto.y), footprint)
	# Server movement contains tile coordinates only. Keep the last sampled
	# rendered-surface height until Main performs the ray sample for the new tile;
	# otherwise each packet temporarily pushes actors back to the flat manifest
	# fallback and can leave them visibly embedded in sculpted terrain.
	next_target.y = server_target.y
	var target_changed: bool = server_target.distance_squared_to(next_target) > 0.000001
	# Where the server had this actor before this update. The step it just took
	# is that far, which is what the pace below is measured and spent against -
	# not the distance from the rendered body, which trails by the arrival
	# margin and would feed its own lag back into the pacing.
	var previous_target: Vector3 = server_target
	server_target = next_target
	var actor_command: int = int(dto.get("command", -1))
	var combat_changed: bool = bool(dto.get("in_combat", _in_combat)) != _in_combat
	_in_combat = bool(dto.get("in_combat", _in_combat))
	var command_sequence := int(dto.get("command_sequence", -1))
	var fresh_command := command_sequence != _last_command_sequence
	_last_command_sequence = command_sequence
	# Combat interrupts the movement stream. Its duration is not a step
	# interval, and the network buffer from the approach must not slow the
	# short move onto the bag. Keep learned gaits and any step still rendering;
	# only the next step's timing starts afresh. Explicit transition commands
	# also cover entering and leaving combat within one reduced update.
	if combat_changed or (fresh_command and actor_command in [18, 19]):
		_last_movement_update_msec = -1
		_unconfirmed_paces.clear()
		_unconfirmed_gait = -1
		_jitter_allowance = 0.0
		_schedule_due = -1.0
	# Which command the facing comes from, and which it does not. Everything
	# arriving in one socket read is reduced to a single state and rendered
	# once, so the last command of a frame is rarely the one that named a
	# direction: a creature sends the turn that puts it on its target and the
	# swing that follows it in the same flush, and reading the facing off the
	# last command threw the turn away every round. The reducer keeps the last
	# directional command of the burst apart for exactly this.
	var facing_command: int = int(dto.get("facing_command", actor_command))
	# The server has answered a predicted turn. Drop the prediction so the
	# rendered facing is the authoritative one from here on.
	if _predicted_turn_pending and EloriaProtocol.is_turn_command(facing_command):
		_predicted_turn_pending = false
	var authoritative_yaw: float = target_yaw_for_state(
		_target_yaw, facing_command, int(dto.rotation), adapter)
	_target_yaw = _predicted_turn_yaw if _predicted_turn_pending else authoritative_yaw
	_hastened = (int(dto.get("buffs", 0))
		& EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED) != 0 or "haste" in _status_effects
	_presentation_speed = walk_presentation_speed
	if _hastened or (actor_command >= 30 and actor_command <= 37):
		_presentation_speed = run_presentation_speed
	# A delayed creature burst can cover several tiles. Present its recovery
	# continuously; only an explicit relocation or an out-of-view correction snaps.
	if teleport or global_position.distance_to(server_target) > (64.0 if _is_creature else 8.0):
		global_position = server_target
		rotation.y = _target_yaw
		_segment_start = server_target
		_segment_elapsed = 0.0
		_segment_duration = 0.0
		_last_movement_update_msec = -1
		_pace_histories.clear()
		_smoothed_server_interval = _pace_for_gait(pace_gait(facing_command, _hastened))
		_unconfirmed_paces.clear()
		_unconfirmed_gait = -1
		_jitter_allowance = 0.0
		_schedule_due = -1.0
		_previous_step_tiles = 1.0
		_previous_step_gait = pace_gait(facing_command, _hastened)
		_movement_coast_remaining = 0.0
		_snap_pending = false
		_travel_yaw_active = false
	elif target_changed:
		# A step the server stamped with its own clock is timed by when it was
		# taken (server_time_pacing.gd); any other by when it arrived.
		var clock_msec: int = _movement_time_msec()
		var stamped: bool = dto.has(ServerTimePacing.STEP_KEY)
		var now_msec: int = int(dto[ServerTimePacing.STEP_KEY]) if stamped else clock_msec
		var now: float = float(now_msec) / 1000.0
		# How much ground the server covered, in tiles. A diagonal step is 1.41
		# of them and a folded burst several, so timing the update against it
		# gives a pace per tile that every step shape agrees on. Timing it
		# against the step count instead read a diagonal as a short interval
		# and rendered it 41% faster than the straight step beside it, which is
		# what walking and running at an uneven speed was.
		var step_tiles: float = maxf(
			previous_target.distance_to(server_target) / _metres_per_tile, 0.001)
		if _last_movement_update_msec >= 0:
			var observed_interval: float = float(
				now_msec - _last_movement_update_msec) / 1000.0
			# The gap before this packet is the hold the server gave the step
			# before it, so it is measured per tile of that step.
			var gap_tiles: float = maxf(_previous_step_tiles, 0.001)
			var gap_pace: float = maxf(observed_interval / gap_tiles, 0.05)
			var history: PackedFloat32Array = _pace_histories.get(
				_previous_step_gait, PackedFloat32Array())
			# A stationary pause is idle time, not a cadence. Folding it in
			# paced the next burst by how long the player stood still: a few
			# single steps from bag to bag with a second's looting between them
			# were enough to make the median a second a tile, and the run after
			# them crawled for its first steps while the body fell tiles behind.
			# A pause is told from the cadence by the same lateness a network
			# hold is allowed, against the pace this gait has already shown, so
			# it is only ever judged against steps of its own kind - #walk after
			# #run is a different history, not a late step. A gait still being
			# learned has nothing to judge against and takes what it is given,
			# short of a gap longer than any step the server holds.
			var idle: bool = gap_pace > maximum_segment_duration
			var standing: bool = idle
			if not standing and history.size() >= PACE_MINIMUM_REFERENCE:
				standing = is_pause_gap(observed_interval,
					median_of(history, _smoothed_server_interval) * gap_tiles)
			if idle:
				_unconfirmed_paces.clear()
			elif standing:
				# Pauses are not a cadence, but a pace that really has slowed -
				# a creature back from a pursuit to its ordinary walk - looks
				# like one pause after another. Those agree with each other and
				# a player's looting does not, so enough of them in a row that
				# agree replace what the gait knew.
				if _unconfirmed_gait != _previous_step_gait:
					_unconfirmed_paces.clear()
					_unconfirmed_gait = _previous_step_gait
				_unconfirmed_paces.append(gap_pace)
				if confirms_new_pace(_unconfirmed_paces):
					history = _unconfirmed_paces.slice(
						_unconfirmed_paces.size() - PACE_CONFIRM_STEPS)
					_unconfirmed_paces.clear()
			else:
				_unconfirmed_paces.clear()
				history.append(gap_pace)
				if history.size() > PACE_WINDOW:
					history = history.slice(history.size() - PACE_WINDOW)
			_pace_histories[_previous_step_gait] = history
			_smoothed_server_interval = _pace_for_gait(_previous_step_gait)
			# How late this step was against the cadence, if it was. The
			# allowance keeps the worst of it for a while, so the steps after a
			# hold are scheduled far enough behind their packets that the next
			# hold of the same size lands before the body needs the tile. A gap
			# long enough to be a player pausing earns nothing.
			var expected_gap: float = _smoothed_server_interval * gap_tiles
			var lateness: float = observed_interval - expected_gap
			_jitter_allowance = jitter_allowance(_jitter_allowance,
				0.0 if standing or is_pause_gap(observed_interval, expected_gap) else lateness,
				JITTER_DECAY, maximum_buffer_seconds)
		# The arriving step is held for its own gait's length, so that is the
		# pace it is shown at: #run and #walk change it on the step they apply
		# to rather than after half a window of steps has outvoted the other.
		var gait: int = pace_gait(facing_command, _hastened)
		_smoothed_server_interval = _pace_for_gait(gait)
		# A hasted run covers 10 m/s on metre tiles, beyond the nominal 9 m/s
		# presentation limit. The limit must accommodate the measured cadence
		# and its bounded catch-up, or lag grows until the teleport guard fires.
		_presentation_speed = maxf(_presentation_speed,
			_metres_per_tile / maxf(_smoothed_server_interval, 0.001)
			* maxf(catch_up_factor, 1.0))
		_last_movement_update_msec = now_msec
		_previous_step_tiles = step_tiles
		_previous_step_gait = gait
		_segment_start = global_position
		_segment_elapsed = 0.0
		_movement_coast_remaining = 0.0
		# The server holds this step for its own length before the next one,
		# so the schedule continues by that much: the body crosses the tile
		# at one speed on the ground whatever shape the step is.
		var cadence: float = _smoothed_server_interval * step_tiles
		# When this step should finish: on the schedule the last one set, at
		# the pace the server is sending, or later if the packet came too late
		# for that. The body is given exactly that long to cross from wherever
		# it is to the new tile, so a late packet costs nothing but a shorter
		# buffer and an early one nothing but a longer one - neither changes
		# the speed on the ground. Restarting each step from the body's
		# position at the arrival margin, as this used to, made a late packet
		# a stop and the early one behind it a sprint.
		var due: float
		if stamped:
			due = ServerTimePacing.due_seconds(now, _schedule_due, cadence,
				float(dto.get(ServerTimePacing.PLAYOUT_KEY, 0.0)))
		else:
			due = scheduled_arrival(now, _schedule_due, cadence,
				cadence * arrival_margin + _jitter_allowance, catch_up_factor)
		# A server-confirmed fast mount can cross a tile faster than the
		# ordinary segment floor. Keep its short steps on the supplied cadence.
		var segment_floor := minf(minimum_segment_duration, cadence) if is_instance_valid(_mount_visual) else minimum_segment_duration
		var clock_now: float = float(clock_msec) / 1000.0
		_segment_duration = clampf(maxf(due - clock_now,
			global_position.distance_to(server_target) / maxf(_presentation_speed, 0.001)),
			segment_floor, maximum_segment_duration + maximum_buffer_seconds)
		_schedule_due = clock_now + _segment_duration
		_travel_yaw = travel_yaw(_segment_start, server_target, _target_yaw)
		_travel_yaw_active = true
	_wake()
	# Loadout changes in this packet must choose the right strike immediately.
	apply_equipment_visuals(dto.get("equipment_visuals", {}) as Dictionary,
		dto.get("equipment_fallback_parts", []) as Array)
	if dto.has("command") and resolver != null:
		var action := _movement_aware_action(
			_paced_travel_action(resolver.action_for_command(actor_command, _in_combat)), target_changed)
		# Health/equipment/aim updates restate the last command. Replaying it
		# can repeat a completed sit/stand transition or interrupt an emote.
		# Only a new command, movement or combat change may change the action;
		# records without command sequences retain their legacy behavior.
		var transient := current_action in [&"cast", &"cast_channel_enter", &"cast_channel",
			&"cast_aggressive", &"cast_defensive", &"heal", &"cast_exit", &"ranged_draw",
			&"ranged_hold", &"ranged_attack", &"attack_primary", &"attack_secondary", &"pain"]
		var stale_strike := command_sequence >= 0 and not fresh_command and action in [&"attack_primary", &"pain"]
		if not stale_strike and (fresh_command or target_changed
				or (not transient and (combat_changed or command_sequence < 0)) or action == &"death"):
			if action == &"attack_primary" and fresh_command and resolver.action_to_clip.has("attack_secondary"):
				action = &"attack_primary" if _swing_index % 2 == 0 else &"attack_secondary"
				_swing_index += 1
			play_action(action, fresh_command and action in [&"attack_primary", &"attack_secondary", &"pain"])
	var aiming: bool = int(dto.get("aiming_at", -1)) >= 0 or dto.get("aiming_at_tile") is Vector2i
	if aiming != _ranged_aiming and current_action != &"death":
		_ranged_aiming = aiming
		if aiming:
			play_action(&"ranged_draw")
		elif current_action in [&"ranged_draw", &"ranged_hold"]:
			play_action(&"combat_idle" if _in_combat else &"idle")
	if current_action == &"death":
		_segment_duration = 0.0
		_movement_coast_remaining = 0.0
		_travel_yaw_active = false

func _apply_server_state_native(dto: Dictionary, adapter: CoordinateAdapter, teleport := false) -> void:
	# A revived body starts a new movement stream at its respawn tile. Do
	# not interpolate from its corpse or retain the old step schedule.
	teleport = teleport or (current_action == &"death"
		and int(dto.get("health", 0)) > 0 and bool(dto.get("alive", true)))
	if teleport and _charge_leap != null: end_charge_leap()
	_sync_death_presentation(dto)
	# A guild refresh removes and re-adds the actor in one socket read. Main
	# coalesces that into an update of the existing body, including its label.
	if dto.has("name") and is_instance_valid(_nameplate):
		var next_name_info := _name_info(dto)
		if _name_dto != next_name_info:
			_name_dto = next_name_info
			_sync_nameplate_text()
			_layout_overhead()
	set_status_effects(dto.get("status_effects", dto.get("negative_statuses", [])))
	# The capability handshake can correct an actor already spawned from the
	# legacy clothing bytes. Update its dyes once, including under worn armour.
	if dto.has("appearance") and dto.appearance != _appearance:
		apply_appearance_variants(dto.appearance as Dictionary)
	if not is_equal_approx(_metres_per_tile, adapter.metres_per_tile):
		_metres_per_tile = maxf(0.01, adapter.metres_per_tile)
		_resize_selection()
	if dto.has("footprint"):
		set_footprint(dto.get("footprint") as Vector2i)
	if dto.has("scale"):
		set_server_scale(float(dto.get("scale")))
	var motion := _apply_server_motion(dto, adapter, teleport)
	var target_changed: bool = motion.target_changed
	var actor_command: int = motion.actor_command
	var combat_changed: bool = motion.combat_changed
	var fresh_command: bool = motion.fresh_command
	var command_sequence: int = motion.command_sequence
	# Loadout changes in this packet must choose the right strike immediately.
	apply_equipment_visuals(dto.get("equipment_visuals", {}) as Dictionary,
		dto.get("equipment_fallback_parts", []) as Array)
	if dto.has("command") and resolver != null:
		var service = RemotePresentationService.current()
		var native_handled := false
		if service != null and service.owns(self):
			native_handled = service.choose_action(self, resolver.action_for_command(actor_command, _in_combat),
				target_changed, combat_changed, fresh_command, command_sequence,
				resolver.action_to_clip.has("attack_secondary"))
		if not native_handled:
			var action := _movement_aware_action(
				_paced_travel_action(resolver.action_for_command(actor_command, _in_combat)), target_changed)
			# Health/equipment/aim updates restate the last command. Replaying it
			# can repeat a completed sit/stand transition or interrupt an emote.
			# Only a new command, movement or combat change may change the action;
			# records without command sequences retain their legacy behavior.
			var transient := current_action in [&"cast", &"cast_channel_enter", &"cast_channel",
				&"cast_aggressive", &"cast_defensive", &"heal", &"cast_exit", &"ranged_draw",
				&"ranged_hold", &"ranged_attack", &"attack_primary", &"attack_secondary", &"pain"]
			var stale_strike := command_sequence >= 0 and not fresh_command and action in [&"attack_primary", &"pain"]
			if not stale_strike and (fresh_command or target_changed
					or (not transient and (combat_changed or command_sequence < 0)) or action == &"death"):
				if action == &"attack_primary" and fresh_command and resolver.action_to_clip.has("attack_secondary"):
					action = &"attack_primary" if _swing_index % 2 == 0 else &"attack_secondary"
					_swing_index += 1
				play_action(action, fresh_command and action in [&"attack_primary", &"attack_secondary", &"pain"])
	var aiming: bool = int(dto.get("aiming_at", -1)) >= 0 or dto.get("aiming_at_tile") is Vector2i
	if aiming != _ranged_aiming and current_action != &"death":
		_ranged_aiming = aiming
		if aiming:
			play_action(&"ranged_draw")
		elif current_action in [&"ranged_draw", &"ranged_hold"]:
			play_action(&"combat_idle" if _in_combat else &"idle")
	if current_action == &"death":
		_segment_duration = 0.0
		_movement_coast_remaining = 0.0
		_travel_yaw_active = false
	var remote = RemotePresentationService.current()
	if remote != null: remote.sync_sink(self)

func _apply_server_motion(dto: Dictionary, adapter: CoordinateAdapter, teleport: bool) -> Dictionary:
	var service = RemotePresentationService.current()
	if service != null:
		var native: Dictionary = service.motion(self, dto, adapter, teleport)
		if not native.is_empty(): return native
	var next_target: Vector3 = adapter.footprint_center(
		int(dto.x), int(dto.y), footprint)
	# Server movement contains tile coordinates only. Keep the last sampled
	# rendered-surface height until Main performs the ray sample for the new tile;
	# otherwise each packet temporarily pushes actors back to the flat manifest
	# fallback and can leave them visibly embedded in sculpted terrain.
	next_target.y = server_target.y
	var target_changed: bool = server_target.distance_squared_to(next_target) > 0.000001
	# Where the server had this actor before this update. The step it just took
	# is that far, which is what the pace below is measured and spent against -
	# not the distance from the rendered body, which trails by the arrival
	# margin and would feed its own lag back into the pacing.
	var previous_target: Vector3 = server_target
	server_target = next_target
	var actor_command: int = int(dto.get("command", -1))
	var combat_changed: bool = bool(dto.get("in_combat", _in_combat)) != _in_combat
	_in_combat = bool(dto.get("in_combat", _in_combat))
	var command_sequence := int(dto.get("command_sequence", -1))
	var fresh_command := command_sequence != _last_command_sequence
	_last_command_sequence = command_sequence
	# Combat interrupts the movement stream. Its duration is not a step
	# interval, and the network buffer from the approach must not slow the
	# short move onto the bag. Keep learned gaits and any step still rendering;
	# only the next step's timing starts afresh. Explicit transition commands
	# also cover entering and leaving combat within one reduced update.
	if combat_changed or (fresh_command and actor_command in [18, 19]):
		_last_movement_update_msec = -1
		_unconfirmed_paces.clear()
		_unconfirmed_gait = -1
		_jitter_allowance = 0.0
		_schedule_due = -1.0
	# Which command the facing comes from, and which it does not. Everything
	# arriving in one socket read is reduced to a single state and rendered
	# once, so the last command of a frame is rarely the one that named a
	# direction: a creature sends the turn that puts it on its target and the
	# swing that follows it in the same flush, and reading the facing off the
	# last command threw the turn away every round. The reducer keeps the last
	# directional command of the burst apart for exactly this.
	var facing_command: int = int(dto.get("facing_command", actor_command))
	# The server has answered a predicted turn. Drop the prediction so the
	# rendered facing is the authoritative one from here on.
	if _predicted_turn_pending and EloriaProtocol.is_turn_command(facing_command):
		_predicted_turn_pending = false
	var authoritative_yaw: float = target_yaw_for_state(
		_target_yaw, facing_command, int(dto.rotation), adapter)
	_target_yaw = _predicted_turn_yaw if _predicted_turn_pending else authoritative_yaw
	_hastened = (int(dto.get("buffs", 0))
		& EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED) != 0 or "haste" in _status_effects
	_presentation_speed = walk_presentation_speed
	if _hastened or (actor_command >= 30 and actor_command <= 37):
		_presentation_speed = run_presentation_speed
	# A delayed creature burst can cover several tiles. Present its recovery
	# continuously; only an explicit relocation or an out-of-view correction snaps.
	if teleport or global_position.distance_to(server_target) > (64.0 if _is_creature else 8.0):
		global_position = server_target
		rotation.y = _target_yaw
		_segment_start = server_target
		_segment_elapsed = 0.0
		_segment_duration = 0.0
		_last_movement_update_msec = -1
		_pace_histories.clear()
		_smoothed_server_interval = _pace_for_gait(pace_gait(facing_command, _hastened))
		_unconfirmed_paces.clear()
		_unconfirmed_gait = -1
		_jitter_allowance = 0.0
		_schedule_due = -1.0
		_previous_step_tiles = 1.0
		_previous_step_gait = pace_gait(facing_command, _hastened)
		_movement_coast_remaining = 0.0
		_snap_pending = false
		_travel_yaw_active = false
	elif target_changed:
		# A step the server stamped with its own clock is timed by when it was
		# taken (server_time_pacing.gd); any other by when it arrived.
		var clock_msec: int = _movement_time_msec()
		var stamped: bool = dto.has(ServerTimePacing.STEP_KEY)
		var now_msec: int = int(dto[ServerTimePacing.STEP_KEY]) if stamped else clock_msec
		var now: float = float(now_msec) / 1000.0
		# How much ground the server covered, in tiles. A diagonal step is 1.41
		# of them and a folded burst several, so timing the update against it
		# gives a pace per tile that every step shape agrees on. Timing it
		# against the step count instead read a diagonal as a short interval
		# and rendered it 41% faster than the straight step beside it, which is
		# what walking and running at an uneven speed was.
		var step_tiles: float = maxf(
			previous_target.distance_to(server_target) / _metres_per_tile, 0.001)
		if _last_movement_update_msec >= 0:
			var observed_interval: float = float(
				now_msec - _last_movement_update_msec) / 1000.0
			# The gap before this packet is the hold the server gave the step
			# before it, so it is measured per tile of that step.
			var gap_tiles: float = maxf(_previous_step_tiles, 0.001)
			var gap_pace: float = maxf(observed_interval / gap_tiles, 0.05)
			var history: PackedFloat32Array = _pace_histories.get(
				_previous_step_gait, PackedFloat32Array())
			# A stationary pause is idle time, not a cadence. Folding it in
			# paced the next burst by how long the player stood still: a few
			# single steps from bag to bag with a second's looting between them
			# were enough to make the median a second a tile, and the run after
			# them crawled for its first steps while the body fell tiles behind.
			# A pause is told from the cadence by the same lateness a network
			# hold is allowed, against the pace this gait has already shown, so
			# it is only ever judged against steps of its own kind - #walk after
			# #run is a different history, not a late step. A gait still being
			# learned has nothing to judge against and takes what it is given,
			# short of a gap longer than any step the server holds.
			var idle: bool = gap_pace > maximum_segment_duration
			var standing: bool = idle
			if not standing and history.size() >= PACE_MINIMUM_REFERENCE:
				standing = is_pause_gap(observed_interval,
					median_of(history, _smoothed_server_interval) * gap_tiles)
			if idle:
				_unconfirmed_paces.clear()
			elif standing:
				# Pauses are not a cadence, but a pace that really has slowed -
				# a creature back from a pursuit to its ordinary walk - looks
				# like one pause after another. Those agree with each other and
				# a player's looting does not, so enough of them in a row that
				# agree replace what the gait knew.
				if _unconfirmed_gait != _previous_step_gait:
					_unconfirmed_paces.clear()
					_unconfirmed_gait = _previous_step_gait
				_unconfirmed_paces.append(gap_pace)
				if confirms_new_pace(_unconfirmed_paces):
					history = _unconfirmed_paces.slice(
						_unconfirmed_paces.size() - PACE_CONFIRM_STEPS)
					_unconfirmed_paces.clear()
			else:
				_unconfirmed_paces.clear()
				history.append(gap_pace)
				if history.size() > PACE_WINDOW:
					history = history.slice(history.size() - PACE_WINDOW)
			_pace_histories[_previous_step_gait] = history
			_smoothed_server_interval = _pace_for_gait(_previous_step_gait)
			# How late this step was against the cadence, if it was. The
			# allowance keeps the worst of it for a while, so the steps after a
			# hold are scheduled far enough behind their packets that the next
			# hold of the same size lands before the body needs the tile. A gap
			# long enough to be a player pausing earns nothing.
			var expected_gap: float = _smoothed_server_interval * gap_tiles
			var lateness: float = observed_interval - expected_gap
			_jitter_allowance = jitter_allowance(_jitter_allowance,
				0.0 if standing or is_pause_gap(observed_interval, expected_gap) else lateness,
				JITTER_DECAY, maximum_buffer_seconds)
		# The arriving step is held for its own gait's length, so that is the
		# pace it is shown at: #run and #walk change it on the step they apply
		# to rather than after half a window of steps has outvoted the other.
		var gait: int = pace_gait(facing_command, _hastened)
		_smoothed_server_interval = _pace_for_gait(gait)
		# A hasted run covers 10 m/s on metre tiles, beyond the nominal 9 m/s
		# presentation limit. The limit must accommodate the measured cadence
		# and its bounded catch-up, or lag grows until the teleport guard fires.
		_presentation_speed = maxf(_presentation_speed,
			_metres_per_tile / maxf(_smoothed_server_interval, 0.001)
			* maxf(catch_up_factor, 1.0))
		_last_movement_update_msec = now_msec
		_previous_step_tiles = step_tiles
		_previous_step_gait = gait
		_segment_start = global_position
		_segment_elapsed = 0.0
		_movement_coast_remaining = 0.0
		# The server holds this step for its own length before the next one,
		# so the schedule continues by that much: the body crosses the tile
		# at one speed on the ground whatever shape the step is.
		var cadence: float = _smoothed_server_interval * step_tiles
		# When this step should finish: on the schedule the last one set, at
		# the pace the server is sending, or later if the packet came too late
		# for that. The body is given exactly that long to cross from wherever
		# it is to the new tile, so a late packet costs nothing but a shorter
		# buffer and an early one nothing but a longer one - neither changes
		# the speed on the ground. Restarting each step from the body's
		# position at the arrival margin, as this used to, made a late packet
		# a stop and the early one behind it a sprint.
		var due: float
		if stamped:
			due = ServerTimePacing.due_seconds(now, _schedule_due, cadence,
				float(dto.get(ServerTimePacing.PLAYOUT_KEY, 0.0)))
		else:
			due = scheduled_arrival(now, _schedule_due, cadence,
				cadence * arrival_margin + _jitter_allowance, catch_up_factor)
		# A server-confirmed fast mount can cross a tile faster than the
		# ordinary segment floor. Keep its short steps on the supplied cadence.
		var segment_floor := minf(minimum_segment_duration, cadence) if is_instance_valid(_mount_visual) else minimum_segment_duration
		var clock_now: float = float(clock_msec) / 1000.0
		_segment_duration = clampf(maxf(due - clock_now,
			global_position.distance_to(server_target) / maxf(_presentation_speed, 0.001)),
			segment_floor, maximum_segment_duration + maximum_buffer_seconds)
		_schedule_due = clock_now + _segment_duration
		_travel_yaw = travel_yaw(_segment_start, server_target, _target_yaw)
		_travel_yaw_active = true
	_wake()
	return {"target_changed": target_changed, "actor_command": actor_command,
		"combat_changed": combat_changed, "fresh_command": fresh_command,
		"command_sequence": command_sequence}

func _sync_death_presentation(dto: Dictionary) -> void:
	if not dto.has("health"):
		return
	collision_layer = 0 if _crowd_hidden or (_is_creature and (int(dto.health) <= 0 or not bool(dto.get("alive", true)))) else 2
	if int(dto.health) > 0 and bool(dto.get("alive", true)):
		if current_action == &"death":
			current_action = &"idle"
			_sync_selection_marker()
			_death_finished = false
			_death_elapsed = 0.0
			_death_animation_seconds = 0.0
			_death_snapshot_msec = -1
			_corpse_temporary = false
			if _corpse_dissolve != null:
				_corpse_dissolve.reset()
				_corpse_dissolve = null
				_corpse_geometry.clear()
			_set_corpse_transparency(0.0)
			play_action(&"idle", true)
			_refresh_stand_in()
		return
	var snapshot: Dictionary = dto.get("death_presentation", {})
	_death_animation_seconds = float(snapshot.get("animation_seconds", 0.0))
	_corpse_temporary = bool(snapshot.get("temporary", false))
	_corpse_hold_seconds = float(snapshot.get("hold_seconds", 3.0))
	_corpse_fade_seconds = maxf(0.01, float(snapshot.get("fade_seconds", 4.0)))
	play_action(&"death")
	var received := int(snapshot.get("received_msec", -1))
	if received >= 0 and received != _death_snapshot_msec:
		_death_snapshot_msec = received
		_death_elapsed = maxf(_death_elapsed, float(snapshot.get("elapsed", 0.0))
			+ float(Time.get_ticks_msec() - received) / 1000.0)
		if animation_player != null and resolver != null:
			var clip := resolver.clip_for_action(&"death")
			if animation_player.has_animation(clip):
				animation_player.speed_scale = _playback_speed_for(&"death")
				animation_player.seek(minf(_death_elapsed * animation_player.speed_scale,
					animation_player.get_animation(clip).length), true)
	_update_corpse_pose()
	set_process(true)

func death_animation_finished() -> bool:
	return current_action == &"death" and _death_finished

func _death_duration() -> float:
	return _death_animation_seconds if _death_animation_seconds > 0.0 else cinematic_action_duration(&"death")

func _hold_death_pose() -> void:
	_death_finished = true
	if animation_player != null and resolver != null:
		var clip := resolver.clip_for_action(&"death")
		if animation_player.has_animation(clip):
			animation_player.seek(animation_player.get_animation(clip).length, true)
			animation_player.pause()

func _update_corpse_pose() -> void:
	if not _death_finished and _death_elapsed >= _death_duration():
		_hold_death_pose()
	if _corpse_temporary or _is_creature:
		# Temporary bodies dissolve two seconds after their clip ends. The
		# server can retain the hidden corpse until its existing cleanup time.
		var hold_seconds := CREATURE_DISSOLVE_DELAY_SECONDS if _is_creature and _corpse_temporary else _corpse_hold_seconds
		var fade := clampf((_death_elapsed - _death_duration() - hold_seconds)
			/ _corpse_fade_seconds, 0.0, 1.0)
		if _is_creature and _corpse_temporary and fade > 0.0:
			if _corpse_dissolve == null and fade < 1.0:
				_corpse_dissolve = CREATURE_DISSOLVE.new()
				_corpse_dissolve.begin(self, _corpse_fade_seconds, actor_id)
			if _corpse_dissolve != null:
				_corpse_dissolve.update(fade)
			# The body is cut into opaque patches instead of fading as a whole.
			_set_corpse_transparency(1.0 if fade >= 1.0 else 0.0)
		else:
			_set_corpse_transparency(fade)
		if fade >= 1.0: set_process(false)

func _set_corpse_transparency(amount: float) -> void:
	if is_equal_approx(_corpse_transparency, amount):
		return
	_corpse_transparency = amount
	if _corpse_geometry.is_empty():
		for node: Node in find_children("*", "GeometryInstance3D", true, false):
			_corpse_geometry.append(node as GeometryInstance3D)
	for geometry: GeometryInstance3D in _corpse_geometry:
		if is_instance_valid(geometry):
			geometry.transparency = amount

func _process(delta: float) -> void:
	if current_action != &"death":
		set_process(false)
		return
	_death_elapsed += delta
	_update_corpse_pose()
	if _death_finished and not _corpse_temporary and not _is_creature:
		set_process(false)

## Resting commands can arrive before the body finishes its buffered step,
## including combat ending on the way to a dropped bag. Keep the step's gait
## until arrival, even when the last command in a reduced burst names idle.
## Conversely, a restated movement command must not restart a finished step.
func _movement_aware_action(action: StringName,
		target_changed: bool) -> StringName:
	if _segment_duration > 0.0 and action in [&"idle", &"combat_idle", &"turn"]:
		return _paced_travel_action(&"run" if _previous_step_gait & 1 else &"walk")
	if action not in [&"walk", &"run"]:
		return action
	if target_changed or _segment_duration > 0.0 or _movement_coast_remaining > 0.0:
		return action
	return &"idle"

## Walking is the ordinary pace, so the walk commands the server sends for every
## step resolve to the walk clip. Speed Hax is what makes an actor run: it halves
## the server's move interval without ever naming a run command, so the buff -
## not the command - is what promotes the travel action to a run.
func _paced_travel_action(action: StringName) -> StringName:
	if _hastened and action == &"walk":
		return &"run"
	if _is_creature and action == &"walk" and resolver != null:
		var scale := _small_creature_scale * server_scale
		var walk := resolver.stride_speed_for_action(&"walk", scale)
		var run := resolver.stride_speed_for_action(&"run", scale)
		if walk > 0 and run > walk and _travel_speed() > walk * 1.8:
			return &"run"
	return action

func apply_equipment_visuals(visuals: Dictionary, fallback_parts: Array = []) -> void:
	# Every actor packet restates the whole wardrobe, and almost none of them
	# change it: a crowd walking past asked for the clothes it was already
	# wearing on every step. Everything below reconciles what is worn against
	# what was asked for and skips each part that already agrees, so a request
	# that matches in full does nothing but walk the model's meshes again in
	# `_refresh_wardrobe_cover`, which reads only state this function writes.
	# The first pass always runs, so nothing an actor is built with is skipped.
	# A deferred actor has nothing to dress: its replacement is built from the
	# record as it stands then, wardrobe included.
	if _model_deferred:
		return
	if _equipment_applied and _equipment_matches(visuals, fallback_parts):
		return
	_equipment_applied = true
	var torso_before: int = int(_equipment_visuals.get(BODY_PART, 0))
	var shins_before := Vector2i(int(_equipment_visuals.get(LEGS_PART, 0)),
		int(_equipment_visuals.get(BOOTS_PART, 0)))
	for raw_part: Variant in _equipment_visuals.keys():
		var old_part: int = int(raw_part)
		if not visuals.has(old_part) and not visuals.has(str(old_part)):
			_clear_equipment_part(old_part)
	# The torso goes on first. It is the one part another is cut against - the
	# cape is draped over whatever armour is worn - so a cape built before it
	# would be cut against the armour being taken off.
	var order: Array = []
	for raw_part: Variant in visuals:
		if int(raw_part) == BODY_PART:
			order.push_front(raw_part)
		else:
			order.append(raw_part)
	var cape_rebuilt := false
	for raw_part: Variant in order:
		var part: int = int(raw_part)
		var visual_id: int = int(visuals[raw_part])
		var allow_fallback: bool = fallback_parts.has(part)
		if int(_equipment_visuals.get(part, -1)) == visual_id and (
				not allow_fallback or _equipment_nodes.has(part)):
			continue
		_clear_equipment_part(part)
		_equipment_visuals[part] = visual_id
		_create_equipment_part(part, visual_id, allow_fallback)
		cape_rebuilt = cape_rebuilt or part == CAPE_PART
	# A cape kept from before still hangs on the armour it was cut against, so
	# a change of chest piece re-cuts it even though the cape itself did not
	# change. One rebuilt in the loop above was already cut against the new
	# torso, which went on first.
	if int(_equipment_visuals.get(BODY_PART, 0)) != torso_before and (
			not cape_rebuilt) and _equipment_nodes.has(CAPE_PART):
		var cape_visual: int = int(_equipment_visuals.get(CAPE_PART, 0))
		_clear_equipment_part(CAPE_PART)
		_equipment_visuals[CAPE_PART] = cape_visual
		_create_equipment_part(CAPE_PART, cape_visual,
			fallback_parts.has(CAPE_PART))
	# The hem is kept off whatever is worn on the shins, so new trousers or
	# boots are news to the cloth, whenever they went on relative to the cape.
	if _equipment_nodes.has(CAPE_PART) and shins_before != Vector2i(
			int(_equipment_visuals.get(LEGS_PART, 0)),
			int(_equipment_visuals.get(BOOTS_PART, 0))):
		_tell_cloth_what_is_worn()
	_refresh_wardrobe_cover()
	_refresh_melee_animation_mapping()
	_refresh_quiver_cape_fit()
	if _weapon_carry != null:
		_weapon_carry.call("refresh_equipment")
	if combat_presentation != null:
		var weapon := _equipment_model_config(0, int(_equipment_visuals.get(0, 0)))
		var bow_path := _ranged_bow_path(weapon)
		combat_presentation.set_equipped_bow(bow_path)
	# Equipment adds and removes mesh instances, so the silhouette's clone set
	# has to be built again against what the actor is now made of.
	if _silhouette != null and _silhouette.is_enabled():
		_silhouette.rebuild()
	_apply_render_quality_to_visuals()
	if is_instance_valid(_native_model):
		OLDCRAFT_ACTOR_STYLE.apply_surface_finish(_native_model)

## The quiver carries authored cape-on and cape-off fits on the same skin.
## Changing one actor's morph weight leaves shared meshes and other wearers alone.
func _refresh_quiver_cape_fit() -> void:
	var cape_worn := false
	var layers: Array = []
	layers.append_array(_equipment_nodes.get(BODY_PART, []))
	layers.append_array(_equipment_nodes.get(CAPE_PART, []))
	var outfit_key := "%s|%s|%s" % [str(_model_config.get("scene", "")),
		_worn_torso_scene(), _worn_skinned_scene(CAPE_PART)]
	for node: Node in _equipment_nodes.get(CAPE_PART, []):
		if node is MeshInstance3D:
			cape_worn = true
			break
	for node: Node in _equipment_nodes.get(QUIVER_PART, []):
		if not node is MeshInstance3D:
			continue
		var quiver := node as MeshInstance3D
		QUIVER_STRAP_FIT.apply(quiver, layers, _native_skeleton, outfit_key)
		var shape := quiver.find_blend_shape_by_name("Cape_Clearance")
		if shape >= 0:
			quiver.set_blend_shape_value(shape, 1.0 if cape_worn else 0.0)

func _refresh_melee_animation_mapping() -> void:
	if resolver == null or not resolver.melee_styles.has("unarmed"):
		return
	var style: Dictionary = (resolver.melee_styles["unarmed"]
		if int(_equipment_visuals.get(0, 0)) <= 0 else _default_melee_clips)
	for action: Variant in _default_melee_clips:
		resolver.action_to_clip[action] = style.get(action, _default_melee_clips[action])

## Whether `visuals` asks for exactly what is already worn. The part loop's own
## skip condition, taken over the whole request: the same visual id for every
## part, no part left over on either side, and a part the server offered a
## fallback for already carrying its nodes.
func _equipment_matches(visuals: Dictionary, fallback_parts: Array) -> bool:
	if visuals.size() != _equipment_visuals.size():
		return false
	for raw_part: Variant in visuals:
		var part: int = int(raw_part)
		if int(_equipment_visuals.get(part, -1)) != int(visuals[raw_part]):
			return false
		if fallback_parts.has(part) and not _equipment_nodes.has(part):
			return false
	return true

func equipment_diagnostics() -> Dictionary:
	# Modified 2026-08-28 for Eloria Client: garments are now skinned to this
	# actor's skeleton rather than parented to a bone, so the two attachment
	# paths are reported separately and a regression in either one is visible.
	var native_count: int = 0
	var fallback_count: int = 0
	var skinned_count: int = 0
	var socket_count: int = 0
	for nodes_value: Variant in _equipment_nodes.values():
		for node_value: Variant in nodes_value:
			var node: Node = node_value as Node
			if not is_instance_valid(node):
				continue
			if node.has_meta("native_equipment"):
				native_count += 1
				if node is MeshInstance3D:
					skinned_count += 1
				else:
					socket_count += 1
			else:
				fallback_count += 1
	return {"visuals": _equipment_visuals.duplicate(), "native": native_count,
		"fallback": fallback_count, "skinned": skinned_count,
		"socket": socket_count, "rigFitScale": rig_fit_scale()}

func _clear_equipment_part(part: int) -> void:
	if part == 0:
		_trail_weapon_mesh = null
		_invalidate_hand_prop_ranged_cache()
	var nodes_value: Variant = _equipment_nodes.get(part, [])
	if nodes_value is Array:
		for node_value: Variant in nodes_value:
			var node: Node = node_value as Node
			if is_instance_valid(node):
				node.queue_free()
	_equipment_nodes.erase(part)
	_equipment_visuals.erase(part)
	_release_equipment_hides(part)
	if part == CAPE_PART:
		_set_cape_cloth_active(false)

func _create_equipment_part(part: int, visual_id: int, allow_fallback: bool) -> void:
	# Modified 2026-08-28 for Eloria Client: equipment used to be parented to a
	# raw bone with an identity transform.  Bone rest bases are not axis aligned,
	# so every hilt left the hand sideways, and a rigid child of one bone could
	# never follow the spine or the knees.  Props now resolve a character-space
	# socket through the bone rest, and garments rebind to this actor's skeleton.
	if _native_skeleton == null:
		return
	var parts: Dictionary = _equipment_config.get("parts", {}) as Dictionary
	var part_config: Dictionary = parts.get(str(part), {}) as Dictionary
	if part_config.is_empty():
		return
	# Visual 0 is "nothing equipped".  On a wardrobe slot that used to mean a
	# generic shirt, pants or boots, because the shipped bodies were nude
	# under their Wardrobe_* meshes.  The race bodies now carry their clothing
	# in their own texture, so an empty slot is the body itself -- and drawing
	# the generic garment would put a second set of clothes over a painted one.
	# Marked per part in equipment.json, so a slot that must always show
	# something is unaffected.  Returning here also skips the fallback: bare is
	# the intended result, not a missing model.
	if visual_id == 0 and bool(part_config.get("bareWhenEmpty", false)):
		return
	var model_config: Dictionary = _equipment_model_config(part, visual_id)
	if ARCHIVED_MODEL_POLICY.is_retired_equipment(part, visual_id) or bool(model_config.get("retired", false)):
		# Reserve the visual ID and lifecycle slot without a generated fallback.
		var marker := Node3D.new()
		marker.name = "RetiredEquipment_%d_%d" % [part, visual_id]
		marker.set_meta("native_equipment", true)
		marker.set_meta("retired_equipment", true)
		_native_skeleton.add_child(marker)
		_equipment_nodes[part] = [marker]
		return
	if part == 0:
		_hand_prop_weapon_has_ranged_animation = not _ranged_bow_path(model_config).is_empty()
		_hand_prop_ranged_cache_valid = true
	if str(model_config.get("attach", "")) == "ranged_bow" and combat_presentation != null:
		# The presentation follows both hands; ordinary equipment follows one socket.
		return
	var created: Array[Node] = []
	if not model_config.is_empty():
		var scene_path: String = str(model_config.get("scene", ""))
		if bool(model_config.get("wardrobeOnly", false)):
			# Starter looks can deliberately use the actor's own fitted wardrobe
			# instead of drawing a second skinned torso.  A lightweight marker keeps
			# the ordinary equipment lifecycle and diagnostics intact without adding
			# another mesh or skin to every actor in a crowded scene.
			var marker := Node3D.new()
			marker.name = "WardrobeVisual_%d_%d" % [part, visual_id]
			marker.set_meta("native_equipment", true)
			marker.set_meta("wardrobe_only", true)
			_native_skeleton.add_child(marker)
			created.append(marker)
		elif str(model_config.get("attach", "socket")) == "skinned":
			created.append_array(_attach_skinned_equipment(scene_path, part, visual_id,
				model_config.get("tint", []) as Array,
				str(model_config.get("authoredFor", "")),
				str(model_config.get("skinRegion", "")),
				str(model_config.get("fitProfile", "")),
				bool(model_config.get("suppressGeneratedBacking", false))))
		else:
			var socket: Dictionary = _equipment_socket(part, model_config)
			var attachment: BoneAttachment3D = _attach_socketed_equipment(
				socket, scene_path, model_config, part, visual_id)
			if attachment != null:
				created.append(attachment)
	if created.is_empty() and allow_fallback:
		created.append_array(_attach_fallback_equipment(part, visual_id, part_config))
	if created.is_empty():
		_equipment_nodes.erase(part)
	else:
		_equipment_nodes[part] = created
		_apply_equipment_hides(part, part_config, model_config)
	if part == CAPE_PART:
		for node: Node in created:
			if node is MeshInstance3D:
				CapeEmblems.apply(node as MeshInstance3D, str(model_config.get("emblem", "")))
		_set_cape_cloth_active(not created.is_empty())

## The scene of the torso piece this actor is wearing, or "" when the chest is
## bare. A bare chest needs no drape: the capes were conformed against the bare
## back offline and already clear it.
func _worn_torso_scene() -> String:
	return _worn_skinned_scene(BODY_PART)

## The skinned scene worn on a part, or "" when nothing is.
func _worn_skinned_scene(part: int) -> String:
	var visual: int = int(_equipment_visuals.get(part, 0))
	if visual == 0:
		return ""
	var model: Dictionary = _equipment_model_config(part, visual)
	if bool(model.get("wardrobeOnly", false)):
		return ""
	if str(model.get("attach", "socket")) != "skinned":
		return ""
	return str(model.get("scene", ""))

## One cape surface, cut to clear the torso worn under it. The mesh itself
## when nothing is worn there, or when nothing on it had to move.
func _draped_over(torso_scene: String, cape_scene: String,
		piece: Dictionary) -> Mesh:
	var mesh: Mesh = piece.get("mesh") as Mesh
	if torso_scene.is_empty() or mesh == null:
		return mesh
	var key: String = "%s|%s|%s" % [cape_scene, torso_scene,
		str(piece.get("name", ""))]
	var cached: Mesh = _draped_capes.get(key) as Mesh
	if cached != null:
		return cached
	# A cut cape is a whole mesh, not a handful of matrices like a rebound
	# skin, so this cache is capped where that one is not: twenty-nine capes
	# against sixty-four torsos would be more geometry than the map it is
	# drawn on. Dropping the lot is fine - it is rebuilt on the next wearer.
	if _draped_capes.size() >= DRAPE_CACHE_LIMIT:
		_draped_capes.clear()
	var grid: PackedFloat32Array = _drape_envelopes.get(torso_scene,
		PackedFloat32Array()) as PackedFloat32Array
	if not _drape_envelopes.has(torso_scene):
		grid = CapeDrape.envelope(_equipment_pieces(torso_scene))
		_drape_envelopes[torso_scene] = grid
	var draped: Mesh = CapeDrape.drape(mesh,
		piece.get("bones", PackedStringArray()) as PackedStringArray, grid)
	_draped_capes[key] = draped
	return draped

## Cloth for the cape chains. A SkeletonModifier3D so the engine runs it once
## the animation has posed the skeleton - writing bone poses from _process
## would race the AnimationPlayer - and inactive, and therefore free, until a
## cape is actually worn.
func _attach_cape_cloth(skeleton: Skeleton3D) -> void:
	if skeleton.find_bone("cape_c_01") < 0:
		return
	if skeleton.get_node_or_null("CapeCloth") != null:
		return
	var cloth: SkeletonModifier3D = (
		load("res://src/actors/cape_cloth.gd") as Script).new()
	cloth.name = "CapeCloth"
	cloth.active = false
	skeleton.add_child(cloth)
	_cape_cloth = cloth

func _set_cape_cloth_active(enabled: bool) -> void:
	_cape_cloth_worn = enabled
	if _cape_cloth == null:
		return
	if enabled:
		_tell_cloth_what_is_worn()
	_refresh_cape_cloth_activity(true)

## Whether this body may simulate its cape at all: in a crowd Main allows it
## for the bodies nearest the camera only (crowd_presentation.gd
## `CLOTH_BODIES`); the rest hang as every non-local cape does below High.
func set_cape_cloth_allowed(allowed: bool) -> void:
	if allowed == _cape_cloth_allowed:
		return
	_cape_cloth_allowed = allowed
	# A cape that slept while its body walked on starts again from rest.
	_refresh_cape_cloth_activity(true)

func cape_cloth_allowed() -> bool:
	return _cape_cloth_allowed

## Whether a cape that can simulate is worn: what the cloth budget ranks.
func wears_cape_cloth() -> bool:
	return _cape_cloth != null and _cape_cloth_worn

func cape_cloth_active() -> bool:
	if is_instance_valid(_mount_visual):
		return bool(_mount_visual.call("cape_simulation_enabled"))
	return _cape_cloth != null and _cape_cloth.active

## The automatic modifier and mounted manual clock consume the same policy.
## The mounted path deliberately keeps the automatic modifier inactive.
func cape_cloth_should_simulate() -> bool:
	return _cape_cloth != null and _cape_cloth_worn and _cape_cloth_allowed \
		and _animation_tier != AnimationGate.Tier.PAUSED \
		and _animation_tier != AnimationGate.Tier.QUARTER \
		and ACTOR_RENDER_QUALITY.cape_enabled(_render_quality, _render_quality_local_actor)

## Cape cloth is enabled only when all four owners agree: equipment says a
## cape is worn, the crowd's cloth budget allows this body, the animation gate
## has not paused this actor, and the actor quality permits cloth for this
## local/non-local role. Re-enabling after a
## quality change resets stale solver points; animation-tier wakes preserve the
## previous behavior and resume them where they slept.
func _refresh_cape_cloth_activity(reset_when_enabled: bool = false) -> void:
	if _cape_cloth == null:
		return
	var enabled := cape_cloth_should_simulate() and not is_instance_valid(_mount_visual)
	if enabled and reset_when_enabled and not _cape_cloth.active:
		_cape_cloth.call("reset")
	_cape_cloth.active = enabled
	if is_instance_valid(_mount_visual):
		_mount_visual.call("refresh_cloth_permission", reset_when_enabled)

## How far the worn torso reaches from each of the solver's capsules. The
## solver knows the skeleton and nothing else; the equipment is only known
## here, and the cape is the one garment whose shape depends on another.
func _tell_cloth_what_is_worn() -> void:
	if _cape_cloth == null or _native_skeleton == null:
		return
	var torso_scene: String = _worn_torso_scene()
	var fabric: Array = _cape_fabric_line(torso_scene)
	_cape_cloth.call("set_fabric_line", fabric[0], fabric[1])
	_cape_cloth.call("set_shin_reach", _shin_reach(torso_scene))
	var empty := PackedFloat32Array()
	if torso_scene.is_empty():
		_cape_cloth.call("set_torso_reach", empty, empty)
		return
	var key: String = "%s|%s" % [str(_model_config.get("scene", "")),
		torso_scene]
	var reach: Array = _torso_reaches.get(key, []) as Array
	if reach.is_empty():
		var pieces: Array = _equipment_pieces(torso_scene)
		reach = [_axis_reach(pieces, "spine_01", "neck_01"),
			_axis_reach(pieces, "pelvis", "spine_01", CapeDrape.SEAT_BELOW)]
		_torso_reaches[key] = reach
	_cape_cloth.call("set_torso_reach", reach[0], reach[1])

## Where the worn cape's cloth hangs behind each of its chains, for the solver
## to hang plumb and to collide. It depends on the rig, the cape and - through
## the drape that holds the yoke out over armour - the torso, so it is shared
## by every actor wearing the three. The line, then the cape's cross-section.
func _cape_fabric_line(torso_scene: String) -> Array:
	var cape: Array = []
	for node_value: Variant in _equipment_nodes.get(CAPE_PART, []) as Array:
		if node_value is MeshInstance3D and is_instance_valid(node_value):
			cape.append(node_value)
	if cape.is_empty():
		return [[], []]
	var visual: int = int(_equipment_visuals.get(CAPE_PART, 0))
	var key: String = "%s|%s|%s" % [str(_model_config.get("scene", "")),
		str(_equipment_model_config(CAPE_PART, visual).get("scene", "")),
		torso_scene]
	if not _fabric_lines.has(key):
		var section: Array = []
		var line: Array = CapeDrape.fabric_line(_native_skeleton, cape, section)
		_fabric_lines[key] = [line, section]
	return _fabric_lines[key] as Array

## How far the legs reach behind each thigh and shin - left thigh, right
## thigh, left shin, right shin, as the cloth takes them: the body's own legs,
## and the trousers, boots and any long coat worn over them. Shared by every
## actor of the rig wearing the same three.
func _shin_reach(torso_scene: String) -> Array:
	var scenes := PackedStringArray([torso_scene, _worn_skinned_scene(LEGS_PART),
		_worn_skinned_scene(BOOTS_PART)])
	var key: String = "%s|%s" % [str(_model_config.get("scene", "")), "|".join(scenes)]
	if not _shin_reaches.has(key):
		var pieces: Array = []
		var native_model := get_node_or_null("NativeModel")
		var body: MeshInstance3D = null
		if native_model != null:
			body = native_model.find_child("body", true, false) as MeshInstance3D
		if body != null and body.mesh != null:
			pieces.append({"mesh": body.mesh})
		for scene: String in scenes:
			if not scene.is_empty():
				pieces.append_array(_equipment_pieces(scene))
		var reaches: Array = []
		for segment: Array in [["thigh", "calf"], ["calf", "foot"]]:
			for side: String in ["l", "r"]:
				var top: int = _native_skeleton.find_bone("%s_%s" % [segment[0], side])
				var bottom: int = _native_skeleton.find_bone("%s_%s" % [segment[1], side])
				reaches.append(PackedFloat32Array() if top < 0 or bottom < 0
					else CapeDrape.shin_reach(pieces,
						_native_skeleton.get_bone_global_rest(top).origin,
						_native_skeleton.get_bone_global_rest(bottom).origin,
						CapeDrape.BARE_SHIN_RADIUS,
						CapeDrape.THIGH_FROM if segment[0] == "thigh" else 0.0))
		_shin_reaches[key] = reaches
	return _shin_reaches[key] as Array

func _axis_reach(pieces: Array, from: String, to: String,
		below: float = 0.0) -> PackedFloat32Array:
	var head: int = _native_skeleton.find_bone(from)
	var tail: int = _native_skeleton.find_bone(to)
	if head < 0 or tail < 0:
		return PackedFloat32Array()
	return CapeDrape.axis_reach(pieces,
		_native_skeleton.get_bone_global_rest(head).origin,
		_native_skeleton.get_bone_global_rest(tail).origin,
		CapeDrape.BARE_TRUNK_RADIUS, below)

func _apply_equipment_hides(part: int, part_config: Dictionary,
		model_config: Dictionary) -> void:
	# Garments are lofted with clearance over the reference body, but a bulkier
	# wardrobe would still poke through, so the surfaces a piece covers are
	# switched off while it is worn and counted so overlapping parts unwind.
	var names_value: Variant = model_config.get("hides", part_config.get("hides", []))
	var names: Array[String] = []
	if names_value is Array:
		for raw_name: Variant in names_value:
			names.append(str(raw_name).to_lower())
	for surface: String in _race_feature_hides(part, model_config):
		if not names.has(surface):
			names.append(surface)
	if names.is_empty():
		return
	_equipment_hides[part] = names
	for surface: String in names:
		_hidden_body_surfaces[surface] = int(_hidden_body_surfaces.get(surface, 0)) + 1
	_refresh_body_surface_visibility()

## The head and race-feature surfaces a worn piece hides, beyond its `hides`.
##
## These are added here in code rather than through the registry's `hides`
## lists, which list the wardrobe a piece covers and are pinned to the Human
## body's meshes. A model's `raceFeatures` ("show" or "hide") comes from
## eloria-assets/tools/headwear_race_policy.json for headwear.
##
## Headwear that covers the hair always hides it. On a body that carries
## `race_feature_head`, "show" pieces (hoods, open bands) leave the race head
## features up and keep the scalp drawn: since the features moved to their own
## node the scalp is a plain cranium, and hiding it under horns or a crown
## seen through a hood would open the inside of the head. A body without the
## node also keeps its scalp behind open hood brows: the scalp closes the
## head above the face even when no separate race features are present.
## Every other hair-covering piece
## hides the scalp and the features with the hair, which is also the default
## for a piece with no policy, so a new helm is safe without data. An explicit
## "hide" hides the features even on a piece that leaves the hair alone. An
## open-faced helm whose `scalp` is "show" (policy `scalp`) keeps the scalp
## drawn too: a low camera looks up under its brow past the face's top edge,
## and without the scalp sees the inside of the helm through the head.
##
## Mycelari shoulder growths go under any torso piece and any cape unless the
## item says "show", and under headwear whose `raceShoulders` is "hide" (the
## pieces whose rim, mantle, scarf or neck guard reaches the growths in some
## played clip; from the policy table's `shoulders`).
func _race_feature_hides(part: int, model_config: Dictionary) -> Array[String]:
	var hides: Array[String] = []
	var policy: String = str(model_config.get("raceFeatures", ""))
	if part == 3:
		var covers_hair := false
		var scene: String = str(model_config.get("scene", ""))
		if not scene.is_empty():
			for piece: Dictionary in _equipment_pieces(scene):
				if bool(piece.get("covers_hair", false)):
					covers_hair = true
					break
		if covers_hair:
			hides.append("hair")
			if policy != "show" and str(model_config.get("scalp", "")) != "show":
				hides.append("scalp")
		if policy == "hide" or (covers_hair and policy != "show"):
			hides.append(RACE_FEATURE_HEAD)
		if str(model_config.get("raceShoulders", "")) == "hide":
			hides.append(RACE_FEATURE_SHOULDERS)
	elif part == BODY_PART or part == CAPE_PART:
		if policy != "show":
			hides.append(RACE_FEATURE_SHOULDERS)
	return hides

## Whether the loaded body carries the `race_feature_head` node.
func _has_race_feature_head() -> bool:
	var native_model: Node3D = get_node_or_null("NativeModel") as Node3D
	return native_model != null and native_model.find_child(RACE_FEATURE_HEAD, true, false) != null

func _release_equipment_hides(part: int) -> void:
	var names_value: Variant = _equipment_hides.get(part, [])
	if names_value is Array:
		for raw_name: Variant in names_value:
			var surface: String = str(raw_name)
			var remaining: int = int(_hidden_body_surfaces.get(surface, 0)) - 1
			if remaining > 0:
				_hidden_body_surfaces[surface] = remaining
			else:
				_hidden_body_surfaces.erase(surface)
	_equipment_hides.erase(part)
	_refresh_body_surface_visibility()

## Generated torsos, trousers and boots replace their covered default clothing
## with fitted backing. Other torso equipment retains the undershirt tint.
func _refresh_wardrobe_cover() -> void:
	var native_model: Node3D = get_node_or_null("NativeModel") as Node3D
	if native_model == null:
		return
	var torso_visual: int = int(_equipment_visuals.get(BODY_PART, 0))
	var covered: bool = torso_visual != 0
	var torso_model := {}
	if covered:
		torso_model = _equipment_model_config(BODY_PART, torso_visual)
	var wardrobe_only := false
	for piece: Node in _equipment_nodes.get(BODY_PART, []):
		if is_instance_valid(piece) and bool(piece.get_meta("wardrobe_only", false)):
			wardrobe_only = true
			break
	var cover_regions: Array = []
	var open_throat := 0.0
	var fitted_legs := false
	var fitted_boots := false
	var ranger_paired_lower := (
		int(_equipment_visuals.get(4, 0)) == 230
		and int(_equipment_visuals.get(6, 0)) == 224)
	for part: int in [BODY_PART, 4, 6]:
		for piece: Node in _equipment_nodes.get(part, []):
			if not is_instance_valid(piece):
				continue
			if piece.has_meta("replaces_torso_body") and not piece.has_meta("generated_body_cover"):
				cover_regions.append(Vector3(TorsoBodyCover.LOW, TorsoBodyCover.HIGH, TorsoBodyCover.WRIST))
			elif piece.has_meta("generated_body_cover"):
				cover_regions.append(piece.get_meta("generated_body_cover"))
				if piece.has_meta("generated_open_throat"):
					open_throat = float(piece.get_meta("generated_open_throat"))
				if part == 4:
					fitted_legs = true
				if part == 6:
					fitted_boots = true
	for piece: Node in _equipment_nodes.get(6, []):
		if is_instance_valid(piece) and piece.has_meta("boot_backing_with_legs"):
			# The Ranger trousers already provide the continuous leg-to-boot
			# lining. Drawing the paired boot lining as well puts a second shell
			# through the toe and vamp. Scope the suppression to this reviewed
			# 230+224 pairing so the same ankle boots still back other outfits.
			(piece as MeshInstance3D).visible = not ranger_paired_lower \
				and not piece.has_meta("suppress_generated_backing") and \
				bool(piece.get_meta("boot_backing_with_legs")) == fitted_legs
	for piece: Node in _equipment_nodes.get(4, []):
		if is_instance_valid(piece) and piece.has_meta("leg_backing_with_boots"):
			(piece as MeshInstance3D).visible = not piece.has_meta("suppress_generated_backing") and \
				bool(piece.get_meta("leg_backing_with_boots")) == fitted_boots
	for node_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		if mesh_node.has_meta("native_equipment"):
			continue
		var surface_name: String = mesh_node.name.to_lower()
		var is_body_surface: bool = (surface_name in ["body", "char1", "mesh_node"]
			or surface_name.begins_with("wardrobe_"))
		if surface_name == "wardrobe_shirt":
			# Every body-cover pass starts from the authored shirt. The fitted
			# wardrobe-only variant is presentation state, applied again below.
			WARDROBE_SHIRT_FIT.restore(mesh_node)
		if _native_skeleton != null and mesh_node.skin != null and is_body_surface:
			var mask_to_wardrobe_neckline := (wardrobe_only
				and surface_name in ["body", "char1", "mesh_node"])
			# The fitted native shirt owns its shaped opening. Mask only the body
			# beneath that opening; shirt/trim surfaces stay on the ordinary path.
			TorsoBodyCover.apply(mesh_node,
				not cover_regions.is_empty() or mask_to_wardrobe_neckline,
				_native_skeleton.global_transform.affine_inverse() * mesh_node.global_transform,
				rig_fit_scale(), cover_regions,
				rig_name().begins_with("ssarathi_"), mask_to_wardrobe_neckline, open_throat)
		if wardrobe_only and surface_name == "wardrobe_shirt" \
				and _native_skeleton != null:
			WARDROBE_SHIRT_FIT.apply(mesh_node, _native_skeleton)
		if not SHIRT_SURFACES.has(mesh_node.name.to_lower()):
			continue
		if not mesh_node.has_meta("wardrobe_color"):
			continue
		var wardrobe_color := mesh_node.get_meta("wardrobe_color") as Color
		var want: Color = COVERED_SHIRT if covered else wardrobe_color
		if wardrobe_only:
			var color_key := ("wardrobeTrimColor" if
				surface_name == "wardrobe_shirt_trim" else "wardrobeColor")
			want = _tint_colour(torso_model.get(color_key,
				torso_model.get("wardrobeColor", [])), wardrobe_color)
		if mesh_node.mesh.get_surface_count() > 1:
			for surface in range(mesh_node.mesh.get_surface_count()):
				var part_material := mesh_node.get_surface_override_material(surface) as StandardMaterial3D
				if part_material != null:
					part_material.albedo_color = want
			continue
		# Set on the override the appearance pass already installed rather than
		# through `_set_mesh_color`: that duplicates the material afresh, which
		# would drop the `grow` WARDROBE_GROW put on it and sink the shirt back
		# into the skin it was lifted off.
		var material: StandardMaterial3D = (mesh_node.material_override
			as StandardMaterial3D)
		if material == null:
			_set_mesh_color(mesh_node, want)
			continue
		material.albedo_color = want

func _refresh_body_surface_visibility() -> void:
	var native_model: Node3D = get_node_or_null("NativeModel") as Node3D
	if native_model == null:
		return
	for node_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		var surface: String = mesh_node.name.to_lower()
		if surface in ["hair", "scalp"] or surface.begins_with(RACE_FEATURE_PREFIX):
			if not mesh_node.has_meta("uncovered_head_visible"):
				mesh_node.set_meta("uncovered_head_visible", mesh_node.visible)
			mesh_node.visible = bool(mesh_node.get_meta("uncovered_head_visible")) and not _hidden_body_surfaces.has(surface)
			continue
		if not surface.begins_with("wardrobe_"):
			continue
		if _hidden_body_surfaces.has(surface):
			mesh_node.visible = false
		elif not mesh_node.has_meta("appearance_hidden"):
			mesh_node.visible = true
	if _native_skeleton != null:
		var hide_hair: bool = _hidden_body_surfaces.has("hair")
		for node_value: Node in _native_skeleton.get_children():
			if node_value.name.begins_with("AppearanceHair_"):
				(node_value as Node3D).visible = not hide_hair
	if _silhouette != null:
		_silhouette.sync()

## Draws the actor's shape over anything hiding it from the camera. Only ever
## switched on for the local player - see OccludedSilhouette.
func set_occlusion_silhouette_enabled(enabled: bool) -> void:
	if _silhouette == null:
		if not enabled:
			return
		_silhouette = OccludedSilhouette.new(self, _native_skeleton)
	_silhouette.set_enabled(enabled)
	if enabled:
		_apply_render_quality_to_visuals()

func occlusion_silhouette_enabled() -> bool:
	return _silhouette != null and _silhouette.is_enabled()

func get_skeleton() -> Skeleton3D:
	return _native_skeleton

func set_mount_state(state: Dictionary, models: Dictionary) -> void:
	_set_mount_state_legacy(state, models)
	var remote = RemotePresentationService.current() if _remote_generation > 0 else null
	if remote != null: remote.sync_transfer(self)

func _set_mount_state_legacy(state: Dictionary, models: Dictionary) -> void:
	if _model_deferred:
		# Kept for the record only; the built actor seats its own rider.
		mount_state = state.duplicate(true)
		return
	var was_mounted := is_instance_valid(_mount_visual)
	var mount_id := str(state.get("mount_id", ""))
	var riding: bool = state.get("mode") == "mounted" and preload("res://src/mounts/mount_profiles.gd").supports(mount_id)
	if was_mounted and riding and mount_state.get("mount_id") != mount_id:
		set_mount_state({}, models)
		was_mounted = false
	mount_state = state.duplicate(true)
	if riding and not was_mounted:
		# Seat fitting records the neutral imported root, without terrain lean.
		_clear_native_surface_tilt()
		# A previously stepped player must leave the gate before mounted sampling
		# takes ownership. Reference-pose seeks remain explicit and immediate.
		if _animation_gate_owner != null:
			_animation_gate_owner.discard(animation_player)
		_set_model_processing(true)
		if animation_player != null:
			animation_player.active = true
			animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var visual := (load("res://src/mounts/mounted_player_visual.gd") as Script).new() as Node3D
		add_child(visual)
		# Configure before marking mounted: reference poses must play normally.
		var errors: Array = visual.call("configure", self, models, mount_id)
		if not errors.is_empty():
			visual.call("restore")
			visual.free()
			_restore_unmounted_animation_gate()
			push_warning("Mount: " + str(errors))
			play_action(&"idle", true)
			_apply_surface_orientation()
			return
		_mount_visual = visual
		_mount_visual.name = "MountedPony"
		_mount_visual.call("apply_render_quality", _render_quality, _render_quality_local_actor)
		_mount_visual.call("set_animation_tier", _animation_tier,
			_animation_gate_owner.one_shot_tier if _animation_gate_owner != null else AnimationGate.Tier.HALF,
			_animation_gate_owner.gate_skeletons if _animation_gate_owner != null else true,
			_animation_gate_owner.stagger if _animation_gate_owner != null else true)
		_refresh_cape_cloth_activity(true)
		_pace_histories.clear()
		_last_movement_update_msec = -1
		current_action = &"idle"
	elif not riding and was_mounted:
		var previous := _mount_visual
		_mount_visual = null
		previous.call("restore")
		previous.free()
		_restore_unmounted_animation_gate()
		_pace_histories.clear()
		_last_movement_update_msec = -1
		current_action = &"idle"
		play_action(&"walk" if _segment_duration > 0.0 else &"idle", true)
	if is_instance_valid(_mount_visual):
		_mount_visual.set("state", mount_state)
		_mount_visual.call("set_coat", str(mount_state.get("coat_id", "original")))
	if riding != was_mounted:
		_surface_applied_up = Vector3(NAN, NAN, NAN)
		_apply_surface_orientation()

func _equipment_model_config(part: int, visual_id: int) -> Dictionary:
	var aliases: Dictionary = _equipment_config.get("aliases", {}) as Dictionary
	var model_key: String = "%d:%d" % [part, visual_id]
	model_key = str(aliases.get(model_key, model_key))
	var models: Dictionary = _equipment_config.get("models", {}) as Dictionary
	var model: Dictionary = models.get(model_key, {}) as Dictionary
	return _fit_variant(model)

## The race this actor's body was built as, which is what the registry keys its
## fit groups and its body measurements on.
func rig_name() -> String:
	return str(_model_config.get("scene", "")).get_file().get_basename()

## The fit groups this actor's race belongs to, in precedence order.
##
## Generated garments share male/female body fits; headwear keeps a fit for
## each retained head. Registries list these fit groups in priority
## order; the parser also retains compatibility with a single group string.
func fit_groups() -> PackedStringArray:
	var groups: Dictionary = _equipment_config.get("fitGroups", {}) as Dictionary
	var mine: Variant = groups.get(rig_name(), "")
	if mine is Array:
		var names := PackedStringArray()
		for value: Variant in mine as Array:
			names.append(str(value))
		return names
	var single := str(mine)
	return PackedStringArray() if single.is_empty() else PackedStringArray([single])

func _fit_variant(model: Dictionary) -> Dictionary:
	# Modified 2026-08-28 for Eloria Client: some builds cannot be reached by
	# resizing a garment, only by authoring one.  A race in a fit group wears
	# the copy of the piece built on its own rig where one exists, and the
	# reference piece everywhere else, so a group only costs the kinds it
	# actually changes.
	if model.is_empty():
		return model
	var variants: Dictionary = model.get("variants", {}) as Dictionary
	for group: String in fit_groups():
		var variant: Dictionary = variants.get(group, {}) as Dictionary
		if variant.is_empty():
			continue
		var resolved: Dictionary = model.duplicate(true)
		resolved.erase("variants")
		resolved.merge(variant, true)
		return resolved
	return model

func _equipment_socket(part: int, model_config: Dictionary) -> Dictionary:
	# A model may override the shared part socket, which is how a two-handed
	# haft can ride differently from a one-handed hilt on the same bone.
	var override: Dictionary = model_config.get("socket", {}) as Dictionary
	if not override.is_empty():
		return override
	var sockets: Dictionary = _equipment_config.get("sockets", {}) as Dictionary
	return sockets.get(str(part), {}) as Dictionary

func _equipment_fit_profile(name: String = "") -> Dictionary:
	var profiles: Dictionary = _equipment_config.get("fitProfiles", {}) as Dictionary
	return profiles.get(name, _equipment_config) as Dictionary

func rig_fit_scale(profile: String = "") -> float:
	# Canonical body variants use current Rest_Pose units. Unchanged socketed
	# props/capes retain their recorded legacy units and measurement profile.
	# A body variant already fits its wearer; no stature correction is repeated.
	if _native_skeleton == null:
		return 1.0
	var canonical: float = float(_equipment_fit_profile(profile).get("canonicalHeadRestY", 0.0))
	if canonical <= 0.0:
		return 1.0
	var head: int = _native_skeleton.find_bone("Head")
	if head < 0:
		return 1.0
	return _native_skeleton.get_bone_global_rest(head).origin.y / canonical

func _attach_socketed_equipment(socket: Dictionary, scene_path: String,
		model_config: Dictionary, part: int, visual_id: int) -> BoneAttachment3D:
	if socket.is_empty():
		return null
	var bone: String = str(socket.get("bone", ""))
	var attachment: BoneAttachment3D = _bone_attachment(bone, part, visual_id)
	if attachment == null:
		return null
	var native_model: Node3D = _equipment_instance(scene_path)
	if native_model == null:
		attachment.queue_free()
		return null
	var bone_index: int = _native_skeleton.find_bone(bone)
	var rest: Transform3D = _native_skeleton.get_bone_global_rest(bone_index)
	var fit: float = rig_fit_scale(str(model_config.get("fitProfile", "")))
	var scale: float = fit * float(model_config.get("scale", 1.0))
	# The socket is authored in character space; cancelling the bone rest keeps
	# it readable while still riding the bone once the clip plays.
	native_model.transform = rest.affine_inverse() * _socket_placement(
		socket, rest, fit, scale)
	# The fighting socket seats the hilt inside the closed fist. Retain the
	# reviewed idle socket and its authoring metadata for geometry checks.
	# WeaponCarryPose reads the stable fighting grip and turns the wrist
	# while closing the fingers, so the prop remains inside that grip.
	var idle_socket: Dictionary = model_config.get("idleSocket", {}) as Dictionary
	if not idle_socket.is_empty() and str(idle_socket.get("bone", bone)) == bone:
		native_model.set_meta(&"fighting_grip", native_model.transform)
		native_model.set_meta(&"idle_grip", rest.affine_inverse() * _socket_placement(
			idle_socket, rest, fit, scale))
		native_model.set_meta(&"idle_style", StringName(str(idle_socket.get("style", ""))))
		native_model.set_meta(&"idle_arm_spread", float(idle_socket.get("armSpread", 0.0)))
		if idle_socket.has("floorPoint"):
			native_model.set_meta(&"idle_floor_point", _vector3(idle_socket.get("floorPoint", []), Vector3.ZERO))
	_tint_equipment(native_model, model_config.get("tint", []) as Array)
	attachment.add_child(native_model)
	attachment.set_meta("native_equipment", true)
	return attachment

## Where `socket` puts a prop in character space: its rotation, scaled to the
## piece and this body, at the bone's rest position moved by the authored
## offset. The offset is in the units the piece was fitted in, so it scales
## with the body the same way the piece does.
func _socket_placement(socket: Dictionary, bone_rest: Transform3D, fit: float,
		scale: float) -> Transform3D:
	return Transform3D(
		Basis.from_euler(_vector3(socket.get("rotationDegrees", []),
			Vector3.ZERO) * (PI / 180.0)).scaled(Vector3.ONE * scale),
		bone_rest.origin + _vector3(socket.get("offset", []), Vector3.ZERO) * fit)

func _attach_skinned_equipment(scene_path: String, part: int, visual_id: int,
		tint: Array = [], author_rig: String = "",
		skin_region: String = "", fit_profile: String = "",
		suppress_generated_backing: bool = false) -> Array[Node]:
	# The garment ships with the shared joint hierarchy so it is a valid skinned
	# glTF on its own. Replacing its bind poses with this skeleton's rest poses
	# retargets the garment and applies the rig fit scale in one step.
	var created: Array[Node] = []
	var fit: float = rig_fit_scale(fit_profile)
	var fit_basis: Transform3D = Transform3D(
		Basis.IDENTITY.scaled(Vector3.ONE * fit), Vector3.ZERO)
	# Bind poses depend only on the rig, and every actor built from one model
	# shares a rest pose, so the rebound skin is cached per model and garment
	# instead of rebuilt from 77 named binds for each actor that wears one.
	var cache_key: String = "%s|%s|%s|%s" % [str(_model_config.get("scene", "")), scene_path, fit_profile, fit]
	var ground: Dictionary = _ground_drops(author_rig, skin_region, fit_profile)
	# The cape is the one garment cut against another: its yoke is rigid, so
	# only this can hold it outside the torso worn under it.
	var worn: String = _worn_torso_scene() if part == CAPE_PART else ""
	for piece_value: Variant in _equipment_pieces(scene_path):
		var piece: Dictionary = piece_value as Dictionary
		var surface_key: String = "%s|%s" % [cache_key, str(piece.get("name", ""))]
		var rebound: Skin = _rebound_skins.get(surface_key) as Skin
		if rebound == null:
			rebound = _rebound_skin(piece.get("bones", PackedStringArray()) as PackedStringArray,
				piece.get("binds", [] as Array[Transform3D]) as Array[Transform3D],
				fit_basis, _girth_ratios(author_rig, fit_profile), ground)
			if rebound != null:
				# Skeleton3D registers Skin resources by identity. Garment and
				# backing meshes with identical finalized binds can share that
				# binding while keeping their meshes and materials independent.
				rebound = REBOUND_SKIN_POOL.intern_finalized(rebound)
				_rebound_skins[surface_key] = rebound
		if rebound == null:
			continue
		var clone: MeshInstance3D = MeshInstance3D.new()
		clone.name = "EquipmentSkin_%d_Visual_%d_%s" % [part, visual_id,
			str(piece.get("name", "Mesh"))]
		clone.mesh = _draped_over(worn, scene_path, piece)
		clone.skin = rebound
		clone.transform = piece.get("transform", Transform3D.IDENTITY)
		_restore_piece_render_state(clone, piece)
		_tint_surfaces(clone, tint)
		_native_skeleton.add_child(clone)
		clone.skeleton = NodePath("..")
		clone.set_meta("native_equipment", true)
		var generated_backing: bool = str(piece.get("name", "")).begins_with("Generated")
		if suppress_generated_backing and generated_backing:
			# Some generated backing surfaces are useful only as authoring-time body
			# cover envelopes. Keep the node and its metadata so the native wardrobe
			# is still clipped, but skip the redundant draw when the authored shell is
			# already closed on its own.
			clone.set_meta("suppress_generated_backing", true)
			clone.visible = false
		if part == BODY_PART and str(piece.get("name", "")) == TorsoBodyCover.BACKING_NAME:
			clone.set_meta("replaces_torso_body", true)
			var cover: Array = piece.get("body_cover", []) as Array
			if cover.size() == 3 or cover.size() == 4:
				clone.set_meta("generated_body_cover", _vector3(cover, Vector3.ZERO))
			# The lining's open neckline, where the throat skin stays
			# (TorsoBodyCover.OPEN_THROAT_SLOPE).
			if cover.size() == 4 and float(cover[3]) > 0.0:
				clone.set_meta("generated_open_throat", float(cover[3]))
		if (part == 4 and str(piece.get("name", "")) == "GeneratedLegBacking") or (part == 6 and str(piece.get("name", "")) == "GeneratedBootBacking"):
			var cover: Array = piece.get("body_cover", []) as Array
			if cover.size() == 3:
				clone.set_meta("generated_body_cover", _vector3(cover, Vector3.ZERO))
		if part == 6 and str(piece.get("name", "")).begins_with("GeneratedBootBacking"):
			clone.set_meta("boot_backing_with_legs", str(piece.get("name", "")) == "GeneratedBootBackingWithLegs")
		if part == 4 and str(piece.get("name", "")).begins_with("GeneratedLegBacking"):
			clone.set_meta("leg_backing_with_boots", str(piece.get("name", "")) == "GeneratedLegBackingWithBoots")
		created.append(clone)
	if part == BODY_PART:
		var native_model := get_node_or_null("NativeModel")
		if native_model != null:
			var body := native_model.find_child("body", true, false) as MeshInstance3D
			if body != null:
				var neck := NecklineSkin.make(body, _native_skeleton)
				if neck != null:
					_native_skeleton.add_child(neck)
					created.append(neck)
	return created

func _equipment_instance(scene_path: String) -> Node3D:
	var pieces: Array = _equipment_pieces(scene_path)
	if pieces.is_empty():
		return null
	var holder: Node3D = Node3D.new()
	holder.name = "NativeEquipment"
	for piece_value: Variant in pieces:
		var piece: Dictionary = piece_value as Dictionary
		var mesh_node: MeshInstance3D = MeshInstance3D.new()
		mesh_node.name = str(piece.get("name", "Mesh"))
		mesh_node.mesh = piece.get("mesh") as Mesh
		mesh_node.transform = piece.get("transform", Transform3D.IDENTITY)
		_restore_piece_render_state(mesh_node, piece)
		holder.add_child(mesh_node)
	return holder

static func _restore_piece_render_state(mesh_node: MeshInstance3D,
		piece: Dictionary) -> void:
	# Imported per-node presentation does not live on ArrayMesh itself. Carry it
	# across when equipment is rebound/reparented so using the LOD-capable mesh
	# does not silently discard authored material overrides or LOD bias.
	mesh_node.material_override = piece.get("material_override") as Material
	mesh_node.lod_bias = float(piece.get("lod_bias", 1.0))
	mesh_node.cast_shadow = int(piece.get("cast_shadow",
		GeometryInstance3D.SHADOW_CASTING_SETTING_ON)) as GeometryInstance3D.ShadowCastingSetting
	var surface_overrides: Array = piece.get("surface_overrides", []) as Array
	for surface: int in mini(surface_overrides.size(),
			mesh_node.mesh.get_surface_count() if mesh_node.mesh != null else 0):
		mesh_node.set_surface_override_material(surface,
			surface_overrides[surface] as Material)

const TINT_SLOTS := {"base": 0, "trim": 1, "detail": 2}

func _tint_equipment(root: Node3D, tint: Array) -> void:
	if tint.is_empty():
		return
	for node_value: Node in root.find_children("*", "MeshInstance3D", true, false):
		_tint_surfaces(node_value as MeshInstance3D, tint)

func _tint_surfaces(mesh_node: MeshInstance3D, tint: Array) -> void:
	# One authored mesh serves a whole material ladder, so an iron and a steel
	# helm are the same scene under different tints. The slot is read from the
	# material name rather than the surface index, because a piece that uses no
	# trim geometry would otherwise shift its detail colour onto the trim.
	if tint.is_empty() or mesh_node.mesh == null:
		return
	for surface: int in range(mesh_node.mesh.get_surface_count()):
		var source: Material = mesh_node.mesh.surface_get_material(surface)
		if source is not StandardMaterial3D:
			continue
		var slot: int = _tint_slot(source.resource_name, surface)
		if slot < 0 or slot >= tint.size():
			continue
		var origin: StandardMaterial3D = source as StandardMaterial3D
		var material: StandardMaterial3D = origin.duplicate()
		material.albedo_color = _tint_colour(tint[slot], origin.albedo_color)
		if origin.emission_enabled:
			# An enchanted finish carries its glow on the same slot, so a shared
			# mesh would otherwise keep the first variant's light: a Crown of
			# Life tinted green but still glowing the Crown of Mana's blue.
			var glow: Color = _tint_colour(tint[slot], origin.emission)
			var authored: float = maxf(origin.emission.r, maxf(
				origin.emission.g, origin.emission.b))
			var tinted: float = maxf(glow.r, maxf(glow.g, glow.b))
			material.emission = glow * (authored / maxf(tinted, 0.001))
		mesh_node.set_surface_override_material(surface, material)

static func _tint_slot(material_name: String, fallback: int) -> int:
	var suffix: String = material_name.get_slice(" ", material_name.count(" ")).to_lower()
	return int(TINT_SLOTS.get(suffix, fallback))

static func _tint_colour(value: Variant, fallback: Color) -> Color:
	# Tints are authored as sRGB bytes and albedo_color is sRGB, so they pass
	# through unconverted. The generator converts the same bytes to linear on
	# its way into the glTF factor, which the importer converts back, so a
	# tinted piece and the mesh it was authored from land on the same colour.
	if value is Array and (value as Array).size() >= 3:
		var channels: Array = value as Array
		return Color(float(channels[0]) / 255.0, float(channels[1]) / 255.0,
			float(channels[2]) / 255.0, fallback.a)
	return fallback

## How much wider this actor is than the body a garment was lofted around, bone
## by bone. Empty when the two are the same rig, or when either is unmeasured -
## an unknown body is worn as authored rather than guessed at.
##
## Only ever a widening. A garment is cut close to the reference body, so
## letting it out for a broader wearer is safe while taking it in is not: the
## measurement is one number for a whole bone, and a chest it underestimates
## would come straight through the shirt.
func _shares_authored_body(author_rig: String, profile: String) -> bool:
	if profile != "canonical":
		return false
	if _has_refitted_body(profile):
		return false
	var templates: Dictionary = _equipment_config.get("bodyTemplates", {}) as Dictionary
	var author: String = str(templates.get(author_rig, ""))
	return not author.is_empty() and author == str(templates.get(rig_name(), ""))

func _has_refitted_body(profile: String) -> bool:
	return profile == "canonical" and rig_name() in _equipment_config.get("refittedBodies", [])

func _girth_ratios(author_rig: String, profile: String = "") -> Dictionary:
	var mine: String = rig_name()
	if author_rig.is_empty() or (author_rig == mine and not _has_refitted_body(profile)) or _shares_authored_body(author_rig, profile):
		return {}
	var table: Dictionary = _equipment_fit_profile(profile).get("bodyGirth", {}) as Dictionary
	var authored: Dictionary = _equipment_config.get("authoredBodyGirth", table) as Dictionary if profile == "canonical" else table
	var author: Dictionary = authored.get(author_rig, {}) as Dictionary
	var wearer: Dictionary = table.get(mine, {}) as Dictionary
	if author.is_empty() or wearer.is_empty():
		return {}
	var ratios: Dictionary = {}
	for bone: String in author:
		var from: float = float(author[bone])
		var to: float = float(wearer.get(bone, 0.0))
		if from > 0.0005 and to > 0.0005:
			ratios[bone] = clampf(to / from, 1.0, 2.0)
	return ratios

## Translate a shared boot by measured foot geometry, not skeleton stature.
## Shared male/female body geometry includes matching weighted soles and toes.
## Items authored on that same template need no second foot adjustment. Legacy
## items retain their recorded authoring profile and socket scale.
func _ground_drops(author_rig: String, skin_region: String, profile: String = "") -> Dictionary:
	if skin_region != "boots":
		return {}
	var mine: String = rig_name()
	if author_rig.is_empty() or (author_rig == mine and not _has_refitted_body(profile)) or _shares_authored_body(author_rig, profile):
		return {}
	var table: Dictionary = _equipment_fit_profile(profile).get("footAnchor", {}) as Dictionary
	var authored: Dictionary = _equipment_config.get("authoredFootAnchor", table) as Dictionary if profile == "canonical" else table
	var author: Dictionary = authored.get(author_rig, {}) as Dictionary
	var wearer: Dictionary = table.get(mine, {}) as Dictionary
	if author.is_empty() or wearer.is_empty():
		return {}
	# Per bone, not one datum for the whole chain. Collapsing them onto the
	# ankle's figure was tried, on the reasoning that a boot is rigid and should
	# travel as one piece; measured, it was five times worse - 951 body vertices
	# outside the shell against 185. The shell is skinned rather than rigid, and
	# letting each bone carry its own offset is what lands the ankle and the ball
	# of the foot in the right place at once.
	var drops: Dictionary = {}
	for bone: String in author:
		var from: Vector3 = _vector3(author[bone] as Array, Vector3.ZERO)
		var to: Vector3 = _vector3(wearer.get(bone, []) as Array, Vector3.ZERO)
		if from != Vector3.ZERO and to != Vector3.ZERO:
			# The pair, not the difference: how far the boot has to move depends
			# on how much it has been widened first, and that is decided in
			# `_bone_fit` where the girth ratio is known.
			drops[bone] = [from, to]
	return drops

func _rebound_skin(bone_names: PackedStringArray, binds: Array[Transform3D],
		fit: Transform3D, girth: Dictionary = {},
		ground: Dictionary = {}) -> Skin:
	# Modified 2026-08-28 for Eloria Client: this used to hand every bone the
	# bind `this_rest.inverse() * fit`.  Skinning then evaluates
	# `pose * bind`, and at rest `pose` *is* `this_rest`, so the whole thing
	# collapsed to `fit` - a uniform scale about the floor.  A garment was never
	# retargeted at all, only resized, which is why boots authored on a
	# plantigrade leg stayed at ankle height on the Ssarathi's digitigrade one
	# and left their feet outside the boot.  Keeping the garment's *authored*
	# bind instead makes `pose * bind` carry each vertex from the bone it was
	# modelled on to the same bone here, so the piece follows this rig's rest
	# pose.  The fit scale stays, applied in bone space, so a shorter race still
	# wears a proportionally slimmer garment.
	#
	# The mesh's JOINTS_0 values index this bind array, so a bind may never be
	# skipped: dropping one would shift every later bone by a slot. A garment
	# whose rig this actor does not carry is refused outright instead.
	if bone_names.is_empty():
		return null
	var author_rest: Dictionary = {}
	for index: int in range(bone_names.size()):
		if index < binds.size():
			author_rest[bone_names[index]] = binds[index].affine_inverse()
	var rebound: Skin = Skin.new()
	for index: int in range(bone_names.size()):
		var bone_name: String = bone_names[index]
		var target: int = _native_skeleton.find_bone(bone_name)
		if bone_name.is_empty() or target < 0:
			return null
		if index < binds.size():
			rebound.add_named_bind(bone_name,
				_bone_fit(target, bone_name, author_rest, fit,
					float(girth.get(bone_name, 1.0)),
					ground.get(bone_name, []) as Array,
					_native_skeleton.get_bone_global_rest(target)) * binds[index])
		else:
			# No authored bind survived the import: fall back to the resize so
			# the piece still appears rather than collapsing onto the origin.
			rebound.add_named_bind(bone_name,
				_native_skeleton.get_bone_global_rest(target).affine_inverse() * fit)
	return rebound

func _bone_fit(target: int, bone_name: String, author_rest: Dictionary,
		fit: Transform3D, girth: float = 1.0, ground: Array = [],
		wearer_rest: Transform3D = Transform3D.IDENTITY) -> Transform3D:
	# Carrying a garment onto another rig by rotation alone leaves it the length
	# it was authored, which is fine while the two rigs agree and wrong when
	# they do not: the Ssarathi metatarsal is nearly half again as long as the
	# one the boots were built on, so the boot ran out partway along the foot
	# and the rest of it - toes and claws - came out the front.  Each bone's
	# span is compared against the span it was authored with and the garment is
	# stretched along that bone to match.  Bones the two rigs agree on get a
	# ratio of one and are left exactly as authored.
	var rest: Transform3D = author_rest.get(bone_name, Transform3D.IDENTITY)
	var author_tip: Vector3 = _mean_child_origin(target, author_rest, true)
	var target_tip: Vector3 = _mean_child_origin(target, author_rest, false)
	var ratio: float = 1.0
	var axis := Vector3(0.0, 1.0, 0.0)
	var measured := false
	if author_tip != Vector3.INF and target_tip != Vector3.INF:
		var local: Vector3 = rest.affine_inverse() * author_tip
		var author_span: float = local.length()
		var target_span: float = (target_tip
			- _native_skeleton.get_bone_global_rest(target).origin).length()
		if author_span > 0.0005 and target_span > 0.0005:
			ratio = clampf(target_span / author_span, 0.4, 2.5)
			axis = local / author_span
			measured = true
	# A foot bone carrying a ground ratio takes it instead of the span-and-girth
	# result, and takes it whether it widens or narrows. Everything else here is
	# a guess at how much bigger this body is than the authored one; that is the
	# measured distance between the joint and the floor it has to stand on, and
	# the floor is not negotiable - the actor is placed on the ground by its
	# body, so a boot that disagrees is a boot underneath it. It stays isotropic:
	# the ground ratio is chosen to land the sole, and splitting it would move
	# the sole off the plane it was solved for.
	# A foot bone carrying a ground datum is *moved* onto this body rather than
	# scaled onto it. It is still widened first, because some feet genuinely are
	# broader - an Orun's is twelve per cent wider than the reference - and a
	# shell that does not grow for them leaves the outside of the foot showing.
	# Widening and then moving is why the anchor arrives as a pair rather than a
	# difference: how far the boot has to travel depends on how much bigger it
	# has just been made.
	if ground.size() == 2:
		var wide: float = clampf(maxf(ratio, girth), 1.0, 2.0)
		var scaled: float = fit.basis.get_scale().y * wide
		# The anchor is a signed offset from the joint to the foot, so all three
		# axes read the same way: where the authored foot lands once scaled onto
		# this body, subtracted from where this body's foot actually is. Y is
		# measured to the floor because standing on the ground has to be exact;
		# X and Z to the middle of the foot, which is what puts an Orun's boot
		# around an Orun's foot rather than around the joint it hangs from.
		var landed: Vector3 = (ground[0] as Vector3) * scaled
		var wanted: Vector3 = ground[1] as Vector3
		return Transform3D(fit.basis.scaled(Vector3.ONE * wide),
			wearer_rest.basis.inverse() * (wanted - landed))

	# Widening and lengthening are two different questions and used to be
	# answered with one number.
	#
	# Modified 2026-08-29 for Eloria Client. The scale below is applied in the
	# authored bone's own space, which anchors it at the bone origin, and
	# `calf`'s origin is the knee. Letting an Orun's calf out by the thirty per
	# cent its girth asks for therefore also made the calf thirty per cent
	# longer, and every trouser hem hangs near the far end of that bone: the
	# hems landed 118 to 124 mm below where they belong on the two broadest
	# races, and a boot's sole vertex inheriting the body's own heel weighting -
	# 31 per cent `calf` - was dragged 62 mm under the floor by the same term.
	#
	# The obvious repair, translating the bone's contribution back along its own
	# axis until the joint below lands correctly, moves the error rather than
	# removing it: a translation displaces the bone origin as much as its tip,
	# so the hem is fixed and the knee - where this bone's geometry is blended
	# with its parent's, which was never displaced - opens up by the same amount.
	# The seam moves instead of the hem.
	#
	# So the two questions are answered separately. Along the bone the garment
	# follows the span ratio, which puts the joint below exactly where the
	# wearer's own skeleton puts it and leaves the bone origin fixed. Around the
	# bone it follows girth, and still only ever widens.
	#
	# This is the anisotropy the previous note here refused, and the reason it
	# is safe now is that the axis is the bone's, not the world's. Skinning
	# carries normals through this same matrix, and a scale that is uniform in
	# the plane perpendicular to the bone leaves every radial normal - which is
	# very nearly all of them on a sleeve, a trouser leg or a boot shaft -
	# pointing exactly where it did. What tilts is the oblique minority, by at
	# most eight degrees at the widest girth in the cast. The black band that
	# came of the earlier attempt came of stretching *along* the spine, which is
	# the direction this one deliberately leaves alone.
	var across: float = clampf(maxf(ratio, girth), 1.0, 2.0)
	# A leaf bone has no joint below it to measure a span against, so there is
	# no axis to separate along from across and it stays isotropic.
	var along: float = across if not measured else clampf(ratio, 0.4, 2.5)
	if absf(across - 1.0) < 0.02 and absf(along - 1.0) < 0.02:
		return fit
	# across * I, corrected along the bone axis by (along - across).
	var basis := Basis.IDENTITY.scaled(Vector3.ONE * across)
	var shaped := Basis(
		basis.x + axis * (along - across) * axis.x,
		basis.y + axis * (along - across) * axis.y,
		basis.z + axis * (along - across) * axis.z)
	return Transform3D(fit.basis * shaped, Vector3.ZERO)

func _mean_child_origin(target: int, author_rest: Dictionary,
		authored: bool) -> Vector3:
	# The bone's tip: where its children sit, on whichever rig was asked for.
	# Vector3.INF means the bone is a leaf on one of the two rigs, and a leaf
	# has no span to compare.
	var total := Vector3.ZERO
	var found: int = 0
	for child: int in _native_skeleton.get_bone_children(target):
		var child_name: String = _native_skeleton.get_bone_name(child)
		if not author_rest.has(child_name):
			continue
		total += ((author_rest[child_name] as Transform3D).origin if authored
			else _native_skeleton.get_bone_global_rest(child).origin)
		found += 1
	return total / float(found) if found > 0 else Vector3.INF

func _attach_fallback_equipment(part: int, visual_id: int,
		part_config: Dictionary) -> Array[Node]:
	var created: Array[Node] = []
	var socket: Dictionary = _equipment_socket(part, {})
	var bones: Array[String] = []
	var fallback_bone: String = str(socket.get("bone", ""))
	if not fallback_bone.is_empty():
		bones.append(fallback_bone)
	var semantic: String = str(part_config.get("attachment", ""))
	var bones_value: Variant = _attachment_bones.get(semantic, "")
	if bones_value is Array:
		for raw_bone: Variant in bones_value:
			if not bones.has(str(raw_bone)):
				bones.append(str(raw_bone))
	elif not str(bones_value).is_empty() and not bones.has(str(bones_value)):
		bones.append(str(bones_value))
	for bone: String in bones:
		var attachment: BoneAttachment3D = _bone_attachment(bone, part, visual_id)
		if attachment == null:
			continue
		attachment.add_child(_equipment_fallback_mesh(
			str(part_config.get("fallback", "body"))))
		created.append(attachment)
	return created

static func _vector3(value: Variant, fallback: Vector3) -> Vector3:
	if value is Array and (value as Array).size() >= 3:
		var values: Array = value as Array
		return Vector3(float(values[0]), float(values[1]), float(values[2]))
	return fallback

func _bone_attachment(bone: String, part: int, visual_id: int) -> BoneAttachment3D:
	if _native_skeleton == null or _native_skeleton.find_bone(bone) < 0:
		return null
	var attachment: BoneAttachment3D = BoneAttachment3D.new()
	attachment.name = "EquipmentPart_%d_Visual_%d_%s" % [part, visual_id, bone]
	attachment.bone_name = bone
	_native_skeleton.add_child(attachment)
	return attachment

func _equipment_fallback_mesh(shape: String) -> MeshInstance3D:
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.name = "MissingNativeEquipmentFallback"
	var material: StandardMaterial3D = StandardMaterial3D.new()
	material.albedo_color = Color(1.0, 0.1, 0.85, 0.85)
	material.emission_enabled = true
	material.emission = Color(0.7, 0.0, 0.5)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	match shape:
		"weapon":
			var weapon: BoxMesh = BoxMesh.new()
			weapon.size = Vector3(0.08, 0.7, 0.08)
			instance.mesh = weapon
		"shield":
			var shield: CylinderMesh = CylinderMesh.new()
			shield.top_radius = 0.28
			shield.bottom_radius = 0.28
			shield.height = 0.06
			instance.mesh = shield
		"head":
			var head: SphereMesh = SphereMesh.new()
			head.radius = 0.2
			head.height = 0.35
			instance.mesh = head
		"feet":
			var foot: BoxMesh = BoxMesh.new()
			foot.size = Vector3(0.18, 0.12, 0.32)
			instance.mesh = foot
		_:
			var body: BoxMesh = BoxMesh.new()
			body.size = Vector3(0.32, 0.22, 0.18)
			instance.mesh = body
	instance.material_override = material
	return instance

func play_technique(key: String, phase: String) -> void:
	if animation_player == null or resolver == null: return
	var motion := preload("res://src/world/technique_presentation.gd").motion_for(key, phase)
	if motion.is_empty() or not animation_player.has_animation(motion[0]): return
	var action := str(motion[1])
	if not resolver.action_to_clip.has(action): return
	var original: String = resolver.action_to_clip[action]
	# Override just this playback. The next ordinary attack keeps its normal
	# animation, including after an interrupted technique or changed equipment.
	resolver.action_to_clip[action] = str(motion[0])
	play_action(StringName(action), true)
	resolver.action_to_clip[action] = original

func begin_charge_leap(route: PackedVector3Array, seconds: float) -> void:
	var remote = RemotePresentationService.current()
	if remote != null: remote.detach(self, "charge")
	if current_action == &"death" or _cinematic_active or route.size() < 2: return
	for point in route:
		if not point.is_finite(): return
	var rendered_route := route.duplicate()
	rendered_route[0] = global_position
	_charge_leap = preload("res://src/actors/charge_leap_motion.gd").new(rendered_route, seconds)
	_snap_pending = false
	play_technique("charge", "activate")
	if animation_player != null and str(animation_player.current_animation) == "Technique_Charge_Leap":
		animation_player.speed_scale = animation_player.current_animation_length / _charge_leap.duration
	_wake()
	set_physics_process(true)

func end_charge_leap() -> void:
	if _charge_leap == null: return
	_charge_leap = null
	global_position = server_target
	_segment_start = server_target
	_segment_duration = 0.0
	_movement_coast_remaining = 0.0
	_last_movement_update_msec = -1
	_schedule_due = -1.0
	_travel_yaw_active = false
	_wake()

func play_action(action: StringName, restart := false) -> void:
	var remote = RemotePresentationService.current() if _remote_generation > 0 else null
	var timed: bool = remote != null and remote.owns(self)
	var started := Time.get_ticks_usec() if timed else 0
	if remote != null and not RemotePresentationService.ACTIONS.has(action): remote.detach(self, "custom_action")
	_play_action_legacy(action, restart)
	if remote != null: remote.sync_sink(self)
	if timed: remote.record_boundary("full_action_sink_us", Time.get_ticks_usec() - started)

func _play_action_legacy(action: StringName, restart := false) -> void:
	if _charge_leap != null:
		if action in [&"walk", &"run", &"idle", &"combat_idle", &"turn"]: return
		if action in [&"death", &"pain"]: end_charge_leap()
	# Death can precede the server's dismount snapshot. Release the seated
	# layer first so an active shot/channel cannot mask the full death clip.
	if action == &"death" and is_instance_valid(_mount_visual):
		set_mount_state({}, {})
	# Death is a latched state, including after its one-shot clip finishes.
	# Equipment/health snapshots and late combat commands must never restart it.
	if current_action == &"death":
		return
	if action == &"death" and (animation_player == null or resolver == null \
			or not resolver.action_to_clip.has("death") \
			or not animation_player.has_animation(resolver.clip_for_action(&"death"))):
		current_action = &"death"
		set_combat_target(false)
		_death_finished = true
		_death_elapsed = 0.0
		set_process(true)
		_refresh_stand_in()
		return
	if _cinematic_active and action != _cinematic_action:
		return
	# A kill can turn us toward the next aggressor without ending combat.
	# Keep both animation paths in guard until the engagement actually ends.
	if not _cinematic_active and _in_combat and action in [&"idle", &"turn"]:
		action = &"combat_idle"
	if is_instance_valid(_mount_visual):
		_mount_visual.call("play_action", action, restart)
		return
	if animation_player == null or resolver == null:
		return
	if not resolver.action_to_clip.has(String(action)):
		return
	var clip := resolver.clip_for_action(action)
	if clip.is_empty() or not animation_player.has_animation(clip):
		return
	animation_player.speed_scale = _playback_speed_for(action)
	if current_action == action and animation_player.is_playing() and not restart:
		return
	current_action = action
	if action == &"death":
		set_combat_target(false)
		_death_finished = false
		_death_elapsed = 0.0
		set_process(true)
	var blend := action_blend_seconds
	if action in [&"ranged_attack", &"pain", &"death"]:
		blend = 0.045
	elif action in [&"attack_primary", &"attack_secondary", &"cast_aggressive"]:
		blend = 0.09
	# Preview/cinematic cold starts retain their explicit reset semantics.
	# New strikes and hit reactions instead keep the pose they blend from.
	var cold_restart := restart and action not in [&"attack_primary", &"attack_secondary", &"pain"]
	if cold_restart:
		animation_player.stop(true)
	var had_pose := not cold_restart and not animation_player.assigned_animation.is_empty()
	# Playing the same name resumes its clock. An alias lets a new occurrence
	# start at zero while blending from the previous occurrence's current pose.
	# Only this actor owns the alias library; the animation itself stays shared.
	if restart and not cold_restart and animation_player.assigned_animation == clip:
		if not animation_player.has_animation_library(&"action_restarts"):
			animation_player.add_animation_library(&"action_restarts", AnimationLibrary.new())
		var replays := animation_player.get_animation_library(&"action_restarts")
		var key := StringName("clip_" + str(animation_player.get_animation(clip).get_instance_id()))
		if not replays.has_animation(key):
			replays.add_animation(key, animation_player.get_animation(clip))
		clip = StringName("action_restarts/" + str(key))
	# Several semantic actions share one physical loop (idle/turn, or a
	# flyer's walk/run). Crossfading that clip into itself clears corrective
	# morph weights in the mixer. Keep its clock and pose; only the semantic
	# action and playback speed change. Explicit restarts still restart.
	var same_loop := not restart and animation_player.is_playing() \
		and animation_player.assigned_animation == clip
	if not same_loop:
		animation_player.play(clip, blend)
	action_crossfade_seconds = blend / maxf(
		absf(animation_player.speed_scale), 0.01) if had_pose and not same_loop else 0.0
	# Retarget the facing correction to this action and ease to it over the same
	# crossfade the clips blend across, so the body's turn tracks the pose change
	# rather than snapping ahead of or behind it.
	var target: float = deg_to_rad(resolver.facing_offset_for_action(action))
	if not is_equal_approx(target, _facing_offset_to):
		_facing_offset_from = _facing_offset
		_facing_offset_to = target
		_facing_offset_elapsed = 0.0
		_wake()

## Walk and run clips animate in place, so the feet only stay planted when the
## clip runs at the speed the actor is actually travelling. Anything else -
## and a fixed 1.45 on a clip that covers 0.61 m/s while the server walks an
## actor at 1.86 m/s was a long way else - reads as sliding.
## Species with short strides can opt into a lower cycle-frequency ceiling,
## as mounts do, to keep their motion readable at the game's travel speeds.
##
## The ceiling is 3.5 so nothing in ordinary play reaches it. `Walk` covers
## 0.685 m/s at speed 1.0 against a walking pace of 1.67 m/s (2.43x), and
## `Run_Female` covers 2.666 against a running 5.0 m/s (1.88x). Only Speed Hax
## on top of a run - 10 m/s - asks for more than the ceiling.
func _playback_speed_for(action: StringName) -> float:
	if action == &"death" and _death_animation_seconds > 0.0 and animation_player != null:
		var clip := resolver.clip_for_action(action)
		if animation_player.has_animation(clip):
			return animation_player.get_animation(clip).length / _death_animation_seconds
	var stride: float = resolver.stride_speed_for_action(action, _small_creature_scale * server_scale)
	if stride <= 0.0:
		return resolver.playback_speed_for_action(action)
	var rate := clampf(_travel_speed() / stride, 0.35, 3.5)
	var maximum_cycles := float(resolver.maximum_cycles_per_second.get(String(action), 0.0))
	if maximum_cycles > 0.0 and animation_player != null:
		var clip := resolver.clip_for_action(action)
		if animation_player.has_animation(clip):
			rate = minf(rate, animation_player.get_animation(clip).length * maximum_cycles)
	return rate

## Metres per second the presentation is currently moving this actor. Falls
## back to the nominal speed for the command before the first step is timed.
func _travel_speed() -> float:
	if _charge_leap != null: return _charge_leap.length / _charge_leap.duration
	if _cinematic_active:
		return _cinematic_speed
	if _segment_duration <= 0.0:
		return _presentation_speed
	return _segment_start.distance_to(server_target) / _segment_duration

func _on_animation_finished(_animation_name: StringName) -> void:
	var remote = RemotePresentationService.current() if _remote_generation > 0 else null
	if current_action != &"death" and remote != null and remote.owns(self) and remote.finished(self): return
	# The server sends transition commands, not a second command for the resting
	# pose. Keep this explicit and data-driven through the action map.
	if current_action == &"death":
		_hold_death_pose()
	elif current_action == &"sit":
		play_action(&"seated_idle")
	elif current_action == &"stand":
		play_action(&"idle")
	elif current_action == &"ranged_draw":
		play_action(&"ranged_hold")
	elif current_action == &"cast_channel_enter":
		play_action(&"cast_channel")
	elif current_action in [&"cast", &"cast_aggressive", &"cast_defensive", &"heal",
		&"cast_exit", &"attack_primary", &"attack_secondary", &"defend", &"ranged_attack", &"pain"]:
		play_action(_movement_aware_action(&"combat_idle" if _in_combat else &"idle", false))

func presentation_action_time() -> float:
	if is_instance_valid(_mount_visual) and not _mount_visual.upper.action.is_empty():
		return float(_mount_visual.upper.time)
	return animation_player.current_animation_position if animation_player != null else 0.0

func presentation_action_length() -> float:
	if is_instance_valid(_mount_visual) and not _mount_visual.upper.action.is_empty():
		return float(_mount_visual.upper.duration())
	return animation_player.current_animation_length if animation_player != null else 0.0

func set_hand_props_visible(enabled: bool) -> void:
	for part: int in [0, 1]:
		for prop: Node in _equipment_nodes.get(part, []):
			if is_instance_valid(prop) and prop is Node3D:
				# Native bow variants are replaced by the string-driven bow in the left hand.
				(prop as Node3D).visible = enabled and not (
					part == 0 and _hand_prop_uses_ranged_animation())

func _invalidate_hand_prop_ranged_cache() -> void:
	_hand_prop_ranged_cache_valid = false
	_hand_prop_weapon_has_ranged_animation = false

func _ranged_bow_path(weapon: Dictionary) -> String:
	var path := str(weapon.get("rangedAnimationScene", ""))
	var scene := str(weapon.get("scene", ""))
	if str(weapon.get("attach", "")) == "ranged_bow" or RangerBow3D.supports_asset(scene): path = scene
	return path

func _hand_prop_uses_ranged_animation() -> bool:
	if not _hand_prop_ranged_cache_valid:
		var weapon := _equipment_model_config(0,
			int(_equipment_visuals.get(0, 0)))
		_hand_prop_weapon_has_ranged_animation = not _ranged_bow_path(weapon).is_empty()
		_hand_prop_ranged_cache_valid = true
	return _hand_prop_weapon_has_ranged_animation

func ranged_release_origin() -> Vector3:
	if combat_presentation != null and combat_presentation.bow != null and combat_presentation.bow.visible:
		return combat_presentation.bow.nock_position()
	return global_position + Vector3.UP * 1.1

func spell_release_origin() -> Vector3:
	var skeleton := get_skeleton()
	if skeleton != null:
		var left := skeleton.find_bone("hand_l")
		var right := skeleton.find_bone("hand_r")
		if left >= 0 and right >= 0:
			var left_hand := skeleton.global_transform * skeleton.get_bone_global_pose(left).origin
			var right_hand := skeleton.global_transform * skeleton.get_bone_global_pose(right).origin
			if current_action == &"heal":
				return left_hand if left_hand.y > right_hand.y else right_hand
			return (left_hand + right_hand) * 0.5
	return global_position + Vector3.UP * 1.1

func spell_target_position() -> Vector3:
	var skeleton := get_skeleton()
	if skeleton != null:
		var chest := skeleton.find_bone("spine_03")
		if chest >= 0:
			return skeleton.global_transform * skeleton.get_bone_global_pose(chest).origin
	return global_position + Vector3.UP * 1.0

func set_combat_effects_enabled(enabled: bool) -> void:
	if combat_presentation != null:
		combat_presentation.effects_enabled = enabled
		combat_presentation.update_pose()

func weapon_trail_tip() -> Variant:
	if is_instance_valid(_trail_weapon_mesh):
		return _trail_weapon_mesh.global_transform * _trail_weapon_tip
	# Find the end of the longest visible weapon mesh once per equipment swap.
	# This follows the actual blade instead of assuming a wrist-axis direction.
	var longest := 0.0
	for prop: Node in _equipment_nodes.get(0, []):
		if not is_instance_valid(prop):
			continue
		for mesh_node: MeshInstance3D in prop.find_children("*", "MeshInstance3D", true, false):
			if mesh_node.mesh == null:
				continue
			var bounds := mesh_node.mesh.get_aabb()
			var axis := bounds.size.max_axis_index()
			var length := bounds.size[axis] * mesh_node.global_basis.get_scale()[axis]
			if length <= longest:
				continue
			var a := bounds.get_center()
			var b := a
			a[axis] = bounds.position[axis]
			b[axis] = bounds.end[axis]
			# The tip is the end farther from the piece's own origin, which a
			# held prop is authored at or near its grip (the quarterstaff's
			# sits a hand's width below it). Not the end farther from the wrist:
			# a staff stood at the idle grip is held at its middle, and a swing
			# that asks for its first trail point while the grip is still
			# easing out of that would pick either end.
			var grip := (prop as Node3D).global_position
			if prop.get_child_count() > 0 and prop.get_child(0) is Node3D:
				grip = (prop.get_child(0) as Node3D).global_position
			grip = mesh_node.global_transform.affine_inverse() * grip
			_trail_weapon_tip = a if a.distance_squared_to(grip) > b.distance_squared_to(grip) else b
			_trail_weapon_mesh = mesh_node
			longest = length
	if is_instance_valid(_trail_weapon_mesh):
		return _trail_weapon_mesh.global_transform * _trail_weapon_tip
	return null

## Shows one 45 degree step immediately while the server's answer to
## TURN_LEFT/TURN_RIGHT is in flight. This is prediction, not authority: the
## first turn actor command the server broadcasts clears it and the
## authoritative facing takes over. Nothing here decides an outcome.
func predict_turn(radians: float) -> void:
	var remote = RemotePresentationService.current()
	if remote != null: remote.detach(self, "predicted_turn")
	if current_action == &"death":
		return
	_wake()
	_target_yaw = wrapf(_target_yaw + radians, -PI, PI)
	_predicted_turn_yaw = _target_yaw
	_predicted_turn_pending = true
	play_action(&"turn")

func desired_facing_yaw() -> float:
	return _target_yaw

## The server has reached casting range and supplied the facing before the
## channel starts. Finish the turn now so the channel never begins sideways.
func face_for_spell(yaw: float) -> void:
	if current_action == &"death": return
	_predicted_turn_pending = false
	_travel_yaw_active = false
	_movement_coast_remaining = 0.0
	_target_yaw = yaw
	rotation.y = yaw
	var remote = RemotePresentationService.current()
	if remote != null: remote.sync_transfer(self)
	_wake()

## Abandons a predicted turn the server has not answered. A route ordered
## before the answer arrives supersedes it: the step commands that route
## broadcasts state the facing, and holding the prediction over them would keep
## the actor pointing where it was asked to look rather than where it walks.
func clear_turn_prediction() -> void:
	_predicted_turn_pending = false

static func target_yaw_for_state(current_yaw: float, actor_command: int,
		server_rotation: int, adapter: CoordinateAdapter) -> float:
	var command_direction: Vector2i = EloriaProtocol.actor_command_direction(actor_command)
	if command_direction != Vector2i.ZERO:
		return adapter.direction_to_godot(command_direction)
	# Every other actor command - sitting, standing, entering combat, swinging
	# at someone - carries no rotation of its own. The rotation on the state is
	# the one the actor was last spawned with, so reading it here threw away
	# the facing the actor had been turned to: a creature that turned to face
	# the player it was attacking snapped back to its spawn facing on the very
	# next attack command it sent. Only a spawn packet, which carries no
	# command at all, states a facing this way.
	if actor_command >= 0:
		return current_yaw
	return adapter.rotation_to_godot(server_rotation)

## The yaw of the ground the body is about to cross, which is what "facing the
## way you are walking" means on screen. It is not the tile direction the
## server named: the rendered actor is deliberately a fraction of a tile behind
## its authoritative position (`arrival_margin`), and every step that lands in
## the same frame as another is folded into one segment before the actor node
## sees it, so a segment routinely spans a different bearing - and, across a
## folded burst, several tiles - than the single command that arrived with it.
static func travel_yaw(from: Vector3, to: Vector3, fallback: float) -> float:
	var travel := Vector3(to.x - from.x, 0.0, to.z - from.z)
	if travel.length_squared() < 0.000001:
		return fallback
	return atan2(-travel.x, -travel.z)

## Where the body is pointed this frame. The authoritative facing is still
## `_target_yaw`; this only decides what is drawn while the actor is crossing
## ground, and it hands back to the authoritative value the moment it stops, so
## a resting actor faces exactly where the server says it does. An unanswered
## turn prediction outranks it: that actor is turning on the spot rather than
## travelling, and the step it is asked to show is the whole point of it.
func _rendered_target_yaw() -> float:
	if _predicted_turn_pending or not _travel_yaw_active:
		return _target_yaw
	return _travel_yaw

func _finish_movement_presentation() -> void:
	if current_action in [&"walk", &"run"]:
		_movement_coast_remaining = maxf(movement_coast_seconds,
			_smoothed_server_interval * 0.75)

func set_selected(value: bool) -> void:
	_selected = value
	_sync_selection_marker()

func _sync_selection_marker() -> void:
	if _selection_ring != null:
		# Combat cleanup must not replace the attack circle with a corpse's selection circle.
		_selection_ring.visible = _selected and not _combat_target and _drawn and current_action != &"death"
		_level_selection_ring()

func set_target_marker_style(appearance: Dictionary) -> void:
	var next := TARGET_MARKER_STYLE.normalise(appearance)
	if next == _target_marker_style:
		return
	_target_marker_style = next
	_resize_selection()
	_level_selection_ring()

func set_combat_target(value: bool) -> void:
	var next := value and current_action != &"death"
	if next == _combat_target:
		return
	_combat_target = next
	if _combat_target and _combat_target_marker == null:
		_combat_target_marker = COMBAT_TARGET_MARKER.new()
		add_child(_combat_target_marker)
	_sync_combat_target_marker()

func _sync_combat_target_marker() -> void:
	_sync_selection_marker()
	if _combat_target_marker != null:
		_combat_target_marker.call("configure", _combat_target and _drawn,
			Vector2(footprint) * _metres_per_tile, head_height(), _target_marker_style)

## The height the ground was sampled at under the tile this actor is heading
## for. Main takes the sample after `apply_server_state` has already opened the
## step, so the value describes the far end of the step, not where the actor is
## standing now.
##
## That is why a step in progress only moves the target. `_segment_start` holds
## the height of the tile being left and `server_target` the one being entered,
## so the interpolation already walks the actor up or down the ledge between
## them. Writing the far tile's height straight onto the body as well put the
## actor a whole ledge-height out of place for the frames between this call and
## the next `_physics_process`, which recomputes the lerp and pulls it back:
## on terraced ground - Whitehorn Range steps more than half a metre across 46%
## of its adjacent tiles - every creature crossing a terrace popped and
## returned, several times a second across a populated map.
##
## A standing actor still snaps. Nothing is interpolating it, so a correction
## that never reached the body would leave it embedded in the ground it was
## measured against.
func set_surface_height(value: float, normal := Vector3.UP) -> void:
	_set_surface_normal(normal)
	var remote = RemotePresentationService.current() if _remote_generation > 0 else null
	if remote != null and remote.owns(self) and remote.surface(self, value): return
	if _charge_leap != null:
		server_target.y = value
		return
	if not _snap_pending and is_equal_approx(server_target.y, value):
		return
	server_target.y = value
	var mid_step: bool = _segment_duration > 0.0
	if _snap_pending or (not mid_step and absf(global_position.y - value) > 0.5):
		global_position.y = value
	_wake()

## Normals arrive once per destination tile, including preview terrain at a
## seam. Reject invalid contacts and bound steep facets before interpolating.
func _set_surface_normal(normal: Vector3) -> void:
	if _is_creature:
		return
	var next := Vector3.UP
	if normal.is_finite() and normal.length_squared() > 0.000001 and normal.y > 0.0:
		next = normal.normalized()
		var angle := Vector3.UP.angle_to(next)
		if angle > SURFACE_MAX_TILT:
			next = Vector3.UP.slerp(next, SURFACE_MAX_TILT / angle)
		elif angle < 0.005:
			next = Vector3.UP
	if next.is_equal_approx(_surface_target_up):
		return
	_surface_target_up = next
	if _snap_pending or _native_model == null:
		_surface_up = next
		_apply_surface_orientation()
	_wake()

func _advance_surface_orientation(delta: float, finish := false) -> void:
	if _is_creature:
		return
	# Flat ground needs no orientation work even while heading changes.
	if _surface_up == Vector3.UP and _surface_target_up == Vector3.UP and _surface_applied_up == Vector3.UP:
		return
	# A leap or scripted greeting owns its presentation while airborne/staged.
	var target := Vector3.UP if _charge_leap != null or _cinematic_active else _surface_target_up
	if not _surface_up.is_equal_approx(target):
		var angle := _surface_up.angle_to(target)
		var step := SURFACE_TURN_SPEED * maxf(0.0, delta)
		_surface_up = target if finish or angle <= maxf(step, 0.0001) else _surface_up.slerp(target, step / angle)
	_apply_surface_orientation()

## Restore the exact unleaned transform before scale/facing edits, avoiding
## accumulated rotations and keeping the mount's reference pose terrain-free.
func _clear_native_surface_tilt() -> void:
	if not _surface_native_tilted:
		return
	if is_instance_valid(_native_model):
		_native_model.transform = _surface_native_rest
	_surface_native_tilted = false
	_surface_applied_up = Vector3(NAN, NAN, NAN)

func _apply_surface_orientation() -> void:
	if _is_creature or _native_model == null:
		return
	if _surface_applied_up.is_equal_approx(_surface_up) and is_equal_approx(_surface_applied_yaw, rotation.y):
		return
	_clear_native_surface_tilt()
	var local_up := global_basis.inverse() * _surface_up
	var tilt := Quaternion(Vector3.UP, local_up.normalized())
	if is_instance_valid(_mount_visual):
		# The saddle solver already carries this frame onto the rider, tack,
		# reins and wardrobe, including the native batched pose path.
		var aligned := Transform3D(Basis(tilt), _mount_visual.position)
		# Carry the last rider pose with the mount between gated pose samples.
		# This costs one transform, without waking a skeleton/IK/cloth update.
		_native_model.transform = aligned * _mount_visual.transform.affine_inverse() * _native_model.transform
		_mount_visual.transform = aligned
	elif not _surface_up.is_equal_approx(Vector3.UP):
		_surface_native_rest = _native_model.transform
		_native_model.transform = Transform3D(Basis(Quaternion.IDENTITY.slerp(tilt,
			SURFACE_FOOT_WEIGHT)), Vector3.ZERO) * _surface_native_rest
		_surface_native_tilted = true
	_surface_applied_up = _surface_up
	_surface_applied_yaw = rotation.y

## The middle value of a set of per-tile intervals: the server's cadence as
## measured, with a held-back packet and the burst behind it both read
## through. `fallback` is returned for an empty set.
static func median_of(values: PackedFloat32Array, fallback: float) -> float:
	if values.is_empty():
		return fallback
	var ordered: PackedFloat32Array = values.duplicate()
	ordered.sort()
	var middle: int = ordered.size() / 2
	if ordered.size() % 2 == 1:
		return ordered[middle]
	return (ordered[middle - 1] + ordered[middle]) * 0.5

## Which pace history a step belongs to. The server holds a running step, a
## walking one and a hastened one for different lengths, so each is measured
## on its own: judged against one history, the first walking gap after a run
## was three steps late and a run after a walk three times early.
static func pace_gait(command: int, hastened: bool) -> int:
	return (1 if command >= 30 and command <= 37 else 0) | (2 if hastened else 0)

## Haste halves a known gait's interval. Use that relationship as soon as the
## buff changes, then let this gait's own measurements take over. Falling back
## to the previous step's interval carried walking pace into a new run/haste.
func _pace_for_gait(gait: int) -> float:
	if is_instance_valid(_mount_visual):
		return float(mount_state.get("step_us", 200000)) / 1000000.0
	var history: PackedFloat32Array = _pace_histories.get(gait, PackedFloat32Array())
	if not history.is_empty():
		return median_of(history, initial_server_interval)
	var counterpart: PackedFloat32Array = _pace_histories.get(gait ^ 2, PackedFloat32Array())
	if not counterpart.is_empty():
		return median_of(counterpart, initial_server_interval) * (0.5 if gait & 2 else 2.0)
	var interval := initial_run_interval if gait & 1 else initial_server_interval
	return interval * (0.5 if gait & 2 else 1.0)

func _movement_time_msec() -> int:
	return Time.get_ticks_msec()

## Whether a gap before a step is the actor standing still rather than the
## server's cadence arriving late: later than `expected_gap` by more than the
## gap itself or JITTER_PAUSE_SECONDS, whichever is less - past what any
## network hold the playout buffer covers.
static func is_pause_gap(observed: float, expected_gap: float) -> bool:
	return observed - expected_gap > minf(expected_gap, JITTER_PAUSE_SECONDS)

## Whether the last PACE_CONFIRM_STEPS pause-length gaps agree closely enough
## to be a cadence. A slowed pace repeats itself to within network jitter; a
## player stopping to loot between clicks does not.
static func confirms_new_pace(gaps: PackedFloat32Array) -> bool:
	if gaps.size() < PACE_CONFIRM_STEPS:
		return false
	var recent: PackedFloat32Array = gaps.slice(gaps.size() - PACE_CONFIRM_STEPS)
	var shortest: float = recent[0]
	var longest: float = recent[0]
	for gap: float in recent:
		shortest = minf(shortest, gap)
		longest = maxf(longest, gap)
	return longest <= shortest * PACE_CONFIRM_SPREAD

## The seconds of lateness the playout schedule keeps in hand, updated for one
## more step. A late step raises it to its own lateness at once; every step
## lets it decay by `decay`, so the allowance a hold earns outlives the next
## hold rather than being gone by the time it lands. Never more than `maximum`.
static func jitter_allowance(previous: float, lateness: float, decay: float,
		maximum: float) -> float:
	return clampf(maxf(lateness, previous * decay), 0.0, maximum)

## When the step that has just arrived should finish, in the same seconds as
## `now`. `last_due` is when the step before it was scheduled to finish, or
## anything earlier than `now` with no schedule; `cadence` is how long the
## server took over this step; `buffer` is how long after its arrival the
## step may finish at the earliest - the arrival margin plus the jitter
## allowance.
##
## On cadence the schedule simply continues, which is what keeps the speed on
## the ground constant whether the packet came early or late. A step that
## arrived too late for that is scheduled `buffer` after its arrival instead,
## pushing the schedule out: the body slows for one step and the buffer is
## restored. A schedule that has run ahead of what the buffer needs - a pace
## estimate a shade long, or the burst behind a hold - is trimmed back toward
## it at no more than `catch_up` times the pace, so the buffer settles on
## what the link asks for rather than drifting longer a few milliseconds a
## step; left to run half a step ahead, it did.
static func scheduled_arrival(now: float, last_due: float, cadence: float,
		buffer: float, catch_up: float) -> float:
	var continued: float = last_due + cadence
	var earliest: float = now + buffer
	if continued <= earliest:
		return earliest
	return maxf(earliest, last_due + cadence / maxf(catch_up, 1.0))

func _physics_process(delta: float) -> void:
	if not _remote_pending_transfer.is_empty():
		RemotePresentationService.restore_pending(self)
		if is_queued_for_deletion() or not _remote_pending_transfer.is_empty(): return
	var remote = RemotePresentationService.current() if _remote_generation > 0 else null
	if remote != null and remote.owns(self): return
	if (_speech_bubble_expiry_msec > 0
			and Time.get_ticks_msec() >= _speech_bubble_expiry_msec):
		clear_speech_bubble()
	if current_action == &"death":
		global_position = server_target
		_level_selection_ring()
		set_physics_process(false)
		return
	if _cinematic_active:
		global_position = _cinematic_position
		rotation.y = rotate_toward(rotation.y, _cinematic_yaw, turn_speed_radians * delta)
		_level_selection_ring()
		_advance_facing_offset(delta)
		_advance_surface_orientation(delta)
		return
	if _charge_leap != null:
		_charge_leap.elapsed += delta
		global_position = _charge_leap.position_at(_charge_leap.elapsed)
		var forward: Vector3 = _charge_leap.points[-1] - _charge_leap.points[0]
		rotation.y = rotate_toward(rotation.y, atan2(-forward.x, -forward.z), turn_speed_radians * delta)
		_advance_facing_offset(delta)
		_advance_surface_orientation(delta)
		# A delayed final movement packet must not pull the landed player back
		# to the previous tile. Briefly hold the approved endpoint for confirmation.
		if _charge_leap.elapsed >= _charge_leap.duration and (server_target.distance_to(_charge_leap.points[-1]) < 0.15 \
				or _charge_leap.elapsed >= _charge_leap.duration + 0.35):
			end_charge_leap()
			play_technique("charge", "land")
		return
	if _snap_pending:
		global_position = server_target
		rotation.y = _target_yaw
		_level_selection_ring()
		_segment_start = server_target
		_snap_pending = false
		_travel_yaw_active = false
		_advance_surface_orientation(delta)
		_settle_if_idle()
		return
	if _segment_duration > 0.0:
		_segment_elapsed = minf(_segment_elapsed + delta, _segment_duration)
		var progress: float = _segment_elapsed / _segment_duration
		global_position = _segment_start.lerp(server_target, progress)
		if progress >= 1.0:
			global_position = server_target
			_segment_duration = 0.0
			_travel_yaw_active = false
			_finish_movement_presentation()
	else:
		global_position = server_target
		_travel_yaw_active = false
	rotation.y = rotate_toward(rotation.y, _rendered_target_yaw(),
		turn_speed_radians * delta)
	_level_selection_ring()
	_advance_facing_offset(delta)
	_advance_surface_orientation(delta)
	if _movement_coast_remaining > 0.0:
		_movement_coast_remaining = maxf(0.0, _movement_coast_remaining - delta)
		if _movement_coast_remaining <= 0.0 and current_action in [&"walk", &"run"]:
			play_action(&"idle")
	_settle_if_idle()

## A standing actor reproduced the same transform 60 times a second. Once the
## interpolation segment has finished and the actor faces where the server says
## it should, the node is snapped exactly onto its target and physics processing
## stops until the next packet, keypress or surface sample wakes it. Nothing
## about the resulting pose differs from the value the loop kept rewriting.
func _settle_if_idle() -> void:
	if _cinematic_active or _charge_leap != null:
		return
	if _snap_pending or _segment_duration > 0.0 or _movement_coast_remaining > 0.0:
		return
	if absf(wrapf(_target_yaw - rotation.y, -PI, PI)) > SETTLED_YAW_EPSILON:
		return
	# Do not stop processing until the facing correction has finished easing to
	# the resting action's value, or an actor caught mid-ease from a walk would
	# freeze holding the walk's turn.
	if not is_equal_approx(_facing_offset, _facing_offset_to):
		return
	if not _surface_up.is_equal_approx(_surface_target_up):
		return
	global_position = server_target
	rotation.y = _target_yaw
	_settled = true
	set_physics_process(false)

## A per-view greeting temporarily owns the rendered pose. Network targets
## continue updating normally and are restored when the greeting ends.
func set_cinematic_presentation(point: Vector3, yaw: float, action: StringName, speed := 0.0) -> void:
	var remote = RemotePresentationService.current()
	if remote != null: remote.detach(self, "cinematic")
	end_charge_leap()
	_cinematic_active = true
	_cinematic_position = point
	_cinematic_yaw = yaw
	_cinematic_action = action
	_cinematic_speed = speed
	global_position = point
	play_action(action)
	_wake()

func cinematic_action_duration(action: StringName) -> float:
	if resolver == null or animation_player == null:
		return 2.0
	var clip := resolver.clip_for_action(action)
	if not animation_player.has_animation(clip):
		return 2.0
	return animation_player.get_animation(clip).length / resolver.playback_speed_for_action(action)

func end_cinematic_presentation() -> void:
	_cinematic_active = false
	global_position = server_target
	rotation.y = _target_yaw
	play_action(&"idle")
	_wake()

## Eases the model's facing correction toward the current action's value across
## the animation crossfade and writes it onto the visual root. A no-op once the
## two agree, so a resting actor pays nothing for it.
func _advance_facing_offset(delta: float) -> void:
	if is_instance_valid(_mount_visual):
		return
	if _native_model == null or is_equal_approx(_facing_offset, _facing_offset_to):
		return
	_clear_native_surface_tilt()
	_facing_offset_elapsed += delta
	var progress: float = 1.0 if action_blend_seconds <= 0.0 else clampf(
		_facing_offset_elapsed / action_blend_seconds, 0.0, 1.0)
	_facing_offset = lerp_angle(_facing_offset_from, _facing_offset_to, progress)
	if progress >= 1.0:
		_facing_offset = _facing_offset_to
	_native_model.rotation.y = _base_model_yaw + _facing_offset

func _wake() -> void:
	var remote = RemotePresentationService.current() if _remote_generation > 0 else null
	if remote != null and remote.owns(self):
		remote.sync_sink(self, true)
		if remote.owns(self): return
	# Death can pause physics before a moving body settles. Revival must
	# restart that body too, rather than waiting for a distance-correction snap.
	if not _settled and is_physics_processing():
		return
	_settled = false
	set_physics_process(true)

## How far this actor reaches from its foot point, for the gate's frustum
## test: the body as drawn plus the banner over it, on the widest side of
## the ground it holds.
func view_radius() -> float:
	var radius := (NAMEPLATE_HEIGHT + 0.6) * maxf(server_scale, 0.01) \
		* float(maxi(footprint.x, footprint.y))
	if is_instance_valid(_mount_visual):
		radius = maxf(radius, float(_mount_visual.call("presentation_view_radius")))
	return radius

## The child carrying this actor's mark on the full map, and the one thing left
## drawn when the actor itself is too far away to be worth drawing. A dot on a
## map is how a player finds someone across the water; their name floating over
## the water is not.
const MAP_DOT_NODE := &"MapDot"


## Whether this actor is near enough to draw. Out of range its body, its
## nameplate and its bars are hidden and only its map dot is left, so it still
## marks the maps while a viewport it is a speck in is left clear.
func set_drawn(enabled: bool) -> void:
	if enabled:
		if _drawn:
			return
		_drawn = true
		for node: Node3D in _hidden_by_range:
			if is_instance_valid(node):
				node.visible = true
		_hidden_by_range.clear()
		# What was showing when it went out of range need not be now: the name
		# may have faded, or the banner options changed, in the meantime.
		_refresh_overhead()
		_sync_combat_target_marker()
		_refresh_stand_in()
		return
	# Swept on every call rather than only on the way out. An actor out of range
	# still takes packets: it can change what it is wearing, or lose the model it
	# was drawn with, and the child that arrives to say so arrives visible.
	_drawn = false
	for child: Node in get_children():
		var node := child as Node3D
		if node == null or node.name == MAP_DOT_NODE or node == _stand_in or not node.visible:
			continue
		node.visible = false
		_hidden_by_range.append(node)
	_refresh_stand_in()


func is_drawn() -> bool:
	return _drawn


## Puts this actor's animation in one of the gate's tiers; see AnimationGate.
##
## A clip that does not loop - sitting down, standing up - is played out
## whatever the tier asks. Paused, the actor would be left caught mid-move and
## then seen finishing it when it came back into view. With the crowd gate on
## (`AnimationGate.gate_skeletons`) a body out of view plays it out at half
## rate, or quarter with the crowd's quarter tier (`AnimationGate.one_shot_tier`),
## which finishes it at the same speed: in a fight the bodies behind the
## camera strike every round, and each strike woke them to full rate.
func set_animation_tier(tier: int, gate: AnimationGate) -> void:
	_animation_gate_owner = gate
	if is_instance_valid(_mount_visual):
		# The mounted manager owns both pose clocks. Keep this player out of the
		# gate's stepped membership so an old half-rate group cannot pose it too.
		_take_mounted_animation_ownership(gate)
		_mount_visual.call("set_animation_tier", tier, gate.one_shot_tier, gate.gate_skeletons, gate.stagger)
		return
	if animation_player == null:
		return
	if tier != AnimationGate.Tier.FULL and _playing_one_shot():
		if not gate.gate_skeletons:
			tier = AnimationGate.Tier.FULL
		elif tier == AnimationGate.Tier.PAUSED:
			tier = gate.one_shot_tier
	if tier == _animation_tier:
		return
	_animation_tier = tier
	gate.apply(animation_player, tier, _native_skeleton)
	if gate.gate_skeletons:
		_set_model_processing(tier != AnimationGate.Tier.PAUSED)
	if _weapon_carry != null:
		_weapon_carry.call("update_activity")
	_refresh_cape_cloth_activity()

func animation_tier() -> int:
	return _animation_tier

func _set_mounted_animation_tier(tier: int) -> void:
	_animation_tier = tier
	_set_model_processing(tier != AnimationGate.Tier.PAUSED)
	_refresh_cape_cloth_activity()

func _take_mounted_animation_ownership(gate: AnimationGate) -> void:
	# A paused ordinary player uses idle callbacks. A mounted player instead
	# stays manual and inactive while the manager owns explicit pose sampling.
	# Membership-only removal avoids an idle/manual callback-mode round trip.
	gate.discard(animation_player)
	if animation_player != null:
		animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		animation_player.active = false

func _restore_unmounted_animation_gate() -> void:
	if _animation_gate_owner != null:
		var tier := _animation_tier
		_animation_tier = -1 # Reapply even when the effective tier is unchanged.
		set_animation_tier(tier, _animation_gate_owner)
	elif animation_player != null:
		animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
		animation_player.active = true
		_set_model_processing(true)
		if _native_skeleton != null:
			_native_skeleton.modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_IDLE

## A parked body (crowd_presentation.gd) is hidden while it waits to be worn
## again, so nothing of it animates, whatever clip it was in: paused here, it
## leaves the gate's stepped groups, which otherwise went on posing, solving and
## skinning it every second or fourth frame for as long as it was parked.
func pause_for_parking(gate: AnimationGate) -> void:
	var remote = RemotePresentationService.current()
	if remote != null: remote.detach(self, "parked")
	_animation_gate_owner = gate
	if is_instance_valid(_mount_visual):
		_take_mounted_animation_ownership(gate)
		_mount_visual.call("pause_for_parking")
		return
	if animation_player == null:
		return
	_animation_tier = AnimationGate.Tier.PAUSED
	gate.apply(animation_player, AnimationGate.Tier.PAUSED, _native_skeleton)
	if gate.gate_skeletons:
		_set_model_processing(false)
	if _weapon_carry != null:
		_weapon_carry.call("update_activity")
	_refresh_cape_cloth_activity()

## A paused body has nothing to pose: its player is stopped and its cloth is
## asleep. Its skeleton still processed its modifiers and updated every frame,
## though, so a crowd paid skeleton work for every body off screen (the engine
## profile counted 300 skeleton updates a frame with 150 actors in view).
## Disabling the model's subtree stops that until the body is woken.
func _set_model_processing(enabled: bool) -> void:
	if is_instance_valid(_native_model):
		_native_model.process_mode = (Node.PROCESS_MODE_INHERIT if enabled
			else Node.PROCESS_MODE_DISABLED)

func model_processing() -> bool:
	return not is_instance_valid(_native_model) \
		or _native_model.process_mode != Node.PROCESS_MODE_DISABLED

## Whether this actor still waits for its body; see `_model_deferred`.
func is_model_deferred() -> bool:
	return _model_deferred

## A plain capsule where a deferred actor's body will be, so a crowd walking
## into view is not empty ground for the frames it takes to build. One mesh and
## one material are shared by every stand-in; it casts no shadow and is drawn
## by the gameplay camera only.
func _add_stand_in() -> void:
	if _stand_in_mesh == null:
		_stand_in_mesh = CapsuleMesh.new()
		_stand_in_mesh.radius = 0.3
		_stand_in_mesh.height = 1.6
		_stand_in_mesh.radial_segments = 8
		_stand_in_mesh.rings = 2
		_stand_in_material = StandardMaterial3D.new()
		_stand_in_material.albedo_color = Color(0.34, 0.31, 0.28)
		_stand_in_material.roughness = 1.0
		_stand_in_mesh.material = _stand_in_material
	_stand_in = MeshInstance3D.new()
	_stand_in.name = "StandIn"
	_stand_in.mesh = _stand_in_mesh
	_stand_in.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_stand_in.layers = GAMEPLAY_ONLY_VISUAL_LAYER
	add_child(_stand_in)
	_size_stand_in()
	_refresh_stand_in()

## The stand-in shows while this actor is drawn, alive and not over the body cap.
func _refresh_stand_in() -> void:
	if is_instance_valid(_stand_in):
		_stand_in.visible = _drawn and not _crowd_hidden and current_action != &"death"

func stand_in_visible() -> bool:
	return is_instance_valid(_stand_in) and _stand_in.visible

## See `_crowd_hidden`.
func set_crowd_hidden(hidden: bool) -> void:
	if hidden == _crowd_hidden:
		return
	_crowd_hidden = hidden
	collision_layer = 0 if hidden else (0 if _is_creature and _health_current == 0 else 2)
	_refresh_stand_in()
	_refresh_overhead()

func crowd_hidden() -> bool:
	return _crowd_hidden

func _size_stand_in() -> void:
	if not is_instance_valid(_stand_in):
		return
	var span: float = float(maxi(footprint.x, footprint.y)) * _metres_per_tile
	var height: float = (0.8 if _is_creature else 1.0) * server_scale
	_stand_in.scale = Vector3(span, height, span)
	_stand_in.position.y = 0.8 * height

## Whether this is a corpse that has already faded out of sight, which no body
## needs to be built for.
func corpse_faded() -> bool:
	if current_action != &"death" or not (_corpse_temporary or _is_creature):
		return false
	var hold := (CREATURE_DISSOLVE_DELAY_SECONDS if _is_creature and _corpse_temporary
		else _corpse_hold_seconds)
	return _death_elapsed >= _death_duration() + hold + _corpse_fade_seconds

func creature_death_in_progress() -> bool:
	return _is_creature and current_action == &"death" and not corpse_faded()

## What the server has told a node this one replaces about its last command,
## taken before this one applies the same record: a swing already shown by the
## replaced body, or not shown because it had none, is not started again by
## the body that takes over. Call between `configure` and `apply_server_state`.
func adopt_command_memory_from(previous: ReplicatedActor3D) -> void:
	var remote = RemotePresentationService.current()
	if remote != null and is_instance_valid(previous): remote.detach(previous, "body_transfer")
	if previous == null or not is_instance_valid(previous) or previous == self:
		return
	_last_command_sequence = previous._last_command_sequence
	_in_combat = previous._in_combat
	_swing_index = previous._swing_index

## Carries a replaced node's motion into this one: the body Main builds in a
## deferred actor's place, or the deferred actor that replaces a body gone far
## out of range, carries on with the step it is on and the pace it has learned
## instead of snapping to the tile and relearning the server's cadence. A death
## keeps its time, so a corpse coming into view is not seen dying again. Call
## after this node has applied the same record and been put on the ground.
func adopt_presentation_from(previous: ReplicatedActor3D) -> void:
	if previous == null or not is_instance_valid(previous) or previous == self:
		return
	if current_action == &"death" and previous.current_action == &"death":
		_death_elapsed = maxf(_death_elapsed, previous._death_elapsed)
		if animation_player != null and resolver != null:
			var clip := resolver.clip_for_action(&"death")
			if animation_player.has_animation(clip):
				animation_player.seek(minf(_death_elapsed * animation_player.speed_scale,
					animation_player.get_animation(clip).length), true)
		_update_corpse_pose()
		global_position = server_target
		return
	if _charge_leap != null or _cinematic_active or previous._charge_leap != null \
			or previous._cinematic_active:
		return
	global_position = previous.global_position
	rotation.y = previous.rotation.y
	_target_yaw = previous._target_yaw
	_segment_start = previous._segment_start
	_segment_elapsed = previous._segment_elapsed
	_segment_duration = previous._segment_duration
	_schedule_due = previous._schedule_due
	_last_movement_update_msec = previous._last_movement_update_msec
	_smoothed_server_interval = previous._smoothed_server_interval
	_pace_histories = previous._pace_histories.duplicate(true)
	_unconfirmed_paces = previous._unconfirmed_paces.duplicate()
	_unconfirmed_gait = previous._unconfirmed_gait
	_previous_step_gait = previous._previous_step_gait
	_previous_step_tiles = previous._previous_step_tiles
	_jitter_allowance = previous._jitter_allowance
	_travel_yaw_active = previous._travel_yaw_active
	_travel_yaw = previous._travel_yaw
	_movement_coast_remaining = previous._movement_coast_remaining
	_presentation_speed = previous._presentation_speed
	_surface_up = previous._surface_up
	_surface_target_up = previous._surface_target_up
	_surface_applied_up = Vector3(NAN, NAN, NAN)
	_apply_surface_orientation()
	_snap_pending = false
	_settled = false
	set_physics_process(true)
	if (_segment_duration > 0.0 or _movement_coast_remaining > 0.0) \
			and current_action in [&"idle", &"combat_idle", &"turn"]:
		play_action(_paced_travel_action(&"run" if _previous_step_gait & 1 else &"walk"))

func _playing_one_shot() -> bool:
	if not animation_player.is_playing():
		return false
	var clip: String = animation_player.current_animation
	if clip.is_empty() or not animation_player.has_animation(clip):
		return false
	return animation_player.get_animation(clip).loop_mode == Animation.LOOP_NONE

func _load_native_scene(path: String) -> Array[String]:
	if path.is_empty():
		return ["model scene path missing"]
	var model := GlbSceneCache.instantiate(path)
	if model == null:
		return ["model glTF import failed", path]
	model.name = "NativeModel"
	add_child(model)
	return []

# Parsed equipment geometry, cached for the session. Only resources and plain
# data are held: caching the imported Node3D scenes instead would keep hundreds
# of nodes alive with no owner to free them.
static var _equipment_pieces_cache: Dictionary = {}
static var _rebound_skins: Dictionary = {}
## The worn torso's reach, and the cape surfaces cut to clear it. Both depend
## only on the two scenes, so both are shared by every actor wearing the pair
## rather than measured per actor: the envelope walks a few thousand vertices
## and the drape rebuilds a surface, and a populated map would pay for it once
## per wearer otherwise.
static var _drape_envelopes: Dictionary = {}
static var _draped_capes: Dictionary = {}
static var _torso_reaches: Dictionary = {}
static var _fabric_lines: Dictionary = {}
static var _shin_reaches: Dictionary = {}

static func _equipment_pieces(path: String) -> Array:
	# One cached scene instance per equipment model. In production this comes
	# from Godot's imported PackedScene and therefore retains generated LODs;
	# external test candidates and lean checkouts use GlbSceneCache's raw fallback.
	if _equipment_pieces_cache.has(path):
		return _equipment_pieces_cache[path] as Array
	var pieces: Array = []
	var imported := GlbSceneCache.instantiate(path)
	if imported == null:
		return pieces
	var mesh_nodes: Array[MeshInstance3D] = []
	var embedded_extras := false
	for node_value: Node in imported.find_children("*", "MeshInstance3D", true, false):
		var found := node_value as MeshInstance3D
		if found.mesh == null:
			continue
		mesh_nodes.append(found)
		embedded_extras = embedded_extras or found.mesh.has_meta(&"extras")
	# Godot preserves glTF mesh extras as ArrayMesh metadata in its imported
	# PackedScene, including in an exported PCK where the raw source GLB may be
	# omitted. The JSON-only reader is the fallback for importers/candidates that
	# do not carry that metadata; it never performs a second geometry import.
	var extras_by_name: Dictionary = ({}
		if embedded_extras else GLB_MESH_EXTRAS.read(path))
	var skeleton: Skeleton3D = null
	for node_value: Node in imported.find_children("*", "Skeleton3D", true, false):
		skeleton = node_value as Skeleton3D
		break
	for mesh_node: MeshInstance3D in mesh_nodes:
		var extras: Dictionary = mesh_node.mesh.get_meta(&"extras", {}) as Dictionary
		if not embedded_extras:
			extras = extras_by_name.get(str(mesh_node.name), {}) as Dictionary
			if extras.is_empty() and not mesh_node.mesh.resource_name.is_empty():
				extras = extras_by_name.get(mesh_node.mesh.resource_name, {}) as Dictionary
		var surface_overrides: Array[Material] = []
		for surface: int in mesh_node.mesh.get_surface_count():
			surface_overrides.append(mesh_node.get_surface_override_material(surface))
		pieces.append({
			"mesh": mesh_node.mesh,
			"name": str(mesh_node.name),
			"body_cover": extras.get("bodyCover", []),
			"covers_hair": extras.get("coversHair", false),
			"transform": _relative_transform(mesh_node, imported),
			"bones": _skin_bone_names(mesh_node.skin, skeleton),
			"binds": _skin_bind_poses(mesh_node.skin),
			"material_override": mesh_node.material_override,
			"surface_overrides": surface_overrides,
			"lod_bias": mesh_node.lod_bias,
			"cast_shadow": mesh_node.cast_shadow,
		})
	imported.free()
	if not pieces.is_empty():
		_equipment_pieces_cache[path] = pieces
	return pieces

static func _relative_transform(node: Node3D, root: Node3D) -> Transform3D:
	# Accumulated by hand: global_transform is only meaningful inside the tree,
	# and the cached instance is inspected without ever being added to one.
	var accumulated: Transform3D = Transform3D.IDENTITY
	var walker: Node3D = node
	while walker != null and walker != root:
		accumulated = walker.transform * accumulated
		walker = walker.get_parent() as Node3D
	return accumulated

static func _skin_bind_poses(skin: Skin) -> Array[Transform3D]:
	# The garment's own inverse bind poses: where each bone stood on the rig the
	# garment was authored against.  Retargeting needs them; the old rebind threw
	# them away and so could only ever scale the garment.
	var poses: Array[Transform3D] = []
	if skin == null:
		return poses
	for index: int in range(skin.get_bind_count()):
		poses.append(skin.get_bind_pose(index))
	return poses

static func _skin_bone_names(skin: Skin, skeleton: Skeleton3D) -> PackedStringArray:
	var names: PackedStringArray = PackedStringArray()
	if skin == null:
		return names
	for index: int in range(skin.get_bind_count()):
		var bone_name: String = skin.get_bind_name(index)
		if bone_name.is_empty() and skeleton != null:
			var source_bone: int = skin.get_bind_bone(index)
			if source_bone >= 0 and source_bone < skeleton.get_bone_count():
				bone_name = skeleton.get_bone_name(source_bone)
		names.append(bone_name)
	return names

func _apply_import_adapter(config: Dictionary) -> void:
	var model := get_node_or_null("NativeModel") as Node3D
	if model == null:
		return
	_import_scale = float(config.get("scale", 1.0))
	_apply_model_scale()
	# The two rig families are authored facing opposite ways: the race rigs
	# down +Z to face the creation-preview camera, the creature rigs down -Z,
	# which is already Godot's logical forward axis. Each model states its own
	# correction, so a creature is not turned round and walked backwards. The
	# 180 fallback is only for a model that predates the key. Correct only the
	# imported visual root so server yaw, click targets, keyboard-relative
	# movement, and equipment attachments continue to share one canonical
	# logical heading.
	var forward_axis_correction: float = float(
		config.get("forwardAxisCorrectionDegreesY", 180.0))
	model.rotation_degrees = Vector3(
		float(config.get("rotationDegreesX", 0.0)),
		float(config.get("rotationDegreesY", 0.0)) + forward_axis_correction,
		float(config.get("rotationDegreesZ", 0.0)))
	# The base the per-action facing correction is measured from. Kept in radians
	# because `_physics_process` adds the eased offset to it every frame.
	_native_model = model
	_base_model_yaw = deg_to_rad(model.rotation_degrees.y)
	# The protocol position is a foot point. Normalize the imported visual at
	# its root without flattening or rewriting the glTF hierarchy/skeleton.
	var bounds: AABB = _native_visual_bounds(model)
	_native_body_bounds = bounds
	if bounds.size.y > 0.0:
		model.position.y = -bounds.position.y
	_apply_model_scale()
	_lift_overhead(server_scale)

func _validate_native_visual() -> String:
	var native_model: Node3D = get_node_or_null("NativeModel") as Node3D
	if native_model == null:
		return "native model root missing"
	var visible_meshes: int = 0
	for node_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		if mesh_node.mesh != null and mesh_node.visible and mesh_node.layers != 0:
			visible_meshes += 1
	return "native model has no renderable meshes" if visible_meshes == 0 else ""

func _native_visual_bounds(model: Node3D) -> AABB:
	var combined: AABB = AABB()
	var initialized: bool = false
	var to_model: Transform3D = model.global_transform.affine_inverse()
	for node_value: Node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		if mesh_node.mesh == null:
			continue
		var relative: Transform3D = to_model * mesh_node.global_transform
		var mesh_bounds: AABB = relative * mesh_node.get_aabb()
		combined = combined.merge(mesh_bounds) if initialized else mesh_bounds
		initialized = true
	return combined

static func _external_path(path: String) -> String:
	return ProjectSettings.globalize_path(path) if path.begins_with("res://") else path

var _spell_variants: Dictionary = {}
var _spell_base_clips: Dictionary = {}

func set_spell_variant(effect: int) -> void:
	if animation_player == null or resolver == null: return
	if _spell_variants.is_empty():
		for action: String in ["cast_aggressive", "cast_defensive", "heal"]:
			_spell_base_clips[action] = resolver.clip_for_action(action)
		_spell_variants = SpellAnimationLibrary.install(animation_player, resolver)
	var action := str(SpellPresentation.action_for_effect(effect))
	if effect in [3, 6, 72, 74, 76, 77, 78, 80, 81, 82, 92]: effect = 75
	if _spell_base_clips.has(action):
		resolver.action_to_clip[action] = _spell_variants.get(effect, _spell_base_clips[action])

func _enter_tree() -> void:
	call_deferred("_restore_remote_pending")

func _restore_remote_pending() -> void:
	RemotePresentationService.restore_pending(self)

func _exit_tree() -> void:
	var remote = RemotePresentationService.current()
	if remote != null: remote.release_departing(self)
