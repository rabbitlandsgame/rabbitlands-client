# Magic casting prototype

Branch: `feature/magic-casting-prototype`, based on develop at `98b3f9e5c`.

> Server source links require access to the private [rabbitlands-server repository](https://github.com/rabbitlandsgame/rabbitlands-server). Local commands assume sibling `rabbitlands-client` and `rabbitlands-server` checkouts.

## Selected approach and tutorial

**Quick is the default live ring.** Hold Left Shift, hover a class, then choose
a spell. Right click cycles targets and the scroll wheel adjusts power.
The production widget is `src/ui/quick_spell_ring.gd`; the comparison scene
uses that same implementation. Target choices, powers and pins persist per
character alongside the quickbar settings.

The live spell bar starts visible, attached just left of the item quick slots
on the right HUD. Its twelve slots form a single column with backed corner
badges. Drag the dotted grip to detach and move it; the **⋮** menu also offers
**Detach from HUD** / **Attach to HUD**. Attachment, floating position and
visibility are saved with the HUD settings. **Hide spell bar** leaves a
**Spells** launcher beside the HUD. Left Shift and Alt shortcuts work while
hidden. The menu also opens the spellbook and ring/casting settings.

Use **⋮ → Ring / casting settings** to choose **75%, 90%,
100%, 110% or 125%**. The setting is saved per character and works in the live
client and all native practice variants. Labels, icons and clickable wedges
scale together. Larger rings fit smaller windows automatically while retaining
the requested size. Scrolling over an open ring still changes spell power.

Run **`test-magic-tutorial.bat`** for the real Borrowed Sky tutorial with a
separate local server and saved practice account. Log in as **RingStudent**
with password **ringpractice**, then type **`#tutorial magic`** in chat.
The matching server is the sibling `rabbitlands-server` checkout with the ring tutorial
updates. Pass `-ServerRoot` to use another matching server checkout.
Port 2013 is local only; `-Port` chooses another. `-Fresh` makes
a new practice profile without deleting the previous one. `-Check` runs a
headless client through login and the ring introduction on a fresh local server.

The tutorial first asks you to inspect the book, open the ring, browse a class
and dismiss without casting. Its existing rescue lessons then teach Heal,
quickbar corner badges, cancelling ground targeting, Target/Allies/Burst,
scrolling P1 → P2 → P1, and the other spell classes. Cast lessons still require
real server outcomes. See [tutorial integration](../magic-tutorial/implementation.md).

## Compare streamlined wheels

Hold **Left Shift** for the rings; **Alt+1–0 / minus / equals** casts quickbar
slots in every mode. Right Shift does not open or close a ring. Numbers select
classes/spells while Left Shift is held; right click cycles target type.

The quickbar shows the saved **target letter in the top left** of each icon
(S Self, T Target, A Allies, B Burst, G Ground, I Item, R Recall) and the
**power number in the top right**, including 10. Shortcut keys sit in a
separate gutter. The backed badges stay readable when unavailable spell art
is dimmed. A submitted cast updates all assigned slots for
that spell family, whether it came from the wheel, spellbook, or quickbar.
Ground and utility casts update the slots after confirmation. Hovering,
scrolling, changing target type, cancelling, and failed sends do not update
them. The saved target is the type (Self, Target, Allies, Burst, etc.); Target
uses the currently selected eligible recipient, whose name appears in the
tooltip. Saved spell settings persist per
character. Manual slot assignments set the initial target and power until
the next cast of that family. The tooltip expands abbreviated target labels.

Run **`test-magic-compare.bat`** to start Quick in the practice previewer.
Use the selector at the top right, or **F1 / F2 / F3**, to switch among:

| Version | Selection flow | Purpose |
| --- | --- | --- |
| F1 · Baseline | Class → family → target variant | Original wheel, including scroll-to-power. |
| F2 · Quick | Hover a class → click a spell | Fewest common-case mouse clicks, with a compact target selector. |
| F3 · Orbit | Inner class ring → outer spell ring | Keeps classes visible for switching while browsing spells. |

`test-magic-orbit.bat` starts Orbit directly. Orbit remains **practice-only**;
the live client uses Quick. The launcher rejects `-Live` with Orbit.
The browser comparison is a simulation
of these interactions using the same 86-spell catalog; utility option dialogs
are demonstrated in the runnable Godot practice scene.

Quick and Orbit select whole wedges, freeze the wheel's position while it is
open, and reveal a class after 180 ms of hover. A click or number key still
selects immediately. The first use of a family prefers Target when the selected
recipient is compatible, otherwise Self when available, otherwise the family's
normal targeting flow. The center previews the spell, recipient, target type,
and effective power before selection. Target variants and powers are then
remembered per family. **Right click** cycles Self → Target → Allies → Burst,
skipping unavailable options and wrapping around. It keeps the wheel open and
does not cast; a family with only one target option stays on that option.
The four small buttons select a target type directly.
**Backspace** goes back. Scroll adjusts the highlighted
family's power, subject to its server-stated limit.

Each class begins with up to six pinned families. **Unpin** makes room; choose
**More**, hover a different family, then **Pin** it. Existing pins keep their
order. **[ / ]** and Previous/Next navigate additional More pages. Every family
remains accessible. Quick uses **1–5** for classes and **1–7** for spells/More;
Orbit uses **Q/W/E/R/T** for classes and **1–7** for spells/More.

**Left Shift+Space** repeats the last chosen spell and power using the current eligible
recipient. Burst and Blink still wait for a ground click. Releasing Left Shift, Escape,
or focus loss dismisses an unfinished selection without casting. Switching
versions cancels pending targeting and preserves the shared trial preferences.
Those practice preferences are stored separately in `magic_wheel_trials.cfg`.

Try selecting Tavin, casting Heal twice, selecting Mira and repeating the last
spell, choosing Heal Burst, then pinning a different Offense family. Compare the
three versions with the same recipients and powers. Scrolling or changing scope
alone should never cast; selecting a node should never move the character.

Run `test-magic-wheel.bat` to try the character-centered Left Shift wheel,
`test-magic-prepared.bat` for quick-slot casting, or
`test-magic-aimed.bat` for the explicit-target comparison. All three launch an
offline practice courtyard with the production spellbook, loadout model,
casting bar, spell wheel, targeting controller, and utility picker. No login is needed.
The mode selector on the casting bar switches between them during play.

Run `test-magic-live.bat` to use the prototype with the normal login screen.
Choose your server/account there. This is the actual game client: normal
server rules and resource consumption apply after login. For a local server,
the launcher accepts `-Server 127.0.0.1 -Port 2000`.

## What to compare

| Version | Targeted spell behavior |
| --- | --- |
| Wheel | Hold Left Shift, choose a class, then a family and target variant. Uses an eligible selected recipient, otherwise arms a target click. |
| Prepared | Quick slots cast on an eligible selected recipient. Otherwise arm a target click. |
| Aimed | Always arms a target click, even with someone selected. |

Self/Allies spells are immediate in all modes. Burst and Blink use a ground
preview followed by a click. Switching to another spell replaces targeting;
Escape or right clicking the world cancels. Selecting a recipient retains it
for subsequent casts. Changing mode never casts by itself.

All versions provide twelve editable slots with last-cast target and power,
the effect/target comparison grid, and feedback beside the cursor. The
spellbook closes when a spell is launched, exposing the world.

The book's Magic and Techniques tabs share a compact browser with a side
inspector. Selecting an icon inspects it; **Cast** or **Use** launches the
action. Magic has four narrow columns (Self, Target, Allies and Burst).
Utility icons appear under Self without changing their actual targeting.
The inspector lists the selected power's required reagents and carried counts,
green when sufficient and red when short. Server quotes determine effective
power, cost, focus substitutions and readiness.

Techniques show AP costs and cooldowns in combat rounds. Their inspector shows
skill, knowledge and equipped-gear checks from the server, with a separate
cooldown and overall availability state. Unavailable actions remain inspectable;
learned techniques and visible spells can still be assigned to a chosen shared
slot or dragged onto it. Search, All/Ready/Learned/Favorites filters and the
favorite star use the same controls on both tabs; favorites and the chosen
filter are saved per character. Short windows prioritize requirements and keep
the action and assignment controls visible while collapsing the preview.

## Five-minute evaluation

1. Select Tavin, then cast Heal Target twice. Compare Prepared and Aimed.
2. Cast Fire Burst near the wisp; move outside range and try again.
3. Arm Blink, switch to Heal Target, then cancel with Escape or right click.
4. Open the spellbook. Select a target variant in the grid, choose power and
   a slot, then click **Assign**. Alternatively drag a grid icon.
5. Right click a casting slot to edit its spell/power or clear it. Cast that
   family from the ring at a different power/target and check the icon corners.
6. Close and reopen the launcher. Practice slots should be remembered.

In every mode, Alt+1–0, Alt+minus and Alt+equals cast the twelve slots.
Ctrl+S opens the book. The live client's Settings / Controls can rebind them;
the casting bar tooltips read the actual bindings. Its title bar is draggable.

## Baseline wheel comparison

Hold **Left Shift** to open the wheel around your character. Its first ring is always
**1 Healing · 2 Defense · 3 Offense · 4 Support · 5 Utility**. Click a node or
press its number to open the families in that class. Choose a family, then
**1 Self · 2 Target · 3 Allies · 4 Burst**; missing target variants are dimmed.
Single-variant families such as Blink go straight to their normal casting flow.

For example, select Tavin, then hold Left Shift and press **1, 1, 2** to cast Heal
Target. Release Left Shift afterward. Without a valid selected recipient, the same
sequence arms a target click. **Scroll up to increase power; scroll down to
decrease it.** This works on every ring, including before selecting a utility
spell. The center readout shows the current power, and target choices show the
power they will cast. Selecting a family caps power to its server-stated limit.
The wheel remembers its own power per character across sessions. Scrolling
never casts or changes a quickbar slot until a cast is submitted.

- Choose with **1–8** or a left click. Hovering and releasing Left Shift never cast.
- **Release Left Shift** before a final choice to dismiss without casting. After a
  choice, releasing Left Shift keeps any pending target selection intact.
- **Backspace / right click** goes back one ring; **Escape** closes it.
- **[ / ]** or Previous/Next changes Offense pages.
- Click the casting bar's **Ring** button to use it without holding Left Shift.
- Alt closes an open ring so Alt+number can cast from the quickbar.

The wheel follows the character's projected position and shifts inward near
screen edges so its choices remain reachable. Text fields, settings, and other
blocking dialogs suppress it. Losing focus closes it and clears the held key.
Category, family, and target positions do not reshuffle as resources change.
It owns mouse clicks while open so selecting a node cannot move or attack in
the world underneath. Alt-click remains available for the existing Attack action.

Run `test-magic-wheel.bat -Live` to open the live client with the selected Quick ring.

## Draft boundaries

The offline courtyard simulates outcomes and provides unlimited materials.
It demonstrates selection, target retention, power and area placement; it is
not a balance simulation. Real costs, success/failure, targeting permissions,
and effects are evaluated by the existing server in live play. Ground previews
use the current server's 15-tile Chebyshev range and four-tile Burst radius;
they do not guarantee line of sight or a legal Blink landing. Automatic target
selection is conservative about friendly creatures; explicit targeting remains
available and the server makes the final decision.

The live client retains Eloria's normal settings directory. Offline launchers
keep a separate profile under `godot-client/test-artifacts/magic-casting/offline-profile`.
The tutorial launcher also keeps its own isolated profile. Loadouts are keyed by server, port and character;
the practice profile is separate. A slot's saved power is capped to the
server's current allowed power when casting. All comparison modes share the
same loadout so changing mode does not change the spells being compared.

This local worktree shares artwork and imported textures with the existing
`rabbitlands-client` checkout. The `.bat` files run the game directly; use those
launchers rather than importing the shared artwork through the editor.
The PowerShell launcher also accepts `-GodotPath` for a different installation
of the pinned Godot 4.7.2 runtime.

### Updating this local sparse worktree

Before a merge, checkout, or sparse-checkout change, detach the two directory
junctions at `godot-client/assets` and `eloria-assets` from this worktree.
Verify each path is a junction and remove only the link, never its target or
contents. Git can otherwise apply sparse exclusions through a junction and
remove tracked artwork from the shared checkout. After the Git operation,
the launcher recreates the missing junctions automatically. Keep
`/test-magic-*.bat` in this worktree's sparse patterns so its launchers remain
available after a merge.

## Validation

`powershell -File tools/run-magic-prototype.ps1 -Check` runs the prototype
regressions without opening a game window. Logs and rendered review captures
are written under `godot-client/test-artifacts/magic-casting/`.
The comparison launchers with `-Check` also run `test_magic_wheel_trials.gd`.
`render_magic_wheel_trials.gd` captures Quick and Orbit for visual inspection.
The trial checks cover Left/Right Shift input, Alt quickbar routing, saved
last-cast target/power, class hover, whole-sector clicks,
right-click target cycling and unavailable target options,
remembered target type and power, repeat casting at a different recipient,
ground confirmation, cancellation, pins, More access, and power limits.
Both new batch launchers passed `-Check`; all eight trial captures were
checked at 1280 × 720. Browser interactions were checked at desktop and
narrow widths with no script errors or horizontal overflow.

Verified with Godot 4.7.2: prototype loadout/casting regressions, spell-window
tests, magic-book UI tests, and world-input tests pass. The wheel regressions
cover all catalog spells, held-key navigation, scrolling power and its limits,
per-character power persistence, cancelling, focus loss, stable
target positions, pagination, the live casting connection, and real GUI mouse
routing without world click-through. All three practice batch launchers
were exercised with `-Check`. Practice views and the live client HUD were
rendered and inspected at 1280 × 720. Live gameplay against a logged-in server
has not been playtested as part of this draft.
