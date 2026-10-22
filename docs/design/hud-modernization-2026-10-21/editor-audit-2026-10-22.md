# HUD editor usability review — October 22, 2026

Reviewed the production editor against the official [World of Warcraft Edit Mode introduction](https://worldofwarcraft.blizzard.com/en-us/news/23837944?cmsMode=draft) and [FFXIV HUD layout guide](https://na.finalfantasyxiv.com/uiguide/know/know-hud/hud-layout.html). These describe their documented interaction patterns; this review does not claim hands-on testing of either game.

| Pattern | Rabbit Lands finding | Result |
| --- | --- | --- |
| Click a component and adjust its own options (both references) | Already supported, including individual resource curves; selecting invisible parts requires the list | Retained direct selection and added explicit hidden labels to the component list and selected-part summary |
| Visibility, size and orientation beside the selected component (FFXIV) | Existing Layout, Look, Options and Dock tabs provide these without replacing gameplay controls | Retained grouped controls, independent width/height handles, slot reflow, and the movable inspector |
| Named layouts (both references; FFXIV documents copying between four slots) | Five prebuilt designs are sufficient starting points; old 24-custom limit obscures the requested five-slot limit | Five custom slots, usage counter, disabled creation at capacity, and update/delete controls; excess older designs remain preserved in local configuration |
| Safe experimentation and recovery | Undo/Redo and Cancel exist, but restoring a single component required resetting the entire preset | Added Reset part for the selected component or individual curve, with Undo; restore-all remains separate |
| Alignment aids | Dock and resize snapping worked, but their switches were buried in separate tabs | Added always-visible Grid and Snap edges controls; the latter controls both gestures. Grid is visual guidance; edge snapping continues to use real window/screen edges |
| Clear save boundary | Editing is a transaction, but the initial help did not explain when changes persist | Initial help explains preview, Done & save and Cancel; custom actions explain that Done & save commits the collection |
| Precision and discoverability | Arrow nudging already supports 1px and Shift+arrow 10px, but was undocumented in the inspector | Added the shortcut hint and persistent dock/visibility summary; Alt-drag, Shift snap bypass, and Ctrl+Z remain available |

The five public names are **Classic**, **Compact**, **Modular**, **Adventure** and **Minimal**. Classic is the fresh-install default. The retired legacy selection migrates to Classic; existing modern built-in and custom configurations remain editable. Preset IDs remain stable for compatibility.

Validation exercises real client controls: hidden-state updates, isolated component/curve reset, Undo, snapping switches, custom capacity, migration, persistence, deletion and Cancel. The public walkthrough uses the real Settings and editor interfaces in the offline Landfall sandbox. Captions identify it as a local UI demonstration; it is not combat or public-server footage.

The manual Classic-to-Adventure rebuild also exposed stale offset controls after changing a dock target. The inspector now refreshes immediately after that selection, so its offsets address the new dock correctly. The capture changes each component through its actual inspector controls, with no preset switch while recording. Playback is labeled 2× speed. Adventure's circle/quick-bar root now uses a centered anchor instead of a saved screen-specific position. A separate 45-check alignment pass verifies centered roots and centered dock relationships across three viewport sizes.
