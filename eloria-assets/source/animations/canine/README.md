# Canine reference motion

This offline package contains the selected revision-5 family fits for Briarhide Wolf, Thornhide Wolf, Thornbark Wolf, Crystal Dire Wolf, Moss Armored Hound, Mossbound Hound and Red Fox. Walk, lunge/bite (`Sword_Attack`) and collapse (`Death_A`) retain their original timing. The two actions last five seconds. Four other runtime clips are preserved separately during replay.

`category-motion` contains shared semantic timing, support intent, physical limb-chain guides and muzzle features. These guides describe an authored wolf fit to a reference video. Extra model angles do not provide additional captured video measurements. `actors` contains rig-specific anatomy profiles and qualified numeric native curves; `inputs` contains the corresponding prepared geometry, binds and repaired skins. These local quaternion/control curves cannot be copied directly onto a different rig.

From the repository root, with NumPy, SciPy, OpenCV and Pillow installed:

```powershell
python eloria-assets/source/animations/canine/rebuild_actor.py --actor red_fox --output godot-client/test-artifacts/red_fox-replay.glb
python eloria-assets/tools/test_video_motion_promotion.py
```

Replay verifies the input hash, evaluates the authoritative native curves, preserves the current client's Idle_A, Fighting_Idle, Hit_Chest and Jog, and packs the result losslessly. `--preserve-runtime-from` can explicitly name another compatible current model. Existing runtime and packaged inputs cannot be overwritten by the replay command. The manifest records hashes after removing private authoring paths and unused binary storage; original authoring hashes remain provenance, not hashes of these sanitized files.

Runtime files are under `godot-client/assets/actors/native/creatures`. See [integration and evidence](../../../../docs/creature-video-motion.md) and the repository's creature-animation skill before fitting another actor. Provider reference media, upload receipts and private account records are kept outside the repository.
