# Human age controls

Human character creation and the appearance editor offer two independent sliders
on an updated server:

- **Skin age** adds forehead lines, crow's feet, under-eye detail and softer
  creases around the mouth on the High graphics Human face. The middle is
  restrained; the upper end is more weathered.
- **Greying** mixes silver strands into hair, brows and facial hair. Hair colour
  remains editable independently. Classic hair at Low and Medium graphics blends
  towards grey while keeping its existing texture.

These are cosmetic amounts, not ages in years. Existing characters start at zero
for both, keeping their original appearance. They do not change face identity,
expressions, body proportions or gameplay statistics.

The offline RL head and fit-review lab has the same two controls. Its JSON export
retains their values. On an older server the editor keeps held edits and
explains why it cannot save them. The **Reset these sliders** button clears only
the new age and tied-hair placement settings so the older server can accept the
remaining appearance.

**Hair tie height** appears only for a selected style fitted to support it. The
centre retains that style's authored height; other hairstyles ignore it. Length,
volume and messiness remain independent of these new controls.
