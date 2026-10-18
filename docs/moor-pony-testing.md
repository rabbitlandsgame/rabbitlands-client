# Moor Pony in-game test

Run `test-moor-pony-in-game.bat` from the client checkout. It opens the ordinary
Rabbit Lands game with a temporary rider at Four Gates, using a local server
and a new disposable database. Closing the game stops the server and removes
the test account. The sibling server checkout, Python and Godot 4.7.2 are needed.
The launcher starts with a close camera; normal zoom and camera controls work.

- Press **R** or click **Mount pony** while standing still. Calling takes 1.5 seconds.
- Click to travel, or use the ordinary movement keys. **Shift** runs while
  using the keyboard. `#walk` and `#run` also select the movement pace.
- Press **Space** or click **Gallop** while in running mode. Press again to stop
  galloping. Space is reserved for gallop. Endurance lasts eight moving
  seconds and refills over sixteen seconds outside combat.
- Press **R** or click **Dismount** to return to foot movement. R also cancels a
  summon. Both shortcuts can be changed in **Settings → Controls → Mounts**.

This test enables riding at Four Gates, Grey Moors and Sunmane Steppe. Narrow
terrain, interiors, combat, death, sitting, gathering, crafting and interaction
actions return the rider to foot movement. Damage also blocks remounting for
ten seconds. Normal action and terrain rules still apply.

The existing character and worn equipment ride the approved v8 pony. Handheld
equipment is hidden while holding the reins and restored when dismounting.
Playback follows actual movement speed, with trot cadence reduced to half its
previous rate for review. Walk and gallop cadence are unchanged. The test paces
remain 1.67, 5 and 7.5 metres per second; final mount balance is open for review.
Mounting and dismounting switch the pose immediately; authored transitions and
body-specific fitting beyond this prototype remain future work.

The mounted cape hangs closer down the rider's back and over the pony's
hindquarters at walk and trot. A gentle ripple travels toward the hem at trot.
Galloping gradually lifts the cape into a trailing drape and doubles the ripple
amplitude. Slowing returns it to the closer drape and gentler wave; standing
still settles the wave. The existing cloth bones retain their material lengths and
shoulder spacing while clearing the animated saddle and rump. Dismounting
restores the normal on-foot cape simulation. This drape is ready for visual
review; the pony asset and accepted torso/hand pose are unchanged.

## Normal Landfall server

The independent server profile enables the Moor Pony for every character on
all 15 Landfall outdoor maps. Ownership is saved automatically on login,
including for characters using an older client. Riding and mount visibility
require a client with `mounts_v1`; use the client containing the reviewed
Moor Pony implementation. The visuals, R/Space shortcuts and test paces above
also apply to the normal server.

Interiors, underground areas and practice instances remain on foot. Tight
terrain, activities, combat and map changes dismount the rider. On reconnect,
the pony remains owned and the character starts on foot.

Operators can disable riding without deleting ownership. Server settings and
deployment instructions are maintained in the private server handbook.

The separate `--mount-prototype` switch still requires a loopback listener
and uses the original three-map disposable test area.

Focused checks:

```powershell
python tools/test_moor_pony_in_game.py --probe
python tools/test_moor_pony_in_game.py --godot <Godot executable> --smoke
python tools/test_moor_pony_in_game.py --landfall --probe
python tools/test_moor_pony_in_game.py --landfall --godot <Godot executable> --smoke
```

The smoke run drives the real game through mounting, walking, trotting,
galloping and dismounting. Local logs and game-camera screenshots stay under
the ignored `.local/qa/moor-pony-game/` directory.

The focused integration results and exact runtime source hashes are recorded in
[the develop integration receipt](qa/mounts/moor-pony-develop-integration.json).
