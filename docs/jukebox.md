# Jukebox

Open **Settings → Audio → Open jukebox**. The jukebox includes every music track shipped with the client. Music volume and the main audio switch still apply.

## Choose music

- **Let the game decide** follows the location, time, and event music chosen by the game. This is the default.
- **One song** plays a song selected in the Library.
- **Playlist** plays one of your named playlists.
- **Shuffle all music** plays the full music library in random order.
- **Silence** stops music while leaving other sounds available.

Search the Library by song title, artist, or game context, and combine the search with a context filter. Double-click a song or select **Play song** to listen. Choose a playlist beside **Add song** to build it without leaving the Library.

## Playlists and playback

Create, rename, and delete playlists in **Playlists**. Select a song to move it up or down or remove it. A song appears once per playlist. Deleting a playlist keeps its songs in the Library.

**Shuffle playlist** plays every song before starting a new round, avoiding an immediate repeat between rounds. **Repeat** can stop after the queue, repeat the whole queue, or repeat the current song. **Crossfade** sets the transition between personal songs from 0 to 8 seconds. These options also apply when a rule chooses personal music. Game-directed music keeps its authored transitions.

Use **Previous**, **Pause/Resume**, and **Next** while listening. Previous and Next apply to personal music. After a queue ends with repeat off, **Play again** restarts it.

## Rules

Enable **Use context rules**, choose a condition and music action, then select **Add rule**. Conditions include daytime, nighttime, all encounters and events, and the individual contexts the game supplies, such as inns, caves, and boss encounters. Actions can choose a song, a named playlist, all music shuffled, game-directed music, or silence.

The first enabled matching rule takes precedence over the music mode. Move specific rules above broader rules; for example, place a boss rule above an encounters rule. Select a rule to edit it, then select **Update rule**. Turn off **Use context rules** to use your music mode everywhere.

When a context no longer matches, playback returns to the selected music mode. Returning to a playlist starts a fresh queue. Rules use the music contexts sent by the game; they do not infer combat or change gameplay. Deleting a referenced playlist disables its rules.

Playlists, rules, and music preferences save automatically on this device in `user://jukebox.cfg`. Playback stops on disconnect. Reconnecting uses your saved preferences and the new game context.
