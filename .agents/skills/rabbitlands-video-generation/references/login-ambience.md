# Animate the login paintings

Run from the client checkout with the video Python environment. The approved source paintings are the six `*-poster.jpg` files in `godot-client/assets/ui/start_screen/`; keep those still-image fallbacks intact.

```powershell
$VideoPython = '.\.local\video-generation\venv\Scripts\python.exe'
& $VideoPython tools\video-generation\login_motion.py generate --scenes oldcraft_landfall
& $VideoPython tools\video-generation\login_motion.py export --scenes oldcraft_landfall
```

The default work folder is `.local/video-generation/login-motion-v1/`. Omitting `--scenes` processes all six scenes. Generation reuses the VACE pipeline across the batch and skips completed candidates whose recipe and checksum match. Prompts, seeds and normalized polygons in `tools/video-generation/login-scenes.json` define where ambient motion is allowed. Change a seed or prompt for a new candidate; the recipe-derived filename preserves the earlier take.

VACE receives the painting at both ends of an 81-frame, 640 x 368 window, with only the selected regions available for generation between them. Export crossfades the head and tail into a circular motion track, slows it to a restrained 12-second loop, and transfers only the changing model detail onto the original 1600 x 900 painting. The mean palette and unmasked detail stay intact. Outputs are silent 30 fps MP4 previews and Theora `.ogv` runtime assets, plus recipes, checksums and loop measurements. Per-scene `export.<scene_id>.motion_strength` settings in the scene JSON can strengthen quiet footage without rerunning the model; re-export after changing them. Runtime validation counts timed presentation frames, including legitimate Theora holds of an unchanged picture.

Inspect the previews for moving water, stable landmarks, flicker, mask edges, and the loop boundary. Check them behind the actual login controls before calling them finished. Install reviewed candidates with:

```powershell
& $VideoPython tools\video-generation\login_motion.py install --scenes oldcraft_landfall
```

Installation keeps the first replaced asset in the ignored work folder's `previous/` directory and writes `motion-generation.json` beside the runtime assets. It preserves filenames, poster images, the saved scene choice and the Animate switch. Run `godot-client/tests/test_login_backdrop.gd` for integration checks; setting `ELORIA_ARTIFACT_DIR` during a rendered run captures all six scenes and checks visible playback. On Windows, point the test process's `APPDATA` at an ignored local test folder to isolate player settings and allow the sandboxed test to save them.
