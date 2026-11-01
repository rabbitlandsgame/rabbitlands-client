# Gauntlet waves and bosses

Development behavior pending server release.

Each gauntlet map has one route definition for every party level and challenge. Its three copies let separate parties run it simultaneously. Encounters choose creatures with suitable native Attack/Defense, preferring the map's theme, and retain their normal species stats.

An ordinary wave can arrive with an extra leader. Most leaders are a stronger version of the wave's main creature; occasionally a stronger named boss appears instead. Courts choose a suitable boss from their retained encounter patterns. Higher challenges increase rolled boss and miniboss bonuses.

On trail roads, creatures emerging from channels walk towards the bowl's center, then wander around it. They still attack players who come close along the way. Idle creatures gather around their living leader once inside the bowl, and keep the arena's movement boundaries.

Players can see creatures at twice the usual distance inside gauntlets. Once a wave has fully arrived, its last few survivors occasionally approach the party, making stragglers easier to find.

Killing the boss breaks that movement anchor. Surviving followers and creatures the boss summoned stay alive and return to normal wandering. Finish the remaining enemies to clear the wave. Invasion bosses follow the same rule, and an invasion can still have queued reinforcements after its leader falls.

The encounter card beside the combat HUD separates the wave number, current enemies and future pulses. Ordinary roaming pulses release at their remaining-enemy threshold. Hunted and swarm pulses also have a clock; the displayed countdown is an upper bound because kills can release the next pulse earlier. Arrival cues follow authoritative pulse updates. A countdown reaching zero waits for the server's release.

## Companion orders

Inside an active gauntlet, use `#party bot status` to see companion numbers,
roles, orders and recovery. The living party leader can order one standing
companion by number, or use `all` for every standing companion:

| Command | Order |
| --- | --- |
| `#party bot follow all` | Resume normal following and support. |
| `#party bot hold 1` | Stay on the current tile, defending and healing within reach. |
| `#party bot assist 1` | Prioritize the opponent you are attacking or shooting. Start your attack first. |
| `#party bot help` | Show the available orders. |

Hold pauses travel through gates. Follow resumes travel through gates the party
has already authorized. Orders reset after a companion's defeat, the leader's
absence or the expedition's end. Assist also returns to Follow when its target
ends or becomes unavailable. Orders do not carry into another expedition.
