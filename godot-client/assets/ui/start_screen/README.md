# Start-screen scenes

Six silent, seamless 12-second Theora loops, 1600×900 at 30 fps, with JPEG stills.
`src/ui/login_backdrop.gd` plays one selected scene and releases the decoder when
entry is hidden. Animations play at every graphics quality by default. The
picker's Animate switch explicitly selects video or the still image, saving
`[start_screen] backdrop` and `animated` in `user://eloria_hud.cfg`.
Oldcraft Landfall is the default; saved Waygate choices migrate to Landfall.

The approved paintings remain the source art and still fallbacks. Ambient motion
is generated locally with the open-weight Wan2.1 VACE 1.3B model: flowing water,
lake ripples, drifting mist and clouds, grass movement, and restrained magical
light. Buildings, landmarks, and the composition stay steady. Only the changing
detail inside feathered motion regions is transferred onto the original detailed
painting; the login form and crest remain separate live controls.

From the client repository root, use its video-generation environment:

```powershell
$VideoPython = '.\.local\video-generation\venv\Scripts\python.exe'
& $VideoPython tools\video-generation\login_motion.py generate
& $VideoPython tools\video-generation\login_motion.py export
# Review the MP4 candidates before replacing the runtime loops.
& $VideoPython tools\video-generation\login_motion.py install
```

Use `--scenes oldcraft_landfall` (or another scene ID) to work on one scene.
`tools/video-generation/login-scenes.json` contains the prompts, seeds, motion
regions, and per-scene export strengths. Generation uses an 81-frame 640×368
window, with the original painting conditioned at both ends. Export blends the
head and tail into a circular track,
retimes it to 12 seconds, and composites at 1600×900. `motion-generation.json`
records the pinned model revisions, input and output checksums, settings, and
loop measurements. Weights, raw takes, MP4 previews, and replaced-loop backups
remain in the ignored `.local/video-generation/` directory.

`tests/test_login_backdrop.gd` checks selection, saved preferences, still fallback,
cropping, and decoder lifetime. A rendered run with `ELORIA_ARTIFACT_DIR` also
captures each scene behind the actual login controls and checks visible motion.
