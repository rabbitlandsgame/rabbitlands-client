# Licensed game audio

The game uses 32 sound effects and 39 music tracks, including 36 additional
selections approved on October 16, 2026. Most are CC0 1.0. The waterfall and
MouthlessGames' three home/interior tracks use CC BY 3.0; Angus Macnaughton's
**Fantasy Music - Night Town** uses CC BY 4.0. Each recording and its
adaptation retain the license named in `manifest.json`; Rabbit Lands' original-asset
license does not apply to these recordings.

## Sources and use

| Use | Source and creator | License |
| --- | --- | --- |
| Town music | [A New Town (RPG Theme)](https://opengameart.org/content/a-new-town-rpg-theme) — The Cynic Project / pixelsphere.org / cynicmusic.com | CC0 1.0 |
| Exploration music | [The Field Of Dreams](https://opengameart.org/content/the-field-of-dreams) — pauliuw | CC0 1.0 |
| Dungeon music | [Inside the Overlords Domain](https://opengameart.org/content/inside-the-overlords-domain) — Karate Studios | CC0 1.0 |
| UI and level-up cues | [Interface Sounds](https://kenney.nl/assets/interface-sounds) — Kenney | CC0 1.0 |
| Combat impact | [Impact Sounds](https://kenney.nl/assets/impact-sounds) — Kenney | CC0 1.0 |
| Gathering, pickups, dirt footsteps | [RPG Audio](https://kenney.nl/assets/rpg-audio) — Kenney | CC0 1.0 |
| Weapon swing and magic | [RPG Sound Pack](https://opengameart.org/content/rpg-sound-pack) — artisticdude | CC0 1.0 |
| Leaf/grass and wood footsteps | [Different steps](https://opengameart.org/content/different-steps-on-wood-stone-leaves-gravel-and-mud) — TinyWorlds | CC0 1.0 |
| Sand, stone, and one grass/sand step | [Fantozzi's Footsteps](https://opengameart.org/content/fantozzis-footsteps-grasssand-stone) — Fantozzi; sliced by qubodup / Iwan Gabovitch | CC0 1.0 |
| Snow footsteps | [42 Snow and Gravel Footsteps](https://opengameart.org/content/42-snow-and-gravel-footsteps) — Corsica_S; extracted by Iwan Gabovitch | CC0 1.0 |
| Plaza murmur | [Outside Talks #2](https://bigsoundbank.com/discussions-exterieures-2-s2969.html) — Joseph SARDIN / BigSoundBank.com | CC0 1.0 |
| Waterfall | [Stream Sounds](https://opengameart.org/content/stream-sounds) — kurt | CC BY 3.0 |

`manifest.json` records the source pages, direct downloads, retrieval date,
archive hashes, original file hashes, and exact processing for every game file.
`license-evidence.json` retains excerpts of the reviewed license declarations.
The original snow-pack notice records Corsica_S's permission for the CC0 release.
The original Kenney notices and both full Creative Commons legal texts are
retained in `godot-client/assets/audio/licenses/` relative to the repository root.

## Rebuilding

`music-program.json` is the authored playlist and map allocation. It supplies
day/night pools for every served exterior, room types for shared interiors,
gauntlet preparation/combat/boss pools, and invasion warning/wave/surge/boss/
aftermath choices. Day is game minute 90 through 269 of the 360-minute cycle.
Windowless caves and temples retain their place-based music across the clock.

`python eloria-assets/tools/sync_music_program.py` publishes the context rules
to the sibling server. It derives interior zones from the current map manifests
and registry transforms, including disconnected sections' actual entry points.
Re-run it after changing an interior's authored geometry or coordinate frame.
The server copy also carries music this source does not (the A3 isles'), which a
whole run reverts: `--map <map id>` (repeatable) rewrites only that map's block
and its zone digest, leaving every other byte of the server file as it stands,
and `--check` exits 1 while what it would write differs (the Landfall Town rooms:
`--map landfall_town`).
New clients advertise `music_program_v1`; older clients keep `music.txt` beds.

The server updates music on arrival, clock changes and its encounter upkeep.
Only nearby ordinary invasion threats override outdoor music; a different map
or an unrelated building keeps its own pool. Gauntlets use actual live combat
and bosses rather than a map name alone. An aftermath plays once and restores
the current place/time pool; an administrative clear does not earn a victory.

The client rotates complete pieces without immediate repeats, keeps a shared
piece playing across compatible contexts, crossfades normal changes over five
seconds and combat changes over 1.5 seconds, and holds rapid ambient changes for
six seconds. A four-resource cache bounds music loading. Audio settings show
the current title and the creator in its tooltip, alongside the existing mix
controls and offline credits. Disable/disconnect stops both crossfade voices.

The 36 additions are built from their retained originals under `expanded/`,
normalized in two passes to -24 LUFS with a -3 dBTP ceiling, and encoded as
stereo Ogg Vorbis. Unconfirmed loop seams receive a documented 0.75-second
overlap. The finite aftermath piece is not looped. Source links, original and
output hashes, creator notices and all changes remain in the manifest,
provenance, credits and license-evidence records.

Run `python eloria-assets/tools/build_native_sounds.py` from the repository root.
It reads the retained originals here and never contacts the network. Install
numpy, scipy, and FFmpeg first. Use `--ffmpeg /path/to/ffmpeg` or the optional
imageio_ffmpeg package when FFmpeg is not on PATH. `--out /path/to/audio` builds
a separate set with the same credits and licenses. Source hashes are verified
before conversion.

Effects and positional ambience are mono 16-bit PCM WAV at 44.1 kHz. Music is
stereo Ogg Vorbis at 44.1 kHz. Levels are adjusted to preserve the existing mix;
footsteps are filtered and faded to avoid harsh repeated attacks. Ambience and
music receive overlap crossfades for continuous playback. The waterfall uses
seconds 1–21 of `waterfall2.ogg`, mixed to mono, resampled, level-adjusted and
crossfaded over 0.8 seconds. The plaza uses seconds 30–62 of the crowd recording,
with a 2.2 kHz low-pass filter and a one-second overlap crossfade. These changes
are declared beside the corresponding filenames in the shipped credits.

## Distribution

Rain uses the first recording from [Rain (loopable)](https://opengameart.org/content/rain-loopable)
by Ylmir, under CC0 1.0. The retained `rain/1.ogg` is converted to mono 44.1 kHz
PCM, level-adjusted to a 0.6 sample peak, and given a 0.6-second overlap crossfade.
The continuous rain bed follows the shown rain intensity, with a short fade to
avoid abrupt starts and stops. It uses the world ambience bus, continues when
particles are hidden, and stops indoors, on disconnect, or when sound is disabled.
Source and output hashes, creator credit, and license links ship with the audio.

The game reads `assets/audio/CREDITS.txt` through **Settings → Audio credits**.
Credits include each creator, original title, source URL, license URL, source
notice, and modifications. Requested CC0 acknowledgments are honored too.
Credits do not imply endorsement.

The Windows and Linux package builder copies the audio notices and full legal
texts into `app/assets/audio/`, adds `AUDIO-CREDITS.txt` at the package root, and
fails if a required license or attribution is missing. The Godot export filters
include the text notices so the credits are readable from the packed game too.
Preserve these files in redistributions. If modifying or reusing the CC BY
waterfall, preserve attribution and the source/license links, identify further
changes, and impose no additional legal restrictions or effective technological
measures on that recording. Other Eloria assets keep their existing licenses.

## Verification

`python godot-client/tests/test_native_sounds.py -v` validates catalog coverage,
audio and source hashes, readable non-silent WAVs, unclipped levels, soft footstep
edges, variant diversity, full licenses, credits, and packaging failure when a
license is missing. The engine's `test_audio_director.gd` and
`test_ambient_audio.gd` check playback, Ogg music loops, compressed/stereo WAV
loop lengths, music volume changes, and the actual settings credit button.
