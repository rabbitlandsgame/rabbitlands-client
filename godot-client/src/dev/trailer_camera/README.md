# Trailer camera

A dev-only camera for filming trailer world shots. It loads a served map offline
the way `tests/integration/rendered_*.gd` do (`WorldLoader.load_world`,
`WorldEnvironmentBinder.apply`, the look pass and the hour) and flies a `Camera3D`
along a keyframed path from a JSON shot file. It can do what the game's orbit
camera cannot: ground-level pushes, horizon-level moves and long flyovers
(the game rig is held to pitch -15 to -80 degrees and 1.5 to 90 m).

Nothing in the game reaches this scene. It films the same client code and
content players see, but no live server: use it for scenery only. Combat footage
must be a live, server-resolved fight (server handbook,
`docs/wiki/Media-Capture-and-Provenance.md`). For the gameplay half of a
trailer, film the live client with the capture HUD toggle below.

| File | What it is |
| --- | --- |
| `trailer_camera.tscn`, `trailer_camera.gd` | the scene: load, hold chunks, bind light, fly, write |
| `trailer_shot.gd` | the shot format and path maths (tested by `tests/test_trailer_shot.gd`) |
| `render_shot.py` | renders a shot through Movie Maker at 2560x1440 |
| `shots/*.json` | sample shots: `landfall_north_gate`, `greenlight_causeway` |

## Running a shot

Run from `godot-client/`. Arguments after `--` belong to the scene; a relative
`--shot` or `--preview` path is relative to the client repository.

```sh
# Stills at every key and halfway between keys, then quit: the authoring loop.
godot --path . --resolution 1280x720 res://src/dev/trailer_camera/trailer_camera.tscn -- --shot=res://src/dev/trailer_camera/shots/landfall_north_gate.json --preview=.local/video-generation/trailer-camera/preview
# Play it once in real time (add --loop to repeat; Esc quits).
godot --path . res://src/dev/trailer_camera/trailer_camera.tscn -- --shot=res://src/dev/trailer_camera/shots/landfall_north_gate.json
# Fly freely from the shot's first key to find new keys.
godot --path . res://src/dev/trailer_camera/trailer_camera.tscn -- --shot=res://src/dev/trailer_camera/shots/landfall_north_gate.json --fly
```

In the editor, open `trailer_camera.tscn`, set `shot_path` in the inspector and
press F6. The painted look and graphics quality come from the shot
(`paintedLook`, `quality`); `ELORIA_LOOK` and `ELORIA_LOOK_QUALITY` still
override them as they do in the game.

**Fly mode:** WASD moves, Q/E go down and up, Shift is faster, hold the right
mouse button to look, the wheel changes speed, Z/X change the field of view and
`[` `]` move the hour. K prints the current view as a key and copies it to the
clipboard, with its height above the ground. Chunks stream around the camera as
they do in the game, so the view can pop in while you fly; renders never do (see
Streaming).

## Rendering with Movie Maker

```sh
python godot-client/src/dev/trailer_camera/render_shot.py godot-client/src/dev/trailer_camera/shots/landfall_north_gate.json .local/video-generation/trailer-camera/renders/landfall_north_gate.avi
```

It runs `--write-movie <out> --fixed-fps 60 --resolution 2560x1440` and writes:

- `<out>`: `.avi` is MJPEG at Godot's default quality, 0.75 (the writer does not
  read a quality from `override.cfg`); `.png` is a numbered lossless PNG
  sequence plus a `.wav`.
- `<out>.trailer.json`: `framesDrawnBeforeShot` is the number of leading frames
  that are loading and preroll; the next `shotFrames` frames are the shot. The
  script prints the trim command; `--trim` deletes the head and tail of a PNG
  sequence.

Godot 4.7's Movie Maker records at the project's base viewport size
(`display/window/size/viewport_width` and `_height`, 1280x720 in
`project.godot`), not at the window size, and scales every frame down to it.
`render_shot.py` therefore writes a temporary `godot-client/override.cfg` with the
wanted size for the render and deletes it afterwards. It refuses to run if an
`override.cfg` is already there, because other tooling uses that file. Run by
hand, the same command without that override gives a 1280x720 movie whatever
`--resolution` says.

Measured on a laptop RTX 5080 at 2560x1440: as MJPEG AVI the 6 s Landfall shot
recorded in 33 s (422 frames, 125 MB) and the 8 s Greenlight shot in 49 s (542
frames); an 8 s shot as a PNG sequence took 11 minutes (542 frames, 1.8 GB),
because PNG encoding is the bottleneck. Use AVI for review and PNG for masters.
Both are 60 fps with exact frame times: under `--fixed-fps` the shot clock is
frame / fps, not wall time. A render keeps the GPU busy; run one at a time.

## Streaming

Before the first frame of a shot, every map chunk within `streamRadius` of any
point the camera stands at or looks at (sampled every 0.25 s along the path) is
imported synchronously. The chunk stream is then paused, so nothing loads or
retires while frames are written. Both sample renders logged no chunk events
after the shot began. The loading happens inside a few long frames, so Movie
Maker writes only a handful of frames while it runs; those frames, and the
preroll, are the head that `framesDrawnBeforeShot` counts.

The preroll (default 1 s) holds the first key while the grass beds, ambient
animals and screen-space effects settle: in the Landfall render the grass is
missing from the first loaded frame and fully grown by the first shot frame. The
grass then follows the camera during the shot as it follows the game camera, so
on a very fast move its far edge can still be growing.

