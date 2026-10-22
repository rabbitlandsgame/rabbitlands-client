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
not blink at the edge of the area. The same holds when the actor cap swaps a
player out (the server re-ranks about 1.25 times a second, keeps a newly
shown player at least about 2.4 s and swaps at most two at a time).

A removed rider's riding row is kept too. A client on complete riding tables
is sent the row of every rider on its map, shown or not, and the table is not
sent again when a rider walks back into view, so a kept row is put back when
the server introduces that player again, as long as the client is on player
interest, the name matches and no newer table has replaced it. Without
interest a removal still means the player is gone, and nothing is put back.

The minimap and the full map draw presence dots as player marks a size
smaller than marks with a body, through the same overlay and the same
"players" marker switch. With only the minimap open, dots beyond the corner of
its view are skipped before any mark is made, and the marks are reused rather
than rebuilt, so collecting 500 distant players' marks costs well under a
tenth of a millisecond per minimap refresh.

Drawing them is the larger part. The overlay used to build each dot's ring and
fill point by point with a sine and a cosine, which for 300 extra dots added
about 2 ms to the average frame. It now places one precomputed circle by a
transform and sends each run of dots to the renderer in one triangle-array
draw, ring then fill per dot in mark order, so the picture is unchanged (300
overlapping dots drawn both ways differ in one pixel of 102,400) and a redraw
of 460 dots takes about 0.35 ms instead of about 3 ms. This also speeds up the
minimap for a legacy client holding every player of a busy map.

## The actor cap and "+N nearby"

The server may cap how many players and creatures a client is shown at once,
nearest first, always keeping the player's target, attackers, party and
trade partner, and ranking players who can attack the player above
creatures. The client declares its own cap as `actor_cap:<N>` after the
capability names. It follows the graphics setting **Characters drawn in a
crowd** (`docs/crowd-presentation-policy.md`): the server is asked for no
more actors than the client draws with a body, and never more than 160, the
most the protocol takes. At the setting's default of 160 the declaration is
160, the same as declaring nothing. The rule is one function,
`InterestProtocol.declared_actor_cap`.

The cap is declared at login. When the player changes the setting during a
session, the client declares the new cap once the slider has rested for two
seconds; the server retunes from a repeated `#clientcaps`, which also
restates what the capabilities gate, so it is not sent on every step of the
slider.

When the cap holds actors back, the presence header says how many, and a
small "+N nearby" label in the lower-left corner of the minimap says so too.
It is hidden at zero, which is always on a server or a map that never reaches
the cap.

## Remote movement timed by the server's clock

Without server time, each remote actor measures its pace from the gaps
between the packets that move it, and holds its body a quarter of a step plus
the worst recent lateness behind the newest tile (`apply_server_state` in
`src/actors/replicated_actor_3d.gd`). Every hold on the link reads as a slower
step and the burst behind it as a faster one.

With server time, the server stamps the packets it writes with the time each
event happened; other players' steps travel in its 20 Hz flush and carry the
flush's time, up to 50 ms after the step. `ServerClock` keeps the smallest `arrival - stamp` seen over
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
link (steps stamped with the 50-ms flush that carries them, 40 ms plus up to
150 ms of jitter, read at 60 Hz) both ways. On the development machine:
walking, the speed on the ground varies by 0.5% instead of 7% and the body
trails the server by about 140 ms less; running, 0.5% instead of 12%, with no
stop-start where arrival timing stopped once; a hastened run (100-ms steps,
so a stamp can be half a step late), 0.5% instead of 20%, with no stop-start
where arrival timing stopped three times.

## Riding-table deltas

Without deltas, each `ELORIA_MOUNT_STATES` packet is the whole riding table of
the map, and it restates every rider's countdowns once a second. With them,
`ELORIA_MOUNT_DELTAS` carries the whole table after a teleport, a resync or the
capability starting, and otherwise only the riders whose row changed and the
actors whose row went away. A whole table too big for one frame comes as
several frames in a row with only the first marked `full`; the client upserts
each frame and drops the rows the table did not restate only once it is
complete, at the first packet that is not part of it (or half a second after
it began, if nothing follows), so no rider loses a row between its frames. Countdowns arrive as times on the server's clock:
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

## Measured in the crowd benchmark

`tests/integration/run_crowd_presentation_benchmark.py --presence 300
--server-time` adds 300 presence dots walking 82-139 tiles around the player
and a server-time stamp on every tick to the crowd cells. On the development
laptop (Forward+, windowed, minimap shown, two interleaved runs each, on a
machine shared with other work), with the batched minimap drawing:

| Cell | Frame mean, without / with | Frame p95, without / with |
| --- | --- | --- |
| s3-market-160 | 19.9, 19.6 / 18.3, 17.4 ms | 25.8, 27.3 / 25.7, 25.3 ms |
| s2-invasion-160 | 14.5, 14.1 / 13.9, 14.2 ms | 22.7, 23.0 / 25.0, 25.0 ms |
| aoi-160 | 11.9, 10.9 / 11.9, 12.3 ms | 18.8, 18.4 / 20.6, 20.7 ms |
| empty | 6.0, 5.3 / 6.0, 5.3 ms | 10.5, 9.9 / 11.9, 11.1 ms |

The means are within run-to-run noise; the p95 rises by 1-2 ms in three
cells, where the once-a-second presence snapshot (decoding and placing 300
rows) and the extra minimap redraw fall on the same frames. With the old
per-polygon drawing the same inputs cost 1-10 ms more on the mean.

## Tests

- `tests/test_interest_protocol.gd`: the three packets and the capability line.
- `tests/test_presence_state.gd`: presence dots, the hand-over, riding deltas,
  deadlines, the indicator and the cap, with timings for 500 dots and 200
  riders.
- `tests/test_server_time_pacing.gd`: the clock, stamping and the jittery-link
  comparison.
- `tests/test_interest_state.gd`: the same through AppState and Main with real
  packets, the settings row and the saved cap.
