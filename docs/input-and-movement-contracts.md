# Input and movement contracts

Several client behaviours are decided in two places that no type check holds
together: the pointer and the click handler, the item slots and the server's
storage order, and the presented walk and the server's step timing. Change one
side and check the other. Paths below are relative to `godot-client/`.

## World clicks

A world click is decided twice. `MouseCursors.choose` (`src/ui/mouse_cursors.gd`)
picks the pointer from `_cursor_context()`, so the pointer says what a click
will do before it is spent. `_actor_click_action` (`src/app/main.gd`) decides
what a left click on an actor sends: `attack`, `trade`, `talk`, `look`, `spell`
or `none`. `_handle_world_click` dispatches on that answer, and right-click
cycling (`_available_world_actions_at`) asks the same function, so a tool is
offered only where it would act.

- Put new actor-click behaviour in `_actor_click_action`, not in another branch
  of `_handle_world_click`, or the pointer promises an action the handler never
  sends. `tests/test_world_input.gd` `_check_actor_click_actions` holds the two
  against each other for every actor kind.
- In the default Move mode a plain click attacks a live creature, greets an
  NPC and gives your own summon an order. A player is attacked only in Fight
  mode or with Alt held. A pending actor spell claims any actor under the
  pointer, including yourself. Other tools never turn a missed target into a
  walk.
- Holding Alt also suppresses the empty-ground walk in Move mode and shows
  the attack sword. Releasing Alt restores ordinary clicks. The saved
  `ranging_lock` preference (default shortcut Alt+R, rebindable as
  `toggle_range_lock`) blocks ground/map movement while a ranged weapon is
  equipped, but must still permit actor attacks. Sit lock, death and modal
  input blocking continue to apply to attacks. `tests/test_range_lock.gd`
  checks the shortcut, saved preference and outgoing attack/movement frames.
- The Trade icon arms a mode, as in Eternal Lands (`_on_trade_button_pressed`).
  A player already selected is asked at once; otherwise the next click on a
  player asks them. `Esc` or the Move icon puts the mode down. Covered by
  `_check_trade_mode` in the same test.

## Item clicks

Item slots follow the Eternal Lands model: they act on the mouse press, and a
carried item stays on the cursor until another click places it.

- Inventory, equipment, ground-bag and quickbar slots, and the classic storage
  cells (`src/ui/classic_storage_workspace.gd`), use
  `BaseButton.ACTION_MODE_BUTTON_PRESS`. Acting on the release lost clicks whose
  release slid onto the next slot. A slot's `gui_input` handler runs before the
  button sees the press, so double-click (wear or take off) is taken there.
- With the grab tool, one click lifts a stack and the next places it. A world
  click drops the selected quantity and keeps the rest in hand (`_drop_carry`;
  Ctrl drops the whole stack). Right-click cancels a carry before it cycles the
  inventory tool. Alt+click stores a whole stack while storage is open.
- A stored stack in hand is withdrawn by any click on the backpack; the
  equipment grid ignores it. Storage positions index the server's sorted
  storage list and shift when a kind of item enters or leaves, so the carry is
  re-found by picture and name (`_storage_carry_item`), never by the position
  it was lifted from.
- `tests/test_classic_storage.gd` `_check_el_clicks` and
  `tests/test_world_input.gd` `_check_item_clicks` push real mouse events and
  read the requests sent.

## Movement presentation

The server paces player steps. `ReplicatedActor3D.apply_server_state`
(`src/actors/replicated_actor_3d.gd`) measures that cadence and schedules each
step so the body crosses the ground at one speed whenever its packet arrives.

- `initial_server_interval` (walking) and `initial_run_interval` must equal the
  server's player walk and run intervals, in seconds per tile. They pace the
  first steps before any cadence is measured. A default longer than the real
  pace lets the lag grow every step, and because the rendered facing is the
  chord toward the tile being crossed, the body also turns off its travel line.
- Pace is measured per tile, not per step: a diagonal crosses 1.41 tiles and is
  held 1.41 times as long. The gap before a packet is the hold of the previous
  step, so it is divided by that step's tiles and recorded in that step's gait.
- Walking, running and their hastened forms each keep their own history,
  selected by `pace_gait`; the pace is the median of the last `PACE_WINDOW`
  samples. Haste halves a known gait's interval until its own samples arrive.
- A gap that `is_pause_gap` judges a player standing still is not sampled.
  `confirms_new_pace` accepts a real slowdown only after `PACE_CONFIRM_STEPS`
  agreeing gaps.
- `scheduled_arrival` continues the schedule on cadence. A step too late for
  that finishes `arrival_margin` times the cadence plus the jitter allowance
  after it arrives; the allowance (`jitter_allowance`) keeps the worst recent
  lateness, decays per step and is capped at `maximum_buffer_seconds`. A
  schedule ahead of the buffer is trimmed back at no more than
  `catch_up_factor` times the pace.
- Facing comes from the burst's `facing_command`: of the commands reduced
  before a frame presents the actor, the last one that named a direction
  (kept by `src/state/actor_reducer.gd`). The last command is often the swing
  that followed the turn.
- A step's arrival time is when Main's world sync presents it
  (`_movement_time_msec`), so it is quantised to the frame. `Network` reads the
  socket twice a frame, first and again just before that sync, and each read
  takes every waiting TLS record (`src/network/network_client.gd`); see
  "Reading the game socket" in `docs/runtime-performance.md`. Feeding
  sub-frame arrival times into this pacing would also shrink the jitter
  allowance that today covers the next packet's own presentation delay, so it
  needs a presentation-delay term and an `actor_facing.gd` run of its own.
- Validate with `tests/integration/actor_facing.gd` under
  `--rendering-method gl_compatibility`. It checks facing and lag in all eight
  directions, one ground speed across step shapes, a jittered run, pauses
  between bags and a genuine slowdown. `tests/test_protocol.gd` covers the
  schedule helpers.

## Known gap: HUD icon frames

The HUD icon buttons on the quickbar (`GameView/Quickbar/QuickRows/Buttons`)
are set to `flat = true` in `_apply_eloria_theme`. Godot draws no state StyleBox for a
flat button, so the `hover`, `pressed` and `hover_pressed` overrides set beside
it never appear. `_sync_hud_button_states` still sets the pressed state, but an
armed mode or an open window shows no lit frame. Tests read the pressed state,
not pixels, so check any fix in a rendered capture.
