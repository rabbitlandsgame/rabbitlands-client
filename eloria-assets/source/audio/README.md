# Licensed game audio

The game uses 31 sound effects and three music tracks selected from free online
sources on October 11, 2026. All are CC0 1.0 except kurt's **Stream Sounds**
waterfall recording, which is CC BY 3.0 Unported. Each recording and its
adaptation retain the license named in `manifest.json`; Eloria's original-asset
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
