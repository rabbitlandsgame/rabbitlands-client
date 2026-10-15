# Start-screen scenes

Six silent, seamless 16-second Theora loops, 1600×900 at 30 fps, with JPEG stills.
`src/ui/login_backdrop.gd` plays one selected scene and releases the decoder when
entry is hidden. Animations play at every graphics quality by default. The
picker's Animate switch explicitly selects video or the still image, saving
`[start_screen] backdrop` and `animated` in `user://eloria_hud.cfg`.
Oldcraft Landfall is the default; saved Waygate choices migrate to Landfall.

The five regional paintings and motion were approved in the start-screen art
review. Oldcraft uses `eloria_login_landfall_background.png`, edited with the
built-in image-generation tool to replace the entire waygate with a coast. Motion
was rendered locally with periodic displacement, lighting and particles; the
login and crest remain separate live controls. Reproduction scripts, sources,
MP4 previews and export validation are in the project workspace's
`concept_art/start-screen-backdrops/2026-10-09-motion-v2/` collection.
