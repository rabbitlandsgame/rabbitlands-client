# Player interest, presence, server time and mount deltas (client side)

A crowded shard cannot send every player on a map to every client, and a
client cannot draw them all. Four capabilities let the server keep each client
to the players near it, tell it where everyone else is, time remote movement
by the server's clock and send riding state as changes. The client declares
all of them in `#clientcaps` after login. Each one also needs a server setting,
and the client learns what is in force only from what it receives: until the
first packet of a part arrives it behaves exactly as a client without that
part. A server that sends none of them sees no difference.

| Capability | Packet | Client code |
| --- | --- | --- |
| `player_interest_v1` and the `actor_cap:<N>` token | `ELORIA_PRESENCE` (197) | `src/state/presence_state.gd`, `src/ui/nearby_indicator.gd` |
| `server_time_v1` | `ELORIA_SERVER_TIME` (196) | `src/network/server_clock.gd`, `src/actors/server_time_pacing.gd` |
| `mount_deltas_v1` | `ELORIA_MOUNT_DELTAS` (195) | `src/mounts/mount_delta_state.gd` |

The packets are decoded in `src/network/interest_protocol.gd`.

## Area of interest and presence dots

With interest on, the server sends other players as actors only within 80
tiles of the player (they leave at 88), plus party members, the player's
target and anyone attacking them at any distance. The client's own 80 m draw
distance lies inside that square, so no body that would be drawn is missing.
Everyone else on the map arrives once a second in `ELORIA_PRESENCE` as a dot:
an actor id and a tile, no name.

`PresenceState` keeps each snapshot as packed arrays. Every dot glides from
where it was drawn to its new tile over one presence interval, so a distant
rider moves smoothly across the map instead of jumping; a dot that moved
farther than walking could take it (24 tiles) is placed at once. When a
player walks out of the area the server removes the actor; the client keeps a
dot where the actor stood until the next snapshot places it, so the mark does
not blink at the edge of the area.

The minimap and the full map draw presence dots as player marks a size
smaller than marks with a body, through the same overlay and the same
"players" marker switch. With only the minimap open, dots beyond the corner of
its view are skipped before any mark is made, and the marks are reused rather
than rebuilt, so 500 distant players cost well under a tenth of a millisecond
per minimap refresh.

## The actor cap and "+N nearby"

The server may cap how many players and creatures a client is shown at once,
nearest first, always keeping the player's target, attackers, party and
trade partner, and ranking players who can attack the player above
creatures. The client asks for its own cap with the graphics setting **Most
players and creatures shown** (40-160, default 160), sent as `actor_cap:<N>`
after the capability names. The setting is saved with the graphics settings
and takes effect at the next login.

When the cap holds actors back, the presence header says how many, and a
small "+N nearby" label in the lower-left corner of the minimap says so too. It is hidden
at zero, which is always on a server or a map that never reaches the cap.

## Remote movement timed by the server's clock

Without server time, each remote actor measures its pace from the gaps
between the packets that move it, and holds its body a quarter of a step plus
the worst recent lateness behind the newest tile (`apply_server_state` in
`src/actors/replicated_actor_3d.gd`). Every hold on the link reads as a slower
step and the burst behind it as a faster one.

With server time, the server stamps the packets it writes with the time each
event happened. `ServerClock` keeps the smallest `arrival - stamp` seen over
the last sixteen seconds as the offset between the two clocks, so
`stamp + offset` is when a packet would have arrived on an unloaded link. How
far real arrivals land above that is the link's jitter; the playout delay is
its 95th percentile plus 10 ms (20-350 ms, and at least 150 ms until twenty
frames have been seen). AppState puts the stamp of each remote actor's first
step since the last presentation pass, and the playout delay, on the actor's
row (`step_local_msec`, `step_playout_s`). Where `apply_server_state` finds
them it measures the actor's pace from the stamps and finishes each step one
pace plus the playout delay after the server took it
(`ServerTimePacing.due_seconds`), on the same continuing schedule it already
keeps; a row without them is timed by arrival as before. The player's own
steps stay on arrival timing.

`tests/test_server_time_pacing.gd` drives one remote actor over a simulated
link (frames every 50 ms, 40 ms plus up to 150 ms of jitter, read at 60 Hz)
both ways. On the development machine: walking, the speed on the ground
varies by 0.5% instead of 7% and the body trails the server by about 140 ms
less; running, 0.5% instead of 12%, with no stop-start where arrival timing
stopped once.

## Riding-table deltas

Without deltas, each `ELORIA_MOUNT_STATES` packet is the whole riding table of
the map, and it restates every rider's countdowns once a second. With them,
`ELORIA_MOUNT_DELTAS` carries the whole table after a teleport, a resync or the
capability starting, and otherwise only the riders whose row changed and the
actors whose row went away. Countdowns arrive as times on the server's clock:
when a calling completes, when the riding combat lock ends, and the gallop
endurance at a moment with the rate it is changing at. `MountDeltaState` turns
each row into the shape the complete tables have, so everything that reads
`AppState.actor_mounts` is unchanged, and only the actors a delta named have
their mounts re-bound. The player's own calling and endurance are restated ten
times a second between packets (`AppState._process`), as the complete tables
used to restate them.

On the development machine a complete table of 200 riders is 55 KB and takes
about 4.4 ms to decode, and a crowded map sent one every second; a delta
naming one rider is under 0.4 KB and takes about 0.04 ms, and restating the
player's own countdowns costs under 2 microseconds a tick.

## Tests

- `tests/test_interest_protocol.gd`: the three packets and the capability line.
- `tests/test_presence_state.gd`: presence dots, the hand-over, riding deltas,
  deadlines, the indicator and the cap, with timings for 500 dots and 200
  riders.
- `tests/test_server_time_pacing.gd`: the clock, stamping and the jittery-link
  comparison.
- `tests/test_interest_state.gd`: the same through AppState and Main with real
  packets, the settings row and the saved cap.
