# Combat tactics

Open **Spells → Tactics** to configure your own combat actions or a standing
companion in your current gauntlet. Only the current party leader can edit a
companion. Follow, Hold and Assist orders continue to work.

Each subject has three saved presets: Balanced, Defensive and Offensive. A
preset holds up to 20 rules in a scrolling list. Select a summary on the left to edit its target,
condition, action and spell power in the shared editor on the right. Enable
or disable rules with their checkboxes. Drag a row or use **Up** and **Down**
to change its priority. **Delete** removes the selected rule. Rules are
read from top to bottom. The first usable action wins; unavailable actions
fall through to lower rules. **Save** saves the current preset.
**More → Refresh** discards unsaved edits and loads the server's current plan.
**More → Restore preset** restores that preset's default rules.

The subject picker switches between **My combat actions** and companions.
The three preset buttons switch between saved plans. Switching with unsaved
edits offers **Save & switch**, **Discard & switch**, or **Cancel**.

The **Action** menu groups **Standard actions**, **Spells**, **Techniques** and **Items**.
Spell submenus use the same Healing, Defense, Offense and Support categories
as the spell book; techniques separate Attacks from Support & stances.
Items are grouped into Healing, Ether, Cleansing, Action points, Buffs and Food.
Actions are alphabetical within each category. Type while a menu is open
to jump to a matching action. The current action has a checkmark.

Your own rules can use weapon attacks, combat spells, combat techniques,
consumables and **Flee**.
Normal knowledge, equipment, range, ether, reagent, action-point and cooldown
requirements apply. Health and ether thresholds are percentages. Status
conditions check the selected actor. **Missing buff** lists beneficial effects;
**Missing debuff** lists harmful effects. An active effect suppresses that rule
until it expires or is removed. Use Self or Ally with a missing buff to maintain
protection, or an enemy selector with a missing debuff to apply it once.
Ally selectors choose the lowest health
percentage first; enemy selectors choose among opponents already engaged by
you or your party. They do not search for unrelated creatures to pull.
**Ally's opponent** selects an opponent of another party member who is in combat.

The combat selector beside **Edit Rule** checks the acting character's state:
**Any state**, **In combat** or **Out of combat**. It combines with the target's
condition. For example:

- Out of combat → Ally's opponent → Always → Weapon attack joins an ally's fight.
- In combat → Self → Ether below 20% → Flee retreats using normal flee turns,
  failure chances and retreat protection.
- Out of combat → Self → Ether below 50% → Use Potion of Mana restores ether
  after retreat. Put it below the Flee rule.
- Out of combat → Ally → Missing buff: Shield → Shield Target prepares an ally.

Items always affect the character whose rules are running. Your character and
companions consume stock from your inventory. Each character has independent
potion and food cooldowns; a bot's use does not put your items or another bot's
items on cooldown. Normal consumable effects and cooldown reductions apply.
Unavailable items, active potion effects and full resources fall through to
lower rules. Saved rules identify the item, so moving inventory slots is safe.

Your rules begin paused. **Start** explicitly enables
them for this session and map. Combat actions require an eligible opponent.
Item rules and explicit Out of combat rules for Self or Ally can also run
outside a fight. **Pause** stops them. Manual movement, attacks, casting,
techniques, item use, fleeing and Escape pause your tactics. Changing maps,
defeat or disconnect
also stops execution. Saved presets remain available, but execution never
starts automatically after reconnecting. Your ordinary combat round is
shared with automated actions, so tactics do not grant extra weapon attacks.
An automated Flee keeps tactics running so subsequent recovery rules can act.

Companions retain the actions of their role. Wardens can heal, Vanguards can
protect the party, and all roles can use their normal attack and consumables.
Flee is available for your own character. A companion's
new plan applies individually during this expedition and is also saved as
your default for future companions of that role. Other standing companions
keep their own plans. Orders, movement limits and authorized gates remain in
force; Hold does not permit an approach to a distant target.

The status line explains the current action or why no action is available.
If another edit made your window stale, Refresh before saving again.