A chunk is resident only if it lies within `streamRadius` horizontally of the
path. For a high flyover that sees the whole region, raise `streamRadius` past
the region's size. Landfall (26 of its 32 chunks) loaded in 5-8 s and Greenlight
(58 of 72) in 5-7 s, at an estimated 884 and 610 MiB under the
`residentBudgetMiB` default of 6144. The log line `trailer chunks ...` reports
both figures, and the script warns when the budget leaves chunks out.
`neighbours` loads the adjoining regions as the game shows them across a border.

## Shot files

```json
{
  "schema": "rabbitlands-trailer-shot/1",
  "name": "landfall_north_gate",
  "map": "landfall",
  "gameMinute": 135,
  "msaa": 4,
  "keys": [
    {"t": 0.0, "position": [-102.0, 121.5, -147.6], "aboveGround": 1.4, "lookAt": [-95.6, 125.0, -126.6]},
    {"t": 2.6, "position": [-96.0, 121.5, -128.0], "aboveGround": 1.6, "lookAt": [-90.0, 124.0, -105.0]},
    {"t": 6.0, "position": [-95.0, 121.5, -116.5], "aboveGround": 13.0, "lookAt": [-62.1, 138.0, -27.8], "fov": 50, "ease": "out"}
  ]
}
```

Positions are the map's own metres, as its `world.json` lists landmarks: +X
east, +Y up, north is -Z. `tile` takes a server tile instead (what `#loc` and
the minimap print). Find positions with `--fly` and K, or from the map's
`map-detail.webp` (4 pixels per metre over `minimap.worldMin`..`worldMax`).

**Keys**

| Field | Meaning |
| --- | --- |
| `t` | seconds. The first key defaults to 0 and the last must have one. Keys between without `t` share the time by distance, so the camera keeps one speed. |
| `position` / `tile` | where the camera is: `[x, y, z]` metres, or `[x, y]` server tile. |
| `aboveGround` | replaces the y with this height over the walkable ground: searched from 3 m above the given y down (so a key under an arch finds the road, not the arch), else from high above. A `tile` key defaults to 1.7. |
| `lookAt` / `lookAtTile` | what it looks at. `lookAtAboveGround` grounds that point the same way. |
| `yaw`, `pitch` | instead of `lookAt`: a compass heading (0 north, 90 east) and degrees above the horizon. With neither, the key looks along the path, tilted by `pitch`. |
| `fov` | vertical degrees. The default is the shot's `fov`, else 50. |
| `roll` | degrees of Dutch angle. |
| `ease` | shapes the segment from this key to the next: `linear` (default, keeps speed), `in` (leaves at rest), `out` (arrives at rest), `in-out`. |
| `gameMinute` | the hour at this key, eased to the next key's: a time-lapse. |

The path is a cubic Hermite spline in time whose tangent at a key is the chord
between its neighbours divided by the time between them. Evenly timed keys
therefore glide through without slowing. The look target follows its own spline
the same way. `"interpolation": "linear"` draws straight segments instead.

**Shot options**

| Field | Default | Meaning |
| --- | --- | --- |
| `map` | required | a registry id (`landfall`, `greenlight`) or a `world.json` path |
| `gameMinute` | the map's own light | the server clock, 0-359: 0 midnight, ~48 sunrise, 180 noon, ~312 sunset; the sun casts shadows from ~75 to ~285 |
| `environmentVariant` | none | a manifest variant merged over its environment, such as `golden-hour` |
| `sunBearing` | the map's | the compass bearing the sun stands at |
| `fog` | `true` | `false` turns the map's fog off |
| `msaa`, `taa` | `0`, `false` | anti-aliasing: the game uses none; the samples use `msaa: 4` |
| `paintedLook`, `quality` | `true`, `"high"` | the Graphics settings the shot is drawn with |
| `shadowDistance` | 200 | metres of sun shadow (the game uses Godot's 100) |
| `near`, `far` | 0.1, 3000 | clip planes |
| `streamRadius` | 240 | metres around the path whose chunks are held |
| `residentBudgetMiB` | 6144 | the chunk budget while held (the game's is 256) |
| `neighbours` | `[]` | region ids to show around the map, or `"auto"` for those within `neighbourRadius` (300) of the path, at most `maxNeighbours` (4) |
| `ambientLife`, `lightMarkers` | `true` | the map's ambient animals and lamp lights |
| `preroll` | 1.0 | seconds held on the first key before the clock starts |
| `resolution` | none | warns when the window differs |

The camera draws no weather: rain and storms are configured only for mainland
maps, so the scene does not add any.

## Capture HUD toggle in the live client

Launch the client with `-- --trailer-capture`, for example
`RabbitLands.exe -- --trailer-capture` or `godot --path godot-client -- --trailer-capture`.
F9 then cycles three looks:

1. the normal HUD;
2. a clean feed: the world view alone;
3. the clean feed without nameplates (names, titles and health bars over heads).

It is not a player setting and saves nothing. Without the argument, F9 does
nothing. The clean feed draws the world viewport's own picture over the HUD, so
a chat line, window or popup panel that opens during a take stays out of the
recording. The HUD underneath still takes clicks, so keep to the keyboard and
world clicks while filming. `tests/integration/rendered_trailer_capture.gd`
checks all of this.

Not covered: popup menus (right-click menus, dropdowns) are separate windows and
still draw over the clean feed; a minimap menu opened under it changed 1.5% of
the frame. Selection rings, quest markers and speech bubbles stay in the world.
The OS mouse cursor is not in a Movie Maker frame, but screen recorders capture
it unless told not to. Live footage should be recorded in real time with
a screen recorder: Movie Maker's fixed frame rate runs the client's clock apart
from the server's (not tried).
