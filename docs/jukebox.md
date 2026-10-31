# Jukebox

Click the **gold lyre icon** on the menu bar, or open **Settings → Audio → Open jukebox**. The icon lights while the menu is open. The Moonlit Slate menu includes every music track shipped with the client. Its searchable Library, playlist, and rule editor appear side by side on a wide screen; smaller screens use the Library / Playlists / Rules tabs. Music volume and the main audio switch still apply.

## Compact HUD player

Open the **HUD editor**, choose **Music player**, and enable **Show Music player**. Drag, resize, scale, anchor, or dock it like the other HUD components, then choose **Done & save**. Cancel restores the previous layout. Existing layouts keep the player hidden until you enable it.

The compact player includes the current song and source, previous / pause / next, shuffle, repeat, music volume, mute, and an expand button. Expand opens the full jukebox using the same playback state. The full menu's compact-player button enables the HUD player and closes the full menu. A small grip appears while the HUD editor is open; gameplay controls are handled as HUD placement while editing.

Music volume remains synchronized with the full menu and Audio settings. The player shows the music selected by the first matching rule, with the rule and playlist available in its tooltip. Game-directed music keeps the game's authored order and transitions; shuffle and repeat controls apply to personal music.

## Choose music

- **Let the game decide** follows the location, time, and event music chosen by the game. This is the default.
- **One song** plays a song selected in the Library.
- **Playlist** plays one of your named playlists.
- **Shuffle all music** plays the full music library in random order.
- **Silence** stops music while leaving other sounds available.

Search the Library by song title, artist, or game context, and combine the search with a context filter. Double-click a song or select **Play** to listen. Select a playlist in the middle column, then use **Add** to build it without leaving the Library. On smaller screens the destination picker appears beside Add.

## Playlists and playback

Create, rename, and delete playlists using the **…** button in **Playlist**. Select a song to move it up or down or remove it. A song appears once per playlist. Deleting a playlist keeps its songs in the Library. Editing or renaming the playing playlist preserves the current song.

**Shuffle** plays every song before starting a new round, avoiding an immediate repeat between rounds. **Repeat** cycles between repeating the whole queue, repeating the current song, and stopping after the queue. Its tooltip shows the current choice. **Crossfade** sets the transition between personal songs from 0 to 8 seconds. These options also apply when a rule chooses personal music. Game-directed music keeps its authored transitions.

Use **Previous**, **Pause/Resume**, and **Next** while listening. Previous and Next apply to personal music. After a queue ends with repeat off, **Play again** restarts it.

## Rules

Enable **Use rules**, choose a condition and music action, then select **Add rule**. Conditions include daytime, nighttime, all encounters and events, and the individual contexts the game supplies, such as inns, caves, and boss encounters. Actions can choose a song, a named playlist, all music shuffled, game-directed music, or silence.

The first enabled matching rule takes precedence over the music mode. Drag a rule's grip or use the editor's up/down arrows to change priority. Place specific rules above broader rules; for example, place a boss rule above an encounters rule. Each row has an enable switch. Select a rule to edit it, then select **Save rule**. Turn off **Use rules** to use your music mode everywhere.

When a context no longer matches, playback returns to the selected music mode. Returning to a playlist starts a fresh queue. Rules use the music contexts sent by the game; they do not infer combat or change gameplay. Deleting a referenced playlist disables its rules.

Playlists, rules, and music preferences save automatically on this device in `user://jukebox.cfg`. Playback stops on disconnect. Reconnecting uses your saved preferences and the new game context.
