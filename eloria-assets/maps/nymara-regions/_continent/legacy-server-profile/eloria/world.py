from __future__ import annotations

import asyncio
import copy
import heapq
import logging
import math
import random
import struct
import sys
import time
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import livestock, protocol as p, sky, roads
from .areas import (CHEAP_MAGIC, EXPERIENCE, FAST_READING, FAST_REGENERATION,
                    HARVEST_SPEED, NO_MAGIC, load_special_areas,
                    multiplier_at)
from .calendar import ElderDate
from .coordinate_session import CoordinateFrame, CoordinateSession
from .coordinate_output import legacy_map_supported, map_packet, named_rows_packet
from .models import (ATTRIBUTE_LABELS, ATTRIBUTES, NEXUS, Actor, Animal, BossFight,
                     Character, NPCActor, carry_capacity,
                     might, normalize_inventory_slots, refresh_derived_points)
from .counters import (COUNTER_BREAKDOWN, COUNTER_CATEGORIES, COUNTER_DETAILS,
                       achievement_rows as counter_achievement_rows,
                       detail_rows as counter_detail_rows)
from .achievements import (Catalogue as AchievementCatalogue,
                           Progress as AchievementProgress, load_achievements)
from .creatures import CreatureDefinition, creature_attacks_player
from .footprint import (SINGLE, Footprint, actor_distance, actor_facing_step,
                        actor_point_distance, box_distance, dilate,
                        footprint_of, point_distance)
from .creature_equipment import roll_creature_equipment, slot_compatible
from . import metrics
from .invasion_assistant import creature_strength
from .drops import load_drops, roll_drops
from .items import (ITEMS, ITEMS_BY_ID, ARMOR_STAT_KEYS, DEFENSIVE_WEAR_EQUIP_TYPES,
                    EL_STORAGE_CATEGORIES, WEAPON_WEAR_EQUIP_TYPES,
                    equipment_conflict, equipment_stats, wear_type,
                    equipment_wear_chance, equipped_visuals,
                    clean_item_description, item_inspect_text, item_strength,
                    item_subtype, is_degraded, roll_equipment_effects,
                    tracks_instances)
from .rarity import build_rarity_index
from .legendary_items import (MODIFIER_KEY, instance_effect_descriptions,
                              instance_effects, roll_legendary_modifiers)
from .map_digests import load_map_digests
from .map_layout import FOUR_GATES_ARRIVAL
from .maps import Portal, load_maps
from .profile import PROFILE
from .pk import PKZone, capped_level, pk_zone_at, shared_pk_zone
from .stats import (award_combat_xp, award_experience, combat_experience,
                    stats_packet)
from .magic import (AIMED_OFFENSIVE_SPELL_IDS, BASE_XP,
                    OFFENSIVE_PLAYER_SPELL_IDS, SIGIL_IDS, Spell,
                    active_focus,
                    award_magic_xp, can_cast, life_drain_damage,
                    mana_drain_amount, poison_damage,
                    preferred_spell_power, powered_spell, remote_heal_amount,
                    set_preferred_spell_power,
                    load_spell_balance, spell_archetype,
                    standard_spell_amount, standard_spell_cost,
                    standard_spell_duration,
                    spell_effect, spell_power_preferences, spend_cast,
                    available_spell_power, STANDARD_SPELLS)
from .harvesting import harvest_interval, load_harvesting
from .interactives import load_interactives
from .stats import max_level_for, next_level_experience, post_cap_points
from . import walkthrough as wt
from . import lantern, bell
from . import landing, landing_runtime, watchpost, v2_gate
from . import home
from .territory_raids import Territory, TerritoryRaidService, load_territories
from .recipes import load_recipes, roll_mix_outcome
from .spawns import load_spawns
from . import gauntlets
from .spawn_groups import (WIDE_WANDER_RADIUS, Boss, InstanceDefinition,
                           SpawnGroup, load_bosses, load_instance_control,
                           load_spawn_groups)
from .potions import POTIONS
from .perks import (ATTRIBUTE_MAXIMUM, ATTRIBUTE_MINIMUM, PERKS_BY_NAME,
                    REMOVAL_STONE_NAMES, WRAITH_PERKS,
                    apply_removal_stone, armor_pierced, available_pickpoints,
                    berserker, bone_eater, careful_mixer_chance, closer_tiles,
                    combat_wear_scale, cooldown_scale, extra_food_capacity,
                    flanker_bonus, giantslayer_bonus, harvest_extra_chance,
                    life_steal, magic_defense_bonus, magic_offense_bonus,
                    melee_dodge_luck, melee_hit_luck, mirror_share, next_tier,
                    mixing_food_scale, multicombat_penalty_per_opponent,
                    owned_tier, perk_blocker, rare_harvest_bonus,
                    rare_mix_multiplier, ranging_critical, recycler_chance,
                    regeneration_multiplier as regeneration_multiplier_perk,
                    spend_pickpoint,
                    standard_bearer_aura, summon_combat_bonus,
                    summon_cost_scale, summon_health_bonus, toggle_perk,
                    trophy_hunter_bonus, two_handed,
                    dual_wield_penalty, may_dual_wield)
from .settings import ServerSettings
from .knowledge import BookDefinition, infer_recipe_knowledge, load_books
from .collision import (STEP_BIT, erode_for_footprint, load_collision_maps,
                        with_storage_collision)
from .npcs import load_npcs
from . import npc_dialogue as lore
from . import questlines as ql
from .novac import (NOVAC_QUESTS, THE_LONG_HUNT, advance as advance_novac, completed as novac_completed,
                    current_objective as novac_objective, pending as novac_pending,
                    record_kill as record_novac_kill, set_target as set_novac_target,
                    start as start_novac, started as novac_started,
                    target as novac_target)
from .gods import (BY_PRIEST as GOD_PRIESTS, advance as advance_god, buy_blessing,
                   join as join_god, next_offering, offering_text, rank as god_rank,
                   renounce as renounce_god, worships,
                   xp_multiplier as god_xp_multiplier)
from .daily_quests import (CANCEL_WAIT_HOURS, START_NPCS as DAILY_START_NPCS,
                           active_key as active_daily_key,
                           assign as assign_daily, cancel as cancel_daily,
                           can_complete as can_complete_daily,
                           current_task as current_daily_task,
                           record_engineering as record_daily_engineering,
                           record_harvest as record_daily_harvest,
                           record_kill as record_daily_kill,
                           reward as reward_daily, task_text as daily_task_text)
from .rare_harvest import load_rare_harvest
from .rare_mixes import load_rare_mixes, roll_rare_mix
from .ranging import (AMMUNITION, MIN_RANGING_DISTANCE, RANGED_WEAPONS,
                      equipped_ranging_items, hit_chance, preserves_ammunition,
                      ranged_damage, ranging_experience, shot_interval)
from .shops import ShopDefinition, ShopItem, load_shops
from .summoning import (SUMMONING_STONES, SUMMON_BEHAVIOR_LABELS,
                        SUMMON_BEHAVIOR_OPTIONS, SummonRule, instant_rule,
                        leashed_wander_step, scaled_combat_stats, success_chance,
                        summon_target_allowed)
from .emotes import load_emotes
from .buddies import (ADDED as BUDDY_ADDED, OFFLINE as BUDDY_OFFLINE,
                      ONLINE as BUDDY_ONLINE, REMOVED as BUDDY_REMOVED,
                      add as add_buddy, load as load_buddies,
                      remove as remove_buddy, watchers_of)
from .music import load_music
from .quest_ids import (DAILY as QUEST_DAILY,
                        TUTORIAL as QUEST_TUTORIAL, id_for_title,
                        title_for_id)
from .weather import CLEAR, RAIN, STORM, load_weather, roll_weather
from .special_days import (BAD_DAY_REMOVAL, BY_KEY as SPECIAL_DAYS, DAY_STONES,
                           DAYS as ALL_SPECIAL_DAYS, ORDINARY, SpecialDay, resolve_day)


log = logging.getLogger("eloria")

# Eternal Lands tile coordinates increase toward north.  Keep this mapping in
# server-coordinate form so authoritative positions match the client's actor.
DIRS = {(0,1):p.CMD_MOVE_N, (1,1):p.CMD_MOVE_NE, (1,0):p.CMD_MOVE_E,
        (1,-1):p.CMD_MOVE_SE, (0,-1):p.CMD_MOVE_S, (-1,-1):p.CMD_MOVE_SW,
        (-1,0):p.CMD_MOVE_W, (-1,1):p.CMD_MOVE_NW}
RUNS = {(0,1):p.CMD_RUN_N, (1,1):p.CMD_RUN_NE, (1,0):p.CMD_RUN_E,
        (1,-1):p.CMD_RUN_SE, (0,-1):p.CMD_RUN_S, (-1,-1):p.CMD_RUN_SW,
        (-1,0):p.CMD_RUN_W, (-1,1):p.CMD_RUN_NW}
# random.choice needs a sequence, and rebuilding one from DIRS on every wander
# decision was allocating a tuple per creature per tick.
DIR_CHOICES = tuple(DIRS)

# Every step a tile's mask byte allows, corner cutting included, in DIRS order.
# A route search then iterates the moves it may make instead of testing all
# eight and rejecting most of them; the order is DIRS' own, so the tie-break
# between equal-cost routes - which is the order nodes are pushed in - is the
# one the search has always applied.
LEGAL_STEPS: tuple[tuple[tuple[int, int], ...], ...] = tuple(
    tuple(step for step in DIRS
          if mask & STEP_BIT[step]
          and (not (step[0] and step[1])
               or (mask & STEP_BIT[(step[0], 0)]
                   and mask & STEP_BIT[(0, step[1])])))
    for mask in range(256))

# Creature positions are bucketed into square cells so a visibility or pursuit
# query reads the few cells it overlaps instead of every creature on the map.
# Sixteen tiles keeps a 30-tile view to a 5x5 block of cells while leaving the
# buckets big enough that the index stays cheap to rebuild.
INDEX_CELL_BITS = 4
# The index is a snapshot, so a creature may have stepped since it was built.
# Queries reach this many extra tiles to keep the candidate set a superset of
# the true one; callers still apply the exact distance test to what comes back.
INDEX_SLACK_TILES = 2
# How long a snapshot may serve before it is rebuilt. One AI tick: a creature
# moves at most one tile in that time, which INDEX_SLACK_TILES already covers.
INDEX_REFRESH_SECONDS = 0.05


class OccupiedTiles:
    """A map's occupied tiles, membership-tested and locally enumerable.

    A bounded path search can only reach tiles within its own step limit, so
    what it needs is the neighbourhood around where it starts - not the map.
    Extracting that from a plain set means walking every tile on the map, which
    for an invasion is thousands of them per search. The same tiles are
    therefore also bucketed by index cell, which produces the neighbourhood in
    proportion to its own size and hands the search an argument small enough to
    send to another process.

    The buckets are built on first use. Most maps in a tick are only ever asked
    whether one tile is taken, and they should not pay to be indexed for a
    question nobody asks.
    """

    __slots__ = ("tiles", "_cells")

    def __init__(self, tiles=()):
        self.tiles: set[tuple[int, int]] = set(tiles)
        self._cells: dict[tuple[int, int], set[tuple[int, int]]] | None = None

    def __contains__(self, tile) -> bool:
        return tile in self.tiles

    def __len__(self) -> int:
        return len(self.tiles)

    def __iter__(self):
        return iter(self.tiles)

    def add(self, tile: tuple[int, int]) -> None:
        self.tiles.add(tile)
        if self._cells is not None:
            key = (tile[0] >> INDEX_CELL_BITS, tile[1] >> INDEX_CELL_BITS)
            bucket = self._cells.get(key)
            if bucket is None:
                self._cells[key] = {tile}
            else:
                bucket.add(tile)

    def discard(self, tile: tuple[int, int]) -> None:
        self.tiles.discard(tile)
        if self._cells is not None:
            bucket = self._cells.get(
                (tile[0] >> INDEX_CELL_BITS, tile[1] >> INDEX_CELL_BITS))
            if bucket is not None:
                bucket.discard(tile)

    def cells(self) -> dict[tuple[int, int], set[tuple[int, int]]]:
        """Bucket the tiles by index cell, once, on the first query."""
        if self._cells is None:
            cells: dict[tuple[int, int], set[tuple[int, int]]] = {}
            for tile in self.tiles:
                key = (tile[0] >> INDEX_CELL_BITS, tile[1] >> INDEX_CELL_BITS)
                bucket = cells.get(key)
                if bucket is None:
                    cells[key] = {tile}
                else:
                    bucket.add(tile)
            self._cells = cells
        return self._cells

    def near(self, x: int, y: int, reach: int) -> set[tuple[int, int]]:
        """Occupied tiles within `reach` of a point, excluding the point."""
        cells = self.cells()
        found: set[tuple[int, int]] = set()
        for key in index_cells(x, y, reach):
            bucket = cells.get(key)
            if not bucket:
                continue
            for tile in bucket:
                if abs(tile[0] - x) <= reach and abs(tile[1] - y) <= reach:
                    found.add(tile)
        found.discard((x, y))
        return found


def occupied_near(occupied, start: tuple[int, int],
                  reach: int) -> set[tuple[int, int]]:
    """The occupied tiles a search bounded to `reach` steps can actually test.

    A* stops expanding a node once it is `max_steps` from the start, and every
    step moves one tile, so nothing it looks at lies further than that. Passing
    the rest was never wrong, only wasteful - and it made each search carry an
    argument the size of the map. Falls back to filtering a plain set, which is
    what direct callers and the tests hand in.
    """
    local = getattr(occupied, "near", None)
    if local is not None:
        return local(start[0], start[1], reach)
    x, y = start
    return {tile for tile in occupied
            if abs(tile[0] - x) <= reach and abs(tile[1] - y) <= reach
            and tile != start}


def movement_for(visible: set[int],
                 moved: dict[int, int]) -> list[tuple[int, int]]:
    """Pair each creature a client can see with the step it just took.

    Walks whichever of the two collections is smaller. A player sees a few
    dozen creatures while an invasion tick moves thousands, so scanning the
    moves for every player cost far more than scanning each player's view.
    """
    if len(visible) <= len(moved):
        return [(actor_id, moved[actor_id])
                for actor_id in visible if actor_id in moved]
    return [(actor_id, command) for actor_id, command in moved.items()
            if actor_id in visible]


def index_cells(x: int, y: int, reach: int):
    """Yield the cell keys covering the square of `reach` tiles around x, y."""
    for cell_x in range((x - reach) >> INDEX_CELL_BITS,
                        ((x + reach) >> INDEX_CELL_BITS) + 1):
        for cell_y in range((y - reach) >> INDEX_CELL_BITS,
                            ((y + reach) >> INDEX_CELL_BITS) + 1):
            yield cell_x, cell_y

def movement_direction(dx: int, dy: int, running: bool = False) -> int | None:
    """Return a client movement command, or None for a stale/invalid step.

    Walking and running are the same step at different paces, so the pair of
    tables differ only in which command names the step. The client reads its
    walk or run clip straight off that command.
    """
    return (RUNS if running else DIRS).get((dx, dy))


def combat_roll(upper_bound: int) -> int:
    """Return a safe zero-based combat roll even after severe penalties."""
    return random.randint(0, max(0, upper_bound))


def player_dexterity(character: Character) -> int:
    """What a player brings to landing a hit."""
    return character.attributes["dexterity"]


def player_reaction(character: Character) -> int:
    """What a player brings to avoiding one."""
    return character.attributes["reaction"]


def creature_dexterity(definition: CreatureDefinition) -> int:
    """What a creature brings to landing a hit.

    Read rather than derived, the same way a player's is: a creature owns the
    twelve cross attributes outright now.
    """
    return definition.attributes["dexterity"]


def creature_reaction(definition: CreatureDefinition) -> int:
    """What a creature brings to avoiding one."""
    return definition.attributes["reaction"]


def melee_hit_chance(*, attack: int, dexterity: int, accuracy: int,
                     defense: int, reaction: int, defense_bonus: int,
                     multicombat_penalty: int = 0,
                     attacker_vanquisher: bool = False,
                     defender_vanquisher: bool = False,
                     attacker_luck: float = 0.0,
                     defender_luck: float = 0.0,
                     sigmoid_midpoint: int = 0,
                     sigmoid_scale: int = 10,
                     minimum_chance: float = 0.05,
                     maximum_chance: float = 0.95) -> float:
    """Return logistic melee hit probability based on the U-D difference.

    `attacker_luck` and `defender_luck` are Lucky Hitter and Lucky Dodger
    (register 018), which are specified to work "regardless of combat stats".
    That is why they move the resolved probability instead of joining the
    difference inside the sigmoid: a term in there is worth almost nothing
    once two well-matched fighters are far along the curve, which is exactly
    the fight the perk is bought for.
    """
    upper = attack + dexterity + accuracy + int(attacker_vanquisher)
    target = (defense + reaction + defense_bonus
              + int(defender_vanquisher) - multicombat_penalty)
    scaled_difference = ((upper - target) - sigmoid_midpoint) / sigmoid_scale
    if scaled_difference >= 50.0:
        logistic = 1.0
    elif scaled_difference <= -50.0:
        logistic = 0.0
    else:
        logistic = 1.0 / (1.0 + math.exp(-scaled_difference))
    chance = minimum_chance + (maximum_chance - minimum_chance) * logistic
    return max(0.0, min(1.0, chance + attacker_luck - defender_luck))


def melee_hit(*, critical_to_hit: int = 0, **values) -> bool:
    """Resolve a guaranteed critical hit before sampling the sigmoid chance."""
    critical_chance = max(0, min(100, critical_to_hit))
    if random.randrange(100) < critical_chance:
        return True
    return random.random() < melee_hit_chance(**values)


@dataclass(frozen=True)
class MeleeDamage:
    physical: int
    heat: int
    cold: int
    magic: int
    radiation: int
    critical: bool

    @property
    def total(self) -> int:
        return max(
            1,
            self.physical + self.heat + self.cold + self.magic + self.radiation)

    def scaled(self, factor: float) -> "MeleeDamage":
        """The same blow, harder. Every component moves, because a blow that
        was a fifth stronger was a fifth stronger all the way through - and
        scaling only the physical part would quietly make the perk worthless
        to anyone carrying an elemental weapon."""
        if factor == 1.0:
            return self
        return MeleeDamage(
            physical=int(round(self.physical * factor)),
            heat=int(round(self.heat * factor)),
            cold=int(round(self.cold * factor)),
            magic=int(round(self.magic * factor)),
            radiation=int(round(self.radiation * factor)),
            critical=self.critical)


def _roll_stat_range(values: tuple[int, int]) -> int:
    return random.randint(*values) if values != (0, 0) else 0


def melee_damage(*, weapon_damage: tuple[int, int],
                 innate_damage: tuple[int, int] = (0, 0),
                 might_value: int, attack_skill: int,
                 attack_magic_bonus: int = 0,
                 armor: tuple[int, int] = (0, 0),
                 innate_armor: tuple[int, int] = (0, 0),
                 toughness: int, defense_skill: int,
                 defense_magic_bonus: int = 0,
                 heat_damage: int = 0, cold_damage: int = 0,
                 magic_damage: int = 0, radiation_damage: int = 0,
                 heat_protection: int = 0, cold_protection: int = 0,
                 magic_protection: int = 0,
                 radiation_protection: int = 0,
                 critical_to_damage: int = 0) -> MeleeDamage:
    """Roll shared physical and independently protected elemental damage."""
    normal_attack = max(
        1,
        _roll_stat_range(weapon_damage)
        + _roll_stat_range(innate_damage)
        + might_value + attack_skill // 4 + attack_magic_bonus)
    critical_chance = max(0, min(100, critical_to_damage))
    critical = random.randrange(100) < critical_chance
    rolled_armor = (_roll_stat_range(armor)
                    + _roll_stat_range(innate_armor))
    normal_defense = (
        (0 if critical else rolled_armor)
        + toughness + defense_skill // 4 + defense_magic_bonus)
    return MeleeDamage(
        physical=max(0, normal_attack - normal_defense),
        heat=max(0, heat_damage - heat_protection),
        cold=max(0, cold_damage - cold_protection),
        magic=max(0, magic_damage - magic_protection),
        radiation=max(0, radiation_damage - radiation_protection),
        critical=critical)


def player_toughness(character: Character) -> int:
    """What a player soaks when a hit lands."""
    return character.attributes["toughness"]


def creature_might(definition: CreatureDefinition) -> int:
    """What a creature puts behind a hit that lands."""
    return definition.attributes["might"]


def creature_toughness(definition: CreatureDefinition) -> int:
    """What a creature soaks when one lands on it."""
    return definition.attributes["toughness"]


def creature_magic_defense(definition: CreatureDefinition) -> int:
    """What a creature resists a spell with - the attribute a player uses.

    It read Rationality until the creature side caught up with the split
    between the two magic attributes, which meant one spell was resisted by
    two different rules depending on what it was aimed at. Each creature's
    resist number was carried into Magic Defense when this moved, so nothing
    became easier or harder to cast at.

    Floored at one for the same reason the player's is: a creature with no
    magic defence at all would divide the formula by nothing.
    """
    return max(1, definition.attributes["magic_defense"])


def _wear_position(position: str) -> int:
    """Sort key for the equipment map, whose keys are slot numbers as text.

    A key that is not a number sorts last rather than raising, so one bad row
    in a saved character cannot stop the player getting dressed.
    """
    try:
        return int(position)
    except (TypeError, ValueError):
        return 1 << 16


def quest_progress_popup(message: str) -> bytes:
    """Display quest progress like the stock client tutorial notifications."""
    return p.colored_text(message, color=6, channel=p.CHAT_SERVER_POPUP)

def invasion_movement_due(now: float, next_at: float, interval: float,
                          lead: float) -> bool:
    """Allow one step shortly before the actor's current animation completes."""
    return next_at <= 0.0 or now >= next_at - lead


def next_invasion_movement_at(now: float, next_at: float, interval: float) -> float:
    """Advance an absolute deadline without ever issuing catch-up bursts."""
    candidate = next_at + interval if next_at > 0.0 else now + interval
    return candidate if candidate > now else now + interval


def diagonal_step_hold(interval: float, dx: int, dy: int) -> float:
    """The extra time a step of this shape needs beyond a straight one.

    A pace names how long a *tile* takes, and a diagonal crosses a tile corner
    to corner - 1.41 tiles - so holding both shapes for the one interval walks
    a diagonal 41% faster over the ground than the straight step beside it. It
    is added after the step has been chosen rather than folded into the
    reservation, because the reservation is also what paces a creature that
    turns out to have nowhere to go: that one is still due again after an
    ordinary interval, having travelled nothing.
    """
    return interval * (math.hypot(dx, dy) - 1.0)


def invasion_wait_this_cycle() -> bool:
    """Treat waiting as one of the eight directional invasion-AI choices."""
    return random.randrange(len(DIRS) + 1) == len(DIRS)


def player_in_combat(session: Session) -> bool:
    """Whether the player still has a primary target or invasion aggressor."""
    return session.combat_target is not None or bool(session.aggressors)

SUMMON_DECAY_INTERVAL_SECONDS = 20.0
SUMMON_DECAY_DAMAGE = 10
ADVANCED_SUMMONER_DECAY_DAMAGE = 5


def has_advanced_summoner_perk(character: Character | None) -> bool:
    """Accept the current perk name and its legacy EL-style spelling."""
    return bool(character and (
        character.has_perk("Summoner")
        or character.has_perk("The Summoner")))


def summoned_creature_bonuses(character: Character | None) -> tuple:
    """(share added to a summon's attack and defense, share added to its
    health). Both zero for a summoner who has bought neither perk."""
    if character is None:
        return 0.0, 0.0
    return summon_combat_bonus(character), summon_health_bonus(character)


def summon_decay_damage(character: Character | None) -> int:
    return (ADVANCED_SUMMONER_DECAY_DAMAGE
            if has_advanced_summoner_perk(character)
            else SUMMON_DECAY_DAMAGE)


def aggressive_player_magic_allowed(caster: Character, target: Character,
                                    spell_id: int) -> bool:
    """Offensive player spells require both players to occupy one PK zone."""
    return (spell_id not in AIMED_OFFENSIVE_SPELL_IDS
            or (target is not caster
                and shared_pk_zone(caster, target) is not None))


def restore_drained_stats(character: Character) -> int:
    """Undo every drain on this character, and report how much was undone.

    A drain - a Potion of Attack Reduction, anything that lowered a skill or a
    cross attribute for a while - is recorded as a negative entry in the
    temporary tables, with the real value already lowered to match. The
    per-minute tick walks each entry back to zero one point at a time, so a
    thirty-point drain is thirty minutes of being worse at something.

    Wellspring is the only thing that pays that off at once. Positive entries
    are left exactly alone: a potion the character drank on purpose is not
    something to be cured of.
    """
    restored = 0
    for values, actual in ((character.temporary_skills, character.skills),
                           (character.temporary_attributes,
                            character.attributes)):
        for key, value in list(values.items()):
            if value >= 0:
                continue
            actual[key] -= value
            restored -= value
            del values[key]
    if restored:
        refresh_derived_points(character)
    return restored


TURNS = {(0,1):p.CMD_TURN_N, (1,1):p.CMD_TURN_NE, (1,0):p.CMD_TURN_E,
         (1,-1):p.CMD_TURN_SE, (0,-1):p.CMD_TURN_S, (-1,-1):p.CMD_TURN_SW,
         (-1,0):p.CMD_TURN_W, (-1,1):p.CMD_TURN_NW}
# Clockwise from north, matching CMD_TURN_N..CMD_TURN_NW and the actor packet's
# signed 16-bit rotation field. An actor's facing lives in that field so a
# client that spawns the actor later sees the same direction as one that
# watched it turn.
FACING_ORDER = ((0,1), (1,1), (1,0), (1,-1), (0,-1), (-1,-1), (-1,0), (-1,1))
ROTATION_PER_FACING = 65536 // len(FACING_ORDER)


def wields_two_handed(character) -> bool:
    """Whether this character is holding a weapon that wants both hands."""
    return any(ITEMS[name].equip_type == "both_hands"
               for name in character.equipment.values() if name in ITEMS)


def strikes_from_behind(attacker, defender) -> bool:
    """Whether this blow lands anywhere but the front of its target.

    A creature is drawn facing one of eight directions and that facing is
    stored, so the side of a large creature is a real place to stand for the
    first time. Front is the three directions nearest the one it faces; the
    other five are its flanks and its back.

    A defender that has never turned has rotation zero, which is north, and
    that is the honest answer rather than a special case: it is facing north
    because nothing has made it face anywhere else.
    """
    dx, dy = actor_facing_step(defender, attacker)
    if not dx and not dy:
        return False
    facing = (int(defender.rotation) % 65536) // ROTATION_PER_FACING
    from_attacker = FACING_ORDER.index((dx, dy))
    apart = abs(from_attacker - facing) % len(FACING_ORDER)
    return min(apart, len(FACING_ORDER) - apart) >= 2


def facing_rotation(dx: int, dy: int) -> int:
    """Return the actor-packet rotation for one of the eight tile directions.

    The field is a signed 16-bit integer, so south through north-west are
    negative. Storing the unsigned value instead makes struct.pack reject the
    actor packet the moment a player faces south.
    """
    raw = FACING_ORDER.index((dx, dy)) * ROTATION_PER_FACING
    return raw - 65536 if raw >= 32768 else raw


def facing_direction(rotation: int) -> tuple[int, int]:
    """Return the tile direction an actor rotation is nearest to."""
    step = round((rotation % 65536) / ROTATION_PER_FACING) % len(FACING_ORDER)
    return FACING_ORDER[step]

# --- which attacker a player turns to ----------------------------------------
#
# Several creatures open combat on one player in the same tick, and only one of
# them can be the target the player counterattacks and faces. Left to the event
# loop that was whichever task happened to be scheduled first - the player
# turned to an arbitrary one of the crowd, and every other one told them "You
# are already in combat." A preference decides it instead.
COMBAT_TARGET_HOLD = 0
COMBAT_TARGET_STRONGEST = 1
COMBAT_TARGET_WEAKEST = 2
COMBAT_TARGET_OPTIONS: tuple[tuple[int, str], ...] = (
    (COMBAT_TARGET_HOLD, "Keep the one I am already fighting"),
    (COMBAT_TARGET_STRONGEST, "Turn to the strongest of my attackers"),
    (COMBAT_TARGET_WEAKEST, "Turn to the weakest of my attackers"),
)
COMBAT_TARGET_LABELS = dict(COMBAT_TARGET_OPTIONS)
# Popup id 0 is the stock client's summon-behavior popup; the walkthrough owns
# 4000-4002. This one is the client's generic popup, so any free id will do.
COMBAT_TARGET_POPUP = 1

BUFF_DOUBLE_SPEED = 1024
# The buff ids a spell sets. They share a namespace with the potions, because a
# player under a Potion of Magic Protection and one under Aegis Veil are under
# the same effect and the client draws one icon for it. Seven and eleven sat in
# the duration table with no spell to set them until Swiftwend and Null Mantle.
BUFF_SHIELD = 0
BUFF_MAGIC_PROTECTION = 1
BUFF_INVISIBLE = 3
BUFF_HASTE = 7
BUFF_MAGIC_IMMUNITY = 11
BUFF_TRUE_SIGHT = 22
BUFF_COLD_PROTECTION = 23
BUFF_HEAT_PROTECTION = 24
BUFF_RADIATION_PROTECTION = 25
#: How far Hearthcircle reaches, and how far Ruinfall falls.
SPELL_CIRCLE_RADIUS = 4
#: How far Glassgaze looks for someone standing veiled.
GLASSGAZE_RADIUS = 12
#: Rotbrand on a creature: how many bites, how far apart. A player takes it
#: through the ordinary poison loop instead, which already ticks and weakens.
ROT_TICKS = 6
ROT_TICK_SECONDS = 10
# How far placement will search outward for a free tile, and therefore how
# much of the map's occupancy it needs to know about.
FREE_TILE_SEARCH_RADIUS = 64
# How much larger than its own kind an invasion boss is drawn. Register 024
# asks for bosses to be visibly larger, and a boss that rolled strong (023) is
# larger still - the roll is the one thing about a boss a player most wants to
# know before committing to the fight, and size is how they read it without a
# window.
INVASION_BOSS_SCALE = 1.2
# The epithet a boss earns for its roll, and the roll it needs. Read from the
# top down, so an unnamed weak roll simply keeps the boss's own name.
BOSS_EPITHETS = ((1.6, "Dread"), (1.35, "Elder"), (1.15, "Great"))
# Where a piece of an authored loadout goes when the body has no slot left for
# it - a second weapon, for a boss written to carry two. Deliberately not the
# name of anything anyone wears: the point is that no rule about slots can
# match it, so the piece keeps its stats and its effects without ever being
# offered to the validation that would refuse it a hand.
EXTRA_WEAPON_SLOT_PREFIX = "extra_weapon_"
# Spawn respawns, bag expiry and raid ticks are second-granular, so the AI
# loop runs them on their own cadence instead of on every poll.
UPKEEP_INTERVAL_SECONDS = 0.25
# A creature halts a target that is moving within this many tiles of it.
STOP_MOVING_DISTANCE = 5
# How far a player can reach with a melee weapon: one tile, meaning the two
# bodies are touching. Measured box to box, so this is the same tile of
# contact against a rabbit and against something drawn four tiles wide, and a
# creature's own `attack_range` never lengthens the player's arm - what the
# player swings at is theirs to decide, and ranging is a separate system.
PLAYER_STRIKE_DISTANCE = 1
# How long a route to an attack position may be. The walk itself is capped at
# 128 steps; this bounds the search that finds the way around an obstacle,
# which is the expensive half.
APPROACH_MAX_PATH_STEPS = 64
# How many candidate destinations a route to "any of these" tries when there
# is no terrain data to search over and each one costs a search of its own.
FALLBACK_PATH_TARGETS = 8
# How long a creature that fights at a distance keeps backing away after
# something reached it in melee. Long enough to cover the several steps it
# takes to get clear of somebody chasing it, short enough that it returns
# to shooting rather than retreating across the map.
MELEE_RECOIL_SECONDS = 3.0
# Upper bound on A* searches the AI loop may start in one tick. A 36-tile
# route costs about half a tick and an unreachable target costs more than a
# whole one, so this is what keeps one blocked corner from stalling everyone.
PATH_SEARCHES_PER_TICK = 24
# ...and no more than this share of the tick's own deadline. Lowering
# invasion_max_path_length in config/server.txt is what makes each search
# cheaper; this is what stops them overrunning the tick regardless.
PATH_TICK_FRACTION = 0.4
# A wild creature a chase carried past its spawn row's `leash:N` is routed
# home (World.leash_home_step). One that finds no route waits this long before
# searching again, so a creature behind a long wall does not spend an A*
# search - the expensive, unreachable kind - on every step...
LEASH_ROUTE_RETRY_SECONDS = 2.0
# ...and after this long outside its leash with nobody watching, it is put
# back at its spawn the way a respawn puts it there: a way home longer than a
# bounded search can see (a long shore, a deep bay) must not hold it for good.
LEASH_STRANDED_SECONDS = 60.0
# Fraction of a tick's players whose creature view is fully recomputed. The
# rest still receive movement for what they already see, so a creature enters
# or leaves view up to this many ticks late and never mid-animation.
VISIBILITY_REFRESH_TICKS = 4
# The client capability that asks for the actors of adjoining maps across land seams.
ADJACENT_ACTORS_CAPABILITY = "adjacent_actors_v1"
# The served Nymara equivalent of the old Eternal Lands armed goblin. Territory
# rows may name authored spawn groups; a blank side uses this ordinary force.
TERRITORY_RAID_FALLBACK_CREATURE = "reed_mask_hunter"
# Actor ids travel as an unsigned 16-bit field in every actor packet.
MAX_ACTOR_ID = 0xFFFF
# A recycled id must not collide with a REMOVE_ACTOR still on its way to a
# client, so a retired id waits out any plausible round trip first.
ACTOR_ID_REUSE_DELAY_SECONDS = 30.0
MAX_BAGS = 10_000
BAG_IDS_PER_MAP = 200
BAG_IDLE_TIMEOUT_SECONDS = 10 * 60
BAG_CLEANUP_INTERVAL_SECONDS = 1
NEW_PLAYER_DEATH_LEVEL = 20
DEATH_RESPAWN_HEALTH = 5
#: Deaths being carried out. The event loop holds tasks weakly, and a respawn
#: whose caller was cancelled must not be collected mid-flight - see
#: `World.player_died`.
RESPAWN_TASKS: set[asyncio.Task] = set()
#: Where a character stands before anything moves them, matching
#: `Character.map_id`. Anything that has to put something down without being
#: told where takes this, so the two cannot drift: they already had, and a
#: creature spawned without a named map landed on the Eternal Lands start map
#: while the player it was meant to fight stood here.
START_MAP = "four_gates"
BEAM_RESPAWN = (START_MAP, *FOUR_GATES_ARRIVAL)
#: Where death sends a character past the new-player level. It was two data,
#: chosen by whether the map file was one of the Eternal Lands second
#: continent's; this world has one underworld and no such filenames.
UNDERWORLD_RESPAWN = (START_MAP, *FOUR_GATES_ARRIVAL)

# Lifetime activity totals the client's counter window reports. Server-owned:
# the client used to increment these when it sent a request, so a rejected
# deposit or a failed mix still counted, and seven of the categories were never
# incremented at all because the client cannot observe the event.
ACTIVITY_KILLS = "Kills"
ACTIVITY_DEATHS = "Deaths"
ACTIVITY_BREAKAGES = "Breakages"
ACTIVITY_CRIT_FAILS = "Crit Fails"
ACTIVITY_USED_ITEMS = "Used Items"
ACTIVITY_EVENTS = "Events"
ACTIVITY_HARVESTS = "Harvests"
ACTIVITY_SPELLS = "Spells"
ACTIVITY_SUMMONS = "Summons"
ACTIVITY_STORAGE = "Storage"
ACTIVITY_DROPS = "Drops"
# One category per mixing skill, keyed by the recipe's skill name.
ACTIVITY_MIX_SKILLS = {
    "alchemy": "Alchemy", "crafting": "Crafting",
    "manufacturing": "Manufacturing", "potion": "Potions",
    "engineering": "Engineering", "tailoring": "Tailoring",
}
ACTIVITY_COUNTERS = (
    ACTIVITY_KILLS, ACTIVITY_DEATHS, ACTIVITY_BREAKAGES, ACTIVITY_CRIT_FAILS,
    ACTIVITY_USED_ITEMS, ACTIVITY_EVENTS, ACTIVITY_HARVESTS,
    ACTIVITY_MIX_SKILLS["alchemy"], ACTIVITY_MIX_SKILLS["crafting"],
    ACTIVITY_MIX_SKILLS["manufacturing"], ACTIVITY_MIX_SKILLS["potion"],
    ACTIVITY_SPELLS, ACTIVITY_SUMMONS, ACTIVITY_MIX_SKILLS["engineering"],
    ACTIVITY_MIX_SKILLS["tailoring"], ACTIVITY_STORAGE, ACTIVITY_DROPS,
)

# What the #god_storage window advertises for every item. Withdrawals conjure
# items instead of moving them, so the figure never decreases.
GOD_STORAGE_QUANTITY = 99999

ACHIEVEMENT_COUNTERS = (
    ("mushrooms_eaten", "Mushrooms eaten"),
    ("plants_harvested", "Plants harvested"),
    ("minerals_harvested", "Minerals harvested"),
    ("lucky_finds", "Lucky finds"),
    ("lucky_crafted", "Lucky crafted"),
    ("nature_damage", "Nature damage"),
    ("bricks_lost", "Bricks lost"),
    ("instances_done", "Instances done"),
    ("low_level_kills", "Low level kills"),
    ("medium_level_kills", "Medium level kills"),
    ("high_level_kills", "High level kills"),
    ("very_high_level_kills", "Very high level kills"),
    ("haidir_missions", "Haidir missions"),
    ("xaquelina_missions", "Xaquelina missions"),
    ("daritha_missions", "Daritha missions"),
    ("dorel_missions", "Dorel missions"),
    ("minel_missions", "Minel missions"),
)

# The beginner tutorial, on Four Gates. Both of these were Eternal Lands
# content: a marker route across Isla Prima to its tavern, and that island's
# nine flowers. Neither existed on the map this profile serves, so the route
# led nowhere and none of the nine could be harvested.
#
# The route follows the west civic street from the arrival to Caldus's
# ferry office, with the monument and deposit as familiar bearings.
TUTORIAL_ROUTE_MARKERS = ((203, 163), (191, 172), (166, 206), (151, 218), (133, 225), (131, 244))
TUTORIAL_ROUTE_NPC = "Ferryman Caldus"
# The last lesson in `tutorial_status`. Raise it as lessons come back.
TUTORIAL_FINAL_STAGE = 11
# Harvest nodes that are really on Four Gates - see
# `config/eloria/harvesting.txt` - in the order a new player should meet them:
# the four teaching gardens by arrival first, then the northern workshop beds.
# The package reserves these stable resource IDs before ordinary scatter.
# (name, x, y, how many)
TUTORIAL_HARVESTS = (('Riverflax', 223, 124, 1), ('Reed', 233, 123, 1), ('Sage', 240, 110, 1), ('Wheat', 223, 109, 1), ('Quartz', 181, 301, 1), ('Seed', 228, 294, 1), ('Stormglass', 167, 306, 1), ('Crystal', 239, 313, 1))

INSTANCE_CHOICES = (
    (1300, "swamp_60", "Swamp 60-80 (60+)"),
    (1301, "mountain_80", "Mountain 80-100 (80+)"),
    (1302, "swamp_100", "Swamp 100-120 (100+)"),
    (1303, "mountain_120", "Mountain 120-140 (120+)"),
    (1304, "ice_120", "Ice 120+ (120++)"),
    (1305, "dungeon_110", "Dungeon 110+ (WTF)"),
)

# How far a creature may be scaled from its species when a spawn group is
# set to a level (see `World.apply_level_scale`): a rabbit asked to be a
# dragon is a very large rabbit rather than a bug in the numbers, and a
# dragon asked to be a rabbit still bites.
LEVEL_SCALE_MIN = 0.3
LEVEL_SCALE_MAX = 3.0
# Object ids for the exits `World.map_exit_entries` states, above anything
# a profile writes for a harvest node or an interactive; how close two
# portal tiles to one destination must be to count as one doorway; and how
# near a waygate object has to stand for a doorway to be left to it.
EXIT_OBJECT_BASE = 60000
EXIT_CLUSTER_TILES = 8
WAYGATE_REACH = 6


SHOP_BUY, SHOP_SELL = 3000, 3001
SHOP_BUY_ITEM, SHOP_SELL_ITEM = 3100, 3200
SHOP_QUANTITY = 3300
SHOP_QUANTITIES = (1, 5, 10, 20, 50, 100, 200, 500, 1000)
SHOP_MAX = SHOP_QUANTITY + len(SHOP_QUANTITIES)
SHOP_CANCEL = 3399
AUCTION_BROWSE, AUCTION_MINE, AUCTION_COLLECT = 6000, 6001, 6002
AUCTION_LISTING_BASE, AUCTION_RENEW, AUCTION_CANCEL = 6100, 6200, 6201
AUCTION_PAGE_SIZE = 20
COMBAT_XP_EVENT_CAP = 15
# Conversation and quest lines share the free 2000-2399 block. Topics are
# indexed from `lore.TOPIC_BASE` by their position in the NPC's own entry, and
# the quest ids are offsets into whatever list the NPC is currently showing,
# so neither depends on the order the profile happens to load in.
QUEST_OFFER_BASE = 2200    # hear what a line the NPC starts is about
QUEST_ACCEPT_BASE = 2240   # take it
QUEST_ADVANCE_BASE = 2280  # report a finished stage, or claim the whole line
QUEST_ABOUT_BASE = 2320    # ask what is still outstanding
QUEST_SLOTS = 40
# How many quest options one NPC's menu may carry before the conversation
# topics are pushed off the bottom of the client's dialogue window.
QUEST_OPTION_LIMIT = 4

WRAITH_MAIN_PERKS, WRAITH_MAIN_ATTRIBUTES, WRAITH_MAIN_NEXUS = 4000, 4001, 4002
WRAITH_PERK_BASE, WRAITH_ATTRIBUTE_BASE, WRAITH_NEXUS_BASE = 4100, 4200, 4300
WRAITH_CONFIRM_YES, WRAITH_CONFIRM_NO = 4400, 4401
WRAITH_PERKS_PER_PAGE = 11


@dataclass
class TradeOffer:
    name: str
    quantity: int
    source_type: int
    source_position: int
    instance_ids: list[int] = field(default_factory=list)


PACKET_DIAGNOSTIC_HISTORY = 200
PACKET_DIAGNOSTIC_WINDOW_SECONDS = 1.0

_PACKET_COMMAND_NAMES: dict[int, str] = {}
for _packet_name, _packet_value in vars(p).items():
    if (_packet_name.isupper() and isinstance(_packet_value, int)
            and 0 <= _packet_value <= 255):
        _PACKET_COMMAND_NAMES.setdefault(_packet_value, _packet_name)


def packet_command_name(command: int) -> str:
    return _PACKET_COMMAND_NAMES.get(command, f"UNKNOWN_{command}")


@dataclass(eq=False)
class Session:
    writer: asyncio.StreamWriter
    character: Character | None = None
    open_bag: int | None = None
    pending_bag: int | None = None
    awaiting_ping_response: bool = False
    # Monotonic time of the last packet this client sent. A half-open TCP
    # connection produces no FIN, so without this a vanished client keeps its
    # character in logged_in_users and blocks its own reconnect until the
    # kernel gives up on the socket. The client's HEART_BEAT keeps it fresh.
    last_client_packet_at: float = 0.0
    last_stats_sent: float = 0.0
    move_task: asyncio.Task | None = None
    # The trigger tile a use click is walking toward. A portal bound to an
    # object (a secret's loose stone, a hatch) fires only for the player who
    # used it, never for someone who happens to step on its tile.
    portal_intent: tuple[str, int, int] | None = None
    # Absolute monotonic deadline for this player's next walking step. Held on
    # the session rather than the route, because a click cancels the route and
    # starts another: without somewhere outside the route to keep the pace,
    # every click bought an immediate step and clicking quickly outran the
    # walk entirely.
    next_step_at: float = 0.0
    post_combat_bag_task: asyncio.Task | None = None
    combat_target: int | None = None
    pending_attack: int | None = None
    aggressors: set[int] = None
    fleeing: bool = False
    # Consecutive failed attempts to break off, reset by the one that works.
    # Lives on the session rather than the character: it exists to stop a run
    # of bad luck from trapping someone in a fight, and a fight does not
    # outlive the connection.
    flee_failures: int = 0
    # Monotonic deadline for the swing given up to turn and run. Distinct from
    # `fleeing`, which gates the loops entirely: this one only costs the
    # player their own round, and nothing an opponent does consults it.
    flee_attempt_until: float = 0.0
    frozen_until: float = 0.0
    food_cooldown_until: float = 0.0
    food_cooldown_max: int = 0
    inventory_slots: list[str | None] = None
    joined_channels: list[int] = None
    active_channel: int = 0
    pending_spell: Spell | None = None
    magic_buffs: dict[int, float] = None
    magic_buff_powers: dict[int, int] = None
    harvest_task: asyncio.Task | None = None
    harvest_count: int = 0
    harvest_hour: int = -1
    mix_task: asyncio.Task | None = None
    harvest_required_level: int | None = None
    mix_status: tuple[str, int] | None = None
    #: Where the ingredients for the running mix are taken from, and what it
    #: is making. The window is told both so a queue can send its next batch
    #: the moment this one ends.
    mix_from_storage: bool = False
    mix_output: str = ""
    mix_remaining: int = 0
    #: How many of `mix_output` this run has actually produced. Survives the
    #: end of the run, because the last packet a queue receives is the one
    #: that has to say how many came out.
    mix_made: int = 0
    last_mix_at: float = 0.0
    potion_cooldowns: dict[str, float] = None
    visible_animals: set[int] = None
    visible_npcs: set[int] = None
    # Actors shown from the maps adjoining this client's own across a land
    # seam (creatures, NPCs and players alike): actor id -> the map it stands on.
    visible_adjacent: dict[int, str] = None
    storage_open: bool = False
    storage_category: int = 0
    # Whether the open storage window is the invasion-master #god_storage
    # view rather than the character's own storage. Never persisted: the
    # privilege is re-checked against server settings on every use.
    god_storage_open: bool = False
    peer_ip: str = ""
    demigod: bool = False
    sitting: bool = False
    disconnect_requested: bool = False
    dying: bool = False
    pending_shop: tuple[int, str, int] | None = None
    waypoint: tuple[str, int, int, str] | None = None
    auction_listing_ids: list[int] | None = None
    selected_auction_listing: int | None = None
    # Which conversation flags this session has heard raised. Held here rather
    # than on the character on purpose: the thread is the content, so
    # re-walking two options after a reconnect costs a player nothing, while
    # persisting several hundred flags each would cost the database a great
    # deal. Anything that must outlast a logout is a quest line.
    conversation: set[str] | None = None
    pending_wraith: tuple[str, str] | None = None
    combat_xp_events: dict[int, list[int]] = None
    last_pm_sender: str = ""
    leave_guild_confirmation: bool = False
    trade_partner: Session | None = None
    trade_offers: list[TradeOffer | None] = None
    trade_accept_state: int = 0
    trade_destinations: list[int] = None
    pending_trade_from: tuple[int, float] | None = None
    trade_storage_available: bool = False
    trade_operation_id: str = ""
    ranging_task: asyncio.Task | None = None
    ranging_target: int | None = None
    poison_task: asyncio.Task | None = None
    poison_damage: int = 0
    poison_hits: int = 0
    regeneration_task: asyncio.Task | None = None
    last_map_object_id: int | None = None
    connection_start: tuple[str, str, int, int, int | None] | None = None
    packet_history: deque[tuple[float, int, int, int]] | None = None
    packet_window: deque[tuple[float, int]] | None = None
    packets_sent: int = 0
    packet_bytes_sent: int = 0
    peak_write_buffer: int = 0
    connected_at: float = 0.0
    client_capabilities: set[str] | None = None
    # The 64-bit experience view this client was last told about. None before
    # it has been told anything, so the first pass always sends.
    experience_signature: tuple | None = None
    # The perk catalogue rows this client was last sent, or None before it
    # has been sent any. The rows carry the server's refusals - not enough
    # pick points, not enough gold, a conflict - and every one of those moves
    # on paths that have nothing to do with perks, so the catalogue is
    # reconciled against this rather than restated from each of them.
    perk_catalog_rows: list | None = None
    # The worn-slot mask this client was last told, or -1 before it has been
    # told anything. Starting at -1 rather than 0 means a character carrying
    # nothing worn is still sent an explicit empty mask once, instead of the
    # client being left to assume it.
    worn_slot_mask: int = -1
    # What this client was last told its slots hold, so the loop below can
    # send the difference. None until the first reconcile, which is not the
    # same as an empty inventory.
    inventory_names: tuple | None = None
    # Resolved once on first send; the writer's transport never changes.
    _transport: object | None = None
    # Packets waiting for this tick's flush. CoordinateFrame tags let explicit
    # coordinate producers be rejected if their captured context becomes stale.
    outbox: list[bytes | CoordinateFrame] = None
    # Explicit injection only; ordinary login/dispatch does not enable this yet.
    coordinate_state: object | None = None
    _coordinate_transition: bool = False
    _coordinate_lifecycle: bool = False

    def __post_init__(self):
        if self.aggressors is None:
            self.aggressors = set()
        if self.client_capabilities is None:
            self.client_capabilities = set()
        if self.auction_listing_ids is None:
            self.auction_listing_ids = []
        if self.conversation is None:
            self.conversation = set()
        if self.inventory_slots is None:
            self.inventory_slots = []
        if self.joined_channels is None:
            self.joined_channels = []
        if self.magic_buffs is None:
            self.magic_buffs = {}
        if self.magic_buff_powers is None:
            self.magic_buff_powers = {}
        if self.potion_cooldowns is None:
            self.potion_cooldowns = {}
        if self.visible_animals is None:
            self.visible_animals = set()
        if self.visible_npcs is None:
            self.visible_npcs = set()
        if self.visible_adjacent is None:
            self.visible_adjacent = {}
        if self.combat_xp_events is None:
            self.combat_xp_events = {}
        if self.trade_offers is None:
            self.trade_offers = [None] * 16
        if self.trade_destinations is None:
            self.trade_destinations = [1] * 16
        if self.packet_history is None:
            self.packet_history = deque(maxlen=PACKET_DIAGNOSTIC_HISTORY)
        if self.packet_window is None:
            self.packet_window = deque()
        if self.outbox is None:
            self.outbox = []
        if self.connected_at <= 0.0:
            self.connected_at = time.monotonic()

    def queue(self, data: bytes | CoordinateFrame | None) -> None:
        """Hold a packet for this tick's flush.

        Per-actor fan-out is the server's largest outbound cost: five hundred
        players watching one creature turned every swing into five hundred
        socket writes. Queued frames are concatenated into one write per
        session per tick. Ordering against send() is preserved because send()
        emits whatever is queued ahead of its own payload.
        """
        if data is None or (isinstance(data, CoordinateFrame)
                            and not self.coordinate_token_current(data.token)):
            return
        self.outbox.append(data)

    def install_coordinate_transport(self, catalog) -> None:
        """Inject the world's verified catalog before login; no negotiation IO."""
        if self.coordinate_state is not None or self.character is not None or self._coordinate_transition:
            raise ValueError("coordinate transport must be installed once before login")
        self.coordinate_state = CoordinateSession(catalog)

    def coordinate_token(self):
        if self.coordinate_state is None:
            raise ValueError("coordinate transport is not configured")
        return self.coordinate_state.capture()

    def coordinate_token_current(self, token) -> bool:
        return bool(self.coordinate_state and self.coordinate_state.is_current(token))

    def queue_coordinates(self, token, data: bytes) -> bool:
        """Tag already map-aware bytes; stale producers cause no side effects."""
        if not self.coordinate_token_current(token):
            return False
        if not isinstance(data, bytes):
            raise ValueError("coordinate output must be bytes")
        self.outbox.append(CoordinateFrame(token, data))
        return True

    async def send_coordinates(self, token, data: bytes) -> bool:
        if not self.coordinate_token_current(token):
            return False
        if not isinstance(data, bytes):
            raise ValueError("coordinate output must be bytes")
        return await self.send(CoordinateFrame(token, data)) is not False

    def _take_outbox(self) -> list[bytes]:
        queued, self.outbox = self.outbox, []
        return [entry.data if isinstance(entry, CoordinateFrame) else entry
                for entry in queued if not isinstance(entry, CoordinateFrame)
                or self.coordinate_token_current(entry.token)]

    def reset_coordinate_transport(self) -> None:
        """Connection reset invalidates tokens and all pending output."""
        if self.coordinate_state is not None:
            self.coordinate_state.close()
        self.coordinate_state = None
        self.outbox.clear()

    async def activate_coordinates(self, map_id: str, client_name: str, handles,
                                   *, commit=None):
        """Write old queue + activate + CHANGE_MAP atomically, then allow drain.

        `commit`, if supplied, must synchronously perform already-validated world
        mutations without IO. Once write is attempted a failure closes this
        connection; a partially delivered boundary cannot be safely rolled back.
        All preparation failures occur before queue/state/world mutation.
        """
        if self.coordinate_state is None or self._coordinate_transition:
            raise ValueError("coordinate transport absent or activation in progress")
        if (not isinstance(client_name, str) or not client_name or "\0" in client_name
                or len(client_name.encode("utf-8")) > 65530):
            raise ValueError("invalid map client name")
        if commit is not None and (not callable(commit) or asyncio.iscoroutinefunction(commit)
                                   or asyncio.iscoroutinefunction(getattr(commit, "__call__", None))):
            raise ValueError("coordinate commit must be synchronous")
        state = self.coordinate_state
        activation = state.prepare_activation(map_id, handles)
        old_frames = self._take_outbox()  # evaluate tags under the OLD context
        boundary = (p.packet(p.ELORIA_COORDINATE_CONTEXT, activation.payload)
                    + p.packet(p.CHANGE_MAP, client_name.encode("utf-8") + b"\0"))
        self._coordinate_transition = True
        state.begin(activation)

        def apply_commit():
            state.commit(activation)
            if commit is not None:
                result = commit()
                if result is not None:
                    if asyncio.iscoroutine(result):
                        result.close()
                    raise ValueError("coordinate commit must return None")

        try:
            await self._write(b"".join(old_frames) + boundary, after_write=apply_commit)
            if self.coordinate_state is not state or not state.is_current(activation.token):
                raise ValueError("coordinate connection reset during activation")
        except BaseException:
            # No rollback after write: bytes may already be on the socket.
            self.reset_coordinate_transport()
            self.disconnect_requested = True
            close = getattr(self.writer, "close", None)
            if callable(close):
                close()
            raise
        finally:
            self._coordinate_transition = False
        return activation.token

    async def flush(self) -> None:
        """Write this session's queued packets as a single frame."""
        if not self.outbox:
            return
        frames = self._take_outbox()
        if frames:
            await self._write(b"".join(frames))

    async def send(self, data: bytes | CoordinateFrame | None):
        if data is None:
            return False
        if isinstance(data, CoordinateFrame):
            if not self.coordinate_token_current(data.token):
                return False
            data = data.data
        if self.outbox:
            frames = self._take_outbox()
            frames.append(data)
            data = b"".join(frames)
        await self._write(data)

    async def _write(self, data: bytes, *, after_write=None):
        now = time.monotonic()
        command = data[0] if data else -1
        transport = self._transport
        if transport is None:
            transport = self._transport = getattr(self.writer, "transport", None)
        self.writer.write(data)
        if after_write is not None:
            after_write()
        write_buffer = transport.get_write_buffer_size() if transport else 0
        self.packet_history.append((now, command, len(data), write_buffer))
        self.packet_window.append((now, len(data)))
        cutoff = now - PACKET_DIAGNOSTIC_WINDOW_SECONDS
        while self.packet_window and self.packet_window[0][0] < cutoff:
            self.packet_window.popleft()
        self.packets_sent += 1
        self.packet_bytes_sent += len(data)
        self.peak_write_buffer = max(self.peak_write_buffer, write_buffer)
        # Avoid a syscall/yield for every tiny actor packet. Keep backpressure for
        # genuinely slow clients while allowing the event loop to coalesce writes.
        if transport and write_buffer >= 64 * 1024:
            await self.writer.drain()

    async def send_many(self, frames: list[bytes | CoordinateFrame | None]) -> None:
        """Send several packets in one socket write.

        EL frames are self-delimiting on a byte stream, so concatenating them
        is transparent to the client and saves a write per actor. Filling a
        player's view could otherwise mean hundreds of one-packet writes.
        """
        if any(isinstance(frame, CoordinateFrame) and not self.coordinate_token_current(frame.token)
               for frame in frames):
            return
        token = next((frame.token for frame in frames if isinstance(frame, CoordinateFrame)), None)
        frames = [frame.data if isinstance(frame, CoordinateFrame) else frame
                  for frame in frames if frame is not None]
        if not frames:
            return
        joined = b"".join(frames)
        await self.send(CoordinateFrame(token, joined) if token is not None else joined)

    def packet_diagnostic_lines(self) -> list[str]:
        """Return payload-free recent send diagnostics for disconnect logging."""
        now = time.monotonic()
        recent_packets = len(self.packet_window)
        recent_bytes = sum(size for _, size in self.packet_window)
        current_buffer = 0
        transport = getattr(self.writer, "transport", None)
        if transport:
            current_buffer = transport.get_write_buffer_size()
        character = self.character
        location = (f"{character.map_id}@({character.x},{character.y})"
                    if character else "not-logged-in")
        counts = Counter(command for _, command, _, _ in self.packet_history)
        commands = ",".join(
            f"{packet_command_name(command)}:{count}"
            for command, count in counts.most_common(12)) or "none"
        lines = [
            (f"summary player={character.name if character else '-'} "
             f"peer={self.peer_ip or 'unknown'} location={location} "
             f"connected={now - self.connected_at:.1f}s "
             f"sent={self.packets_sent}/{self.packet_bytes_sent}B "
             f"last_1s={recent_packets}/{recent_bytes}B "
             f"buffer={current_buffer}B peak_buffer={self.peak_write_buffer}B "
             f"visible={len(self.visible_animals)} commands={commands}")
        ]
        for sent_at, command, size, buffer_size in self.packet_history:
            lines.append(
                f"packet age={now - sent_at:.3f}s "
                f"type={packet_command_name(command)}({command}) "
                f"size={size}B buffer={buffer_size}B")
        return lines


def boss_fight(boss: Boss) -> BossFight | None:
    """The fight a `[boss]` block describes, or None if it describes none.

    None rather than an empty record, because the record's presence is what
    `process_boss_response` reads as "this creature answers back". A boss with
    nothing authored is the statblock it has always been.
    """
    if not (boss.heal_charges or boss.summon_thresholds):
        return None
    return BossFight(
        heal=boss.heal, heal_charges=boss.heal_charges, summon=boss.summon,
        thresholds=boss.summon_thresholds, summons_left=boss.summon_budget)


def check_boss_content(bosses: dict[str, Boss],
                       creatures: Mapping[str, CreatureDefinition],
                       items: Mapping[str, object]) -> None:
    """Refuse a boss whose fight names gear or a creature nobody has.

    Both would otherwise fail in silence rather than loudly: an unknown item
    is skipped by `equipment_stats`, so a mistyped weapon simply halves the
    boss's damage, and an unknown creature raises deep inside a combat round
    the first time the boss drops past a threshold. This is the load that
    turns either into a line about a file.
    """
    for boss in bosses.values():
        for weapon in boss.weapons:
            if weapon not in items:
                raise ValueError(
                    f"boss {boss.name}: weapon {weapon!r} is not an item in "
                    "this profile's catalogue")
        if boss.summon and boss.summon not in creatures:
            raise ValueError(
                f"boss {boss.name}: summon {boss.summon!r} is not a creature "
                "in this profile")


def check_territory_raid_content(territories: Mapping[str, Territory],
                                 creatures: Mapping[str, CreatureDefinition],
                                 spawn_groups: Mapping[str, SpawnGroup],
                                 force_size: int) -> None:
    """Reject raid dependencies at startup, not on the first six-hour tick."""
    unknown_groups = sorted({
        group.casefold()
        for territory in territories.values()
        for group in (territory.attacker_group, territory.defender_group)
        if group and group.casefold() not in spawn_groups
    })
    if unknown_groups:
        raise ValueError(
            "Unknown territory raid spawn group(s): "
            + ", ".join(unknown_groups))
    uses_fallback = force_size > 0 and any(
        not territory.attacker_group or not territory.defender_group
        for territory in territories.values())
    if uses_fallback and TERRITORY_RAID_FALLBACK_CREATURE not in creatures:
        raise ValueError(
            "Territory raids require fallback creature "
            f"{TERRITORY_RAID_FALLBACK_CREATURE!r}")


class NoFreeCreatureTile(ValueError):
    """Placement is temporarily blocked by collision or other actors."""


@dataclass
class ActiveSpawnGroup:
    definition: SpawnGroup
    invasion: bool
    activated_at: float
    actor_ids: set[int]
    instance_name: str = ""
    boss_due_at: float | None = None
    boss_spawned: bool = False
    boss_actor_id: int | None = None
    # A gauntlet lands the same group on whichever copy of its map the party
    # holds, so the map and the key it is filed under are the activation's,
    # not the definition's. Empty means the definition's own.
    map_id: str = ""
    key: str = ""
    # The a/d level the group's creatures were scaled to when it was
    # activated, or 0 for creatures standing at their species' own level.
    level_target: int = 0
    pending_count: int = 0
    spawn_index: int = 0
    reinforce_at: float = 0.0


@dataclass
class ActiveInstance:
    definition: InstanceDefinition
    wave: int
    wave_started_at: float
    group_names: set[str]
    participant_ids: set[int]


from .magic_runtime import MagicRuntime


# A land crossing used to be one gate seven lanes wide, so the whole portal
# table was a couple of hundred rows and every asker simply scanned it. A seam
# a player may cross wherever the ground allows is the width of the border
# instead, and `check_portal` asks about a tile on every step of every walking
# session - a scan there is the map's whole boundary per step per walker.
#
# These take the world rather than being methods on it: a good deal of the
# suite exercises one World method against a stand-in object that has only the
# fields that method reads, and the table is one of those fields.
def portal_index(world) -> tuple[dict, dict]:
    """The portal table by tile and by map, rebuilt whenever the table changes.

    The index is cached on the world and thrown away when the table it was
    built from is no longer the table bound there: the sky map adds and removes
    its own portal at runtime and the road content builders extend theirs, and
    each does so by binding a new tuple, which is what this notices.
    """
    portals = getattr(world, 'portals', ())
    cached = getattr(world, '_portal_index_cache', None)
    if cached is not None and cached[0] is portals:
        return cached[1], cached[2]
    at: dict[tuple[str, int, int], list] = {}
    leaving: dict[str, list] = {}
    for portal in portals:
        at.setdefault((portal.source, portal.x, portal.y), []).append(portal)
        leaving.setdefault(portal.source, []).append(portal)
    try:
        world._portal_index_cache = (portals, at, leaving)
    except AttributeError:
        pass  # a stand-in that refuses new attributes still gets its answer
    return at, leaving


def portal_at(world, map_id: str, x: int, y: int):
    """The portal standing on one tile: the first in table order, as a scan found."""
    found = portal_index(world)[0].get((map_id, x, y))
    return found[0] if found else None


def portals_leaving(world, map_id: str) -> list:
    """Every portal that leaves one map, in table order."""
    return portal_index(world)[1].get(map_id, [])


def walkway_portals(world, map_id: str) -> frozenset:
    """The tiles of one map that change maps under anyone who steps on them.

    An object portal fires only when its object is used, so it is no hazard
    to a walk past it; every other portal fires on the step.
    """
    portals = getattr(world, 'portals', ())
    cached = getattr(world, '_walkway_portal_cache', None)
    if cached is None or cached[0] is not portals:
        cached = (portals, {})
        try:
            world._walkway_portal_cache = cached
        except AttributeError:
            pass
    tiles = cached[1].get(map_id)
    if tiles is None:
        tiles = frozenset((portal.x, portal.y) for portal in portals_leaving(world, map_id)
                          if portal.object_id is None)
        cached[1][map_id] = tiles
    return tiles


class World(MagicRuntime):
    # A profile that ships no conversation and no quest lines has none, and so
    # does a World built without running __init__ - which several tests do to
    # exercise one method in isolation. Empty is the honest answer in both
    # cases, so it is the class default rather than something only the
    # constructor knows about.
    npc_lore: dict[str, lore.NPCLore] = {}
    conversation_flags: frozenset[str] = frozenset()
    questlines: dict[str, ql.Questline] = {}
    questline_visit_maps: frozenset[str] = frozenset()
    achievement_catalogue: AchievementCatalogue = AchievementCatalogue((), {}, {})

    def __init__(self, database, creatures: dict[str, CreatureDefinition],
                 drop_tables=None, map_path: str = f"{PROFILE}/maps.txt",
                 spells=None,
                 harvesting_path: str = f"{PROFILE}/harvesting.txt",
                 recipes_path: str = f"{PROFILE}/recipes.txt",
                 spawns_path: str = f"{PROFILE}/spawns.txt",
                 settings: ServerSettings | None = None,
                 books_path: str = f"{PROFILE}/books.txt",
                 special_areas_path: str = f"{PROFILE}/special_areas.txt",
                 shops_path: str = f"{PROFILE}/shops.txt",
                 normal_spawn_path: str = f"{PROFILE}/spawn_groups/normal",
                 invasion_spawn_path: str = f"{PROFILE}/spawn_groups/invasion",
                 instance_path: str = f"{PROFILE}/instances",
                 rare_mix_path: str = f"{PROFILE}/rare_mixes.txt",
                 emotes_path: str = "",
                 spell_balance_path: str = f"{PROFILE}/spell_balance.txt",
                 territories_path: str = f"{PROFILE}/territories.txt"):
        self.content_options = {k: v for k, v in locals().copy().items()
                                if k not in {'self', 'database', 'creatures', 'drop_tables', '__class__'}}
        self.db = database
        # Explicitly installed, verified metadata only. This does not enable
        # coordinate transport; negotiation remains inactive until integration.
        self.coordinate_catalog = None
        self.creatures = creatures
        self.drop_tables = drop_tables if drop_tables is not None else load_drops(f"{PROFILE}/drops.txt")
        self.maps, self.portals = load_maps(map_path)
        # Beside the map table it describes, rather than from PROFILE: a test
        # or a second profile that points `map_path` somewhere else means its
        # maps, and reading the shipped manifest for them would publish the
        # wrong digests. Missing is fine and means the server publishes none.
        self.map_digests = load_map_digests(
            Path(map_path).with_name("client_content_manifest.json"))
        from .exterior_connections import load_land_connections
        self.land_connections = load_land_connections(
            Path(map_path).with_name("exterior_connections.json"))
        from .exterior_connections import load_land_frames
        self.land_frames = load_land_frames(
            Path(map_path).with_name("exterior_connections.json"))
        self.spells = spells or {}
        self.spell_balance = load_spell_balance(spell_balance_path)
        self.harvest_resources, self.harvest_nodes = load_harvesting(harvesting_path)
        interactives_path = Path(harvesting_path).with_name("interactives.txt")
        self.interactives = load_interactives(interactives_path)
        # The wire protocol and client index every kind of map object by the
        # same ID. A door sharing a resource's ID makes that resource vanish.
        object_conflicts = self.harvest_nodes.keys() & self.interactives.keys()
        if object_conflicts:
            raise ValueError(
                "Harvest and interactive object IDs must be unique per map: "
                + ", ".join(f"{map_id}:{object_id}"
                            for map_id, object_id in sorted(object_conflicts)))
        # Beside the harvest table it belongs to, and nowhere else: this used
        # to fall back to `config/rare_harvest.txt`, so a profile shipping no
        # rare table quietly harvested the other one's - and its entries name
        # items, which the fallback profile may not even define. A profile
        # that ships none has none, the same rule the emotes follow below.
        rare_harvest_path = Path(harvesting_path).with_name("rare_harvest.txt")
        self.rare_harvest = (load_rare_harvest(rare_harvest_path, ITEMS)
                             if rare_harvest_path.is_file() else {})
        self.recipes = load_recipes(recipes_path)
        self.rare_mixes = load_rare_mixes(rare_mix_path)
        # Emotes live beside the recipes they were profiled with, so a profile
        # that ships none simply has none rather than borrowing another's.
        self.emotes = load_emotes(
            emotes_path or Path(recipes_path).with_name("emotes.txt"))
        # Which music bed plays under each map. A map that is not listed
        # plays nothing, which is a real answer rather than a missing one.
        self.map_music = load_music(Path(recipes_path).with_name("music.txt"))
        # The sky over each map, and the fires burning on it. A map with no
        # climate is always clear: weather is content, and a map that declares
        # none has none rather than getting a default it never asked for.
        self.climates, self.fires = load_weather(
            Path(recipes_path).with_name("weather.txt"))
        self.weather: dict[str, tuple[int, int]] = {}
        # Objects placed into a map while it is being played in, by map and id.
        self.world_objects: dict[str, dict[int, tuple[int, int, int, str]]] = {}
        recipe_outputs = {recipe.output for recipe in self.recipes}
        unknown_rare_bases = set(self.rare_mixes) - recipe_outputs
        unknown_rare_results = {
            entry.result for entry in self.rare_mixes.values()
            if entry.result not in ITEMS}
        if unknown_rare_bases:
            raise ValueError(
                "Rare mix bases without recipes: "
                + ", ".join(sorted(unknown_rare_bases)))
        if unknown_rare_results:
            raise ValueError(
                "Unknown rare mix results: "
                + ", ".join(sorted(unknown_rare_results)))
        self.books = load_books(books_path, ITEMS)
        # What the region NPCs have to say, and the quest lines that run
        # through them. Both live beside the profile's other content, and a
        # profile that ships neither simply has neither: the compatibility
        # profile is Seridia and has no business carrying Nymara's politics.
        dialogue_path = Path(recipes_path).with_name("npc_dialogue.txt")
        self.npc_lore = (lore.load_npc_dialogue(dialogue_path)
                         if dialogue_path.is_file() else {})
        self.conversation_flags = lore.gating_flags(self.npc_lore)
        questline_path = Path(recipes_path).with_name("questlines.txt")
        self.questlines = (ql.load_questlines(questline_path)
                           if questline_path.is_file() else {})
        # What there is to be proud of in this world, and the titles it grants.
        # Beside the rest of the profile's content, and a profile that ships
        # none has none - the compatibility profile is Eternal Lands', which
        # never had achievements at all.
        achievements_path = Path(recipes_path).with_name("achievements.txt")
        self.achievement_catalogue = (
            load_achievements(achievements_path) if achievements_path.is_file()
            else AchievementCatalogue((), {}, {}))
        # Movement is the hottest loop the server has, and it reports a visit
        # on every step. Knowing up front which maps any line actually asks
        # about turns that report into one set lookup on the maps that none do.
        self.questline_visit_maps = ql.visit_maps(self.questlines)
        unknown_quest_items = {
            name for line in self.questlines.values()
            for reward in [line.reward, *(stage.reward for stage in line.stages)]
            for name, _ in reward.items if name not in ITEMS}
        if unknown_quest_items:
            raise ValueError(
                f"Unknown quest reward items: {', '.join(sorted(unknown_quest_items))}")
        self.special_areas = load_special_areas(special_areas_path)
        self.shops = load_shops(shops_path)
        unknown_shop_items = {entry.name for shop in self.shops.values() for entry in shop.items
                              if entry.name not in ITEMS}
        if unknown_shop_items:
            raise ValueError(f"Unknown shop items: {', '.join(sorted(unknown_shop_items))}")
        # Built on first use: it reads every acquisition table, and a world
        # that never opens a storage window should not pay for it.
        self._item_rarity: dict[str, int] | None = None
        self.knowledge_catalog = tuple(dict.fromkeys(
            book.knowledge for book in self.books.values() if not book.repeatable))
        self.knowledge_index = {name: index for index, name in enumerate(self.knowledge_catalog)}
        self.spawn_definitions = load_spawns(spawns_path)
        self.spawn_groups = load_spawn_groups(normal_spawn_path)
        self.invasion_spawn_groups = load_spawn_groups(invasion_spawn_path)
        boss_file = Path(invasion_spawn_path) / "bosses.def"
        self.bosses = load_bosses(boss_file) if boss_file.exists() else {}
        check_boss_content(self.bosses, self.creatures, ITEMS)
        instance_root = Path(instance_path)
        self.instances = {definition.name.casefold(): definition for definition in
                          (load_instance_control(path) for path in sorted(instance_root.glob("*.def")))} \
                         if instance_root.exists() else {}
        self.active_spawn_groups: dict[str, ActiveSpawnGroup] = {}
        self.active_instances: dict[str, ActiveInstance] = {}
        self._last_spawn_slot: tuple[int, int] | None = None
        self.settings = settings or ServerSettings()
        territories = (load_territories(territories_path)
                       if Path(territories_path).is_file() else {})
        check_territory_raid_content(
            territories, self.creatures,
            {**self.spawn_groups, **self.invasion_spawn_groups},
            self.settings.territory_raid_force_size)
        self.territory_raids = TerritoryRaidService(
            territories, self.settings.territory_raid_duration_seconds)
        load_raid_state = getattr(self.db, "load_global_state", None)
        if callable(load_raid_state):
            self.territory_raids.restore(load_raid_state("territory_raids", ""))
        self._last_raid_tick = 0.0
        self._next_raid_at = (
            time.time() + self.settings.territory_raid_interval_seconds
            if self.settings.territory_raid_interval_seconds else 0.0)
        self.collision_maps = load_collision_maps(
            self.settings.map_data_directory, self.maps,
            self.settings.max_walk_height_change)
        for map_id, collision in self.collision_maps.items():
            self.collision_maps[map_id] = with_storage_collision(
                collision, ((entry.x, entry.y) for entry in self.interactives.values()
                            if entry.map_id == map_id and entry.role == "storage"))
        # (map id, width, depth) -> that map eroded so a body of that size may
        # stand wherever it says walkable. Built on demand by collision_for:
        # most maps never hold a creature larger than one tile, and eroding
        # every map for a size nothing on it uses is work for nothing.
        self._footprint_collision: dict[tuple[str, int, int], object] = {}
        unknown_items = {drop.item for table in self.drop_tables.values()
                         for drop in table if drop.item not in ITEMS}
        if unknown_items:
            raise ValueError(f"Unknown drop items: {', '.join(sorted(unknown_items))}")
        self.sessions: set[Session] = set()
        self.guild_tag_color_for = None
        # The server's PartyBook, injected after construction like the guild
        # colour seam above. None while the world runs without one, which is
        # every unit test that builds a World directly.
        self.parties = None
        self.animals: dict[int, Animal] = {}
        self.animals_by_map: dict[str, set[int]] = defaultdict(set)
        # map id -> (built_at, cell -> creature ids). See creature_index.
        self._creature_index: dict[str, tuple[float, dict[tuple[int, int], list[Animal]]]] = {}
        # A* allowance for the AI tick in progress. None outside the loop, so
        # anything calling in directly is never refused a route.
        self._path_budget: int | None = None
        self._path_deadline = 0.0
        self._last_upkeep_at = 0.0
        # How many outbox_flush_loop tasks are running. See deliver().
        self._flush_drivers = 0
        # True for the duration of one AI tick. See creature_index.
        self._index_pinned = False
        # actor id -> the sessions currently showing that creature, so an
        # update reaches its viewers without scanning every session.
        self.animal_viewers: dict[int, set[Session]] = defaultdict(set)
        # Sessions shown an actor across a land seam, by actor id: creatures,
        # NPCs and players. A creature's adjacent viewers are in animal_viewers too.
        self.adjacent_viewers: dict[int, set[Session]] = defaultdict(set)
        # actor id -> the Rotbrand burning through that creature. Kept so a
        # second cast refreshes the rot instead of stacking a second one, the
        # way `start_poison` refuses to stack on a player.
        self.creature_rot_tasks: dict[int, asyncio.Task] = {}
        # Actor ids are a 16-bit wire field, so they are recycled rather than
        # counted upward forever. See allocate_id and release_id.
        self._free_actor_ids: deque[int] = deque()
        self._retired_actor_ids: deque[tuple[float, int]] = deque()
        self.actor_move_events: dict[int, deque[float]] = defaultdict(deque)
        self.next_actor_id = 100
        self.bags: dict[int, tuple[int, int, list[tuple[str, int]]]] = {}
        self.bag_maps: dict[int, str] = {}
        self.bag_activity: dict[int, float] = {}
        self.next_bag_id = 0
        self._last_bag_cleanup_at = 0.0
        self.npcs = {
            90: (NPCActor(90, "Regia", 15, 369, 3, 20, 20, p.NPC), "whitestone_insides", 400,
                 tuple(range(0, 14))),
            91: (NPCActor(91, "Salina", 128, 363, 3, 20, 20, p.NPC,
                          appearance={"skin":2,"hair":2,"shirt":6,"pants":2,"boots":2,"head":0,"eyes":2}), "whitestone_insides", 700,
                 tuple(range(14, 26))),
        }
        self.npc_roles = {90: "sigil", 91: "sigil"}
        self.npc_dialogues = {}
        self.combatants: set[int] = set()
        self.player_attacks: set[tuple[int, int]] = set()
        self.pk_duels: set[tuple[int, int]] = set()
        load_world_state = getattr(self.db, "load_world_state", None)
        world_state = (load_world_state() if callable(load_world_state) else {
            "game_minute": 120,
            "elapsed_days": 0,
            "special_day_key": "ordinary",
            "special_day_xp_bonus": 1.0,
        })
        self.game_minute = int(world_state["game_minute"]) % 360
        self.elapsed_days = max(0, int(world_state["elapsed_days"]))
        self.special_day = SPECIAL_DAYS.get(
            str(world_state["special_day_key"]), ORDINARY)
        self.special_day_xp_bonus = float(
            world_state["special_day_xp_bonus"])
        for group in self.spawn_groups.values():
            if group.spawn_type == "normal":
                self.activate_spawn_group(group, invasion=False)
        self.populate_static_spawns()
        lantern.initialize(self, harvesting_path)
        bell.initialize(self, harvesting_path)
        sky.initialize(self, harvesting_path)
        landing_runtime.initialize(self, harvesting_path)

    def configure_coordinate_catalog(self, catalog) -> None:
        """Install a verified startup snapshot without changing map coordinates.

        No file discovery, collision reload, minima assignment, or capability
        negotiation happens here. A failed/repeated/live install changes nothing.
        """
        from .coordinate_catalog import CoordinateProfileCatalog
        if not isinstance(catalog, CoordinateProfileCatalog):
            raise ValueError("expected a verified coordinate profile catalog")
        if getattr(self, "coordinate_catalog", None) is not None or self.sessions:
            raise ValueError("coordinate catalog can only be installed once before sessions")
        if any(map_id not in self.maps for map_id in catalog.map_ids):
            raise ValueError("coordinate catalog contains an unknown world map")
        catalog.validate_collisions(self.collision_maps)
        self.coordinate_catalog = catalog

    def populate_static_spawns(self) -> int:
        """Instantiate every `spawns.txt` entry as a live creature.

        The table was loaded and then used for nothing, so the whole Nymara
        wildlife roster existed in configuration and in the client's model
        registry and never appeared in the world: the only creatures a player
        could meet were summons, invasions and spawn-group encounters, and no
        `.def` groups are enabled. Each of these is an ordinary animal, so the
        normal death, drop and respawn cycle applies to it unchanged.
        """
        spawned = 0
        for definition in self.spawn_definitions:
            if definition.map_id not in self.maps:
                log.warning("spawn skipped: unknown map %s", definition.map_id)
                continue
            if definition.creature not in self.creatures:
                log.warning("spawn skipped: unknown creature %s", definition.creature)
                continue
            if self.creatures[definition.creature].boss:
                # A boss creature exists to be placed by a spawn group when
                # its invasion earns one. Standing in a field it is just a
                # very large animal that a player will walk into by accident.
                log.warning("spawn skipped: %s is a boss creature",
                            definition.creature)
                continue
            self.spawn_animal(definition.creature, definition.x, definition.y,
                              map_id=definition.map_id, tame=definition.tame,
                              leash=definition.leash)
            spawned += 1
        if spawned:
            log.info("populated %d static creature spawns across %d maps", spawned,
                     len({definition.map_id for definition in self.spawn_definitions}))
        return spawned

    @property
    def elder_date(self) -> ElderDate:
        return ElderDate.from_elapsed_days(self.elapsed_days)

    def save_world_state(self) -> None:
        save_world_state = getattr(
            getattr(self, "db", None), "save_world_state", None)
        if callable(save_world_state):
            save_world_state(
                game_minute=self.game_minute,
                elapsed_days=self.elapsed_days,
                special_day_key=self.special_day.key,
                special_day_xp_bonus=self.special_day_xp_bonus)

    def day_message(self) -> str:
        if self.special_day is ORDINARY:
            return "Today is an ordinary day."
        return (f"Today is a special day:\n{self.special_day.name}\n"
                f"{self.special_day.description}")

    def experience_multiplier(self, skill: str, character: Character | None = None) -> float:
        multiplier = (self.special_day.multiplier(skill) * self.special_day_xp_bonus
                      * self.territory_raids.multiplier(skill))
        if character:
            # A school: a secret room where the same work teaches more.
            multiplier *= self.area_multiplier(character, EXPERIENCE)
        return multiplier * (god_xp_multiplier(character, skill) if character else 1.0)

    def save_territory_raids(self) -> None:
        save = getattr(self.db, "save_global_state", None)
        if callable(save):
            save("territory_raids", self.territory_raids.snapshot())

    def raid_combat_zone(self, first: Character, second: Character) -> PKZone | None:
        zone = shared_pk_zone(first, second)
        if zone:
            return zone
        raid = self.territory_raids.active
        if (raid and not raid.finished and first.map_id == second.map_id
                and first.map_id == raid.defender.map_id
                and self.territory_raids.opponents(first.username, second.username)):
            return PKZone(first.map_id, no_drops=True, multi_combat=True,
                          label="territory raid")
        return None

    async def start_territory_raid(self, aggressor: str, defender: str):
        left = self.territory_raids.territories.get(aggressor.casefold())
        right = self.territory_raids.territories.get(defender.casefold())
        if left and right:
            route = next((portal for portal in portals_leaving(self, right.map_id)
                          if portal.destination == left.map_id), None)
            entry = (route.x, route.y) if route else left.attacker_spawn
            for connected in list(self.sessions):
                c = connected.character
                team = self.territory_raids.pending_choices.get(c.username.casefold()) if c else None
                if team in (left.key, right.key):
                    spawn = entry if team == left.key else right.defender_spawn
                    self.require_coordinate_destination(connected, right.map_id, *spawn)
        raid = self.territory_raids.start(aggressor, defender)
        route = next((
            portal for portal in portals_leaving(self, raid.defender.map_id)
            if portal.destination == raid.aggressor.map_id), None)
        raid.attacker_entry = ((route.x, route.y) if route
                               else raid.aggressor.attacker_spawn)
        for team, group_name in ((raid.aggressor.key, raid.aggressor.attacker_group),
                                 (raid.defender.key, raid.defender.defender_group)):
            if group_name:
                active = self.activate_spawn_group(group_name, invasion=True)
                actor_ids = active.actor_ids
            else:
                center = (raid.attacker_entry
                          if team == raid.aggressor.key
                          else raid.defender.defender_spawn)
                actor_ids = set()
                for index in range(self.settings.territory_raid_force_size):
                    if team == raid.aggressor.key:
                        offset = ((index % 5) - 2, index // 5)
                    else:
                        ring = 2 + index // 8
                        direction = tuple(DIRS)[index % len(DIRS)]
                        offset = direction[0] * ring, direction[1] * ring
                    x, y = self.free_creature_tile(
                        raid.defender.map_id, center[0] + offset[0],
                        center[1] + offset[1])
                    actor = self.spawn_animal(
                        TERRITORY_RAID_FALLBACK_CREATURE, x, y, invasion=True,
                        map_id=raid.defender.map_id)
                    actor_ids.add(actor.actor_id)
            self.territory_raids.actor_teams.update(
                {actor_id: team for actor_id in actor_ids})
        for connected in list(self.sessions):
            character = connected.character
            team = (self.territory_raids.team_for(character.username)
                    if character else None)
            if not team:
                continue
            spawn = (raid.attacker_entry if team == raid.aggressor.key
                     else raid.defender.defender_spawn)
            await self.change_map(connected, raid.defender.map_id, *spawn)
            await connected.send(p.deep_blue_text(
                f"You have joined {self.territory_raids.territories[team].name}."))
        for connected in list(self.sessions):
            if connected.character and connected.character.map_id == raid.defender.map_id:
                await self.refresh_player_view(connected)
        return raid

    async def finish_territory_raid(self, winner: str):
        raid = self.territory_raids.active
        effects = self.territory_raids.finish(winner)
        self.save_territory_raids()
        if raid:
            ids = set(self.territory_raids.actor_teams)
            for actor_id in ids:
                if animal := self.animals.get(actor_id):
                    animal.alive = False
                    self.remove_animal(animal)
            self.territory_raids.actor_teams.clear()
            for connected in list(self.sessions):
                if connected.character and connected.character.map_id == raid.defender.map_id:
                    await self.refresh_player_view(connected)
        return effects

    async def process_territory_raid(self) -> None:
        now = time.time()
        if now - self._last_raid_tick < 1.0:
            return
        self._last_raid_tick = now
        raid = self.territory_raids.active
        if (not raid or raid.finished) and self._next_raid_at and now >= self._next_raid_at:
            aggressor, defender = self.territory_raids.weighted_pair()
            raid = await self.start_territory_raid(aggressor, defender)
            await self.broadcast(p.deep_blue_text(
                f"{raid.aggressor.name} is raiding {raid.defender.name}! "
                f"Registered supporters may use #raid_enter."))
            self._next_raid_at = now + self.settings.territory_raid_interval_seconds
        if not raid or raid.finished:
            return
        ox, oy = raid.defender.objective
        attackers = defenders = 0
        for connected in self.sessions:
            c = connected.character
            if not c or c.map_id != raid.defender.map_id:
                continue
            if max(abs(c.x - ox), abs(c.y - oy)) > self.territory_raids.capture_radius:
                continue
            team = self.territory_raids.team_for(c.username)
            attackers += int(team == raid.aggressor.key)
            defenders += int(team == raid.defender.key)
        for actor_id, team in self.territory_raids.actor_teams.items():
            animal = self.animals.get(actor_id)
            if not animal or not animal.alive or animal.map_id != raid.defender.map_id:
                continue
            if max(abs(animal.x - ox), abs(animal.y - oy)) <= self.territory_raids.capture_radius:
                attackers += int(team == raid.aggressor.key)
                defenders += int(team == raid.defender.key)
        if winner := self.territory_raids.objective_update(attackers, defenders):
            await self.finish_territory_raid(winner)

    def special_day_has(self, effect: str) -> bool:
        return effect in self.special_day.effects

    async def set_special_day(
            self, day: SpecialDay, announce: bool = True,
            sponsor: str | None = None) -> None:
        self.special_day = day
        self.special_day_xp_bonus = (
            random.randint(101, 140) / 100.0 if day.key == "scholars" else 1.0)
        self.save_world_state()
        await self.broadcast_almanac_state()
        if announce and day is not ORDINARY:
            await self.broadcast(p.deep_blue_text(self.day_message()))
            if sponsor:
                await self.broadcast(p.deep_blue_text(
                    f"This day was sponsored by {sponsor}"))

    async def use_day_stone(self, session: Session, pos: int, name: str) -> None:
        c = session.character
        if not c or c.inventory.get(name, 0) < 1:
            return
        if name == BAD_DAY_REMOVAL:
            if self.special_day.kind != "bad":
                await session.send(p.raw_text(
                    "Bad Day Removal can only be used during a bad special day."))
                return
            target = ORDINARY
        else:
            if self.special_day is not ORDINARY:
                await session.send(p.raw_text(
                    "A special day stone can only be used during an ordinary day."))
                return
            target = SPECIAL_DAYS[DAY_STONES[name]]
        c.inventory[name] -= 1
        if c.inventory[name] <= 0:
            del c.inventory[name]
            session.inventory_slots[pos] = None
            await session.send(p.inventory_remove(pos))
        else:
            item = ITEMS[name]
            await session.send(p.inventory_update(
                item.image_id, c.inventory[name], pos, item.flags))
        self.db.save(c)
        await self.set_special_day(
            target, sponsor=c.name if target is not ORDINARY else None)

    def load_configured_npcs(self, path: str) -> None:
        next_id = 30000
        existing_names = {npc.name.casefold() for npc, _, _, _ in self.npcs.values()}
        for definition in load_npcs(path):
            if definition.map_id not in self.maps:
                raise ValueError(f"NPC {definition.name!r} references unknown map {definition.map_id!r}")
            normalized_name = definition.name.casefold()
            if normalized_name in existing_names:
                continue
            while next_id in self.npcs:
                next_id += 1
            actor = NPCActor(next_id, definition.name, definition.x, definition.y,
                             definition.actor_type, 20, 20, p.NPC,
                             appearance=definition.appearance or {})
            self.npcs[next_id] = (actor, definition.map_id, definition.price,
                                  definition.sold)
            self.npc_roles[next_id] = definition.role
            self.npc_dialogues[next_id] = definition.dialogue
            existing_names.add(normalized_name)
            next_id += 1

    @property
    def item_rarity(self) -> dict[str, int]:
        """How scarce each item is, built once from this world's own tables.

        Rarity is not authored on the item; it follows from where the item can
        actually be obtained, so it stays correct when a drop table changes.
        """
        if self._item_rarity is None:
            self._item_rarity = build_rarity_index(
                ITEMS, drop_tables=self.drop_tables,
                harvest_resources=self.harvest_resources,
                rare_harvest=self.rare_harvest, shops=self.shops,
                recipes=self.recipes)
        return self._item_rarity

    @property
    def storage_categories(self) -> list[tuple[int, str]]:
        present = {item.category for item in ITEMS.values()}
        # The stock client treats any storage list containing a category named
        # "Quest" as the view-only #sto window. NPC storage must omit that
        # sentinel so deposit and withdrawal controls remain enabled.
        names = [name for name in EL_STORAGE_CATEGORIES
                 if name in present and name != "Quest"]
        return list(enumerate(names))

    def storage_positions(self, c: Character) -> list[str]:
        return sorted((name for name, quantity in c.storage.items()
                       if quantity > 0 and name in ITEMS), key=lambda name: (ITEMS[name].category.casefold(), name.casefold()))

    def storage_npc_near(self, c: Character) -> bool:
        npc_near = any(
            self.npc_roles.get(actor_id) == "storage" and map_id == c.map_id
            and max(abs(c.x - npc.x), abs(c.y - npc.y)) <= 4
            for actor_id, (npc, map_id, _, _) in self.npcs.items())
        object_near = any(
            entry.role == "storage" and entry.map_id == c.map_id
            and max(abs(c.x - entry.x), abs(c.y - entry.y)) <= 4
            for entry in self.interactives.values())
        return npc_near or object_near

    def invasion_master(self, c: Character) -> bool:
        configured = {name.strip().casefold() for name in
                      self.settings.invasion_masters.split(",") if name.strip()}
        return bool(configured) and c.username.casefold() in configured

    def god_storage_positions(self) -> list[str]:
        # Only items reachable through a listed category: anything else would
        # occupy a position the window can never show.
        visible = {name for _, name in self.storage_categories}
        return sorted(
            (name for name, item in ITEMS.items() if item.category in visible),
            key=lambda name: (ITEMS[name].category.casefold(), name.casefold()))

    async def open_storage(self, session: Session) -> None:
        c = session.character
        if not c or not self.storage_npc_near(c):
            return
        session.storage_open = True
        session.god_storage_open = False
        categories = self.storage_categories
        await session.send(p.storage_list(categories))
        await self.show_storage_category(session, categories[0][0] if categories else 0)

    async def open_god_storage(self, session: Session) -> None:
        """#god_storage: every item in the game, openable from anywhere.

        Invasion masters only. Withdrawals conjure fresh items; deposits go
        to the character's own storage, so no item can be destroyed by it.
        """
        c = session.character
        if not c or not self.invasion_master(c):
            return
        session.storage_open = True
        session.god_storage_open = True
        categories = self.storage_categories
        await session.send(p.storage_list(categories))
        await self.show_storage_category(session, categories[0][0] if categories else 0)
        await session.send(p.storage_text(
            f"God storage: withdraw any item ({GOD_STORAGE_QUANTITY:,} each); "
            "deposits go to your own storage."))

    async def show_storage_category(self, session: Session, category_id: int) -> None:
        c = session.character
        categories = dict(self.storage_categories)
        if not c or not session.storage_open or category_id not in categories:
            return
        session.storage_category = category_id
        entries = []
        described = []
        positions = (self.god_storage_positions() if session.god_storage_open
                     else self.storage_positions(c))
        rarity = self.item_rarity
        for position, name in enumerate(positions):
            item = ITEMS[name]
            if item.category != categories[category_id]:
                continue
            quantity = (GOD_STORAGE_QUANTITY if session.god_storage_open
                        else c.storage[name])
            entries.append((item.image_id, quantity, position))
            described.append((position, item.image_id, quantity, item.name,
                              item_subtype(item), item_strength(item),
                              rarity.get(name, 0)))
        await session.send(p.storage_items(category_id, entries))
        # The organizer packet rides alongside the stock one, keyed by the
        # same positions, and only for a client that asked for it. Storage
        # keeps working exactly as before for one that did not.
        if "storage_window_v1" in session.client_capabilities:
            await session.send(p.storage_state(category_id, described))

    async def deposit_storage(self, session: Session, inventory_pos: int, quantity: int) -> None:
        c = session.character
        if not c or not session.storage_open or not (
                session.god_storage_open or self.storage_npc_near(c)):
            return
        if not session.inventory_slots:
            session.inventory_slots = self.sync_inventory_slots(c)
        if inventory_pos >= len(session.inventory_slots) or not session.inventory_slots[inventory_pos]:
            return
        name = session.inventory_slots[inventory_pos]
        amount = min(max(0, quantity), c.inventory.get(name, 0))
        instance_ids: list[int] = []
        if tracks_instances(name):
            amount = min(amount, 1)
            instance_id = c.inventory_instance_slots[inventory_pos]
            instance_ids = [instance_id] if instance_id else []
            if not instance_ids:
                return
        if not amount:
            return
        for instance_id in instance_ids:
            self.db.item_instances.transfer(
                instance_id, 1, "storage", c.username,
                actor=c.username, source="storage_deposit")
        c.inventory[name] -= amount
        if not c.inventory[name]:
            del c.inventory[name]
        c.storage[name] = c.storage.get(name, 0) + amount
        await self.walkthrough_event(session, "storage", name, c.storage[name])
        session.inventory_slots = self.sync_inventory_slots(c)
        if modern := getattr(self, "modern", None):
            modern.record_economy(
                "storage_deposit", c.username, item_name=name,
                quantity=amount, instance_id=(instance_ids[0] if instance_ids else None),
                gold_flow="none", item_flow="transfer")
        self.db.save(c)
        await self.record_activity(session, ACTIVITY_STORAGE)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        if session.god_storage_open:
            # The god view keeps advertising 99999 of everything, so tell the
            # depositor where their items actually went.
            await session.send(p.storage_text(
                f"Deposited {amount} {name} into your own storage."))
        await self.show_storage_category(session, session.storage_category)

    async def withdraw_storage(self, session: Session, position: int, quantity: int) -> None:
        c = session.character
        if not c or not session.storage_open:
            return
        if session.god_storage_open:
            await self.withdraw_god_storage(session, position, quantity)
            return
        if not self.storage_npc_near(c):
            return
        positions = self.storage_positions(c)
        if position >= len(positions):
            return
        await self.withdraw_named(session, positions[position], quantity)

    async def withdraw_named(self, session: Session, name: str,
                             quantity: int) -> None:
        """Move some of `name` out of storage and into the pack.

        Split out of `withdraw_storage` because the storage window knows an
        item by the position it happens to occupy in an open storage list and
        the manufacturing window cannot - it knows a tool by name, and never
        opens storage at all. Everything that decides whether the move is
        possible is the same either way: carry weight, free slots, and the
        instance identity of anything that has one.
        """
        c = session.character
        if not c:
            return
        amount = min(max(0, quantity), c.storage.get(name, 0))
        instance_ids = (list(c.storage_instances.get(name, []))[:amount]
                        if tracks_instances(name) else [])
        if tracks_instances(name):
            amount = min(amount, len(instance_ids))
        if not amount:
            return
        # Move as much as possible without exceeding inventory slots or EMU.
        emu = ITEMS[name].emu
        capacity_amount = (max(0, (carry_capacity(c) - self.carried_load(c)) // emu)
                           if emu > 0 else amount)
        if self.inventory_slot_usage(c.inventory) >= 36:
            capacity_amount = 0
        amount = min(amount, capacity_amount)
        if not amount:
            await session.send(p.storage_text("You cannot carry any more." , 1))
            return
        c.storage[name] -= amount
        if not c.storage[name]:
            del c.storage[name]
        c.inventory[name] = c.inventory.get(name, 0) + amount
        for instance_id in instance_ids:
            self.db.item_instances.transfer(
                instance_id, 1, "inventory", c.username,
                actor=c.username, source="storage_withdrawal")
        session.inventory_slots = self.sync_inventory_slots(c)
        await lantern.event(self, session, "withdraw", name, amount)
        await bell.event(self, session, "withdraw", name, amount)
        roads.emit(self,session,"withdraw",name,amount)
        await sky.event(self, session, "withdraw", name, amount)
        if modern := getattr(self, "modern", None):
            modern.record_economy(
                "storage_withdrawal", c.username, item_name=name,
                quantity=amount, instance_id=(instance_ids[0] if instance_ids else None),
                gold_flow="none", item_flow="transfer")
        self.db.save(c)
        await self.record_activity(session, ACTIVITY_STORAGE)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        if session.storage_open:
            await self.show_storage_category(session, session.storage_category)

    async def withdraw_god_storage(self, session: Session, position: int, quantity: int) -> None:
        c = session.character
        # Re-checked on every withdrawal, not just at open time, so revoking
        # invasion_masters in the settings takes effect mid-session.
        if not self.invasion_master(c):
            return
        positions = self.god_storage_positions()
        if position >= len(positions):
            return
        name = positions[position]
        amount = min(max(0, quantity), GOD_STORAGE_QUANTITY)
        if tracks_instances(name):
            amount = min(amount, max(0, 36 - self.inventory_slot_usage(c.inventory)))
        amount = min(amount, max(0, (carry_capacity(c) - self.carried_load(c))
                                 // max(1, ITEMS[name].emu)))
        before = dict(c.inventory)
        if not amount or not self.add_inventory(
                c, name, amount, source="god_storage", creator=c.username):
            await session.send(p.storage_text("You cannot carry any more.", 1))
            return
        session.inventory_slots = c.inventory_slots
        self.record_inventory_economy_delta(c, before, "god_storage_withdrawal")
        self.db.save(c)
        await self.record_activity(session, ACTIVITY_STORAGE)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await self.show_storage_category(session, session.storage_category)

    async def inspect_storage_item(self, session: Session, position: int) -> None:
        c = session.character
        if not c or not session.storage_open:
            return
        positions = (self.god_storage_positions() if session.god_storage_open
                     else self.storage_positions(c))
        if position < len(positions):
            item = ITEMS[positions[position]]
            await session.send(p.storage_text(item.description or item.name))

    @staticmethod
    def novac_target_token(animal: Animal) -> str:
        """Stable identity for a normal creature spawn across wandering and respawns."""
        return "|".join((
            animal.map_id, animal.spawn_group, str(animal.spawn_x),
            str(animal.spawn_y), animal.creature_type,
        ))

    def assign_novac_target(self, c: Character, quest) -> Animal | None:
        """Bind the current objective to one normal actor of the requested type."""
        objective = novac_objective(c, quest)
        if not objective or novac_pending(c, quest):
            return None
        existing = novac_target(c, quest)
        if existing:
            assigned = next((
                animal for animal in self.animals.values()
                if self.novac_target_token(animal) == existing
            ), None)
            if assigned is not None:
                return assigned

        candidates = [
            animal for animal in self.animals.values()
            if animal.creature_type in objective.creature_types
            and not animal.invasion and not animal.instance_name
            and not animal.summoned
        ]
        if not candidates:
            set_novac_target(c, quest, "")
            return None

        location = objective.location.casefold()
        def rank(animal: Animal) -> tuple[int, int, int]:
            map_name = self.maps[animal.map_id].name.casefold()
            location_match = bool(
                location and (location == map_name or location in map_name
                              or map_name in location))
            return (not location_match, not animal.alive, animal.actor_id)

        assigned = min(candidates, key=rank)
        set_novac_target(c, quest, self.novac_target_token(assigned))
        return assigned

    def ensure_novac_targets(self, c: Character) -> None:
        for quest in NOVAC_QUESTS.values():
            if novac_objective(c, quest) and not novac_pending(c, quest):
                self.assign_novac_target(c, quest)

    def spawn_animal(self, species: str, x: int, y: int, actor_id: int | None = None,
                     *, invasion: bool = False, invasion_boss: bool = False,
                     instance_name: str = "", spawn_group: str = "",
                     map_id: str = START_MAP, roll_equipment: bool = True,
                     owner_id: int | None = None, summoned: bool = False,
                     tame: bool = False, leash: int = 0) -> Animal:
        # Occasionally the creature that appears is a named version of the one
        # asked for. Rolled before anything is derived, so the whole spawn -
        # stats, size, drop table, the tile it needs - is the variant's. A tame
        # animal is always the one the camp keeps.
        if not tame:
            species = self.roll_spawn_species(species, summoned=summoned)
        spec = self.creatures[species]
        x, y = self.free_creature_tile(map_id, x, y, spec.footprint)
        # A full map can be retried repeatedly without consuming actor IDs.
        aid = actor_id or self.allocate_id()
        # Summons must not use the NPC kind: the stock client suppresses
        # health for every NPC actor.  A c_blue1 name prefix preserves their
        # light-blue name and minimap dot while the creature kind exposes HP.
        if summoned:
            display_name = chr(127 + p.EL_COLOR_BLUE1) + spec.name
        elif invasion:
            # EL red3: the saturated red used for invasion creature banners.
            display_name = chr(127 + p.EL_COLOR_RED3) + spec.name
        else:
            display_name = spec.name
        # Livestock goes out as an NPC: the client offers to talk, not to fight.
        actor_kind = p.NPC if tame else p.PKABLE_COMPUTER_CONTROLLED
        animal = Animal(aid, display_name, x, y, spec.actor_type, spec.material_points,
            spec.material_points, actor_kind, species=species,
            attack=spec.attack, defense=spec.defense, damage=spec.effective_damage_max,
            xp=max(1, (spec.attack + spec.defense) // 2), spawn_x=x, spawn_y=y,
            creature_type=species, invasion=invasion, invasion_boss=invasion_boss,
            instance_name=instance_name, spawn_group=spawn_group, map_id=map_id,
            ether=spec.ethereal_points, max_ether=spec.ethereal_points,
            owner_id=owner_id, summoned=summoned,
            footprint_width=spec.footprint_width,
            footprint_depth=spec.footprint_depth,
            scale=spec.scale)
        # The spawn row's leash: livestock keeps to its pen by it, and a wild
        # row's `leash:N` holds a huntable creature near its ground instead of
        # the server-wide normal_wander_radius. 0 is no leash of its own.
        animal.wander_radius = max(0, int(leash))
        if tame:
            animal.tame = True
            roll_equipment = False
        now = time.monotonic()
        if invasion or summoned:
            # Distribute first steps across the animation cycle so groups do
            # not move or pause in lockstep.
            interval_ms = (
                self.settings.summon_move_interval_ms
                if summoned else self.settings.invasion_move_interval_ms)
            animal.next_move_at = (
                now + random.uniform(0.0, interval_ms / 1000.0))
        else:
            animal.next_move_at = now + random.uniform(0.5, 3.5)
        if summoned:
            animal.next_summon_decay_at = (
                now + SUMMON_DECAY_INTERVAL_SECONDS)
        self.animals[aid] = animal
        self.animals_by_map[map_id].add(aid)
        self.index_creature(animal)
        if roll_equipment:
            self.equip_creature(animal)
        return animal

    async def spawn_summon(self, session: Session, species: str) -> Animal | None:
        c = session.character
        if not c or species not in self.creatures:
            await session.send(p.raw_text("That summoned creature is not available on this server yet."))
            return None
        animal = self.spawn_animal(
            species, c.x + 1, c.y, map_id=c.map_id,
            owner_id=c.actor_id, summoned=True, roll_equipment=False)
        # A summon fights under its summoner's colours: it wears the guild tag
        # on its nameplate, and it answers to the summoner's party when it
        # picks a target. Both are read off the owner once, here, rather than
        # chased through the session every tick.
        animal.owner_username = c.username
        animal.guild_tag = c.guild_tag
        spec = self.creatures[species]
        animal.attack, animal.defense = scaled_combat_stats(
            spec.attack, spec.defense, c.skills["summoning"],
            summoner_perk=has_advanced_summoner_perk(c))
        # Summoner sharpens what you call; Lifebinder makes it last. Applied
        # once at the summoning rather than read every round, because a
        # creature that changed strength when its summoner bought a perk
        # mid-fight would be a different creature from the one on the field.
        combat, health = summoned_creature_bonuses(c)
        if combat:
            animal.attack = int(round(animal.attack * (1.0 + combat)))
            animal.defense = int(round(animal.defense * (1.0 + combat)))
        if health:
            animal.max_health = max(1, int(round(animal.max_health * (1.0 + health))))
            animal.unequipped_max_health = animal.max_health
            animal.health = animal.max_health
        for visible_session in self.sessions:
            if visible_session.character and visible_session.character.map_id == c.map_id:
                await self.sync_visible_animals(visible_session)
        await self.walkthrough_event(session, "summon", species)
        return animal

    def variants_of(self, species: str) -> list[CreatureDefinition]:
        """The named variants that can appear in place of this creature.

        Sorted by type so a seeded roll is reproducible, and so the order two
        variants of the same creature are offered in does not depend on the
        order their blocks happen to sit in the file.
        """
        return sorted(
            (definition for definition in self.creatures.values()
             if definition.is_variant and definition.variant_of == species),
            key=lambda definition: definition.type)

    def roll_spawn_species(self, species: str, *, summoned: bool = False) -> str:
        """Which creature actually appears where `species` was asked for.

        Ordinarily the creature asked for. Occasionally a named variant of it -
        the same animal, tougher, worth more, and worth telling somebody about.
        The point of the register entry this comes from is variety across the
        whole level range rather than only at the top, so this is deliberately
        not gated on level: a rabbit may have a famous rabbit.

        Not for summons. A player who pays for a creature gets the creature
        they paid for, not a lottery ticket.
        """
        if summoned:
            return species
        for variant in self.variants_of(species):
            if random.randint(1, variant.variant_chance) == 1:
                return variant.type
        return species

    def apply_creature_type(self, animal: Animal, species: str) -> None:
        """Make an existing creature be this species, stats and all.

        Everything here is derived from the definition rather than stored per
        creature, which is what lets a respawn roll afresh: an ordinary bear
        that dies can come back as the named one, and the named one can come
        back ordinary. Without that the variant population would be whatever
        the world happened to roll at startup and would never change again.
        """
        spec = self.creatures[species]
        animal.creature_type = species
        animal.species = species
        animal.actor_type = spec.actor_type
        animal.attack = spec.attack
        animal.defense = spec.defense
        animal.damage = spec.effective_damage_max
        animal.xp = max(1, (spec.attack + spec.defense) // 2)
        animal.max_health = spec.material_points
        animal.ether = animal.max_ether = spec.ethereal_points
        animal.footprint_width = spec.footprint_width
        animal.footprint_depth = spec.footprint_depth
        animal.scale = spec.scale
        # equip_creature only records this the first time, and it is the base
        # the loadout's health contribution is added to. A re-rolled creature
        # has a different base, so the old one has to go.
        animal.unequipped_max_health = 0
        animal.equipment = {}
        if animal.summoned:
            animal.name = chr(127 + p.EL_COLOR_BLUE1) + spec.name
        elif animal.invasion:
            animal.name = chr(127 + p.EL_COLOR_RED3) + spec.name
        else:
            animal.name = spec.name

    @staticmethod
    def fixed_loadout(names: Sequence[str]) -> dict[str, str]:
        """Wear an authored list of gear, including more of it than fits.

        Ordinary creature gear is rolled a slot at a time and never offers a
        piece the body has no room for. An authored loadout is a statement
        rather than a roll, so a boss written with two weapons gets both: the
        first takes the slot its kind wears, and anything with nowhere left to
        go takes a slot named after nothing on the body.

        A synthetic slot is not a loophole in equipment validation, it is
        outside it. Everything that reads gear in combat - `equipment_stats`,
        and the on-hit effects `roll_equipment_effects` rolls - walks the
        values of this dictionary and never asks what the keys are, so a
        second weapon fights. The rule that says a pair of hands holds one
        weapon lives in `equipment_conflict`, on the path where a player
        equips something, and nothing here goes near it.
        """
        equipment: dict[str, str] = {}
        worn: set[str] = set()
        for name in names:
            item = ITEMS.get(name)
            if item is None:
                continue
            if slot_compatible(item.equip_type, worn):
                slot = item.equip_type
                worn.add(slot)
            else:
                slot = f"{EXTRA_WEAPON_SLOT_PREFIX}{len(equipment) + 1}"
            equipment[slot] = name
        return equipment

    def equip_creature(self, animal: Animal,
                       loadout: Sequence[str] = ()) -> None:
        """Roll a fresh loadout and apply its maximum-health contribution.

        `loadout` is the exception: gear an author wrote down, worn as
        written instead of rolled. Nothing but a boss has one.
        """
        definition = self.creatures[animal.creature_type]
        if not animal.unequipped_max_health:
            animal.unequipped_max_health = animal.max_health
        animal.equipment = self.fixed_loadout(loadout) if loadout else (
            roll_creature_equipment(
                ITEMS.values(), definition,
                base_chance=self.settings.creature_equipment_base_chance,
                max_chance=self.settings.creature_equipment_max_chance,
                max_items=self.settings.creature_equipment_max_items))
        gear = equipment_stats(animal.equipment)
        animal.max_health = max(
            1, animal.unequipped_max_health + int(gear["max_health"]))
        animal.health = animal.max_health

    @staticmethod
    def creature_gear_damage(animal: Animal,
                             gear: dict[str, int | tuple[int, int]]) -> int:
        weapon = gear["damage"]
        assert isinstance(weapon, tuple)
        physical = random.randint(*weapon) if weapon != (0, 0) else 0
        elemental = sum(int(gear[key]) for key in
                        ("cold_damage", "heat_damage", "radiation_damage",
                         "magic_damage"))
        return physical + elemental

    async def broadcast_visual_changes(
            self, owner: Character | Animal,
            before: dict[int, int]) -> None:
        """Tell the map what changed about what `owner` is wearing.

        Taken as the difference between two readings of the whole set rather
        than from the item that moved, because one item does not decide one
        part: two one-handed weapons are each part 0 alone, and it is the pair
        that puts one of them in the left hand.  Reading the item would equip
        a second weapon over the first, and taking either one off would empty
        a hand that still held something.

        Parts that emptied are taken off first, so a hand is never briefly
        holding two things on somebody else's screen.
        """
        after = equipped_visuals(owner.equipment)
        for part in sorted(set(before) - set(after)):
            await self.broadcast_map(
                owner.map_id, p.actor_unwear(owner.actor_id, part))
        for part in sorted(after):
            if before.get(part) != after[part]:
                await self.broadcast_map(
                    owner.map_id,
                    p.actor_wear(owner.actor_id, part, after[part]))

    async def remove_equipped_item(
            self, owner: Character | Animal, position: str,
            owner_session: Session | None = None) -> str:
        """Remove one equipped item and synchronize actor/player state."""
        before_visuals = equipped_visuals(owner.equipment)
        name = owner.equipment.pop(position)
        if isinstance(owner, Character):
            instance_id = owner.equipment_instances.pop(str(position), None)
            if instance_id:
                self.db.item_instances.retire(
                    instance_id, actor=owner.username, reason="destroyed")
                if modern := getattr(self, "modern", None):
                    modern.record_economy(
                        "equipment_destroyed", owner.username,
                        item_name=name, quantity=1, instance_id=instance_id,
                        item_flow="sink",
                        metadata={"equipment_slot": str(position)})
        await self.broadcast_visual_changes(owner, before_visuals)
        if isinstance(owner, Animal):
            gear = equipment_stats(owner.equipment)
            owner.max_health = max(
                1, owner.unequipped_max_health + int(gear["max_health"]))
            owner.health = min(owner.health, owner.max_health)
        elif isinstance(owner, Character):
            refresh_derived_points(owner)
            if owner_session:
                owner_session.inventory_slots = self.sync_inventory_slots(owner)
                await owner_session.send(p.inventory_packet(
                    owner.inventory, ITEMS, owner.equipment,
                    owner_session.inventory_slots))
                await self.send_stats(owner_session, force=True)
        return name

    async def degrade_equipped_item(
            self, owner: Character | Animal, position: str,
            owner_session: Session | None = None, *,
            force: bool = False) -> tuple[str, str]:
        """Apply durability wear and advance a configured stage at zero."""
        old_name = owner.equipment[position]
        old_item = ITEMS.get(old_name)
        if isinstance(owner, Character) and tracks_instances(old_name):
            instance_id = owner.equipment_instances.get(str(position))
            instance = self.db.item_instances.get(instance_id) if instance_id else None
            if instance and not force:
                maximum = instance.max_durability or 100
                current = instance.durability if instance.durability is not None else maximum
                remaining = max(0, current - 1)
                self.db.item_instances.set_durability(
                    instance.instance_id, remaining, actor=owner.username,
                    reason="combat_wear")
                if remaining:
                    return old_name, old_name

        replacement = old_item.degrades_to if old_item else ""
        instance_id = (owner.equipment_instances.get(str(position))
                       if isinstance(owner, Character) else None)
        if not replacement or replacement not in ITEMS:
            await self.remove_equipped_item(owner, position, owner_session)
            return old_name, ""
        before_visuals = equipped_visuals(owner.equipment)
        owner.equipment[position] = replacement
        if instance_id:
            maximum = 100
            self.db.db.execute(
                """UPDATE item_instances SET definition_name=?,durability=?,
                   max_durability=?,source='degraded',updated_at=?
                   WHERE instance_id=?""",
                (replacement, maximum, maximum, time.time(), instance_id))
            self.db.item_instances._event(
                instance_id, "degraded", "equipment", owner.username,
                "equipment", owner.username, 1, owner.username,
                {"from": old_name, "to": replacement,
                 "equipment_slot": str(position)})
            if modern := getattr(self, "modern", None):
                modern.record_economy(
                    "equipment_degraded", owner.username,
                    item_name=old_name, quantity=1, instance_id=instance_id,
                    item_flow="sink",
                    metadata={"replacement": replacement,
                              "equipment_slot": str(position)})
                modern.record_economy(
                    "equipment_degraded_output", owner.username,
                    item_name=replacement, quantity=1,
                    instance_id=instance_id, item_flow="source",
                    metadata={"previous": old_name,
                              "equipment_slot": str(position)})
        await self.broadcast_visual_changes(owner, before_visuals)
        if isinstance(owner, Animal):
            gear = equipment_stats(owner.equipment)
            owner.max_health = max(
                1, owner.unequipped_max_health + int(gear["max_health"]))
            owner.health = min(owner.health, owner.max_health)
        elif isinstance(owner, Character):
            refresh_derived_points(owner)
            if owner_session:
                owner_session.inventory_slots = self.sync_inventory_slots(owner)
                await owner_session.send(p.inventory_packet(
                    owner.inventory, ITEMS, owner.equipment,
                    owner_session.inventory_slots))
                await self.send_stats(owner_session, force=True)
        return old_name, replacement

    def combat_wear_chance(self, owner: Character | Animal, item) -> float:
        """Apply owner-specific modifiers to an item's ordinary wear rate."""
        chance = equipment_wear_chance(item)
        if isinstance(owner, Character):
            chance *= combat_wear_scale(owner)
        return chance

    async def apply_normal_combat_wear(
            self, owner: Character | Animal, weapon_use: bool,
            owner_session: Session | None = None,
            observer_session: Session | None = None) -> None:
        """Roll ordinary wear for weapons used or equipment struck in combat."""
        eligible = (WEAPON_WEAR_EQUIP_TYPES if weapon_use
                    else DEFENSIVE_WEAR_EQUIP_TYPES)
        for position, name in list(owner.equipment.items()):
            item = ITEMS.get(name)
            if not item or item.equip_type not in eligible:
                continue
            if random.random() >= self.combat_wear_chance(owner, item):
                continue
            old_name, replacement = await self.degrade_equipped_item(
                owner, position, owner_session)
            if replacement == old_name:
                continue
            if owner_session and not replacement:
                # A degrade is wear; only a total loss is a breakage.
                await self.record_activity(
                    owner_session, ACTIVITY_BREAKAGES, detail=old_name)
            recipient = owner_session or observer_session
            if recipient:
                owner_label = "Your" if owner_session else f"{owner.name}'s"
                outcome = (f"degraded into {replacement}" if replacement
                           else "broke")
                await recipient.send(p.colored_text(
                    f"{owner_label} {old_name} {outcome}.",
                    p.EL_COLOR_ORANGE1))

    def equipped_instance_effects(self, owner: Character | Animal):
        """Resolve effects from the exact objects worn in each equipment slot."""
        store = getattr(getattr(self, "db", None), "item_instances", None)
        if store is None:
            return ()
        effects = []
        for slot, instance_id in getattr(owner, "equipment_instances", {}).items():
            item = ITEMS.get(owner.equipment.get(slot))
            instance = store.get(instance_id)
            if (not item or not instance or instance.state != "active"
                    or instance.owner_type != "equipment"
                    or instance.owner_key.casefold() != owner.username.casefold()
                    or instance.slot_key != str(slot)
                    or instance.definition_name != item.name):
                continue
            effects.extend((item, effect)
                           for _, effect in instance_effects(instance.modifiers))
        return tuple(effects)

    async def apply_item_effects(
            self, owner: Character | Animal, target: Character | Animal,
            owner_session: Session | None, trigger: str,
            target_session: Session | None = None) -> int:
        """Apply one trigger's configured effects and return bonus damage."""
        bonus_damage = 0
        now = time.monotonic()
        triggered = list(roll_equipment_effects(owner.equipment, trigger))
        triggered.extend((item, effect)
                         for item, effect in self.equipped_instance_effects(owner)
                         if effect.trigger == trigger and random.random() < effect.chance)
        for item, effect in triggered:
            amount = max(0, int(effect.parameter("amount", 0)))
            action_cost = max(0, int(effect.parameter("action_cost", 0)))
            if action_cost:
                default_points = (
                    self.rationality(owner) * 20
                    if isinstance(owner, Character) else 20)
                points = owner.combat_bonuses.get(
                    "action_points", default_points)
                if points < action_cost:
                    continue
                owner.combat_bonuses["action_points"] = points - action_cost
            applied = False
            if effect.kind == "extra_damage":
                bonus_damage += amount
                applied = True
            elif effect.kind == "heal":
                healed = min(amount, max(0, owner.max_health - owner.health))
                if healed:
                    owner.health += healed
                    await self.broadcast_map(
                        owner.map_id, p.actor_heal(owner.actor_id, healed))
                    applied = True
            elif effect.kind in {"mana_drain", "mana_burn", "mana_nullify"}:
                removed = min(amount, target.ether)
                target.ether -= removed
                if effect.kind == "mana_drain":
                    owner.ether = min(owner.max_ether, owner.ether + removed)
                elif effect.kind == "mana_burn":
                    bonus_damage += removed
                if isinstance(target, Character) and target_session:
                    await self.send_stats(target_session, force=True)
                applied = removed > 0
            elif effect.kind == "paralyze":
                seconds = max(0.0, float(effect.parameter("seconds", 0)))
                if isinstance(target, Animal):
                    target.frozen_until = max(target.frozen_until, now + seconds)
                elif target_session:
                    target_session.frozen_until = max(
                        target_session.frozen_until, now + seconds)
                applied = seconds > 0
            elif effect.kind == "cooldown_max" and target_session:
                target_session.food_cooldown_until = max(
                    target_session.food_cooldown_until,
                    now + max(1, target_session.food_cooldown_max))
                for potion_name, potion in POTIONS.items():
                    target_session.potion_cooldowns[potion_name] = max(
                        target_session.potion_cooldowns.get(potion_name, 0.0),
                        now + potion.cooldown)
                applied = True
            elif effect.kind == "cooldown_clear" and owner_session:
                owner_session.food_cooldown_until = 0.0
                owner_session.potion_cooldowns.clear()
                applied = True
            elif effect.kind in {"degrade_item", "destroy_item"}:
                protected = (
                    isinstance(target, Character)
                    and any(name.casefold() in {
                        "cape of the unbreakable", "mage robe skirt"}
                            for name in target.equipment.values()))
                if target.equipment and not protected:
                    position = random.choice(tuple(target.equipment))
                    await self.degrade_equipped_item(
                        target, position, target_session, force=True)
                    applied = True
            elif effect.kind == "break_self":
                positions = [
                    position for position, name in owner.equipment.items()
                    if name == item.name]
                if positions:
                    await self.remove_equipped_item(
                        owner, positions[0], owner_session)
                    applied = True
            elif effect.kind == "life_drain":
                drained = min(amount, max(0, target.health - 1))
                if drained:
                    target.health -= drained
                    owner.health = min(owner.max_health, owner.health + drained)
                    await self.broadcast_map(
                        target.map_id, p.actor_damage(target.actor_id, drained))
                    await self.broadcast_map(
                        owner.map_id, p.actor_heal(owner.actor_id, drained))
                    applied = True
            elif effect.kind == "defense_boost":
                cap = max(0, int(effect.parameter("cap", amount)))
                current = owner.temporary_combat.get("evasion", 0)
                increased = min(amount, max(0, cap - current))
                if increased:
                    owner.temporary_combat["evasion"] = current + increased
                    applied = True
            if applied:
                message = effect.message or (
                    f"{item.name} activates {effect.kind.replace('_', ' ')}.")
                await self.broadcast_local_item_effect(
                    owner, message, owner_session, target_session)
        return bonus_damage

    async def broadcast_local_item_effect(
            self, owner: Character | Animal, message: str,
            owner_session: Session | None = None,
            fallback_session: Session | None = None) -> None:
        """Announce an equipment proc in bright orange to local observers.

        Eternal Lands uses second person for the item owner and possessive
        third person for everyone else, e.g. "Your ..." versus "Bob's ...".
        """
        observer_message = message.replace(
            "Your ", f"{owner.name}'s ", 1)
        recipients = list(getattr(self, "sessions", ()))
        if not recipients:
            fallback = owner_session or fallback_session
            if fallback is not None:
                text = message if fallback is owner_session else observer_message
                await fallback.send(
                    p.colored_text(text, p.EL_COLOR_ORANGE1, p.CHAT_LOCAL))
            return
        for recipient in recipients:
            character = recipient.character
            if (not character or character.map_id != owner.map_id
                    or max(abs(character.x-owner.x),
                           abs(character.y-owner.y)) > 18):
                continue
            text = message if recipient is owner_session else observer_message
            await recipient.send(
                p.colored_text(text, p.EL_COLOR_ORANGE1, p.CHAT_LOCAL))

    async def process_boss_response(self, animal: Animal) -> None:
        """Let a boss spend its healing and its reinforcements as it loses.

        Run wherever a blow lands on a creature, so the answer arrives with
        the hit that provoked it rather than on the next tick of some other
        loop. Every creature in the world reaches the first line and returns:
        what makes this one a boss is the record on it, which is loaded from
        `bosses.def` rather than decided here by species.

        Neither resource comes back. The healing is a budget of charges and
        the reinforcements a pool, so a fight that goes long is a fight the
        boss is running out of answers for - which is the whole shape of it.
        """
        fight = animal.boss_fight
        if fight is None or not animal.alive or animal.health <= 0:
            return
        if fight.heal_charges > 0 and animal.health < animal.max_health:
            healed = min(fight.heal, animal.max_health - animal.health)
            if healed > 0:
                animal.health += healed
                fight.heal_charges -= 1
                await self.broadcast_map(
                    animal.map_id, p.actor_heal(animal.actor_id, healed))
        if not fight.summon or fight.summons_left <= 0:
            return
        # After the heal, so a boss held just above a threshold by its own
        # potions does not call reinforcements it no longer needs.
        share = animal.health / max(1, animal.max_health)
        spawned = False
        active = (self.active_spawn_groups.get(animal.spawn_group.casefold())
                  if animal.spawn_group else None)
        for threshold, quantity in fight.thresholds:
            if share > threshold or threshold in fight.fired:
                continue
            fight.fired.add(threshold)
            quantity = min(quantity, fight.summons_left)
            fight.summons_left -= quantity
            for _ in range(quantity):
                add = self.spawn_animal(
                    fight.summon, animal.x, animal.y,
                    invasion=animal.invasion,
                    instance_name=animal.instance_name, spawn_group=animal.spawn_group,
                    map_id=animal.map_id, roll_equipment=False)
                spawned = True
                # Into the boss's own group, which is what makes them part of
                # the invasion rather than loose actors: `clear_invasion` and
                # the dispersal that follows a dead boss both work through
                # this set, and anything outside it is left standing on the
                # map with nothing that will ever remove it.
                if active is not None:
                    active.actor_ids.add(add.actor_id)
        if spawned:
            for session in list(self.sessions):
                if (session.character
                        and session.character.map_id == animal.map_id):
                    await self.sync_visible_animals(session)

        await bell.boss_response(self, animal)

    def map_id_for_spawn(self, value: str) -> str:
        normalized = value.strip().removeprefix("./").removeprefix("maps/")
        normalized = normalized.removesuffix(".def").removesuffix(".elm")
        if normalized in self.maps:
            return normalized
        for map_id, definition in self.maps.items():
            file_name = definition.file.removeprefix("./").removeprefix("maps/")
            file_name = file_name.removesuffix(".elm").removesuffix(".def")
            if file_name.casefold() == normalized.casefold():
                return map_id
        raise ValueError(f"Unknown spawn-group map {value!r}")

    def creature_for_spawn(self, value: str) -> str:
        aliases = {
            "raccoon": "racoon", "snake_1": "snake1", "snake_2": "snake2",
            "snake_3": "snake3", "bear_1": "bear1", "bear_2": "bear2",
            "bear_3": "bear_3", "bear_4": "bear_4", "female_goblin": "female_goblin",
            "armed_female_orc_1": "armed_female_orc",
            "armed_male_orc_1": "armed_male_orc",
        }
        key = value.strip().casefold()
        # The name as written wins. These aliases spell the Eternal Lands
        # roster's own oddities - "raccoon" for its "racoon", "snake_1" for
        # "snake1" - so applying one before looking gives a profile that
        # spells the creature correctly no way to name it: the alias sends
        # "raccoon" to a "racoon" that roster does not have.
        if key not in self.creatures:
            key = aliases.get(key, key)
        if key not in self.creatures:
            raise ValueError(f"Unknown spawn-group creature {value!r}")
        return key

    def activate_spawn_group(self, group: SpawnGroup | str, *, invasion: bool | None = None,
                             instance_name: str = "",
                             now: float | None = None, map_id: str | None = None,
                             key: str | None = None,
                             level_target: int = 0) -> ActiveSpawnGroup:
        if isinstance(group, str):
            lookup = group.casefold()
            definition = self.invasion_spawn_groups.get(lookup) or self.spawn_groups.get(lookup)
            if not definition:
                raise ValueError(f"Unknown spawn group {group!r}")
            group = definition
        key = (key or group.name).casefold()
        invasion = group.spawn_type == "invasion" if invasion is None else invasion
        map_id = map_id or self.map_id_for_spawn(group.map_file)
        points = [(self.creature_for_spawn(point.creature), point.x, point.y)
                  for point in group.points]
        if not points:
            raise ValueError(f"Spawn group {group.name!r} has no monster points")
        activated_at = now if now is not None else time.monotonic()
        active = ActiveSpawnGroup(group, invasion, activated_at, set(),
                                  instance_name=instance_name, map_id=map_id, key=key,
                                  level_target=level_target,
                                  pending_count=max(0, group.quantity(len(self.sessions))))
        self.fill_spawn_group(active, activated_at)
        # The first boss is due immediately, waiting for space if necessary.
        # Subsequent bosses use the configured threshold,
        # chance (out of 10,000), and delay.
        if group.boss_type:
            active.boss_due_at = activated_at
        self.active_spawn_groups[key] = active
        return active

    def fill_spawn_group(self, active: ActiveSpawnGroup, now: float) -> int:
        """Spawn the unplaced part of a wave, stopping when its map is full."""
        group = active.definition
        added = 0
        # Removed corpses may have released IDs for a different group to use.
        active.actor_ids = {aid for aid in active.actor_ids
                            if (actor := self.animals.get(aid))
                            and actor.spawn_group == active.key}
        while active.pending_count:
            point = group.points[active.spawn_index % len(group.points)]
            creature = self.creature_for_spawn(point.creature)
            try:
                actor = self.spawn_animal(creature, point.x, point.y,
                    invasion=active.invasion, instance_name=active.instance_name,
                    spawn_group=active.key, map_id=active.map_id,
                    roll_equipment=False)
            except NoFreeCreatureTile:
                if not group.queue_overflow:
                    raise
                break
            actor.wander_radius = group.wander_radius
            if group.spawn_health_multiplier != 1.0:
                actor.max_health = max(1, int(actor.max_health * group.spawn_health_multiplier))
                actor.health = actor.max_health
            if active.level_target:
                self.apply_level_scale(actor, active.level_target)
            actor.unequipped_max_health = actor.max_health
            self.equip_creature(actor)
            active.actor_ids.add(actor.actor_id)
            active.pending_count -= 1
            active.spawn_index += 1
            added += 1
        active.reinforce_at = now + 1.0
        return added

    def group_alive_count(self, active: ActiveSpawnGroup) -> int:
        return sum(1 for actor_id in active.actor_ids
                   if (animal := self.animals.get(actor_id)) and animal.alive)

    async def respawn_spawn_group(self, active: ActiveSpawnGroup,
                                  now: float | None = None) -> None:
        for session in self.sessions:
            stale = session.visible_animals & active.actor_ids
            for actor_id in stale:
                await session.send(p.packet(p.REMOVE_ACTOR, struct.pack("<H", actor_id)))
            session.visible_animals.difference_update(stale)
            self.drop_animal_viewer(session, stale)
        if active.definition.queue_overflow:
            for actor_id in active.actor_ids:
                animal = self.animals.get(actor_id)
                if animal and animal.spawn_group == active.key:
                    self.remove_animal(animal)
            active.actor_ids.clear()
            active.pending_count += active.spawn_index
            active.spawn_index = 0
            self.fill_spawn_group(active, time.monotonic() if now is None else now)
        else:
            self.restore_spawn_group_actors(active)
        for session in self.sessions:
            if session.character:
                await self.sync_visible_animals(session)

    def restore_spawn_group_actors(self, active: ActiveSpawnGroup) -> None:
        for actor_id in active.actor_ids:
            animal = self.animals.get(actor_id)
            if not animal:
                continue
            animal.x, animal.y = self.free_creature_tile(
                animal.map_id, animal.spawn_x, animal.spawn_y,
                footprint_of(animal))
            self.equip_creature(animal)
            animal.health, animal.alive = animal.max_health, True
            # Inside the loop: this sat after it, reading whatever the loop
            # variable happened to hold. A group whose last member had been
            # removed left that None and raised, killing animal_loop and with
            # it every creature on the server; a group that survived only ever
            # had its last member's aggressor cleared, so the rest went on
            # chasing a ranged attacker straight through their own respawn.
            animal.ranged_aggressor_id = None

    async def process_spawn_groups(self, second: int | None = None,
                                   now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        second = int(time.time()) % 60 if second is None else second
        for active in list(self.active_spawn_groups.values()):
            if active.boss_actor_id is None:
                continue
            boss = self.animals.get(active.boss_actor_id)
            if boss is not None and boss.alive:
                continue
            # Register 024. Checked every pass rather than on the half-minute
            # slot below: a horde that stands around for another thirty
            # seconds after its boss falls has not dispersed, it has waited.
            active.boss_actor_id = None
            active.boss_spawned = False
            if active.definition.boss_disperse:
                await self.disperse_group(active)
                # And the group is over. Leaving it active would schedule the
                # next boss at once, because the population the boss rule
                # waits on is exactly what just walked off the map.
                for name, other in list(self.active_spawn_groups.items()):
                    if other is active:
                        del self.active_spawn_groups[name]
        slot = (int(now // 60), second)
        if second in (18, 48) and slot != self._last_spawn_slot:
            self._last_spawn_slot = slot
            for active in list(self.active_spawn_groups.values()):
                definition = active.definition
                if active.pending_count:
                    continue
                boss = self.animals.get(active.boss_actor_id) if active.boss_actor_id else None
                if active.boss_actor_id is not None and (boss is None or not boss.alive):
                    active.boss_actor_id = None
                    active.boss_spawned = False
                if active.invasion and definition.auto_respawn_minutes:
                    minutes = definition.auto_respawn_minutes
                    # A negative window is shut before it opens: the group
                    # spawns once and does not come back. A positive one runs
                    # out that many minutes after the group was activated.
                    if (minutes < 0
                            or now > active.activated_at + 60 * minutes):
                        continue
                alive = self.group_alive_count(active)
                if (alive == 0 and not definition.boss_type
                        and not active.instance_name):
                    await self.respawn_spawn_group(active, now=now)
                if (definition.boss_type
                        and active.boss_actor_id is None
                        and active.boss_due_at is None
                        and alive <= definition.boss_threshold
                        and definition.boss_chance > 0
                        and random.randrange(10_000) < definition.boss_chance):
                    active.boss_due_at = now + definition.boss_delay
        for active in list(self.active_spawn_groups.values()):
            if active.boss_due_at is not None and now >= active.boss_due_at and not active.boss_spawned:
                await self.spawn_group_boss(active, now=now)
            # A waiting boss gets the next free space before more escorts.
            if (active.pending_count and now >= active.reinforce_at
                    and active.boss_due_at is None):
                if self.fill_spawn_group(active, now):
                    for session in list(self.sessions):
                        if session.character and session.character.map_id == active.map_id:
                            await self.sync_visible_animals(session)
        await self.process_instances(now)
        await gauntlets.tick(self, now)

    def apply_boss_strength(self, actor: Animal) -> None:
        """Scale everything that decides the fight by this boss's own roll.

        Register 023: a boss is "a randomly-strong version of itself", so the
        roll has to reach more than its health bar - a boss with three times
        the health and its species' attack is a longer fight, not a harder
        one. Health, both combat levels and the damage it deals all move
        together, which is what makes one roll legible as one adjective.
        """
        strength = actor.boss_strength
        if strength == 1.0:
            return
        actor.max_health = max(1, int(actor.max_health * strength))
        actor.attack = max(0, int(round(actor.attack * strength)))
        actor.defense = max(0, int(round(actor.defense * strength)))
        if actor.boss_fight is not None and actor.boss_fight.heal:
            # Healing is one of the things that decides the fight, so it moves
            # with the rest of the roll. Left fixed, a boss that rolled strong
            # would heal a smaller share of a larger bar - the roll would make
            # it worse at the one thing that is not simply "more of it".
            actor.boss_fight.heal = max(
                1, int(round(actor.boss_fight.heal * strength)))
        # Damage is not stored on the actor - it is read from the species
        # every swing - so the roll reaches it in `creature_damage_range`.

    def apply_level_scale(self, actor: Animal, target_level: int) -> None:
        """Scale a creature to fight at `target_level`, a party's a/d level.

        A gauntlet is run at the level its party chose rather than at the
        level its roster was authored for, so every creature it lands is a
        version of its species at that level: the ratio of the target to
        the species' own combat level moves the health bar, both combat
        levels and - through `creature_damage_range` - the damage, the way a
        boss's roll does. The experience it is worth follows its levels.
        """
        definition = self.creatures[actor.creature_type]
        native = max(1.0, (definition.attack + definition.defense) / 2.0)
        factor = max(LEVEL_SCALE_MIN, min(LEVEL_SCALE_MAX, target_level / native))
        if abs(factor - 1.0) < 0.01:
            return
        actor.level_scale = factor
        actor.max_health = max(1, int(round(actor.max_health * factor)))
        actor.health = actor.max_health
        actor.attack = max(1, int(round(actor.attack * factor)))
        actor.defense = max(1, int(round(actor.defense * factor)))
        actor.xp = max(1, (actor.attack + actor.defense) // 2)
        if actor.boss_fight is not None and actor.boss_fight.heal:
            actor.boss_fight.heal = max(1, int(round(actor.boss_fight.heal * factor)))

    def creature_damage_range(self, animal: Animal) -> tuple[int, int]:
        """What this creature hits for, its boss roll included.

        Attack and defense live on the actor and are scaled once at spawn.
        Damage is read from the species on every swing, so a boss that rolled
        strong has to be applied here or it would hit for exactly what an
        ordinary one of its kind does.
        """
        definition = self.creatures[animal.creature_type]
        low = definition.effective_damage_min
        high = definition.effective_damage_max
        strength = animal.boss_strength * getattr(animal, "level_scale", 1.0)
        if strength == 1.0:
            return low, high
        low = max(0, int(round(low * strength)))
        return low, max(low, int(round(high * strength)))

    async def disperse_group(self, active: ActiveSpawnGroup) -> None:
        """Take the boss's horde off the map now that the boss is gone.

        Register 024's other half. What is left of a group after its boss dies
        is a scatter of ordinary creatures with nothing to defend, and leaving
        them standing turns the end of an invasion into a cleanup shift.
        """
        remaining = [animal for actor_id in active.actor_ids
                     if (animal := self.animals.get(actor_id)) and animal.alive]
        if not remaining:
            return
        maps = {animal.map_id for animal in remaining}
        ids = {animal.actor_id for animal in remaining}
        for animal in remaining:
            animal.alive = False
            self.combatants.discard(animal.actor_id)
            self.remove_animal(animal)
        payload = b"".join(struct.pack("<H", actor_id) for actor_id in ids)
        for session in list(self.sessions):
            # Every client on the map, not only the tracked viewers: removing
            # an actor a client never had is a no-op, and skipping one strands
            # the model on screen for good.
            if session.character and session.character.map_id in maps:
                await session.send(p.packet(p.REMOVE_ACTOR, payload))
            session.visible_animals.difference_update(ids)
            self.drop_animal_viewer(session, ids)
            had_aggressor = bool(session.aggressors & ids)
            session.aggressors.difference_update(ids)
            if session.combat_target in ids:
                session.combat_target = None
                session.pending_attack = None
                session.fleeing = False
                had_aggressor = True
            if session.character and had_aggressor and session.combat_target is None:
                await self.broadcast_map(
                    session.character.map_id,
                    p.actor_command(session.character.actor_id,
                                    p.CMD_LEAVE_COMBAT))
        active.actor_ids.difference_update(ids)

    async def spawn_group_boss(self, active: ActiveSpawnGroup,
                               now: float | None = None) -> None:
        definition = active.definition
        boss = self.bosses.get(definition.boss_type.casefold())
        creature_name = boss.creature if boss else definition.boss_type
        creature = self.creature_for_spawn(creature_name)
        point = definition.points[0]
        # The boss keeps the ordinary leash even when its group roams widely:
        # the group follows the boss, so a wandering boss would drag the whole
        # invasion behind it instead of holding the ground it spawned on.
        try:
            actor = self.spawn_animal(creature, point.x, point.y, invasion=active.invasion,
                invasion_boss=True, instance_name=active.instance_name,
                spawn_group=getattr(active, "key", "") or definition.name.casefold(),
                map_id=getattr(active, "map_id", "") or self.map_id_for_spawn(definition.map_file),
                roll_equipment=False)
        except NoFreeCreatureTile:
            if not definition.queue_overflow:
                raise
            active.boss_due_at = (time.monotonic() if now is None else now) + 1.0
            return
        boss_name = ""
        if boss:
            boss_name = boss.name
            actor.max_health = max(1, int(actor.max_health * boss.health_multiplier))
            low, high = boss.strength_min, boss.strength_max
            # Armed before the roll, so the roll can reach the healing too.
            actor.boss_fight = boss_fight(boss)
        elif definition.boss_name:
            boss_name = definition.boss_name
            actor.max_health = max(
                1, int(actor.max_health * definition.boss_health_multiplier))
            low, high = definition.boss_strength_min, definition.boss_strength_max
        else:
            low = high = 1.0
        # Register 023: how powerful a version of itself this one is, rolled
        # here and applied to everything that decides the fight. A range of
        # 1.0 to 1.0 rolls 1.0, so a boss that was a fixed statblock stays one.
        actor.boss_strength = random.uniform(low, high) if high > low else low
        self.apply_boss_strength(actor)
        # A group set to a level scales its boss to it as well, on top of
        # the roll: the boss is still a bigger one of the wave it leads.
        if getattr(active, "level_target", 0):
            self.apply_level_scale(actor, active.level_target)
        actor.health = actor.max_health
        actor.unequipped_max_health = actor.max_health
        # A boss's gear is authored rather than rolled where its block says
        # so; `boss.weapons` is empty for one that carries whatever any
        # creature of its kind might, and the roll happens as usual.
        self.equip_creature(actor, boss.weapons if boss else ())
        if boss_name:
            epithet = next((word for threshold, word in BOSS_EPITHETS
                            if actor.boss_strength >= threshold), "")
            titled = f"{epithet} {boss_name}" if epithet else boss_name
            actor.name = ((chr(127 + p.EL_COLOR_RED3) + titled)
                          if active.invasion else titled)
        if active.invasion:
            # Multiplied, not assigned: a boss is a bigger one of its species,
            # and assigning would make the boss of a species authored above
            # 1.2 smaller than its own kind. A strong roll shows on top of
            # that, because size is how a player reads the roll without a
            # window - which is register 024 answering register 023.
            actor.scale = min(p.MAX_ACTOR_SCALE,
                              actor.scale * INVASION_BOSS_SCALE
                              * max(1.0, actor.boss_strength))
        active.actor_ids.add(actor.actor_id)
        active.boss_actor_id = actor.actor_id
        active.boss_due_at = None
        active.boss_spawned = True

    async def start_instance(self, name: str, now: float | None = None,
                             participant_ids: set[int] | None = None) -> ActiveInstance:
        definition = self.instances.get(name.casefold())
        if not definition:
            raise ValueError(f"Unknown instance {name!r}")
        map_id = self.map_id_for_spawn(definition.map_file)
        if self.active_instance_on_map(map_id):
            raise ValueError(f"An instance is already active on {self.maps[map_id].name}.")
        active = ActiveInstance(
            definition, 0, now if now is not None else time.monotonic(),
            set(), set(participant_ids or ()))
        self.active_instances[name.casefold()] = active
        try:
            await self.start_instance_wave(active, 1, active.wave_started_at)
        except Exception:
            self.active_instances.pop(name.casefold(), None)
            raise
        return active

    async def start_instance_wave(self, active: ActiveInstance, number: int, now: float) -> None:
        wave = next((item for item in active.definition.waves if item.number == number), None)
        if not wave:
            return
        variant = random.choice(wave.variants) if wave.variants else ()
        active.group_names.clear()
        for group_name in variant:
            self.activate_spawn_group(group_name, invasion=True,
                                      instance_name=active.definition.name.casefold(), now=now)
            active.group_names.add(group_name.casefold())
        active.wave, active.wave_started_at = number, now

    async def process_instances(self, now: float) -> None:
        for active in self.active_instances.values():
            wave = next((item for item in active.definition.waves if item.number == active.wave), None)
            if not wave:
                continue
            remaining = sum(self.group_alive_count(self.active_spawn_groups[name])
                            for name in active.group_names if name in self.active_spawn_groups)
            elapsed = int(now - active.wave_started_at)
            for trigger in wave.triggers:
                if (elapsed >= trigger.minimum_time
                        and (trigger.maximum_monsters is None or remaining <= trigger.maximum_monsters)
                        and trigger.next_wave and trigger.next_wave > active.wave):
                    await self.start_instance_wave(active, trigger.next_wave, now)
                    break

    def boss_follow_anchor(self, animal: Animal) -> tuple[int, int] | None:
        """Return the living group boss that temporarily anchors this creature."""
        if not animal.spawn_group:
            return None
        active = self.active_spawn_groups.get(animal.spawn_group.casefold())
        if not active or active.boss_actor_id in (None, animal.actor_id):
            return None
        boss = self.animals.get(active.boss_actor_id)
        if not boss or not boss.alive or boss.map_id != animal.map_id:
            return None
        return boss.x, boss.y

    def invalidate_creature_index(self, map_id: str) -> None:
        """Drop a map's position snapshot after a death or relocation."""
        self._creature_index.pop(map_id, None)

    def index_creature(self, animal: Animal) -> None:
        """Add a newly spawned creature to the current snapshot.

        Dropping the snapshot instead would make the next placement rebuild it
        from scratch, which turned spawning a wave into quadratic work in the
        size of the wave.
        """
        cached = self._creature_index.get(animal.map_id)
        if cached is None:
            return
        key = (animal.x >> INDEX_CELL_BITS, animal.y >> INDEX_CELL_BITS)
        cached[1].setdefault(key, []).append(animal)

    def occupied_tiles_near(self, map_id: str, x: int, y: int,
                            radius: int) -> set[tuple[int, int]]:
        """Occupied tiles within `radius` of a point.

        Placement only ever inspects a small neighbourhood, so building the
        whole map's occupancy for it was work proportional to the population
        of the map on every single spawn.
        """
        occupied = set()
        for animal in self.creatures_near(map_id, x, y, radius):
            if animal.alive:
                occupied.update(footprint_of(animal).tiles(animal.x, animal.y))
        for session in self.sessions:
            character = session.character
            if (character is not None and character.map_id == map_id
                    and max(abs(character.x - x), abs(character.y - y)) <= radius):
                occupied.update(footprint_of(character).tiles(character.x, character.y))
        for npc, npc_map, _, _ in self.npcs.values():
            if (npc_map == map_id
                    and max(abs(npc.x - x), abs(npc.y - y)) <= radius):
                occupied.update(footprint_of(npc).tiles(npc.x, npc.y))
        return occupied

    def blocked_anchors(self, occupied, start: tuple[int, int],
                        shape: Footprint, reach: int) -> set[tuple[int, int]]:
        """Anchors a mover of `shape` cannot take, within `reach` of `start`.

        Three things happen here, in this order because none of them commutes:
        take the neighbourhood a bounded search can actually reach, drop the
        mover's own body from it - a creature does not block itself - and grow
        what is left by the mover's shape, so the search's existing one-tile
        membership test answers "does my whole box clear this".

        The reach is widened by the footprint because an obstacle just outside
        the search's own range still blocks a wide body inside it.
        """
        span = max(shape.width, shape.depth)
        local = occupied_near(occupied, start, reach + span)
        if not shape.is_single_tile:
            local = local - set(shape.tiles(*start))
        return dilate(local, shape)

    @staticmethod
    def anchor_blocked(occupied, x: int, y: int, shape: Footprint,
                       ignore: tuple[int, int] | None = None) -> bool:
        """Whether a body of `shape` anchored at (x, y) would overlap anything.

        For one candidate tile this is cheaper than dilating the whole set;
        `blocked_anchors` is for searches that test the same set thousands of
        times. `ignore` is the mover's current anchor, whose own tiles are
        still in `occupied` and must not count against it.
        """
        if shape.is_single_tile:
            return (x, y) in occupied and (x, y) != ignore
        ignored = frozenset(shape.tiles(*ignore)) if ignore is not None else frozenset()
        return any(tile in occupied and tile not in ignored
                   for tile in shape.tiles(x, y))

    def creature_index(self, map_id: str) -> dict[tuple[int, int], list[Animal]]:
        """Return this map's creature positions bucketed into index cells.

        Rebuilt at most once per AI tick. Walking every creature on the map for
        every player was the single most expensive thing the server did: at 500
        players and 10,000 creatures it cost five million distance tests a tick
        to reject creatures that were never within thirty tiles of anyone.
        """
        now = time.monotonic()
        cached = self._creature_index.get(map_id)
        if cached is not None and (
                self._index_pinned or now - cached[0] < INDEX_REFRESH_SECONDS):
            # Pinned: one AI tick shares a single snapshot. Letting the age
            # test run mid-tick made a slow tick rebuild the index over and
            # over, so the loop got slower the slower it already was.
            return cached[1]
        cells: dict[tuple[int, int], list[Animal]] = {}
        animals = self.animals
        for actor_id in self.animals_by_map.get(map_id, ()):
            animal = animals.get(actor_id)
            if animal is None or not animal.alive:
                continue
            key = (animal.x >> INDEX_CELL_BITS, animal.y >> INDEX_CELL_BITS)
            bucket = cells.get(key)
            if bucket is None:
                cells[key] = [animal]
            else:
                bucket.append(animal)
        self._creature_index[map_id] = (now, cells)
        return cells

    def creatures_near(self, map_id: str, x: int, y: int, radius: int):
        """Yield candidate creatures around a point, whole cells at a time.

        The result is a superset of what is genuinely in range; callers apply
        the exact Chebyshev test to the live position of each candidate.
        """
        cells = self.creature_index(map_id)
        if not cells:
            return
        for key in index_cells(x, y, radius + INDEX_SLACK_TILES):
            bucket = cells.get(key)
            if bucket:
                yield from bucket

    @staticmethod
    def index_sessions(sessions) -> dict[tuple[int, int], list[Session]]:
        """Bucket logged-in sessions by index cell for pursuit-radius queries."""
        cells: dict[tuple[int, int], list[Session]] = {}
        for session in sessions:
            character = session.character
            if character is None:
                continue
            key = (character.x >> INDEX_CELL_BITS, character.y >> INDEX_CELL_BITS)
            bucket = cells.get(key)
            if bucket is None:
                cells[key] = [session]
            else:
                bucket.append(session)
        return cells

    @staticmethod
    def sessions_near(cells: dict[tuple[int, int], list[Session]],
                      x: int, y: int, radius: int) -> list[Session]:
        """Return sessions within `radius` of a point, nearest first."""
        if not cells:
            return []
        found: list[tuple[int, int, Session]] = []
        for key in index_cells(x, y, radius):
            for session in cells.get(key, ()):
                character = session.character
                distance = max(abs(character.x - x), abs(character.y - y))
                if distance <= radius:
                    found.append((distance, character.actor_id, session))
        found.sort()
        return [session for _, _, session in found]

    def awake_maps(self, players_by_map, self_driven: set[str]) -> set[str]:
        """The maps whose creatures the AI tick walks.

        The served world is sixty-five maps and twenty-five of them hold
        wildlife; at any moment a player is on one or two. The other twenty-odd
        were being walked twenty times a second so that creatures nobody could
        see could take a step nobody would be told about, and then take another
        one somewhere else before anybody arrived. A map with no player on it
        and nothing on it that drives itself is dormant: its creatures hold
        their ground until somebody turns up, which is the tick after they do,
        because the player list is rebuilt every tick.

        What is *not* behind this switch: respawns, spawn-group upkeep, bag
        expiry and the raid clock all run above it on their own cadence, so a
        dormant map still repopulates and still keeps its clocks.

        What keeps a map awake with nobody on it:

        - a creature that drives itself rather than merely wandering - an
          invasion or event wave, a summon whose owner walked off, an instance
          or gauntlet roster. The caller finds these in the one pass it already
          makes over the creature table and hands them in as `self_driven`;
        - a spawn group, instance or gauntlet that is active but has nothing
          alive on its map this instant, between waves or waiting for a boss,
          because the next thing it does is put creatures there;
        - the map a territory raid is being fought over.
        """
        awake = set(players_by_map)
        awake |= self_driven
        # A map whose creatures a player watches across a land seam steps them
        # too, or they would stand frozen until the seam was crossed.
        for session in self.sessions:
            watched = getattr(session, "visible_adjacent", None)
            if watched:
                awake.update(watched.values())
        for active in self.active_spawn_groups.values():
            if active.invasion or active.instance_name:
                awake.add(active.map_id
                          or self.map_id_for_spawn(active.definition.map_file))
        for active in self.active_instances.values():
            awake.add(self.map_id_for_spawn(active.definition.map_file))
        awake.update(map_id for map_id, run in gauntlets.runs(self).items()
                     if not run.over)
        raid = self.territory_raids.active
        if raid is not None and not raid.finished:
            awake.add(raid.defender.map_id)
        awake.discard("")
        return awake

    def creature_occupied_tiles(self, map_id: str,
                                exclude_id: int | None = None) -> OccupiedTiles:
        tiles: set[tuple[int, int]] = set()
        for actor_id in self.animals_by_map.get(map_id, ()):
            if actor_id == exclude_id:
                continue
            animal = self.animals.get(actor_id)
            if animal and animal.alive:
                tiles.update(footprint_of(animal).tiles(animal.x, animal.y))
        for session in self.sessions:
            character = session.character
            if character and character.map_id == map_id:
                tiles.update(footprint_of(character).tiles(character.x, character.y))
        for npc, npc_map, _, _ in self.npcs.values():
            if npc_map == map_id:
                tiles.update(footprint_of(npc).tiles(npc.x, npc.y))
        return OccupiedTiles(tiles)

    def free_creature_tile(self, map_id: str, x: int, y: int,
                           shape: Footprint = SINGLE) -> tuple[int, int]:
        occupied = self.occupied_tiles_near(map_id, x, y, FREE_TILE_SEARCH_RADIUS)
        if (not self.anchor_blocked(occupied, x, y, shape)
                and self.is_walkable(map_id, x, y, shape)):
            return x, y
        # Expanding square rings provide deterministic, compact, non-overlapping
        # invasion placement without repeating after the first 25 creatures.
        for radius in range(1, FREE_TILE_SEARCH_RADIUS + 1):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    candidate = x + dx, y + dy
                    if (max(abs(dx), abs(dy)) == radius
                            and not self.anchor_blocked(occupied, *candidate, shape)
                            and self.is_walkable(map_id, *candidate, shape)):
                        return candidate
        raise NoFreeCreatureTile(
            f"No free {shape} creature tile near {x},{y} on {map_id}.")

    def remove_animal(self, animal: Animal):
        animal.alive = False
        self.clear_actor_magic(animal)
        self.animals.pop(animal.actor_id, None)
        self.animal_viewers.pop(animal.actor_id, None)
        # Actor ids are recycled, so a rot left running on a departed creature
        # would keep biting whatever inherited its number.
        rot = self.creature_rot_tasks.pop(animal.actor_id, None)
        if rot is not None and not rot.done():
            rot.cancel()
        self.invalidate_creature_index(animal.map_id)
        self.release_id(animal.actor_id)
        ids = self.animals_by_map.get(animal.map_id)
        if ids is not None:
            ids.discard(animal.actor_id)
            if not ids:
                self.animals_by_map.pop(animal.map_id, None)

    def invasion_monsters_remaining(self) -> int:
        return sum(1 for animal in self.animals.values()
                   if animal.invasion and not animal.instance_name and animal.alive)

    def instance_monsters_remaining(self, map_id: str) -> int:
        return sum(1 for animal in self.animals.values()
                   if animal.instance_name and animal.map_id == map_id and animal.alive)

    def active_instance_on_map(self, map_id: str):
        run = gauntlets.run_on(self, map_id)
        if run is not None:
            return run
        return next((active for active in self.active_instances.values()
                     if self.map_id_for_spawn(active.definition.map_file) == map_id), None)

    @staticmethod
    def active_channel_number(session: Session) -> int | None:
        if not session.joined_channels or not 0 <= session.active_channel < len(session.joined_channels):
            return None
        return session.joined_channels[session.active_channel]

    async def enter_instance_team(self, leader: Session, npc: NPCActor,
                                  instance_name: str) -> int:
        character = leader.character
        definition = self.instances.get(instance_name.casefold())
        if not character or not definition:
            raise ValueError(f"Unknown instance {instance_name!r}.")
        channel = self.active_channel_number(leader)
        if channel is None or channel <= 1000:
            raise ValueError("Set a team channel above 1000 as your active channel first.")

        team = [
            session for session in self.sessions
            if session.character
            and session.character.map_id == character.map_id
            and self.active_channel_number(session) == channel
            and max(abs(session.character.x - npc.x),
                    abs(session.character.y - npc.y)) <= 4
        ]
        if len(team) < definition.minimum_players:
            raise ValueError(
                f"{definition.description} requires at least "
                f"{definition.minimum_players} nearby team member(s).")

        ineligible = []
        now_epoch = int(time.time())
        for member in team:
            teammate = member.character
            average_ad = (teammate.skills["attack"] + teammate.skills["defense"]) // 2
            if average_ad < definition.minimum_ad or (
                    definition.maximum_ad and average_ad > definition.maximum_ad):
                ineligible.append(
                    f"{teammate.name} ({average_ad} a/d; needs "
                    f"{definition.minimum_ad}"
                    f"{'-' + str(definition.maximum_ad) if definition.maximum_ad else '+'})")
                continue
            last_entered = int(
                teammate.quest_state.get(f"last_instance_{definition.name.casefold()}", 0))
            hours_since = (now_epoch - last_entered) / 3600 if last_entered else float("inf")
            if hours_since < definition.cooldown_hours:
                ineligible.append(
                    f"{teammate.name} ({definition.cooldown_hours - hours_since:.1f} hours left)")
        if ineligible:
            raise ValueError("Team cannot enter: " + "; ".join(ineligible))

        for member in team:
            self.require_coordinate_destination(member, self.map_id_for_spawn(definition.map_file),
                                                definition.entry_x, definition.entry_y)
        active = await self.start_instance(
            definition.name,
            participant_ids={member.character.actor_id for member in team})
        for member in team:
            teammate = member.character
            teammate.quest_state[
                f"last_instance_{definition.name.casefold()}"] = now_epoch
            await self.change_map(
                member, self.map_id_for_spawn(definition.map_file),
                definition.entry_x, definition.entry_y)
            await member.send(p.deep_blue_text(
                f"Entered {definition.description}, wave {active.wave}."))
        return len(team)

    async def create_invasion(self, x: int, y: int, map_id: str, creature_type: str, quantity: int):
        requested_map = map_id
        map_id = self.resolve_map(map_id)
        if not map_id:
            raise ValueError(f"Unknown map id {requested_map!r}.")
        if creature_type not in self.creatures:
            raise ValueError(f"Unknown creature {creature_type!r}.")
        if not 1 <= quantity <= 100:
            raise ValueError("Quantity must be between 1 and 100.")
        spawned = []
        for index in range(quantity):
            ox, oy = (index % 5) - 2, (index // 5) % 5 - 2
            animal = self.spawn_animal(creature_type, x + ox, y + oy,
                                       invasion=True, map_id=map_id)
            # #invasion names no region, so the wave spreads over the map
            # rather than pacing around the coordinates it landed on.
            animal.wander_radius = WIDE_WANDER_RADIUS
            spawned.append(animal)
        for session in self.sessions:
            if session.character and session.character.map_id == map_id:
                await self.sync_visible_animals(session)

    async def clear_invasion(self) -> int:
        invaded = [animal for animal in self.animals.values()
                   if animal.invasion and not animal.instance_name]
        for name, active in list(self.active_spawn_groups.items()):
            if active.invasion and not active.instance_name:
                del self.active_spawn_groups[name]
        for animal in invaded:
            animal.alive = False
            self.combatants.discard(animal.actor_id)
            self.remove_animal(animal)
        invaded_ids = {animal.actor_id for animal in invaded}
        if invaded:
            invaded_maps = {animal.map_id for animal in invaded}
            payload = b"".join(struct.pack("<H", animal.actor_id) for animal in invaded)
            # Removal goes to everyone standing on an invaded map, not only to
            # the tracked viewers: this is the command that has to leave the map
            # clean, and removing an actor id a client never had is a no-op for
            # it, whereas skipping one strands the model on screen for good.
            for session in list(self.sessions):
                if session.character and session.character.map_id in invaded_maps:
                    await session.send(p.packet(p.REMOVE_ACTOR, payload))
                session.visible_animals.difference_update(invaded_ids)
                self.drop_animal_viewer(session, invaded_ids)
        for session in list(self.sessions):
            had_invasion_aggressor = bool(session.aggressors & invaded_ids)
            session.aggressors.difference_update(invaded_ids)
            target_was_invasion = session.combat_target in invaded_ids
            if target_was_invasion:
                session.combat_target = None
                session.pending_attack = None
                session.fleeing = False
            if session.character and (target_was_invasion or
                                      (had_invasion_aggressor and session.combat_target is None)):
                await self.broadcast_map(
                    session.character.map_id,
                    p.actor_command(session.character.actor_id,
                                    p.CMD_LEAVE_COMBAT))
        return len(invaded)

    def allocate_id(self):
        """Return an unused actor id, recycling retired ones.

        Actor ids go on the wire as an unsigned 16-bit field, so counting
        upward forever raised `struct.error` on the first spawn past 65535.
        At the invasion sizes this server targets, respawn churn reaches that
        ceiling in ordinary play rather than as an edge case.
        """
        if self._retired_actor_ids:
            cutoff = time.monotonic() - ACTOR_ID_REUSE_DELAY_SECONDS
            while self._retired_actor_ids and self._retired_actor_ids[0][0] <= cutoff:
                self._free_actor_ids.append(self._retired_actor_ids.popleft()[1])
        if self.next_actor_id < MAX_ACTOR_ID:
            self.next_actor_id += 1
            return self.next_actor_id
        if self._free_actor_ids:
            return self._free_actor_ids.popleft()
        if self._retired_actor_ids:
            # Nothing has cooled down yet, but an id in hand beats a crash: the
            # oldest retirement is the one whose REMOVE_ACTOR is least likely
            # to still be in flight.
            return self._retired_actor_ids.popleft()[1]
        raise RuntimeError(
            f"actor id space exhausted: all {MAX_ACTOR_ID} ids are in use")

    def release_id(self, actor_id: int) -> None:
        """Retire an actor id for later reuse once its removal has landed."""
        if 0 < actor_id <= MAX_ACTOR_ID:
            self._retired_actor_ids.append((time.monotonic(), actor_id))

    def tutorial_return_destination(self, session: Session | None = None) -> tuple[str, int, int]:
        """Return beside the guide so another adventure is within talking range.

        The guide stands at the home (eloria/home.py): Four Gates by default.
        """
        return home.tutorial_return(self, session)

    def free_player_tile(self, map_id: str, x: int, y: int, *, exclude=None,
                         shape: Footprint = SINGLE) -> tuple[int, int]:
        occupied: set[tuple[int, int]] = set()
        for session in self.sessions:
            character = session.character
            if (character and character is not exclude
                    and character.map_id == map_id):
                occupied.update(footprint_of(character).tiles(character.x, character.y))
        for actor_id in self.animals_by_map.get(map_id, ()):
            animal = self.animals.get(actor_id)
            if animal and animal.alive:
                occupied.update(footprint_of(animal).tiles(animal.x, animal.y))
        if (not self.anchor_blocked(occupied, x, y, shape)
                and self.is_walkable(map_id, x, y, shape)):
            return x, y
        for radius in range(1, 20):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if (max(abs(dx), abs(dy)) == radius
                            and not self.anchor_blocked(occupied, x+dx, y+dy, shape)
                            and self.is_walkable(map_id, x+dx, y+dy, shape)):
                        return x+dx, y+dy
        return x, y

    def collision_for(self, map_id: str, shape: Footprint = SINGLE):
        """This map as a creature of that shape sees it.

        A footprint larger than one tile gets a map eroded by its own box, so
        the tiles it may stand on are the tiles that are walkable on it. That
        turns "does my body fit here" back into "is this tile walkable", which
        is the question every path search, step mask and corner test already
        asks - so none of them need to know that footprints exist.

        Eroding is proportional to the map, so it is done once per map per
        shape and kept. Most maps never hold a large creature and never build
        one; a map that does builds it when the first one is placed.
        """
        collision = self.collision_maps.get(map_id)
        if collision is None or shape.is_single_tile:
            return collision
        key = (map_id, shape.width, shape.depth)
        eroded = self._footprint_collision.get(key)
        if eroded is None:
            eroded = erode_for_footprint(
                collision, shape, self.settings.max_walk_height_change)
            self._footprint_collision[key] = eroded
            log.debug("eroded collision for %s at %s", map_id, shape)
        return eroded

    def is_walkable(self, map_id: str, x: int, y: int,
                    shape: Footprint = SINGLE) -> bool:
        collision = self.collision_for(map_id, shape)
        if collision:
            return collision.walkable(x, y)
        # No terrain data: the whole map is open, but a footprint still has to
        # fit inside the coordinate space rather than hang off the edge of it.
        min_x, min_y, max_x, max_y = shape.bounds(x, y)
        return 0 <= min_x and 0 <= min_y and max_x <= 2047 and max_y <= 2047

    def step_mask_at(self, map_id: str, x: int, y: int,
                     shape: Footprint = SINGLE) -> int | None:
        """The legal steps off one tile as a bitmask, or None to test singly."""
        collision = self.collision_for(map_id, shape)
        if collision is None:
            return None
        return collision.steps_from(x, y, self.settings.max_walk_height_change)

    def step_allowed(self, map_id: str, x: int, y: int, sx: int, sy: int,
                     mask: int | None, shape: Footprint = SINGLE) -> bool:
        """Whether a creature at (x, y) may step (sx, sy), corners included.

        `mask` comes from step_mask_at and is resolved once per creature. The
        check itself is a bit test; finding out which map to test against cost
        several times more than the test did, and the loop was paying that
        once per candidate direction.
        """
        bit = STEP_BIT.get((sx, sy)) if mask is not None else None
        if bit is not None:
            if not mask & bit:
                return False
            return (not sx or not sy
                    or bool(mask & STEP_BIT[(sx, 0)]
                            and mask & STEP_BIT[(0, sy)]))
        # No mask, or a movement that is not one of the eight single steps -
        # a standing "step" of (0, 0) among them. Derive it as before.
        start = (x, y)
        if not self.can_walk_step(map_id, start, (x + sx, y + sy), shape):
            return False
        return (not sx or not sy
                or (self.can_walk_step(map_id, start, (x + sx, y), shape)
                    and self.can_walk_step(map_id, start, (x, y + sy), shape)))

    def search_mask(self, collision):
        """One map's step mask and logical bounds, or None where there is none.

        Resolved once for a whole A* traversal. Every node a search expands
        asks up to sixteen questions of `can_walk_step` - eight moves and, for
        each of the four diagonals, the two orthogonal moves whose corner it
        cuts - and each of those walks `collision_for`, the footprint cache and
        the mask property again to answer from the same byte. The mask holds
        all of a tile's answers in that one byte, so an expansion becomes one
        read and a few bit tests.

        None when the map has no mask - no numpy to build one, or a climb
        limit it was not built for - and the searches fall back to the tests
        they always used.
        """
        if collision is None:
            return None
        if self.settings.max_walk_height_change != collision.step_climb:
            return None
        mask = collision.steps
        if mask is None:
            return None
        return mask, collision.bounds

    def can_walk_step(self, map_id: str, start: tuple[int, int],
                      end: tuple[int, int], shape: Footprint = SINGLE) -> bool:
        collision = self.collision_for(map_id, shape)
        return (collision.can_step(*start, *end, self.settings.max_walk_height_change)
                if collision else self.is_walkable(map_id, *end, shape))

    def find_path(self, map_id: str, start: tuple[int, int], target: tuple[int, int],
                  occupied: set[tuple[int, int]],
                  shape: Footprint = SINGLE) -> list[tuple[int, int]]:
        """A* over authoritative ELM height tiles, with diagonal corner blocking.

        `shape` is the mover's footprint: the search runs over the map eroded
        by it, so every tile it reaches is one the whole body fits on. The
        anchors it returns are still single tiles, because that is what the
        mover's position is. `occupied` must already be dilated by the same
        shape - see `blocked_anchors` - since which anchors an obstacle rules
        out depends on who is asking.

        An occupied destination is approached from any reachable adjacent
        tile. Clicking an NPC must not require stepping onto its body.
        """
        collision = self.collision_for(map_id, shape)
        if not collision:
            x, y = start
            result = []
            while (x, y) != target and len(result) < 512:
                nx = x + (target[0] > x) - (target[0] < x)
                ny = y + (target[1] > y) - (target[1] < y)
                if (nx, ny) in occupied or not self.is_walkable(map_id, nx, ny, shape):
                    break
                x, y = nx, ny
                result.append((x, y))
            return result
        if target not in occupied and not self.is_walkable(map_id, *target, shape):
            target = self.free_player_tile(map_id, *target, shape=shape)
        goal_radius = 1 if target in occupied else 0
        masked = self.search_mask(collision)
        mask_bytes, mask_bounds = masked or (None, None)
        queue = [(0, 0, start)]
        previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost = {start: 0}
        sequence = 0
        destination = None
        while queue and len(previous) <= 100_000:
            _, _, current = heapq.heappop(queue)
            if max(abs(target[0] - current[0]),
                   abs(target[1] - current[1])) <= goal_radius:
                destination = current
                break
            cx, cy = current
            mask_index = mask_bounds.index(cx, cy) if mask_bounds is not None else None
            masked_here = mask_bytes is not None and mask_index is not None
            for dx, dy in (LEGAL_STEPS[mask_bytes[mask_index]]
                           if masked_here else DIRS):
                nxt = cx + dx, cy + dy
                if nxt in occupied:
                    continue
                if not masked_here:
                    if not self.can_walk_step(map_id, current, nxt, shape):
                        continue
                    if dx and dy and (
                            not self.can_walk_step(map_id, current, (cx+dx, cy), shape)
                            or not self.can_walk_step(map_id, current, (cx, cy+dy), shape)):
                        continue
                new_cost = cost[current] + (14 if dx and dy else 10)
                if nxt not in cost or new_cost < cost[nxt]:
                    cost[nxt] = new_cost
                    previous[nxt] = current
                    sequence += 1
                    heuristic = 10 * max(
                        max(abs(target[0]-nxt[0]), abs(target[1]-nxt[1])) - goal_radius, 0)
                    heapq.heappush(queue, (new_cost + heuristic, sequence, nxt))
        if destination is None:
            return []
        path = []
        current = destination
        while current != start:
            path.append(current)
            current = previous[current]
        return list(reversed(path))[:512]

    def spend_path_budget(self) -> bool:
        """Claim one of this tick's A* searches, or report that none are left.

        The allowance is a slice of wall-clock time, not a count: what a
        search costs depends on the map and on how far the target is, and a
        single one can exceed a whole tick when the target is unreachable.
        Counting them bounds the number but not the tick, which is the thing
        that has to stay inside its deadline. A creature refused here keeps
        its existing route or wanders, and asks again next tick.
        """
        if self._path_budget is None:
            return True
        if self._path_budget <= 0 or time.monotonic() >= self._path_deadline:
            return False
        self._path_budget -= 1
        return True

    def find_path_to_any(self, map_id: str, start: tuple[int, int],
                         targets: set[tuple[int, int]],
                         occupied: set[tuple[int, int]], max_steps: int,
                         shape: Footprint = SINGLE) -> list[tuple[int, int]]:
        """Find one bounded route to any target using a single A* traversal."""
        if not targets or max_steps <= 0:
            return []
        collision = self.collision_for(map_id, shape)
        if not collision:
            # No terrain data, so there is no eroded grid to run the search
            # over and each target has to be tried on its own. Nearest first,
            # and more than one of them: the closest tile of a ring of attack
            # positions is routinely the one somebody is standing on, and
            # giving up there reported "unreachable" for a target with eleven
            # other open sides.
            ordered = sorted(targets, key=lambda point: (
                max(abs(point[0] - start[0]), abs(point[1] - start[1])), point))
            for target in ordered[:FALLBACK_PATH_TARGETS]:
                path = self.find_path(map_id, start, target, occupied, shape)
                if path and len(path) <= max_steps:
                    return path
            return []

        # Distance to the targets' bounding box. Every target lies inside the
        # box, so this never exceeds the true distance to the nearest one and
        # A* keeps finding shortest routes - but it costs the same for one
        # target as for the ring of attack positions around a player, instead
        # of rescanning them all for every node the search expands.
        min_x = min(point[0] for point in targets)
        max_x = max(point[0] for point in targets)
        min_y = min(point[1] for point in targets)
        max_y = max(point[1] for point in targets)

        def heuristic(point: tuple[int, int]) -> int:
            x, y = point
            return 10 * max(min_x - x, 0, x - max_x,
                            min_y - y, 0, y - max_y)

        masked = self.search_mask(collision)
        mask_bytes, mask_bounds = masked or (None, None)
        queue = [(heuristic(start), 0, start)]
        previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost = {start: 0}
        steps = {start: 0}
        sequence = 0
        destination = None
        while queue:
            _, _, current = heapq.heappop(queue)
            if current in targets:
                destination = current
                break
            if steps[current] >= max_steps:
                continue
            cx, cy = current
            mask_index = mask_bounds.index(cx, cy) if mask_bounds is not None else None
            masked_here = mask_bytes is not None and mask_index is not None
            for dx, dy in (LEGAL_STEPS[mask_bytes[mask_index]]
                           if masked_here else DIRS):
                nxt = cx + dx, cy + dy
                if nxt in occupied:
                    continue
                if not masked_here:
                    if not self.can_walk_step(map_id, current, nxt, shape):
                        continue
                    if dx and dy and (
                            not self.can_walk_step(
                                map_id, current, (cx + dx, cy), shape)
                            or not self.can_walk_step(
                                map_id, current, (cx, cy + dy), shape)):
                        continue
                new_cost = cost[current] + (14 if dx and dy else 10)
                new_steps = steps[current] + 1
                if (nxt not in cost or new_cost < cost[nxt]
                        or (new_cost == cost[nxt] and new_steps < steps[nxt])):
                    cost[nxt] = new_cost
                    steps[nxt] = new_steps
                    previous[nxt] = current
                    sequence += 1
                    heapq.heappush(
                        queue, (new_cost + heuristic(nxt), sequence, nxt))
        if destination is None:
            return []
        path = []
        current = destination
        while current != start:
            path.append(current)
            current = previous[current]
        return list(reversed(path))

    async def broadcast(self, data: bytes):
        for s in list(self.sessions):
            if s.character:
                await self.deliver(s, data)

    async def broadcast_except(self, data: bytes, excluded: Session):
        for s in list(self.sessions):
            if s is not excluded and s.character:
                await self.deliver(s, data)

    async def ensure_animal_visible(self, session: Session, animal: Animal) -> None:
        """Put a creature on a client's screen before telling it about one.

        Views are refreshed on a stagger, so a creature can start a fight in
        the fraction of a second before its target's next refresh. Combat
        commands go to the creature's viewers, so its opponent has to be one.
        """
        actor_id = animal.actor_id
        if actor_id in session.visible_animals:
            self.animal_viewers[actor_id].add(session)
            return
        if actor_id in (getattr(session, "visible_adjacent", None) or {}):
            self.animal_viewers[actor_id].add(session)
            return
        character = session.character
        if character is None or character.map_id != animal.map_id:
            return
        session.visible_animals.add(actor_id)
        self.animal_viewers[actor_id].add(session)
        await session.send(self.creature_actor_packet(session, animal))

    def drop_animal_viewer(self, session: Session, actor_ids) -> None:
        """Forget that a session was showing these creatures."""
        viewers = self.animal_viewers
        for actor_id in actor_ids:
            watching = viewers.get(actor_id)
            if watching is None:
                continue
            watching.discard(session)
            if not watching:
                del viewers[actor_id]

    async def deliver(self, session: Session, data: bytes) -> None:
        """Send a packet to one session, batching it when that is safe.

        Queueing is only correct while something is draining the queue, so
        this batches when a flush driver is running and writes immediately
        otherwise. Nothing may be parked in a buffer nobody will empty.
        """
        if self._flush_drivers:
            session.queue(data)
            return
        try:
            await session.send(data)
        except (ConnectionError, asyncio.CancelledError):
            pass

    async def broadcast_actor(self, actor, data: bytes) -> None:
        """Send an actor update to the clients that can actually use it.

        A creature's combat rounds, damage numbers and facing changes go to
        the players tracking that creature; a player's go to everyone on the
        same map. These all used to go to every session on the server, so a
        client standing on another map still paid to receive - and discard -
        every swing of every creature in an invasion it could not see.
        """
        actor_id = actor.actor_id
        map_id = actor.map_id
        if actor_id in self.animals:
            # Straight to the clients showing this creature. Scanning every
            # session for each one turned a busy invasion into hundreds of
            # full session sweeps per tick. Combat participants are put in
            # this set by ensure_animal_visible before they are told about
            # the fight, so a staggered view refresh cannot lose a command.
            recipients = tuple(self.animal_viewers.get(actor_id, ()))
        else:
            recipients = [session for session in self.sessions
                          if session.character is not None
                          and session.character.map_id == map_id]
            # And the clients watching this actor across a land seam.
            for viewer in tuple(self.adjacent_viewer_table().get(actor_id, ())):
                if viewer not in recipients:
                    recipients.append(viewer)
        for session in recipients:
            if session.character is not None:
                await self.deliver(session, data)

    async def broadcast_map(self, map_id: str, data: bytes):
        for session in list(self.sessions):
            if session.character and session.character.map_id == map_id:
                await self.deliver(session, data)

    def coordinate_packet(self, session, map_id, build, *, handle=None, named=False):
        return map_packet(session, getattr(self, "coordinate_catalog", None), map_id,
                          build, handle=handle, named=named,
                          collision_maps=getattr(self, 'collision_maps', None))

    def tutorial_state_packet(self, session, state, *, source_map=None):
        from .coordinate_json import tutorial_packet
        return tutorial_packet(self, session, state, source_map=source_map)

    def magic_options_packet(self, session, state):
        from .coordinate_json import recall_packet
        return recall_packet(self, session, state)

    async def broadcast_coordinates(self, map_id, build, *, excluding=None, source_current=None):
        # Build before yielding so a delayed fanout retains each viewer's epoch.
        frames = [(session, self.coordinate_packet(session, map_id, build))
                  for session in list(self.sessions)
                  if session is not excluding and session.character and session.character.map_id == map_id]
        for session, frame in frames:
            if source_current is not None and not source_current():
                return
            await self.deliver(session, frame)

    async def broadcast_player_actor(self, character, *, remove_first=False):
        frames = []
        for viewer in list(self.sessions):
            if viewer.character and viewer.character.map_id == character.map_id:
                frame = self.player_actor_packet(viewer, character)
                if remove_first and frame is not None:
                    prefix = p.packet(p.REMOVE_ACTOR, struct.pack("<H", character.actor_id))
                    frame = (CoordinateFrame(frame.token, prefix + frame.data)
                             if isinstance(frame, CoordinateFrame) else prefix + frame)
                frames.append((viewer, frame))
        for viewer, frame in frames:
            await self.deliver(viewer, frame)

    async def send_map_marker(self, session, marker_id, x, y, map_name, text):
        map_id = next((key for key, definition in self.maps.items()
                       if map_name in (key, definition.client_name)), None)
        if map_id is None:
            map_id = self.resolve_map(map_name)
        if map_id is None and session.coordinate_state is not None:
            raise ValueError("unknown marker map")
        frame = self.coordinate_packet(session, map_id or map_name,
            lambda point: p.map_marker(marker_id, *point(x, y), map_name, text), named=True)
        if frame is None:
            await session.send(p.raw_text("This destination needs a client with map storage coordinate support."))
        else:
            await session.send(frame)

    def bags_packet(self, session, map_id):
        def build(point):
            rows = [struct.pack("<HHB", *point(x, y), self.bag_wire_id(bag_id))
                    for bag_id, (x, y, _) in self.bags.items()
                    if self.bag_maps.get(bag_id, "") == map_id]
            return p.packet(p.GET_BAGS_LIST, bytes((len(rows),)) + b"".join(rows))
        return self.coordinate_packet(session, map_id, build)

    async def send_party_rows(self, session, rows, **options):
        rows = tuple(rows)
        def build(point):
            converted = []
            for row in rows:
                map_id, x, y = row[7:10]
                # Empty-map offline/invitation rows carry clearing sentinels.
                if map_id:
                    x, y = point(map_id, x, y)
                elif session.coordinate_state is not None and (x, y) != (0, 0):
                    raise ValueError("empty party map requires zero location sentinel")
                converted.append((*row[:8], x, y))
            return p.party_state(converted, **options)
        frame = named_rows_packet(session, getattr(self, "coordinate_catalog", None),
                                  [row[7] for row in rows if row[7]], build,
                                  collision_maps=getattr(self, 'collision_maps', None))
        if frame is None:
            await session.send(p.raw_text("Party location display needs map storage coordinate support."))
        else:
            await session.send(frame)

    def record_actor_move(self, actor_id: int, now: float | None = None) -> None:
        """Track recent movement pressure for resync diagnostics."""
        timestamp = time.monotonic() if now is None else now
        events = self.actor_move_events[actor_id]
        events.append(timestamp)
        cutoff = timestamp - 2.0
        while events and events[0] < cutoff:
            events.popleft()

    def recent_movement_diagnostics(self, map_id: str, x: int, y: int) -> str:
        """Summarize nearby actor commands issued during the preceding second."""
        now = time.monotonic()
        cutoff = now - 1.0
        nearby = [
            animal for animal in self.animals.values()
            if animal.alive and animal.map_id == map_id
            and max(abs(animal.x - x), abs(animal.y - y)) <= 50
        ]
        summon_moves = invasion_moves = other_moves = peak = 0
        for animal in nearby:
            events = self.actor_move_events.get(animal.actor_id)
            count = sum(timestamp >= cutoff for timestamp in events) if events else 0
            peak = max(peak, count)
            if animal.summoned:
                summon_moves += count
            elif animal.invasion:
                invasion_moves += count
            else:
                other_moves += count
        return (
            f"nearby={len(nearby)} moves_1s="
            f"summons:{summon_moves},invasions:{invasion_moves},"
            f"other:{other_moves},peak_actor:{peak}"
        )

    def creature_visibility_distance(self, session: Session) -> int:
        """Return the light/perception-limited creature view radius in tiles."""
        c = session.character
        if not c:
            return 0
        # One six-hour EL clock cycle represents a full day. Minute 180 is the
        # brightest point; minute 0 is the darkest.
        daylight = (1.0 - math.cos(2.0 * math.pi * self.game_minute / 360.0)) / 2.0
        low = self.settings.creature_visibility_night
        high = self.settings.creature_visibility_day
        light_radius = low + round((high - low) * daylight)
        perception = max(0, c.attributes["perception"])
        return min(high, light_radius + perception)

    async def sync_visible_animals(self, session: Session,
                                   moved: dict[int, int] | None = None,
                                   *, refresh: bool = True):
        """Reconcile one client's creature list, then forward movement.

        `refresh` recomputes which creatures are in view. The AI loop staggers
        that across ticks because entering and leaving view a fraction of a
        second late is invisible to a player, whereas recomputing every
        player's whole view twenty times a second is not affordable at scale.
        Movement for creatures already on screen is forwarded every tick.
        """
        c = session.character
        if not c:
            return
        if not refresh:
            if moved:
                commands = movement_for(session.visible_animals, moved)
                if commands:
                    await session.send(p.actor_commands(commands))
            return
        radius = self.creature_visibility_distance(session)
        cells = self.creature_index(c.map_id)
        desired: set[int] = set()
        if cells:
            reach = radius + INDEX_SLACK_TILES
            px, py = c.x, c.y
            for cell_x in range((px - reach) >> INDEX_CELL_BITS,
                                ((px + reach) >> INDEX_CELL_BITS) + 1):
                for cell_y in range((py - reach) >> INDEX_CELL_BITS,
                                    ((py + reach) >> INDEX_CELL_BITS) + 1):
                    bucket = cells.get((cell_x, cell_y))
                    if not bucket:
                        continue
                    for animal in bucket:
                        if (animal.alive
                                and abs(animal.x - px) <= radius
                                and abs(animal.y - py) <= radius):
                            desired.add(animal.actor_id)
        visible = session.visible_animals
        previous = frozenset(visible)
        removed = previous - desired
        # The tracked set is committed around each send rather than assigned at
        # the end. move() runs as session.move_task and is cancelled whenever a
        # player clicks a new destination or attacks, so a sync can stop at any
        # await with packets already on the wire. Keeping the set a superset of
        # what the client holds means a lost update only costs a redundant
        # removal later; the reverse leaves actors the server can never remove.
        if removed:
            payload = b"".join(struct.pack("<H", actor_id) for actor_id in sorted(removed))
            await session.send(p.packet(p.REMOVE_ACTOR, payload))
            visible.difference_update(removed)
            self.drop_animal_viewer(session, removed)
        added: list[bytes] = []
        for actor_id in sorted(desired - previous):
            animal = self.animals.get(actor_id)
            if animal and animal.alive:
                visible.add(actor_id)
                self.animal_viewers[actor_id].add(session)
                added.append(self.creature_actor_packet(session, animal))
                if animal.summoned:
                    added.append(p.actor_health(
                        animal.actor_id, animal.max_health))
        await session.send_many(added)
        if moved:
            commands = movement_for(desired & previous, moved)
            if commands:
                await session.send(p.actor_commands(commands))
        await self.sync_visible_adjacent(session)

    async def sync_visible_npcs(self, session: Session):
        # NPCs replicate map-wide, not within the perception/light radius that
        # gates creatures. They stand at fixed posts, and the client draws its
        # map and minimap dots from replicated actors, so a radius here made
        # every service NPC vanish from the maps the moment a player walked
        # away. Talking range is enforced in touch_actor() instead.
        c = session.character
        if not c:
            return
        desired = {actor_id for actor_id, (npc, map_id, _, _) in self.npcs.items()
                   if map_id == c.map_id}
        visible = session.visible_npcs
        previous = frozenset(visible)
        removed = previous - desired
        # Committed around each send for the same reason as the animal sync.
        if removed:
            payload = b"".join(struct.pack("<H", actor_id) for actor_id in sorted(removed))
            await session.send(p.packet(p.REMOVE_ACTOR, payload))
            visible.difference_update(removed)
        added: list[bytes] = []
        for actor_id in sorted(desired - previous):
            npc = self.npcs[actor_id][0]
            visible.add(actor_id)
            added.append(self.npc_actor_packet(npc, recipient=session, map_id=self.npcs[actor_id][1]))
        await session.send_many(added)

    async def send_stats(self, session: Session, *, force: bool = False):
        """Publish XP/level changes without flooding a surrounded player."""
        now = time.monotonic()
        if force or now - session.last_stats_sent >= 0.5:
            await session.send(stats_packet(session.character))
            session.last_stats_sent = now

    def player_step_seconds(self, c: Character,
                            session: Session | None = None) -> float:
        """How long one tile takes at this character's chosen pace.

        Speed Hax and Swiftwend do the same thing to a step and do not stack:
        one is a draught that costs food and switches off when the character is
        hungry, the other is a spell that costs ether and reagents and runs out
        on its own. The haste lives on the session because that is where every
        magic buff lives, so it is asked for only when the caller has one.
        """
        interval = (self.settings.player_run_interval_ms if c.running
                    else self.settings.player_move_interval_ms) / 1000.0
        hastened = c.speed_hax_active or (
            session is not None and self.has_buff(session, BUFF_HASTE))
        return interval / 2 if hastened else interval

    async def await_player_step(self, session: Session | None,
                                c: Character, dx: int = 1, dy: int = 0) -> None:
        """Hold a route until this character's next step is due.

        Sleeping for the interval after each step instead added it to whatever
        the step itself cost - the broadcast, the visibility syncs, the portal
        check - so the cadence was the pace plus a variable tail. The client
        paces its walk from the cadence it measures, so a tail it could not
        predict left the rendered actor further behind its own tile with every
        step, walking slowly and facing the chord back to where it had been
        rather than the way it was going.

        The pace names how long a *tile* takes, so the step being taken is
        held for as far as it actually travels: a diagonal crosses a tile
        corner to corner, 1.41 tiles, and waits that much longer than a
        straight one. Handing both shapes the same interval walked a diagonal
        41% faster over the ground - and a click-path that is not one of the
        eight tile directions is walked as a zigzag of the two, so the player
        sped up and slowed down on every step of it. The pace the settings
        name is now the pace in all eight directions.

        The deadline is absolute and never catches up: a player who has been
        standing still steps at once, and one who is already walking waits out
        the remainder however the last step was interrupted.
        """
        interval = self.player_step_seconds(c, session) * math.hypot(dx, dy)
        now = time.monotonic()
        due = max(session.next_step_at, now) if session else now
        if due > now:
            await asyncio.sleep(due - now)
        if session:
            session.next_step_at = due + interval

    async def set_running(self, session: Session, running: bool) -> None:
        """#run and #walk. The next step is broadcast at the new pace.

        A route already in flight keeps stepping; it reads the flag each tile,
        so the change takes effect where the player is rather than at the end
        of wherever they were going.
        """
        c = session.character
        if not c:
            return
        if c.running == running:
            await session.send(p.colored_text(
                "You are already running." if running else "You are already walking.",
                p.EL_COLOR_GREEN2))
            return
        c.running = running
        self.save_soon(c)
        # The lighter action green, shared with the harvest start/stop lines.
        await session.send(p.colored_text(
            "You break into a run." if running else "You slow to a walk.",
            p.EL_COLOR_GREEN2))

    async def disable_speed_hax(self, session: Session, *, notify: bool = True) -> bool:
        c = session.character
        if not c or not c.speed_hax_active or session.demigod:
            return False
        c.speed_hax_active = False
        await self.broadcast_map(c.map_id, p.actor_buffs(c.actor_id, 0))
        if notify:
            await session.send(p.raw_text("You are too hungry to continue using Speed Hax."))
        return True

    async def expire_buffs(self) -> int:
        """Tell each player when one of their effects has run out.

        `has_buff` drops an expired effect the next time something asks about
        it, so the server's own view is already correct - but nothing told the
        client, which left it either showing an effect that had ended or
        deciding on its own that it had. Returns how many were announced.
        """
        self.expire_magic_modifiers()
        announced = 0
        now = time.monotonic()
        for session in list(self.sessions):
            for buff_id, expires in list(session.magic_buffs.items()):
                if expires > now:
                    continue
                session.magic_buffs.pop(buff_id, None)
                session.magic_buff_powers.pop(buff_id, None)
                if (buff_id == BUFF_HASTE and session.character
                        and not session.character.speed_hax_active):
                    # The client chooses its running frames from the actor
                    # buff, so a haste that ended without clearing it left
                    # everyone watching a walker sprinting on the spot.
                    await self.broadcast_map(
                        session.character.map_id,
                        p.actor_buffs(session.character.actor_id, 0))
                try:
                    await session.send(p.remove_active_spell(buff_id))
                except (ConnectionError, OSError):
                    continue
                announced += 1
        return announced

    def save_soon(self, character: Character) -> None:
        """Persist a character without paying for a commit on the hot path.

        Used by the paths that run continuously - movement, combat rounds,
        ranging, harvesting, mixing, spells and the per-minute upkeep. Anything
        that moves items or money between owners still saves immediately.
        """
        deferred = getattr(self.db, "save_deferred", None)
        if deferred is None:
            self.db.save(character)
            return
        deferred(character)

    def flush_saves(self) -> int:
        """Commit whatever save_soon has accumulated."""
        flush = getattr(self.db, "flush", None)
        return flush() if flush is not None else 0

    async def flush_sessions(self) -> int:
        """Write every session's queued packets. Returns how many were written."""
        written = 0
        for session in list(self.sessions):
            if not session.outbox:
                continue
            try:
                await session.flush()
                written += 1
            except (ConnectionError, asyncio.CancelledError, OSError):
                session.outbox.clear()
        return written

    async def outbox_flush_loop(self, interval: float | None = None) -> None:
        """Drain queued packets on the AI tick's cadence.

        The AI loop flushes the sessions it touched, but a player whose map saw
        no creature movement still has chat, combat and spell packets waiting,
        so nothing may sit in an outbox longer than one tick.
        """
        if interval is None:
            interval = self.settings.invasion_ai_tick_ms / 1000.0
        self._flush_drivers += 1
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.flush_sessions()
                except Exception:
                    log.exception("session outbox flush failed")
        finally:
            self._flush_drivers -= 1
            await self.flush_sessions()

    async def save_flush_loop(self, interval: float = 1.0) -> None:
        """Commit deferred character writes on a fixed cadence."""
        while True:
            await asyncio.sleep(interval)
            try:
                self.flush_saves()
            except Exception:
                log.exception("deferred character flush failed")

    async def buff_expiry_loop(self, interval: float = 2.0) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.expire_buffs()

    @staticmethod
    def has_buff(session: Session, buff_id: int) -> bool:
        expires = session.magic_buffs.get(buff_id, 0.0)
        if expires <= time.monotonic():
            session.magic_buffs.pop(buff_id, None)
            session.magic_buff_powers.pop(buff_id, None)
            return False
        return True

    @classmethod
    def buff_power(cls, session: Session, buff_id: int) -> int:
        return (max(1, int(session.magic_buff_powers.get(buff_id, 1)))
                if cls.has_buff(session, buff_id) else 0)

    async def announce_levels(self, session: Session, level_ups):
        base_stat_ids = {"manufacturing":25, "harvesting":27, "alchemy":29,
                         "overall":31, "attack":33, "defense":35, "magic":37,
                         "potion":39, "summoning":70, "crafting":74,
                         "engineering":78, "ranging":82, "tailoring":86}
        skill_advanced = False
        overall_advanced = False
        for skill, _, level in level_ups:
            if skill in base_stat_ids:
                # The stock client turns base-level partial stats into its blue
                # overhead notification and optional level-up eye candy.
                await session.send(p.partial_stats([(base_stat_ids[skill], level)]))
                skill_advanced = True
            await session.send(p.colored_text(
                f"You advanced to level {level} of {skill.title()}!", 10))
            overall_advanced = overall_advanced or skill == "overall"
            if skill == "magic":
                # A Magic level raises what powers are reachable, and the
                # client is told rather than deriving it from a levels table.
                await self.send_spell_power_state(session)
        if skill_advanced and session.character:
            # Base-level notifications do not update current HUD levels,
            # next-level XP, or overall's spent/earned pickpoint pair.
            # Refresh once per batch, even when overall did not advance.
            await session.send(stats_packet(session.character))
        if overall_advanced and session.character:
            # An overall level is new pick points, so perks that were out of
            # reach may not be any more. The catalogue carries the refusals,
            # so it is restated rather than left for the client to recompute.
            await self.send_perk_catalog(session)
            await landing_runtime.tip(self, session, "first_level")
            await self.send_attribute_state(session)
        if level_ups:
            # Skill milestones are levels rather than counts, so this is the
            # only moment they can move.
            await self.award_achievements(session)

    async def send_combat_xp(self, session: Session, *, attack: bool = False,
                             defense: bool = False):
        c = session.character
        entries = [(55, c.experience["overall"])]
        if attack:
            entries.append((59, c.experience["attack"]))
        if defense:
            entries.append((57, c.experience["defense"]))
        await session.send(p.partial_stats(entries))

    def summon_allies(self, owner_username: str) -> frozenset[str]:
        """The usernames a summon of this owner treats as its own side.

        A summon inherits its summoner's party, so the party is the answer -
        the owner included, which also keeps a summon off its own summoner
        when they are in a PK zone together.
        """
        book = self.parties
        if book is None or not owner_username:
            return frozenset()
        party = book.party_of(owner_username)
        names = party.names() if party is not None else [owner_username]
        return frozenset(str(name).strip().casefold() for name in names)

    @staticmethod
    def summon_target_allied(allies: frozenset[str], target) -> bool:
        """Whether one candidate belongs to the summoner's side.

        A creature answers for the player who summoned it and a player for
        themselves, so both are reduced to the username the party is keyed by.
        Wildlife has neither and is never an ally; livestock is everybody's.
        """
        if livestock.is_tame(target):
            return True
        if not allies:
            return False
        owner = str(getattr(target, "owner_username", "")
                    or getattr(target, "username", "")).strip().casefold()
        return bool(owner) and owner in allies

    # ------------------------------------------------------------------
    # Actors across land seams.
    #
    # A client that advertised ADJACENT_ACTORS_CAPABILITY is told about the
    # creatures, NPCs and players on the maps adjoining its own across a
    # seamless land crossing, within the perception radius that gates the
    # creatures of its own map, so that a seam shows no actor appearing or
    # vanishing as it is crossed. Their packets carry the neighbour's handle
    # in the stock "z" field; ELORIA_ADJACENT_MAPS names the handles per map.
    # Players on the client's own map keep their map-wide replication.

    def adjacent_viewer_table(self) -> dict:
        """actor id -> sessions shown it across a seam; made on first use for worlds built without __init__."""
        table = self.__dict__.get("adjacent_viewers")
        if table is None:
            table = self.adjacent_viewers = defaultdict(set)
        return table

    def adjacent_maps(self, map_id: str) -> list[str]:
        """The land neighbours of a map with continent frames, in handle order."""
        frames = getattr(self, "land_frames", None) or {}
        return sorted(far for near, far in frames if near == map_id)

    def adjacent_handles(self, map_id: str) -> dict[str, int]:
        return {far: handle for handle, far in enumerate(self.adjacent_maps(map_id), 1)}

    def adjacent_actors_enabled(self, session: Session) -> bool:
        return (ADJACENT_ACTORS_CAPABILITY in (getattr(session, "client_capabilities", None) or ())
                and bool(getattr(self, "land_frames", None)))

    async def send_adjacent_maps(self, session: Session) -> None:
        """Name the handles the actor packets of this client's neighbours carry."""
        c = session.character
        if not c:
            return
        if session.coordinate_state is not None:
            await session.send(CoordinateFrame(session.coordinate_token(),
                p.packet(p.ELORIA_COORDINATE_CONTEXT, session.coordinate_state.definition_payload())))
            return
        if not self.adjacent_actors_enabled(session):
            return
        entries = [(handle, self.maps[far].client_name)
                   for far, handle in self.adjacent_handles(c.map_id).items()
                   if far in self.maps and legacy_map_supported(getattr(self, "coordinate_catalog", None), far,
                                                               getattr(self, 'collision_maps', None))]
        await session.send(p.adjacent_maps_packet(entries))

    def actor_map(self, actor_id: int) -> str | None:
        animal = self.animals.get(actor_id)
        if animal is not None:
            return animal.map_id
        npc = self.npcs.get(actor_id)
        if npc is not None:
            return npc[1]
        player = self.find_player_by_actor(actor_id)
        return player.character.map_id if player and player.character else None

    def adjacent_candidates(self, session: Session) -> dict:
        """actor id -> (map, actor) for the neighbours' actors within this viewer's radius."""
        from .exterior_connections import neighbour_tile
        c = session.character
        radius = self.creature_visibility_distance(session)
        found: dict[int, tuple] = {}
        for far in self.adjacent_maps(c.map_id):
            if session.coordinate_state is None and not legacy_map_supported(
                    getattr(self, "coordinate_catalog", None), far,
                    getattr(self, 'collision_maps', None)):
                continue
            frames = self.land_frames[c.map_id, far]
            fx, fy = neighbour_tile(frames, c.x, c.y)
            bounds = frames[1].bounds
            if (fx < bounds.min_x - radius or fy < bounds.min_y - radius
                    or fx >= bounds.max_x + radius or fy >= bounds.max_y + radius):
                continue
            for animal in self.creatures_near(far, fx, fy, radius):
                if animal.alive and abs(animal.x - fx) <= radius and abs(animal.y - fy) <= radius:
                    found[animal.actor_id] = (far, animal)
            for actor_id, (npc, npc_map, _, _) in self.npcs.items():
                if npc_map == far and abs(npc.x - fx) <= radius and abs(npc.y - fy) <= radius:
                    found[actor_id] = (far, npc)
            for other in self.sessions:
                oc = other.character
                if (other is not session and oc and oc.map_id == far
                        and abs(oc.x - fx) <= radius and abs(oc.y - fy) <= radius):
                    found[oc.actor_id] = (far, oc)
        return found

    @staticmethod
    def wire_actor(actor, point):
        wire = copy.copy(actor)
        wire.x, wire.y = point(actor.x, actor.y)
        return wire

    def npc_actor_packet(self, npc, map_handle: int = 0, *, recipient=None, map_id=None):
        def build(point):
            actor = self.wire_actor(npc, point)
            return (p.actor_packet(actor, map_handle=map_handle)
                    if actor.actor_type == 6 or actor.actor_type > 0xFF
                    else p.enhanced_actor_packet(actor, map_handle=map_handle))
        if recipient is None:
            return build(lambda x, y: (x, y))
        if map_id is None:
            raise ValueError("NPC output requires its explicit map")
        return self.coordinate_packet(recipient, map_id, build, handle=map_handle)

    def drop_adjacent_viewer(self, session: Session, actor_id: int) -> None:
        watching = self.adjacent_viewer_table().get(actor_id)
        if watching is None:
            return
        watching.discard(session)
        if not watching:
            del self.adjacent_viewers[actor_id]

    def forget_adjacent(self, session: Session) -> None:
        """Forget every actor this session was shown across a seam."""
        if not getattr(session, "visible_adjacent", None):
            return
        for actor_id in list(session.visible_adjacent):
            self.drop_adjacent_viewer(session, actor_id)
        self.drop_animal_viewer(session, tuple(session.visible_adjacent))
        session.visible_adjacent.clear()

    async def sync_visible_adjacent(self, session: Session) -> None:
        """Reconcile the actors this client sees across the land seams of its map."""
        c = session.character
        if not c or not self.adjacent_actors_enabled(session):
            return
        candidates = self.adjacent_candidates(session)
        visible = session.visible_adjacent
        gone: list[int] = []
        for actor_id, far in list(visible.items()):
            if actor_id in candidates and candidates[actor_id][0] == far:
                continue
            visible.pop(actor_id, None)
            self.drop_adjacent_viewer(session, actor_id)
            if self.actor_map(actor_id) == c.map_id:
                # It walked onto this client's own map: the map-wide path
                # sends it afresh, and a removal here would take that back.
                continue
            gone.append(actor_id)
        if gone:
            await session.send(p.packet(p.REMOVE_ACTOR, b"".join(struct.pack("<H", actor_id) for actor_id in sorted(gone))))
            self.drop_animal_viewer(session, gone)
        handles = self.adjacent_handles(c.map_id)
        added: list[bytes] = []
        for actor_id in sorted(candidates):
            if actor_id in visible or actor_id in session.visible_animals or actor_id in session.visible_npcs:
                continue
            far, actor = candidates[actor_id]
            visible[actor_id] = far
            self.adjacent_viewer_table()[actor_id].add(session)
            handle = handles[far]
            if actor_id in self.animals:
                self.animal_viewers[actor_id].add(session)
                added.append(self.creature_actor_packet(session, actor, map_handle=handle))
                if actor.summoned:
                    added.append(p.actor_health(actor.actor_id, actor.max_health))
            elif actor_id in self.npcs:
                added.append(self.npc_actor_packet(actor, map_handle=handle, recipient=session, map_id=far))
            else:
                added.append(self.player_actor_packet(session, actor, map_handle=handle))
        await session.send_many(added)

    async def forward_adjacent_movement(self, session: Session, movement_commands: dict) -> None:
        """Send this tick's steps of the neighbours' creatures the client watches."""
        moved: dict[int, int] = {}
        for actor_id, far in session.visible_adjacent.items():
            commands = movement_commands.get(far)
            if commands:
                command = commands.get(actor_id)
                if command is not None:
                    moved[actor_id] = command
        if moved:
            await session.send(p.actor_commands(sorted(moved.items())))

    def carry_actors_across(self, session: Session, old_map: str, map_id: str) -> set[int]:
        """Re-file a client's actor sets for a land crossing it renders seamlessly.

        The actors it already shows on the map it arrives on become its own,
        those on the map it leaves become its neighbours, and the syncs that
        follow send only the difference. Returns the players it already
        holds that now stand on its own map, which need no fresh packet.
        """
        visible = session.visible_adjacent
        own_creatures = {a for a, m in visible.items() if m == map_id and a in self.animals}
        own_npcs = {a for a, m in visible.items() if m == map_id and a in self.npcs}
        carried_players = {a for a, m in visible.items()
                           if m == map_id and a not in self.animals and a not in self.npcs}
        adjacent = {a: m for a, m in visible.items() if m != map_id}
        for actor_id in list(visible):
            self.drop_adjacent_viewer(session, actor_id)
        for actor_id in session.visible_animals:
            adjacent[actor_id] = old_map
        for actor_id in session.visible_npcs:
            adjacent[actor_id] = old_map
        for other in self.sessions:
            oc = other.character
            if other is not session and oc and oc.map_id == old_map:
                adjacent[oc.actor_id] = old_map
        session.visible_animals = own_creatures
        session.visible_npcs = own_npcs
        session.visible_adjacent = adjacent
        for actor_id in adjacent:
            self.adjacent_viewer_table()[actor_id].add(session)
        return carried_players

    async def remove_creature_from_clients(self, animal: Animal) -> None:
        """Take a creature off every client showing it, on its own map or across a seam."""
        removal = p.packet(p.REMOVE_ACTOR, struct.pack("<H", animal.actor_id))
        for session in self.sessions:
            if animal.actor_id in session.visible_animals:
                await session.send(removal)
                session.visible_animals.discard(animal.actor_id)
                self.drop_animal_viewer(session, (animal.actor_id,))
            elif animal.actor_id in (getattr(session, "visible_adjacent", None) or {}):
                await session.send(removal)
                session.visible_adjacent.pop(animal.actor_id, None)
                self.drop_adjacent_viewer(session, animal.actor_id)
                self.drop_animal_viewer(session, (animal.actor_id,))

    def creature_actor_packet(self, recipient: Session, animal: Animal, map_handle: int = 0) -> bytes:
        """One creature as this viewer should see it.

        Only a summon carries a guild tag, and its colour is the viewer's
        guild's opinion of the owner's guild - the same per-viewer choice
        `player_actor_packet` makes about a player's tag, so a summon is
        coloured on a field exactly as the summoner standing beside it is.
        """
        color = None
        if animal.guild_tag and self.guild_tag_color_for and recipient.character:
            owner = self.find_player_by_actor(animal.owner_id)
            if owner and owner.character:
                color = self.guild_tag_color_for(recipient.character, owner.character)
        return self.coordinate_packet(recipient, animal.map_id,
            lambda point: p.actor_packet(self.wire_actor(animal, point), guild_tag_color=color,
                                          map_handle=map_handle), handle=map_handle)

    def player_actor_packet(self, recipient: Session, character: Character, map_handle: int = 0) -> bytes:
        color = None
        if self.guild_tag_color_for and recipient.character:
            color = self.guild_tag_color_for(recipient.character, character)
        raid_enemy = bool(
            recipient.character
            and self.territory_raids.opponents(
                recipient.character.username, character.username))
        actor_type = (p.PKABLE_HUMAN
                      if raid_enemy or pk_zone_at(
                          character.map_id, character.x, character.y)
                      else character.actor_type)
        return self.coordinate_packet(recipient, character.map_id,
            lambda point: p.enhanced_actor_packet(
                self.wire_actor(character, point), guild_tag_color=color, actor_type=actor_type,
                wardrobe="actor_wardrobe_v1" in recipient.client_capabilities,
                map_handle=map_handle), handle=map_handle)

    async def refresh_player_view(self, session: Session) -> None:
        """Refresh player names using this recipient's guild-color preferences."""
        character = session.character
        if not character:
            return
        for visible in list(self.sessions):
            target = visible.character
            if target and target.map_id == character.map_id:
                await session.send(p.packet(p.REMOVE_ACTOR, struct.pack("<H", target.actor_id)))
                await session.send(self.player_actor_packet(session, target))

    async def enter(self, session: Session, character: Character):
        self.require_coordinate_login(session, character)
        session.character = character
        if session.coordinate_state is None:
            self.sessions.add(session)
        character = await sky.login(self, session, character)
        from .creature_retirements import migrate_progress
        migrate_progress(character, self.creatures)
        lantern.prepare(self, character)
        await bell.prepare(self, character)
        self.reconcile_research(character)
        # No session: #clientcaps follows LOG_IN_OK, so the client has not
        # said what it draws yet. The home's own beam; the #clientcaps gate
        # moves a client that cannot draw it.
        destination = ((character.map_id, character.x, character.y)
                       if character.map_id in self.maps
                       else home.point(self, "beam"))
        map_id, x, y = destination
        x, y = self.free_player_tile(map_id, x, y, exclude=character)
        self.require_coordinate_destination(session, map_id, x, y)
        await session.send(p.packet(p.LOG_IN_OK))
        if session.coordinate_state is not None:
            def commit_login():
                character.map_id, character.x, character.y = map_id, x, y
                self.sessions.add(session)
            await session.activate_coordinates(map_id, self.maps[map_id].client_name,
                                              self.coordinate_handles(session, map_id),
                                              commit=commit_login)
        else:
            character.map_id, character.x, character.y = map_id, x, y
            await session.send(p.packet(p.CHANGE_MAP, self.maps[map_id].client_name.encode() + b"\0"))
        await session.send(stats_packet(character))
        await self.send_knowledge_list(session)
        session.inventory_slots = self.sync_inventory_slots(character)
        await session.send(p.inventory_packet(character.inventory, ITEMS, character.equipment,
                                              character.inventory_slots))
        await session.send(p.sync_clock(int(time.monotonic() * 1000)))
        await session.send(p.new_minute(self.game_minute))
        await session.send(p.packet(p.YOU_ARE, struct.pack("<H", character.actor_id)))
        await self.send_adjacent_maps(session)
        for other in self.sessions:
            if (other is not session and other.character
                    and other.character.map_id == character.map_id):
                await session.send(self.player_actor_packet(session, other.character))
        await self.sync_visible_animals(session)
        await self.sync_visible_npcs(session)
        await session.send(p.sigils(character.sigils))
        await self.send_map_objects(session)
        await self.send_perks(session)
        await self.send_perk_catalog(session)
        await self.send_attribute_state(session)
        await self.send_activity_counters(session)
        await self.send_counter_layout(session)
        await self.send_mix_state(session)
        await self.send_spell_power_state(session)
        await self.send_almanac_state(session)
        await self.send_map_music(session)
        await self.send_weather(session)
        await self.send_fires(session)
        await self.send_buddy_list(session)
        await self.send_teleporters(session)
        await self.send_world_objects(session)
        # Anyone watching for this character is told they are here.
        await self.announce_buddy_presence(character, True)
        if self.bags:
            await session.send(self.bags_packet(session, character.map_id))
        await session.send(self.player_actor_packet(session, character))
        for other in self.sessions:
            if (other is not session and other.character
                    and other.character.map_id == character.map_id):
                await other.send(self.player_actor_packet(other, character))
        if character.speed_hax_active:
            await self.broadcast_map(character.map_id,
                                     p.actor_buffs(character.actor_id, BUFF_DOUBLE_SPEED))
        await session.send(p.raw_text("A ferry is grounded. Nesh's lantern is waiting on the shore."
                                     if lantern.on_island(character) else
                                     "Welcome to Eloria. Walk near an animal and click it to attack."))
        # The map this character is standing on counts as visited, and several
        # of the catalogue's requirements are facts rather than counts - guild,
        # party, gold, quests - which nothing increments and so nothing else
        # would ever prompt a look at.
        if self.mark_map_visit(character, character.map_id):
            self.db.save(character)
        await self.award_achievements(session)
        await self.send_actor_titles(session)
        if character.title:
            await self.broadcast_title(character)
        await self.sync_tutorial_markers(session)
        if not await self.offer_walkthrough(session):
            await self.resume_walkthrough(session)
        if lantern.active(character):
            await lantern.event(self, session, "state")
            await lantern.sync(self, session)

        if sky.on_map(character):
            # Map/login packets clear the native actor table. Preparing the
            # resumed lesson before those packets would mark its creatures as
            # already visible, preventing them from being sent after login.
            if getattr(character, "_sky_resume_pending", False):
                character._sky_resume_pending = False
                await sky.setup(self, session, resume=True)
            await sky.sync(self, session)
        if bell.on_map(character):
            await bell.ensure_phase(self, session)
            await bell.event(self, session, "state")
            await bell.sync(self, session)
        await landing_runtime.login(self, session)
        await watchpost.login(self, session)

    async def resync_actors(self, session: Session) -> None:
        """Rebuild the actor list after the stock client requests a resync."""
        c = session.character
        if not c:
            return
        if session.coordinate_state is not None:
            await self.send_adjacent_maps(session)
        self.drop_animal_viewer(session, tuple(session.visible_animals))
        session.visible_animals.clear()
        session.visible_npcs.clear()
        self.forget_adjacent(session)
        await session.send(self.player_actor_packet(session, c))
        for other in self.sessions:
            if (other is not session and other.character
                    and other.character.map_id == c.map_id):
                await session.send(self.player_actor_packet(session, other.character))
        await self.sync_visible_animals(session)
        await self.sync_visible_npcs(session)
        if c.speed_hax_active:
            await session.send(p.actor_buffs(c.actor_id, BUFF_DOUBLE_SPEED))
        if player_in_combat(session):
            combat_ids = set(session.aggressors)
            if session.combat_target is not None:
                combat_ids.add(session.combat_target)
            commands = [(c.actor_id, p.CMD_ENTER_COMBAT)]
            commands.extend((actor_id, p.CMD_ENTER_COMBAT) for actor_id in combat_ids
                            if actor_id in self.animals and self.animals[actor_id].alive)
            await session.send(p.actor_commands(commands))

    async def leave(self, session: Session):
        self.stop_ranging(session)
        await self.cancel_trade(session, notify_partner=True)
        self.sessions.discard(session)
        if session.move_task and not session.move_task.done():
            session.move_task.cancel()
        if session.harvest_task and not session.harvest_task.done():
            session.harvest_task.cancel()
        self.stop_poison(session)
        self.drop_animal_viewer(session, tuple(session.visible_animals))
        session.visible_animals.clear()
        if session.character:
            # A logout is a durability boundary: commit this character and
            # anything else the deferred writer is still holding.
            self.clear_actor_magic(session.character)
            sky.checkpoint(self, session.character)
            bell.checkpoint(self, session.character)
            self.db.save(session.character)
            self.release_id(session.character.actor_id)
            await self.broadcast(p.packet(p.REMOVE_ACTOR, struct.pack("<H", session.character.actor_id)))
            # The session is already out of the set, so this reaches everyone
            # still watching and not the person leaving.
            await self.announce_buddy_presence(session.character, False)
            lantern.cleanup(self, session.character)
            bell.cleanup(self, session.character)
            sky.cleanup(self, session.character)

    async def set_sitting(self, session: Session, sitting: bool) -> None:
        c = session.character
        if not c or session.sitting == sitting:
            return
        if sitting:
            if session.move_task and session.move_task is not asyncio.current_task() \
                    and not session.move_task.done():
                session.move_task.cancel()
        session.sitting = sitting
        await self.broadcast_map(c.map_id, p.actor_command(
            c.actor_id, p.CMD_SIT_DOWN if sitting else p.CMD_STAND_UP))

    async def show_player_achievements(self, session: Session, actor_id: int) -> None:
        target = next((candidate.character for candidate in self.sessions
                       if candidate.character and candidate.character.actor_id == actor_id), None)
        if not target or not session.character or target.map_id != session.character.map_id:
            return
        if "player_info_v1" in session.client_capabilities:
            # Names the player and states what they have earned, so the client
            # neither pairs a reply with its own outstanding request nor keeps
            # a second copy of the achievement catalog.
            #
            # Catalogue achievements are stored by key - `keeper_of_secrets` -
            # so they are put back through the catalogue for their names here;
            # a quest title, which has always lived in the same set, comes back
            # unchanged. The worn title is appended only for a client that
            # asked for titles, so an older one reads the frame it always did.
            named = sorted(self.achievement_catalogue.display_name(name)
                           for name in target.achievements)
            await session.send(p.player_info(
                target.actor_id, target.name, named,
                title=target.title
                if "actor_titles_v1" in session.client_capabilities else None))
            return
        await session.send(p.raw_text(f"You see: {target.name}"))
        native_ids = {0} if "Beginner Tutorial" in target.achievements else set()
        await session.send(p.achievements_packet(native_ids))

    async def send_spell_power_state(self, session: Session) -> None:
        """State what power each effect will be cast at, and what it may reach.

        The `#sp` command reports both as chat text, which is unreadable to a
        client that must not parse the chat stream. Both numbers come from the
        character's Magic level, nexus and stored preference, so both are
        stated here instead.
        """
        c = session.character
        if not c or "spell_power_v1" not in session.client_capabilities:
            return
        preferences = spell_power_preferences(c)
        entries = []
        for effect in sorted(STANDARD_SPELLS):
            limit = available_spell_power(c, effect)
            if limit < 1:
                continue
            entries.append((effect, preferences.get(effect, 1), limit))
        await session.send(p.spell_power_state(entries))

    async def send_almanac_state(self, session: Session) -> None:
        """State the date and the day in force, rather than only saying them.

        Both were chat lines: `GET_DATE` answered with one and a special day
        was announced with another. A client that wanted to show either had to
        read the chat stream, which it must not do. The catalogue of days
        travels with them because which days exist and what they do is the
        server's to decide - a copy shipped in the client is a second source
        of truth that goes stale without anyone noticing.
        """
        if "almanac_v1" not in session.client_capabilities:
            return
        await session.send(p.almanac_state(
            self.elder_date, self.special_day, self.special_day_xp_bonus,
            ALL_SPECIAL_DAYS))

    async def broadcast_almanac_state(self) -> None:
        # `sessions` is absent on the stripped-down worlds some suites build,
        # and a day changing with nobody connected is not an error.
        for session in list(getattr(self, "sessions", ())):
            if session.character:
                try:
                    await self.send_almanac_state(session)
                except (ConnectionError, asyncio.CancelledError):
                    pass

    @staticmethod
    def stray_arrow_tile(shooter, target, bounds=None) -> tuple[int, int]:
        """Where a missed arrow lands: past the target, off to one side.

        It is deliberately a function of the two positions rather than a fresh
        random tile each time, so what every client draws is what the server
        decided and two clients watching the same shot see the same thing.
        """
        step_x = (target.x - shooter.x)
        step_y = (target.y - shooter.y)
        drift = 1 if (target.x + target.y) % 2 else -1
        x = target.x + (1 if step_x > 0 else -1 if step_x < 0 else drift)
        y = target.y + (1 if step_y > 0 else -1 if step_y < 0 else drift)
        if bounds is not None:
            return (max(bounds.min_x, min(bounds.max_x - 1, x)),
                    max(bounds.min_y, min(bounds.max_y - 1, y)))
        return max(0, x), max(0, y)

    @staticmethod
    def location_context_current(session, map_id, token):
        return (session.character is not None and session.character.map_id == map_id
                and (token is None or session.coordinate_token_current(token)))

    async def fire_at_ground(self, session: Session, x: int, y: int) -> None:
        """Loose an arrow at a place instead of at somebody.

        A practice shot: it costs the arrow, which lands where it was aimed and
        can be picked up again, and it grants nothing. Ranging experience comes
        from hitting something that can be hit.
        """
        c = session.character
        if not c:
            return
        source_map = c.map_id
        token = session.coordinate_token() if session.coordinate_state is not None else None
        if token is not None:
            session.coordinate_state.catalog.profile(source_map).to_wire(x, y)
        loadout = equipped_ranging_items(c)
        if not loadout:
            await session.send(p.raw_text(
                "Equip a bow and ammunition before shooting at anything."))
            return
        weapon_name, ammunition_name = loadout
        distance = max(abs(c.x - x), abs(c.y - y))
        if distance < MIN_RANGING_DISTANCE:
            await session.send(p.raw_text(
                "That is too close to range; aim at least four spaces away."))
            return
        await self.broadcast_coordinates(source_map,
            lambda point: p.missile_aim_at_ground(c.actor_id, *point(x, y)))
        await asyncio.sleep(0.25)
        if not self.location_context_current(session, source_map, token):
            return
        await self.broadcast_coordinates(source_map,
            lambda point: p.missile_fire_at_ground(c.actor_id, *point(x, y)))
        if not self.location_context_current(session, source_map, token):
            return
        await self.consume_ranging_ammunition(
            session, weapon_name, ammunition_name)
        if self.location_context_current(session, source_map, token):
            await self.drop_into_bag(x, y, [(ammunition_name, 1)], source_map)

    def weather_on(self, map_id: str) -> tuple[int, int]:
        """The sky over a map as (kind, intensity). Clear until rolled."""
        return self.weather.get(map_id, (CLEAR, 0))

    async def send_weather(self, session: Session) -> None:
        """State the sky, and start the rain for a client that only knows the
        legacy signal."""
        c = session.character
        if not c:
            return
        kind, intensity = self.weather_on(c.map_id)
        await session.send(p.send_weather(kind, intensity))
        if kind == CLEAR:
            await session.send(p.stop_rain())
        else:
            await session.send(p.start_rain(intensity))

    async def send_fires(self, session: Session) -> None:
        """Every fire burning on the map the character is standing on."""
        c = session.character
        if not c:
            return
        map_id = c.map_id
        frames = [self.coordinate_packet(session, map_id,
                    lambda point: p.fire_particles(*point(fire.x, fire.y), fire.kind))
                  for fire in self.fires if fire.map_id == map_id]
        await session.send_many(frames)

    async def remove_fire_at(self, map_id: str, x: int, y: int) -> None:
        await self.broadcast_coordinates(map_id, lambda point: p.remove_fire_at(*point(x, y)))

    async def set_weather(self, map_id: str, kind: int, intensity: int) -> None:
        """Change the sky over one map and tell everyone standing under it.

        Nothing is sent when the sky has not actually changed: a restatement
        of the same weather is not an event, and a client that redrew its rain
        every turn would flicker.
        """
        previous = self.weather_on(map_id)
        # The sky is recorded either way; only a change is announced. A map
        # that rolls clear twice running has clear weather, not no weather.
        self.weather[map_id] = (kind, intensity)
        if previous == (kind, intensity):
            return
        await self.broadcast_map(map_id, p.send_weather(kind, intensity))
        await self.broadcast_map(
            map_id, p.stop_rain() if kind == CLEAR else p.start_rain(intensity))
        if kind == STORM:
            await self.broadcast_map(
                map_id, p.thunder(max(1, min(5, 1 + intensity // 20))))

    async def turn_weather(self) -> None:
        """Roll the sky over every map that has a climate.

        Called once per game day from the clock, so weather moves at the pace
        of the day the world already has rather than at real-time speed.
        """
        for map_id in sorted(self.climates):
            kind, intensity = roll_weather(self.climates[map_id], random)
            await self.set_weather(map_id, kind, intensity)

    async def play_sound_at(self, map_id: str, name: str, x: int, y: int,
                            gain: int = 100,
                            excluding: Session | None = None) -> None:
        """Tell everyone on a map about a sound, except whoever caused it.

        The client answers its own actions itself - its own harvest, its own
        pick-up - so sending it a sound for those would play everything twice.
        What it cannot know is what somebody else is doing, and that is what
        this carries.
        """
        frames = [(session, self.coordinate_packet(session, map_id,
                    lambda point: p.play_sound(name, *point(x, y), gain)))
                  for session in list(getattr(self, "sessions", ()))
                  if session is not excluding and session.character and session.character.map_id == map_id]
        for session, frame in frames:
            try:
                await session.send(frame)
            except (ConnectionError, asyncio.CancelledError):
                pass

    async def send_map_music(self, session: Session) -> None:
        """State the music for the map the character is standing on."""
        c = session.character
        if not c:
            return
        await session.send(p.play_music(self.map_music.get(c.map_id, "")))

    async def do_emote(self, session: Session, name: str) -> None:
        """Play an emote, seen by everyone on the map who can see the player.

        The animation and the words are sent separately and the words always
        go out: a client with no clip for the action shows nothing but still
        reads what happened, so an emote is never silently lost.
        """
        c = session.character
        if not c:
            return
        emote = self.emotes.get(name.casefold().strip())
        if not emote:
            known = ", ".join(sorted(self.emotes)) or "none"
            await session.send(p.raw_text(
                f"There is no {name!r} emote. Known emotes: {known}"))
            return
        await self.broadcast_map(c.map_id,
                                 p.actor_animation(c.actor_id, emote.action))
        await session.send(p.raw_text(emote.to_actor(c.name)))
        others = p.raw_text(emote.to_others(c.name))
        for nearby in list(self.sessions):
            if (nearby is not session and nearby.character
                    and nearby.character.map_id == c.map_id):
                try:
                    await nearby.send(others)
                except (ConnectionError, asyncio.CancelledError):
                    pass

    async def use_item_on_item(self, session: Session, source_slot: int,
                               target_slot: int) -> None:
        """Combine one carried item with another.

        The legacy client sends this whenever a player drops one item onto
        another, and this server had no concept of it at all. Rather than
        invent a second crafting system beside the recipes, it means the one
        thing it can honestly mean here: mix the recipe whose ingredients are
        exactly these two items. Quantities come from the recipe, so putting a
        plank on a cloth roll makes a torch whatever the stacks hold.
        """
        c = session.character
        if not c:
            return
        slots = session.inventory_slots
        if (source_slot == target_slot
                or source_slot >= len(slots) or target_slot >= len(slots)
                or not slots[source_slot] or not slots[target_slot]):
            await session.send(p.item_description(
                "Put one item onto a different item to combine them."))
            return
        first, second = slots[source_slot], slots[target_slot]
        wanted = {first, second}
        recipe = next((recipe for recipe in self.recipes
                       if {name for name, _quantity in recipe.ingredients} == wanted
                       and len(recipe.ingredients) == 2), None)
        if not recipe:
            await session.send(p.item_description(
                f"Nothing comes of putting {first} together with {second}."))
            return
        required = dict(recipe.ingredients)
        short = [f"{quantity} {name}" for name, quantity in required.items()
                 if c.inventory.get(name, 0) < quantity]
        if short:
            await session.send(p.item_description(
                f"Making {recipe.output} needs " + " and ".join(short) + "."))
            return
        required_knowledge = recipe.knowledge or infer_recipe_knowledge(
            recipe.output, recipe.skill, self.books)
        if required_knowledge and required_knowledge not in c.known_books:
            await session.send(p.item_description(
                f"You need to read {required_knowledge} before making"
                f" {recipe.output}."))
            return
        if session.mix_task and not session.mix_task.done():
            session.mix_task.cancel()
        session.mix_status = None
        session.mix_task = asyncio.create_task(self._mix_loop(session, recipe, 1))

    async def send_map_digest(self, session: Session) -> None:
        """Tell the client which package this server expects for its map.

        Sent at login and after every map change, because the client checks it
        while it loads the map and a client that walked in from somewhere else
        has a different map to check. Silent when the profile publishes no
        digest for the map: there is nothing to say, and saying it with an
        empty string would be the same as saying nothing at a packet's cost.

        The client cannot act on this and is not meant to. Its map cache is
        keyed on the package it actually has, so a mismatch cannot make the
        cache wrong; it means the install is not the one this server was built
        against, which is worth a line in a log and nothing more.
        """
        c = session.character
        if not c or "map_digest_v1" not in session.client_capabilities:
            return
        digest = self.map_digests.get(c.map_id.strip().lower(), "")
        if not digest:
            return
        await session.send(p.map_digest(c.map_id, digest))

    async def send_navigation_state(self, session: Session) -> None:
        c, waypoint = session.character, session.waypoint
        if not c or "navigation_hud_v1" not in session.client_capabilities:
            return
        if not waypoint:
            frame = p.navigation_state(False, 0, 0, 0, "", "")
            await session.send(CoordinateFrame(session.coordinate_token(), frame)
                               if session.coordinate_state is not None else frame)
            return
        map_id, x, y, label = waypoint
        distance = (max(abs(c.x - x), abs(c.y - y))
                    if c.map_id == map_id else 0)
        frame = self.coordinate_packet(session, map_id,
            lambda point: p.navigation_state(True, *point(x, y), distance, map_id, label), named=True)
        if frame is None:
            await session.send(p.raw_text("Waypoint location needs map storage coordinate support."))
        else:
            await session.send(frame)

    async def set_waypoint(self, session: Session, x: int, y: int,
                           label: str = "Waypoint") -> None:
        c = session.character
        if not c:
            return
        if session.coordinate_state is not None:
            session.coordinate_state.catalog.profile(c.map_id).to_wire(x, y)
        elif not 0 <= x <= 2047 or not 0 <= y <= 2047:
            raise ValueError("Waypoint coordinates must be between 0 and 2047.")
        label = label.strip()[:79] or "Waypoint"
        session.waypoint = (c.map_id, x, y, label)
        await self.send_map_marker(session, 490, x, y, c.map_id, label)
        await self.send_navigation_state(session)

    async def clear_waypoint(self, session: Session) -> None:
        session.waypoint = None
        await session.send(p.remove_map_marker(490))
        await self.send_navigation_state(session)

    def blocking_tiles(self, map_id: str,
                       ignore=()) -> set[tuple[int, int]]:
        """Every tile on this map an actor is standing on.

        A large body blocks every tile it stands on, so a walker routes around
        the whole of it rather than through the parts that are not its anchor.
        `ignore` is the mover itself, whose own tiles must not count against
        it, and anything else the caller has already accounted for.
        """
        ignored = {id(actor) for actor in ignore}
        occupied: set[tuple[int, int]] = set()
        for other in self.sessions:
            character = other.character
            if (character is not None and id(character) not in ignored
                    and character.map_id == map_id):
                occupied.update(footprint_of(character).tiles(character.x, character.y))
        for actor_id in self.animals_by_map.get(map_id, ()):
            animal = self.animals.get(actor_id)
            if animal and animal.alive and id(animal) not in ignored:
                occupied.update(footprint_of(animal).tiles(animal.x, animal.y))
        for npc, npc_map, _, _ in self.npcs.values():
            if npc_map == map_id and id(npc) not in ignored:
                occupied.update(footprint_of(npc).tiles(npc.x, npc.y))
        return occupied

    def walk_blocked(self, map_id: str, target: tuple[int, int], ignore=()) -> set:
        """What a walk to `target` may not step on: bodies, and every other way off the map.

        A walk goes where it was sent. The server fires a portal under any tile
        a walker steps onto, so a path over another one changed maps short of
        its target. That was rare while a land crossing was a gate of seven
        lanes; a border open along its length is a row of crossings beside the
        walker's own ground, and a path shaving a corner of it would cross. The
        target itself is never refused - a click on a crossing or a door is a
        walk through it.
        """
        blocked = self.blocking_tiles(map_id, ignore=ignore)
        return blocked | (walkway_portals(self, map_id) - {tuple(target)})

    def create_location_task(self, session, function, *args):
        """Capture before task scheduling, not when its coroutine first runs."""
        map_id = session.character.map_id
        token = session.coordinate_token() if session.coordinate_state is not None else None
        async def run():
            if self.location_context_current(session, map_id, token):
                return await function(*args)
        return asyncio.create_task(run())

    async def move(self, c: Character, target_x: int, target_y: int):
        # The EL client applies one tile per actor command; keep server authoritative.
        session = next((item for item in self.sessions if item.character is c), None)
        map_id = c.map_id
        token = session.coordinate_token() if session and session.coordinate_state is not None else None
        def current():
            return c.map_id == map_id and (session is None or self.location_context_current(session, map_id, token))
        occupied = self.walk_blocked(c.map_id, (target_x, target_y), ignore=(c,))
        path = self.find_path(c.map_id, (c.x, c.y), (target_x, target_y), occupied,
                              footprint_of(c))
        session = next((item for item in self.sessions if item.character is c), None)
        if path and session and session.sitting:
            await self.set_sitting(session, False)
        if not current():
            return
        at_destination = ((c.x, c.y) == (target_x, target_y)
                          or ((target_x, target_y) in occupied
                              and max(abs(c.x - target_x), abs(c.y - target_y)) == 1))
        if not path and not at_destination:
            if session:
                await session.send(p.raw_text("You cannot reach that location."))
        # Movement immediately interrupts active harvesting in the stock
        # client. Cancel before the first step so the stop message and eye-candy
        # cleanup are not delayed until the complete route has finished.
        if path and session and session.harvest_task \
                and session.harvest_task is not asyncio.current_task() \
                and not session.harvest_task.done():
            session.harvest_task.cancel()
        for next_pos in path:
            if not current():
                return
            previous_pk_zone = pk_zone_at(c.map_id, c.x, c.y)
            dx, dy = next_pos[0] - c.x, next_pos[1] - c.y
            command = movement_direction(dx, dy, c.running)
            if command is None:
                # Combat and a newly queued route can move the character before
                # an older route resumes. Ignore an already completed step, and
                # abandon any other route that is no longer adjacent.
                if (dx, dy) == (0, 0):
                    continue
                break
            if next_pos in occupied:
                if session:
                    await session.send(p.raw_text("That tile is occupied."))
                break
            step_origin = (c.map_id, c.x, c.y)
            await self.await_player_step(session, c, dx, dy)
            if not current() or (c.map_id, c.x, c.y) != step_origin:
                # Another route or teleport took over while this step waited.
                # Its delta was computed from the old position: publishing it
                # now would permanently offset clients from the server tile.
                return
            c.x, c.y = next_pos
            c.rotation = facing_rotation(dx, dy)
            if session and sky.on_map(c):
                await sky.event(self, session, "reach")
            if session and bell.on_map(c):
                await bell.event(self, session, "reach")
            if session and lantern.on_island(c):
                await lantern.event(self, session, "reach")
            if session and landing.on_map(c, v2_gate.isle_maps(self)):
                await landing_runtime.event(self, session, "reach")
            if session and watchpost.on_map(c, self):
                await watchpost.event(self, session, "reach")
            if session and c.map_id == wt.HOME_MAP:
                panel = wt.panel_for(c) if wt.is_active(c) else None
                if panel and panel.marker and max(
                        abs(c.x - panel.marker[0]),
                        abs(c.y - panel.marker[1])) <= wt.REACH_RADIUS:
                    await self.walkthrough_event(session, "reach")
            if session and c.map_id in self.questline_visit_maps:
                await self.questline_event(session, "visit")
            if not current():
                return
            if session and session.waypoint:
                waypoint_map, waypoint_x, waypoint_y, _ = session.waypoint
                if (c.map_id, c.x, c.y) == (waypoint_map, waypoint_x, waypoint_y):
                    await self.clear_waypoint(session)
                    await session.send(p.raw_text("Waypoint reached."))
                else:
                    await self.send_navigation_state(session)
            if not current():
                return
            current_pk_zone = pk_zone_at(c.map_id, c.x, c.y)
            speed_hax = c.speed_hax_active
            # BUFF_DOUBLE_SPEED makes the stock client choose its running frames
            # and halve step_duration. Explicit run commands as well cause the
            # local movement queue to diverge and eventually request a resync.
            if token is not None:
                await self.broadcast_coordinates(map_id,
                    lambda point: p.actor_command(c.actor_id, command), source_current=current)
            else:
                await self.broadcast_map(c.map_id, p.actor_command(c.actor_id, command))
            if not current():
                return
            # The replacement actor already contains this step's new position.
            # Send it after the delta, otherwise clients take that step twice.
            if session and current_pk_zone != previous_pk_zone:
                await self.refresh_player_actor(session)
                await session.send(p.raw_text(
                    f"You entered {current_pk_zone.label}. Player killing is enabled."
                    if current_pk_zone else
                    "You left the PK area. Player killing is disabled."))
            # The mover's own step goes out now, not on the next flush tick.
            # deliver() parks every packet in the session outbox while a flush
            # driver runs, and the loop writes it up to invasion_ai_tick_ms
            # later - so each step reached the client with up to a tick of
            # jitter on top of the network's. The client paces its walk from
            # the cadence it measures and tolerates only a fraction of a step
            # of lateness, so that tick was enough to stop and restart the body
            # every few steps. Everyone else on the map keeps the batched
            # delivery: their copy of this actor is buffered on their client.
            if session:
                try:
                    await session.flush()
                except (ConnectionError, OSError):
                    session.outbox.clear()
            if not current():
                return
            self.record_actor_move(c.actor_id)
            if speed_hax:
                if random.random() < self.speed_food_loss_chance(c):
                    c.food = max(-30, c.food - 1)
                    if session:
                        await session.send(p.partial_stats([(46, c.food)]))
                    if c.food <= -30:
                        if session:
                            await self.disable_speed_hax(session)
            if session:
                await self.sync_visible_animals(session)
                await self.sync_visible_npcs(session)
            if session and session.open_bag is not None:
                bag = self.bags.get(session.open_bag)
                if not bag or (c.x, c.y) != bag[:2]:
                    session.open_bag = None
                    await session.send(p.packet(p.CLOSE_BAG))
            if session and await self.check_portal(session):
                return
        if not current():
            return
        self.save_soon(c)
        if session and session.pending_bag is not None:
            bag = self.bags.get(session.pending_bag)
            if bag and (c.x, c.y) == bag[:2]:
                await self._open_bag(session, session.pending_bag)

    async def check_portal(self, session: Session) -> bool:
        c = session.character
        if not c:
            return False
        portal = portal_at(self, c.map_id, c.x, c.y)
        if not portal:
            return False
        if portal.object_id is not None and session.portal_intent != (c.map_id, c.x, c.y):
            # An object portal is entered by using its object, not by walking
            # over its tile: a secret stays secret from anyone crossing the spot.
            return False
        self.require_coordinate_destination(session, portal.destination, portal.destination_x, portal.destination_y)
        session.portal_intent = None
        departure = (c.map_id, c.x, c.y)
        land = (getattr(self, 'land_connections', {}).get((c.map_id, portal.destination))
                if portal.object_id is None else None)
        if land is not None:
            from .exterior_connections import transport_direction
            c.rotation = facing_rotation(*transport_direction(facing_direction(c.rotation), land))
        await self.change_map(session, portal.destination,
                              portal.destination_x, portal.destination_y)
        if land is None:
            await self.announce_teleport(
                c, departure,
                (portal.destination, portal.destination_x, portal.destination_y))
        return True

    def map_object_entries(self, map_id: str
                           ) -> list[tuple[int, int, int, int, str, str]]:
        """Every clickable world object on one map, newest contract first.

        Harvest nodes come first because they are the reason this exists: the
        client had no way at all to know which rendered prop was a resource.
        """
        entries: list[tuple[int, int, int, int, str, str]] = []
        for (node_map, object_id), node in sorted(self.harvest_nodes.items()):
            if node_map != map_id:
                continue
            resource = self.harvest_resources.get(node.resource)
            detail = "Harvesting level %d" % (resource.required_level if resource else 0)
            if resource and resource.tool:
                detail += ", needs a %s" % resource.tool
            entries.append((object_id, p.MAP_OBJECT_HARVEST, node.x, node.y,
                            node.resource, detail))
        for (interactive_map, object_id), interactive in sorted(self.interactives.items()):
            if interactive_map != map_id:
                continue
            entries.append((object_id, p.MAP_OBJECT_INTERACTIVE,
                            interactive.x, interactive.y,
                            interactive.role.replace("_", " ").title(),
                            interactive.text))
        entries.extend(self.map_exit_entries(map_id))
        return entries

    def border_gate(self, map_id: str, destination: str,
                    tiles: list[tuple[int, int]]) -> tuple[int, int]:
        """The crossing of an open border that its road arrives at.

        The survey anchors every land crossing at its gate, the station its
        seam road runs to; the crossing tile nearest that anchor is where a
        marker for the way to the neighbour belongs. Without the survey, the
        tile nearest the middle of the border's crossings.
        """
        frames = getattr(self, "land_frames", {}).get((map_id, destination))
        near = (getattr(self, "land_connections", {}).get((map_id, destination)) or ({},))[0] or {}
        anchor = near.get("globalAnchor")
        if frames and isinstance(anchor, list) and len(anchor) == 3:
            ax, ay = frames[0].to_tile(float(anchor[0]), float(anchor[2]))
        else:
            ax = sum(x for x, _ in tiles) / len(tiles)
            ay = sum(y for _, y in tiles) / len(tiles)
        return min(tiles, key=lambda tile: ((tile[0] - ax) ** 2 + (tile[1] - ay) ** 2, tile))

    def map_exit_entries(self, map_id: str) -> list[tuple[int, int, int, int, str, str]]:
        """The ways off this map that nothing else marks, one per doorway.

        `maps.txt` knows every walk-in transition as portal tiles; the client
        knows none of them, so a march with no waygate and every door into
        an interior went unmarked on both of its maps. The tiles are grouped
        by destination and nearness - a march is a run of neighbouring tiles
        - and each group is one exit at its middle, named for where it
        leads. A doorway with a waygate object beside it is left to the
        waygate, which is already a marked, clickable thing.
        """
        portals = [portal for portal in portals_leaving(self, map_id)
                   if portal.object_id is None and portal.destination != map_id]
        if not portals:
            return []
        waygates = [(entry.x, entry.y)
                    for (entry_map, _), entry in getattr(self, "interactives", {}).items()
                    if entry_map == map_id and getattr(entry, "role", "") == "portal"]
        # A seamless land crossing is the map's own border, open wherever the
        # ground allows: one way to each neighbour, marked at the crossing its
        # road arrives at, rather than a mark for every stretch of open ground
        # along the border - which gave one map twelve and one neighbour seven.
        land = getattr(self, "land_connections", {})
        borders: dict[str, list[tuple[int, int]]] = {}
        for portal in portals:
            if (map_id, portal.destination) in land:
                borders.setdefault(portal.destination, []).append((portal.x, portal.y))
        portals = [portal for portal in portals if portal.destination not in borders]
        clusters: list[tuple[str, list[tuple[int, int]]]] = [
            (destination, [self.border_gate(map_id, destination, tiles)])
            for destination, tiles in sorted(borders.items())]
        for portal in sorted(portals, key=lambda entry: (entry.destination, entry.x, entry.y)):
            for destination, tiles in clusters:
                # Newest tile first: a run of seam tiles is added in order, so
                # the one that answers is the one just added rather than the far
                # end of a boundary-long cluster. `any` is a yes or no, so the
                # order it asks in cannot change which cluster a tile joins.
                if destination == portal.destination and any(
                        max(abs(portal.x - x), abs(portal.y - y)) <= EXIT_CLUSTER_TILES
                        for x, y in reversed(tiles)):
                    tiles.append((portal.x, portal.y))
                    break
            else:
                clusters.append((portal.destination, [(portal.x, portal.y)]))
        maps = getattr(self, "maps", {})
        entries: list[tuple[int, int, int, int, str, str]] = []
        for destination, tiles in clusters:
            if any(max(abs(tx - wx), abs(ty - wy)) <= WAYGATE_REACH
                   for tx, ty in tiles for wx, wy in waygates):
                continue
            x = int(round(sum(tx for tx, _ in tiles) / len(tiles)))
            y = int(round(sum(ty for _, ty in tiles) / len(tiles)))
            named = maps.get(destination)
            name = named.name if named is not None else destination.replace("_", " ").title()
            entries.append((EXIT_OBJECT_BASE + len(entries), p.MAP_OBJECT_EXIT, x, y,
                            name, f"The way to {name}."))
        return entries

    async def send_map_objects(self, session: Session) -> None:
        c = session.character
        if not c:
            return
        await session.send(self.coordinate_packet(session, c.map_id,
            lambda point: b"".join(p.map_object_packets(
                (object_id, kind, *point(x, y), label, detail)
                for object_id, kind, x, y, label, detail in self.map_object_entries(c.map_id)))))

    async def send_harvest_state(self, session: Session, active: bool,
                                 object_id: int = 0, resource: str = "") -> None:
        await session.send(p.harvest_state_packet(active, object_id, resource))

    async def use_map_object(self, session: Session, object_id: int):
        """Approach the configured outdoor exit for the current map.

        Official object-to-portal tables are server-side and are not shipped in
        the open client. Each currently enabled outdoor map has one configured
        ferry/flag exit, so a use click can safely resolve to that exit.
        """
        c = session.character
        if not c or session.combat_target is not None or session.aggressors:
            return
        interactive = self.interactives.get((c.map_id, object_id))
        # Gates can award/save progress before selecting their portal below.
        if ((getattr(self, 'coordinate_catalog', None) is not None or session.coordinate_state is not None)
                and (interactive is None or interactive.role in ('portal', 'secret', 'gate'))):
            leaving = portals_leaving(self, c.map_id)
            exact = [portal for portal in leaving if portal.object_id == object_id]
            choices = exact or [portal for portal in leaving if portal.object_id is None
                               and max(abs(c.x-portal.x), abs(c.y-portal.y)) <= self.settings.portal_activation_distance]
            if choices:
                portal = min(choices, key=lambda entry: max(abs(c.x-entry.x), abs(c.y-entry.y)))
                self.require_coordinate_destination(session, portal.destination,
                                                    portal.destination_x, portal.destination_y)
        if interactive:
            distance = max(abs(c.x - interactive.x), abs(c.y - interactive.y))
            if distance > self.settings.portal_activation_distance:
                await session.send(p.raw_text("You are too far away to use that."))
                return
            if await roads.use_object(self, session, interactive):
                return
            if await sky.use_object(self, session, interactive):
                return
            if await bell.use_object(self, session, interactive):
                return
            if await lantern.use_object(self, session, interactive):
                return
            if await landing_runtime.use_object(self, session, interactive):
                return
            if interactive.role == "storage":
                await session.send(p.raw_text(interactive.text))
                await self.open_storage(session)
                return
            if interactive.role == "water_source":
                cooldown_key = f"interactive_water_{c.map_id}_{object_id}"
                now = int(time.time())
                ready_at = int(c.quest_state.get(cooldown_key, 0))
                if now < ready_at:
                    await session.send(p.raw_text(
                        f"{interactive.text} It will be ready again shortly."))
                    return
                c.food = min(45, c.food + 5)
                c.quest_state[cooldown_key] = now + 300
                self.db.save(c)
                await self.send_stats(session, force=True)
                await session.send(p.raw_text(interactive.text))
                return
            if interactive.role == "cache":
                await gauntlets.use_cache(self, session, interactive)
                return
            if interactive.role == "waystone":
                await gauntlets.use_waystone(self, session, interactive)
                return
            if interactive.role == "gate":
                # a barred way: the gauntlet decides whether the portal
                # behind it may fire
                if not await gauntlets.use_gate(self, session, interactive):
                    return
            if interactive.role in ("portal", "secret", "gate"):
                # Portal destinations and arrival safety remain authoritative in maps.txt.
                if interactive.role == "secret":
                    key = (interactive.target[4:].strip()
                           if interactive.target.startswith("key:") else "")
                    if key and c.inventory.get(key, 0) < 1 and key not in c.equipment.values():
                        await session.send(p.raw_text(
                            f"{interactive.text} It does not give. Something like a {key} "
                            "might move it."))
                        return
                    await session.send(p.raw_text(interactive.text))
            else:
                await session.send(p.raw_text(interactive.text))
                await self.walkthrough_event(session, interactive.role)
                return
        leaving = portals_leaving(self, c.map_id)
        exact = [portal for portal in leaving if portal.object_id == object_id]
        choices = exact or [portal for portal in leaving
                            if portal.object_id is None
                            and max(abs(c.x-portal.x), abs(c.y-portal.y))
                            <= self.settings.portal_activation_distance]
        if not choices:
            # Most USE_MAP_OBJECT packets are ordinary scenery. Ignore those;
            # maps.txt remains the authoritative list of usable exits.
            return
        portal = min(choices, key=lambda entry:
                      max(abs(c.x-entry.x), abs(c.y-entry.y)))
        self.require_coordinate_destination(session, portal.destination, portal.destination_x, portal.destination_y)
        session.portal_intent = (c.map_id, portal.x, portal.y)
        if session.move_task and not session.move_task.done():
            session.move_task.cancel()
        if (c.x, c.y) == (portal.x, portal.y):
            # A zero-length route has no movement step on which check_portal()
            # can run. Activate the selected object portal immediately when
            # the player is already standing on its configured trigger tile.
            session.portal_intent = None
            await self.change_map(session, portal.destination,
                                  portal.destination_x, portal.destination_y)
            return
        session.move_task = self.create_location_task(session, self.move, c, portal.x, portal.y)

    async def inspect_map_object(self, session: Session, object_id: int):
        c = session.character
        if not c:
            return
        session.last_map_object_id = object_id
        node = self.harvest_nodes.get((c.map_id, object_id))
        if node:
            resource = self.harvest_resources.get(node.resource)
            description = node.resource
            if resource:
                description += " - harvesting level %d" % resource.required_level
                if resource.tool:
                    description += ", needs a %s" % resource.tool
            await session.send(p.raw_text(description))
            return
        interactive = self.interactives.get((c.map_id, object_id))
        if interactive:
            await session.send(p.raw_text(interactive.text))
            return
        await session.send(p.raw_text("There is nothing to see there."))

    def require_coordinate_destination(self, session, map_id, x=None, y=None):
        from .coordinate_admission import require_destination
        require_destination(self, session, map_id, x, y)
        if session.coordinate_state is not None:
            if map_id not in self.maps:
                raise ValueError("Coordinate destination is not loaded.")
            session.coordinate_state.prepare_activation(map_id, self.coordinate_handles(session, map_id))

    def coordinate_handles(self, session, map_id):
        handles = {0: map_id}
        # Rendering capabilities may arrive after login; the coordinate table
        # must already bind every handle before a later adjacent actor appears.
        handles.update({handle: far for far, handle in self.adjacent_handles(map_id).items()})
        return handles

    def require_coordinate_login(self, session, character):
        from .coordinate_admission import require_private_support
        if character.map_id in v2_gate.RETIRED_MAPS:
            character.map_id, character.x, character.y = home.point(self, "beam")
        if session.coordinate_state is not None:
            if character.map_id not in self.maps:
                raise ValueError("Saved coordinate map is not loaded.")
            if ((character.quest_state.get('sky_run') and not character.quest_state.get('sky_paused'))
                    or (lantern.active(character) and getattr(self, 'lantern_layout', None)
                        and lantern.current(character).key != 'handoff')
                    or (bell.active(character) and getattr(self, 'bell_layout', None)
                        and not bell.flag(character, 'paused'))):
                require_private_support(session)
        # The home's own beam, as in enter: nothing is declared at login.
        destination = ((character.map_id, character.x, character.y)
                       if character.map_id in self.maps
                       else home.point(self, "beam"))
        self.require_coordinate_destination(session, *destination)
        if session.coordinate_state is not None:
            session.coordinate_state.prepare_activation(destination[0],
                self.coordinate_handles(session, destination[0]))

    async def change_map(self, session: Session, map_id: str, x: int, y: int):
        self.require_coordinate_destination(session, map_id, x, y)
        if session.coordinate_state is None:
            return await self._change_map(session, map_id, x, y)
        if getattr(session, '_coordinate_lifecycle', False):
            raise ValueError("Map transition already in progress.")
        session.coordinate_state.prepare_activation(map_id, self.coordinate_handles(session, map_id))
        session._coordinate_lifecycle = True
        try:
            return await self._change_map(session, map_id, x, y)
        finally:
            session._coordinate_lifecycle = False

    async def _change_map(self, session: Session, map_id: str, x: int, y: int):
        c = session.character
        if not c or map_id not in self.maps:
            return
        if not roads.allowed_destination(c, map_id):
            return
        if not sky.allowed_destination(c, map_id):
            await session.send(p.raw_text("Use Recall or Leave tutorial to leave Stillglass. Each practice belongs to its owner."))
            return
        if not bell.allowed_destination(c, map_id):
            await session.send(p.raw_text("Use Nesh or Leave tutorial to leave Bellwatch; each rescue belongs to its owner."))
            return
        if not lantern.allowed_destination(self, c, map_id):
            await session.send(p.raw_text("Finish the crossing, or choose Skip tutorial to leave." if lantern.on_island(c) else "That rescue belongs to another traveler."))
            return
        old_map = c.map_id
        token = session.coordinate_token() if session.coordinate_state is not None else None
        x, y = self.free_player_tile(map_id, x, y, exclude=c)
        self.require_coordinate_destination(session, map_id, x, y)
        if old_map == wt.HOME_MAP and map_id != wt.HOME_MAP:
            await self.walkthrough_event(session, "travel")
        if not self.location_context_current(session, old_map, token):
            return
        land_crossing = (self.adjacent_actors_enabled(session)
                         and (old_map, map_id) in (getattr(self, "land_frames", None) or {}))
        await self.broadcast_except(p.packet(p.REMOVE_ACTOR, struct.pack("<H", c.actor_id)), session)
        if not self.location_context_current(session, old_map, token):
            return
        if session.coordinate_state is None:
            c.map_id, c.x, c.y = map_id, x, y
            await gauntlets.on_map_change(self, session, old_map)
        carried_players: set[int] = set()
        if land_crossing:
            # A seamless crossing keeps every actor the client already shows:
            # KILL_ALL_ACTORS would empty its table and repopulate it, which is
            # the discontinuity the adjacency exists to remove.
            carried_players = self.carry_actors_across(session, old_map, map_id)
        else:
            self.drop_animal_viewer(session, tuple(session.visible_animals))
            session.visible_animals.clear()
            session.visible_npcs.clear()
            self.forget_adjacent(session)
        session.open_bag = session.pending_bag = None
        await session.send(p.packet(p.CLOSE_BAG))
        if not land_crossing:
            # CHANGE_MAP does not reliably discard the stock client's old actor
            # table. Clear it explicitly, then repopulate destination-map actors.
            await session.send(p.packet(p.KILL_ALL_ACTORS))
        if session.coordinate_state is not None:
            if not self.location_context_current(session, old_map, token):
                return
            def commit_location():
                c.map_id, c.x, c.y = map_id, x, y
                session.pending_spell = None
            await session.activate_coordinates(map_id, self.maps[map_id].client_name,
                                              self.coordinate_handles(session, map_id),
                                              commit=commit_location)
            await gauntlets.on_map_change(self, session, old_map)
        else:
            await session.send(p.packet(p.CHANGE_MAP, self.maps[map_id].client_name.encode() + b"\0"))
        # Immediately behind the map change rather than with the scenery below:
        # the client starts loading the package the moment CHANGE_MAP arrives,
        # and the digest is what it checks that package against.
        await self.send_map_digest(session)
        await session.send(p.packet(p.YOU_ARE, struct.pack("<H", c.actor_id)))
        await self.send_adjacent_maps(session)
        for other in self.sessions:
            if (other is not session and other.character and other.character.map_id == map_id
                    and other.character.actor_id not in carried_players):
                await session.send(self.player_actor_packet(session, other.character))
        await self.sync_visible_animals(session)
        await self.sync_visible_npcs(session)
        await self.send_map_objects(session)
        # A new map has its own music, its own sky and its own fires, or
        # none of them, which is also an answer.
        await self.send_map_music(session)
        await self.send_weather(session)
        await self.send_fires(session)
        await self.send_teleporters(session)
        await self.send_world_objects(session)
        if any(self.bag_maps.get(bag_id, "") == map_id for bag_id in self.bags):
            await session.send(self.bags_packet(session, map_id))
        await session.send(self.player_actor_packet(session, c))
        for other in self.sessions:
            if other is not session and other.character and other.character.map_id == map_id:
                await other.send(self.player_actor_packet(other, c))
        if c.speed_hax_active:
            await self.broadcast_map(map_id,
                                     p.actor_buffs(c.actor_id, BUFF_DOUBLE_SPEED))
        self.save_soon(c)
        await session.send(p.raw_text(
            f"Entered {self.maps[map_id].name} [{x}, {y}] from {self.maps[old_map].name}."))
        # Who is calling themselves what, on the map just arrived at.
        await self.send_actor_titles(session)
        if c.title:
            await self.broadcast_title(c)
        # First arrival is a thing worth recording whether or not any
        # achievement currently names this map: adding one later should not
        # need a player to walk the world again.
        if self.mark_map_visit(c, map_id):
            self.db.save(c)
        await self.award_achievements(session)

        if bell.on_map(c):
            await bell.sync(self, session)
        if old_map.startswith(lantern.MAP):
            lantern.cleanup(self, c)
        if lantern.active(c):
            await lantern.sync(self, session)
        await landing_runtime.arrived(self, session, old_map)
        await watchpost.sync(self, session)

    def resolve_map(self, value: str) -> str | None:
        normalized = value.casefold().replace(" ", "").replace("_", "")
        for map_id, definition in self.maps.items():
            candidates = {map_id.casefold().replace("_", ""),
                          definition.name.casefold().replace(" ", "").replace("_", ""),
                          definition.file.casefold().removeprefix("maps/").removesuffix(".elm")}
            candidates.update(alias.casefold().replace(" ", "").replace("_", "")
                              for alias in definition.aliases)
            if normalized in candidates:
                return map_id
        return None

    async def teleport(self, session: Session, x: int, y: int, map_id: str):
        if not session.character:
            return
        if session.coordinate_state is None and (not 0 <= x <= 2047 or not 0 <= y <= 2047):
            raise ValueError("Coordinates must be between 0 and 2047.")
        resolved = self.resolve_map(map_id)
        if not resolved:
            raise ValueError(f"Unknown map {map_id!r}.")
        self.require_coordinate_destination(session, resolved, x, y)
        if session.move_task and session.move_task is not asyncio.current_task() \
                and not session.move_task.done():
            session.move_task.cancel()
        session.pending_attack = session.combat_target = None
        session.aggressors.clear()
        session.fleeing = False
        await self.change_map(session, resolved, x, y)

    async def refresh_player_actor(self, session: Session) -> None:
        """Refresh an online player's overhead name for everyone on their map."""
        character = session.character
        if not character:
            return
        remove = p.packet(p.REMOVE_ACTOR, struct.pack("<H", character.actor_id))
        for recipient in list(self.sessions):
            other = recipient.character
            if other and other.map_id == character.map_id:
                await recipient.send(remove)
                await recipient.send(self.player_actor_packet(recipient, character))
            elif other and character.actor_id in (getattr(recipient, "visible_adjacent", None) or {}):
                handle = self.adjacent_handles(other.map_id).get(character.map_id, 0)
                await recipient.send(remove)
                await recipient.send(self.player_actor_packet(recipient, character, map_handle=handle))

    def find_player_by_actor(self, actor_id: int) -> Session | None:
        return next((session for session in self.sessions
                     if session.character and session.character.actor_id == actor_id), None)

    @staticmethod
    def trade_in_range(first: Session, second: Session) -> bool:
        a, b = first.character, second.character
        return bool(a and b and a.map_id == b.map_id
                    and max(abs(a.x - b.x), abs(a.y - b.y)) <= 4)

    async def request_trade(self, session: Session, actor_id: int) -> None:
        c = session.character
        target = self.find_player_by_actor(actor_id)
        if not c or not target or target is session or not self.trade_in_range(session, target):
            await session.send(p.raw_text("That player is not close enough to trade."))
            return
        if session.trade_partner or target.trade_partner:
            await session.send(p.raw_text("One of you is already trading."))
            return
        now = time.monotonic()
        pending = session.pending_trade_from
        if pending and pending[0] == actor_id and now - pending[1] <= 30:
            session.pending_trade_from = None
            target.pending_trade_from = None
            await self.start_trade(session, target)
            return
        target.pending_trade_from = (c.actor_id, now)
        await session.send(p.raw_text(
            f"{target.character.name} was notified, now wait to see if s/he wants to trade with you."))
        await target.send(p.raw_text(
            f"{c.name} wants to trade with you. Click the trade icon on {c.name} to accept."))

    async def start_trade(self, first: Session, second: Session) -> None:
        operation_id = (
            f"trade:{time.time_ns()}:{min(first.character.actor_id, second.character.actor_id)}:"
            f"{max(first.character.actor_id, second.character.actor_id)}")
        storage = (self.storage_npc_near(first.character)
                   and self.storage_npc_near(second.character))
        for own, partner in ((first, second), (second, first)):
            own.trade_partner = partner
            own.trade_offers = [None] * 16
            own.trade_accept_state = 0
            own.trade_destinations = [1] * 16
            own.trade_storage_available = storage
            own.trade_operation_id = operation_id
            own.inventory_slots = self.sync_inventory_slots(own.character)
            await own.send(p.trade_partner(partner.character.name, storage))
            await own.send(p.trade_inventory(own.character.inventory, ITEMS,
                                             own.character.equipment,
                                             own.character.inventory_slots))

    async def reset_trade_accepts(self, first: Session, second: Session) -> None:
        if not first.trade_accept_state and not second.trade_accept_state:
            return
        first.trade_accept_state = second.trade_accept_state = 0
        await first.send(p.trade_reject(False))
        await first.send(p.trade_reject(True))
        await second.send(p.trade_reject(False))
        await second.send(p.trade_reject(True))

    async def refresh_trade_source(self, session: Session) -> None:
        c = session.character
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment,
                                              c.inventory_slots))
        if session.storage_open and self.storage_npc_near(c):
            await self.show_storage_category(session, session.storage_category)

    async def put_trade_item(self, session: Session, source_type: int,
                             source_position: int, quantity: int) -> None:
        partner, c = session.trade_partner, session.character
        if not partner or not c or not self.trade_in_range(session, partner):
            await self.cancel_trade(session, notify_partner=True)
            return
        if source_type == 1:
            if not session.inventory_slots:
                session.inventory_slots = self.sync_inventory_slots(c)
            if not 0 <= source_position < len(session.inventory_slots):
                return
            name = session.inventory_slots[source_position]
            available = c.inventory.get(name, 0) if name else 0
        elif source_type == 2 and session.trade_storage_available \
                and self.storage_npc_near(c):
            positions = self.storage_positions(c)
            if not 0 <= source_position < len(positions):
                return
            name = positions[source_position]
            available = c.storage.get(name, 0)
        else:
            return
        amount = min(max(0, quantity), available)
        if not amount or name not in ITEMS:
            return
        instance_ids: list[int] = []
        if tracks_instances(name):
            if source_type == 1:
                amount = min(amount, 1)
                instance_id = (
                    c.inventory_instance_slots[source_position]
                    if source_position < len(c.inventory_instance_slots)
                    else None)
                if not instance_id:
                    self.db.item_instances.reconcile_character(c)
                    instance_id = c.inventory_instance_slots[source_position]
                instance_ids = [instance_id] if instance_id else []
            else:
                instance_ids = list(c.storage_instances.get(name, []))[:amount]
                amount = min(amount, len(instance_ids))
            if not instance_ids:
                await session.send(p.raw_text(
                    "That equipment object has no valid identity; reopen the trade window."))
                return
        slot = next((i for i, offer in enumerate(session.trade_offers)
                     if offer and offer.name == name and offer.source_type == source_type), None)
        if slot is None:
            slot = next((i for i, offer in enumerate(session.trade_offers) if offer is None), None)
        if slot is None:
            await session.send(p.raw_text("The trade window is full."))
            return
        source = c.inventory if source_type == 1 else c.storage
        for instance_id in instance_ids:
            self.db.item_instances.transfer(
                instance_id, 1, "system",
                f"trade_escrow:{session.trade_operation_id}",
                actor=c.username, source="player_trade_escrow")
        source[name] -= amount
        if not source[name]:
            del source[name]
        offer = session.trade_offers[slot]
        if offer:
            offer.quantity += amount
            offer.instance_ids.extend(instance_ids)
        else:
            session.trade_offers[slot] = TradeOffer(
                name, amount, source_type, source_position, instance_ids)
            offer = session.trade_offers[slot]
        await self.reset_trade_accepts(session, partner)
        packet = p.trade_object(ITEMS[name].image_id, amount, source_type, slot, False)
        await session.send(packet)
        await partner.send(p.trade_object(ITEMS[name].image_id, amount, source_type, slot, True))
        self.db.save(c)
        await self.refresh_trade_source(session)

    async def remove_trade_item(self, session: Session, slot: int, quantity: int) -> None:
        partner = session.trade_partner
        if not partner or not 0 <= slot < 16:
            return
        offer = session.trade_offers[slot]
        if not offer:
            return
        amount = min(max(0, quantity), offer.quantity)
        if not amount:
            return
        await self.reset_trade_accepts(session, partner)
        self.restore_trade_offer(session, offer, amount)
        offer.quantity -= amount
        if not offer.quantity:
            session.trade_offers[slot] = None
        await session.send(p.trade_remove(amount, slot, False))
        await partner.send(p.trade_remove(amount, slot, True))
        self.db.save(session.character)
        await self.refresh_trade_source(session)

    def restore_trade_offer(self, session: Session, offer: TradeOffer, amount: int) -> None:
        c = session.character
        destination = c.storage if offer.source_type == 2 else c.inventory
        returning_ids = offer.instance_ids[-amount:] if offer.instance_ids else []
        if returning_ids:
            del offer.instance_ids[-len(returning_ids):]
        owner_type = "storage" if offer.source_type == 2 else "inventory"
        for index, instance_id in enumerate(returning_ids):
            self.db.item_instances.transfer(
                instance_id, 1, owner_type, c.username,
                slot_key=(str(offer.source_position)
                          if owner_type == "inventory" and index == 0 else ""),
                actor=c.username, source="player_trade_return")
        destination[offer.name] = destination.get(offer.name, 0) + amount
        if offer.source_type == 1:
            slots = normalize_inventory_slots(c.inventory, c.inventory_slots)
            if offer.source_position < len(slots) and slots[offer.source_position] is None:
                slots[offer.source_position] = offer.name
            c.inventory_slots = slots

    async def reject_trade(self, session: Session) -> None:
        if session.trade_partner:
            await self.reset_trade_accepts(session, session.trade_partner)

    async def accept_trade(self, session: Session, destinations: bytes) -> None:
        partner = session.trade_partner
        if not partner or not self.trade_in_range(session, partner):
            await self.cancel_trade(session, notify_partner=True)
            return
        session.trade_destinations = [
            (2 if value == 2 and session.trade_storage_available else 1)
            for value in (list(destinations[:16]) + [1] * 16)[:16]
        ]
        if session.trade_accept_state == 0:
            session.trade_accept_state = 1
        elif session.trade_accept_state == 1 and partner.trade_accept_state >= 1:
            session.trade_accept_state = 2
        else:
            return
        await session.send(p.trade_accept(False, session.trade_accept_state))
        await partner.send(p.trade_accept(True, session.trade_accept_state))
        if session.trade_accept_state == 2 and partner.trade_accept_state == 2:
            await self.complete_trade(session, partner)

    async def complete_trade(self, first: Session, second: Session) -> None:
        if first.trade_partner is not second or second.trade_partner is not first:
            return
        storage = (first.trade_storage_available and second.trade_storage_available
                   and self.storage_npc_near(first.character)
                   and self.storage_npc_near(second.character))
        incoming = {}
        for receiver, sender in ((first, second), (second, first)):
            additions = []
            for slot, offer in enumerate(sender.trade_offers):
                if offer and (receiver.trade_destinations[slot] != 2 or not storage):
                    additions.append((offer.name, offer.quantity))
            incoming[receiver] = additions
            if not self.can_add_inventory(receiver.character, additions):
                await first.send(p.raw_text(f"{receiver.character.name} does not have enough inventory space."))
                await second.send(p.raw_text(f"{receiver.character.name} does not have enough inventory space."))
                await self.reset_trade_accepts(first, second)
                return
        for receiver, sender in ((first, second), (second, first)):
            for slot, offer in enumerate(sender.trade_offers):
                if not offer:
                    continue
                destination = receiver.character.storage if (
                    storage and receiver.trade_destinations[slot] == 2) else receiver.character.inventory
                destination[offer.name] = destination.get(offer.name, 0) + offer.quantity
        operation_key = first.trade_operation_id
        with self.db.db:
            if self.modern and not self.modern.claim_operation(
                    operation_key, first.character.username, "player_trade"):
                return
            for receiver, sender in ((first, second), (second, first)):
                for slot, offer in enumerate(sender.trade_offers):
                    if not offer:
                        continue
                    owner_type = ("storage" if storage
                                  and receiver.trade_destinations[slot] == 2
                                  else "inventory")
                    first_instance_id = None
                    for instance_id in offer.instance_ids:
                        moved_id = self.db.item_instances.transfer(
                            instance_id, 1, owner_type,
                            receiver.character.username,
                            actor=sender.character.username,
                            source="player_trade")
                        first_instance_id = first_instance_id or moved_id
                    if self.modern:
                        self.modern.record_economy(
                            "player_trade", sender.character.username,
                            counterparty=receiver.character.username,
                            item_name=offer.name, quantity=offer.quantity,
                            gold=(offer.quantity if offer.name == "Gold Coins" else 0),
                            instance_id=first_instance_id,
                            gold_flow=("transfer" if offer.name == "Gold Coins" else "none"),
                            item_flow=("none" if offer.name == "Gold Coins" else "transfer"),
                            metadata={"operation_key": operation_key,
                                      "destination": owner_type})
            self.db.save(first.character, commit=False)
            self.db.save(second.character, commit=False)
            if self.modern:
                self.modern.finish_operation(operation_key, {"status": "completed"})
        for own in (first, second):
            roads.emit(self,own,"trade",instance_ids=[iid for offer in own.trade_offers if offer for iid in offer.instance_ids])
            if storage and 2 in own.trade_destinations: roads.emit(self,own,"trade_storage")
            own.trade_partner = None
            own.trade_offers = [None] * 16
            own.trade_accept_state = 0
            own.trade_destinations = [1] * 16
            own.trade_storage_available = False
            own.trade_operation_id = ""
            await own.send(p.packet(p.GET_TRADE_EXIT))
            await self.refresh_trade_source(own)
            await own.send(stats_packet(own.character))
            # Counted on the way out, once, for both sides: a trade that was
            # cancelled or refused for space never reaches here.
            self.increment_achievement(own.character, "trades_completed")
            await self.award_achievements(own)

    async def cancel_trade(self, session: Session, notify_partner: bool = False) -> None:
        partner = session.trade_partner
        if not partner:
            session.pending_trade_from = None
            return
        roads.emit(self,session,"trade_cancel")
        pair = (session, partner) if partner.trade_partner is session else (session,)
        for own in pair:
            for offer in own.trade_offers:
                if offer:
                    self.restore_trade_offer(own, offer, offer.quantity)
            own.trade_offers = [None] * 16
            own.trade_accept_state = 0
            own.trade_destinations = [1] * 16
            own.trade_storage_available = False
            own.trade_operation_id = ""
            own.trade_partner = None
            self.db.save(own.character)
            await own.send(p.packet(p.GET_TRADE_EXIT))
            await self.refresh_trade_source(own)
        if notify_partner and partner in pair:
            await partner.send(p.raw_text("The trade was cancelled."))

    async def inspect_trade_item(self, session: Session, slot: int, other: bool) -> None:
        owner = session.trade_partner if other else session
        if not owner or not 0 <= slot < 16 or not owner.trade_offers[slot]:
            return
        offer = owner.trade_offers[slot]
        item = ITEMS[offer.name]
        await session.send(p.raw_text(item.description or offer.name))

    def find_player(self, name: str) -> Session | None:
        wanted = name.casefold()
        return next((session for session in self.sessions
                     if session.character and session.character.name.casefold() == wanted), None)

    async def join_channel(self, session: Session, channel: int):
        if not 0 <= channel <= 999999:
            raise ValueError("Channel numbers may contain up to 6 digits.")
        if channel in session.joined_channels:
            session.active_channel = min(session.joined_channels.index(channel), 2)
        else:
            if len(session.joined_channels) >= 4:
                raise ValueError("You may join up to 4 channels.")
            session.joined_channels.append(channel)
            session.active_channel = min(len(session.joined_channels) - 1, 2)
        await session.send(p.active_channels(session.active_channel,
                                             session.joined_channels))
        await session.send(p.raw_text(f"Joined channel {channel}."))

    async def local_chat(self, sender: Session, message: str):
        c = sender.character
        if not c or not message:
            return
        payload = p.colored_text_segments((
            (p.EL_COLOR_GREY1, f"{c.name}: "),
            (p.EL_COLOR_YELLOW1, message),
        ), p.CHAT_LOCAL)
        for recipient in list(self.sessions):
            other = recipient.character
            if (other and other.map_id == c.map_id
                    and max(abs(other.x-c.x), abs(other.y-c.y)) <= 18):
                await recipient.send(payload)

    async def private_message(self, sender: Session, raw_text: str) -> None:
        character = sender.character
        if not character:
            return
        if raw_text.startswith("//"):
            target_name = sender.last_pm_sender
            message = raw_text[2:].lstrip()
            if not target_name:
                await sender.send(p.raw_text("No player has sent you a private message yet."))
                return
        else:
            body = raw_text[1:].lstrip()
            parts = body.split(maxsplit=1)
            if len(parts) != 2:
                await sender.send(p.raw_text("Syntax: /player_name message"))
                return
            target_name, message = parts
        if not message:
            await sender.send(p.raw_text("Private messages cannot be empty."))
            return
        recipient = self.find_player(target_name)
        if not recipient:
            await sender.send(p.raw_text(f"{target_name} is not online."))
            return
        recipient.last_pm_sender = character.name
        # Personal messages use CHAT_PERSONAL and a closed bracketed header.
        await recipient.send(p.colored_text(
            f"[PM from {character.name}: {message}]", p.EL_COLOR_ORANGE1, p.CHAT_PERSONAL))
        await sender.send(p.colored_text(
            f"[PM to {recipient.character.name}: {message}]", p.EL_COLOR_ORANGE1, p.CHAT_PERSONAL))

    async def channel_chat(self, sender: Session, channel: int, message: str):
        c = sender.character
        if not c or not message:
            return
        if channel not in sender.joined_channels:
            raise ValueError(f"You have not joined channel {channel}.")
        for recipient in list(self.sessions):
            if not recipient.character or channel not in recipient.joined_channels:
                continue
            slot = recipient.joined_channels.index(channel)
            # The stock client has three rendered channel tabs. A fourth joined
            # channel is still addressable with @@number and appears in View All.
            client_channel = 5 + min(slot, 2)
            await recipient.send(p.colored_text(
                f"[{channel}] {c.name}: {message}", 6, client_channel))

    async def turn_player(self, session: Session, clockwise: bool) -> None:
        """Rotate a player one 45 degree step and broadcast the new facing.

        The client sends TURN_LEFT/TURN_RIGHT and renders whatever comes back;
        it does not decide its own facing. The rotation is stored on the actor
        so a later actor packet reports the same direction.
        """
        c = session.character
        if not c or session.sitting:
            return
        step = 1 if clockwise else -1
        index = (FACING_ORDER.index(facing_direction(c.rotation)) + step) % len(FACING_ORDER)
        c.rotation = facing_rotation(*FACING_ORDER[index])
        await self.broadcast_map(
            c.map_id, p.actor_command(c.actor_id, TURNS[FACING_ORDER[index]]))

    async def face_toward(self, actor, target):
        # Between the middles of the two footprints, not their anchor tiles.
        # A creature is drawn in the middle of the ground it holds, so a large
        # one reading its own anchor turned towards a corner of itself.
        dx, dy = actor_facing_step(actor, target)
        if not dx and not dy:
            return
        rotation = facing_rotation(dx, dy)
        if actor.rotation == rotation:
            # Already facing that way. A pursuing attacker re-stops its target
            # on every tick, and each of those was re-sending a turn the actor
            # had already made.
            return
        actor.rotation = rotation
        await self.broadcast_actor(
            actor, p.actor_command(actor.actor_id, TURNS[(dx, dy)]))

    async def face_each_other(self, first, second):
        # Footprint middles, as in face_toward. The pair still get exactly
        # opposite facings: the eight directions are symmetric about their
        # middle, so whichever one this picks, its reverse is the other.
        dx, dy = actor_facing_step(first, second)
        if not dx and not dy:
            return
        # Store both facings, not only broadcast them: a turn command carries
        # no rotation field, so an actor packet sent afterwards would restate
        # the old direction and spin the pair back round.
        first.rotation = facing_rotation(dx, dy)
        second.rotation = facing_rotation(-dx, -dy)
        await self.broadcast_map(first.map_id, p.actor_commands([
            (first.actor_id, TURNS[(dx, dy)]),
            (second.actor_id, TURNS[(-dx, -dy)]),
        ]))

    async def stop_moving_attack_target(self, attacker, target,
                                        target_session: Session | None = None) -> bool:
        """Stop a moving target within five tiles and turn it toward its attacker.

        Something being walked up to stands still and looks at whoever is
        coming, so the fight opens with the two facing each other rather than
        with the target halfway across the next tile. A target already in a
        fight of its own is left alone: it is somebody else's now, and
        stopping it a second time on another attacker's behalf would turn it
        away from the opponent it is actually swinging at.

        `target_session` spares a scan of every session when the caller
        already has it - the AI loop does, and calls this for every creature
        standing near a player on every tick.
        """
        if (attacker.map_id != target.map_id
                or actor_distance(attacker, target) > STOP_MOVING_DISTANCE):
            return False
        stopped = False
        if isinstance(target, Character):
            if target_session is None:
                target_session = self.find_player_by_actor(target.actor_id)
            if target_session is not None and player_in_combat(target_session):
                return False
            task = target_session.move_task if target_session else None
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
                target_session.move_task = None
                stopped = True
        elif isinstance(target, Animal) and target.actor_id not in self.combatants:
            # The AI movement loop honors frozen_until. A short hold is refreshed
            # by the pursuing attacker until normal combat takes over.
            target.frozen_until = max(target.frozen_until, time.monotonic() + 0.75)
            target.wander_steps_remaining = 0
            stopped = True
        if stopped:
            await self.face_toward(target, attacker)
        return stopped

    def stop_ranging(self, session: Session) -> None:
        task = session.ranging_task
        session.ranging_target = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
        if task is not asyncio.current_task():
            session.ranging_task = None

    async def start_ranging(self, session: Session, target_id: int) -> None:
        c = session.character
        animal = self.animals.get(target_id)
        if (not c or not animal or not animal.alive
                or animal.map_id != c.map_id
                or target_id not in session.visible_animals
                or livestock.is_tame(animal)):
            return
        if player_in_combat(session):
            await session.send(p.raw_text("You cannot range while engaged in close combat."))
            return
        loadout = equipped_ranging_items(c)
        if not loadout:
            return
        distance = actor_distance(c, animal)
        if distance < MIN_RANGING_DISTANCE:
            await session.send(p.raw_text(
                "That target is too close to range; move at least four spaces away."))
            return
        self.stop_ranging(session)
        session.ranging_target = target_id
        session.ranging_task = asyncio.create_task(
            self.ranging_loop(session, target_id))

    async def start_player_ranging(
            self, session: Session, target: Session) -> None:
        attacker, defender = session.character, target.character
        if not attacker or not defender:
            return
        zone = self.raid_combat_zone(attacker, defender)
        if not zone:
            await session.send(p.raw_text(
                "You can only range another player while both of you are in the same PK area."))
            return
        if player_in_combat(session):
            await session.send(p.raw_text(
                "You cannot range while engaged in close combat."))
            return
        if (target.combat_target is not None
                and target.combat_target != attacker.actor_id
                and not zone.multi_combat):
            await session.send(p.raw_text(
                f"{defender.name} is already fighting another player."))
            return
        if not equipped_ranging_items(attacker):
            return
        distance = max(abs(attacker.x-defender.x), abs(attacker.y-defender.y))
        if distance < MIN_RANGING_DISTANCE:
            await session.send(p.raw_text(
                "That target is too close to range; move at least four spaces away."))
            return
        self.stop_ranging(session)
        session.ranging_target = defender.actor_id
        session.ranging_task = asyncio.create_task(
            self.player_ranging_loop(session, target))

    async def consume_ranging_ammunition(
            self, session: Session, weapon_name: str, ammunition_name: str) -> None:
        c = session.character
        if not session.inventory_slots:
            session.inventory_slots = self.sync_inventory_slots(c)
        if preserves_ammunition(c, weapon_name):
            return
        if c.inventory.get(ammunition_name, 0) > 0:
            position = next(
                (pos for pos, name in enumerate(session.inventory_slots)
                 if name == ammunition_name), None)
            c.inventory[ammunition_name] -= 1
            if not c.inventory[ammunition_name]:
                del c.inventory[ammunition_name]
                if position is not None:
                    session.inventory_slots[position] = None
                    await session.send(p.inventory_remove(position))
            elif position is not None:
                item = ITEMS[ammunition_name]
                await session.send(p.inventory_update(
                    item.image_id, c.inventory[ammunition_name],
                    position, item.flags))
        else:
            position = next((slot for slot, name in c.equipment.items()
                             if name == ammunition_name), None)
            if position is not None:
                before_visuals = equipped_visuals(c.equipment)
                del c.equipment[position]
                await session.send(p.inventory_remove(int(position)))
                await self.broadcast_visual_changes(c, before_visuals)
        session.inventory_slots = self.sync_inventory_slots(c)
        self.save_soon(c)
        # A HERE_YOUR_INVENTORY refresh clears the stock client's inspect text.
        # Incremental slot packets keep quantities accurate without disturbing it.
        await session.send(stats_packet(c))

    async def award_ranging_hit_xp(
            self, session: Session, target_defense: int, distance: int,
            moving: bool) -> None:
        c = session.character
        amount = int(ranging_experience(
            c, target_defense, distance, moving=moving)
            * self.experience_multiplier("ranging", c))
        level_ups = []
        for skill in ("ranging", "overall"):
            old_level = c.skills[skill]
            c.experience[skill] = c.experience[skill] + amount
            while (c.skills[skill] < max_level_for(skill)
                   and c.experience[skill] >= next_level_experience(c.skills[skill])):
                c.skills[skill] += 1
            if c.skills[skill] != old_level:
                level_ups.append((skill, old_level, c.skills[skill]))
        # The native Ranging window observes per-hit experience deltas. Send
        # this before the full snapshot, which establishes rather than emits
        # the client's experience baseline.
        await session.send(p.partial_stats([(79, c.experience["ranging"])]))
        await session.send(stats_packet(c))
        await self.announce_levels(session, level_ups)

    async def finish_ranged_kill(
            self, session: Session, animal: Animal, *, count_ranging: bool = True) -> None:
        c = session.character
        animal.alive = False
        animal.ranged_aggressor_id = None
        for connected in list(self.sessions):
            connected.aggressors.discard(animal.actor_id)
        await self.broadcast_map(
            animal.map_id, p.actor_command(animal.actor_id, p.CMD_DIE1))
        c.kills[animal.species] = c.kills.get(animal.species, 0) + 1
        await self.notify_tutorial_quarry_kill(session, animal)
        await self.walkthrough_event(session, "kill", animal.species)
        await self.questline_event(session, "kill", animal.species)
        if count_ranging:
            await self.walkthrough_event(session, "ranged_kill", animal.species)
            await self.questline_event(session, "ranged_kill", animal.species)
        self.record_creature_kill(c, animal)
        await self.record_activity(session, ACTIVITY_KILLS)
        if count_ranging:
            self.increment_leaderboard(c, "ranging_kills")
        self.ensure_novac_targets(c)
        for quest, objective in record_novac_kill(
                c, animal.creature_type, self.novac_target_token(animal)):
            await session.send(quest_progress_popup(
                f"You killed the {objective.name} the Tallykeeper asked for "
                f"{quest.title}. Return to Tallykeeper Ysolde."))
        drops = self.roll_creature_drops(animal)
        if modern := getattr(self, "modern", None):
            for drop_name, drop_quantity in drops:
                modern.record_economy(
                    "creature_drop", c.username,
                    counterparty=animal.species,
                    item_name=drop_name, quantity=drop_quantity,
                    item_flow="source",
                    metadata={"actor_id": animal.actor_id,
                              "map_id": animal.map_id,
                              "invasion": bool(animal.invasion)})
        if c.autogather and drops and self.can_add_inventory(c, drops):
            for name, quantity in drops:
                self.add_inventory(
                    c, name, quantity,
                    source=f"creature_drop:{animal.species}")
            await session.send(p.inventory_packet(
                c.inventory, ITEMS, c.equipment, c.inventory_slots))
            await session.send(stats_packet(c))
            await session.send(p.raw_text("Gathered: " + ", ".join(
                f"{quantity} {name}" for name, quantity in drops)))
            await self.walkthrough_event(session, "loot")
        elif drops:
            drop_bag_id = await self.drop_into_bag(
                animal.x, animal.y, drops, animal.map_id)
            self.create_tracked_bag_items(
                drop_bag_id, drops,
                source=f"creature_drop:{animal.species}",
                actor=c.username)
            if lantern.on_island(c): await lantern.sync(self, session)
            if bell.on_map(c): await bell.sync(self, session)
            if c.autogather:
                await session.send(p.raw_text(
                    "Not enough carry capacity for every drop; "
                    "all drops were placed in a bag."))
        self.save_soon(c)
        await session.send(p.raw_text(
            f"You killed a {bell.actor_label(animal)}. Total: {c.kills[animal.species]}."))
        if animal.spawn_group:
            return
        if animal.invasion:
            asyncio.create_task(self._remove_dead_invasion(animal))
        else:
            asyncio.create_task(self._respawn(animal))

    async def apply_glow_swing(self, session: Session) -> None:
        """Deal the active glow perk's radiation damage to every combat enemy."""
        c = session.character
        if (not c or not c.has_perk("I Glow in the Dark")
                or not bool(c.quest_state.get("glow_active", False))):
            return
        target_ids = set(session.aggressors)
        if session.combat_target is not None:
            target_ids.add(session.combat_target)
        primary_id = session.combat_target
        for actor_id in sorted(target_ids):
            animal = self.animals.get(actor_id)
            if (not animal or not animal.alive or animal.health <= 0
                    or animal.map_id != c.map_id):
                continue
            dealt = min(5, animal.health)
            animal.health -= dealt
            await self.broadcast_map(
                animal.map_id, p.actor_damage(animal.actor_id, dealt))
            await self.process_boss_response(animal)
            if animal.health <= 0 and actor_id != primary_id:
                await self.finish_ranged_kill(
                    session, animal, count_ranging=False)

    async def ranging_loop(self, session: Session, target_id: int) -> None:
        c = session.character
        source_map = c.map_id if c else ""
        token = session.coordinate_token() if session.coordinate_state is not None else None
        task = asyncio.current_task()
        try:
            while c and c.health > 0 and not player_in_combat(session):
                if not self.location_context_current(session, source_map, token):
                    break
                animal = self.animals.get(target_id)
                if (session.ranging_target != target_id or not animal
                        or not animal.alive or animal.map_id != c.map_id):
                    break
                loadout = equipped_ranging_items(c)
                if not loadout:
                    await session.send(p.raw_text(
                        "Ranging stopped: equip a compatible bow and ammunition."))
                    break
                weapon_name, ammunition_name = loadout
                distance = actor_distance(c, animal)
                await self.face_toward(c, animal)
                if not self.location_context_current(session, source_map, token):
                    break
                await self.broadcast_map(
                    c.map_id, p.missile_aim(c.actor_id, animal.actor_id))
                await asyncio.sleep(0.25)
                if session.ranging_target != target_id or not self.location_context_current(session, source_map, token):
                    break
                await self.consume_ranging_ammunition(
                    session, weapon_name, ammunition_name)
                if not self.location_context_current(session, source_map, token):
                    break
                target_moving = (
                    time.monotonic() - animal.last_moved_at <= 0.75)
                struck = ranging_critical(c) > random.randrange(100) or (
                    random.random() < hit_chance(
                        c, weapon_name, ammunition_name, distance,
                        moving=target_moving,
                        sigmoid_midpoint=self.settings.ranging_hit_sigmoid_midpoint,
                        sigmoid_scale=self.settings.ranging_hit_sigmoid_scale,
                        minimum_chance=(
                            self.settings.ranging_hit_min_chance_permyriad
                            / 10_000.0),
                        maximum_chance=(
                            self.settings.ranging_hit_max_chance_permyriad
                            / 10_000.0)))
                # Where the arrow goes is the server's to decide, so it is
                # stated. A miss drawn as a shot at the target it missed is the
                # one thing it demonstrably was not.
                if struck:
                    await self.broadcast_map(
                        c.map_id, p.missile_fire(c.actor_id, animal.actor_id))
                else:
                    bounds = session.coordinate_state.catalog.profile(source_map).bounds if token else None
                    stray_x, stray_y = self.stray_arrow_tile(c, animal, bounds)
                    await self.broadcast_coordinates(source_map,
                        lambda point: p.missile_fire_at_ground(c.actor_id, *point(stray_x, stray_y)))
                if not self.location_context_current(session, source_map, token):
                    break
                if struck:
                    attacker_gear = equipment_stats(c.equipment)
                    defender_gear = equipment_stats(animal.equipment)
                    armor = defender_gear["armor"]
                    assert isinstance(armor, tuple)
                    armor_value = (
                        random.randint(*armor) if armor != (0, 0) else 0)
                    definition = self.creatures[animal.creature_type]
                    innate_armor = (definition.armor_min, definition.armor_max)
                    armor_value += (
                        random.randint(*innate_armor)
                        if innate_armor != (0, 0) else 0)
                    archery_ap = min(100, max(
                        0, int(attacker_gear["archery_ap"])
                        + c.combat_bonuses.get("archery_ap", 0)))
                    bypass_armor = random.randrange(100) < archery_ap
                    armor_value = int(armor_value * (1.0 - armor_pierced(c)))
                    damage = ranged_damage(
                        c, distance, armor=armor_value,
                        missile_protection=int(
                            defender_gear["missile_protection"]),
                        bypass_armor=bypass_armor,
                        heat_protection=int(
                            defender_gear["heat_protection"]),
                        cold_protection=int(
                            defender_gear["cold_protection"]),
                        magic_protection=int(
                            defender_gear["magic_protection"]),
                        radiation_protection=int(
                            defender_gear["radiation_protection"]))
                    # An arrow into something enormous is still an arrow
                    # into something enormous, and so is an arrow into a boss.
                    damage = int(round(damage * (
                        1.0 + self.attacker_damage_bonus(c, animal))))
                    damage += await self.apply_item_effects(
                        c, animal, session, "on_hit")
                    await self.apply_item_effects(
                        animal, c, None, "when_hit", session)
                    if not self.location_context_current(session, source_map, token):
                        break
                    animal.health = max(0, animal.health - damage)
                    animal.ranged_aggressor_id = c.actor_id
                    animal.pursuit_retry_at = 0.0
                    roads.emit(self,session,"shot")
                    await bell.event(self, session, "shot")
                    await self.broadcast_map(
                        animal.map_id, p.actor_damage(animal.actor_id, damage))
                    await self.process_boss_response(animal)
                    await self.award_ranging_hit_xp(
                        session, animal.defense, distance, target_moving)
                    if not animal.health:
                        await self.finish_ranged_kill(session, animal)
                        break
                if not equipped_ranging_items(c):
                    await session.send(p.raw_text(
                        "Ranging stopped: you ran out of ammunition."))
                    break
                await asyncio.sleep(max(
                    0.0, shot_interval(weapon_name, ammunition_name) - 0.25))
        except asyncio.CancelledError:
            return
        finally:
            if session.ranging_task is task:
                session.ranging_task = None
                session.ranging_target = None
            if c:
                self.save_soon(c)

    async def player_ranging_loop(
            self, session: Session, target: Session) -> None:
        attacker = session.character
        task = asyncio.current_task()
        try:
            while attacker and attacker.health > 0 and not player_in_combat(session):
                defender = target.character
                zone = (self.raid_combat_zone(attacker, defender)
                        if defender is not None else None)
                if (session.ranging_target != (
                        defender.actor_id if defender else None) or not zone
                        or defender.health <= 0):
                    break
                loadout = equipped_ranging_items(attacker)
                if not loadout:
                    await session.send(p.raw_text(
                        "Ranging stopped: equip a compatible bow and ammunition."))
                    break
                weapon_name, ammunition_name = loadout
                distance = max(abs(attacker.x-defender.x), abs(attacker.y-defender.y))
                await self.face_toward(attacker, defender)
                await self.broadcast_map(
                    attacker.map_id,
                    p.missile_aim(attacker.actor_id, defender.actor_id))
                await asyncio.sleep(0.25)
                if session.ranging_target != defender.actor_id:
                    break
                await self.broadcast_map(
                    attacker.map_id,
                    p.missile_fire(attacker.actor_id, defender.actor_id))
                await self.consume_ranging_ammunition(
                    session, weapon_name, ammunition_name)
                # Register 020, Lucky Archer: a share of shots that cannot
                # miss, the ranged twin of a weapon's critical to hit.
                if ranging_critical(attacker) > random.randrange(100) or (
                        random.random() < hit_chance(
                        attacker, weapon_name, ammunition_name, distance,
                        sigmoid_midpoint=self.settings.ranging_hit_sigmoid_midpoint,
                        sigmoid_scale=self.settings.ranging_hit_sigmoid_scale,
                        minimum_chance=(
                            self.settings.ranging_hit_min_chance_permyriad
                            / 10_000.0),
                        maximum_chance=(
                            self.settings.ranging_hit_max_chance_permyriad
                            / 10_000.0))):
                    attacker_gear = equipment_stats(attacker.equipment)
                    defender_gear = equipment_stats(defender.equipment)
                    armor = defender_gear["armor"]
                    assert isinstance(armor, tuple)
                    armor_value = (
                        random.randint(*armor) if armor != (0, 0) else 0)
                    archery_ap = min(100, max(
                        0, int(attacker_gear["archery_ap"])
                        + attacker.combat_bonuses.get("archery_ap", 0)))
                    bypass_armor = random.randrange(100) < archery_ap
                    buffs = self.melee_magic_bonuses(target)
                    armor_value = int(armor_value * (1.0 - armor_pierced(attacker)))
                    damage = ranged_damage(
                        attacker, distance,
                        armor=armor_value + self.standard_bearer_armor(defender),
                        missile_protection=int(
                            defender_gear["missile_protection"]),
                        bypass_armor=bypass_armor,
                        heat_protection=(
                            int(defender_gear["heat_protection"])
                            + buffs["heat_protection"]),
                        cold_protection=(
                            int(defender_gear["cold_protection"])
                            + buffs["cold_protection"]),
                        magic_protection=(
                            int(defender_gear["magic_protection"])
                            + buffs["magic_protection"]),
                        radiation_protection=(
                            int(defender_gear["radiation_protection"])
                            + buffs["radiation_protection"]))
                    damage += await self.apply_item_effects(
                        attacker, defender, session, "on_hit", target)
                    await self.apply_item_effects(
                        defender, attacker, target, "when_hit", session)
                    await self.award_ranging_hit_xp(
                        session, capped_level(defender.skills["defense"], zone),
                        distance, False)
                    if await self.damage_player(target, damage, cause=attacker.name):
                        await session.send(p.raw_text(
                            f"You killed {defender.name}."))
                        await target.send(p.raw_text(
                            f"You were killed by {attacker.name}."))
                        break
                if not equipped_ranging_items(attacker):
                    await session.send(p.raw_text(
                        "Ranging stopped: you ran out of ammunition."))
                    break
                await asyncio.sleep(max(
                    0.0, shot_interval(weapon_name, ammunition_name) - 0.25))
        except asyncio.CancelledError:
            return
        finally:
            if session.ranging_task is task:
                session.ranging_task = None
                session.ranging_target = None
            if attacker:
                self.save_soon(attacker)

    async def request_attack(self, session: Session, target_id: int):
        """Approach a clicked creature and begin combat when in range."""
        c = session.character
        if self.special_day_has("peace") and not lantern.on_island(c) and not bell.on_map(c) and not sky.on_map(c):
            await session.send(p.raw_text("Combat is disabled during Peace Day."))
            return
        if bell.on_map(c) and equipped_ranging_items(c) and target_id in self.animals and not bell.combat_allowed(c, self.animals[target_id]):
            await session.send(p.raw_text("Leave the refuge before engaging. The court is a recovery area."))
            return
        player_target = self.find_player_by_actor(target_id)
        if player_target and player_target is not session:
            if c and equipped_ranging_items(c):
                await self.start_player_ranging(session, player_target)
            else:
                await self.request_player_attack(session, player_target)
            return
        animal = self.animals.get(target_id)
        if not c or not animal or not animal.alive or animal.map_id != c.map_id:
            return
        if livestock.is_tame(animal):
            await session.send(p.raw_text(livestock.REFUSAL))
            return
        raid_actor_team = self.territory_raids.actor_teams.get(target_id)
        if (raid_actor_team
                and self.territory_raids.team_for(c.username) == raid_actor_team):
            await session.send(p.raw_text("You cannot attack your own raid force."))
            return
        if equipped_ranging_items(c):
            await self.start_ranging(session, target_id)
            return
        standing = session.combat_target
        if standing is not None:
            if not self.fighting_standing_target(session):
                # A claim with no loop behind it is not a fight, and must not be
                # allowed to answer for one. It is what an engage that ended
                # before its first round leaves, and while it stood the click on
                # that creature was the one click the server ignored in silence,
                # and the click on any other creature "That creature is not
                # fighting you." See `attack`, which gives its claim back for
                # the same reason.
                session.combat_target = None
            elif self.within_engage_distance(c, standing):
                # A fight the player is actually in. One at a time, and only an
                # attacker of theirs may take the place of the one they face.
                if target_id == standing:
                    return
                if target_id not in session.aggressors:
                    await session.send(p.raw_text("That creature is not fighting you."))
                    return
                await self.switch_combat_target(session, animal)
                return
            elif target_id == standing:
                # Swinging at something further off than a swing can carry -
                # `attack` has no distance check, so a fight the player has
                # walked out of runs until the creature dies. Clicking it is a
                # player asking to close that gap, so close it.
                self.approach_target(session, target_id)
                return
            else:
                # And it must not refuse every *other* creature on the player's
                # behalf either. This is the shape the report came in as: a
                # field of loose creatures, one fight latched on to something
                # out of reach, and every click answered "That creature is not
                # fighting you." - a line the chat log fades away before it is
                # read.
                await self.switch_combat_target(session, animal)
                return
        self.approach_target(session, target_id)

    def within_engage_distance(self, c: Character, actor_id: int) -> bool:
        """Whether the player is close enough to this creature to be fighting it.

        The same number `attack` consults before it opens a fight - the
        creature's strike distance, one tile of contact for anything melee: a
        distance that would not let one start is a distance that should not let
        one go on speaking for the player. A duel answers True - which player
        may hit which is `attack_player`'s to say, not this.
        """
        animal = self.animals.get(actor_id)
        if animal is None:
            return True
        if not animal.alive or animal.map_id != c.map_id:
            return False
        return actor_distance(c, animal) <= PLAYER_STRIKE_DISTANCE

    def approach_target(self, session: Session, target_id: int) -> None:
        """Walk the player to a creature and open combat when they arrive.

        Its own method because `attack` needs it too, and reaching back into
        `request_attack` for it was the bug: that one is the click handler, and
        it declines a target the session already holds.
        """
        session.pending_attack = target_id
        if session.move_task and not session.move_task.done():
            session.move_task.cancel()
        session.move_task = asyncio.create_task(self._approach_and_attack(session, target_id))

    def fighting_standing_target(self, session: Session) -> bool:
        """Whether an attack loop is really running for `session.combat_target`.

        The flag and the fight are separate things: every retarget claims
        `combat_target` before it starts the coroutine that swings, and any of
        the ways that coroutine can decline - the creature died in between, or
        it is out of engage distance - leaves the claim standing with nothing
        behind it. `player_attacks` holds a key per running loop, so it answers
        the question the claim cannot. A duel is live by the fact of the
        opponent: `attack_player` runs one loop for the pair rather than one
        per side, so it registers no key here.
        """
        c = session.character
        target_id = session.combat_target
        if not c or target_id is None:
            return False
        if (c.actor_id, target_id) in self.player_attacks:
            return True
        return self.find_player_by_actor(target_id) is not None

    async def switch_combat_target(self, session: Session, animal, *,
                                   approach: bool = True) -> None:
        """Make `animal` the creature the player faces and swings at.

        The old attack coroutine observes the changed primary target and
        exits; exactly one loop is started for the newly faced creature.

        `approach` is whether the player walks to it when it turns out to be
        out of engage distance. True for the click that asked for this target,
        false when the server picked it - being carried off to a creature you
        never pointed at is not a retarget.
        """
        c = session.character
        if not c:
            return
        previous = session.combat_target
        session.combat_target = animal.actor_id
        session.combat_xp_events.setdefault(animal.actor_id, [0, 0])
        await self.face_each_other(c, animal)
        if (c.actor_id, animal.actor_id) not in self.player_attacks:
            asyncio.create_task(self.attack(
                c, animal.actor_id, session, announce_conflict=False,
                approach=approach))
        if previous is not None:
            self.player_attacks.discard((c.actor_id, previous))

    def combat_target_mode(self, session: Session) -> int:
        """How this player wants their target chosen among their attackers."""
        c = session.character
        if not c:
            return COMBAT_TARGET_HOLD
        mode = int(c.quest_state.get("combat_target_mode", COMBAT_TARGET_HOLD))
        return mode if mode in COMBAT_TARGET_LABELS else COMBAT_TARGET_HOLD

    def creature_combat_rating(self, animal) -> int:
        """How strong a creature is, on the scale the invasion assistant shows.

        The species' rating rather than the animal's remaining health: a
        player who set "strongest" means the Legendary one, not whichever of
        them they have hurt least, and a rating that moved as a fight went on
        would swap their target every few swings.
        """
        definition = self.creatures.get(animal.creature_type)
        if definition is None:
            return 0
        return int(creature_strength(definition)["rating"])

    async def engage_preferred_target(self, session: Session, joining) -> None:
        """Point the player at whichever attacker their preference names.

        Called as each aggressor opens combat. It claims `combat_target`
        before its first await, so several creatures engaging in one tick see
        a target that is already set and compare against it, rather than all
        seeing None and racing to be the one the player happens to face.

        Comparing the newcomer against the standing target is enough to track
        the strongest or weakest of the whole crowd, because attackers arrive
        one at a time and the standing target is the best of those so far. A
        tie keeps the target: switching between two equals would be churn.
        """
        c = session.character
        if not c:
            return
        current_id = session.combat_target
        current = self.animals.get(current_id) if current_id is not None else None
        if current is not None and (not current.alive
                                    or current.map_id != c.map_id):
            current = None
        if current is None:
            # Nothing to weigh against: the first attacker is the target
            # whatever the preference says, including "keep my target".
            await self.switch_combat_target(session, joining, approach=False)
            return
        if current.actor_id == joining.actor_id:
            return
        mode = self.combat_target_mode(session)
        if mode == COMBAT_TARGET_HOLD:
            return
        standing = self.creature_combat_rating(current)
        arriving = self.creature_combat_rating(joining)
        stronger = arriving > standing
        weaker = arriving < standing
        if (stronger if mode == COMBAT_TARGET_STRONGEST else weaker):
            await self.switch_combat_target(session, joining, approach=False)

    async def open_combat_target(self, session: Session) -> None:
        """Ask the player which of several attackers they want to face.

        A standing preference on the character, so it is settable out of
        combat - which is the only time a player can read the options without
        being hit while they do it. `#targetmode` with a word after it sets
        the same preference without the popup, which is how it was set before
        it had one.
        """
        if not session.character:
            return
        await session.send(p.display_popup(
            COMBAT_TARGET_POPUP, "Combat Target",
            "When more than one creature attacks you, choose which of them "
            "you turn to fight.",
            COMBAT_TARGET_OPTIONS, option_type=p.POPUP_RADIOOPTION))

    async def set_combat_target_mode(self, session: Session, value: int) -> None:
        character = session.character
        label = COMBAT_TARGET_LABELS.get(value)
        if not character or label is None:
            return
        character.quest_state["combat_target_mode"] = value
        self.db.save(character)
        await session.send(p.raw_text(f"Combat target set to: {label}."))

    async def request_player_attack(
            self, session: Session, target: Session) -> None:
        attacker, defender = session.character, target.character
        if not attacker or not defender:
            return
        zone = self.raid_combat_zone(attacker, defender)
        if not zone:
            await session.send(p.raw_text(
                "You can only attack an opposing raid player or a player in the same PK area."))
            return
        duel_key = tuple(sorted((attacker.actor_id, defender.actor_id)))
        if (duel_key in self.pk_duels
                or (session.combat_target == defender.actor_id
                    and target.combat_target == attacker.actor_id)):
            return
        if session.combat_target not in (None, defender.actor_id):
            await session.send(p.raw_text("You are already in combat."))
            return
        if target.combat_target not in (None, attacker.actor_id):
            if not zone.multi_combat:
                await session.send(p.raw_text(
                    f"{defender.name} is already fighting another player."))
                return
        session.pending_attack = defender.actor_id
        if session.move_task and not session.move_task.done():
            session.move_task.cancel()
        session.move_task = asyncio.create_task(
            self._approach_and_attack_player(session, target))

    async def _approach_and_attack_player(
            self, session: Session, target: Session) -> None:
        attacker = session.character
        try:
            for _ in range(128):
                defender = target.character
                if (not attacker or not defender
                        or session.pending_attack != defender.actor_id
                        or not self.raid_combat_zone(attacker, defender)):
                    return
                distance = actor_distance(attacker, defender)
                if distance <= STOP_MOVING_DISTANCE:
                    await self.stop_moving_attack_target(attacker, defender)
                if distance <= PLAYER_STRIKE_DISTANCE:
                    session.pending_attack = None
                    await self.attack_player(session, target)
                    return
                step = self.player_approach_step(attacker, defender)
                if step is None:
                    session.pending_attack = None
                    await session.send(p.raw_text(
                        f"You cannot reach {defender.name}."))
                    return
                dx, dy = step
                command = movement_direction(dx, dy, attacker.running)
                if command is None:
                    return
                await self.await_player_step(session, attacker, dx, dy)
                attacker.x, attacker.y = attacker.x + dx, attacker.y + dy
                attacker.rotation = facing_rotation(dx, dy)
                await self.broadcast_map(
                    attacker.map_id,
                    p.actor_command(attacker.actor_id, command))
        except asyncio.CancelledError:
            return
        finally:
            if attacker and session.pending_attack == (
                    target.character.actor_id if target.character else None):
                session.pending_attack = None

    async def award_pvp_event_xp(
            self, session: Session, opponent: Character, zone: PKZone, *,
            attack: bool = False, dodge: bool = False) -> None:
        character = session.character
        if not character:
            return
        counts = session.combat_xp_events.setdefault(opponent.actor_id, [0, 0])
        attack_xp, defense_xp = combat_experience(
            character, capped_level(opponent.skills["attack"], zone),
            capped_level(opponent.skills["defense"], zone))
        award_attack = attack and counts[0] < COMBAT_XP_EVENT_CAP
        award_defense = dodge and counts[1] < COMBAT_XP_EVENT_CAP
        if award_attack:
            counts[0] += 1
        if award_defense:
            counts[1] += 1
        attack_xp = (int(attack_xp * self.experience_multiplier("attack", character))
                     if award_attack else 0)
        defense_xp = (int(defense_xp * self.experience_multiplier("defense", character))
                      if award_defense else 0)
        if attack_xp or defense_xp:
            levels = award_combat_xp(character, attack_xp, defense_xp)
            await self.send_combat_xp(
                session, attack=bool(attack_xp), defense=bool(defense_xp))
            await self.announce_levels(session, levels)

    async def attack_player(self, first: Session, second: Session) -> None:
        first_character, second_character = first.character, second.character
        if not first_character or not second_character:
            return
        duel_key = tuple(sorted((first_character.actor_id,
                                 second_character.actor_id)))
        if duel_key in self.pk_duels:
            return
        zone = self.raid_combat_zone(first_character, second_character)
        if not zone:
            return
        self.pk_duels.add(duel_key)
        first.pending_attack = second.pending_attack = None
        first.combat_target = second_character.actor_id
        second.combat_target = first_character.actor_id
        first.aggressors.add(second_character.actor_id)
        second.aggressors.add(first_character.actor_id)
        first.combat_xp_events.setdefault(second_character.actor_id, [0, 0])
        second.combat_xp_events.setdefault(first_character.actor_id, [0, 0])
        await self.face_each_other(first_character, second_character)
        await self.broadcast_map(first_character.map_id, p.actor_commands([
            (first_character.actor_id, p.CMD_ENTER_COMBAT),
            (second_character.actor_id, p.CMD_ENTER_COMBAT)]))
        try:
            while (first_character.health > 0 and second_character.health > 0
                   and not first.fleeing and not second.fleeing
                   and first.combat_target == second_character.actor_id
                   and second.combat_target == first_character.actor_id):
                if not self.raid_combat_zone(first_character, second_character):
                    break
                for attacker_session, defender_session in (
                        (first, second), (second, first)):
                    attacker = attacker_session.character
                    defender = defender_session.character
                    if not attacker or not defender or defender.health <= 0:
                        break
                    zone = self.raid_combat_zone(attacker, defender)
                    if not zone:
                        break
                    if self.flee_round_remaining(attacker_session):
                        # This one turned to run and lost the swing for it.
                        # The other still takes theirs, which is the whole
                        # risk of trying to leave a fight.
                        continue
                    await self.broadcast_map(
                        attacker.map_id,
                        p.actor_command(attacker.actor_id, p.CMD_ATTACK_UP_1))
                    attacker_gear = equipment_stats(attacker.equipment)
                    defender_gear = equipment_stats(defender.equipment)
                    attack_level = capped_level(attacker.skills["attack"], zone)
                    defense_level = capped_level(defender.skills["defense"], zone)
                    hit = self.resolve_melee_hit(
                        attack=attack_level,
                        dexterity=player_dexterity(attacker),
                        accuracy=(int(attacker_gear["accuracy"])
                                  + attacker.temporary_combat.get("accuracy", 0)),
                        defense=defense_level,
                        reaction=player_reaction(defender),
                        defense_bonus=(int(defender_gear["defense"])
                                       + defender.temporary_combat.get("evasion", 0)
                                       - dual_wield_penalty(defender)),
                        attacker_vanquisher=attacker.has_perk("Vanquisher"),
                        defender_vanquisher=defender.has_perk("Vanquisher"),
                        attacker_luck=melee_hit_luck(attacker),
                        defender_luck=melee_dodge_luck(defender),
                        critical_to_hit=int(attacker_gear["critical_to_hit"]))
                    if not hit:
                        await self.award_pvp_event_xp(
                            defender_session, attacker, zone, dodge=True)
                        continue
                    damage = self.resolve_melee_damage(
                        attacker, defender, attacker_gear, defender_gear,
                        attacker_session=attacker_session,
                        defender_session=defender_session)
                    bonus_damage = await self.apply_item_effects(
                        attacker, defender, attacker_session, "on_hit",
                        defender_session)
                    bonus_damage += await self.apply_item_effects(
                        defender, attacker, defender_session, "when_hit",
                        attacker_session)
                    await self.apply_normal_combat_wear(
                        attacker, True, attacker_session, defender_session)
                    await self.apply_normal_combat_wear(
                        defender, False, defender_session, attacker_session)
                    await self.award_pvp_event_xp(
                        attacker_session, defender, zone, attack=True)
                    if await self.damage_player(
                            defender_session, damage.total + bonus_damage,
                            cause=attacker.name):
                        await attacker_session.send(p.raw_text(
                            f"You killed {defender.name}."))
                        await defender_session.send(p.raw_text(
                            f"You were killed by {attacker.name}."))
                        break
                if first_character.health <= 0 or second_character.health <= 0:
                    break
                await asyncio.sleep(min(
                    self.player_combat_round_interval(first_character),
                    self.player_combat_round_interval(second_character)))
        finally:
            self.pk_duels.discard(duel_key)
            for participant, opponent in (
                    (first, second_character), (second, first_character)):
                participant.pending_attack = None
                if participant.combat_target == opponent.actor_id:
                    participant.combat_target = None
                participant.aggressors.discard(opponent.actor_id)
                participant.combat_xp_events.pop(opponent.actor_id, None)
            await self.broadcast_map(first_character.map_id, p.actor_commands([
                (first_character.actor_id, p.CMD_LEAVE_COMBAT),
                (second_character.actor_id, p.CMD_LEAVE_COMBAT)]))
            self.save_soon(first_character)
            self.save_soon(second_character)

    def choose_combat_target(self, session: Session) -> Animal | None:
        """Which of the creatures still on the player their target dying hands
        them to, under the preference they set.

        Picking one at all is not a change of target - there is nothing left
        to change from - so "keep my target" is answered here too. It just has
        no opinion about strength, and takes whichever of them engaged first.
        """
        choices = [self.animals[actor_id] for actor_id in session.aggressors
                   if actor_id in self.animals and self.animals[actor_id].alive]
        if not choices:
            return None
        mode = self.combat_target_mode(session)
        if mode == COMBAT_TARGET_HOLD:
            return min(choices, key=lambda animal: animal.actor_id)
        strength = lambda animal: (self.creature_combat_rating(animal),
                                   animal.max_health, animal.actor_id)
        return (max if mode == COMBAT_TARGET_STRONGEST
                else min)(choices, key=strength)

    def melee_magic_bonuses(self, session: Session | None) -> dict[str, int]:
        """Translate active protection spells into melee damage modifiers."""
        if session is None:
            return {
                "attack": 0, "defense": 0, "heat_protection": 0,
                "cold_protection": 0, "magic_protection": 0,
                "radiation_protection": 0,
            }
        return {
            "attack": 0,
            "defense": 3 * self.buff_power(session, 0),
            "magic_protection": 3 * self.buff_power(session, 1),
            "cold_protection": 3 * self.buff_power(session, 23),
            "heat_protection": 3 * self.buff_power(session, 24),
            "radiation_protection": 3 * self.buff_power(session, 25),
        }

    def resolve_melee_damage(
            self, attacker: Character | Animal, defender: Character | Animal,
            attacker_gear: dict[str, int | tuple[int, int]],
            defender_gear: dict[str, int | tuple[int, int]], *,
            attacker_session: Session | None = None,
            defender_session: Session | None = None) -> MeleeDamage:
        """Build the shared damage equation from player or creature stats."""
        weapon = attacker_gear["damage"]
        armor = defender_gear["armor"]
        assert isinstance(weapon, tuple)
        assert isinstance(armor, tuple)
        if isinstance(attacker, Character):
            # Armour piercing takes its share off both ends of the range, so
            # it is worth the same against a defender whose armour rolls low
            # as against one whose armour rolls high.
            pierced = armor_pierced(attacker)
            if pierced:
                keep = 1.0 - pierced
                armor = (int(armor[0] * keep), int(armor[1] * keep))
            # A two-handed weapon hits harder in the hands that trained for it.
            bonus, _cost = two_handed(attacker)
            if bonus and wields_two_handed(attacker):
                weapon = (int(round(weapon[0] * (1.0 + bonus))),
                          int(round(weapon[1] * (1.0 + bonus))))
        attacker_buffs = self.melee_magic_bonuses(attacker_session)
        defender_buffs = self.melee_magic_bonuses(defender_session)

        if isinstance(attacker, Character):
            weapon = weapon if weapon != (0, 0) else (1, 3)
            innate_damage = (0, 0)
            might_value = might(attacker)
            attack_skill = attacker.skills["attack"]
        else:
            definition = self.creatures[attacker.creature_type]
            innate_damage = self.creature_damage_range(attacker)
            might_value = creature_might(definition)
            attack_skill = attacker.attack

        if isinstance(defender, Character):
            # A player has no innate armour of their own, which is the hole
            # the standard fills: it is armour that came from standing near
            # somebody rather than from anything they are wearing.
            standard = self.standard_bearer_armor(defender)
            innate_armor = (standard, standard)
            toughness = player_toughness(defender)
            defense_skill = defender.skills["defense"]
        else:
            definition = self.creatures[defender.creature_type]
            innate_armor = (definition.armor_min, definition.armor_max)
            toughness = creature_toughness(definition)
            defense_skill = defender.defense

        damage = melee_damage(
            weapon_damage=weapon,
            innate_damage=innate_damage,
            might_value=might_value,
            attack_skill=attack_skill,
            attack_magic_bonus=attacker_buffs["attack"],
            armor=armor,
            innate_armor=innate_armor,
            toughness=toughness,
            defense_skill=defense_skill,
            defense_magic_bonus=defender_buffs["defense"],
            heat_damage=(int(attacker_gear["heat_damage"])
                         + attacker.temporary_combat.get("heat_damage", 0)),
            cold_damage=(int(attacker_gear["cold_damage"])
                         + attacker.temporary_combat.get("cold_damage", 0)),
            magic_damage=(int(attacker_gear["magic_damage"])
                          + attacker.temporary_combat.get("magic_damage", 0)),
            radiation_damage=(int(attacker_gear["radiation_damage"])
                              + attacker.temporary_combat.get("radiation_damage", 0)),
            heat_protection=(int(defender_gear["heat_protection"])
                             + defender_buffs["heat_protection"]
                             + defender.temporary_combat.get("heat_protection", 0)),
            cold_protection=(int(defender_gear["cold_protection"])
                             + defender_buffs["cold_protection"]
                             + defender.temporary_combat.get("cold_protection", 0)),
            magic_protection=(int(defender_gear["magic_protection"])
                              + defender_buffs["magic_protection"]
                              + defender.temporary_combat.get("magic_protection", 0)),
            radiation_protection=(int(defender_gear["radiation_protection"])
                                  + defender_buffs["radiation_protection"]
                                  + defender.temporary_combat.get("radiation_protection", 0)),
            critical_to_damage=int(attacker_gear["critical_to_damage"]))
        if isinstance(attacker, Character):
            damage = damage.scaled(1.0 + self.attacker_damage_bonus(
                attacker, defender))
            extra, _defense = berserker(attacker)
            if extra:
                # Flat, and added after the multipliers: Berserker is a
                # weapon you swing rather than a share of one.
                damage = MeleeDamage(
                    physical=damage.physical + extra, heat=damage.heat,
                    cold=damage.cold, magic=damage.magic,
                    radiation=damage.radiation, critical=damage.critical)
        return damage

    def attacker_damage_bonus(self, attacker: Character, defender) -> float:
        """Every share this attacker adds against this particular defender.

        Summed rather than multiplied together, so three perks that each
        promise a fifth deliver three fifths and not a doubling - which is
        what a player reading three descriptions expects.
        """
        bonus = 0.0
        if not isinstance(defender, Character):
            shape = footprint_of(defender)
            bonus += giantslayer_bonus(attacker, shape.width * shape.depth)
            if getattr(defender, "invasion_boss", False):
                bonus += trophy_hunter_bonus(
                    attacker, getattr(defender, "boss_strength", 1.0))
        if strikes_from_behind(attacker, defender):
            bonus += flanker_bonus(attacker)
        return bonus

    def standard_bearer_armor(self, character: Character) -> int:
        """Armour this character is being lent by a party member's standard.

        The best standard in reach rather than the sum of them, so a party of
        six bearers is a party with one standard: stacking would make the
        perk a thing every member buys instead of a thing one member carries.
        A bearer is inside their own reach, which is why they are not skipped.
        """
        book = self.parties
        if book is None or not character.username:
            return 0
        party = book.party_of(character.username)
        if party is None:
            return 0
        wanted = {str(name).strip().casefold() for name in party.names()}
        best = 0
        for session in list(self.sessions):
            bearer = session.character
            if (bearer is None or bearer.map_id != character.map_id
                    or str(bearer.username).strip().casefold() not in wanted):
                continue
            tiles, armour = standard_bearer_aura(bearer)
            if armour > best and tiles and actor_distance(bearer, character) <= tiles:
                best = armour
        return best

    def resolve_melee_hit(self, **values) -> bool:
        """Apply the server-configured sigmoid to a melee hit/dodge check."""
        return melee_hit(
            **values,
            sigmoid_midpoint=getattr(
                self.settings, "melee_hit_sigmoid_midpoint", 0),
            sigmoid_scale=getattr(
                self.settings, "melee_hit_sigmoid_scale", 10),
            minimum_chance=getattr(
                self.settings, "melee_hit_min_chance_permyriad", 500)
                / 10_000.0,
            maximum_chance=getattr(
                self.settings, "melee_hit_max_chance_permyriad", 9500)
                / 10_000.0)

    @staticmethod
    def player_multicombat_penalty(session: Session) -> int:
        engaged = set(session.aggressors)
        if session.combat_target is not None:
            engaged.add(session.combat_target)
        extra = max(0, len(engaged) - 1)
        if not extra:
            return 0
        # Dancing lowers what each extra opponent costs, rather than scaling
        # the total: the perk was written as an absolute number per opponent
        # and it reads that way in a fight, where the third attacker either
        # costs you three defense or it costs you five.
        per_opponent = multicombat_penalty_per_opponent(session.character)
        penalty = (0 if session.character.has_perk("There is no fork")
                   else per_opponent * extra)
        if session.character.has_perk("I can't dance"):
            penalty += 15
        return penalty

    def creature_multicombat_penalty(self, actor_id: int) -> int:
        attackers = {player_id for player_id, target_id in self.player_attacks
                     if target_id == actor_id}
        return 5 * max(0, len(attackers) - 1)

    def flee_round_remaining(self, session: Session) -> float:
        """Seconds left of the swing this player gave up to turn and run.

        Turning to run costs the round whether or not it works. Without that,
        a failed flee is free: the attempt rolls, the player stands exactly
        where they were, and their next blow lands on the beat it would have
        landed on anyway, which makes trying to leave strictly better than not
        trying.

        Only the player who tried pays it. Creatures and opposing players do
        not consult this, so turning your back leaves them swinging at you -
        which is the risk that makes a retreat a decision.

        A deadline rather than a flag, so a skipped round always ends by
        itself. `session.fleeing` is the flag that stops a fight outright;
        this is not that, and must not be confused for it.
        """
        return max(0.0, session.flee_attempt_until - time.monotonic())

    def flee_succeeds(self, session: Session) -> bool:
        """Whether this attempt to break off gets away.

        Rolled per attempt, so a retreat is something a player commits to
        rather than a free exit taken at one hit of health. The streak limit
        is what keeps that a setback rather than a trap: the attempt after
        `flee_failure_streak_limit` consecutive failures does not roll at all,
        which caps the run of bad luck a player can be handed no matter what
        the percentage is set to. At 100 percent every flee still works on the
        twenty-first try.
        """
        if session.flee_failures >= self.settings.flee_failure_streak_limit:
            return True
        return random.randrange(100) >= self.settings.flee_failure_percent

    async def begin_flee(self, session: Session, target_x: int, target_y: int):
        source_map = session.character.map_id if session.character else None
        token = session.coordinate_token() if session.coordinate_state is not None else None
        c = session.character
        if self.special_day_has("brave") and not bell.on_map(c):
            await session.send(p.raw_text("You cannot flee during the Day of the Brave."))
            return
        if not c or session.fleeing:
            return
        # Set before the roll, because the round is spent on the attempt
        # rather than on the outcome. The Day of the Brave refusal above costs
        # nothing, correctly: there the player never got to try.
        session.flee_attempt_until = (
            time.monotonic() + self.player_combat_round_interval(c))
        if not self.flee_succeeds(session):
            # Rolled before anything is touched, the way the Day of the Brave
            # refusal is: a failed attempt leaves the fight exactly as it was.
            # Nobody is unfrozen, nobody leaves combat, and the player does not
            # take the step they asked for - the flag in particular never goes
            # up, so nothing has to remember to bring it down.
            session.flee_failures += 1
            await session.send(p.raw_text("You failed to get away."))
            return
        session.flee_failures = 0
        engaged = set(session.aggressors)
        if session.combat_target is not None:
            engaged.add(session.combat_target)
        session.fleeing = True
        # Everything from the flag going up is inside the try. The two sends
        # below are awaits like the sleep is, and a cancellation landing on one
        # of them - the click that changes the player's mind arrives on its own
        # schedule, not after the writes have drained - skipped the clear just
        # as surely, for the same permanent result.
        try:
            session.pending_attack = None
            session.combat_target = None
            session.aggressors.clear()
            session.combat_xp_events.clear()
            freeze_until = time.monotonic() + 3.0
            commands = [(c.actor_id, p.CMD_LEAVE_COMBAT)]
            for actor_id in engaged:
                animal = self.animals.get(actor_id)
                if animal:
                    animal.frozen_until = max(animal.frozen_until, freeze_until)
                    commands.append((actor_id, p.CMD_LEAVE_COMBAT))
                    continue
                opponent = self.find_player_by_actor(actor_id)
                if opponent and opponent.character:
                    opponent.aggressors.discard(c.actor_id)
                    if opponent.combat_target == c.actor_id:
                        opponent.combat_target = None
                    opponent.combat_xp_events.pop(c.actor_id, None)
                    commands.append((actor_id, p.CMD_LEAVE_COMBAT))
            await self.broadcast_map(c.map_id, p.actor_commands(commands))
            await session.send(p.raw_text("You begin fleeing from combat."))
            roads.emit(self,session,"fled")
            await bell.event(self, session, "fled")
            await asyncio.sleep(1.0)
        finally:
            # Changing your mind mid-flight cancels this task: request_attack
            # cancels the move task to walk you back to the creature you just
            # clicked. The flag has to come down anyway, because everything
            # that reads it reads it as "still running away" - the player's
            # attack loop and every creature's refuse to swing, begin_flee
            # refuses a second attempt, and the move handler drops the
            # player's steps on the floor. Left raised by a cancellation it
            # did not survive, it took the character out of the game
            # entirely: unable to attack, to be attacked, to walk or to flee.
            session.fleeing = False
        if self.location_context_current(session, source_map, token):
            await self.move(c, target_x, target_y)

    def player_approach_step(self, c: Character, target) -> tuple[int, int] | None:
        """One step of a player's walk to somewhere they can strike `target` from.

        The destination is a tile `attack_anchors` accepts - touching the
        target's body, walkable, and free - and not the target's own anchor,
        which for anything larger than a single tile is a square inside it. A
        step straight at it is tried first and is what happens in the open;
        the search is for what a straight line cannot answer, a creature
        against a wall or behind somebody else.

        None means there is nowhere to attack it from that the player can
        reach. That is a real answer and the caller reports it, rather than
        walking on the spot until the loop runs out.
        """
        shape = footprint_of(c)
        start = (c.x, c.y)
        occupied = self.blocking_tiles(c.map_id, ignore=(c,))
        anchors = self.attack_anchors(
            c.map_id, start, shape, target, occupied,
            nearest=1, furthest=PLAYER_STRIKE_DISTANCE)
        if not anchors:
            return None
        dx = (target.x > c.x) - (target.x < c.x)
        dy = (target.y > c.y) - (target.y < c.y)
        direct = (c.x + dx, c.y + dy)
        if ((dx or dy)
                and not self.anchor_blocked(occupied, *direct, shape, start)
                and self.can_walk_step(c.map_id, start, direct, shape)
                and (not dx or not dy
                     or (self.can_walk_step(
                            c.map_id, start, (c.x + dx, c.y), shape)
                         and self.can_walk_step(
                            c.map_id, start, (c.x, c.y + dy), shape)))):
            return dx, dy
        path = self.find_path_to_any(
            c.map_id, start, anchors,
            self.blocked_anchors(occupied, start, shape, APPROACH_MAX_PATH_STEPS),
            APPROACH_MAX_PATH_STEPS, shape)
        if not path:
            return None
        return path[0][0] - c.x, path[0][1] - c.y

    async def _approach_and_attack(self, session: Session, target_id: int):
        """Walk the player to a tile they can hit this creature from, then hit it.

        Not "towards the creature": melee reaches one tile, so the walk has a
        destination - a square touching the creature's body - and the fight
        opens on arrival there rather than at whatever range the creature
        happened to be noticed from. On the way, a creature that is not
        already fighting somebody is stopped and turned to face the player, so
        it is waiting when the player arrives instead of wandering off.

        Paced by `await_player_step`, the same as any other route this
        character walks. It used to hold a flat 0.22s per step, which was a
        third of the configured pace and ignored the shape of the step - and
        this walk takes diagonals often, because it routes round bodies rather
        than through them. Chasing something is now as fast as the player is,
        which is what `#run` is for.
        """
        c = session.character
        try:
            for _ in range(128):
                animal = self.animals.get(target_id)
                if not c or not animal or not animal.alive or session.pending_attack != target_id:
                    return
                distance = actor_distance(c, animal)
                if distance <= STOP_MOVING_DISTANCE:
                    await self.stop_moving_attack_target(c, animal)
                if distance <= PLAYER_STRIKE_DISTANCE:
                    session.pending_attack = None
                    await self.attack(c, target_id, session)
                    return
                step = self.player_approach_step(c, animal)
                if step is None:
                    session.pending_attack = None
                    await session.send(p.raw_text(
                        "You cannot reach that creature."))
                    return
                dx, dy = step
                command = movement_direction(dx, dy, c.running)
                if command is None:
                    return
                await self.await_player_step(session, c, dx, dy)
                c.x += dx
                c.y += dy
                c.rotation = facing_rotation(dx, dy)
                await self.broadcast_actor(
                    c, p.actor_command(c.actor_id, command))
        except asyncio.CancelledError:
            return
        finally:
            # Only the approach the session is still holding may clear the
            # request. A newer one replaces `move_task` and re-raises
            # `pending_attack`, and an older frame unwinding afterwards used to
            # wipe it, leaving the new task to find nothing to walk towards and
            # return on its first line.
            if (session.pending_attack == target_id
                    and session.move_task is asyncio.current_task()):
                session.pending_attack = None
            if c:
                self.save_soon(c)


    async def apply_mirror(self, session: Session, animal: Animal,
                           taken: int) -> None:
        """Deal a share of a blow back to the creature that landed it.

        The blow still lands in full - this is a riposte, not a shield, and a
        defender who took nothing would be buying immunity under another
        name. Never less than one, so the perk is worth something against the
        small hits as well as the large.

        It can kill, which is why it goes through the same ending a swing
        does. A riposte that reduced a creature to nothing and left it
        standing would be a perk that cannot finish anything.
        """
        c = session.character
        if not c or not animal.alive or taken <= 0:
            return
        share = mirror_share(c)
        if not share:
            return
        dealt = min(animal.health, max(1, int(round(taken * share))))
        if dealt <= 0:
            return
        animal.health -= dealt
        await self.broadcast_actor(animal, p.actor_damage(animal.actor_id, dealt))
        if not animal.health:
            await self.finish_melee_kill(session, animal)

    async def finish_melee_kill(self, session: Session, a: Animal) -> None:
        """Everything that happens when a creature dies to a melee blow.

        Lifted out of the attack loop so that a blow the player did not swing
        can end a creature too: Mirror deals damage back to whoever struck
        you, and a riposte that reduced a creature to nothing but left it
        standing would be a perk that cannot finish anything.

        The caller is the one that stops fighting - this does not break the
        loop it was lifted from, it only does the dying.
        """
        c = session.character
        a.alive = False
        bonuses = []
        for connected in list(self.sessions):
            connected.aggressors.discard(a.actor_id)
            attack_bonus, defense_bonus, level_ups = (
                self.claim_early_kill_bonus(connected, a))
            if attack_bonus or defense_bonus:
                bonuses.append((
                    connected, attack_bonus, defense_bonus, level_ups))
        for connected, attack_bonus, defense_bonus, level_ups in bonuses:
            await self.send_combat_xp(
                connected, attack=bool(attack_bonus),
                defense=bool(defense_bonus))
            await self.announce_levels(connected, level_ups)
            # Experience reports share the deeper green.
            await connected.send(p.colored_text(
                f"Early kill bonus: {attack_bonus} attack and "
                f"{defense_bonus} defense experience.",
                p.EL_COLOR_GREEN3))
        await self.broadcast_actor(
            a, p.actor_command(a.actor_id, p.CMD_DIE1))
        c.kills[a.species] = c.kills.get(a.species, 0) + 1
        await self.notify_tutorial_quarry_kill(session, a)
        await self.walkthrough_event(session, "kill", a.species)
        await self.questline_event(session, "kill", a.species)
        self.record_creature_kill(c, a)
        await self.record_activity(session, ACTIVITY_KILLS)
        self.ensure_novac_targets(c)
        for quest, objective in record_novac_kill(
                c, a.creature_type, self.novac_target_token(a)):
            await session.send(quest_progress_popup(
                f"You killed the {objective.name} the Tallykeeper asked for "
                f"{quest.title}. Return to Tallykeeper Ysolde."))
        drops = self.roll_creature_drops(a)
        if modern := getattr(self, "modern", None):
            for drop_name, drop_quantity in drops:
                modern.record_economy(
                    "creature_drop", c.username,
                    counterparty=a.species,
                    item_name=drop_name, quantity=drop_quantity,
                    item_flow="source",
                    metadata={"actor_id": a.actor_id,
                              "map_id": a.map_id,
                              "invasion": bool(a.invasion)})
        if c.autogather and drops and self.can_add_inventory(c, drops):
            for name, quantity in drops:
                self.add_inventory(
                    c, name, quantity,
                    source=f"creature_drop:{a.species}")
            await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
            await session.send(stats_packet(c))
            await session.send(p.raw_text("Gathered: " + ", ".join(
                f"{quantity} {name}" for name, quantity in drops)))
            await self.walkthrough_event(session, "loot")
        elif drops:
            post_combat_bag = await self.drop_into_bag(a.x, a.y, drops, a.map_id)
            self.create_tracked_bag_items(
                post_combat_bag, drops,
                source=f"creature_drop:{a.species}",
                actor=c.username)
            if lantern.on_island(c): await lantern.sync(self, session)
            if bell.on_map(c): await bell.sync(self, session)
            if c.autogather:
                await session.send(p.raw_text(
                    "Not enough carry capacity for every drop; all drops were placed in a bag."))
        self.save_soon(c)
        await session.send(p.raw_text(f"You killed a {bell.actor_label(a)}. Total: {c.kills[a.species]}."))
        if a.spawn_group:
            # Group members remain dead until the group-level scheduler
            # revives the complete group at second 18 or 48.
            pass
        elif a.summoned:
            asyncio.create_task(self._remove_dead_invasion(a))
        elif not a.invasion:
            asyncio.create_task(self._respawn(a))
        else:
            asyncio.create_task(self._remove_dead_invasion(a))

    def player_combat_round_interval(self, c: Character) -> float:
        """Player attack interval; future equipment/attribute modifiers belong here."""
        return self.settings.player_combat_round_ms / 1000.0

    def creature_combat_round_interval(self, animal: Animal) -> float:
        """Creature attack interval; future species/attribute modifiers belong here."""
        return self.settings.creature_combat_round_ms / 1000.0

    @staticmethod
    def claim_combat_event_xp(
            session: Session, animal: Animal, *, attack: bool = False,
            dodge: bool = False) -> tuple[int, int]:
        """Claim one successful-hit or successful-dodge award below its cap."""
        c = session.character
        if not c:
            return 0, 0
        counts = session.combat_xp_events.setdefault(animal.actor_id, [0, 0])
        attack_xp, defense_xp = combat_experience(c, animal.attack, animal.defense)
        awarded_attack = attack and counts[0] < COMBAT_XP_EVENT_CAP
        awarded_defense = dodge and counts[1] < COMBAT_XP_EVENT_CAP
        if awarded_attack:
            counts[0] += 1
        if awarded_defense:
            counts[1] += 1
        return (attack_xp if awarded_attack else 0,
                defense_xp if awarded_defense else 0)

    async def award_combat_event_xp(
            self, session: Session, animal: Animal, *, attack: bool = False,
            dodge: bool = False) -> None:
        """Award one capped successful-hit or successful-dodge XP event."""
        attack_xp, defense_xp = self.claim_combat_event_xp(
            session, animal, attack=attack, dodge=dodge)
        if not attack_xp and not defense_xp:
            return
        attack_xp = int(attack_xp * self.experience_multiplier("attack", session.character))
        defense_xp = int(defense_xp * self.experience_multiplier("defense", session.character))
        level_ups = award_combat_xp(
            session.character, attack_xp, defense_xp)
        await self.send_combat_xp(
            session, attack=bool(attack_xp), defense=bool(defense_xp))
        await self.announce_levels(session, level_ups)

    def claim_early_kill_bonus(
            self, session: Session, animal: Animal
            ) -> tuple[int, int, list[tuple[str, int, int]]]:
        """Settle and clear half of the XP remaining below each combat cap."""
        c = session.character
        counts = session.combat_xp_events.pop(animal.actor_id, None)
        if not c or counts is None:
            return 0, 0, []
        attack_xp, defense_xp = combat_experience(c, animal.attack, animal.defense)
        attack_bonus = (
            (COMBAT_XP_EVENT_CAP - min(counts[0], COMBAT_XP_EVENT_CAP))
            * attack_xp // 2)
        defense_bonus = (
            (COMBAT_XP_EVENT_CAP - min(counts[1], COMBAT_XP_EVENT_CAP))
            * defense_xp // 2)
        return (attack_bonus, defense_bonus,
                award_combat_xp(c, attack_bonus, defense_bonus))

    def stop_poison(self, session: Session) -> None:
        if session.character:
            spell_task = getattr(self, '_magic_dots', {}).pop((session.character.actor_id, False), None)
            if spell_task and spell_task is not asyncio.current_task():
                spell_task.cancel()
        task = session.poison_task
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
        if task is not asyncio.current_task():
            session.poison_task = None
            session.poison_damage = 0
            session.poison_hits = 0

    async def apply_creature_poison(self, animal: Animal, session: Session) -> None:
        """Poison a player a creature has just landed a hit on.

        Only creatures whose profile says they are venomous, which is none of
        them unless a profile says so. Re-poisoning refreshes rather than
        stacks - `start_poison` cancels whatever was running - so a shooter
        that lands four spores in a row leaves one poisoning, not four, which
        is both what the spell does and the only version that is survivable.
        """
        definition = self.creatures.get(animal.creature_type)
        if definition is None or definition.poison_damage <= 0:
            return
        c = session.character
        if not c or session.dying or c.health <= 0:
            return
        already = session.poison_task
        if already is not None and not already.done():
            # Already poisoned by something. Only a stronger dose takes over,
            # or a creature would keep resetting the clock on a worse one.
            if session.poison_damage >= definition.poison_damage:
                return
        self.start_poison(session, definition.poison_damage)
        await session.send(p.raw_text("You have been poisoned!"))

    def start_creature_rot(self, animal: Animal, damage: int) -> None:
        """Set Rotbrand burning through a creature, replacing any already on it.

        A creature has no poison of its own - `start_poison` and the antidote
        both belong to a session - so the rot is its own small task, on the
        poison loop's own ten-second cadence. Recasting refreshes rather than
        stacks, for the same reason poison refuses to stack: four brands in a
        row would be four times the damage of one and nothing would survive it.
        """
        running = self.creature_rot_tasks.get(animal.actor_id)
        if running is not None and not running.done():
            running.cancel()
        self.creature_rot_tasks[animal.actor_id] = asyncio.create_task(
            self.rot_creature(animal, max(1, damage)))

    async def rot_creature(self, animal: Animal, damage: int) -> None:
        """Bite a branded creature every ten seconds until the rot burns out.

        Like every other offensive spell here it wounds without killing: the
        floor is one point, so a rot cannot take a creature a player never
        engaged and hand nobody the kill.
        """
        task = asyncio.current_task()
        try:
            for _ in range(ROT_TICKS):
                await asyncio.sleep(ROT_TICK_SECONDS)
                if not animal.alive or animal.health <= 1:
                    return
                animal.health = max(1, animal.health - damage)
                await self.broadcast_actor(
                    animal, p.actor_damage(animal.actor_id, damage))
        except asyncio.CancelledError:
            raise
        finally:
            if self.creature_rot_tasks.get(animal.actor_id) is task:
                self.creature_rot_tasks.pop(animal.actor_id, None)

    def start_poison(self, session: Session, damage: int) -> None:
        self.stop_poison(session)
        session.poison_damage = max(1, damage)
        session.poison_hits = 0
        session.poison_task = asyncio.create_task(
            self.poison_player(session, session.poison_damage))

    async def poison_player(self, session: Session, initial_damage: int) -> None:
        """Damage a poisoned player every ten seconds, lowering each third hit."""
        task = asyncio.current_task()
        damage = max(1, initial_damage)
        hits = 0
        try:
            while damage > 0:
                await asyncio.sleep(10)
                c = session.character
                if not c or session.dying or c.health <= 0:
                    break
                session.poison_damage = damage
                session.poison_hits = hits
                if await self.damage_player(session, damage, cause="Poison"):
                    break
                hits += 1
                session.poison_hits = hits
                if hits % 3 == 0:
                    damage -= 1
            if session.character and session.character.health > 0 and not session.dying:
                await session.send(p.raw_text("The poison has worn off."))
        except asyncio.CancelledError:
            return
        finally:
            if session.poison_task is task:
                session.poison_task = None
                session.poison_damage = 0
                session.poison_hits = 0

    async def damage_player(self, session: Session, amount: int, *,
                            cause: str = "Unknown") -> bool:
        """Apply lethal player damage and return whether the player died."""
        c = session.character
        if not c or session.dying:
            return session.dying
        if c.health <= 0:
            # On zero health and not being respawned means a death that went
            # wrong. Answering "already dead" left them standing there for
            # good; carry the death out again instead.
            await self.player_died(session, cause=cause)
            return True
        damage = min(c.health, max(0, amount))
        roads.emit(self,session,"incoming",amount=1,damage=damage)
        if len(session.aggressors | ({session.combat_target} if session.combat_target else set()))>=2:
            roads.emit(self,session,"multi_hit",amount=1,damage=damage)
        if not damage:
            return False
        c.health -= damage
        await self.broadcast_actor(c, p.actor_damage(c.actor_id, damage))
        if c.health > 0:
            await landing_runtime.hurt(self, session)
            return False
        await self.player_died(session, cause=cause)
        return True

    async def create_player_death_bag(
            self, session: Session, zone: PKZone | None) -> int | None:
        """Apply EL's Rostogol, no-drop, and per-slot death-drop rules."""
        c = session.character
        if not c or c.skills["overall"] < NEW_PLAYER_DEATH_LEVEL:
            return None
        rosto = "Rostogol Stone"
        has_rosto = c.inventory.get(rosto, 0) > 0
        no_rosto_day = self.special_day_has("no_rostogols")
        no_rosto_map = bool(zone and zone.no_rostogol)
        if has_rosto and not no_rosto_map:
            c.inventory[rosto] -= 1
            if c.inventory[rosto] <= 0:
                del c.inventory[rosto]
            if not no_rosto_day:
                session.inventory_slots = self.sync_inventory_slots(c)
                return None
        if self.special_day_has("no_drops") or (zone and zone.no_drops):
            session.inventory_slots = self.sync_inventory_slots(c)
            return None

        undroppable = {
            "Leather Helm", "Iron Helm", "Steel Helm", "Padded Leather Armor",
            "Iron Chain Mail", "Steel Chain Mail", "Leather Pants",
            "Leather Boots", "Wooden Shield", "Enhanced Wooden Shield",
            "Iron Shield", "Steel Shield", "Iron Sword", "Gold Coins",
            "Creature food",
        }
        drop_chance = 0.4 if c.has_perk("Careful Guy") else 0.5
        kept = (dict(c.inventory), dict(c.equipment), dict(c.equipment_instances))
        dropped: list[tuple[str, int]] = []
        dropped_instances: list[int] = []
        for name, quantity in list(c.inventory.items()):
            if name not in undroppable and random.random() < drop_chance:
                dropped.append((name, quantity))
                if tracks_instances(name):
                    dropped_instances.extend(
                        instance_id for pos, instance_id
                        in enumerate(c.inventory_instance_slots)
                        if instance_id and c.inventory_slots[pos] == name)
                del c.inventory[name]
        for position, name in list(c.equipment.items()):
            if name not in undroppable and random.random() < drop_chance:
                dropped.append((name, 1))
                instance_id = c.equipment_instances.pop(str(position), None)
                if instance_id:
                    dropped_instances.append(instance_id)
                del c.equipment[position]
        if not dropped:
            session.inventory_slots = self.sync_inventory_slots(c)
            return None
        try:
            bag_id = await self.drop_into_bag(c.x, c.y, dropped, c.map_id)
        except Exception:
            # No bag to put them in (a map out of bag ids after an invasion's
            # kills, say). Keep the items rather than deleting them, and let
            # the respawn go on: raising here used to abandon it, leaving the
            # player where they fell on zero health.
            log.exception("Death drops for %s on %s could not be bagged",
                          c.username, c.map_id)
            c.inventory, c.equipment, c.equipment_instances = kept
            session.inventory_slots = self.sync_inventory_slots(c)
            return None
        for instance_id in dropped_instances:
            self.db.item_instances.transfer(
                instance_id, 1, "bag", str(bag_id),
                actor=c.username, source="death_drop")
        if modern := getattr(self, "modern", None):
            for name, quantity in dropped:
                modern.record_economy(
                    "death_drop", c.username, counterparty=f"bag:{bag_id}",
                    item_name=name, quantity=quantity,
                    gold_flow="none", item_flow="transfer",
                    metadata={"map_id": c.map_id, "bag_id": bag_id})
        session.inventory_slots = self.sync_inventory_slots(c)
        return bag_id

    async def player_died(self, session: Session, *,
                          cause: str = "Unknown") -> None:
        """Apply death drops, then move the player to the beam or underworld."""
        c = session.character
        if not c or session.dying:
            return
        # Claimed before the first await, so a second blow landing while the
        # respawn runs is answered "already dead" instead of starting another.
        session.dying = True
        # The respawn is a string of awaits, and it used to run inside whatever
        # task landed the killing blow - which the fight itself then cancels.
        # A creature's retaliation is a child of the player's `attack()` loop:
        # the respawn clears `combat_target`, which wakes that loop, and it
        # cancels the retaliation from its `finally` while it is still inside
        # `change_map` - leaving the player standing where they fell. Walking during the
        # death does the same to `move_task`. The shielded task finishes the
        # respawn whatever happens to its caller.
        #
        # Started eagerly where the runtime allows, so the death runs up to its
        # first real suspension right here, as it did when it was inline -
        # before the killing blow's own task, or a loop that never yields,
        # gets another look at a player still on zero health.
        death = self._carry_out_death(session, cause)
        if sys.version_info >= (3, 12):
            respawn = asyncio.Task(death, loop=asyncio.get_running_loop(),
                                   eager_start=True)
        else:
            respawn = asyncio.create_task(death)
        RESPAWN_TASKS.add(respawn)
        respawn.add_done_callback(RESPAWN_TASKS.discard)
        await asyncio.shield(respawn)

    async def _carry_out_death(self, session: Session, cause: str) -> None:
        c = session.character
        try:
            if await roads.rescue(self, session):
                return
            if await sky.rescue(self, session):
                return
            if await bell.rescue(self, session):
                return
            if await lantern.rescue(self, session):
                return
            await self._respawn_after_death(session, c, cause)
            await landing_runtime.death(self, session)
        finally:
            session.dying = False

    def _coordinate_death_destination(self, c, session: Session | None = None):
        destination = gauntlets.death_exit(self, c)
        if destination is not None:
            return destination
        raid = self.territory_raids.active
        team = self.territory_raids.team_for(c.username)
        if raid and not raid.finished and team:
            spawn = raid.attacker_entry if team == raid.aggressor.key else raid.defender.defender_spawn
            return raid.defender.map_id, *spawn
        return home.point(self, "respawn" if c.skills['overall'] < NEW_PLAYER_DEATH_LEVEL
                          else "underworld", session)

    async def _respawn_after_death(self, session: Session, c: Character,
                                   cause: str) -> None:
        destination = self._coordinate_death_destination(c, session)
        self.require_coordinate_destination(session, *destination)
        source_map = c.map_id
        token = session.coordinate_token() if session.coordinate_state is not None else None
        # A same-map respawn keeps the actor id. Drop the creature-side
        # memories before yielding so retaliation cannot follow that id to
        # the beam after the player's combat state has been cleared.
        for animal in self.animals.values():
            if animal.ranged_aggressor_id == c.actor_id:
                animal.ranged_aggressor_id = None
                animal.melee_recoil_until = 0.0
            if animal.held_target_id == c.actor_id:
                animal.held_target_id = None
            if animal.pursuit_target_id == c.actor_id:
                animal.pursuit_target_id = None
                animal.pursuit_target_x = animal.pursuit_target_y = 0
                animal.pursuit_path.clear()
                animal.pursuit_retry_at = 0.0
        self.clear_actor_magic(c)
        self.stop_poison(session)
        try:
            raid = self.territory_raids.active
            raid_team = self.territory_raids.team_for(c.username)
            # Everything before the teleport is bookkeeping around the death,
            # and none of it may stop the respawn. An exception here used to
            # leave the player where they fell on zero health, with no message:
            # every later blow was answered "already dead", regeneration
            # refilled the bar, and the next hit did it all again.
            try:
                await self.record_activity(session, ACTIVITY_DEATHS,
                                           detail=cause or "Unknown")
                death_zone = pk_zone_at(c.map_id, c.x, c.y)
                if (raid and not raid.finished and raid_team
                        and c.map_id == raid.defender.map_id):
                    death_zone = PKZone(c.map_id, no_drops=True,
                                        multi_combat=True,
                                        label="territory raid")
                await self.create_player_death_bag(session, death_zone)
                await self.broadcast_actor(
                    c, p.actor_command(c.actor_id, p.CMD_DIE1))
            except Exception:
                log.exception("Death of %s on %s failed before the respawn",
                              c.username, c.map_id)
            current_task = asyncio.current_task()
            if (session.move_task and session.move_task is not current_task
                    and not session.move_task.done()):
                session.move_task.cancel()
            if (session.post_combat_bag_task
                    and session.post_combat_bag_task is not current_task
                    and not session.post_combat_bag_task.done()):
                session.post_combat_bag_task.cancel()
            session.pending_attack = None
            session.combat_target = None
            session.aggressors.clear()
            session.combat_xp_events.clear()
            for connected in list(self.sessions):
                if connected is session or not connected.character:
                    continue
                connected.aggressors.discard(c.actor_id)
                if connected.combat_target == c.actor_id:
                    connected.combat_target = None
                connected.combat_xp_events.pop(c.actor_id, None)
            session.fleeing = True
            if not self.location_context_current(session, source_map, token):
                return
            c.health = DEATH_RESPAWN_HEALTH
            await self.change_map(session, *destination)
            await self.send_stats(session, force=True)
        finally:
            session.fleeing = False

    async def send_combat_state(self, session: Session, target: Animal,
                                event: int = 0, damage: int = 0) -> None:
        c = session.character
        if not c or "combat_hud_v1" not in session.client_capabilities:
            return
        await session.send(p.combat_state(
            event, target.actor_id, c.health, c.max_health, target.health,
            target.max_health, damage, bell.actor_label(target)))

    async def creature_retaliation(self, animal: Animal, session: Session) -> None:
        """Run creature attacks independently from the player's attack cadence."""
        c = session.character
        if not c:
            return
        try:
            # Offset the first counterattack so entering combat does not produce
            # simultaneous player and creature attack animations.
            await asyncio.sleep(self.creature_combat_round_interval(animal) / 2)
            while (animal.alive and c.health > 0 and not session.fleeing
                   and session.combat_target == animal.actor_id):
                await self.face_toward(animal, c)
                gear = equipment_stats(c.equipment)
                creature_gear = equipment_stats(animal.equipment)
                definition = self.creatures[animal.creature_type]
                # A creature with reach may strike only from inside that reach:
                # without the guard a ranged creature would keep hitting a
                # player who has walked out of range, which is the difference
                # between a bow and a curse.
                #
                # Only a creature that has reach, though. Applied to melee it
                # silenced every creature in the profile the moment the player
                # was not exactly adjacent, because nothing closes the gap
                # again: a creature holding a combat lock is skipped by the
                # movement AI, so it stands there unable to swing and unable to
                # step, and the player cannot re-engage it either - clicking
                # the creature you are already targeting is a no-op. The fight
                # deadlocked with both sides idle and the client still showing
                # "In combat".
                if definition.is_ranged:
                    distance = actor_distance(animal, c)
                    if distance > definition.attack_range:
                        # Ending the retaliation rather than waiting out the
                        # round, for the same reason invasion_attack ends when
                        # its target leaves engage range: a loop that neither
                        # swings nor exits is what pinned the melee creatures.
                        return
                    # The client already draws actor-to-actor missiles for
                    # player ranging; the packets take a source actor id and
                    # do not care that this one is a creature.
                    await self.broadcast_actor(
                        animal, p.missile_aim(animal.actor_id, c.actor_id))
                    await self.broadcast_actor(
                        animal, p.missile_fire(animal.actor_id, c.actor_id))
                # The swing itself, which is what the client plays the attack
                # clip on. This loop resolved the round without ever naming it,
                # so a creature the player attacked stood in its combat idle
                # and hit back invisibly; only invasion_attack, the aggressor's
                # loop, sent one.
                await self.broadcast_actor(
                    animal, p.actor_command(animal.actor_id, p.CMD_ATTACK_UP_1))
                creature_hit = self.resolve_melee_hit(
                    attack=animal.attack,
                    dexterity=creature_dexterity(definition),
                    accuracy=(int(creature_gear["accuracy"])
                              + animal.temporary_combat.get("accuracy", 0)),
                    defense=c.skills["defense"],
                    reaction=player_reaction(c),
                    defense_bonus=(int(gear["defense"])
                                   + c.temporary_combat.get("evasion", 0)
                                   - dual_wield_penalty(c)),
                    multicombat_penalty=self.player_multicombat_penalty(session),
                    defender_vanquisher=c.has_perk("Vanquisher"),
                    defender_luck=melee_dodge_luck(c),
                    critical_to_hit=int(creature_gear["critical_to_hit"]))
                if creature_hit:
                    damage = self.resolve_melee_damage(
                        animal, c, creature_gear, gear,
                        defender_session=session)
                    bonus_damage = await self.apply_item_effects(
                        animal, c, None, "on_hit", session)
                    bonus_damage += await self.apply_item_effects(
                        c, animal, session, "when_hit")
                    await self.apply_normal_combat_wear(
                        animal, True, observer_session=session)
                    await self.apply_normal_combat_wear(
                        c, False, owner_session=session)
                    total_damage = damage.total + bonus_damage
                    died = await self.damage_player(
                        session, total_damage, cause=animal.name)
                    await self.apply_mirror(session, animal, total_damage)
                    if died:
                        await self.send_combat_state(session, animal, 5, total_damage)
                        return
                    await self.send_combat_state(session, animal, 3, total_damage)
                else:
                    await self.award_combat_event_xp(
                        session, animal, dodge=True)
                    await self.send_combat_state(session, animal, 4)
                await asyncio.sleep(self.creature_combat_round_interval(animal))
        except asyncio.CancelledError:
            return

    async def release_unfought_target(self, session: Session, animal) -> None:
        """Hand back a target this player turned out not to be fighting.

        The claim is only half of being in combat, and the half the client
        reads. Dropping it silently would leave the player standing in the
        combat stance with the panel still open on a creature that walked away,
        so the same two messages the end of a fight sends are sent here.
        """
        c = session.character
        if not c or session.combat_target != animal.actor_id:
            return
        session.combat_target = None
        session.combat_xp_events.pop(animal.actor_id, None)
        if not player_in_combat(session):
            await self.broadcast_actor(
                c, p.actor_command(c.actor_id, p.CMD_LEAVE_COMBAT))
        await self.send_combat_state(session, animal, 5)

    async def attack(self, c: Character, target_id: int, session: Session, *,
                     announce_conflict: bool = True, approach: bool = True):
        a = self.animals.get(target_id)
        if not a or not a.alive or livestock.is_tame(a): return
        if session.combat_target is not None and session.combat_target != target_id:
            # A player who clicked a second creature is told why nothing
            # happened. A loop the server started for a target that has since
            # been superseded - another attacker arrived and the preference
            # moved on - is not the player's doing, and saying so once per
            # creature in a crowd is how a swarm filled the chat log.
            if announce_conflict:
                await session.send(p.raw_text("You are already in combat."))
            return
        attack_key = (c.actor_id, a.actor_id)
        if attack_key in self.player_attacks: return
        if actor_distance(c, a) > PLAYER_STRIKE_DISTANCE:
            # Give the claim back before doing anything else. Every retarget
            # names `combat_target` before it starts this coroutine, so a loop
            # that declines here leaves a target nobody is fighting: the client
            # reads "In combat", the creature is released by the movement AI and
            # wanders off, and every later click on it is refused in silence.
            await self.release_unfought_target(session, a)
            if approach:
                # This used to call `request_attack`, which declines a target
                # the session already holds - so the walk it asked for never
                # started. It is the same walk either way, and asking for it
                # directly is what makes it happen.
                self.approach_target(session, target_id)
            return
        player_was_in_combat = player_in_combat(session)
        session.combat_target = target_id
        session.combat_xp_events.setdefault(target_id, [0, 0])
        owns_combat_lock = a.actor_id not in self.combatants
        self.combatants.add(a.actor_id)
        self.player_attacks.add(attack_key)
        post_combat_bag: int | None = None
        await self.ensure_animal_visible(session, a)
        await self.face_each_other(c, a)
        if not player_was_in_combat:
            await self.broadcast_actor(
                c, p.actor_command(c.actor_id, p.CMD_ENTER_COMBAT))
        if owns_combat_lock:
            await self.broadcast_actor(
                a, p.actor_command(a.actor_id, p.CMD_ENTER_COMBAT))
        await self.send_combat_state(session, a)
        retaliation_task = (asyncio.create_task(self.creature_retaliation(a, session))
                            if not a.invasion or owns_combat_lock else None)
        # The combat locks below are what the invasion AI consults before it
        # lets a creature swing: an actor left in self.combatants is skipped
        # for good and stands there passively. Releasing them from a finally
        # keeps one raised exception from silencing a creature permanently.
        try:
            while (a.alive and c.health > 0 and not session.fleeing
                   and session.combat_target == target_id):
                forfeited = self.flee_round_remaining(session)
                if forfeited:
                    # A round given up to an attempt to get away. Bounded by a
                    # deadline that was set before this loop looked at it, so
                    # it is a skipped swing and not a loop waiting on
                    # something else to move.
                    await asyncio.sleep(forfeited)
                    continue
                await self.broadcast_actor(
                    c, p.actor_command(c.actor_id, p.CMD_ATTACK_UP_1))
                gear = equipment_stats(c.equipment)
                creature_gear = equipment_stats(a.equipment)
                definition = self.creatures[a.creature_type]
                hit = self.resolve_melee_hit(
                    attack=c.skills["attack"],
                    dexterity=player_dexterity(c),
                    accuracy=(int(gear["accuracy"])
                              + c.temporary_combat.get("accuracy", 0)),
                    defense=a.defense,
                    reaction=creature_reaction(definition),
                    defense_bonus=(int(creature_gear["defense"])
                                   + a.temporary_combat.get("evasion", 0)),
                    multicombat_penalty=self.creature_multicombat_penalty(a.actor_id),
                    attacker_vanquisher=c.has_perk("Vanquisher"),
                    attacker_luck=melee_hit_luck(c),
                    critical_to_hit=int(gear["critical_to_hit"]))
                if hit:
                    damage = self.resolve_melee_damage(
                        c, a, gear, creature_gear, attacker_session=session)
                    bonus_damage = await self.apply_item_effects(
                        c, a, session, "on_hit")
                    await self.apply_item_effects(
                        a, c, None, "when_hit", session)
                    await self.apply_normal_combat_wear(
                        c, True, owner_session=session)
                    await self.apply_normal_combat_wear(
                        a, False, observer_session=session)
                    total_damage = damage.total + bonus_damage
                    a.health = max(0, a.health - total_damage)
                    # Register 020, Life Stealing. On the blow that landed, so
                    # it rewards connecting rather than swinging.
                    stolen = min(life_steal(c), c.max_health - c.health)
                    if stolen > 0:
                        c.health += stolen
                        # Actor health is tracked separately from statistics;
                        # the next damage delta must start from the healed HP.
                        await self.broadcast_actor(
                            c, p.actor_heal(c.actor_id, stolen))
                        await self.send_stats(session, force=True)
                    # Something reached it in melee. For a creature that fights
                    # at a distance that is the signal to break off and open the
                    # range again, and to turn on whoever closed - both of which
                    # are read off these two fields by `ranged_creature_tick`.
                    # Melee creatures also read ranged_aggressor_id to chase
                    # whoever shot them, so a melee hit must not set it for
                    # them and turn a passive creature into a map-wide pursuer.
                    if definition.is_ranged:
                        a.ranged_aggressor_id = c.actor_id
                        a.melee_recoil_until = time.monotonic() + MELEE_RECOIL_SECONDS
                    await self.broadcast_actor(
                        a, p.actor_damage(a.actor_id, total_damage))
                    await self.process_boss_response(a)
                    await self.award_combat_event_xp(
                        session, a, attack=True)
                    await self.send_combat_state(session, a, 1, total_damage)
                    roads.emit(self,session,"weapon_hit",amount=total_damage)
                    await sky.event(self, session, "weapon_hit",
                                    detail=str(damage.heat + damage.cold + damage.magic + damage.radiation)
                                    if damage.heat + damage.cold + damage.magic + damage.radiation > 0 else "",
                                    amount=total_damage)
                else:
                    await self.send_combat_state(session, a, 2)
                await self.apply_glow_swing(session)
                if not a.health:
                    await self.finish_melee_kill(session, a)
                    break
                await asyncio.sleep(self.player_combat_round_interval(c))
        finally:
            if retaliation_task:
                retaliation_task.cancel()
            self.player_attacks.discard(attack_key)
            if owns_combat_lock:
                self.combatants.discard(a.actor_id)
            if session.combat_target == target_id:
                session.combat_target = None
            session.combat_xp_events.pop(target_id, None)
        if not player_in_combat(session):
            await self.broadcast_actor(
                c, p.actor_command(c.actor_id, p.CMD_LEAVE_COMBAT))
        await self.send_stats(session, force=True)
        await self.send_combat_state(session, a, 5)
        if not session.fleeing:
            next_target = self.choose_combat_target(session)
            if next_target:
                asyncio.create_task(self.attack(
                    c, next_target.actor_id, session, announce_conflict=False,
                    approach=False))
            elif post_combat_bag is not None and not player_in_combat(session):
                await self.inspect_bag(session, post_combat_bag, post_combat=True)

    async def finish_summon_creature_kill(
            self, owner: Session, target: Animal) -> None:
        """Credit a summon kill and deliver its drops to the summoner."""
        c = owner.character
        if not c:
            return
        target.alive = False
        target.ranged_aggressor_id = None
        for connected in list(self.sessions):
            connected.aggressors.discard(target.actor_id)
        await self.broadcast_map(
            target.map_id, p.actor_command(target.actor_id, p.CMD_DIE1))

        c.kills[target.species] = c.kills.get(target.species, 0) + 1
        self.record_creature_kill(c, target)
        await self.record_activity(owner, ACTIVITY_KILLS)
        self.ensure_novac_targets(c)
        for quest, objective in record_novac_kill(
                c, target.creature_type, self.novac_target_token(target)):
            await owner.send(quest_progress_popup(
                f"Your summon killed the {objective.name} the Tallykeeper asked for "
                f"{quest.title}. Return to Tallykeeper Ysolde."))

        drops = self.roll_creature_drops(target)
        if modern := getattr(self, "modern", None):
            for drop_name, drop_quantity in drops:
                modern.record_economy(
                    "creature_drop", c.username,
                    counterparty=target.species,
                    item_name=drop_name, quantity=drop_quantity,
                    item_flow="source",
                    metadata={"actor_id": target.actor_id,
                              "map_id": target.map_id,
                              "invasion": bool(target.invasion)})
        if c.autogather and drops and self.can_add_inventory(c, drops):
            for name, quantity in drops:
                self.add_inventory(
                    c, name, quantity,
                    source=f"creature_drop:{target.species}")
            await owner.send(p.inventory_packet(
                c.inventory, ITEMS, c.equipment, c.inventory_slots))
            await owner.send(stats_packet(c))
            await owner.send(p.raw_text("Gathered: " + ", ".join(
                f"{quantity} {name}" for name, quantity in drops)))
            roads.emit(self,owner,"loot",amount=len(drops))
        elif drops:
            drop_bag_id = await self.drop_into_bag(
                target.x, target.y, drops, target.map_id)
            self.create_tracked_bag_items(
                drop_bag_id, drops,
                source=f"creature_drop:{target.species}",
                actor=c.username)
            if c.autogather:
                await owner.send(p.raw_text(
                    "Not enough carry capacity for every drop; "
                    "all drops were placed in a bag."))

        self.save_soon(c)
        display_species = target.species.replace("_", " ")
        await owner.send(p.raw_text(
            f"Your summon killed a {display_species}. "
            f"Total: {c.kills[target.species]}."))

        if target.spawn_group:
            return
        if target.summoned or target.invasion:
            asyncio.create_task(self._remove_dead_invasion(target))
        else:
            asyncio.create_task(self._respawn(target))

    def reserve_summon_combat(
            self, summon: Animal, target: Animal) -> bool:
        """Reserve both actors before their asynchronous combat task starts."""
        owner = self.find_player_by_actor(summon.owner_id)
        opponents = (set(owner.aggressors) | {owner.combat_target}) if owner else set()
        occupied = target.actor_id in self.combatants
        if (not summon.alive or not target.alive
                or summon.actor_id in self.combatants
                or occupied and target.actor_id not in opponents):
            return False
        if not hasattr(self, '_summon_target_locks'):
            self._summon_target_locks = {}
        self._summon_target_locks[summon.actor_id] = not occupied
        self.combatants.update((summon.actor_id, target.actor_id))
        return True

    async def summon_attack(
            self, summon: Animal, target: Animal, *,
            reserved: bool = False) -> None:
        """Run autonomous creature combat for an owner-controlled summon."""
        if not reserved:
            if not self.reserve_summon_combat(summon, target):
                return
        elif (not summon.alive or not target.alive
              or summon.actor_id not in self.combatants
              or target.actor_id not in self.combatants):
            self.combatants.discard(summon.actor_id)
            if getattr(self, "_summon_target_locks", {}).pop(summon.actor_id, True):
                self.combatants.discard(target.actor_id)
            return
        owner = self.find_player_by_actor(summon.owner_id)
        if not owner or not owner.character:
            self.combatants.discard(summon.actor_id)
            if getattr(self, "_summon_target_locks", {}).pop(summon.actor_id, True):
                self.combatants.discard(target.actor_id)
            return
        await self.face_each_other(summon, target)
        await self.broadcast_map(summon.map_id, p.actor_commands([
            (summon.actor_id, p.CMD_ENTER_COMBAT),
            (target.actor_id, p.CMD_ENTER_COMBAT)]))
        try:
            while summon.alive and target.alive:
                owner = self.find_player_by_actor(summon.owner_id)
                if not owner or not owner.character or owner.character.map_id != summon.map_id:
                    break
                mode = int(owner.character.quest_state.get("summon_behavior", 1))
                opponents = set(owner.aggressors)
                if owner.combat_target is not None:
                    opponents.add(owner.combat_target)
                allies = self.summon_allies(summon.owner_username)
                if not summon_target_allowed(
                        mode, target.actor_id, target_summoned=target.summoned,
                        target_owner_id=target.owner_id, owner_id=summon.owner_id,
                        owner_opponents=opponents,
                        target_allied=self.summon_target_allied(allies, target)):
                    break
                if actor_distance(summon, target) > \
                        self.strike_distance_against(summon, target):
                    break
                await self.broadcast_actor(
                    summon, p.actor_command(summon.actor_id, p.CMD_ATTACK_UP_1))
                summon_gear = equipment_stats(summon.equipment)
                target_gear = equipment_stats(target.equipment)
                summon_definition = self.creatures[summon.creature_type]
                target_definition = self.creatures[target.creature_type]
                hit = self.resolve_melee_hit(
                    attack=summon.attack,
                    dexterity=creature_dexterity(summon_definition),
                    accuracy=int(summon_gear["accuracy"]),
                    defense=target.defense,
                    reaction=creature_reaction(target_definition),
                    defense_bonus=int(target_gear["defense"]),
                    critical_to_hit=int(summon_gear["critical_to_hit"]))
                if hit:
                    damage = self.resolve_melee_damage(
                        summon, target, summon_gear, target_gear)
                    target.health = max(0, target.health - damage.total)
                    roads.emit(self,owner,"summon_hit",amount=damage.total)
                    roads.emit(self,owner,"filtered_hit",str(mode),damage.total,target_id=target.actor_id,target_summoned=target.summoned)
                    await self.broadcast(
                        p.actor_damage(target.actor_id, damage.total))
                    await self.process_boss_response(target)
                if not target.health:
                    await self.finish_summon_creature_kill(owner, target)
                    break
                await asyncio.sleep(self.creature_combat_round_interval(summon))
        finally:
            self.combatants.discard(summon.actor_id)
            if getattr(self, "_summon_target_locks", {}).pop(summon.actor_id, True):
                self.combatants.discard(target.actor_id)
            await self.broadcast_map(summon.map_id, p.actor_commands([
                (summon.actor_id, p.CMD_LEAVE_COMBAT),
                (target.actor_id, p.CMD_LEAVE_COMBAT)]))

    async def summon_attack_player(
            self, summon: Animal, target: Session) -> None:
        """Attack a nearby player when both the summon and its owner are in PK."""
        character = target.character
        owner = self.find_player_by_actor(summon.owner_id)
        if (not summon.alive or not character or character.health <= 0
                or summon.actor_id in self.combatants
                or not owner or not owner.character
                or not shared_pk_zone(summon, character)
                or not shared_pk_zone(owner.character, character)):
            return
        self.combatants.add(summon.actor_id)
        target.aggressors.add(summon.actor_id)
        await self.face_each_other(summon, character)
        await self.broadcast_map(summon.map_id, p.actor_commands([
            (summon.actor_id, p.CMD_ENTER_COMBAT),
            (character.actor_id, p.CMD_ENTER_COMBAT)]))
        try:
            while summon.alive and character.health > 0:
                owner = self.find_player_by_actor(summon.owner_id)
                if (not owner or not owner.character
                        or not shared_pk_zone(summon, character)
                        or not shared_pk_zone(owner.character, character)):
                    break
                mode = int(owner.character.quest_state.get(
                    "summon_behavior", 1))
                opponents = set(owner.aggressors)
                if owner.combat_target is not None:
                    opponents.add(owner.combat_target)
                allies = self.summon_allies(summon.owner_username)
                if not summon_target_allowed(
                        mode, character.actor_id, target_summoned=False,
                        target_owner_id=None, owner_id=summon.owner_id,
                        owner_opponents=opponents,
                        target_allied=self.summon_target_allied(allies, character)):
                    break
                if actor_distance(summon, character) > \
                        self.strike_distance_against(summon, character):
                    break
                await self.broadcast_map(
                    summon.map_id,
                    p.actor_command(summon.actor_id, p.CMD_ATTACK_UP_1))
                summon_gear = equipment_stats(summon.equipment)
                target_gear = equipment_stats(character.equipment)
                zone = shared_pk_zone(summon, character)
                if zone is None:
                    break
                summon_definition = self.creatures[summon.creature_type]
                hit = self.resolve_melee_hit(
                    attack=summon.attack,
                    dexterity=creature_dexterity(summon_definition),
                    accuracy=int(summon_gear["accuracy"]),
                    defense=capped_level(character.skills["defense"], zone),
                    reaction=player_reaction(character),
                    defense_bonus=(int(target_gear["defense"])
                                   + character.temporary_combat.get("evasion", 0)
                                   - dual_wield_penalty(character)),
                    defender_vanquisher=character.has_perk("Vanquisher"),
                    defender_luck=melee_dodge_luck(character),
                    critical_to_hit=int(summon_gear["critical_to_hit"]))
                if hit:
                    damage = self.resolve_melee_damage(
                        summon, character, summon_gear, target_gear,
                        defender_session=target)
                    bonus_damage = await self.apply_item_effects(
                        summon, character, None, "on_hit", target)
                    await self.apply_item_effects(
                        character, summon, target, "when_hit")
                    if await self.damage_player(
                            target, damage.total + bonus_damage, cause=summon.name):
                        await owner.send(p.raw_text(
                            f"Your summon killed {character.name}."))
                        await target.send(p.raw_text(
                            f"You were killed by {owner.character.name}'s summon."))
                        break
                await asyncio.sleep(
                    self.creature_combat_round_interval(summon))
        finally:
            self.combatants.discard(summon.actor_id)
            target.aggressors.discard(summon.actor_id)
            target.combat_xp_events.pop(summon.actor_id, None)
            await self.broadcast_map(summon.map_id, p.actor_commands([
                (summon.actor_id, p.CMD_LEAVE_COMBAT),
                (character.actor_id, p.CMD_LEAVE_COMBAT)]))

    async def invasion_attack(self, animal: Animal, session: Session):
        c = session.character
        if not c or not animal.alive or animal.actor_id in self.combatants: return
        if sky.bot(c): return
        if not bell.combat_allowed(c, animal): return
        bag_task = session.post_combat_bag_task
        if bag_task and not bag_task.done():
            bag_task.cancel()
        player_was_in_combat = player_in_combat(session)
        # Claim the combat lock before the first await. Yielding between the
        # membership test above and this add lets several tasks enter combat
        # for one creature.
        self.combatants.add(animal.actor_id)
        session.aggressors.add(animal.actor_id)
        session.combat_xp_events.setdefault(animal.actor_id, [0, 0])
        await self.ensure_animal_visible(session, animal)
        # Every aggressor faces the player, but only the primary attack
        # coroutine rotates the player. Rotating the player once per simultaneous
        # aggressor can overflow the stock client's actor-command queue.
        await self.face_toward(animal, c)
        await self.broadcast_actor(
            animal, p.actor_command(animal.actor_id, p.CMD_ENTER_COMBAT))
        if not player_was_in_combat:
            await self.broadcast_actor(
                c, p.actor_command(c.actor_id, p.CMD_ENTER_COMBAT))
        # Aggressive creatures initiate combat and the player automatically
        # counters one of them; the rest can still hit. Which one is the
        # player's own preference - see engage_preferred_target.
        await self.engage_preferred_target(session, animal)
        try:
            while (animal.alive and c.health > 1 and not session.fleeing
                   and animal.actor_id in session.aggressors
                   and actor_distance(c, animal) <=
                       self.strike_distance_against(animal, c)):
                # Face the player before every swing, not only when combat
                # starts: the player circles, is knocked back, or walks away
                # and is followed, and a creature that swings at a target it
                # is not looking at is what the fight looks like from outside.
                await self.face_toward(animal, c)
                await self.broadcast_actor(
                    animal, p.actor_command(animal.actor_id, p.CMD_ATTACK_UP_1))
                definition = self.creatures[animal.creature_type]
                gear = equipment_stats(c.equipment)
                creature_gear = equipment_stats(animal.equipment)
                creature_hit = self.resolve_melee_hit(
                    attack=animal.attack,
                    dexterity=creature_dexterity(definition),
                    accuracy=int(creature_gear["accuracy"]),
                    defense=c.skills["defense"],
                    reaction=player_reaction(c),
                    defense_bonus=(int(gear["defense"])
                                   + c.temporary_combat.get("evasion", 0)
                                   - dual_wield_penalty(c)),
                    multicombat_penalty=self.player_multicombat_penalty(session),
                    defender_vanquisher=c.has_perk("Vanquisher"),
                    defender_luck=melee_dodge_luck(c),
                    critical_to_hit=int(creature_gear["critical_to_hit"]))
                if creature_hit:
                    damage = self.resolve_melee_damage(
                        animal, c, creature_gear, gear,
                        defender_session=session)
                    bonus_damage = await self.apply_item_effects(
                        animal, c, None, "on_hit", session)
                    await self.apply_item_effects(c, animal, session, "when_hit")
                    await self.apply_creature_poison(animal, session)
                    died = await self.damage_player(
                        session, damage.total + bonus_damage, cause=animal.name)
                    await self.apply_mirror(session, animal, damage.total + bonus_damage)
                    if died:
                        break
                else:
                    await self.award_combat_event_xp(
                        session, animal, dodge=True)
                await asyncio.sleep(self.creature_combat_round_interval(animal))
        finally:
            await self.broadcast_actor(
                animal, p.actor_command(animal.actor_id, p.CMD_LEAVE_COMBAT))
            self.combatants.discard(animal.actor_id)
            session.aggressors.discard(animal.actor_id)
            if session.combat_target != animal.actor_id:
                session.combat_xp_events.pop(animal.actor_id, None)
            if not player_in_combat(session):
                await self.broadcast_actor(
                    c, p.actor_command(c.actor_id, p.CMD_LEAVE_COMBAT))
            self.save_soon(c)
            await self.send_stats(session, force=True)

    def sync_inventory_slots(self, c: Character) -> list[str | None]:
        self.db.item_instances.reconcile_character(c)
        return c.inventory_slots

    async def show_sky_shop(self, session):
        actor_id = next(aid for aid, row in self.npcs.items() if row[1] == session.character.map_id and row[0].name == "Stillglass fittings")
        await self.show_shop_main(session, actor_id)

    def creature_attack_range(self, animal: Animal) -> int:
        """How far this creature can strike from. 1 for everything melee."""
        definition = self.creatures.get(animal.creature_type)
        return definition.attack_range if definition else 1

    def strike_distance_against(self, animal: Animal, target) -> int:
        """How close this creature must come to strike *this* target.

        Closer is per-target rather than a property of the creature, so a
        shooter kiting two players holds at a different distance from each.
        Never below one: a creature that had to stand inside its own target
        would have no square to shoot from at all.
        """
        reach = self.creature_strike_distance(animal)
        if isinstance(target, Character):
            reach = max(1, reach - closer_tiles(target))
        return reach

    def creature_strike_distance(self, animal: Animal) -> int:
        """How close a creature has to be before it can attack at all.

        Its `attack_range`, whatever kind of creature it is - which is 1 for
        everything melee, and 1 means the two bodies are touching, because
        distance is measured box to box and not between anchor tiles.

        This used to be the engage distance for a melee creature, and that
        conflated two different questions. `combat_engage_distance` is how far
        off a creature notices a player and sets out after one; it is not a
        reach. Reading it as one let a creature authored to notice you from two
        tiles swing at you from two tiles - across a visible gap, and across a
        wider one still for a large creature, whose anchor sits at the near
        corner of a body that is drawn over several tiles.
        """
        definition = self.creatures.get(animal.creature_type)
        return definition.attack_range if definition else 1

    def creature_pursuit_distance(self, animal: Animal) -> int:
        """How far off a creature will notice a player and set off after one."""
        definition = self.creatures.get(animal.creature_type)
        return definition.pursuit_distance if definition else 1

    def creature_holds_distance(self, animal: Animal) -> int:
        """The tile count a ranged creature wants between itself and its target.

        Zero for anything that closes, which is every creature the profile
        currently ships. The movement code asks this rather than reading the
        definition, so a creature that acquires reach starts holding ground
        without the pursuit logic learning what a bow is.
        """
        definition = self.creatures.get(animal.creature_type)
        return definition.effective_preferred_distance if definition else 0

    def experience_rows(self, c: Character) -> list[tuple[str, int, int, int]]:
        """Every skill's true lifetime experience and what it has bought."""
        return [(skill, int(c.experience.get(skill, 0)),
                 next_level_experience(c.skills.get(skill, 0)),
                 post_cap_points(c, skill))
                for skill in sorted(c.skills)]

    def actor_footprint_rows(self) -> list[tuple[int, int, int]]:
        """Every actor type that stands on more than one tile.

        Sorted by actor type and deduplicated: several creature definitions
        can share one actor type, and if two of them ever disagreed about
        their size the client would draw whichever arrived last. Taking the
        larger of the two is the safe way to disagree - a model centred in a
        box slightly too big is a model in the right place.
        """
        sizes: dict[int, tuple[int, int]] = {}
        for definition in self.creatures.values():
            shape = definition.footprint
            if shape.is_single_tile:
                continue
            width, depth = sizes.get(definition.actor_type, (1, 1))
            sizes[definition.actor_type] = (max(width, shape.width),
                                            max(depth, shape.depth))
        return [(actor_type, width, depth)
                for actor_type, (width, depth) in sorted(sizes.items())]

    def experience_signature(self, c: Character) -> tuple:
        """What has to change before the 64-bit view is worth resending.

        Experience moves on every swing, and restating fourteen skills for
        each one would be a lot of traffic to keep a number honest that the
        legacy packet already carries correctly below four billion. So this
        watches only the two things that packet cannot express: a total past
        its 32-bit field, and a point earned beyond the cap.
        """
        return tuple(
            (skill, int(c.experience.get(skill, 0)) > 0xFFFFFFFF,
             post_cap_points(c, skill))
            for skill in sorted(c.skills))

    def inventory_name_rows(self, c: Character) -> tuple[tuple[int, str], ...]:
        """What is in each of this character's slots, by name.

        The same positions the stock inventory packet writes, equipment
        included, so the two describe one grid rather than two. Read straight
        from the character the way the worn-slot mask below is, so it cannot
        drift from what was actually sent.
        """
        rows: list[tuple[int, str]] = []
        for slot, name in enumerate(c.inventory_slots or []):
            if 0 <= slot < 64 and name:
                rows.append((slot, name))
        for position, name in (c.equipment or {}).items():
            try:
                slot = int(position)
            except (TypeError, ValueError):
                continue
            if 0 <= slot < 64 and name:
                rows.append((slot, name))
        return tuple(sorted(rows))

    def worn_slot_mask(self, c: Character) -> int:
        """Which of this character's slots hold something that has worn down.

        Read straight from the catalog rather than from anything the client
        was told earlier, so it cannot drift: an item is worn exactly when
        some other item degrades into it.
        """
        mask = 0
        for slot, name in enumerate(c.inventory_slots or []):
            if 0 <= slot < 64 and name and is_degraded(name):
                mask |= 1 << slot
        for position, name in (c.equipment or {}).items():
            try:
                slot = int(position)
            except (TypeError, ValueError):
                continue
            if 0 <= slot < 64 and is_degraded(name):
                mask |= 1 << slot
        return mask

    def record_inventory_economy_delta(
            self, c: Character, before: dict[str, int], event_type: str, *,
            counterparty: str = "", metadata: dict | None = None) -> None:
        modern = getattr(self, "modern", None)
        if not modern:
            return
        for name in sorted(set(before) | set(c.inventory)):
            delta = int(c.inventory.get(name, 0)) - int(before.get(name, 0))
            if not delta:
                continue
            if name == "Gold Coins":
                modern.record_economy(
                    event_type, c.username, counterparty=counterparty,
                    item_name=name, gold=abs(delta),
                    gold_flow=("source" if delta > 0 else "sink"),
                    item_flow="none", metadata=metadata)
            else:
                modern.record_economy(
                    event_type, c.username, counterparty=counterparty,
                    item_name=name, quantity=abs(delta), gold_flow="none",
                    item_flow=("source" if delta > 0 else "sink"),
                    metadata=metadata)

    @staticmethod
    def _inventory_landing_slot(session: Session, preferred: int) -> int:
        """Where an unequipped piece goes: the slot the worn item just left,
        or the first free one after that.

        Returns -1 when the backpack has no free slot, which is legitimate for
        an untracked item that already has a stack there: the count rises and
        the existing slot keeps holding it.
        """
        slots = session.inventory_slots or []
        if 0 <= preferred < min(36, len(slots)) and slots[preferred] is None:
            return preferred
        return next((pos for pos, held in enumerate(slots[:36])
                     if held is None), -1)

    @staticmethod
    def inventory_slot_usage(inventory: dict[str, int]) -> int:
        return sum(
            int(quantity) if tracks_instances(name) else 1
            for name, quantity in inventory.items() if quantity > 0)

    def add_inventory(self, c: Character, name: str, quantity: int, *,
                      source: str = "gameplay", creator: str = "",
                      create_instances: bool = True,
                      modifiers: dict | None = None) -> bool:
        if name not in ITEMS or quantity <= 0:
            return False
        additional_slots = (quantity if tracks_instances(name)
                            else int(name not in c.inventory))
        if self.inventory_slot_usage(c.inventory) + additional_slots > 36:
            return False
        carried = sum(qty * ITEMS[item_name].emu for item_name, qty in c.inventory.items() if item_name in ITEMS)
        carried += sum(ITEMS[name].emu for name in c.equipment.values() if name in ITEMS)
        if carried + quantity * ITEMS[name].emu > carry_capacity(c):
            return False
        c.inventory[name] = c.inventory.get(name, 0) + quantity
        if create_instances and tracks_instances(name):
            for _ in range(quantity):
                self.db.item_instances.create(
                    name, 1, "inventory", c.username,
                    durability=100, max_durability=100,
                    creator=creator, source=source, actor=c.username,
                    modifiers=modifiers)
        self.sync_inventory_slots(c)
        return True

    @staticmethod
    def carried_load(c: Character) -> int:
        return (sum(quantity * ITEMS[name].emu for name, quantity in c.inventory.items()
                    if name in ITEMS)
                + sum(ITEMS[name].emu for name in c.equipment.values() if name in ITEMS))

    @classmethod
    def speed_food_loss_chance(cls, c: Character) -> float:
        capacity = max(1, carry_capacity(c))
        chance = 0.01 + 0.98 * min(1.0, cls.carried_load(c) / capacity)
        if any(name.casefold() == "runner's cape"
               for name in c.equipment.values()):
            chance *= 0.5
        return chance

    def can_add_inventory(self, c: Character, additions: list[tuple[str, int]]) -> bool:
        combined = dict(c.inventory)
        for name, quantity in additions:
            if name not in ITEMS or quantity <= 0:
                return False
            combined[name] = combined.get(name, 0) + quantity
        if self.inventory_slot_usage(combined) > 36:
            return False
        equipment_weight = sum(ITEMS[name].emu for name in c.equipment.values() if name in ITEMS)
        return (sum(quantity * ITEMS[name].emu for name, quantity in combined.items()) + equipment_weight
                <= carry_capacity(c))

    async def give_item(self, session: Session, name: str, quantity: int):
        await self.give_items(session, [(name, quantity)])

    async def give_random_legendary_items(
            self, session: Session, quantity: int = 1) -> list[tuple[str, int]]:
        """Give legendary equipment with independently rolled instance effects."""
        if not 1 <= quantity <= 36:
            raise ValueError("Random legendary quantity must be between 1 and 36.")
        rarity = self.item_rarity
        candidates = [name for name, item in ITEMS.items()
                      if rarity.get(name) == 4 and item.equip_type
                      and tracks_instances(name)]
        if not candidates:
            raise ValueError("No legendary equipment is available.")
        additions = list(Counter(random.choice(candidates)
                                 for _ in range(quantity)).items())
        await self.give_items(session, additions, legendary_effects=True)
        return additions

    async def give_items(self, session: Session, additions: list[tuple[str, int]], *,
                         legendary_effects: bool = False):
        """Validate and save the whole admin grant before sending any packets."""
        c = session.character
        if not c or not self.can_add_inventory(c, additions):
            raise ValueError("Not enough inventory slots or carry capacity.")
        for name, quantity in additions:
            if legendary_effects:
                for _ in range(quantity):
                    self.add_inventory(
                        c, name, 1, source="admin_grant",
                        modifiers=roll_legendary_modifiers(name))
            else:
                self.add_inventory(c, name, quantity, source="admin_grant")
            if modern := getattr(self, "modern", None):
                modern.record_economy(
                    "admin_grant", c.username, counterparty="server_admin",
                    item_name=name, quantity=quantity,
                    gold=(quantity if name == "Gold Coins" else 0),
                    gold_flow=("source" if name == "Gold Coins" else "none"),
                    item_flow=("none" if name == "Gold Coins" else "source"))
        self.db.save(c)
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await session.send(stats_packet(c))

    async def use_summoning_stone(self, session: Session, pos: int, name: str) -> None:
        c = session.character
        if not c or c.inventory.get(name, 0) < 1:
            return
        species = SUMMONING_STONES[name]
        animal = await self.spawn_summon(session, species)
        if not animal:
            return
        c.inventory[name] -= 1
        if c.inventory[name] <= 0:
            del c.inventory[name]
            session.inventory_slots[pos] = None
            await session.send(p.inventory_remove(pos))
        else:
            item = ITEMS[name]
            await session.send(p.inventory_update(item.image_id, c.inventory[name], pos,
                                                   item.flags))
        self.db.save(c)
        roads.emit(self,session,"stone",name,1)
        await session.send(p.raw_text(f"You used {name} and summoned {animal.name}."))

    async def use_removal_stone(self, session: Session, pos: int, name: str) -> None:
        c = session.character
        if not c or c.inventory.get(name, 0) < 1:
            return
        result = apply_removal_stone(c, name)
        if result is None:
            return
        changed, message = result
        if not changed:
            await session.send(p.raw_text(message))
            return
        await self.send_perks(session)
        # A stone hands pick points back and may clear a conflict, so what
        # the shelf refuses has moved; restate it rather than leave the
        # window showing yesterday's refusals.
        await self.send_perk_catalog(session)

        c.inventory[name] -= 1
        if c.inventory[name] <= 0:
            del c.inventory[name]
            session.inventory_slots[pos] = None
        refresh_derived_points(c)
        session.inventory_slots = self.sync_inventory_slots(c)
        self.db.save(c)
        await session.send(p.inventory_packet(
            c.inventory, ITEMS, c.equipment, session.inventory_slots))
        await session.send(stats_packet(c))
        await session.send(p.raw_text(message))

    async def use_inventory_item(self, session: Session, pos: int) -> None:
        """Dispatch an item use and count it only if the item was consumed.

        The client used to count a use the moment it sent the request, so a
        refused use still incremented its lifetime total. Comparing the
        authoritative inventory across the dispatch counts the outcome
        instead, whichever of the specialised handlers ran.
        """
        character = session.character
        before = dict(character.inventory) if character else {}
        health_before = character.health if character else 0
        ether_before = character.ether if character else 0
        food_before = character.food if character else 0
        await self._use_inventory_item(session, pos)
        if character and character.inventory != before:
            await self.record_activity(session, ACTIVITY_USED_ITEMS)
            if character.ether > ether_before:
                await sky.event(self, session, "mana", amount=character.ether-ether_before)
            if character.food > food_before:
                await sky.event(self, session, "food", amount=character.food-food_before)
            if character.health > health_before:
                await bell.event(self, session, "heal", amount=character.health-health_before)

    async def _use_inventory_item(self, session: Session, pos: int):
        c = session.character
        if c and not session.inventory_slots:
            session.inventory_slots = self.sync_inventory_slots(c)
        if not c or not 0 <= pos < len(session.inventory_slots):
            return
        name = session.inventory_slots[pos]
        if name is None or name not in c.inventory:
            return
        item = ITEMS[name]
        if name.casefold() in REMOVAL_STONE_NAMES:
            await self.use_removal_stone(session, pos, name)
            return
        if name in DAY_STONES or name == BAD_DAY_REMOVAL:
            await self.use_day_stone(session, pos, name)
            return
        bones = bone_eater(c) if name == "Bones" else None
        perk_bones = name == "Bones" and (
            c.has_perk("I Eat Dead People") or self.special_day_has("bones"))
        food_value = 10 if perk_bones else item.food
        food_cooldown = 0 if perk_bones else item.cooldown
        if bones is not None:
            # Bone Eater is the tiered version of the same idea: bones are
            # worth more, come round sooner, and at the low tiers a mouthful
            # occasionally goes badly wrong instead.
            interval, spoil = bones
            food_value, food_cooldown = 30, interval
            if spoil and random.random() < spoil:
                c.food = 0
                await session.send(p.item_description(
                    "The bones were rotten. You bring up everything you had."))
                await self.send_stats(session, force=True)
                return
        if name in POTIONS:
            await self.use_potion(session, pos, name)
            return
        if name in SUMMONING_STONES:
            await self.use_summoning_stone(session, pos, name)
            return
        if name in self.books:
            await self.read_book(session, pos, self.books[name])
            return
        old_daily_progress = int(c.quest_state.get("daily_progress", 0))
        handled, complete = record_daily_engineering(c, name, c.map_id, c.x, c.y)
        if handled:
            new_daily_progress = int(c.quest_state.get("daily_progress", 0))
            if new_daily_progress == old_daily_progress:
                await session.send(p.raw_text(
                    "Place it near the assigned location on a tile you have not used yet."))
                return
            c.inventory[name] -= 1
            if c.inventory[name] <= 0:
                del c.inventory[name]
                session.inventory_slots[pos] = None
            session.inventory_slots = self.sync_inventory_slots(c)
            self.db.save(c)
            await session.send(p.inventory_packet(
                c.inventory, ITEMS, c.equipment, session.inventory_slots))
            message = f"Daily engineering progress: {new_daily_progress}."
            if complete:
                message += " Return to the client for your reward."
            await session.send(p.raw_text(message))
            return
        if self.special_day_has("fasting") and not lantern.on_island(c) and not bell.on_map(c) and not sky.on_map(c):
            await session.send(p.raw_text("You cannot eat during the Day of Fasting."))
            return
        if not food_value:
            await session.send(p.raw_text(f"{name} cannot be eaten."))
            return
        now = time.monotonic()
        remaining = session.food_cooldown_until - now
        if remaining > 0 and not perk_bones:
            await session.send(p.item_cooldown(pos, session.food_cooldown_max,
                                               max(1, int(remaining + 0.999))))
            await session.send(p.raw_text(f"You must wait {int(remaining + 0.999)} seconds to use {name}."))
            return
        c.food = min(100 + extra_food_capacity(c), c.food + food_value)
        await self.walkthrough_event(session, "food", name, c.food)
        if "mushroom" in name.casefold():
            self.increment_achievement(c, "mushrooms_eaten")
        c.inventory[name] -= 1
        if c.inventory[name] <= 0:
            del c.inventory[name]
            session.inventory_slots[pos] = None
            await session.send(p.inventory_remove(pos))
        else:
            await session.send(p.inventory_update(item.image_id, c.inventory[name], pos,
                                                   item.flags))
        # The stock client recalculates carried EMU from a complete inventory
        # packet.  Stack updates alone leave the displayed load stale after food
        # (including Potion of Feasting) is consumed.
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(
            c.inventory, ITEMS, c.equipment, session.inventory_slots))
        if food_cooldown:
            if self.special_day_has("half_cooldowns"):
                food_cooldown = max(1, food_cooldown // 2)
            # Cooldown Reduction. Applied before the cooldown is stored and
            # before the client is told, so the number on the icon is the
            # number the player actually waits. Never below a second: a
            # cooldown that rounded to nothing would stop being one.
            food_cooldown = max(1, int(round(food_cooldown * cooldown_scale(c))))
            session.food_cooldown_until = now + food_cooldown
            session.food_cooldown_max = food_cooldown
            for food_pos, food_name in enumerate(session.inventory_slots):
                if food_name in ITEMS and ITEMS[food_name].food:
                    await session.send(p.item_cooldown(food_pos, food_cooldown))
        await session.send(p.partial_stats([(46, c.food)]))
        await session.send(p.raw_text(f"You ate {name}. Food level: {c.food}."))
        self.db.save(c)

    async def read_book(self, session: Session, pos: int, book: BookDefinition):
        c = session.character
        if not c or c.inventory.get(book.item_name, 0) < 1:
            return
        if not book.repeatable and book.knowledge in c.known_books:
            await session.send(p.raw_text(f"You already know {book.knowledge}."))
            return
        if c.reading_book:
            await session.send(p.raw_text(
                f"You are already reading {c.reading_book} ({c.reading_pages} pages remaining)."))
            return
        c.inventory[book.item_name] -= 1
        if c.inventory[book.item_name] <= 0:
            del c.inventory[book.item_name]
            session.inventory_slots[pos] = None
            await session.send(p.inventory_remove(pos))
        else:
            await session.send(p.inventory_update(
                ITEMS[book.item_name].image_id, c.inventory[book.item_name], pos,
                ITEMS[book.item_name].flags))
        if book.repeatable:
            level_ups = award_experience(
                c, ((book.experience_skill, book.experience),))
            await session.send(p.colored_text(
                f"You read {book.item_name} and gained {book.experience} "
                f"{book.experience_skill} experience.", p.EL_COLOR_GREEN3))
            if level_ups:
                await self.announce_levels(session, level_ups)
            await self.send_stats(session, force=True)
        else:
            c.reading_book = book.knowledge
            c.reading_pages = book.pages
            c.reading_total = book.pages
            await self.walkthrough_event(session, "read", book.item_name)
            await self.questline_event(session, "read", book.item_name)
            c.reading_index = self.knowledge_index.get(book.knowledge, 1024)
            eta = math.ceil(book.pages / self.research_rate(c))
            await session.send(p.colored_text(
                f"You started to research {book.knowledge}. ETA: {eta} minutes.", 0))
            await session.send(p.partial_stats([
                (47, c.reading_index), (65, 0), (66, min(c.reading_total, 0xFFFF))]))
        session.inventory_slots = self.sync_inventory_slots(c)
        self.db.save(c)

    @staticmethod
    def rationality(c: Character) -> int:
        return max(1, c.attributes["rationality"])

    def maximum_action_points(self, c: Character) -> int:
        return self.rationality(c) * 20

    def regenerate_action_points(
            self, c: Character, *, active: bool) -> int:
        """Apply one minute of EL action-point recovery and return points gained."""
        maximum = self.maximum_action_points(c)
        current = min(
            maximum, c.combat_bonuses.get("action_points", maximum))
        gain = self.rationality(c) if active else (
            1 if random.random() < 0.10 else 0)
        updated = min(maximum, current + gain)
        c.combat_bonuses["action_points"] = updated
        return updated - current

    def area_multiplier(self, c: Character, kind: str) -> int:
        return multiplier_at(self.special_areas, kind, c.map_id, c.x, c.y)

    def research_rate(self, c: Character) -> int:
        return self.rationality(c) * self.area_multiplier(c, FAST_READING)

    def reconcile_research(self, c: Character):
        if not c.reading_book:
            c.reading_pages, c.reading_total, c.reading_index = 0, 0, 1024
            return
        c.reading_index = self.knowledge_index.get(c.reading_book, 1024)
        if c.reading_total <= 0:
            definition = next((book for book in self.books.values()
                               if book.knowledge == c.reading_book and not book.repeatable), None)
            c.reading_total = definition.pages if definition else c.reading_pages
        c.reading_total = max(c.reading_total, c.reading_pages)

    async def send_knowledge_list(self, session: Session):
        c = session.character
        if c:
            known = {self.knowledge_index[name] for name in c.known_books
                     if name in self.knowledge_index}
            await session.send(p.knowledge_list(known, len(self.knowledge_catalog)))

    async def inspect_knowledge(self, session: Session, index: int):
        if 0 <= index < len(self.knowledge_catalog):
            await session.send(p.knowledge_text(self.knowledge_catalog[index]))

    async def report_research(self, session: Session):
        c = session.character
        if not c or not c.reading_book:
            await session.send(p.colored_text("You are not researching anything.", 3))
            return
        self.reconcile_research(c)
        eta = math.ceil(c.reading_pages / self.research_rate(c))
        await session.send(p.colored_text(
            f"You are researching {c.reading_book}. Research points left:"
            f"{c.reading_pages}/{c.reading_total}. ETA: {eta} minutes", 3))

    async def list_knowledge(self, session: Session, arguments: str):
        c = session.character
        if not c:
            return
        tokens = arguments.split()
        modes = {token.casefold() for token in tokens if token.casefold() in {"-t", "-r", "-u"}}
        if len(modes) > 1:
            await session.send(p.raw_text("Use only one of -t (total), -r (read), or -u (unread)."))
            return
        mode = next(iter(modes), "-t")
        filter_text = " ".join(token for token in tokens if token.casefold() not in modes).casefold()
        entries = sorted({book.knowledge for book in self.books.values()
                          if not book.repeatable}, key=str.casefold)
        if filter_text:
            entries = [name for name in entries if filter_text in name.casefold()]
        total_matching = len(entries)
        known_matching = sum(name in c.known_books for name in entries)
        if mode == "-r":
            entries = [name for name in entries if name in c.known_books]
        elif mode == "-u":
            entries = [name for name in entries if name not in c.known_books]
        for name in entries:
            await session.send(p.raw_text(name))
        await session.send(p.raw_text(
            f"You have read {known_matching} of {total_matching} matching books."))
        await session.send(p.raw_text("Use -(t)otal, -(r)ead or -(u)nread to select output."))

    async def use_potion(self, session: Session, pos: int, name: str):
        c, effect = session.character, POTIONS[name]
        now = time.monotonic()
        remaining = session.potion_cooldowns.get(name, 0.0) - now
        if remaining > 0:
            seconds = max(1, int(math.ceil(remaining)))
            await session.send(p.item_cooldown(pos, effect.cooldown,
                                               seconds))
            await session.send(p.raw_text(f"You must wait {seconds} seconds to use {name}."))
            return
        if effect.kind == "health" and c.health >= c.max_health:
            await session.send(p.raw_text("Your material points are already full.")); return
        if effect.kind == "mana" and c.ether >= c.max_ether:
            await session.send(p.raw_text("Your ethereal points are already full.")); return
        if effect.target == "speed" and c.food <= -30:
            await session.send(p.raw_text("You are too hungry to use Speed Hax.")); return
        if effect.kind == "attribute":
            c.attributes[effect.target] += effect.amount
            c.temporary_attributes[effect.target] = c.temporary_attributes.get(effect.target, 0) + effect.amount
            refresh_derived_points(c)
        elif effect.kind == "skill":
            old = c.skills[effect.target]
            c.skills[effect.target] = max(0, old + effect.amount)
            applied = c.skills[effect.target] - old
            c.temporary_skills[effect.target] = c.temporary_skills.get(effect.target, 0) + applied
        elif effect.kind == "health":
            amount = min(effect.amount, c.max_health-c.health); c.health += amount
            await self.broadcast_map(c.map_id, p.actor_heal(c.actor_id, amount))
        elif effect.kind == "mana": c.ether = min(c.max_ether, c.ether + effect.amount)
        elif effect.kind == "combat":
            c.temporary_combat[effect.target] = c.temporary_combat.get(effect.target, 0) + effect.amount
            if effect.target == "speed":
                c.temporary_combat.pop("speed", None)
                c.speed_hax_active = True
                await self.broadcast_map(c.map_id, p.actor_buffs(c.actor_id, BUFF_DOUBLE_SPEED))
        elif effect.kind == "permanent_combat":
            c.combat_bonuses[effect.target] = min(60, c.combat_bonuses.get(effect.target, 0) + effect.amount)
        elif effect.kind == "buff":
            # The protection ids are the ones melee_magic_bonuses reads (the
            # same ids spell casts store); the old 17-19 lit a client icon
            # that no combat math ever looked at.
            buff_ids = {"magic":1, "cold":23, "heat":24, "radiation":25,
                        "invisibility":3, "true_sight":22}
            buff_id = buff_ids[effect.target]
            session.magic_buffs[buff_id] = now + effect.duration
            session.magic_buff_powers[buff_id] = max(1, effect.amount)
            await session.send(p.active_spell(buff_id, effect.duration))
        elif effect.kind == "action_points":
            maximum = self.maximum_action_points(c)
            current = min(maximum, c.combat_bonuses.get("action_points", maximum))
            c.combat_bonuses["action_points"] = min(maximum, current + effect.amount)
        elif effect.kind == "antidote":
            self.stop_poison(session)
        c.inventory[name] -= 1
        if c.inventory[name] <= 0:
            del c.inventory[name]; session.inventory_slots[pos] = None
            await session.send(p.inventory_remove(pos))
        else:
            await session.send(p.inventory_update(ITEMS[name].image_id, c.inventory[name], pos,
                                                   ITEMS[name].flags))
        if effect.returned_item:
            self.add_inventory(c, effect.returned_item, 1)
        cooldown = max(1, int(round(effect.cooldown * cooldown_scale(c))))
        session.potion_cooldowns[name] = now + cooldown
        await session.send(p.item_cooldown(pos, cooldown))
        await session.send(p.raw_text(f"You used {name}: {ITEMS[name].description or self.potion_effect_text(effect)}"))
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await self.send_stats(session, force=True)
        self.save_soon(c)

    @staticmethod
    def potion_effect_text(effect):
        labels = {"health":"material points", "mana":"ethereal points",
                  "attribute":effect.target, "skill":effect.target,
                  "combat":effect.target.replace("_", " "), "permanent_combat":effect.target.replace("_", " "),
                  "buff":effect.target.replace("_", " "), "antidote":"poison protection",
                  "action_points":"action points"}
        return f"{labels.get(effect.kind, effect.kind)} {effect.amount:+d}" if effect.amount else labels.get(effect.kind, effect.kind)

    async def move_inventory_item(self, session: Session, source: int, destination: int):
        await self._move_inventory_item(session, source, destination)
        await lantern.event(self, session, "equipment")
        await bell.event(self, session, "equipment")
        await landing_runtime.event(self, session, "equipment")
        await watchpost.event(self, session, "equipment")

    async def _move_inventory_item(self, session: Session, source: int, destination: int):
        """Equip/unequip using the client's eight generic wear positions (36-43)."""
        c = session.character
        if not c or not (0 <= source < 44 and 0 <= destination < 44):
            return
        if not session.inventory_slots:
            session.inventory_slots = self.sync_inventory_slots(c)
        old_max_health, old_max_ether = c.max_health, c.max_ether
        # What the map is drawing now.  The visuals the move causes are the
        # difference between this and what the same reading gives once the
        # move is done, rather than a note taken beside each item as it is
        # picked up and put down.  An item is not the whole answer: two
        # one-handed weapons are both part 0 on their own, and it is only the
        # pair that puts one of them in the left hand, so a per-item note
        # equipped the second weapon over the first and unequipping either one
        # emptied the hand that still held something.
        before_visuals = equipped_visuals(c.equipment)
        if source < 36 and destination < 36:
            slots = self.sync_inventory_slots(c)
            if source == destination or slots[source] is None:
                return
            slots[source], slots[destination] = slots[destination], slots[source]
            c.inventory_instance_slots[source], c.inventory_instance_slots[destination] = (
                c.inventory_instance_slots[destination],
                c.inventory_instance_slots[source])
            session.inventory_slots = slots
            self.db.save(c)
            await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment,
                                                  c.inventory_slots))
            return
        if source < 36 and destination >= 36:
            if source >= len(session.inventory_slots) or not session.inventory_slots[source]:
                return
            name = session.inventory_slots[source]
            item = ITEMS[name]
            kind = wear_type(item)
            if not kind and (name in POTIONS or name in self.books or item.food):
                await self.use_inventory_item(session, source)
                return
            if not kind:
                await session.send(p.raw_text(f"{name} cannot be equipped.")); return
            # What has to come off before this can go on: only what clashes
            # with it. A piece of the same kind is swapped for the new one,
            # which takes over its wear position, so the positions a player
            # arranged stay arranged; a two-handed weapon empties both hands
            # the same way.
            displaced = [position for position in
                         sorted(c.equipment, key=_wear_position)
                         if equipment_conflict(
                             kind, wear_type(ITEMS.get(c.equipment[position])))]
            if (item.equip_type == "right_hand" and may_dual_wield(c)
                    and len(displaced) == 1
                    and not any(getattr(ITEMS.get(worn), "equip_type", "")
                                == "left_hand"
                                for worn in c.equipment.values())):
                # Two Handed Wielding, at the tiers that allow it: a second
                # one-handed weapon goes on beside the first rather than
                # replacing it - but only instead of a shield, never as well
                # as one, and the stance costs defense while both are held.
                displaced = []
            target = displaced[0] if displaced else str(destination)
            if not displaced and target in c.equipment:
                # The position asked for holds something this piece can be
                # worn alongside. Taking that off is not what was asked, and
                # these eight positions are generic, so the piece goes to a
                # free one instead. All eight are full only when one of every
                # kind is worn, and every kind clashes with something, so a
                # piece that reaches here and finds none is a saved character
                # wearing two of a kind rather than anything a player can do.
                target = next((str(position) for position in range(36, 44)
                               if str(position) not in c.equipment), "")
                if not target:
                    await session.send(p.raw_text(
                        "You have no free equipment position.")); return
            # What comes off has to have somewhere to land. The slot the new
            # item leaves counts, which is why a plain swap never needs room.
            projected = dict(c.inventory)
            projected[name] = projected.get(name, 0) - 1
            if projected[name] <= 0:
                del projected[name]
            for position in displaced:
                worn = c.equipment[position]
                projected[worn] = projected.get(worn, 0) + 1
            if self.inventory_slot_usage(projected) > 36:
                await session.send(p.raw_text("Your inventory is full.")); return
            instance_id = (c.inventory_instance_slots[source]
                           if tracks_instances(name) else None)
            c.inventory[name] -= 1
            if not c.inventory[name]:
                del c.inventory[name]
            session.inventory_slots[source] = None
            c.inventory_instance_slots[source] = None
            for position in displaced:
                worn = c.equipment.pop(position)
                c.inventory[worn] = c.inventory.get(worn, 0) + 1
                landing = self._inventory_landing_slot(session, source)
                if landing >= 0:
                    session.inventory_slots[landing] = worn
                    c.inventory_instance_slots[landing] = None
                worn_instance = c.equipment_instances.pop(position, None)
                if worn_instance and landing >= 0:
                    c.inventory_instance_slots[landing] = (
                        self.db.item_instances.transfer(
                            worn_instance, 1, "inventory", c.username,
                            slot_key=str(landing), actor=c.username,
                            source="unequipped"))
            c.equipment[target] = name
            if instance_id:
                moved_id = self.db.item_instances.transfer(
                    instance_id, 1, "equipment", c.username,
                    slot_key=target, actor=c.username,
                    source="equipped")
                c.equipment_instances[target] = moved_id
        elif source >= 36 and destination < 36:
            name = c.equipment.get(str(source))
            if not name:
                return
            if self.inventory_slot_usage(c.inventory) >= 36:
                await session.send(p.raw_text("Your inventory is full.")); return
            c.inventory[name] = c.inventory.get(name, 0) + 1
            session.inventory_slots[destination] = name
            instance_id = c.equipment_instances.pop(str(source), None)
            if instance_id:
                moved_id = self.db.item_instances.transfer(
                    instance_id, 1, "inventory", c.username,
                    slot_key=str(destination), actor=c.username,
                    source="unequipped")
                c.inventory_instance_slots[destination] = moved_id
            del c.equipment[str(source)]
        else:
            return
        session.inventory_slots = self.sync_inventory_slots(c)
        refresh_derived_points(c)
        self.db.save(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await session.send(stats_packet(c))
        # A cape can carry a perk, so equipping or unequipping changes the
        # effective perk set the client is showing.
        await self.send_perks(session)
        await self.broadcast_visual_changes(c, before_visuals)
        if c.max_health != old_max_health:
            await self.broadcast_actor(
                c, p.actor_max_health(c.actor_id, c.max_health))
        if session.ranging_task and not equipped_ranging_items(c):
            self.stop_ranging(session)

    async def repair_item(self, session: Session, query: str) -> None:
        c = session.character
        if not c:
            return
        self.sync_inventory_slots(c)
        query = query.strip()
        candidates: list[int] = []
        if query.isdigit():
            slot = int(query)
            if 0 <= slot < 36 and slot < len(c.inventory_instance_slots):
                instance_id = c.inventory_instance_slots[slot]
                if instance_id:
                    candidates.append(instance_id)
            elif slot >= 36 and str(slot) in c.equipment_instances:
                candidates.append(c.equipment_instances[str(slot)])
        else:
            wanted = query.casefold()
            candidates.extend(
                instance_id for pos, instance_id
                in enumerate(c.inventory_instance_slots)
                if instance_id and c.inventory_slots[pos]
                and c.inventory_slots[pos].casefold() == wanted)
            candidates.extend(
                instance_id for slot, instance_id in c.equipment_instances.items()
                if c.equipment.get(slot, "").casefold() == wanted)
        instances = [self.db.item_instances.get(value) for value in candidates]
        instances = [item for item in instances if item and item.state == "active"]
        if not instances:
            await session.send(p.raw_text(
                "Usage: #repair inventory/equipment-slot or exact tracked item name"))
            return
        instance = min(
            instances,
            key=lambda item: (item.durability if item.durability is not None
                              else item.max_durability or 100,
                              item.instance_id))
        maximum = instance.max_durability or 100
        current = instance.durability if instance.durability is not None else maximum
        missing = maximum - current
        if missing <= 0:
            await session.send(p.raw_text(
                f"{instance.definition_name} #{instance.instance_id} is already fully repaired."))
            return
        unit_cost = max(1, ITEMS[instance.definition_name].emu) * 2
        cost = missing * unit_cost
        if c.inventory.get("Gold Coins", 0) < cost:
            roads.emit(self,session,"repair_quote",instance.definition_name,cost,instance_id=instance.instance_id)
            await session.send(p.raw_text(
                f"Repairing {instance.definition_name} #{instance.instance_id} "
                f"costs {cost} Gold Coins."))
            return
        operation_key = (
            f"repair:{c.username.casefold()}:{instance.instance_id}:{current}")
        with self.db.db:
            if self.modern and not self.modern.claim_operation(
                    operation_key, c.username, "equipment_repair"):
                return
            c.inventory["Gold Coins"] -= cost
            if not c.inventory["Gold Coins"]:
                del c.inventory["Gold Coins"]
            self.db.item_instances.repair(
                instance.instance_id, missing, actor=c.username)
            if self.modern:
                self.modern.record_economy(
                    "equipment_repair", c.username,
                    item_name=instance.definition_name, quantity=1,
                    gold=cost, instance_id=instance.instance_id,
                    gold_flow="sink", item_flow="none",
                    metadata={"durability_restored": missing,
                              "unit_cost": unit_cost})
                self.modern.finish_operation(
                    operation_key, {"cost": cost, "durability": maximum})
            self.db.save(c, commit=False)
        roads.emit(self,session,"repair",instance.definition_name,missing,instance_id=instance.instance_id)
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(
            c.inventory, ITEMS, c.equipment, session.inventory_slots))
        await session.send(p.raw_text(
            f"Repaired {instance.definition_name} #{instance.instance_id} "
            f"to {maximum}/{maximum} durability for {cost} Gold Coins."))

    async def send_inventory_organizer(self, session: Session) -> None:
        c = session.character
        if not c:
            return
        if "inventory_window_v1" not in session.client_capabilities:
            await session.send(p.raw_text(
                "The inventory organizer requires the independent Eloria client."))
            return
        session.inventory_slots = self.sync_inventory_slots(c)
        entries = [
            (slot, ITEMS[name],
             1 if c.inventory_instance_slots[slot] else c.inventory[name])
            for slot, name in enumerate(session.inventory_slots)
            if name and name in ITEMS and name in c.inventory
        ]
        await session.send(p.inventory_state(
            c.inventory.get("Gold Coins", 0), self.carried_load(c),
            carry_capacity(c), entries))

    @staticmethod
    def item_stats_text(item) -> str:
        parts = []
        for key, value in item.stats:
            label = key.replace("_", " ").title()
            if isinstance(value, tuple):
                parts.append(f"{label} {value[0]}-{value[1]}")
            else:
                parts.append(f"{label} {value:+d}")
        if item.food:
            parts.append(f"Food {item.food:+d}")
        if item.cooldown:
            parts.append(f"Cooldown {item.cooldown}s")
        parts.append(f"Weight {item.emu} EMU")
        return ", ".join(parts)

    @staticmethod
    def item_comparison_text(item, equipped) -> str:
        current = dict(item.stats)
        baseline = dict(equipped.stats)
        parts = []
        for key in sorted(set(current) | set(baseline)):
            value, old = current.get(key, 0), baseline.get(key, 0)
            label = key.replace("_", " ").title()
            if isinstance(value, tuple) or isinstance(old, tuple):
                value = value if isinstance(value, tuple) else (value, value)
                old = old if isinstance(old, tuple) else (old, old)
                delta = (value[0] - old[0], value[1] - old[1])
                if delta != (0, 0):
                    parts.append(f"{label} {delta[0]:+d}/{delta[1]:+d}")
            elif value != old:
                parts.append(f"{label} {value - old:+d}")
        weight_delta = item.emu - equipped.emu
        if weight_delta:
            parts.append(f"Weight {weight_delta:+d} EMU")
        return ", ".join(parts) or "No numerical stat change"

    async def inspect_ground_item(self, session: Session, pos: int) -> None:
        """Describe one item lying in the open bag.

        The bag packet carries an image id, a quantity and a slot and nothing
        else, so a player could see a picture of something on the ground and
        had no way to ask what it was. This answers with the same description
        an inventory item gets, through the same two routes.
        """
        c = session.character
        bag_id = session.open_bag
        if not c or bag_id is None or bag_id not in self.bags:
            return
        contents = self.bags[bag_id][2]
        if not 0 <= pos < len(contents):
            return
        name, quantity = contents[pos]
        if quantity <= 0 or name not in ITEMS:
            return
        item = ITEMS[name]
        if "item_detail_v1" not in session.client_capabilities:
            await session.send(p.item_description(item_inspect_text(item)))
            return
        await session.send(p.item_detail(
            item.image_id, quantity, False, item.name, item.category,
            item.equip_type or "", clean_item_description(
                item.name, item.description),
            self.item_stats_text(item), "", ""))

    async def inspect_inventory_item(self, session: Session, pos: int):
        c = session.character
        if not c:
            return
        if pos < 36:
            if not session.inventory_slots:
                session.inventory_slots = self.sync_inventory_slots(c)
            name = session.inventory_slots[pos] if pos < len(session.inventory_slots) else None
            instance_id = (c.inventory_instance_slots[pos]
                           if pos < len(c.inventory_instance_slots) else None)
            quantity = 1 if instance_id else (c.inventory.get(name, 0) if name else 0)
            equipped = False
        else:
            name = c.equipment.get(str(pos))
            quantity = 1
            instance_id = c.equipment_instances.get(str(pos))
            equipped = True
        if not name or name not in ITEMS:
            return
        roads.emit(self,session,"inspect",name,instance_id=instance_id)
        item = ITEMS[name]
        instance = self.db.item_instances.get(instance_id) if instance_id else None
        effect_lines = (instance_effect_descriptions(instance.modifiers)
                        if instance else ())
        if "item_detail_v1" not in session.client_capabilities:
            description = item_inspect_text(item)
            if effect_lines:
                description += f" Object #{instance.instance_id}. " + " ".join(effect_lines)
            await session.send(p.item_description(description))
            return
        comparison_name = comparison = ""
        if item.equip_type and not equipped:
            for equipped_name in c.equipment.values():
                candidate = ITEMS.get(equipped_name)
                if candidate and candidate.equip_type == item.equip_type:
                    comparison_name = candidate.name
                    comparison = self.item_comparison_text(item, candidate)
                    break
        description = clean_item_description(item.name, item.description)
        stats_text = self.item_stats_text(item)
        if instance:
            current = (instance.durability if instance.durability is not None
                       else instance.max_durability)
            maximum = instance.max_durability
            details = [f"Object #{instance.instance_id}"]
            if current is not None and maximum is not None:
                details.append(f"Durability {current}/{maximum}")
            details.append(f"Quality {instance.quality}")
            if instance.bound_to:
                details.append(f"Bound to {instance.bound_to}")
            if instance.creator:
                details.append(f"Created by {instance.creator}")
            other_modifiers = {key: value for key, value in instance.modifiers.items()
                               if key != MODIFIER_KEY}
            if other_modifiers:
                details.append("Modifiers " + ", ".join(
                    f"{key}={value}" for key, value
                    in sorted(other_modifiers.items())))
            description = description + "\n" + "; ".join(details)
            if effect_lines:
                description += "\nLegendary effects:\n" + "\n".join(effect_lines)
            stats_text += f", Durability {current}/{maximum}, Quality {instance.quality}"
        await session.send(p.item_detail(
            item.image_id, quantity, equipped, item.name, item.category,
            item.equip_type, description, stats_text,
            comparison_name, comparison))

    def stop_harvesting(self, session: Session) -> bool:
        """Cancel a running harvest; True when there was one to stop.

        Only the cancel lives here. The harvest loop's own exit path sends
        the stock "You stopped harvesting." line and clears the client's
        harvest state, so every interruption reads the same to the player.
        """
        task = session.harvest_task
        if not task or task.done() or task is asyncio.current_task():
            return False
        task.cancel()
        return True

    async def start_harvesting(self, session: Session, object_id: int):
        c = session.character
        if self.special_day_has("green") and not lantern.on_island(c) and not bell.on_map(c) and not sky.on_map(c):
            await session.send(p.raw_text("Nothing can be harvested during Green Day."))
            return
        node = self.harvest_nodes.get((c.map_id, object_id)) if c else None
        if not c or not node or node.resource not in self.harvest_resources:
            await session.send(p.raw_text("You cannot harvest that object."))
            return
        if session.combat_target is not None or session.aggressors:
            await session.send(p.raw_text("You cannot harvest while in combat."))
            return
        if session.harvest_task and not session.harvest_task.done():
            session.harvest_task.cancel()
            return
        # The approach below calls move() from the harvest task. Retire the
        # previous click/attack/bag route first so two tasks cannot walk the
        # same character from different snapshots of its position.
        if session.move_task and not session.move_task.done():
            session.move_task.cancel()
        session.pending_attack = None
        session.pending_bag = None
        session.harvest_task = asyncio.create_task(self._harvest_loop(session, node))
        # Everyone else hears it start. The harvester's own client already
        # knows - it is told the harvest state - so it is left out rather than
        # hearing the sound twice.
        await self.play_sound_at(c.map_id, "harvest_start", node.x, node.y,
                                 excluding=session)

    async def send_mix_state(self, session: Session) -> None:
        """Tell the window what it cannot work out for itself.

        Whether storage is in reach is a distance to an actor whose role the
        client is never told, so a window guessing at it would grey the
        control out in the one place a player wanted it. What is being made
        and how much is left is what lets a queue send its next batch when
        this one ends rather than watching an inventory that stopped moving.
        """
        character = session.character
        if not character or "mix_window_v1" not in session.client_capabilities:
            return
        running = session.mix_task is not None and not session.mix_task.done()
        await session.send(p.mix_state_packet(
            near_storage=self.storage_npc_near(character),
            running=running,
            output=session.mix_output,
            remaining=session.mix_remaining if running else 0,
            made=session.mix_made))

    async def mix_from_request(self, session: Session, data: bytes) -> None:
        """Start a mix the window asked for, by recipe rather than by slot.

        `MANUFACTURE_THIS` names the inventory positions the ingredients sit
        in, which is the only thing the Eternal Lands client could say. That
        makes mixing from storage unsayable in it - the ingredients are not in
        any inventory position - so this asks for a recipe instead and lets
        the server find the materials wherever they were asked for.
        """
        character = session.character
        if not character or len(data) < 5:
            return
        index, wanted, source = struct.unpack_from("<HHB", data, 0)
        if index >= len(self.recipes):
            await session.send(p.item_description("No such recipe."))
            return
        recipe = self.recipes[index]
        from_storage = source == 1
        if from_storage and not self.storage_npc_near(character):
            await session.send(p.item_description(
                "You are not close enough to storage to mix from it."))
            return
        if session.mix_task and not session.mix_task.done():
            session.mix_task.cancel()
        session.mix_status = None
        session.mix_from_storage = from_storage
        session.mix_output = recipe.output
        session.mix_remaining = max(1, min(0xFFFF, int(wanted)))
        session.mix_made = 0
        session.mix_task = asyncio.create_task(
            self._mix_loop(session, recipe, session.mix_remaining))
        await self.send_mix_state(session)

    def recipe_tools(self) -> frozenset[str]:
        """Every item some recipe calls for as a tool, folded for comparison."""
        cached = getattr(self, "_recipe_tools", None)
        if cached is None:
            cached = frozenset(tool.casefold() for recipe in self.recipes
                               for tool in recipe.tools)
            self._recipe_tools = cached
        return cached

    async def tool_from_storage(self, session: Session, data: bytes) -> None:
        """Fetch a tool the manufacturing window named out of storage.

        Tools wear out, so a mix that ran yesterday can fail today for want of
        a hatchet rather than for materials - and the fix, open storage, find
        the tool among everything else in it, withdraw one, close storage, is
        the window sending a player away to do something it is already
        standing next to. Clicking the tool does it instead.

        Only names some recipe actually calls for are honoured, so this stays
        a way to pick up a tool rather than a way to take anything at all out
        of storage without opening it.
        """
        character = session.character
        if not character or not data:
            return
        name = data.split(b"\0")[0].decode("utf-8", "replace")
        if name.casefold() not in self.recipe_tools():
            return
        if not self.storage_npc_near(character):
            await session.send(p.item_description(
                "You are not close enough to storage."))
            return
        if character.storage.get(name, 0) < 1:
            await session.send(p.item_description(
                "You have no %s in storage." % name))
            return
        # A withdrawal can still refuse for weight or for a full pack, and
        # says so itself; only claim the tool was picked up if it moved.
        before = character.inventory.get(name, 0)
        await self.withdraw_named(session, name, 1)
        if character.inventory.get(name, 0) > before:
            await session.send(p.item_description(
                "You take a %s from storage." % name))

    async def start_mixing(self, session: Session, data: bytes):
        """Handle the packet shared by the manufacture window and Inventory Mix All."""
        c = session.character
        if self.special_day_has("labour") and not lantern.on_island(c) and not bell.on_map(c) and not sky.on_map(c):
            await session.send(p.item_description("Nothing can be mixed during Labour Day."))
            return
        count = data[0] if data else 0
        expected = 1 + count * 3 + 1
        if not c or not count or len(data) < expected:
            await session.send(p.item_description("Select some ingredients before mixing."))
            return
        chosen = {}
        for offset in range(count):
            pos = data[1 + offset * 3]
            quantity = struct.unpack_from("<H", data, 2 + offset * 3)[0]
            if pos >= len(session.inventory_slots) or not session.inventory_slots[pos]:
                await session.send(p.item_description("The selected ingredients are no longer in your inventory."))
                return
            name = session.inventory_slots[pos]
            chosen[name] = chosen.get(name, 0) + quantity
        wanted = data[1 + count * 3]
        recipe = next((recipe for recipe in self.recipes
                       if dict(recipe.ingredients) == chosen), None)
        if not recipe:
            await session.send(p.item_description("No known recipe uses that exact selection of ingredients."))
            return
        required_knowledge = recipe.knowledge or infer_recipe_knowledge(
            recipe.output, recipe.skill, self.books)
        if required_knowledge and required_knowledge not in c.known_books:
            await session.send(p.item_description(
                f"You need to read {required_knowledge} before making {recipe.output}."))
            return
        if session.mix_task and not session.mix_task.done():
            session.mix_task.cancel()
        session.mix_status = None
        # This packet names inventory positions, so it can only ever have meant
        # the pack - and the flag has to be cleared rather than left, or a run
        # started here after one started from storage would quietly draw from
        # storage too.
        session.mix_from_storage = False
        session.mix_output = recipe.output
        session.mix_made = 0
        attempts = 0xFFFF if wanted == 255 else max(1, wanted)
        session.mix_remaining = attempts
        session.mix_task = asyncio.create_task(self._mix_loop(session, recipe, attempts))

    @staticmethod
    def mix_source(session: Session) -> dict[str, int]:
        """The pile a mix draws from: the pack, or the storage box beside it.

        Storage is the same dictionary shape as an inventory, so everything
        downstream counts and consumes without caring which it was handed -
        the one thing that differs is that a player has to be standing next
        to storage, and `mix_from_request` refuses before it gets here.
        """
        character = session.character
        if character is None:
            return {}
        return character.storage if session.mix_from_storage else character.inventory

    def return_mix_ingredients(self, c: Character, stock: dict[str, int], recipe) -> None:
        """Put a mix's ingredients back on the pile they were taken from.

        Straight back, as they were taken: not through `add_inventory`, whose
        capacity check made a pack already over its capacity (a newcomer whose
        allowance has ended) lose them, and which put a storage mix's
        ingredients in the pack instead of the box.
        """
        for name, quantity in recipe.ingredients:
            stock[name] = stock.get(name, 0) + quantity
        self.sync_inventory_slots(c)

    async def _mix_loop(self, session: Session, recipe, attempts: int):
        c = session.character
        if bell.on_map(c) or sky.on_map(c):
            await session.send(p.item_description(
                "Return to Four Gates before mixing with your permanent belongings."))
            return
        xp_ids = {"manufacturing":49, "alchemy":53, "potion":63, "summoning":67,
                  "crafting":71, "engineering":75, "tailoring":83}
        try:
            made = 0
            while made < attempts and c:
                stock = self.mix_source(session)
                if any(stock.get(name, 0) < quantity
                       for name, quantity in recipe.ingredients):
                    if not made:
                        await session.send(p.item_description(
                            "You do not have enough ingredients in storage."
                            if session.mix_from_storage
                            else "You do not have enough ingredients."))
                    break
                if any(c.inventory.get(tool, 0) < 1
                       and tool not in c.equipment.values()
                       for tool in recipe.tools):
                    await session.send(p.item_description("Required tools: " + ", ".join(recipe.tools)))
                    break
                summon_rule = None
                if recipe.skill == "summoning":
                    # A profile-local recipe names its own creature; otherwise
                    # fall back to the shared Eternal Lands summon table.
                    summon_rule = (SummonRule(recipe.summon, recipe.animal_nexus)
                                   if recipe.summon else instant_rule(recipe.output))
                if summon_rule and player_in_combat(session):
                    roads.emit(self,session,"summon_combat_refusal")
                    await session.send(p.item_description("You cannot summon while in combat."))
                    break
                if summon_rule and c.nexus["animal"] < summon_rule.animal_nexus:
                    await session.send(p.item_description(
                        f"You need Animal Nexus {summon_rule.animal_nexus} to summon {recipe.output}."))
                    break
                if c.food <= 0 or c.ether < recipe.mana:
                    await session.send(p.item_description("You do not have enough food or ethereal points."))
                    break
                await asyncio.sleep(0.8)
                session.last_mix_at = time.monotonic()
                c.food = max(-30, c.food - max(
                    0, int(round(recipe.food * mixing_food_scale(c)))))
                if c.food <= -30:
                    await self.disable_speed_hax(session)
                mana_cost = recipe.mana
                if summon_rule:
                    scale = summon_cost_scale(c)
                    if scale != 1.0:
                        mana_cost = max(1, int(round(mana_cost * scale)))
                c.ether -= mana_cost
                chance = (success_chance(c.skills["summoning"], recipe.level)
                          if summon_rule else
                          max(0.05, min(0.97, 0.65 + 0.03 *
                                      (c.skills[recipe.skill] - recipe.level))))
                outcome = roll_mix_outcome(chance)
                if outcome != "success":
                    critical = outcome == "critical_failure"
                    if critical and random.random() < careful_mixer_chance(c):
                        # Careful Mixer. The mix is still ruined; what it does
                        # not do is take the ingredients down with it.
                        critical = False
                        await session.send(p.item_description(
                            "You spoiled the mix but saved the ingredients."))
                    if critical:
                        for name, quantity in recipe.ingredients:
                            stock[name] -= quantity
                            if stock[name] <= 0:
                                del stock[name]
                        session.inventory_slots = self.sync_inventory_slots(c)
                        if modern := getattr(self, "modern", None):
                            for ingredient_name, ingredient_quantity in recipe.ingredients:
                                modern.record_economy(
                                    "mix_critical_loss", c.username,
                                    item_name=ingredient_name,
                                    quantity=ingredient_quantity,
                                    item_flow="sink",
                                    metadata={"recipe": recipe.output,
                                              "skill": recipe.skill})
                    if critical:
                        await self.record_activity(session, ACTIVITY_CRIT_FAILS)
                    message = (
                        f"You critically failed to make {recipe.output}; "
                        "the ingredients were lost."
                        if critical else
                        f"You failed to make {recipe.output}.")
                    session.mix_status = (message, 0)
                    self.save_soon(c)
                    if critical:
                        await session.send(p.inventory_packet(
                            c.inventory, ITEMS, c.equipment,
                            session.inventory_slots))
                    await session.send(p.item_description(*session.mix_status))
                    await self.send_stats(session, force=True)
                    await landing_runtime.tip(self, session, "mix_failed")
                    break
                rare_result = roll_rare_mix(
                    self.rare_mixes.get(recipe.output),
                    skill_level=c.skills[recipe.skill],
                    recommended_level=recipe.level,
                    chance_multiplier=rare_mix_multiplier(c))
                mixed_output = rare_result or recipe.output
                # Recycler: now and then the bench gives everything back.
                # Then nothing was taken, and a mix that cannot finish has
                # nothing to return either.
                taken = random.random() >= recycler_chance(c)
                if taken:
                    for name, quantity in recipe.ingredients:
                        stock[name] -= quantity
                        if stock[name] <= 0: del stock[name]
                if summon_rule:
                    animal = await self.spawn_summon(session, summon_rule.creature)
                    if not animal:
                        if taken:
                            self.return_mix_ingredients(c, stock, recipe)
                        break
                elif not self.add_inventory(
                        c, mixed_output, 1, source=f"mix:{recipe.output}",
                        creator=c.username):
                    if taken:
                        self.return_mix_ingredients(c, stock, recipe)
                    await session.send(p.item_description(
                        "You do not have enough carry capacity for the result."))
                    break
                # The mix is now committed: the ingredients are gone and the
                # result (or the summon) exists. Counting earlier would count a
                # request rather than an outcome.
                if summon_rule:
                    await self.record_activity(session, ACTIVITY_SUMMONS)
                mix_counter = ACTIVITY_MIX_SKILLS.get(recipe.skill)
                if mix_counter:
                    # What came out, not what was asked for: a rare result is
                    # the thing the bench actually made, and it is the row a
                    # player opens the total to find.
                    await self.record_activity(
                        session, mix_counter, detail=mixed_output)
                if modern := getattr(self, "modern", None):
                    for ingredient_name, ingredient_quantity in recipe.ingredients:
                        modern.record_economy(
                            "mix_ingredient", c.username,
                            item_name=ingredient_name,
                            quantity=ingredient_quantity, item_flow="sink",
                            metadata={"recipe": recipe.output,
                                      "skill": recipe.skill})
                    if not summon_rule:
                        modern.record_economy(
                            "mix_output", c.username, item_name=mixed_output,
                            quantity=1, item_flow="source",
                            metadata={"recipe": recipe.output,
                                      "rare": bool(rare_result),
                                      "skill": recipe.skill})
                if (recipe.output == "Fire Essence"
                        and c.map_id == "desert_pines_insides"
                        and c.quest_state.get("ayelle_alchemy_started")
                        and not c.quest_state.get("ayelle_first_objective_complete")):
                    c.quest_state["ayelle_fire_essence_made"] = True
                    await session.send(p.raw_text(
                        "Ayelle's lesson: Fire Essence made. Report back to Ayelle."))
                if (recipe.output == "Torch"
                        and not lantern.active(c)
                        and int(c.quest_state.get("beginner_tutorial", 0)) == 6
                        and not c.quest_state.get("tutorial_making_complete")):
                    tutorial_made = min(5, int(c.quest_state.get("tutorial_torches_made", 0)) + 1)
                    c.quest_state["tutorial_torches_made"] = tutorial_made
                    if tutorial_made == 5:
                        c.quest_state["tutorial_making_complete"] = True
                        await session.send(quest_progress_popup(
                            "Well made - five Torches. "
                            "Return to the Tutorial NPC for your reward."))
                await watchpost.dressing_mixed(self, session, recipe, mixed_output)
                await self.walkthrough_event(session, "mix", mixed_output)
                if session.mix_from_storage: roads.emit(self,session,"storage_mix",mixed_output)
                await self.questline_event(session, "mix", mixed_output)
                level_ups = []
                for skill in (recipe.skill, "overall"):
                    old = c.skills[skill]
                    gained = int(recipe.experience * self.experience_multiplier(recipe.skill, c))
                    c.experience[skill] = c.experience[skill] + gained
                    while c.skills[skill] < max_level_for(skill) and c.experience[skill] >= next_level_experience(c.skills[skill]):
                        c.skills[skill] += 1
                    if c.skills[skill] != old: level_ups.append((skill, old, c.skills[skill]))
                await session.send(p.partial_stats([(xp_ids[recipe.skill], c.experience[recipe.skill]),
                                                    (55, c.experience["overall"])]))
                await self.announce_levels(session, level_ups)
                session.mix_status = (
                    f"You made {mixed_output} and gained {recipe.experience} "
                    f"{recipe.skill} experience.", 10)
                await session.send(p.colored_text(
                    f"You successfully mixed {mixed_output}.", 10))
                if rare_result:
                    self.increment_achievement(c, "lucky_crafted")
                    self.increment_leaderboard(c, "rare_mixes")
                    await self.broadcast_map(
                        c.map_id,
                        p.actor_overtext(c.actor_id, rare_result, color=4))
                    await self.award_achievements(session)
                made += 1
                session.mix_made = made
                session.mix_remaining = max(0, attempts - made)
                session.inventory_slots = self.sync_inventory_slots(c)
                self.save_soon(c)
                await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
                # A full inventory refresh clears the stock client's bottom text.
                # Re-send the unchanged status so a success run stays readable.
                if session.mix_status:
                    await session.send(p.item_description(*session.mix_status))
                await self.send_stats(session, force=True)
        except asyncio.CancelledError:
            pass
        finally:
            # However the run ended - finished, out of materials, cancelled -
            # the window is told, because a queue that was never told would
            # wait for a batch that had already stopped.
            session.mix_remaining = 0
            await self.send_mix_state(session)

    async def _harvest_loop(self, session: Session, node):
        c = session.character
        resource = self.harvest_resources[node.resource]
        session.harvest_required_level = resource.required_level
        started = False
        try:
            if max(abs(c.x-node.x), abs(c.y-node.y)) > 2:
                await self.move(c, node.x, node.y)
            if max(abs(c.x-node.x), abs(c.y-node.y)) > 2:
                await session.send(p.raw_text("You could not get close enough to harvest."))
                return
            if resource.tool and c.inventory.get(resource.tool, 0) < 1 \
                    and resource.tool not in c.equipment.values():
                await session.send(p.raw_text(f"You need a {resource.tool} to harvest this."))
                return
            # The stock client matches this exact phrase to set its local
            # harvesting state and display the optional ongoing eye candy.
            await session.send(p.harvesting_text(
                f"You started to harvest {resource.name}."))
            await self.send_harvest_state(session, True, node.object_id, resource.name)
            started = True
            while c and c.map_id == node.map_id and not session.aggressors:
                tutorial_step_message = None
                await asyncio.sleep(harvest_interval(
                    c.skills["harvesting"], resource.required_level,
                    self.area_multiplier(c, HARVEST_SPEED)))
                item = ITEMS.get(resource.name)
                if not item or not self.can_add_inventory(c, [(resource.name, 1)]):
                    await session.send(p.raw_text("You cannot carry any more."))
                    await landing_runtime.tip(self, session, "pack_full")
                    return
                self.add_inventory(c, resource.name, 1)
                # Register 020, Gatherer. A second item from the same swing,
                # rolled after the first is safely in - so a full pack loses
                # the bonus rather than the harvest.
                if (random.random() < harvest_extra_chance(c)
                        and self.can_add_inventory(c, [(resource.name, 1)])):
                    self.add_inventory(c, resource.name, 1)
                await self.record_activity(
                    session, ACTIVITY_HARVESTS, detail=resource.name)
                await self.walkthrough_event(session, "harvest", resource.name)
                await self.questline_event(
                    session, "harvest", resource.name, node.x, node.y)
                if modern := getattr(self, "modern", None):
                    modern.record_economy(
                        "harvest_yield", c.username, item_name=resource.name,
                        quantity=1, item_flow="source",
                        metadata={"map_id": node.map_id,
                                  "x": node.x, "y": node.y})
                daily_task = current_daily_task(c)
                daily_complete = record_daily_harvest(
                    c, resource.name, node.map_id, node.x, node.y)
                if daily_complete and daily_task:
                    self.save_soon(c)
                    await session.send(quest_progress_popup(
                        f"Daily quest complete!\n"
                        f"You harvested {daily_task.amount} {daily_task.target}.\n"
                        f"Return to {daily_task.client} to receive your reward."))
                if (not lantern.active(c) and int(c.quest_state.get("beginner_tutorial", 0)) == 3
                        and c.quest_state.get("harvest_tutorial_started")):
                    flower_index = int(c.quest_state.get("tutorial_flower_index", 0))
                    if flower_index < len(TUTORIAL_HARVESTS):
                        expected, _, _, needed = TUTORIAL_HARVESTS[flower_index]
                        if resource.name == expected:
                            count = int(c.quest_state.get("tutorial_flower_count", 0)) + 1
                            if count >= needed:
                                c.quest_state["tutorial_flower_index"] = flower_index + 1
                                c.quest_state["tutorial_flower_count"] = 0
                                await self.sync_tutorial_markers(session)
                                if flower_index + 1 == len(TUTORIAL_HARVESTS):
                                    tutorial_step_message = (
                                        "Excellent, you harvested all eight resources.\n"
                                        "You got some Harvesting experience.\n"
                                        "Deposit them with Cache Keeper Dellin and return to Wayfinder Nesh.")
                                else:
                                    next_name = TUTORIAL_HARVESTS[flower_index + 1][0]
                                    tutorial_step_message = (
                                        f"Excellent, now move to the {next_name}.\n"
                                        "You got some Harvesting experience.\n"
                                        "New map marker available.")
                            else:
                                c.quest_state["tutorial_flower_count"] = count
                resource_name = resource.name.casefold()
                mineral_names = ("ore", "quartz", "ruby", "emerald", "sapphire", "diamond",
                                 "amber", "cinnabar", "gypsum", "turquoise", "wolframite",
                                 "coal", "sulfur")
                if any(word in resource_name for word in mineral_names):
                    self.increment_achievement(c, "minerals_harvested")
                else:
                    self.increment_achievement(c, "plants_harvested")
                rare_entries = self.rare_harvest.get(resource.name, self.rare_harvest.get("*", ()))
                lucky = 1.0 + rare_harvest_bonus(c)
                for rare in rare_entries:
                    if (random.random() < rare.chance * lucky
                            and self.add_inventory(c, rare.item, 1)):
                        self.increment_achievement(c, "lucky_finds")
                        await session.send(p.colored_text(
                            f"You found a {rare.item} while harvesting!", 3))
                        break
                hour = self.game_minute // 60
                if session.harvest_hour != hour:
                    session.harvest_hour, session.harvest_count = hour, 0
                level_ups = []
                xp_awarded = False
                if session.harvest_count < 120:
                    session.harvest_count += 1
                    xp_awarded = True
                    gained = int(resource.experience * self.experience_multiplier("harvesting", c))
                    for skill, amount in (("harvesting", gained),
                                          ("overall", gained)):
                        old = c.skills[skill]
                        c.experience[skill] = c.experience[skill] + amount
                        while c.skills[skill] < max_level_for(skill) and c.experience[skill] >= next_level_experience(c.skills[skill]):
                            c.skills[skill] += 1
                        if c.skills[skill] != old:
                            level_ups.append((skill, old, c.skills[skill]))
                elif session.harvest_count == 120:
                    session.harvest_count += 1
                    await session.send(p.colored_text(
                        "You have harvested 120 items this hour; harvesting XP is paused.", 1))
                session.inventory_slots = self.sync_inventory_slots(c)
                self.save_soon(c)
                await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
                if xp_awarded:
                    await session.send(p.partial_stats([
                        (51, c.experience["harvesting"]), (55, c.experience["overall"])]))
                await self.announce_levels(session, level_ups)
                # The plant/mineral split is incremented above, after the
                # `Harvests` total went out, so the catalogue is asked again
                # here rather than reading a stale pair.
                await self.award_achievements(session)
                await self.send_stats(session, force=True)
                if tutorial_step_message:
                    # Channel 255 is the stock client's server-popup channel.
                    # Returning ends this harvesting action after the one item.
                    # c_grey1 (palette index 6) is the stock client's bright
                    # white text used by the Eternal Lands tutorial popups.
                    await session.send(quest_progress_popup(tutorial_step_message))
                    return
                event = random.randrange(250)
                if event in (0, 1):
                    await self.record_activity(session, ACTIVITY_EVENTS)
                if event == 0:
                    damage = random.randint(1, 5)
                    applied = min(c.health, damage)
                    if applied > 0:
                        self.increment_achievement(c, "nature_damage", applied)
                        await self.damage_player(
                            session, damage, cause="Harvesting bees")
                    await session.send(p.colored_text("A swarm of bees interrupts your harvesting!", 1))
                    await self.broadcast_map(c.map_id, p.special_effect(17, c.actor_id))
                    return
                if event == 1 and xp_awarded:
                    self.increment_achievement(c, "lucky_finds")
                    bonus = random.randint(200, 700)
                    level_ups = award_experience(c, (("harvesting", bonus),))
                    await session.send(p.colored_text(
                        f"Mother Nature blesses you with {bonus} harvesting experience!",
                        p.EL_COLOR_GREEN3))
                    await session.send(p.partial_stats([
                        (51, c.experience["harvesting"]), (55, c.experience["overall"])]))
                    await self.announce_levels(session, level_ups)
                    await self.broadcast_map(c.map_id, p.special_effect(14, c.actor_id))
                    await self.send_stats(session, force=True)
                    return
            if started and session.aggressors:
                await landing_runtime.tip(self, session, "harvest_stopped")
        except asyncio.CancelledError:
            pass
        finally:
            if started:
                # This exact stock phrase clears the client harvesting state
                # and recalls its ongoing eye-candy effect on every exit path.
                await session.send(p.harvesting_text(
                    "You stopped harvesting."))
                await self.send_harvest_state(session, False)
            if session.harvest_task is asyncio.current_task():
                session.harvest_task = None
            session.harvest_required_level = None

    def quest_journal_entries(self, c: Character) -> list[tuple]:
        """Build one normalized view of active tutorial, daily, and hunting-chain quests."""
        entries = []
        if sky.on_map(c) or c.quest_state.get(sky.STATE):
            active_sky = sky.on_map(c)
            step = sky.current(c) if active_sky else None
            entries.append(("The Borrowed Sky", step.title + " — " + step.hint if step else "Completed." if c.quest_state.get(sky.STATE)==99 else "Talk to Sera or use #tutorial magic to resume.", "Stillglass Observatory", int(c.quest_state.get("sky_stage", 1))-1 if active_sky else 1, len(sky.route(c)) if active_sky else 1, not active_sky and c.quest_state.get(sky.STATE)==99))
            if active_sky: return entries
        if bell.active(c):
            step = bell.current(c)
            entries.append(("The Second Bell", step.title + ": " + step.hint,
                "Bellwatch (talk to Ilyon to resume)" if bell.flag(c, "paused") else "Bellwatch",
                bell.stage(c)-1, len(bell.STEPS), False))
            if bell.on_map(c): return entries
        elif bell.stage(c) == bell.DONE:
            entries.append(("The Second Bell", "Bellwatch is safe. " +
                ("Completed with assistance." if bell.flag(c, "assisted") else "Completed the independent departure encounter."),
                "Four Gates", len(bell.STEPS), len(bell.STEPS), True))
        entries.extend(landing_runtime.journal_entries(self, c))
        entries.extend(watchpost.journal(c))
        if lantern.active(c):
            step = lantern.current(c)
            entries.append(("The Last Lantern", step.title + ": " + step.hint,
                "Four Gates" if step.key == "handoff" else "Lantern Reach",
                lantern.stage(c)-1, len(lantern.STEPS), False))
            return entries
        stage = int(c.quest_state.get("beginner_tutorial", 0))
        if stage in {1, 2}:
            entries.append((
                "Scouting tutorial",
                f"Follow the blue markers south and talk to {TUTORIAL_ROUTE_NPC}.",
                "Four Gates", int(stage >= 2), 1, stage >= 2))
        elif 3 <= stage <= TUTORIAL_FINAL_STAGE:
            title, objective, ready = self.tutorial_status(c, stage)
            current, target = (int(ready), 1)
            if stage == 4:
                current = max(0, c.kills.get("crown_antler_stag", 0) -
                              int(c.quest_state.get("tutorial_quarry_kills_start", 0)))
                target = 10
            elif stage == 6:
                current = int(c.quest_state.get("tutorial_torches_made", 0))
                target = 5
            entries.append((title, objective, "Tutorial", current, target, ready))

        if wt.is_active(c):
            panel = wt.panel_for(c)
            if panel:
                entries.append((
                    f"Four Gates: {panel.title}", panel.objective, "Four Gates",
                    min(wt.progress(c, panel.stage), panel.target),
                    panel.target, False))

        for quest in self.questlines.values():
            entry = ql.journal_entry(c, quest)
            if entry:
                entries.append(entry)

        road_stage = int(c.quest_state.get("nymara_road_stage", -1))
        if not c.quest_state.get("nymara_road_complete") and road_stage >= 0:
            target = self.NYMARA_ROAD[min(road_stage, len(self.NYMARA_ROAD) - 1)]
            entries.append((
                "The Western Road", target[2], target[1],
                road_stage, len(self.NYMARA_ROAD), False))

        task = current_daily_task(c)
        daily_key = active_daily_key(c)
        if task and daily_key:
            current = (c.inventory.get(task.target, 0) if task.kind == "delivery"
                       else int(c.quest_state.get("daily_progress", 0)))
            location = task.map_id.replace("_", " ").title()
            entries.append((
                f"{DAILY_START_NPCS.get(daily_key, daily_key.title())}'s daily quest",
                daily_task_text(task, current), location, current, task.amount,
                current >= task.amount))

        for quest in NOVAC_QUESTS.values():
            objective = novac_objective(c, quest)
            if not objective:
                continue
            entries.append((
                quest.title, f"Kill your assigned {objective.name}, then return to Tallykeeper Ysolde.",
                objective.location or "See the active map marker", int(novac_pending(c, quest)),
                1, novac_pending(c, quest)))
        return entries

    def completed_quest_entries(self, c: Character) -> list[tuple]:
        """Everything this character has finished, gathered into one list.

        The journal above answers "what am I doing"; nothing answered "what
        have I done". A player who changed machine, or lost a client log, had
        no way to find out - and the server knew the whole time, because every
        one of these completions is already durable state. It is only that
        each quest kind records its ending in its own way, so they are joined
        here rather than any of them being asked to change how they store it.

        Ordered by kind rather than by date: none of these completions records
        *when* it happened, and inventing an order would be worse than a
        stable one.
        """
        entries: list[tuple] = []
        if "Keeper of the First Light" in c.achievements:
            entries.append(("The Last Lantern", "Lantern Reach", "You restored the beacon and guided the boat home."))
        entries.extend(landing_runtime.archive_entries(c))
        entries.extend(watchpost.archive(c))
        if "Beginner Tutorial" in c.achievements:
            entries.append(("Beginner Tutorial", "Four Gates",
                            "You learned to move, fight, gather and mix."))
        if int(c.quest_state.get(wt.STATE, 0)) >= wt.DONE:
            entries.append(("The Four Gates walkthrough", "Four Gates",
                            "You were shown the city and what it is for."))
        if c.quest_state.get("nymara_road_complete"):
            entries.append(("The Western Road", "Nymara",
                            "You walked the road west and came back."))
        for quest in self.questlines.values():
            if ql.finished(c, quest):
                entries.append((
                    quest.title, ql.region_name(quest.region),
                    quest.complete or f"Finished for {quest.start}."))
        for quest in NOVAC_QUESTS.values():
            if novac_completed(c, quest):
                entries.append((quest.title, "Tallykeeper Ysolde",
                                "Every assigned creature was killed."))
        return entries

    def teleporter_tiles(self, map_id: str) -> list[tuple[int, int]]:
        """Every tile on a map that takes you somewhere else.

        Not the tiles of a seamless land crossing: those are the map's own
        border, walked over wherever the ground allows, and no more a way
        somewhere else than the ground beside them. Listing them would also
        bury the doors - a border open along its length is hundreds of tiles,
        and the packet carries 255.
        """
        land = getattr(self, 'land_connections', {})
        return sorted({(portal.x, portal.y)
                       for portal in portals_leaving(self, map_id)
                       if portal.object_id is not None
                       or (map_id, portal.destination) not in land})

    async def send_teleporters(self, session: Session) -> None:
        c = session.character
        if not c:
            return
        await session.send(self.coordinate_packet(session, c.map_id,
            lambda point: p.teleporters_list([point(x, y) for x, y in self.teleporter_tiles(c.map_id)])))

    async def place_world_object(self, map_id: str, object_id: int, x: int,
                                 y: int, rotation: int, model: str) -> None:
        """Put an object into a map that is already being played in.

        Everything the client knew about a map came with the map. An event
        that raises a totem in the square, or clears one away, had no way to
        say so, so the world could not change while anybody was looking at it.
        """
        self.world_objects.setdefault(map_id, {})[object_id] = (
            x, y, rotation, model)
        await self.broadcast_coordinates(map_id,
            lambda point: p.world_object(object_id, *point(x, y), rotation, model))

    async def remove_world_object(self, map_id: str, object_id: int) -> None:
        placed = self.world_objects.get(map_id, {})
        if object_id not in placed:
            return
        del placed[object_id]
        await self.broadcast_map(map_id, p.remove_world_object(object_id))

    async def send_world_objects(self, session: Session) -> None:
        """Everything already standing on this map, for someone arriving."""
        c = session.character
        if not c:
            return
        placed = self.world_objects.get(c.map_id, {})
        if not placed:
            return
        await session.send(self.coordinate_packet(session, c.map_id,
            lambda point: p.world_object_list(
                [(object_id, *point(x, y), rotation, model)
                 for object_id, (x, y, rotation, model) in sorted(placed.items())])))

    async def announce_teleport(self, character, from_tile, to_tile) -> None:
        """Both ends of a teleport, each to the map it happened on.

        The actor packets already say who moved; these say where the two ends
        were, which is the only part a client cannot work out - by the time it
        is told about the arrival, the departure has already gone.
        """
        if from_tile is not None:
            await self.broadcast_coordinates(from_tile[0],
                lambda point: p.teleport_out(*point(from_tile[1], from_tile[2])))
        if to_tile is not None:
            await self.broadcast_coordinates(to_tile[0],
                lambda point: p.teleport_in(*point(to_tile[1], to_tile[2])))

    async def add_buddy(self, session: Session, name: str) -> None:
        """Put a name on the player's own list.

        Nobody is asked and nobody is told: a buddy list is one player's note
        about who they want to know is around, not a friendship both sides
        have to agree to, so there is no request to accept and no way to use
        it to pester anybody.
        """
        c = session.character
        if not c:
            return
        try:
            added = add_buddy(self.db, c.username, name)
        except ValueError as refusal:
            await session.send(p.raw_text(str(refusal)))
            return
        await session.send(p.buddy_event(BUDDY_ADDED, added))
        await session.send(p.raw_text(f"{added} is on your list."))
        # Tell them straight away whether that person is here.
        if self.find_player(added):
            await session.send(p.buddy_event(BUDDY_ONLINE, added))

    async def remove_buddy(self, session: Session, name: str) -> None:
        c = session.character
        if not c:
            return
        try:
            removed = remove_buddy(self.db, c.username, name)
        except ValueError as refusal:
            await session.send(p.raw_text(str(refusal)))
            return
        await session.send(p.buddy_event(BUDDY_REMOVED, removed))
        await session.send(p.raw_text(f"{removed} is off your list."))

    async def send_buddy_list(self, session: Session) -> None:
        """State the whole list, and who on it is here.

        Sent at login so a client never has to keep its own copy: the list is
        the server's, and a client asking "who is on my list" is asking the
        only thing that knows.
        """
        c = session.character
        if not c:
            return
        for name in load_buddies(self.db, c.username):
            await session.send(p.buddy_event(BUDDY_ADDED, name))
            if self.find_player(name):
                await session.send(p.buddy_event(BUDDY_ONLINE, name))

    async def announce_buddy_presence(self, character, online: bool) -> None:
        """Tell everyone watching that somebody arrived or left."""
        watching = watchers_of(
            self.db,
            [session.character.username for session in list(self.sessions)
             if session.character],
            character.name)
        if not watching:
            return
        frame = p.buddy_event(BUDDY_ONLINE if online else BUDDY_OFFLINE,
                              character.name)
        for session in list(self.sessions):
            if (session.character
                    and session.character.username in watching
                    and session.character is not character):
                try:
                    await session.send(frame)
                except (ConnectionError, asyncio.CancelledError):
                    pass

    async def announce_quest_dialogue(self, session: Session,
                                      quest_id: int) -> None:
        """Say that the NPC text about to be sent belongs to a quest.

        The flag goes first because it describes the frame after it, and the
        id follows so a client can file the dialogue against the right quest.
        A quest with no id says nothing at all rather than sending zero, which
        a client would have to special-case.
        """
        if quest_id <= 0:
            return
        await session.send(p.next_npc_message_is_quest())
        await session.send(p.here_is_quest_id(quest_id))

    async def announce_quest_finished(self, session: Session,
                                      quest_id: int) -> None:
        if quest_id > 0:
            await session.send(p.quest_finished(quest_id))

    def questline_ids(self) -> dict[str, int]:
        """Journal title -> quest id, for the profile's own quest lines.

        The stable ids in `quest_ids.py` are for the quests written in code.
        A profile's quest lines carry their own ids in their config, so the
        two registries are joined here rather than one of them guessing.
        """
        return {quest.title: quest.quest_id for quest in self.questlines.values()}

    def quest_id_for_title(self, title: str) -> int:
        return self.questline_ids().get(title) or id_for_title(title)

    def quest_title_for_id(self, quest_id: int) -> str:
        for title, known in self.questline_ids().items():
            if known == int(quest_id):
                return title
        return title_for_id(quest_id)

    def active_quest_id(self, c: Character) -> int:
        """The quest whose dialogue an NPC is most likely giving right now.

        Taken from the journal rather than kept separately, so the two cannot
        disagree about what the player is doing.
        """
        for entry in self.quest_journal_entries(c):
            found = self.quest_id_for_title(str(entry[0]))
            if found:
                return found
        return 0

    async def answer_quest_title(self, session: Session, quest_id: int) -> None:
        """What `WHAT_QUEST_IS_THIS_ID(63)` asks for: the quest's name.

        An id this server does not know is answered with an empty title rather
        than with silence, so a client is never left waiting on a reply that
        is not coming.
        """
        await session.send(p.here_is_quest_id(quest_id))
        await session.send(p.raw_text(self.quest_title_for_id(quest_id) or
                                      "That is not a quest this world knows."))

    async def send_quest_journal(self, session: Session) -> None:
        c = session.character
        if not c:
            return
        entries = self.quest_journal_entries(c)
        if "quest_journal_v1" in session.client_capabilities:
            await session.send(p.quest_journal_state(entries))
            return
        if not entries:
            await session.send(p.raw_text("Quest journal: no active quests."))
        for title, objective, location, current, target, ready in entries:
            status = "Ready to turn in" if ready else f"{current}/{target}"
            await session.send(p.raw_text(
                f"{title} [{status}] - {objective} ({location})"))

    async def send_quest_archive(self, session: Session) -> None:
        """What this character has finished.

        A capable client gets the packet and draws it; anything else gets the
        same list as text. Either way the record comes from the server, so it
        survives a reinstall, a new machine, and a lost chat log - which is
        what a player who lost theirs had no way to recover.
        """
        c = session.character
        if not c:
            return
        entries = self.completed_quest_entries(c)
        if "quest_archive_v1" in session.client_capabilities:
            await session.send(p.quest_archive_state(entries))
            return
        if not entries:
            await session.send(p.raw_text(
                "You have not finished any quests yet."))
            return
        await session.send(p.raw_text(
            f"Completed quests ({len(entries)}):"))
        for title, location, detail in entries:
            await session.send(p.raw_text(f"  {title} ({location}) - {detail}"))

    async def tutorial_main_menu(self, session: Session, actor_id: int,
                                 text: str | None = None, *, ladder: bool = True) -> None:
        """The ladder guide's menu; `ladder` False offers none of the ladder.

        Without it the guide says who he is and heals newcomers (1000, 1002)
        and nothing else, whatever stage the player's ladder is at, and
        leaves the ladder's markers, which stand at Four Gates, as they are.
        """
        c = session.character
        stage = int(c.quest_state.get("beginner_tutorial", 0)) if ladder else 0
        if stage > TUTORIAL_FINAL_STAGE:
            if "Beginner Tutorial" in c.achievements:
                await session.send(p.npc_text("You have completed the Beginner Tutorial."))
                await session.send(p.npc_options(actor_id, [(1002, "Heal me"), (900, "Bye")]))
                return
            # Retired lessons beyond the current ladder cannot be handed in.
            # Resume those older saves at the final supported hand-in instead.
            c.quest_state["beginner_tutorial"] = stage = TUTORIAL_FINAL_STAGE
            self.db.save(c)
        if stage in {3, 5}:
            self.prepare_tutorial_stage(c, stage)
            self.db.save(c)
        if ladder:
            await self.sync_tutorial_markers(session)
        # A tutorial NPC is giving quest dialogue whenever the player is in
        # one, which is what the flag is for.
        if stage:
            await self.announce_quest_dialogue(session, self.active_quest_id(c))
        await session.send(p.npc_text(text or
            f'For some unknown reason, maybe because of the floating name above his head, '
            f'you guess this is a tutorial NPC designed to help you. He says: "Hello, {c.name}. Do you need any help?"'))
        options = [(1000, "Who are you?")]
        if stage == 0:
            if ladder:
                options.append((1001, "Tutorials"))
        elif stage == 1:
            options.append((1003, "What's my current task?"))
        elif stage == 2:
            options.append((801, "Scouting tutorial completed"))
        elif stage == 3:
            title, _, complete = self.tutorial_status(c, stage)
            if complete:
                options.append((801, f"{title} completed"))
            elif c.quest_state.get("harvest_tutorial_started"):
                options.append((1003, "What's my current task?"))
            else:
                options.append((1200, "Harvest Tutorial"))
        elif stage > 3:
            title, _, complete = self.tutorial_status(c, min(stage, TUTORIAL_FINAL_STAGE))
            if complete:
                options.append((801, f"{title} completed"))
            else:
                options.append((1003, "What's my current task?"))
        options.extend([(1002, "Heal me")]
                       + ([(1003, "What's my current task?")] if ladder else [])
                       + [(900, "Bye")])
        # Preserve order while removing a duplicate current-task option.
        await session.send(p.npc_options(actor_id, list(dict.fromkeys(options))))

    @staticmethod
    def bearing_from(origin: tuple[int, int], target: tuple[int, int]) -> str:
        """Name the compass direction from one tile to another, EL-style."""
        dx, dy = target[0] - origin[0], target[1] - origin[1]
        if not dx and not dy:
            return "right here"
        vertical = "north" if dy > 0 else "south" if dy < 0 else ""
        horizontal = "east" if dx > 0 else "west" if dx < 0 else ""
        # Only name the second axis when it carries real distance.
        if vertical and horizontal and min(abs(dx), abs(dy)) * 2 < max(abs(dx), abs(dy)):
            return vertical if abs(dy) > abs(dx) else horizontal
        return f"{vertical}{horizontal}" or vertical or horizontal

    SERVICE_LABELS = {"storage": "a storage cache", "shop": "a shop",
                      "auction": "the Exchange", "sigil": "sigils",
                      "guide": "directions"}

    async def answer_guide_question(self, session: Session, actor_id: int,
                                    response_id: int) -> None:
        """Answer a guide NPC's questions from the region's own configuration."""
        c = session.character
        if not c:
            return
        here = (c.x, c.y)
        lines: list[str] = []
        if response_id == 710:
            for npc, map_id, _, _ in self.npcs.values():
                role = self.npc_roles.get(npc.actor_id, "dialogue")
                if map_id != c.map_id or npc.actor_id == actor_id:
                    continue
                label = self.SERVICE_LABELS.get(role)
                if label:
                    lines.append(f"{npc.name} keeps {label}, "
                                 f"{self.bearing_from(here, (npc.x, npc.y))} of here.")
            for entry in self.interactives.values():
                if entry.map_id != c.map_id or entry.role in {"portal", "scenery_effect"}:
                    continue
                lines.append(f"{entry.text} It is "
                             f"{self.bearing_from(here, (entry.x, entry.y))} of here.")
            if not lines:
                lines.append("Nothing here but the road, I am afraid.")
        elif response_id == 711:
            # One line per destination, by its portal nearest the asker, in
            # the order the table first lists it. An object portal says its
            # own row's text (the isle's ferry names the boat, where it goes
            # and who keeps it); a secret door is a thing to find, not a road.
            nearest: dict[str, tuple] = {}
            for portal in portals_leaving(self, c.map_id):
                entry = (self.interactives.get((c.map_id, portal.object_id))
                         if portal.object_id is not None else None)
                if entry is not None and entry.role == "secret":
                    continue
                distance = (portal.x - here[0]) ** 2 + (portal.y - here[1]) ** 2
                known = nearest.get(portal.destination)
                if known is None or distance < known[0]:
                    nearest[portal.destination] = (distance, portal, entry)
            for _, portal, entry in nearest.values():
                bearing = self.bearing_from(here, (portal.x, portal.y))
                if entry is not None and entry.role == "portal":
                    lines.append(f"{entry.text} It is {bearing} of here.")
                else:
                    destination = self.maps.get(portal.destination)
                    name = destination.name if destination else portal.destination
                    lines.append(f"{name} lies {bearing} of here.")
            if not lines:
                lines.append("No road leaves from here.")
        else:
            for npc, map_id, _, _ in self.npcs.values():
                if map_id != c.map_id:
                    continue
                if npc.name.casefold() in {
                        name.casefold() for name in DAILY_START_NPCS.values()}:
                    lines.append(f"{npc.name} posts work worth taking.")
            lines.append("Your quest log keeps whatever you accept.")
        await session.send(p.npc_text("\n".join(lines[:12])))
        await session.send(p.npc_options(actor_id, [
            (710, "Where do I find things here?"),
            (711, "Where do the roads go?"),
            (712, "What work is there?"),
            (900, "Goodbye")]))

    # ---------------------------------------------------------------- #
    # The Four Gates walkthrough                                        #
    # ---------------------------------------------------------------- #

    @property
    def walkthrough_available(self) -> bool:
        """Nymara content only; the compatibility profile has no Four Gates."""
        return wt.HOME_MAP in self.maps

    def walkthrough_chapter(self, c: Character) -> wt.Chapter | None:
        return wt.active_chapter(c) if self.walkthrough_available and not lantern.active(c) and not bell.on_map(c) and not sky.on_map(c) and not landing.active(c) else None

    def walkthrough_marker_target(self, c: Character,
                                  panel: wt.Panel) -> tuple[int, int] | None:
        """Resolve where this panel's marker belongs, if it has one."""
        if panel.marker:
            return panel.marker
        if panel.event == "summon":
            # Reuse the harvest lesson's exposed Reed patch. Other nearby
            # patches lie beneath market awnings in the authored 3D scene.
            return next(((x, y) for name, x, y, _ in TUTORIAL_HARVESTS
                         if name == panel.marker_label), None)
        if panel.marker_npc:
            nodes = [npc for npc, map_id, _, _ in self.npcs.values()
                     if map_id == wt.HOME_MAP and npc.name == panel.marker_npc]
        elif panel.marker_role:
            nodes = [entry for entry in self.interactives.values()
                     if entry.map_id == wt.HOME_MAP and entry.role == panel.marker_role]
        elif panel.event == "harvest":
            nodes = [node for node in self.harvest_nodes.values()
                     if node.map_id == wt.HOME_MAP and node.resource == panel.marker_label]
        elif panel.event in {"kill", "ranged_kill"}:
            nodes = [spawn for spawn in self.spawn_definitions
                     if spawn.map_id == wt.HOME_MAP and spawn.creature == wt.STARTER_CREATURE]
        elif panel.event == "travel":
            nodes = [portal for portal in portals_leaving(self, wt.HOME_MAP)
                     if portal.object_id is None
                     and portal.destination in {"mirrorhold", "crownwater",
                                                "sunmane_steppe", "ssarathi_ruins"}]
        else:
            nodes = []
        if not nodes:
            return None
        nearest = min(nodes, key=lambda n: max(abs(n.x - c.x), abs(n.y - c.y)))
        return (nearest.x, nearest.y)

    async def sync_walkthrough_marker(self, session: Session) -> None:
        c = session.character
        if not c:
            return
        await session.send(p.remove_map_marker(wt.MARKER_ID))
        chapter = self.walkthrough_chapter(c)
        if not chapter or not chapter.is_active(c):
            return
        panel = chapter.panel_for(c)
        target = self.walkthrough_marker_target(c, panel) if panel else None
        if not target:
            return
        definition = self.maps.get(wt.HOME_MAP)
        if not definition:
            return
        await self.send_map_marker(session, wt.MARKER_ID, target[0], target[1], definition.client_name, panel.marker_label or panel.title)

    async def send_walkthrough_text(self, session: Session, title: str,
                                    *paragraphs: str) -> None:
        """Deliver one panel as a popup, or as console text when asked to."""
        c = session.character
        if not c:
            return
        if wt.wants_popups(c):
            await session.send(quest_progress_popup(
                "\n\n".join((title,) + paragraphs)))
            return
        await session.send(p.raw_text(f"[{title}]"))
        for paragraph in paragraphs:
            await session.send(p.raw_text(paragraph))

    async def send_walkthrough_panel(self, session: Session) -> None:
        c = session.character
        chapter = self.walkthrough_chapter(c) if c else None
        panel = chapter.panel_for(c) if chapter else None
        if not panel:
            return
        # Some lessons describe a state the player may already have reached.
        # Requiring another deposit, meal, or unread copy can strand a resume.
        if chapter.is_active(c):
            current = None
            detail = ""
            if panel.event == "storage":
                detail, current = wt.SAGE, c.storage.get(wt.SAGE, 0)
            elif panel.event == "food":
                current = c.food
            elif panel.event == "read":
                book = self.books.get(wt.BOOK)
                if book and (book.knowledge in c.known_books
                             or c.reading_book == book.knowledge):
                    detail, current = wt.BOOK, panel.target
            if current is not None and current >= panel.target:
                await self.walkthrough_event(session, panel.event, detail, current)
                return
        if panel.is_choice:
            # The panel carries its own popup id and button labels.
            await session.send(p.display_popup(
                panel.popup_id, panel.title, panel.body[0], panel.choices,
                lines=panel.body[1:]))
            return
        await self.send_walkthrough_text(session, panel.title, *panel.body)
        await self.sync_walkthrough_marker(session)

    async def offer_walkthrough(self, session: Session) -> bool:
        """Show the opening panel on a character's first arrival in Nymara."""
        c = session.character
        if not c or not self.walkthrough_available or lantern.active(c) or bell.on_map(c) or sky.on_map(c) or landing.active(c):
            return False
        if wt.roads_ready(c):
            # Chapter one is behind them and the long roads are affordable.
            await self.start_walkthrough(
                session, wt.LONG_ROADS, wt.ROADS_FIRST_STAGE)
            return True
        if wt.stage_of(c) or c.quest_state.get(wt.SKIPPED):
            return False
        c.quest_state[wt.STATE] = wt.FIRST_STAGE
        c.quest_state.setdefault(wt.POPUPS, 1)
        self.db.save(c)
        await self.send_walkthrough_panel(session)
        return True

    async def resume_walkthrough(self, session: Session) -> None:
        """Re-send the current panel, so a reconnect never leaves it guessing."""
        c = session.character
        if c and self.walkthrough_chapter(c):
            await self.send_walkthrough_panel(session)

    async def start_walkthrough(self, session: Session, chapter: wt.Chapter,
                                stage: int) -> None:
        """Enter a new stage, or resume without discarding earned progress."""
        c = session.character
        if not c:
            return
        if chapter.stage_of(c) != stage:
            c.quest_state.pop(chapter.progress_key(stage), None)
        c.quest_state[chapter.state] = stage
        c.quest_state.pop(chapter.stopped, None)
        c.quest_state.pop(chapter.skipped, None)
        self.db.save(c)
        await self.send_walkthrough_panel(session)

    async def restart_walkthrough(self, session: Session) -> None:
        """Pick the walkthrough back up wherever the player left it."""
        c = session.character
        if not c:
            return
        if not self.walkthrough_available:
            await session.send(p.raw_text("There is no walkthrough here."))
            return
        for chapter in wt.CHAPTERS:
            stage = chapter.stage_of(c)
            if stage and stage != wt.DONE:
                await self.start_walkthrough(session, chapter, stage)
                return
        # Nothing part-finished: offer whichever chapter is next owed.
        if wt.FOUR_GATES.stage_of(c) != wt.DONE:
            await self.start_walkthrough(
                session, wt.FOUR_GATES, wt.FIRST_STAGE)
            return
        if wt.LONG_ROADS.stage_of(c) == wt.DONE:
            await session.send(p.raw_text(
                "You have already finished both walkthroughs."))
            return
        if not wt.roads_ready(c):
            await session.send(p.raw_text(
                f"The long roads want overall level {wt.ROADS_LEVEL} and "
                f"{wt.ROADS_GOLD:,} gold; sigils and arrows are not cheap."))
            return
        await self.start_walkthrough(
            session, wt.LONG_ROADS, wt.ROADS_FIRST_STAGE)

    async def stop_walkthrough(self, session: Session) -> None:
        c = session.character
        chapter = self.walkthrough_chapter(c) if c else None
        if not chapter or not chapter.is_active(c):
            await session.send(p.raw_text("The walkthrough is not running."))
            return
        c.quest_state[chapter.stopped] = chapter.stage_of(c)
        self.db.save(c)
        await session.send(p.remove_map_marker(wt.MARKER_ID))
        await self.send_walkthrough_text(session, *chapter.stopped_text)

    async def set_walkthrough_popups(self, session: Session, enabled: bool) -> None:
        c = session.character
        if not c:
            return
        c.quest_state[wt.POPUPS] = 1 if enabled else 0
        self.db.save(c)
        await session.send(p.raw_text(
            "Walkthrough panels will open in a popup window."
            if enabled else
            "Walkthrough panels will be printed to the console instead."))

    async def walkthrough_popup_reply(self, session: Session, popup_id: int,
                                      value: int) -> None:
        c = session.character
        if not c or not self.walkthrough_available:
            return
        chapter = wt.POPUP_CHAPTERS.get(popup_id)
        panel = chapter.panel_for(c) if chapter else None
        # Only answer the popup the player is actually looking at.
        if not panel or panel.popup_id != popup_id:
            return
        if value == wt.OPTION_ACCEPT:
            await self.advance_walkthrough(session)
            return
        first = panel.stage == chapter.first_stage
        c.quest_state[chapter.skipped if first else chapter.stopped] = panel.stage
        self.db.save(c)
        await session.send(p.remove_map_marker(wt.MARKER_ID))
        await self.send_walkthrough_text(
            session, *(chapter.declined if first else chapter.stopped_text))

    async def reward_walkthrough_panel(self, session: Session,
                                       panel: wt.Panel) -> None:
        c = session.character
        level_ups = award_experience(c, panel.experience)
        if panel.experience:
            await self.send_stats(session, force=True)
        if level_ups:
            await self.announce_levels(session, level_ups)

    async def advance_walkthrough(self, session: Session) -> None:
        """Move to the next panel, or finish the walkthrough."""
        c = session.character
        if not c:
            return
        chapter = self.walkthrough_chapter(c)
        if not chapter:
            return
        # A panel's kit is handed over as the player leaves it, so the next
        # panel can say Ilyon gave it to them and be telling the truth.
        finished = chapter.panel_for(c)
        if finished and finished.grants:
            stored = []
            for name, quantity in finished.grants:
                # An overloaded pack must not swallow the kit silently; the
                # next panel expects the player to be holding it.
                if not self.add_inventory(c, name, quantity,
                                          source="walkthrough"):
                    c.storage[name] = c.storage.get(name, 0) + quantity
                    stored.append(f"{quantity} {name}")
            await session.send(p.inventory_packet(
                c.inventory, ITEMS, c.equipment, self.sync_inventory_slots(c)))
            if stored:
                await session.send(p.raw_text(
                    "You could not carry " + ", ".join(stored)
                    + "; it went to storage instead."))
        stage = chapter.stage_of(c) + 1
        if stage in chapter.panels:
            await self.start_walkthrough(session, chapter, stage)
            return
        c.quest_state[chapter.state] = wt.DONE
        c.achievements.add(chapter.achievement)
        self.db.save(c)
        await self.award_achievements(session)
        await session.send(p.remove_map_marker(wt.MARKER_ID))
        await self.send_walkthrough_text(session, *chapter.finale)

    async def walkthrough_event(self, session: Session, event: str,
                                detail: str = "", amount: int = 1) -> None:
        """Report a gameplay event; complete the showing panel if it matches."""
        await lantern.event(self, session, event, detail, amount)
        await bell.event(self, session, event, detail, amount)
        roads.emit(self, session, event, detail, amount)
        await sky.event(self, session, event, detail, amount)
        await landing_runtime.event(self, session, event, detail, amount)
        await watchpost.event(self, session, event, detail, amount)
        c = session.character
        chapter = self.walkthrough_chapter(c) if c else None
        if not chapter or not chapter.is_active(c):
            return
        panel = chapter.panel_for(c)
        if not panel or not chapter.matches(panel, event, detail):
            return
        if not wt.record(c, panel, amount, key=chapter.progress_key(panel.stage)):
            self.db.save(c)
            await self.sync_walkthrough_marker(session)
            return
        await self.reward_walkthrough_panel(session, panel)
        await self.advance_walkthrough(session)

    async def sync_tutorial_markers(self, session: Session) -> None:
        c = session.character
        for marker_id in range(500, 507):
            await session.send(p.remove_map_marker(marker_id))
        stage = int(c.quest_state.get("beginner_tutorial", 0))
        # The tutorial runs on the home map, and these named `startmap.elm`
        # instead - an Eternal Lands map file this profile has never served,
        # which only ever resolved because the client aliased that name.
        home = self.maps.get(wt.HOME_MAP)
        marker_map = home.client_name if home else wt.HOME_MAP
        if stage == 1:
            for offset, (x, y) in enumerate(TUTORIAL_ROUTE_MARKERS):
                await self.send_map_marker(session, 500 + offset, x, y, marker_map, f"To {TUTORIAL_ROUTE_NPC}")
        elif stage == 3 and c.quest_state.get("harvest_tutorial_started"):
            index = int(c.quest_state.get("tutorial_flower_index", 0))
            if index >= len(TUTORIAL_HARVESTS):
                return
            name, x, y, _ = TUTORIAL_HARVESTS[index]
            await self.send_map_marker(session, 506, x, y, marker_map, name)

    async def tutorial_page(self, session: Session, actor_id: int, response_id: int) -> None:
        scouting = [
            "Before I go on, I will explain a few useful things. Press Tab or the Map icon to view the map. The blue X is your location; click the map to walk there.",
            "Your destination is marked by a red X. Circles mark the trades: green for general stores, purple for smiths, pink for growers, and yellow for the arcane.",
            "The compass shows the camera direction and, when clicked, your x and y coordinates. Write down useful entrances and resources.",
            "Now test what you learned. Walk south to the ferry landing. I have placed blue markers along the way.",
            "Talk to Ferryman Caldus there, then return to me. You can review this objective in your Quest Log."]
        harvesting = [
            "Harvesting gathers resources for money and item making. It is useful no matter which skills you choose.",
            "Resources are Vegetal or Mineral. Vegetal includes plants, flowers, fruits and vegetables; mineral includes sulfur, coal, quartz, metals and gemstones.",
            "Eight resources grow and lie within the walls. Follow one blue marker at a time and gather one of each, in order.",
            "First withdraw your Pickaxe from Cache Keeper Dellin. After gathering, deposit the eight resources with him. Stored goods can be drawn from any keeper.",
            "Once they are stored, return to me. The objective is also saved in your quest log.",
            "The easy ones are slow at low level. Select walk, move over the resource until the cursor becomes a pickaxe, and click once."]
        pages, first, finish = (scouting, 1110, 1114) if 1110 <= response_id <= 1114 else (harvesting, 1210, 1215)
        index = response_id - first
        # Bound here, not in the branch below. Announcing the dialogue reads
        # the character, so every page of both lessons raised UnboundLocalError
        # before reaching its own text.
        c = session.character
        await self.announce_quest_dialogue(session,
                                           self.active_quest_id(c))
        await session.send(p.npc_text(pages[index]))
        if response_id < finish:
            await session.send(p.npc_options(actor_id, [(response_id + 1, "More")]))
        else:
            if first == 1110:
                c.quest_state["beginner_tutorial"] = 1
            else:
                self.prepare_tutorial_stage(c, 3)
                c.quest_state["harvest_tutorial_started"] = True
                c.quest_state.setdefault("tutorial_flower_index", 0)
                c.quest_state.setdefault("tutorial_flower_count", 0)
            self.db.save(c)
            await self.sync_tutorial_markers(session)
            await session.send(p.npc_options(actor_id, [(900, "Close")]))

    def shop_for_actor(self, actor_id: int) -> ShopDefinition | None:
        record = self.npcs.get(actor_id)
        return self.shops.get(record[0].name.casefold()) if record else None

    async def show_shop_main(self, session: Session, actor_id: int,
                             text: str | None = None) -> None:
        shop = self.shop_for_actor(actor_id)
        if not shop:
            return
        session.pending_shop = None
        c = session.character
        gold = c.inventory.get("Gold Coins", 0) if c else 0
        load = self.carried_load(c) if c else 0
        capacity = carry_capacity(c) if c else 0
        if c and "merchant_window_v1" in session.client_capabilities:
            session.pending_shop = (actor_id, "ui", -1)
            entries = [(index, entry, c.inventory.get(entry.name, 0))
                       for index, entry in enumerate(shop.items)]
            await session.send(p.merchant_state(
                actor_id, shop.npc_name, gold, load, capacity, entries, ITEMS,
                include_weights="merchant_weights_v1" in session.client_capabilities))
            if text:
                await session.send(p.raw_text(text))
            return
        heading = text or shop.greeting
        await session.send(p.npc_text(
            f"{heading}\\n\\nGold: {gold:,}   Carry: {load}/{capacity} EMU"))
        await session.send(p.npc_options(actor_id, [
            (SHOP_BUY, "Browse goods"),
            (SHOP_SELL, "Sell from inventory")]
            + self.conversation_options(session, shop.npc_name) + [(900, "Close shop")]))

    async def answer_shop_response(self, session: Session, actor_id: int,
                                   response_id: int, shop) -> bool:
        """Handle one shop-window response id. False means it was not one.

        Shared between the shop role and any NPC that keeps a side business
        (the sigil keepers sell reagents as well as sigils), so the whole
        buy/sell/quantity flow behaves identically at either counter.
        """
        if response_id == SHOP_BUY:
            await self.show_shop_items(session, actor_id, "buy")
        elif response_id == SHOP_SELL:
            await self.show_shop_items(session, actor_id, "sell")
        elif SHOP_BUY_ITEM <= response_id < SHOP_BUY_ITEM + len(shop.items):
            await self.show_shop_quantities(
                session, actor_id, "buy", response_id - SHOP_BUY_ITEM)
        elif SHOP_SELL_ITEM <= response_id < SHOP_SELL_ITEM + len(shop.items):
            await self.show_shop_quantities(
                session, actor_id, "sell", response_id - SHOP_SELL_ITEM)
        elif SHOP_QUANTITY <= response_id < SHOP_QUANTITY + len(SHOP_QUANTITIES):
            await self.complete_shop_trade(
                session, actor_id, SHOP_QUANTITIES[response_id - SHOP_QUANTITY])
        elif response_id == SHOP_MAX:
            await self.complete_shop_trade(session, actor_id, None)
        elif response_id == SHOP_CANCEL:
            await self.show_shop_main(session, actor_id)
        elif response_id == 900:
            session.pending_shop = None
            await session.send(p.packet(p.CLOSE_NPC_MENU))
        else:
            return False
        return True

    async def modern_shop_trade(self, session: Session, actor_id: int,
                                mode: str, item_index: int,
                                requested: int | None) -> None:
        """Validate and execute one action from the dedicated merchant window."""
        pending, shop = session.pending_shop, self.shop_for_actor(actor_id)
        if (not shop or not pending or pending[0] != actor_id or
                mode not in {"buy", "sell"} or
                not 0 <= item_index < len(shop.items)):
            raise ValueError("That merchant is no longer available. Open the shop again.")
        if requested is not None and not 1 <= requested <= 1_000_000:
            raise ValueError("Quantity must be between 1 and 1,000,000.")
        session.pending_shop = (actor_id, mode, item_index)
        await self.complete_shop_trade(session, actor_id, requested)

    async def show_shop_items(self, session: Session, actor_id: int, mode: str) -> None:
        c, shop = session.character, self.shop_for_actor(actor_id)
        if not c or not shop:
            return
        buying = mode == "buy"
        entries = [(index, item) for index, item in enumerate(shop.items)
                   if buying or c.inventory.get(item.name, 0) > 0]
        if not entries:
            await self.show_shop_main(session, actor_id, "You do not have any items I buy.")
            return
        base = SHOP_BUY_ITEM if buying else SHOP_SELL_ITEM
        verb = "buy" if buying else "sell"
        gold = c.inventory.get("Gold Coins", 0)
        await session.send(p.npc_text(
            f"{shop.npc_name} — {verb.title()}\n"
            f"Gold: {gold:,}   Select an item to see quantities and totals."))
        labels = []
        for index, item in entries:
            price = item.buy_price if buying else item.sell_price
            context = (f"afford {gold // max(1, price):,}"
                       if buying else f"owned {c.inventory.get(item.name, 0):,}")
            labels.append((base + index,
                           f"{item.name}  —  {price:,} gc  ({context})"))
        await session.send(p.npc_options(
            actor_id, labels + [(SHOP_CANCEL, "Back to shop")]))

    async def show_shop_quantities(self, session: Session, actor_id: int,
                                   mode: str, item_index: int) -> None:
        shop = self.shop_for_actor(actor_id)
        if not shop or not 0 <= item_index < len(shop.items):
            return
        entry = shop.items[item_index]
        price = entry.buy_price if mode == "buy" else entry.sell_price
        session.pending_shop = (actor_id, mode, item_index)
        if "merchant_window_v1" in session.client_capabilities:
            # A dedicated merchant window picks the item and the quantity in one
            # gesture and sends both response ids together, so there is no menu
            # to draw. Remember the selection and let the second response finish
            # the trade; drawing the legacy dialogue here would cover the very
            # window the player is trading in.
            return
        action = "buy" if mode == "buy" else "sell"
        available = (session.character.inventory.get("Gold Coins", 0) // max(1, price)
                     if mode == "buy"
                     else session.character.inventory.get(entry.name, 0))
        await session.send(p.npc_text(
            f"{entry.name}\nUnit price: {price:,} Gold Coins\n"
            f"Available to {action}: {available:,}\n"
            "Choose a quantity; the total is shown before the action."))
        options = [(SHOP_QUANTITY + index,
                    f"{quantity:,}  —  {price * quantity:,} gc")
                   for index, quantity in enumerate(SHOP_QUANTITIES)
                   if quantity <= available]
        if available > 0:
            options.append((SHOP_MAX, f"Maximum ({available:,})"))
        options.append((SHOP_CANCEL, "Back to shop"))
        await session.send(p.npc_options(actor_id, options))

    async def refuse_shop_trade(self, session: Session, actor_id: int, mode: str,
                                item_index: int, message: str) -> None:
        """Report a refused shop trade in whichever window the player is using."""
        if "merchant_window_v1" in session.client_capabilities:
            await self.show_shop_main(session, actor_id, message)
            return
        await session.send(p.npc_text(message))
        await self.show_shop_quantities(session, actor_id, mode, item_index)

    def shop_purchase_fits(self, c: Character, entry: ShopItem, quantity: int) -> bool:
        if quantity <= 0 or c.inventory.get("Gold Coins", 0) < entry.buy_price * quantity:
            return False
        inventory = dict(c.inventory)
        inventory["Gold Coins"] -= entry.buy_price * quantity
        if inventory["Gold Coins"] == 0:
            del inventory["Gold Coins"]
        inventory[entry.name] = inventory.get(entry.name, 0) + quantity
        equipment_weight = sum(ITEMS[name].emu for name in c.equipment.values() if name in ITEMS)
        return (len(inventory) <= 36 and
                sum(ITEMS[name].emu * amount for name, amount in inventory.items())
                + equipment_weight <= carry_capacity(c))

    async def complete_shop_trade(self, session: Session, actor_id: int,
                                  requested: int | None) -> None:
        c, pending = session.character, session.pending_shop
        shop = self.shop_for_actor(actor_id)
        if not c or not shop or not pending or pending[0] != actor_id:
            return
        _, mode, item_index = pending
        if not 0 <= item_index < len(shop.items):
            return
        entry = shop.items[item_index]
        if mode == "buy":
            maximum = c.inventory.get("Gold Coins", 0) // max(1, entry.buy_price)
            if ITEMS[entry.name].emu:
                free_emu = max(0, carry_capacity(c) - self.carried_load(c))
                maximum = min(maximum, free_emu // ITEMS[entry.name].emu)
            if maximum and not self.shop_purchase_fits(c, entry, maximum):
                # Usually only the inventory-slot limit can reject this candidate.
                # Binary search avoids iterating through a large gold balance.
                low, high = 0, maximum
                while low < high:
                    middle = (low + high + 1) // 2
                    if self.shop_purchase_fits(c, entry, middle):
                        low = middle
                    else:
                        high = middle - 1
                maximum = low
            quantity = maximum if requested is None else requested
            if quantity > maximum or not self.shop_purchase_fits(c, entry, quantity):
                await self.refuse_shop_trade(
                    session, actor_id, mode, item_index,
                    "You do not have enough gold or free EMU to buy that many. "
                    f"You can buy at most {maximum}.")
                return
            cost = entry.buy_price * quantity
            c.inventory["Gold Coins"] -= cost
            if not c.inventory["Gold Coins"]:
                del c.inventory["Gold Coins"]
            c.inventory[entry.name] = c.inventory.get(entry.name, 0) + quantity
            if tracks_instances(entry.name):
                for _ in range(quantity):
                    self.db.item_instances.create(
                        entry.name, 1, "inventory", c.username,
                        durability=100, max_durability=100,
                        source=f"npc_shop:{shop.npc_name}",
                        actor=c.username)
            message = f"You bought {quantity} {entry.name} for {cost} gold coins."
        else:
            maximum = c.inventory.get(entry.name, 0)
            quantity = maximum if requested is None else requested
            if quantity <= 0 or quantity > maximum:
                await self.refuse_shop_trade(
                    session, actor_id, mode, item_index,
                    f"You can sell at most {maximum}.")
                return
            proceeds = entry.sell_price * quantity
            inventory = dict(c.inventory)
            inventory[entry.name] -= quantity
            if not inventory[entry.name]:
                del inventory[entry.name]
            inventory["Gold Coins"] = inventory.get("Gold Coins", 0) + proceeds
            if len(inventory) > 36:
                await self.refuse_shop_trade(
                    session, actor_id, mode, item_index,
                    "You need a free inventory slot for the gold coins, or must "
                    "sell the whole stack.")
                return
            c.inventory = inventory
            message = f"You sold {quantity} {entry.name} for {proceeds} gold coins."
        if modern := getattr(self, "modern", None):
            if mode == "buy":
                modern.record_economy(
                    "npc_shop_buy", c.username, counterparty=shop.npc_name,
                    item_name=entry.name, quantity=quantity, gold=cost,
                    gold_flow="sink", item_flow="source",
                    metadata={"actor_id": actor_id,
                              "unit_price": entry.buy_price})
            else:
                modern.record_economy(
                    "npc_shop_sell", c.username, counterparty=shop.npc_name,
                    item_name=entry.name, quantity=quantity, gold=proceeds,
                    gold_flow="source", item_flow="sink",
                    metadata={"actor_id": actor_id,
                              "unit_price": entry.sell_price})
        session.pending_shop = None
        session.inventory_slots = self.sync_inventory_slots(c)
        self.db.save(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await session.send(stats_packet(c))
        await self.show_shop_main(session, actor_id, message)
        roads.emit(self,session,"purchase" if mode=="buy" else "sale",entry.name,quantity)
        await landing_runtime.event(self, session, "purchase" if mode == "buy" else "sale",
                                    entry.name, quantity, npc=shop.npc_name)
        if shop.npc_name == "Stillglass fittings" and mode == "buy":
            await sky.event(self, session, "purchase", entry.name, quantity)
        if shop.npc_name == lantern.GALLEY:
            await lantern.event(self, session, mode, entry.name, quantity)
        # The client's [repeat] control resends the last response ID. Preserve
        # the completed trade so repeating a quantity replays the same item,
        # mode, and amount without walking through the shop menus again.
        session.pending_shop = (actor_id, mode, item_index)

    async def show_wraith_main(self, session: Session, actor_id: int,
                               text: str | None = None) -> None:
        c = session.character
        if not c:
            return
        session.pending_wraith = None
        await session.send(p.npc_text(
            text or f"Hello, {c.name}. What brings you here? You have "
                    f"{available_pickpoints(c)} pick points available."))
        await session.send(p.npc_options(actor_id, [
            (WRAITH_MAIN_PERKS, "Get a perk"),
            (WRAITH_MAIN_ATTRIBUTES, "Get attribute[s]"),
            (WRAITH_MAIN_NEXUS, "Get nexuses"),
            (900, "Nothing, just passing by.")]))

    async def show_wraith_perks(self, session: Session, actor_id: int,
                                page: int = 0) -> None:
        c = session.character
        if not c:
            return
        start = page * WRAITH_PERKS_PER_PAGE
        listed = WRAITH_PERKS[start:start + WRAITH_PERKS_PER_PAGE]
        options = [(WRAITH_PERK_BASE + start + offset, perk.name)
                   for offset, perk in enumerate(listed)]
        if start + len(listed) < len(WRAITH_PERKS):
            options.append((WRAITH_PERK_BASE + len(WRAITH_PERKS) + page + 1, "More"))
        if page:
            options.append((WRAITH_PERK_BASE + len(WRAITH_PERKS) + page - 1, "Back"))
        else:
            options.append((WRAITH_CONFIRM_NO, "Back"))
        await session.send(p.npc_text(
            f"What perk would you like to get? You have {available_pickpoints(c)} pick points available."))
        await session.send(p.npc_options(actor_id, options))

    async def show_wraith_choices(self, session: Session, actor_id: int,
                                  kind: str) -> None:
        c = session.character
        if not c:
            return
        names = ATTRIBUTES if kind == "attribute" else NEXUS
        base = WRAITH_ATTRIBUTE_BASE if kind == "attribute" else WRAITH_NEXUS_BASE
        label = "attribute" if kind == "attribute" else "nexus"
        options = [(base + index, name.title() + (" Nexus" if kind == "nexus" else ""))
                   for index, name in enumerate(names)]
        options.append((WRAITH_MAIN_ATTRIBUTES if kind == "attribute"
                        else WRAITH_MAIN_NEXUS, "Back"))
        await session.send(p.npc_text(
            f"Which {label} would you like to increase? Each {label} costs 1 pick point. "
            f"You have {available_pickpoints(c)} pick points."))
        await session.send(p.npc_options(actor_id, options))

    async def confirm_wraith_choice(self, session: Session, actor_id: int,
                                    kind: str, value: str) -> None:
        c = session.character
        if not c:
            return
        session.pending_wraith = (kind, value)
        if kind == "perk":
            perk = next(perk for perk in WRAITH_PERKS if perk.name == value)
            # Price the step this character would buy, not the perk's first
            # tier: the second tier of a perk asks for more gold than the
            # first, and a confirmation that quoted the wrong sum would be
            # agreed to and then refused.
            tier = next_tier(c, perk) or perk.max_tier
            step = perk.tier(tier)
            pp = (f"costs {step.pickpoints} pick points" if step.pickpoints > 0
                  else f"gives {-step.pickpoints} pick points" if step.pickpoints < 0
                  else "costs no pick points")
            gold = f" and {step.gold:,} gold coins" if step.gold else ""
            what = (f"Tier {tier} of {perk.name}" if perk.max_tier > 1
                    else perk.name)
            text = f"{what} {pp}{gold}. {step.description} Are you sure?"
        else:
            text = f"Increase {value.title()} by one for 1 pick point? Are you sure?"
        await session.send(p.npc_text(text))
        await session.send(p.npc_options(actor_id, [
            (WRAITH_CONFIRM_YES, "Yes"), (WRAITH_CONFIRM_NO, "No")]))

    async def buy_with_pickpoints(self, session: Session, kind: str, value: str,
                                  counterparty: str) -> tuple[bool, str]:
        """Spend pick points and tell the client everything that moved.

        The one path a purchase takes, whichever way it was asked for: the
        wraith's dialogue and the statistics window both arrive here, so a
        raised Physique refreshes the point pools, re-broadcasts the health
        cap, and lands in the economy log the same way from either.
        """
        c = session.character
        if not c:
            return False, "You are not in the world."
        before_inventory = dict(c.inventory)
        old_health, old_max_health = c.health, c.max_health
        before_attributes = dict(c.attributes)
        bought, message = spend_pickpoint(c, kind, value)
        if not bought:
            return False, message
        if kind in ("attribute", "batch"):
            refresh_derived_points(c)
        session.inventory_slots = self.sync_inventory_slots(c)
        self.record_inventory_economy_delta(
            c, before_inventory, "pickpoint_purchase",
            counterparty=counterparty, metadata={"kind": kind, "value": value})
        self.db.save(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment,
                                              c.inventory_slots))
        await session.send(stats_packet(c))
        if kind == "perk":
            await self.send_perks(session)
        await self.send_perk_catalog(session)
        await self.send_attribute_state(session)
        if c.max_health != old_max_health:
            await self.broadcast_map(
                c.map_id, p.actor_max_health(c.actor_id, c.max_health))
        if c.health > old_health:
            await self.broadcast_map(
                c.map_id, p.actor_heal(c.actor_id, c.health - old_health))
        attribute_points = sum(c.attributes[key] - old
                               for key, old in before_attributes.items())
        if attribute_points > 0:
            await lantern.event(self, session, "attribute", value, attribute_points)
            await landing_runtime.event(self, session, "attribute", value, attribute_points)
        return True, message

    async def complete_wraith_choice(self, session: Session, actor_id: int) -> None:
        c, pending = session.character, session.pending_wraith
        if not c or not pending:
            return
        kind, value = pending
        bought, message = await self.buy_with_pickpoints(
            session, kind, value, "Wraith")
        if not bought:
            session.pending_wraith = None
            await self.show_wraith_main(session, actor_id, message)
            return
        await self.show_wraith_main(session, actor_id, message)
        # Attributes and nexuses may be bought repeatedly. Keeping the
        # successful choice lets the client's [repeat] control resend Yes.
        if kind in ("attribute", "nexus"):
            session.pending_wraith = (kind, value)

    async def show_novac_main(self, session: Session, actor_id: int,
                              message: str = "") -> None:
        c = session.character
        if not c:
            return
        intro = (
            "A hunter sits over a tally of pelts and claws, one column to a "
            "region. She looks up as you approach. I keep count of what walks "
            "where. Hunt what I name, in the order I name it, and you will "
            "learn more about fighting than I could tell you."
        )
        lines = [message] if message else [intro]
        options = [(5000, "Who are you?"), (5001, "What are you counting?")]
        if not novac_started(c, THE_LONG_HUNT):
            options.append((5010, THE_LONG_HUNT.title))
        for response, quest in ((5100, THE_LONG_HUNT),):
            current = novac_objective(c, quest)
            if current and novac_pending(c, quest):
                options.append((response, f"I killed the {current.name}."))
        if any(novac_objective(c, quest) for quest in NOVAC_QUESTS.values()):
            options.append((5190, "What must I kill?"))
        options.append((900, "Goodbye"))
        await session.send(p.npc_text("\n".join(line for line in lines if line)))
        await session.send(p.npc_options(actor_id, options))

    async def claim_novac_objective(self, session: Session, actor_id: int,
                                    quest_key: str) -> None:
        c = session.character
        if not c:
            return
        quest = NOVAC_QUESTS[quest_key]
        try:
            objective, finished = advance_novac(c, quest)
        except ValueError as exc:
            await self.show_novac_main(session, actor_id, str(exc))
            return
        attack_xp = objective.attack_xp
        defense_xp = objective.defense_xp
        if finished:
            attack_xp += quest.final_attack_xp
            defense_xp += quest.final_defense_xp
        levels = award_combat_xp(c, attack_xp, defense_xp)
        if quest is THE_LONG_HUNT and int(c.quest_state.get("novac_kta_step", 0)) >= 2:
            c.quest_state["novac_two_objectives"] = True
        if finished and quest is THE_LONG_HUNT:
            c.perks.add("Vanquisher")
            await self.send_perks(session)
        if not finished:
            self.assign_novac_target(c, quest)
        self.db.save(c)
        if attack_xp or defense_xp:
            await self.send_combat_xp(session, attack=True, defense=True)
            await self.announce_levels(session, levels)
        if finished:
            message = (
                f"{quest.title} is complete. You receive {attack_xp} Attack and "
                f"{defense_xp} Defense experience."
            )
            if quest is THE_LONG_HUNT:
                message += " You have also earned the Vanquisher perk: +1 Attack and +1 Defense in combat."
        else:
            following = novac_objective(c, quest)
            message = (
                f"Well done. You receive {attack_xp} Attack and {defense_xp} Defense "
                f"experience. Your next target is {following.name}"
                f"{f' in {following.location}' if following.location else ''}."
            )
        await self.show_novac_main(session, actor_id, message)

    async def respond_to_novac(self, session: Session, actor_id: int,
                               response_id: int) -> None:
        c = session.character
        if not c:
            return
        if response_id == 5000:
            await self.show_novac_main(
                session, actor_id,
                "Tallykeeper Ysolde. Every region sends me its count - what was "
                "taken, and what was seen and left alone. A tally nobody walks "
                "out to check is a rumour with columns.")
            return
        if response_id == 5001:
            await self.show_novac_main(
                session, actor_id,
                "Three quarries, on three maps, each harder than the one "
                "before. You bring me the count and I will tell you where to "
                "go next. What you learn on the road is the payment.")
            return
        starts = {5010: THE_LONG_HUNT}
        if response_id in starts:
            quest = starts[response_id]
            if not novac_started(c, quest):
                start_novac(c, quest)
                self.assign_novac_target(c, quest)
                self.db.save(c)
            else:
                self.assign_novac_target(c, quest)
            current = novac_objective(c, quest)
            await self.show_novac_main(
                session, actor_id,
                f"{quest.title} has begun. Kill a {current.name}"
                f"{f' in {current.location}' if current.location else ''}, then return to me.")
            return
        reports = {5100: "kta", 5101: "reloaded", 5102: "potion"}
        if response_id in reports:
            await self.claim_novac_objective(session, actor_id, reports[response_id])
            return
        if response_id == 5190:
            assignments = [
                f"{quest.title}: {current.name}"
                f"{f' in {current.location}' if current.location else ''}"
                for quest in NOVAC_QUESTS.values()
                if (current := novac_objective(c, quest))
            ]
            await self.show_novac_main(
                session, actor_id,
                "Your current assignment" + ("s are:\n" if len(assignments) != 1 else " is:\n")
                + "\n".join(assignments))
            return
        if response_id == 900:
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            return
        await self.show_novac_main(session, actor_id)

    async def open_summon_behavior(self, session: Session) -> None:
        """Ask the player how their summons should choose targets.

        Reached by clicking one of your own summons and by the command the
        client's hotkey sends. The command route matters: the behavior is a
        standing preference on the character, so it has to be settable before
        anything has been summoned, when there is nothing on the field to
        click.
        """
        c = session.character
        if not c:
            return
        if c.skills["summoning"] < 30:
            await session.send(p.raw_text(
                "You need summoning level 30 to set summon behavior."))
            return
        await session.send(p.summon_behavior_popup(SUMMON_BEHAVIOR_OPTIONS))

    async def set_summon_behavior(self, session: Session, value: int) -> None:
        character = session.character
        label = SUMMON_BEHAVIOR_LABELS.get(value)
        if not character or label is None or character.skills["summoning"] < 30:
            return
        character.quest_state["summon_behavior"] = value
        roads.emit(self,session,"behavior",str(value))
        self.db.save(character)
        await session.send(p.raw_text(f"Summon behavior set to: {label}."))

    def daily_npc_names(self) -> set[str]:
        return {record[0].name for record in self.npcs.values()}

    async def show_daily_quest_npc(
            self, session: Session, actor_id: int, npc_name: str) -> bool:
        c = session.character
        if not c:
            return False
        starter = next((key for key, name in DAILY_START_NPCS.items()
                        if name.casefold() == npc_name.casefold()), None)
        task = current_daily_task(c)
        if not starter and (not task or task.client.casefold() != npc_name.casefold()):
            return False
        await session.send(p.npc_info(npc_name, 0))
        # Everything this NPC says is about the daily assignment, which is a
        # quest, so it is flagged as one rather than left indistinguishable
        # from small talk.
        await self.announce_quest_dialogue(session, QUEST_DAILY)
        if task:
            progress = int(c.quest_state.get("daily_progress", 0))
            options = []
            if can_complete_daily(c, npc_name):
                options.append((8001, "I completed the assignment."))
            if starter and starter == active_daily_key(c):
                options.append((8002, "Cancel this assignment."))
            options.append((900, "Goodbye"))
            objective = daily_task_text(task, progress)
            await session.send(p.npc_text(objective))
            await session.send(p.raw_text(f"Daily quest: {objective}"))
            await session.send(p.npc_options(actor_id, options))
        elif starter:
            await session.send(p.npc_text(
                "I can give you one of the daily assignments available in Eternal Lands. "
                "Only one daily quest can be active at a time."))
            await session.send(p.npc_options(
                actor_id, [(8000, "Give me a daily assignment."), (900, "Not today")]))
        return True

    async def respond_to_daily_quest_npc(
            self, session: Session, actor_id: int, npc_name: str,
            response_id: int) -> bool:
        c = session.character
        if not c:
            return False
        starter = next((key for key, name in DAILY_START_NPCS.items()
                        if name.casefold() == npc_name.casefold()), None)
        task = current_daily_task(c)
        if not starter and (not task or task.client.casefold() != npc_name.casefold()):
            return False
        if response_id == 900:
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            return True
        try:
            if response_id == 8000 and starter:
                task = assign_daily(c, starter, self.daily_npc_names(), self.maps)
                self.db.save(c)
                objective = daily_task_text(task)
                await session.send(p.npc_text(objective))
                await session.send(p.raw_text(f"New daily quest: {objective}"))
            elif response_id == 8001 and can_complete_daily(c, npc_name):
                before_inventory = dict(c.inventory)
                before_levels = dict(c.skills)
                task, xp, gold, _ = reward_daily(c)
                self.record_inventory_economy_delta(
                    c, before_inventory, "daily_quest_reward",
                    counterparty=npc_name,
                    metadata={"task_kind": task.kind,
                              "task_target": task.target})
                # The reward levels as it pays (overall included), so the
                # announcement is read off the before/after levels.
                level_ups = [(skill, before_levels[skill], level)
                             for skill, level in c.skills.items()
                             if level != before_levels.get(skill, level)]
                session.inventory_slots = self.sync_inventory_slots(c)
                self.db.save(c)
                await session.send(p.inventory_packet(
                    c.inventory, ITEMS, c.equipment, session.inventory_slots))
                await self.send_stats(session, force=True)
                if level_ups:
                    await self.announce_levels(session, level_ups)
                rewards = ", ".join(f"{amount} {skill} XP" for skill, amount in xp.items())
                if gold:
                    rewards += (", " if rewards else "") + f"{gold} gold coins"
                await session.send(p.npc_text(
                    f"Assignment complete. You received {rewards or 'your reward'}."))
            elif response_id == 8002 and starter and starter == active_daily_key(c):
                key = cancel_daily(c)
                self.db.save(c)
                wait = CANCEL_WAIT_HOURS
                await session.send(p.npc_text(
                    f"Assignment cancelled. You may request another in {wait} hours."))
            else:
                await self.show_daily_quest_npc(session, actor_id, npc_name)
                return True
        except ValueError as exc:
            message = str(exc)
            await session.send(p.npc_text(message))
            await session.send(p.raw_text(f"Daily quest: {message}"))
        await session.send(p.npc_options(actor_id, [(900, "Goodbye")]))
        return True

    async def show_god_priest(self, session: Session, actor_id: int, god) -> None:
        c = session.character
        if not c:
            return
        await session.send(p.npc_info(god.priest, 0))
        if not worships(c, god):
            conflicts = ", ".join(g.title() for g in sorted(god.enemies))
            await session.send(p.npc_text(
                f"I serve {god.name}, patron of {god.skill}. Worship begins at rank -2 "
                f"(-8% {god.skill} experience) and rises by 4% per offering to +20%. "
                f"{god.name} is opposed to {conflicts}."))
            await session.send(p.npc_options(actor_id, [(9100, f"Worship {god.name}"), (900, "Goodbye")]))
            return
        current = god_rank(c, god)
        options = [(9103, f"Renounce {god.name}")]
        offering = next_offering(c, god)
        if offering:
            options.insert(0, (9101, f"Offer {offering_text(offering)}"))
        if current >= god.blessing_rank:
            options.insert(0, (9102, f"Buy +{god.blessing_levels} {god.skill} blessing ({god.blessing_cost} gc)"))
        detail = (f"You are rank {current}: {current * 4:+d}% {god.skill} experience."
                  if current < 5 else f"You are rank 5: +20% {god.skill} experience, the maximum.")
        await session.send(p.npc_text(detail))
        await session.send(p.npc_options(actor_id, options + [(900, "Goodbye")]))

    async def respond_to_god_priest(self, session: Session, actor_id: int, god, response_id: int) -> None:
        c = session.character
        if not c:
            return
        before_inventory = dict(c.inventory)
        try:
            if response_id == 9100:
                join_god(c, god)
                message = f"You now worship {god.name} at rank -2 (-8% {god.skill} experience)."
            elif response_id == 9101:
                new_rank = advance_god(c, god)
                message = f"{god.name} raises you to rank {new_rank}: {new_rank * 4:+d}% {god.skill} experience."
                session.inventory_slots = self.sync_inventory_slots(c)
                await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, session.inventory_slots))
            elif response_id == 9102:
                levels = buy_blessing(c, god)
                message = f"{god.name} blesses you with +{levels} temporary {god.skill} levels."
                session.inventory_slots = self.sync_inventory_slots(c)
                await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, session.inventory_slots))
                await self.send_stats(session, force=True)
            elif response_id == 9103:
                renounce_god(c, god)
                message = f"You have renounced {god.name}. Rejoining will begin again at rank -2."
            elif response_id == 900:
                await session.send(p.packet(p.CLOSE_NPC_MENU))
                return
            else:
                await self.show_god_priest(session, actor_id, god)
                return
            self.record_inventory_economy_delta(
                c, before_inventory, "god_service",
                counterparty=god.name,
                metadata={"response_id": response_id})
            self.db.save(c)
            await session.send(p.npc_text(message))
        except ValueError as exc:
            await session.send(p.npc_text(str(exc)))
        await self.show_god_priest(session, actor_id, god)

    async def show_auction_main(self, session: Session, actor_id: int,
                                message: str | None = None) -> None:
        if not getattr(self, "auctions", None) or not session.character:
            return
        gold, returns = self.auctions.balances(session.character.username)
        if "market_window_v1" in session.client_capabilities:
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            await session.send(p.marketplace_state(
                0, gold, sum(quantity for _, _, quantity in returns),
                self.auctions.browse(limit=40), ITEMS, time.time()))
            return
        session.auction_listing_ids = []
        session.selected_auction_listing = None
        await session.send(p.npc_text(
            (message + "\n\n" if message else "") +
            f"Welcome to the Nymara Exchange. Escrow holds every listing for "
            f"365 days. You have {gold:,} Gold Coins and "
            f"{sum(quantity for _, _, quantity in returns):,} returned item(s) "
            "waiting in escrow."))
        record = self.npcs.get(actor_id)
        await session.send(p.npc_options(actor_id, [
            (AUCTION_BROWSE, "Browse current listings"),
            (AUCTION_MINE, "My listings"),
            (AUCTION_COLLECT, "Collect proceeds and returns")]
            + (self.conversation_options(session, record[0].name)
               if record else [])
            + [(900, "Close auction house")]))

    async def show_auction_browse(self, session: Session, actor_id: int) -> None:
        listings = self.auctions.browse(limit=AUCTION_PAGE_SIZE)
        if not listings:
            await self.show_auction_main(session, actor_id, "There are no active listings.")
            return
        lines = ["Current listings (use #auction buy ID quantity|all to purchase):"]
        for listing in listings:
            days = max(0, int((listing.expires_at - time.time()) / 86400) + 1)
            lines.append(
                f"#{listing.listing_id} {listing.item_name} x{listing.quantity:,} — "
                f"{listing.unit_price:,} gc each — {listing.seller} — {days}d")
        await session.send(p.npc_text("\n".join(lines)))
        await session.send(p.npc_options(actor_id, [
            (AUCTION_MINE, "My listings"),
            (AUCTION_COLLECT, "Collect"),
            (AUCTION_BROWSE, "Refresh"),
            (900, "Close")]))

    async def show_my_auctions(self, session: Session, actor_id: int) -> None:
        c = session.character
        listings = self.auctions.mine(c.username)[:AUCTION_PAGE_SIZE]
        session.auction_listing_ids = [entry.listing_id for entry in listings]
        if not listings:
            await self.show_auction_main(session, actor_id, "You have no active listings.")
            return
        await session.send(p.npc_text(
            "My listings — select one to renew its full 365-day term or cancel it."))
        options = [
            (AUCTION_LISTING_BASE + index,
             f"#{entry.listing_id} {entry.item_name} x{entry.quantity:,} — "
             f"{entry.unit_price:,} gc")
            for index, entry in enumerate(listings)
        ]
        options.append((AUCTION_BROWSE, "Back to browse"))
        await session.send(p.npc_options(actor_id, options))

    async def show_auction_listing(self, session: Session, actor_id: int,
                                   listing_id: int) -> None:
        listing = next(
            (entry for entry in self.auctions.mine(session.character.username)
             if entry.listing_id == listing_id), None)
        if not listing:
            await self.show_my_auctions(session, actor_id)
            return
        session.selected_auction_listing = listing_id
        days = max(0, int((listing.expires_at - time.time()) / 86400) + 1)
        await session.send(p.npc_text(
            f"Listing #{listing.listing_id}\n{listing.item_name} x{listing.quantity:,}\n"
            f"Price: {listing.unit_price:,} Gold Coins each\n"
            f"Time remaining: {days} day(s)"))
        await session.send(p.npc_options(actor_id, [
            (AUCTION_RENEW, "Renew for 365 days"),
            (AUCTION_CANCEL, "Cancel and return items"),
            (AUCTION_MINE, "Back to my listings"),
            (900, "Close")]))

    async def collect_auction_escrow(self, session: Session, actor_id: int) -> None:
        c = session.character
        gold, returned = self.auctions.collect(
            c, can_receive=self.can_add_inventory)
        session.inventory_slots = normalize_inventory_slots(
            c.inventory, session.inventory_slots)
        await session.send(p.inventory_packet(
            c.inventory, ITEMS, c.equipment, session.inventory_slots))
        details = ", ".join(
            f"{quantity:,} {name}" for name, quantity in returned) or "no items"
        await self.show_auction_main(
            session, actor_id,
            f"Collected {gold:,} Gold Coins and {details}.")

    NYMARA_ROAD = (
        ("Eryn Amber", "Amberwood", "Ask Eryn Amber about the western road."),
        ("Mora Fen", "Grey Moors", "Carry Eryn's warning to Mora Fen."),
        ("Captain Iven", "Westhaven", "Report the barrow lights to Captain Iven."),
        ("Tessara", "Verdant Stair", "Ask Tessara how the southern waters are changing."),
        ("Archivist Sesh", "Ssarathi Ruins", "Deliver Tessara's observations to Archivist Sesh."),
    )

    async def show_nymara_road(self, session: Session, actor_id: int, npc_name: str) -> bool:
        c = session.character
        names = [entry[0].casefold() for entry in self.NYMARA_ROAD]
        if not c or npc_name.casefold() not in names:
            return False
        stage = int(c.quest_state.get("nymara_road_stage", -1))
        index = names.index(npc_name.casefold())
        if stage < 0 and index == 0:
            text = ("Amberwood's roots are carrying warnings westward. Follow the road through "
                    "the Grey Moors, Westhaven, Verdant Stair, and the Ssarathi ruins, and ask "
                    "each keeper what has changed.")
            options = [(8800, "I will follow the western road."), (900, "Not yet.")]
        elif stage == index and stage < len(self.NYMARA_ROAD):
            text = self.NYMARA_ROAD[index][2]
            options = [(8800, "Share what you learned."), (900, "I will return.")]
        elif stage >= len(self.NYMARA_ROAD):
            text = "The western road record is complete. Nymara is better prepared because you carried it."
            options = [(900, "Farewell.")]
        else:
            expected = self.NYMARA_ROAD[max(0, min(stage, len(self.NYMARA_ROAD)-1))]
            text = f"Continue the western road. Your next contact is {expected[0]} in {expected[1]}."
            options = [(900, "I understand.")]
        await session.send(p.npc_info(npc_name, 0))
        await session.send(p.npc_text(text))
        await session.send(p.npc_options(actor_id, options))
        return True

    async def advance_nymara_road(self, session: Session, actor_id: int, npc_name: str) -> bool:
        c = session.character
        names = [entry[0].casefold() for entry in self.NYMARA_ROAD]
        if not c or npc_name.casefold() not in names:
            return False
        if c.quest_state.get("nymara_road_complete"):
            await self.show_nymara_road(session, actor_id, npc_name)
            return True
        stage = int(c.quest_state.get("nymara_road_stage", -1))
        index = names.index(npc_name.casefold())
        if response_expected := (stage < 0 and index == 0 or stage == index):
            stage = 1 if stage < 0 else stage + 1
            c.quest_state["nymara_road_stage"] = stage
            if stage >= len(self.NYMARA_ROAD):
                c.quest_state["nymara_road_complete"] = True
                self.add_inventory(c, "Gold Coins", 500, source="quest:nymara_road")
                session.inventory_slots = self.sync_inventory_slots(c)
                await session.send(p.inventory_packet(
                    c.inventory, ITEMS, c.equipment, session.inventory_slots))
                message = "The Western Road is complete. Archivist Sesh awards you 500 Gold Coins."
            else:
                target = self.NYMARA_ROAD[stage]
                message = f"Western Road updated: travel to {target[0]} in {target[1]}."
            self.db.save(c)
            await session.send(quest_progress_popup(message))
        await self.show_nymara_road(session, actor_id, npc_name)
        return True

    # ------------------------------------------------- conversation and quests
    #
    # Every NPC menu the profile builds gets the same two additions: the quest
    # lines this person can move forward, and the things they have to say that
    # are not an errand. Both lists are rebuilt from the character's own state
    # each time rather than remembered on the session, so a response that
    # arrives after the world has moved on is answered against the world as it
    # is now instead of against a stale menu.

    def quest_offers(self, c: Character, npc_name: str) -> list:
        """Lines this NPC can start for this character, in profile order.

        A person standing on more than one map (the landing isle's cast
        before the home migration) offers a line only from the copy in the
        line's own region: the isle's errands are not handed out at Four
        Gates. A line whose giver stands nowhere in its region is offered
        wherever the giver is, as before.
        """
        return [quest for quest in ql.offered_by(self.questlines, npc_name)
                if ql.available(c, quest, self.questlines)
                and (c.map_id == quest.region
                     or not self.stands_on(quest.start, quest.region))]

    def stands_on(self, npc_name: str, map_id: str) -> bool:
        """Whether someone of this name stands on that map."""
        folded = npc_name.casefold()
        return any(row[1] == map_id and row[0].name.casefold() == folded
                   for row in self.npcs.values())

    def quest_business(self, c: Character, npc_name: str) -> list:
        """Lines this NPC can move forward now: (quest, stage or None)."""
        return list(ql.waiting_on(c, self.questlines, npc_name))

    def conversation_options(self, session: Session,
                             npc_name: str) -> list[tuple[int, str]]:
        """The quest and topic options to append to any NPC's own menu.

        Which topics those are depends on what this session has already been
        told: a thread opens as it is walked, so the menu is built from the
        conversation rather than from the file. A topic that names a map is
        raised only on it (eloria/npc_dialogue.py); the player stands on the
        NPC's map whenever a menu is built.
        """
        c = session.character
        options: list[tuple[int, str]] = []
        for index, (quest, stage) in enumerate(self.quest_business(c, npc_name)):
            if len(options) >= QUEST_OPTION_LIMIT:
                break
            if stage is None:
                options.append((QUEST_ADVANCE_BASE + index,
                                f"{quest.title}: it is finished."))
            elif ql.stage_satisfied(c, quest, stage):
                options.append((QUEST_ADVANCE_BASE + index,
                                f"{quest.title}: I have what you asked for."))
            else:
                options.append((QUEST_ABOUT_BASE + index,
                                f"{quest.title}: remind me."))
        for index, quest in enumerate(self.quest_offers(c, npc_name)):
            if len(options) >= QUEST_OPTION_LIMIT:
                break
            options.append((QUEST_OFFER_BASE + index, f"Is there work? ({quest.title})"))
        entry = self.npc_lore.get(npc_name.casefold())
        if entry:
            options.extend(entry.options(session.conversation, c.quest_state,
                                         place=c.map_id))
        return options

    def npc_greeting(self, actor_id: int, npc_name: str) -> str:
        """What an NPC opens with: their written greeting, then the roster's."""
        entry = self.npc_lore.get(npc_name.casefold())
        if entry and entry.greeting:
            return entry.greeting
        return self.npc_dialogues.get(actor_id, f"Hello. I am {npc_name}.")

    async def show_quest_offer(self, session: Session, actor_id: int,
                               quest) -> None:
        c = session.character
        reason = ql.blocked_reason(c, quest, self.questlines)
        if reason:
            await session.send(p.npc_text(reason))
            await session.send(p.npc_options(actor_id, [(900, "Another time.")]))
            return
        await self.announce_quest_dialogue(session, quest.quest_id)
        await session.send(p.npc_text(quest.offer or quest.summary))
        index = self.quest_offers(c, quest.start).index(quest)
        await session.send(p.npc_options(actor_id, [
            (QUEST_ACCEPT_BASE + index, "I will do it."),
            (900, "Not now.")]))

    async def accept_questline(self, session: Session, actor_id: int,
                               quest) -> None:
        c = session.character
        if not ql.available(c, quest, self.questlines):
            await session.send(p.npc_text(
                ql.blocked_reason(c, quest, self.questlines)
                or "You are already carrying that."))
            await session.send(p.npc_options(actor_id, [(900, "Very well.")]))
            return
        stage = ql.begin(c, quest)
        self.db.save(c)
        await self.announce_quest_dialogue(session, quest.quest_id)
        await session.send(p.npc_text(quest.accepted or quest.summary))
        await session.send(quest_progress_popup(
            f"{quest.title} started. {stage.objective}"))
        await session.send(p.npc_options(actor_id, [(900, "I will begin.")]))

    async def remind_questline(self, session: Session, actor_id: int,
                               quest, stage) -> None:
        """What the stage's own NPC says while the work is still outstanding."""
        await self.announce_quest_dialogue(session, quest.quest_id)
        text = stage.prompt or stage.objective
        if stage.counts:
            text += (f"\n\nProgress: {ql.progress(session.character, quest)}"
                     f"/{stage.amount}.")
        await session.send(p.npc_text(text))
        await session.send(p.npc_options(actor_id, [(900, "I will see to it.")]))

    async def advance_questline(self, session: Session, actor_id: int,
                                quest, stage, npc_name: str) -> None:
        c = session.character
        try:
            if stage is None:
                reward = ql.finish(c, quest, npc_name)
                text = quest.complete or "It is done. Thank you."
            else:
                stage, reward, _ = ql.advance(c, quest, npc_name)
                text = stage.done or "Good. That is one thing fewer."
        except ValueError as exc:
            await session.send(p.npc_text(str(exc)))
            await session.send(p.npc_options(actor_id, [(900, "I understand.")]))
            return
        granted = await self.pay_quest_reward(session, reward)
        await self.announce_quest_dialogue(session, quest.quest_id)
        await session.send(p.npc_text(text))
        if stage is None:
            await self.announce_quest_finished(session, quest.quest_id)
            c.achievements.add(quest.title)
            await session.send(quest_progress_popup(
                f"{quest.title} complete. Reward: {granted}."))
            # How many lines are finished, and of what tier, are facts the
            # catalogue reads rather than counts, so this is where they move.
            await self.award_achievements(session)
        else:
            following = ql.current_stage(c, quest)
            await session.send(quest_progress_popup(
                f"{quest.title}: {granted}."
                + (f" Next: {following.objective}" if following else
                   f" Return to {quest.start}.")))
        self.db.save(c)
        await session.send(p.npc_options(actor_id, [(900, "Farewell.")]))

    async def pay_quest_reward(self, session: Session, reward) -> str:
        """Apply one reward and describe what actually landed.

        Items that will not fit are put into storage rather than dropped: a
        quest chain paid over five stages should not punish a player for
        arriving with a full pack at the last one.
        """
        c = session.character
        level_ups = award_experience(
            c, [(skill, amount) for skill, amount in reward.experience
                if skill in c.experience])
        stored: list[str] = []
        if reward.gold:
            self.add_inventory(c, "Gold Coins", reward.gold, source="quest")
        for name, quantity in reward.items:
            if not self.add_inventory(c, name, quantity, source="quest"):
                c.storage[name] = c.storage.get(name, 0) + quantity
                stored.append(name)
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(
            c.inventory, ITEMS, c.equipment, session.inventory_slots))
        await self.send_stats(session, force=True)
        if level_ups:
            await self.announce_levels(session, level_ups)
        described = reward.describe()
        if stored:
            described += f" ({', '.join(sorted(stored))} placed in storage)"
        return described

    async def questline_event(self, session: Session, kind: str, detail: str = "",
                              x: int | None = None, y: int | None = None,
                              amount: int = 1) -> None:
        """Report a gameplay event to every quest line the player is carrying.

        Lines are independent, so one event may advance several at once and a
        line that is not interested is simply not told anything.
        """
        c = session.character
        if not c or not self.questlines:
            return
        position = (c.x if x is None else x, c.y if y is None else y)
        finished = []
        # Progress that does not close a stage used to be silent, so a player
        # killing the fifth of ten wolves had no way to tell the kill had
        # counted - or that it had not, which is the same silence. The count
        # before and after is compared here rather than in `record`, which
        # stays a pure banking function.
        counted: list[tuple] = []
        for quest in self.questlines.values():
            if not ql.is_active(c, quest):
                continue
            stage = ql.current_stage(c, quest)
            if stage is None:
                continue
            before = ql.progress(c, quest)
            if ql.record(c, quest, kind, detail, c.map_id, *position, amount):
                finished.append((quest, stage))
            elif stage.counts and ql.progress(c, quest) > before:
                counted.append((quest, stage, ql.progress(c, quest)))
        if not finished and not counted:
            return
        self.db.save(c)
        for quest, stage, banked in counted:
            await session.send(p.colored_text(
                f"{quest.title}: {banked} of {stage.amount}.", 1))
        for quest, stage in finished:
            if stage.npc and stage.npc.casefold() != quest.start.casefold():
                where = f"Take it to {stage.npc}."
            else:
                where = f"Return to {quest.start}."
            await session.send(quest_progress_popup(
                f"{quest.title}: {stage.objective} {where}"))

    async def touch_actor(self, session: Session, actor_id: int):
        c = session.character
        if not c:
            return
        if session.pending_spell:
            spell, session.pending_spell = session.pending_spell, None
            target = next((s.character for s in self.sessions if s.character and s.character.actor_id == actor_id), None)
            target = target or self.animals.get(actor_id)
            if target:
                await self.apply_spell(session, spell, target)
            return
        summon = self.animals.get(actor_id)
        if summon and summon.summoned:
            if summon.owner_id != c.actor_id:
                await session.send(p.raw_text("That summon does not belong to you."))
            else:
                await self.open_summon_behavior(session)
            return
        if livestock.is_tame(summon) and summon.map_id == c.map_id:
            await session.send(p.raw_text(livestock.touch_line(summon)))
            return
        if await roads.touch(self, session, actor_id):
            return
        if await sky.touch(self, session, actor_id):
            return
        record = self.npcs.get(actor_id)
        if not record or record[1] != c.map_id:
            return
        npc, _, price, sold = record
        if await watchpost.touch(self, session, actor_id):
            return
        if await lantern.touch(self, session, actor_id):
            return
        if await landing_runtime.touch(self, session, actor_id):
            return
        if await bell.touch(self, session, actor_id):
            return
        # The Four Gates walkthrough, its tour and the Eternal Lands ladder are
        # Four Gates' own: their markers stand there. A copy of one of its
        # people elsewhere (the landing isle's cast) offers none of them.
        # Once the home has moved one of them away (nobody of the name is left
        # at Four Gates), a save already under way still finishes with them;
        # the tour and a fresh ladder are still offered only at Four Gates.
        starts_here = record[1] == wt.HOME_MAP
        at_home = starts_here or not self.stands_on(npc.name, wt.HOME_MAP)
        # NPCs replicate map-wide so their map dots never fade, which lets the
        # client send a touch for one standing anywhere on the map. Talking
        # range stays what replication used to imply: the perception/light
        # radius that still bounds creature visibility.
        if (max(abs(npc.x - c.x), abs(npc.y - c.y))
                > self.creature_visibility_distance(session)):
            await session.send(p.raw_text("You are too far away to talk."))
            return
        role = self.npc_roles.get(actor_id, "dialogue")
        if await self.show_nymara_road(session, actor_id, npc.name):
            return
        if role == "god-priest":
            await self.show_god_priest(session, actor_id, GOD_PRIESTS[npc.name.casefold()])
            return
        if role == "novac":
            await session.send(p.npc_info(npc.name, 0))
            await self.show_novac_main(session, actor_id)
            return
        if await self.show_daily_quest_npc(session, actor_id, npc.name):
            return
        if await self.show_tutorial_quest_npc(session, actor_id, npc.name):
            return
        tutorial_message = self.record_tutorial_npc_progress(c, npc.name)
        if tutorial_message:
            self.db.save(c)
            await session.send(quest_progress_popup(tutorial_message))
        if role == "kane":
            await session.send(p.npc_info(npc.name, 0))
            await self.show_kane_dialogue(session, actor_id)
            return
        if (at_home and npc.name.casefold() == TUTORIAL_ROUTE_NPC.casefold()
                and c.quest_state.get("beginner_tutorial") == 1):
            c.quest_state["beginner_tutorial"] = 2
            levels = award_combat_xp(c, 400, 400)
            self.db.save(c)
            await self.sync_tutorial_markers(session)
            await session.send(p.npc_info(npc.name, 0))
            await session.send(p.npc_text(f"Hello {c.name}! What can I do for you? Would you like to buy some bread or drinks?"))
            await self.send_combat_xp(session, attack=True, defense=True)
            await self.announce_levels(session, levels)
            await session.send(p.raw_text("Great, task completed, you can go back to the Tutorial NPC now. You got 400 attack and defense experience."))
            await session.send(p.npc_options(actor_id, [(900, "Goodbye")]))
            return
        if role == "wraith":
            await session.send(p.npc_info(npc.name, 0))
            await self.show_wraith_main(session, actor_id)
            return
        if role == "tutorial":
            stage = int(c.quest_state.get("beginner_tutorial", 0))
            await session.send(p.npc_info(npc.name, 0))
            if stage == 0 or not at_home:
                # The ladder's offer at Four Gates. A copy of the guide elsewhere,
                # and the moved guide to someone who never started it, offer none
                # of it, but still say who he is and heal newcomers.
                await self.tutorial_main_menu(session, actor_id, ladder=starts_here)
            elif stage == 1:
                await self.tutorial_main_menu(
                    session, actor_id,
                    "Your current task is to follow the blue markers south and"
                    f" talk to {TUTORIAL_ROUTE_NPC}.")
            elif stage == 2:
                await self.tutorial_main_menu(session, actor_id, "Perfect, you finished this quest. The next tutorial is Harvesting.")
            else:
                await self.tutorial_main_menu(session, actor_id)
            return
        if role == "instance":
            await session.send(p.npc_info(npc.name, 0))
            gauntlet_menu = gauntlets.menu(self, npc, session)
            if gauntlet_menu:
                await session.send(p.npc_text(
                    getattr(npc, "dialogue", "") or "The road is open to a party that stands here "
                    "together. Tell me how hard a road you want; I set it to the strongest of you "
                    "and open it for all of you at once."))
                await session.send(p.npc_options(actor_id, gauntlet_menu + [(900, "Not now")]))
                return
            await session.send(p.npc_text(
                "I manage Seridia's combat instances. Gather beside me, set the same "
                "channel above 1000 as active, then choose your team's bracket."))
            await session.send(p.npc_options(
                actor_id,
                [(response_id, label) for response_id, _, label in INSTANCE_CHOICES]
                + [(900, "Not now")]))
            return
        if role == "auction":
            await session.send(p.npc_info(npc.name, 0))
            await self.show_auction_main(session, actor_id)
            return
        if role == "storage":
            await session.send(p.npc_info(npc.name, 0))
            await session.send(p.npc_text(self.npc_greeting(actor_id, npc.name)))
            await session.send(p.npc_options(actor_id, [
                (700, "Open storage"), (701, "How does storage work?")]
                + self.conversation_options(session, npc.name) + [(900, "Goodbye")]))
            return
        if role == "guide":
            if at_home:
                await self.walkthrough_event(session, "talk", npc.name)
            await self.questline_event(session, "talk", npc.name)
            await session.send(p.npc_info(npc.name, 0))
            await session.send(p.npc_text(self.npc_greeting(actor_id, npc.name)))
            options = [(710, "Where do I find things here?"),
                       (711, "Where do the roads go?"),
                       (712, "What work is there?")]
            if starts_here and self.walkthrough_available and not wt.is_active(c)                     and wt.stage_of(c) != wt.DONE:
                options.append((713, "Show me around Four Gates."))
            options.extend(self.conversation_options(session, npc.name))
            await session.send(p.npc_options(actor_id, options + [(900, "Goodbye")]))
            return
        if role == "shop":
            await session.send(p.npc_info(npc.name, 0))
            await self.show_shop_main(session, actor_id)
            return
        if role != "sigil":
            await self.questline_event(session, "talk", npc.name)
            await session.send(p.npc_info(npc.name, 0))
            await session.send(p.npc_text(self.npc_greeting(actor_id, npc.name)))
            await session.send(p.npc_options(
                actor_id,
                self.conversation_options(session, npc.name) + [(900, "Goodbye")]))
            return
        await session.send(p.npc_info(npc.name, 0 if npc.name == "Regia" else 1))
        await session.send(p.npc_text(
            f"Hello, {c.name}! I sell magic items and sigils.\nWhat can I do for you?"))
        await session.send(p.npc_options(actor_id, [
            (1, "Buy items"), (2, "Sell"), (3, "Buy sigils"), (4, "Just passing by...")]))

    async def answer_conversation(self, session: Session, actor_id: int,
                                  npc_name: str, response_id: int) -> bool:
        """Handle a quest or topic option. False means it was not one of ours.

        The option lists are rebuilt here from the character's current state
        rather than remembered, so an index that no longer names anything is
        answered with the NPC's menu again instead of with the wrong quest.
        """
        c = session.character
        if not c or not (lore.TOPIC_BASE <= response_id
                         < QUEST_ABOUT_BASE + QUEST_SLOTS):
            return False
        entry = self.npc_lore.get(npc_name.casefold())
        topic = entry.topic_for(response_id) if entry else None
        if topic is not None:
            if topic not in entry.visible(session.conversation, c.quest_state,
                                          place=c.map_id):
                # An option from a menu built before the thread moved on. The
                # menu is reopened rather than the topic answered, so a replayed
                # id can never reach past a gate the player has not opened.
                await self.reopen_conversation(session, actor_id, npc_name)
                return True
            self.remember_conversation(session, entry, topic)
            await session.send(p.npc_text("\n\n".join(topic.paragraphs)))
            await session.send(p.npc_options(
                actor_id,
                self.conversation_options(session, npc_name) + [(900, "Goodbye")]))
            return True
        if not (QUEST_OFFER_BASE <= response_id < QUEST_ABOUT_BASE + QUEST_SLOTS):
            return False
        base = (response_id - QUEST_OFFER_BASE) // QUEST_SLOTS
        index = (response_id - QUEST_OFFER_BASE) % QUEST_SLOTS
        offers = self.quest_offers(c, npc_name)
        business = self.quest_business(c, npc_name)
        if base == 0 and index < len(offers):
            await self.show_quest_offer(session, actor_id, offers[index])
        elif base == 1 and index < len(offers):
            await self.accept_questline(session, actor_id, offers[index])
        elif base == 2 and index < len(business):
            quest, stage = business[index]
            await self.advance_questline(session, actor_id, quest, stage, npc_name)
        elif base == 3 and index < len(business):
            quest, stage = business[index]
            if stage is None:
                await self.advance_questline(session, actor_id, quest, None, npc_name)
            else:
                await self.remind_questline(session, actor_id, quest, stage)
        else:
            await self.reopen_conversation(session, actor_id, npc_name)
        return True

    def remember_conversation(self, session: Session, entry, topic) -> None:
        """Record what hearing this topic raises, and only what matters.

        A flag nobody is waiting for is a fact about a conversation that has
        already happened, and remembering it would grow the session's set for
        no one's benefit.
        """
        session.conversation.update(
            flag for flag in entry.unlocked_by(topic)
            if flag in self.conversation_flags)

    async def reopen_conversation(self, session: Session, actor_id: int,
                                  npc_name: str) -> None:
        """Show the greeting and whatever the thread currently offers."""
        await session.send(p.npc_text(self.npc_greeting(actor_id, npc_name)))
        await session.send(p.npc_options(
            actor_id,
            self.conversation_options(session, npc_name) + [(900, "Goodbye")]))

    async def show_sigil_menu(self, session: Session, actor_id: int):
        c = session.character
        record = self.npcs.get(actor_id)
        if not c or not record:
            return
        _, _, price, sold = record
        options = [(100 + sid, name.title()) for name, sid in SIGIL_IDS.items()
                   if sid in sold and not c.sigils & (1 << sid)]
        options.append((999, "None, thanks!"))
        await session.send(p.npc_text(
            f"A sigil costs {price} gold coins. What sigil would you like to buy?"))
        await session.send(p.npc_options(actor_id, options))

    async def show_kane_dialogue(self, session: Session, actor_id: int) -> None:
        """Show Captain Kane's EL-DB-derived introductory conversation."""
        await session.send(p.npc_text(
            "A weathered elf sits at the table aboard the Black Raven II, "
            "carefully nursing a flagon of White Stone mead. He looks up as "
            "you approach. \"I see you made it past the rats. Have you come "
            "about the job?\""))
        await session.send(p.npc_options(actor_id, [
            (7400, "The job?"),
            (7401, "Tell me about the Black Raven II."),
            (7402, "What happened to your last mate?"),
            (7403, "How did you become her captain?"),
            (7408, "Who are your clients?"),
            (7410, "Do you know Captain Ios?"),
            (900, "Goodbye"),
        ]))

    async def respond_to_kane(
            self, session: Session, actor_id: int, response_id: int) -> None:
        """Navigate Kane's ship, crew, and smuggling stories."""
        pages = {
            7400: (
                "Captain Kane says he commands the Black Raven II and is "
                "looking for a new mate. His former mate left him badly in "
                "need of someone dependable.",
                [(7402, "What was wrong with the last mate?"),
                 (7401, "Tell me about the ship."), (900, "Not interested.")]),
            7401: (
                "Kane calls the Black Raven II a battered but dependable "
                "ferry between White Stone and Desert Pines. She is smaller "
                "than the original Black Raven, but he is fiercely proud of her.",
                [(7403, "What happened to the original?"),
                 (7408, "Who hires you?"), (900, "Goodbye")]),
            7402: (
                "The former mate was careless, habitually drunk, and once "
                "fell into the water while mooring at Lakeside, dragging a "
                "helpful passenger in with him. Kane is glad to be rid of him.",
                [(7400, "Are you still hiring?"),
                 (7403, "Tell me your story."), (900, "Goodbye")]),
            7403: (
                "Kane once captained the original Black Raven as a merchant "
                "marine. On a voyage carrying passengers and gold ore, a "
                "violent storm caught the ship near Roanof.",
                [(7404, "What happened in the storm?"), (900, "Goodbye")]),
            7404: (
                "He put the passengers into a lifeboat and remained aboard, "
                "trying to save the Black Raven. A monstrous wave tore the "
                "ship apart, and Kane survived only by clinging to wreckage.",
                [(7405, "How were you rescued?"), (900, "Goodbye")]),
            7405: (
                "Kane awoke on the north coast of Tarsengaard after drifting "
                "ashore. The passengers and lifeboat were never found, and "
                "his survivor's guilt still drives him to drink.",
                [(7406, "How did you recover?"), (900, "Goodbye")]),
            7406: (
                "Friends and fellow sailors helped him buy and repair an old "
                "fishing vessel. He renamed it the Black Raven II and began "
                "running the ferry route.",
                [(7408, "And your private clients?"), (900, "Goodbye")]),
            7408: (
                "The official ferry work pays poorly, so Kane quietly moves "
                "goods for private clients who prefer to avoid government "
                "taxes and scrutiny.",
                [(7409, "That sounds like smuggling."),
                 (7410, "What does Captain Ios think?"), (900, "Goodbye")]),
            7409: (
                "Kane dislikes the word smuggling. He sees it as matching "
                "buyers and sellers while taking a modest share for the risk. "
                "He admits that Captain Ios would never conduct such business.",
                [(7410, "Tell me about Captain Ios."), (900, "Goodbye")]),
            7410: (
                "Kane describes Captain Ios as an honest sailor who runs the "
                "Isla Prima to White Stone ferry. He suggests finding Ios and "
                "speaking with him sometime.",
                [(7400, "Back to the job."), (900, "Farewell, Captain.")]),
        }
        if response_id == 900:
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            return
        page = pages.get(response_id)
        if not page:
            await self.show_kane_dialogue(session, actor_id)
            return
        text, options = page
        await session.send(p.npc_text(text))
        await session.send(p.npc_options(actor_id, options))

    async def show_sigil_menu(self, session: Session, actor_id: int):
        c = session.character
        record = self.npcs.get(actor_id)
        if not c or not record:
            return
        _, _, price, sold = record
        options = [(100 + sid, name.title()) for name, sid in SIGIL_IDS.items()
                   if sid in sold and not c.sigils & (1 << sid)]
        options.append((999, "None, thanks!"))
        await session.send(p.npc_text(
            f"A sigil costs {price} gold coins. What sigil would you like to buy?"))
        await session.send(p.npc_options(actor_id, options))

    async def respond_to_npc(self, session: Session, actor_id: int, response_id: int):
        c = session.character
        if not c:
            return
        record = self.npcs.get(actor_id)
        if not record:
            # Stillglass companions are spell-targetable Characters, with
            # their own map, distance and lesson checks for dialogue responses.
            if sky.on_map(c):
                await sky.respond(self, session, actor_id, response_id)
            return
        if record[1] != c.map_id \
                or max(abs(c.x-record[0].x), abs(c.y-record[0].y)) > 4:
            return
        if await watchpost.respond(self, session, actor_id, response_id):
            return
        if await roads.respond(self, session, actor_id, response_id):
            return
        if await sky.respond(self, session, actor_id, response_id):
            return
        if await bell.respond(self, session, actor_id, response_id):
            return
        if await lantern.respond(self, session, actor_id, response_id):
            return
        if await landing_runtime.respond(self, session, actor_id, response_id):
            return
        role = self.npc_roles.get(actor_id, "dialogue")
        starts_here = record[1] == wt.HOME_MAP
        at_home = starts_here or not self.stands_on(record[0].name, wt.HOME_MAP)
        if role == "tutorial" and response_id not in (1000, 1002) and not (
                at_home and (starts_here or c.quest_state.get("beginner_tutorial"))):
            # The ladder is Four Gates' (see touch_actor): a copy of its guide
            # elsewhere answers as an ordinary person, replayed ids included,
            # and so does the moved guide to someone who never started it,
            # beyond who he is and the newcomers' heal.
            role = "dialogue"
        # Conversation and quest options are appended to every role's menu, so
        # they are answered before the role gets a look at the number.
        if await self.answer_conversation(
                session, actor_id, record[0].name, response_id):
            return
        if response_id == 8800 and await self.advance_nymara_road(
                session, actor_id, record[0].name):
            return
        if role == "novac":
            await session.send(p.npc_info(record[0].name, 0))
            await self.respond_to_novac(session, actor_id, response_id)
            return
        if role == "wraith":
            if response_id == WRAITH_MAIN_PERKS:
                await self.show_wraith_perks(session, actor_id)
            elif response_id == WRAITH_MAIN_ATTRIBUTES:
                await self.show_wraith_choices(session, actor_id, "attribute")
            elif response_id == WRAITH_MAIN_NEXUS:
                await self.show_wraith_choices(session, actor_id, "nexus")
            elif WRAITH_PERK_BASE <= response_id < WRAITH_PERK_BASE + len(WRAITH_PERKS):
                perk = WRAITH_PERKS[response_id - WRAITH_PERK_BASE]
                await self.confirm_wraith_choice(session, actor_id, "perk", perk.name)
            elif (WRAITH_PERK_BASE + len(WRAITH_PERKS) < response_id
                  <= WRAITH_PERK_BASE + len(WRAITH_PERKS) + 3):
                page = response_id - WRAITH_PERK_BASE - len(WRAITH_PERKS)
                await self.show_wraith_perks(session, actor_id, page)
            elif WRAITH_ATTRIBUTE_BASE <= response_id < WRAITH_ATTRIBUTE_BASE + len(ATTRIBUTES):
                await self.confirm_wraith_choice(
                    session, actor_id, "attribute",
                    ATTRIBUTES[response_id - WRAITH_ATTRIBUTE_BASE])
            elif WRAITH_NEXUS_BASE <= response_id < WRAITH_NEXUS_BASE + len(NEXUS):
                await self.confirm_wraith_choice(
                    session, actor_id, "nexus",
                    NEXUS[response_id - WRAITH_NEXUS_BASE])
            elif response_id == WRAITH_CONFIRM_YES:
                await self.complete_wraith_choice(session, actor_id)
            elif response_id == WRAITH_CONFIRM_NO:
                await self.show_wraith_main(session, actor_id)
            elif response_id == 900:
                session.pending_wraith = None
                await session.send(p.packet(p.CLOSE_NPC_MENU))
            else:
                await self.show_wraith_main(session, actor_id)
            return
        if role == "auction":
            await session.send(p.npc_info(record[0].name, 0))
            if response_id == AUCTION_BROWSE:
                await self.show_auction_browse(session, actor_id)
            elif response_id == AUCTION_MINE:
                await self.show_my_auctions(session, actor_id)
            elif response_id == AUCTION_COLLECT:
                await self.collect_auction_escrow(session, actor_id)
            elif (AUCTION_LISTING_BASE <= response_id <
                  AUCTION_LISTING_BASE + len(session.auction_listing_ids)):
                listing_id = session.auction_listing_ids[
                    response_id - AUCTION_LISTING_BASE]
                await self.show_auction_listing(session, actor_id, listing_id)
            elif response_id in {AUCTION_RENEW, AUCTION_CANCEL}:
                listing_id = session.selected_auction_listing
                if listing_id is None:
                    await self.show_my_auctions(session, actor_id)
                elif response_id == AUCTION_RENEW:
                    listing = self.auctions.renew(c.username, listing_id)
                    await self.show_auction_listing(
                        session, actor_id, listing.listing_id)
                else:
                    listing = self.auctions.cancel(c.username, listing_id)
                    await self.show_my_auctions(session, actor_id)
            elif response_id == 900:
                session.auction_listing_ids = []
                session.selected_auction_listing = None
                await session.send(p.packet(p.CLOSE_NPC_MENU))
            else:
                await self.show_auction_main(session, actor_id)
            return
        if role == "shop":
            shop = self.shop_for_actor(actor_id)
            if not shop:
                await session.send(p.packet(p.CLOSE_NPC_MENU))
                return
            if not await self.answer_shop_response(
                    session, actor_id, response_id, shop):
                await session.send(p.packet(p.CLOSE_NPC_MENU))
            return
        if role == "instance" and gauntlets.MENU_BASE <= response_id < gauntlets.MENU_BASE + gauntlets.MENU_SPAN:
            picked = gauntlets.choice_for_response(self, record[0], response_id)
            if picked is not None:
                definition, tier = picked
                try:
                    await gauntlets.start(self, session, record[0], definition, tier=tier)
                except ValueError as exc:
                    await session.send(p.npc_text(str(exc)))
                    await session.send(p.npc_options(actor_id, [(900, "Close")]))
                return
            choice = next(
                (name for option, name, _ in INSTANCE_CHOICES if option == response_id),
                "")
            try:
                await self.enter_instance_team(session, record[0], choice)
            except ValueError as exc:
                await session.send(p.npc_text(str(exc)))
                await session.send(p.npc_options(actor_id, [(900, "Close")]))
            return
        if role == "tutorial" and response_id == 1000:
            await session.send(p.npc_text("I am the Tutorial NPC. I can explain the game and guide you through its beginner lessons."))
            await session.send(p.npc_options(actor_id, [(900, "Close")]))
            return
        if role == "tutorial" and response_id == 1001:
            if int(c.quest_state.get("beginner_tutorial", 0)) == 0:
                await session.send(p.npc_text(
                    "Finish the tutorials to understand the game and earn useful items and experience."))
                await session.send(p.npc_options(actor_id, [(1100, "Scouting Tutorial")]))
            else:
                await session.send(p.npc_text(
                    "Scouting is already complete. Continue with your current tutorial task."))
                await session.send(p.npc_options(actor_id, [(1003, "What's my current task?")]))
            return
        if role == "tutorial" and response_id == 1100:
            if int(c.quest_state.get("beginner_tutorial", 0)) == 0:
                await self.tutorial_page(session, actor_id, 1110)
            else:
                await session.send(p.npc_text("Scouting is already complete."))
                await session.send(p.npc_options(actor_id, [(1003, "What's my current task?")]))
            return
        if role == "tutorial" and 1110 <= response_id <= 1114:
            if int(c.quest_state.get("beginner_tutorial", 0)) == 0:
                await self.tutorial_page(session, actor_id, response_id)
            else:
                await session.send(p.npc_text("Scouting is already complete."))
                await session.send(p.npc_options(actor_id, [(1003, "What's my current task?")]))
            return
        if role == "tutorial" and response_id == 1200:
            await self.tutorial_page(session, actor_id, 1210)
            return
        if role == "tutorial" and 1210 <= response_id <= 1215:
            await self.tutorial_page(session, actor_id, response_id)
            return
        if role == "tutorial" and response_id == 1002:
            if c.skills["attack"] <= 20:
                c.health = c.max_health
                # Recreate the actor with authoritative current and maximum HP.
                # GET_ACTOR_HEALTH does not update the stock client's overhead
                # current-health bar reliably, while the actor packet carries both.
                remove = p.packet(p.REMOVE_ACTOR, struct.pack("<H", c.actor_id))
                for viewer in list(self.sessions):
                    if viewer.character and viewer.character.map_id == c.map_id:
                        await viewer.send(remove)
                        await viewer.send(self.player_actor_packet(viewer, c))
                # The lower UI health value is carried in the complete stats packet.
                await session.send(stats_packet(c))
                self.db.save(c)
                await session.send(p.npc_text("There you are. You are fully healed."))
            else:
                await session.send(p.npc_text("I can only heal players of Attack level 20 or lower."))
            await session.send(p.npc_options(actor_id, [(900, "Close")]))
            return
        if role == "tutorial" and response_id == 1003:
            stage = int(c.quest_state.get("beginner_tutorial", 0))
            message = ("Choose Tutorials, then Scouting Tutorial." if stage == 0 else
                       f"Follow the blue markers south and talk to {TUTORIAL_ROUTE_NPC}." if stage == 1 else
                       "Return here and choose Scouting tutorial completed." if stage == 2 else
                       self.tutorial_status(c, min(stage, TUTORIAL_FINAL_STAGE))[1] if stage <= TUTORIAL_FINAL_STAGE else
                       "You have completed the Beginner Tutorial.")
            await session.send(p.npc_text(message))
            await session.send(p.npc_options(actor_id, [(900, "Close")]))
            return
        if response_id == 800 and role == "tutorial":
            c.quest_state["beginner_tutorial"] = 1
            self.db.save(c)
            await session.send(p.npc_text(
                "Scouting lesson: follow the markers to the Four Gates ferry"
                f" landing and talk to {TUTORIAL_ROUTE_NPC} at"
                f" [{TUTORIAL_ROUTE_MARKERS[-1][0]},{TUTORIAL_ROUTE_MARKERS[-1][1]}],"
                " then return here."))
            await session.send(p.npc_options(actor_id, [(900, "I understand")]))
            return
        if response_id == 801 and role == "tutorial" and c.quest_state.get("beginner_tutorial") == 2:
            c.quest_state["beginner_tutorial"] = 3
            self.prepare_tutorial_stage(c, 3)
            self.db.save(c)
            await session.send(p.npc_text("Perfect, you finished this quest. The next tutorial is Harvesting, teaching you how to gather resources and use storage."))
            await session.send(p.npc_options(actor_id, [(1200, "Harvest Tutorial"), (900, "Later")]))
            return
        if response_id == 801 and role == "tutorial" and 3 <= int(c.quest_state.get("beginner_tutorial", 0)) <= TUTORIAL_FINAL_STAGE:
            stage = int(c.quest_state["beginner_tutorial"])
            title, _, complete = self.tutorial_status(c, stage)
            if not complete:
                await session.send(p.npc_text("You have not completed that lesson yet."))
                return
            reward_text = await self.reward_tutorial_stage(session, stage)
            c.quest_state["beginner_tutorial"] = stage + 1
            self.prepare_tutorial_stage(c, stage + 1)
            session.inventory_slots = self.sync_inventory_slots(c)
            await session.send(p.inventory_packet(
                c.inventory, ITEMS, c.equipment, session.inventory_slots))
            if stage == TUTORIAL_FINAL_STAGE:
                c.achievements.add("Beginner Tutorial")
                await self.award_achievements(session)
                next_text = "You have completed the Beginner Tutorial."
                # The quest is over, and the client is told so rather than
                # working it out from the journal falling silent.
                await self.announce_quest_finished(session, QUEST_TUTORIAL)
            else:
                next_title, next_objective, _ = self.tutorial_status(c, stage + 1)
                next_text = f"Next: {next_title}. {next_objective}"
            self.db.save(c)
            await session.send(p.npc_text(
                f"{title} complete. Reward: {reward_text}.\n{next_text}"))
            await session.send(p.npc_options(
                actor_id, [(1003, "Next task"), (900, "Continue")]))
            return

        if response_id == 700 and role == "storage":
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            await self.open_storage(session)
            return
        if response_id == 701 and role == "storage":
            await session.send(p.npc_text("Choose a category, then click inventory items to deposit them or storage items to withdraw them. Stored items persist between logins."))
            await session.send(p.npc_options(actor_id, [(700, "Open storage"), (900, "Goodbye")]))
            return
        if 710 <= response_id <= 712 and role == "guide":
            await self.answer_guide_question(session, actor_id, response_id)
            return
        if response_id == 713 and role == "guide" and starts_here:
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            await self.restart_walkthrough(session)
            return
        if response_id == 900:
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            return
        if role != "sigil":
            await session.send(p.packet(p.CLOSE_NPC_MENU))
            return
        keeper_shop = self.shop_for_actor(actor_id)
        if response_id == 3:
            await self.show_sigil_menu(session, actor_id)
        elif response_id in {1, 2}:
            # "Buy items" and "Sell": the keeper's reagent counter, run
            # through the same shop flow every merchant uses, so the NPC's
            # own greeting ("I sell magic items and sigils") is honest.
            if keeper_shop:
                await self.show_shop_items(
                    session, actor_id, "buy" if response_id == 1 else "sell")
            else:
                await session.send(p.npc_text("That part of my shop is not stocked yet."))
                await session.send(p.npc_options(actor_id, [(3, "Buy sigils"), (4, "Just passing by...")]))
        elif 100 <= response_id < 126:
            sid = response_id - 100
            name = next((name for name, value in SIGIL_IDS.items() if value == sid), "")
            try:
                await self.buy_sigil(session, name)
                await session.send(p.npc_text(f"The {name.title()} sigil is now yours."))
            except ValueError as exc:
                await session.send(p.npc_text(str(exc)))
            await self.show_sigil_menu(session, actor_id)
        elif keeper_shop and await self.answer_shop_response(
                session, actor_id, response_id, keeper_shop):
            pass
        else:
            await session.send(p.packet(p.CLOSE_NPC_MENU))

    @staticmethod
    def increment_achievement(c: Character, key: str, amount: int = 1) -> None:
        c.achievement_counters[key] = min(
            0xFFFFFFFF, max(0, int(c.achievement_counters.get(key, 0))) + max(0, int(amount)))

    @staticmethod
    def increment_leaderboard(c: Character, key: str, amount: int = 1) -> None:
        c.leaderboard_stats[key] = min(
            0xFFFFFFFF, max(0, int(c.leaderboard_stats.get(key, 0)))
            + max(0, int(amount)))

    @staticmethod
    def prepare_tutorial_stage(c: Character, stage: int) -> None:
        """Initialize objectives that must be completed after their lesson starts."""
        if stage == 3 and not c.quest_state.get("tutorial_pickaxe_given"):
            if c.inventory.get("Pickaxe", 0) + c.storage.get("Pickaxe", 0) < 1:
                c.storage["Pickaxe"] = 1
            c.quest_state["tutorial_pickaxe_given"] = True
        elif stage == 4:
            c.quest_state["tutorial_quarry_kills_start"] = int(
                c.kills.get("crown_antler_stag", 0))
            c.quest_state.pop("tutorial_combat_complete", None)
        elif stage == 5 and not c.quest_state.get("tutorial_food_given"):
            c.storage["Bread"] = c.storage.get("Bread", 0) + 3
            c.quest_state["tutorial_food_given"] = True
        elif stage == 6 and not c.quest_state.get("tutorial_making_materials_given"):
            # What a Torch takes, plus the tool it is held with.
            for name in ("Wood Plank", "Cloth Roll"):
                c.inventory[name] = c.inventory.get(name, 0) + 10
            c.inventory["Hatchet"] = c.inventory.get("Hatchet", 0) + 1
            c.quest_state["tutorial_making_materials_given"] = True
            c.quest_state["tutorial_torches_made"] = 0
            c.quest_state.pop("tutorial_making_complete", None)

    async def notify_tutorial_quarry_kill(
            self, session: Session, animal: Animal) -> None:
        """Notify once when the fighting tutorial's tenth new kill lands."""
        c = session.character
        if (not c or animal.species.casefold() != "crown_antler_stag"
                or int(c.quest_state.get("beginner_tutorial", 0)) != 4
                or c.quest_state.get("tutorial_combat_complete")):
            return
        start = int(c.quest_state.get("tutorial_quarry_kills_start", 0))
        killed = max(0, int(c.kills.get("crown_antler_stag", 0)) - start)
        if killed < 10:
            return
        c.quest_state["tutorial_combat_complete"] = True
        await session.send(quest_progress_popup(
            "Excellent, you killed all 10 Crown Stags. Return to the Tutorial NPC "
            "for your bonus Attack and Defense experience."))

    @staticmethod
    def record_tutorial_npc_progress(c: Character, npc_name: str) -> str | None:
        """Advance passive tutorial hand-offs without bypassing their real quests."""
        stage = int(c.quest_state.get("beginner_tutorial", 0))
        name = npc_name.casefold()
        if stage == 7 and name == "kane":
            c.quest_state["visited_kane"] = True
            return "You found Kane. Return to the Tutorial NPC."
        if stage == 17 and name == "aurora":
            c.quest_state["visited_aurora"] = True
            return "You found Aurora in the fast-reading area. Return to the Tutorial NPC."

        if c.quest_state.get("seridia_journey_started") \
                and not c.quest_state.get("seridia_journey_complete"):
            route = ("tobias", "kalana", "nyeald", "erokin", "koki", "rosalyn", "tankel")
            index = int(c.quest_state.get("seridia_journey_index", 0))
            if index < len(route) and name == route[index]:
                index += 1
                c.quest_state["seridia_journey_index"] = index
                if index == len(route):
                    c.quest_state["seridia_journey_ready"] = True
                    return ("Tankel has finished the last lesson. Return to the Wraith on "
                            "Isla Prima and choose the skill for your reward.")
                return f"Journey lesson complete. Your next guide is {route[index].title()}."
        return None

    async def show_tutorial_quest_npc(self, session: Session, actor_id: int,
                                      npc_name: str) -> bool:
        """Show dialogue for quests that the Beginner Tutorial depends upon."""
        c = session.character
        name = npc_name.casefold()
        stage = int(c.quest_state.get("beginner_tutorial", 0))

        if name == "lasud" and not (
                c.quest_state.get("past_quest_complete")
                or c.quest_state.get("lasud_quest")):
            await session.send(p.npc_info(npc_name, 0))
            if c.quest_state.get("past_quest_started"):
                text = ("Atekel in Nordcarn's magic shop can reveal your past. "
                        "Bring her 10 Rose Quartz.")
                options = [(900, "I will find her.")]
            else:
                text = ("New arrivals remember very little. Atekel, the leader of the "
                        "Nordcarn mages, may be able to uncover your past.")
                options = [(7200, "I want to learn about my past."), (900, "Not now.")]
            await session.send(p.npc_text(text))
            await session.send(p.npc_options(actor_id, options))
            return True

        if name == "atekel" and c.quest_state.get("past_quest_started") \
                and not c.quest_state.get("past_quest_complete"):
            quartz = c.inventory.get("Rose Quartz", 0)
            await session.send(p.npc_info(npc_name, 0))
            await session.send(p.npc_text(
                "Lasud sent you to me. Ten Rose Quartz will focus the spell that "
                "reveals the memories hidden by your arrival."))
            options = ([(7201, "Give 10 Rose Quartz")] if quartz >= 10 else
                       [(900, f"I only have {quartz} Rose Quartz.")])
            await session.send(p.npc_options(actor_id, options))
            return True

        if name == "ayelle" and not (
                c.quest_state.get("ayelle_first_objective_complete")
                or c.quest_state.get("ayenne_objective")):
            await session.send(p.npc_info(npc_name, 0))
            if not c.quest_state.get("ayelle_alchemy_started"):
                text = ("My alchemy course begins with Fire Essence. Start the lesson, "
                        "then mix one here in the Desert Pines Alchemical Academy.")
                options = [(7204, "Start the alchemy tutorial."), (900, "Not now.")]
            elif not c.quest_state.get("ayelle_fire_essence_made"):
                text = ("Mix one Fire Essence here in the academy. Bringing an old "
                        "essence does not complete the lesson.")
                options = [(900, "I will make one.")]
            else:
                text = "You successfully made the Fire Essence. Report it to finish the first objective."
                options = [(7205, "I made the Fire Essence."), (900, "Later.")]
            await session.send(p.npc_text(text))
            await session.send(p.npc_options(actor_id, options))
            return True

        if name == "the wraith" and stage == 20 and not (
                c.quest_state.get("seridia_journey_complete")
                or c.quest_state.get("seridian_journey")):
            await session.send(p.npc_info(npc_name, 0))
            if not (c.quest_state.get("past_quest_complete")
                    or c.quest_state.get("lasud_quest")):
                text = "Lasud's past quest must be completed before the Seridia Journey."
                options = [(900, "I will speak with Lasud.")]
            elif not c.quest_state.get("seridia_journey_started"):
                text = ("Your Seridia Journey will take you, in order, to Tobias, Kalana, "
                        "Nyeald, Erokin, Koki, Rosalyn, and Tankel.")
                options = [(7206, "Begin the Seridia Journey."), (900, "Not yet.")]
            elif not c.quest_state.get("seridia_journey_ready"):
                route = ("Tobias", "Kalana", "Nyeald", "Erokin", "Koki", "Rosalyn", "Tankel")
                index = min(int(c.quest_state.get("seridia_journey_index", 0)), len(route) - 1)
                text = f"Continue your journey by speaking with {route[index]}."
                options = [(900, "I will continue.")]
            else:
                skills = ("attack", "defense", "harvesting", "alchemy", "magic",
                          "potion", "summoning", "manufacturing", "crafting",
                          "engineering", "tailoring", "ranging")
                text = "Your journey is complete. Choose the skill that receives 1,000 experience."
                options = [(7300 + index, skill.title())
                           for index, skill in enumerate(skills)]
            await session.send(p.npc_text(text))
            await session.send(p.npc_options(actor_id, options))
            return True
        return False

    async def respond_to_tutorial_quest_npc(self, session: Session, actor_id: int,
                                            npc_name: str,
                                            response_id: int) -> bool:
        """Apply explicit quest choices; ordinary contact never completes these quests."""
        if not (7200 <= response_id < 7400):
            return False
        c = session.character
        name = npc_name.casefold()
        message = None
        journey_levels = []

        if response_id == 7200 and name == "lasud":
            c.quest_state["past_quest_started"] = True
            message = "Find Atekel in Nordcarn's magic shop and bring her 10 Rose Quartz."
        elif response_id == 7201 and name == "atekel":
            if c.inventory.get("Rose Quartz", 0) < 10:
                message = "You need 10 Rose Quartz."
            else:
                c.inventory["Rose Quartz"] -= 10
                if not c.inventory["Rose Quartz"]:
                    del c.inventory["Rose Quartz"]
                c.quest_state["past_quest_complete"] = True
                c.quest_state["lasud_quest"] = True
                message = "The spell restores your memories. Lasud's past quest is complete."
        elif response_id == 7204 and name == "ayelle":
            c.quest_state["ayelle_alchemy_started"] = True
            c.quest_state.pop("ayelle_fire_essence_made", None)
            message = "Mix one Fire Essence inside this academy, then report back to Ayelle."
        elif response_id == 7205 and name == "ayelle":
            if not c.quest_state.get("ayelle_fire_essence_made"):
                message = "You have not made the Fire Essence in the academy yet."
            else:
                c.quest_state["ayelle_first_objective_complete"] = True
                c.quest_state["ayenne_objective"] = True
                message = "Ayelle's first alchemy objective is complete."
        elif response_id == 7206 and name == "the wraith":
            if not (c.quest_state.get("past_quest_complete")
                    or c.quest_state.get("lasud_quest")):
                message = "Complete Lasud's past quest first."
            else:
                c.quest_state["seridia_journey_started"] = True
                c.quest_state["seridia_journey_index"] = 0
                c.quest_state.pop("seridia_journey_ready", None)
                message = "Your journey has begun. First, speak with Tobias in White Stone."
        elif 7300 <= response_id < 7312 and name == "the wraith":
            if not c.quest_state.get("seridia_journey_ready"):
                message = "Your Seridia Journey is not complete."
            else:
                skills = ("attack", "defense", "harvesting", "alchemy", "magic",
                          "potion", "summoning", "manufacturing", "crafting",
                          "engineering", "tailoring", "ranging")
                skill = skills[response_id - 7300]
                journey_levels = award_experience(c, ((skill, 1000),))
                c.quest_state["seridia_journey_complete"] = True
                c.quest_state["seridian_journey"] = True
                message = f"Seridia Journey complete. You receive 1,000 {skill.title()} experience."
        else:
            return False

        session.inventory_slots = self.sync_inventory_slots(c)
        self.db.save(c)
        await session.send(p.inventory_packet(
            c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await self.send_stats(session, force=True)
        if journey_levels:
            await self.announce_levels(session, journey_levels)
        await session.send(p.npc_text(message or "Quest updated."))
        await session.send(p.npc_options(actor_id, [(900, "Close")]))
        return True

    @staticmethod
    def tutorial_status(c: Character, stage: int) -> tuple[str, str, bool]:
        """One lesson's title, objective and whether it is done.

        This ladder ran to stage 20 and was Eternal Lands' own: Isla Prima's
        nine flowers and rat cave, then Kane on the Desert Pines ship, Novac,
        Xaquelina, Haidir, Ayenne, Aurora, Lasud and Atekel, and the Wraith's
        journey across Seridia. Every one of those NPCs exists only in the
        Eternal Lands profile, so on the profile this server actually runs the
        tutorial stalled at stage 7 - a ship on an unserved map, crewed by
        nobody - and could not be finished at all.

        What is here is the part Eloria can complete today, in the same order
        and with the same mechanics. The lessons that need an NPC to hand out a
        mission come back as that content is authored; `TUTORIAL_FINAL_STAGE`
        is what moves when they do.
        """
        have = lambda name, amount=1: (c.inventory.get(name, 0) + c.storage.get(name, 0)
                                      + sum(worn == name for worn in c.equipment.values()) >= amount)
        stored = lambda name, amount=1: c.storage.get(name, 0) >= amount
        data = {
            3: ("Harvesting tutorial",
                "Gather one of each resource inside Four Gates, in marker order,"
                " and place them in storage. Nesh's Pickaxe is in your storage;"
                " withdraw it from Cache Keeper Dellin before mining.",
                all(stored(name) for name, _, _, _ in TUTORIAL_HARVESTS)),
            4: ("Fighting tutorial", "Kill 10 Crown Stags on the Four Gates approach.",
                c.kills.get("crown_antler_stag", 0)
                - int(c.quest_state.get("tutorial_quarry_kills_start", 0)) >= 10),
            5: ("Eating tutorial", "Raise your food level to at least 35. Withdraw your Bread"
                " from Cache Keeper Dellin; Bettany Orl sells more.", c.food >= 35),
            6: ("Item making tutorial", "Successfully make 5 Torches from the materials provided."
                " Quartermaster Perrin Lock sells replacement planks, cloth and tools.",
                int(c.quest_state.get("tutorial_torches_made", 0)) >= 5),
            7: ("Mineral harvesting tutorial", "Harvest Quartz in Four Gates with your Pickaxe"
                " and store 100 with Cache Keeper Dellin. Make several trips if your pack fills.",
                stored("Quartz", 100) or stored("Sulfur", 100)),
            8: ("Increasing attributes tutorial", "Spend 2 pickpoints on any attributes. Earn"
                " pickpoints through overall levels, use minus and plus in Statistics to"
                " adjust your choices, then click Confirm.",
                sum(max(0, c.attributes[key] - c.temporary_attributes.get(key, 0) - 4)
                    for key in ATTRIBUTES) >= 2),
            9: ("Moneymaking tutorial", "Sell harvested Sage or Reed to Bettany Orl on the plaza"
                " and place 1,000 Gold Coins in storage.", stored("Gold Coins", 1000)),
            10: ("Magic tutorial", "Own Change and Move, the sigils for Heal. Withdraw 800 Gold"
                 " Coins and buy both from Sigil Keeper Ansa on the plaza.",
                 (bool(c.sigils & (1 << SIGIL_IDS["change"])) and
                  bool(c.sigils & (1 << SIGIL_IDS["move"]))) or
                 (bool(c.sigils & (1 << SIGIL_IDS["increase"])) and
                  bool(c.sigils & (1 << SIGIL_IDS["health"])))),
            11: ("Manufacturing tutorial", "Make or bring a Militia Arming Sword. The sword"
                 " awarded for the fighting lesson is in storage and also qualifies.",
                 have("Militia Arming Sword")),
        }
        # A character saved partway up the old twenty-stage ladder can arrive
        # here asking for stage 15. Clamping is what stops that being a crash
        # on login; they see the last lesson and finish from there.
        return data[min(max(stage, 3), TUTORIAL_FINAL_STAGE)]

    async def reward_tutorial_stage(self, session: Session, stage: int) -> str:
        c = session.character
        # Keyed to the lessons in `tutorial_status`. The old table ran to
        # stage 20 and rewarded lessons that could not be reached.
        xp = {
            3: (("harvesting", 400),),
            4: (("attack", 400), ("defense", 400)),
            5: (("attack", 300), ("defense", 300), ("harvesting", 300)),
            6: (("manufacturing", 400),),
            7: (("harvesting", 1000),),
            8: (("attack", 500), ("defense", 500)),
            9: (("harvesting", 1000),),
            10: (("magic", 1000),),
            11: (("manufacturing", 1000), ("magic", 1000)),
        }
        level_ups = award_experience(c, xp.get(stage, ()))
        rewards = {3: (("Homespun Shirt", 1),),
                   4: (("Militia Arming Sword", 1), ("Bonehook Jerkin", 1)),
                   9: (("Gold Coins", 500),),
                   TUTORIAL_FINAL_STAGE: (("Gold Coins", 1000),)}
        granted_items = rewards.get(stage, ())
        for name, quantity in granted_items:
            c.storage[name] = c.storage.get(name, 0) + quantity
        await self.send_stats(session, force=True)
        if level_ups:
            await self.announce_levels(session, level_ups)
        parts = [f"{amount:,} {skill.title()} experience"
                 for skill, amount in xp.get(stage, ())]
        parts.extend(f"{quantity} {name} in storage"
                     for name, quantity in granted_items)
        return ", ".join(parts) or "lesson completion"

    def roll_creature_drops(self, animal: Animal) -> list[tuple[str, int]]:
        """Combine the species drop table with the creature's equipped loadout."""
        if getattr(self,"road_run",None) and animal.map_id in self.road_run.private_maps and not animal.summoned:
            return [("Wood Plank",1)]
        if animal.map_id.startswith(sky.MAP + "_"):
            return [("Bones", 1)]
        if animal.map_id.startswith(bell.MAP + "_"):
            return [("Raw Meat", 1)] if animal.species == bell.SCOUT else []
        if animal.species == lantern.BOAR and animal.map_id.startswith(lantern.MAP + "_"):
            return [("Raw Meat", 1)]
        if animal.summoned or self.special_day_has("no_drops"):
            return []
        table = self.drop_tables.get(animal.species, ())
        drops = roll_drops(table)
        # A gauntlet pays more the harder the road its party chose: what
        # falls on it rolls its own table again per step of challenge.
        for _extra in range(gauntlets.creature_drop_rolls(self, animal) - 1):
            drops.extend(roll_drops(table))
        drops.extend((name, 1) for name in animal.equipment.values())
        return drops

    def record_creature_kill(self, c: Character, animal: Animal) -> None:
        rating = animal.attack + animal.defense
        tier = ("low_level_kills" if rating < 60 else
                "medium_level_kills" if rating < 120 else
                "high_level_kills" if rating < 200 else "very_high_level_kills")
        self.increment_achievement(c, tier)
        record_daily_kill(c, animal.species, animal.map_id)
        # Kills on the handful of maps the catalogue counts them on. Only
        # those, so the tally a character carries stays the size of the
        # catalogue rather than the size of the world.
        if animal.map_id in self.achievement_catalogue.tracked_kill_maps:
            self.increment_achievement(c, f"kills_map_{animal.map_id}")
        definition = self.creatures.get(animal.species)
        if definition is not None and getattr(definition, "boss", False):
            self.increment_achievement(c, "bosses_killed")
            # The first of its kind. Every caller bumps `kills` just before
            # this runs, so exactly one there means this species has never
            # fallen to this character before.
            if int(c.kills.get(animal.species, 0)) <= 1:
                self.increment_achievement(c, "boss_kinds")
        if animal.invasion and not animal.instance_name:
            c.invasion_monsters_killed = min(0xFFFFFFFF, c.invasion_monsters_killed + 1)
            if animal.invasion_boss:
                c.invasion_bosses_killed = min(0xFFFFFFFF, c.invasion_bosses_killed + 1)

    def ordered_perks(self, character: Character) -> list[tuple[str, str, int, bool]]:
        """Return (name, description, pickpoints, from_gear) for owned perks.

        Permanent perks come first in the catalog's own order, then any perk
        granted by equipped gear, then anything the catalog does not know
        about, so a renamed or newly added perk still reaches the client.
        """
        effective = character.effective_perks()
        permanent = {name.casefold() for name in character.perks}
        rows: list[tuple[str, str, int, bool]] = []
        seen: set[str] = set()
        for perk in WRAITH_PERKS:
            key = perk.name.casefold()
            if key in {name.casefold() for name in effective}:
                rows.append((perk.name, perk.description, perk.pickpoints,
                             key not in permanent))
                seen.add(key)
        for name in sorted(effective, key=str.casefold):
            if name.casefold() in seen:
                continue
            definition = PERKS_BY_NAME.get(name.casefold())
            rows.append((
                name,
                definition.description if definition else "",
                definition.pickpoints if definition else 0,
                name.casefold() not in permanent))
        return rows

    async def send_perks(self, session: Session) -> None:
        """Publish the player's perks as state instead of as chat text."""
        character = session.character
        if not character:
            return
        await session.send(p.perks_packet(self.ordered_perks(character)))

    async def send_perk_catalog(self, session: Session) -> None:
        """Publish every buyable perk, priced, with the server's own refusal.

        Only the perks a character has are on the wire otherwise, so a window
        offering to spend pick points would have to carry its own copy of the
        perk table to know what one costs. This states the table and states
        why each row cannot be taken, so the client never decides either.
        """
        character = session.character
        if not character:
            return
        categories = "perk_catalog_v3" in session.client_capabilities
        tiers = categories or "perk_catalog_v2" in session.client_capabilities
        if not tiers and "perk_catalog_v1" not in session.client_capabilities:
            return
        rows = self.perk_catalog_rows(character)
        session.perk_catalog_rows = rows
        await session.send(p.perk_catalog_packet(
            rows, tiers=tiers, categories=categories))

    @staticmethod
    def perk_catalog_rows(character: Character) -> list[tuple]:
        """Every buyable perk as the catalogue states it, refusals included."""
        rows = []
        for perk in WRAITH_PERKS:
            if perk.hidden:
                continue
            owned = owned_tier(character, perk)
            # What is priced is the step this character would buy next, not
            # the perk's first tier: a row is an offer, and offering tier one
            # of a perk they already hold is not one.
            step = perk.tier(min(perk.max_tier, owned + 1))
            rows.append((perk.name, step.description, step.pickpoints,
                         step.gold, perk_blocker(character, perk) or "",
                         owned, perk.max_tier, perk.category))
        return rows

    async def restate_perk_catalog(self, session: Session) -> bool:
        """Resend the catalogue if any refusal in it has stopped being true.

        A row's refusal is a snapshot: "not enough gold" was true when the
        catalogue was sent and stops being true the moment a sale goes
        through, and gold moves in fifty places that know nothing about
        perks. The sites that *do* know - a purchase, a level, a stone -
        restate it at once; this catches everything else, so a perk that has
        become affordable is offered rather than left greyed out until the
        next overall level happens to restate the shelf.

        Nothing is sent to a client that has never been sent the catalogue:
        it either cannot read the packet or has not logged in yet.
        """
        character = session.character
        if not character or session.perk_catalog_rows is None:
            return False
        if self.perk_catalog_rows(character) == session.perk_catalog_rows:
            return False
        await self.send_perk_catalog(session)
        return True

    async def restate_perk_catalogs(self) -> int:
        """One reconcile pass over every session. Returns how many were resent."""
        resent = 0
        for session in list(self.sessions):
            try:
                if await self.restate_perk_catalog(session):
                    resent += 1
            except (ConnectionError, OSError):
                # A socket that has gone is the disconnect path's to reap;
                # one dead client must not cost the others their pass.
                continue
        return resent

    async def send_attribute_state(self, session: Session) -> None:
        """State every attribute this character can buy, and its ceiling.

        Sent whenever one of them could have moved. The legacy stats packet
        carries six of the twelve at fixed offsets, so a client that can read
        this should prefer it - and a client that cannot is not shown a wrong
        number, only fewer of them.
        """
        character = session.character
        if not character or "attribute_state_v1" not in session.client_capabilities:
            return
        await session.send(p.attribute_state_packet(
            (name, ATTRIBUTE_LABELS[name],
             character.attributes.get(name, ATTRIBUTE_MINIMUM), ATTRIBUTE_MAXIMUM)
            for name in ATTRIBUTES))

    async def send_counter_layout(self, session: Session) -> None:
        """State how the counters window is arranged, and what fills it.

        Sent whenever a tally could have moved, because the breakdown rows
        and the achievement bars carry values as well as structure. The
        arrangement itself never changes, which is cheap enough to restate.
        """
        character = session.character
        if (not character
                or "counter_layout_v1" not in session.client_capabilities):
            return
        tallies = dict(character.achievement_counters)
        tallies["invasion_monsters_killed"] = int(
            character.invasion_monsters_killed)
        tallies["invasion_bosses_killed"] = int(character.invasion_bosses_killed)
        labels = dict(ACHIEVEMENT_COUNTERS)
        labels["invasion_monsters_killed"] = "Invasion monsters killed"
        labels["invasion_bosses_killed"] = "Invasion bosses killed"
        breakdowns = self.counter_breakdowns(character)
        breakdowns.extend(
            (counter, [(labels.get(key, key), int(tallies.get(key, 0)))
                       for key in keys])
            for counter, keys in COUNTER_BREAKDOWN.items())
        await session.send(p.counter_layout_packet(
            COUNTER_CATEGORIES, breakdowns,
            counter_achievement_rows(tallies)))

    def counter_breakdowns(self, character: Character) -> list[tuple]:
        """(counter, ((name, count), ...)) for every total kept per name.

        The tallies themselves: what was killed, harvested, or made, rather
        than the achievement rungs that measure them. A total with an empty
        tally is left out entirely - the client draws no arrow on a row it was
        sent no breakdown for, which is what a character who has never mixed
        anything should see.
        """
        rows: list[tuple] = []
        for counter in COUNTER_DETAILS:
            tally = (character.kills if counter == ACTIVITY_KILLS
                     else character.counter_details.get(counter, {}))
            if counter in (ACTIVITY_DEATHS, ACTIVITY_BREAKAGES):
                # Older characters have totals without per-name records.
                # Keep those counts visible without inventing their cause.
                missing = int(character.activity_counters.get(counter, 0)) - sum(
                    max(0, int(value)) for value in tally.values())
                if missing > 0:
                    tally = dict(tally)
                    tally["Unknown"] = max(0, int(tally.get("Unknown", 0))) + missing
            detail = [(self.counter_detail_label(counter, name), count)
                      for name, count in counter_detail_rows(tally)]
            if detail:
                rows.append((counter, detail))
        return rows

    def counter_detail_label(self, counter: str, name: str) -> str:
        """What to call one breakdown row.

        Deaths and items are already tallied under their displayed name or
        cause. Kills are tallied by species id, because that is
        what the whole server keys a creature by, so the catalog is asked for
        the name that was on the actor.
        """
        if counter != ACTIVITY_KILLS:
            return name
        spec = getattr(self, "creatures", {}).get(name)
        return spec.name if spec else name.replace("_", " ").title()

    async def send_activity_counters(self, session: Session) -> None:
        """Send the complete lifetime activity totals."""
        character = session.character
        if not character:
            return
        await session.send(p.activity_counters_packet(
            ((name, character.activity_counters.get(name, 0))
             for name in ACTIVITY_COUNTERS), full=True))

    async def record_activity(self, session: Session | None, key: str,
                              amount: int = 1, *, detail: str = "") -> None:
        """Count one confirmed authoritative event and publish the new total.

        Every call site is downstream of the outcome, never of the request, so
        a rejected deposit or a failed mix does not count.

        `detail` names the thing it happened to - the resource that came out
        of the node, the item that came off the bench - and is tallied beside
        the total so the window can open the row onto what it is made of. It
        is recorded here rather than at each call site for the same reason the
        total is: this is the one place that already knows an event happened
        rather than was asked for.
        """
        if session is None or amount <= 0:
            return
        character = session.character
        if not character:
            return
        total = min(0xFFFFFFFF,
                    int(character.activity_counters.get(key, 0)) + amount)
        character.activity_counters[key] = total
        if detail:
            tally = character.counter_details.setdefault(key, {})
            tally[detail] = min(0xFFFFFFFF, int(tally.get(detail, 0)) + amount)
        await session.send(p.activity_counters_packet(
            ((key, total),), full=False))
        # The rows under this one and the bars beside it are values too, and
        # a breakdown that lagged its own total would be the worse half of
        # the window.
        await self.send_counter_layout(session)
        # Every confirmed player event runs through here - that is why this
        # method exists - so this is the one hook the achievement catalogue
        # needs for most of what it measures.
        await self.award_achievements(session)

    def session_for(self, character: Character) -> Session | None:
        return next((candidate for candidate in self.sessions
                     if candidate.character is character), None)

    async def list_perks(self, session: Session) -> None:
        character = session.character
        if not character:
            return
        effective = character.effective_perks()
        owned = {name.casefold(): name for name in effective}
        ordered = [perk.name for perk in WRAITH_PERKS if perk.name.casefold() in owned]
        known = {name.casefold() for name in ordered}
        ordered.extend(sorted(
            (name for name in effective if name.casefold() not in known),
            key=str.casefold))
        if not ordered:
            await session.send(p.raw_text("You have no perks."))
            return
        for name in ordered:
            await session.send(p.raw_text(self.perk_line(character, name)))
        switched_off = sorted(character.perks_disabled, key=str.casefold)
        for name in switched_off:
            await session.send(p.raw_text(f"{name} (switched off)"))

    @staticmethod
    def perk_line(character: Character, name: str) -> str:
        """One perk as a player reads it: where it stands and what it does.

        The tier shown is the one in effect, which is not always the one that
        was bought - gear adds tiers, and a player looking at this list wants
        to know what they have rather than what they paid for. When the two
        differ the line says so, because otherwise a cape looks like nothing
        is happening.

        The description is the tier they are actually at, not the perk's
        first: a list that told somebody at tier three what tier one does
        would be describing a perk they no longer have.
        """
        perk = PERKS_BY_NAME.get(name.casefold())
        if perk is None:
            return name
        tier = character.perk_tier(perk.name)
        if perk.max_tier == 1 and tier <= 1:
            return f"{name} - {perk.description}"
        bought = owned_tier(character, perk)
        worn = tier - bought
        if worn > 0:
            # Past what pick points buy, "of three" would read as a mistake,
            # so the line says where the extra came from instead.
            standing = f"tier {tier}, {bought} bought and {worn} worn"
        else:
            standing = f"tier {tier} of {perk.max_tier}"
        return f"{name} ({standing}) - {perk.describe(tier)}"

    async def toggle_perk_command(self, session: Session, name: str) -> None:
        """Switch a perk at its highest tier off, or back on again.

        Register 017 allows this at maximum tier only, which is enforced in
        `perks.toggle_perk`; this reports its answer and restates the perks,
        because a switched-off perk is not in `effective_perks` and the
        window would otherwise keep showing it as active.
        """
        character = session.character
        if not character:
            return
        if not name:
            await session.send(p.raw_text("Syntax: #perk name"))
            return
        _, message = toggle_perk(character, name)
        await session.send(p.raw_text(message))
        await self.send_perks(session)
        await self.send_perk_catalog(session)
        await self.send_stats(session, force=True)

    def achievement_rows(self, c: Character) -> list[tuple[str, int]]:
        """Every counter this character carries, labelled, in one list.

        The invasion tallies live on the character rather than in the counter
        table, so they are appended here instead of being left as the two
        lines nobody could see anywhere but in chat.
        """
        rows = [(label, int(c.achievement_counters.get(key, 0)))
                for key, label in ACHIEVEMENT_COUNTERS]
        rows.append(("Invasion monsters killed", int(c.invasion_monsters_killed)))
        rows.append(("Invasion bosses killed", int(c.invasion_bosses_killed)))
        return rows

    # ------------------------------------------------------- the catalogue
    #
    # `achievement_rows` above and `counters.py` measure the nineteen tallies
    # against a placeholder ladder. Everything below measures the authored
    # catalogue in `config/eloria/achievements.txt` instead. The two coexist:
    # the counters window keeps its bars, and this is the browsable list.

    def achievement_facts(self, c: Character) -> dict[str, int]:
        """The questions the catalogue asks that are not counts.

        Whether a player is in a guild is not a tally and never will be, so
        `achievements.py` does not try to keep one - it asks for a number and
        this is where the world answers. Every fact the loader accepts is
        answered here; a fact answered nowhere fails the catalogue at start-up
        rather than reading as a permanent zero.
        """
        party = None
        if self.parties is not None and c.username:
            party = self.parties.party_of(c.username)
        finished = [quest for quest in self.questlines.values()
                    if ql.finished(c, quest)]
        return {
            "guild": 1 if c.guild_tag else 0,
            "party": 1 if party is not None and len(party.names()) > 1 else 0,
            "gold": (int(c.inventory.get("Gold Coins", 0))
                     + int(c.storage.get("Gold Coins", 0))),
            "mixes": sum(int(c.activity_counters.get(name, 0))
                         for name in ACTIVITY_MIX_SKILLS.values()),
            "quests_done": len(self.completed_quest_entries(c)),
            "quests_tier3": sum(1 for quest in finished if quest.tier >= 3),
            "quests_tier4": sum(1 for quest in finished if quest.tier >= 4),
            "skills_at_20": sum(1 for skill, level in c.skills.items()
                                if skill != "overall" and int(level) >= 20),
        }

    def achievement_progress(self, c: Character) -> AchievementProgress:
        """Everything the catalogue measures this character against.

        The invasion tallies are folded into the counters here, the same way
        `send_counter_layout` folds them: they live on the character rather
        than in the counter table for historical reasons, and no achievement
        should have to know that.
        """
        counters = dict(c.achievement_counters)
        counters["invasion_monsters_killed"] = int(c.invasion_monsters_killed)
        counters["invasion_bosses_killed"] = int(c.invasion_bosses_killed)
        return AchievementProgress(
            counters=counters, activity=c.activity_counters,
            details=c.counter_details, kills=c.kills, skills=c.skills,
            facts=self.achievement_facts(c))

    def mark_map_visit(self, c: Character, map_id: str) -> bool:
        """Record a first arrival. True when this map is new to the character.

        A visit is a counter rather than a set on the character, so exploration
        arrived without a database migration - see `docs/achievements.md`. The
        rollups are counted here rather than derived from the per-map keys,
        because deriving them would mean walking forty-one keys on every step
        between maps.
        """
        key = f"visited_{map_id}"
        if int(c.achievement_counters.get(key, 0)):
            return False
        c.achievement_counters[key] = 1
        # Only a map the catalogue classifies counts towards a total. The
        # gauntlets are twenty-four copies of eight roads, and a player who ran
        # them would otherwise have walked most of "Nowhere Left" without
        # leaving the instances.
        classification = self.achievement_catalogue.map_class(map_id)
        if not classification:
            return True
        self.increment_achievement(c, "maps_visited")
        rollup = {"exterior": "exteriors_visited",
                  "interior": "interiors_visited",
                  "secrets": "secrets_visited"}.get(classification, "")
        if rollup:
            self.increment_achievement(c, rollup)
        return True

    async def award_achievements(self, session: Session | None) -> None:
        """Unlock everything this character has just qualified for.

        Eighty-odd dictionary lookups, called from the sites that already knew
        an event happened - chiefly `record_activity`, which every confirmed
        player event runs through. Cheap enough to run on each of them, which
        is the whole reason the requirements are all "one number against one
        threshold".
        """
        if session is None:
            return
        c = session.character
        if not c or not self.achievement_catalogue.entries:
            return
        earned = self.achievement_catalogue.newly_earned(
            self.achievement_progress(c), c.achievements)
        if not earned:
            return
        for entry in earned:
            c.achievements.add(entry.key)
            self.increment_achievement(c, "achievements_unlocked")
            await session.send(p.colored_text(
                f"Achievement unlocked: {entry.name} - {entry.description}",
                p.EL_COLOR_GREEN3))
            if entry.title:
                await session.send(p.colored_text(
                    f"You may now call yourself \"{entry.title}\". "
                    f"Wear it with #title {entry.title}.", 10))
            # The people standing next to them see it happen, which is most of
            # what an achievement is for.
            await self.broadcast_map(c.map_id, p.actor_overtext(
                c.actor_id, entry.name, color=4))
        self.db.save(c)
        await self.send_achievement_catalog(session)

    def achievement_catalog_rows(self, c: Character) -> list[tuple]:
        """(key, name, category, description, progress, threshold, done, title)."""
        return [(entry.key, entry.name, entry.category, entry.description,
                 progress, entry.threshold, done, entry.title)
                for entry, progress, done in self.achievement_catalogue.rows(
                    self.achievement_progress(c), c.achievements)]

    async def send_achievement_catalog(self, session: Session) -> None:
        c = session.character
        if (not c or not self.achievement_catalogue.entries
                or "achievements_catalog_v1" not in session.client_capabilities):
            return
        await session.send(p.achievements_catalog(
            self.achievement_catalog_rows(c), c.title))

    async def list_achievement_catalogue(self, session: Session) -> None:
        """`#achievements`, for a client that cannot decode the catalogue.

        Grouped by category and finished lines marked, because the whole point
        of a catalogue is that it can be read before any of it is earned.
        """
        c = session.character
        if not c:
            return
        catalogue = self.achievement_catalogue
        if not catalogue.entries:
            await session.send(p.raw_text("This world has no achievements."))
            return
        if "achievements_catalog_v1" in session.client_capabilities:
            await self.send_achievement_catalog(session)
            return
        rows = catalogue.rows(self.achievement_progress(c), c.achievements)
        done = sum(1 for _entry, _progress, finished in rows if finished)
        await session.send(p.raw_text(
            f"Achievements: {done} of {len(rows)}."))
        for category in catalogue.categories:
            await session.send(p.colored_text(category, 10))
            for entry, progress, finished in rows:
                if entry.category != category:
                    continue
                mark = "x" if finished else " "
                await session.send(p.raw_text(
                    f"  [{mark}] {entry.name} ({progress}/{entry.threshold})"
                    + (f" - grants \"{entry.title}\"" if entry.title else "")))

    async def list_titles(self, session: Session) -> None:
        c = session.character
        if not c:
            return
        titles = self.achievement_catalogue.titles_for(c.achievements)
        if not titles:
            await session.send(p.raw_text(
                "You have earned no titles yet. #achievements shows what grants one."))
            return
        await session.send(p.raw_text(
            "Titles you have earned: " + ", ".join(titles)))
        await session.send(p.raw_text(
            f"Wearing: {c.title}." if c.title else "Wearing none."))

    async def set_title(self, session: Session, wanted: str) -> None:
        """`#title <name>`, `#title none`.

        Only a title this character has earned may be worn, and the check is
        against the catalogue rather than against a free-text field: a title is
        a thing other people see, and one anybody could type would be worth
        nothing at all.
        """
        c = session.character
        if not c:
            return
        wanted = wanted.strip()
        if not wanted:
            await session.send(p.raw_text("Syntax: #title <name>, or #title none."))
            return
        if wanted.casefold() in {"none", "off", "clear"}:
            if not c.title:
                await session.send(p.raw_text("You are not wearing a title."))
                return
            c.title = ""
            self.db.save(c)
            await session.send(p.raw_text("You set your title aside."))
            await self.broadcast_title(c)
            await self.send_achievement_catalog(session)
            return
        chosen = self.achievement_catalogue.resolve_title(wanted, c.achievements)
        if not chosen:
            await session.send(p.raw_text(
                f"You have not earned the title \"{wanted}\". #titles lists yours."))
            return
        c.title = chosen
        self.db.save(c)
        await session.send(p.colored_text(f"{c.name} {chosen}.", 10))
        await self.broadcast_title(c)
        await self.send_achievement_catalog(session)

    async def broadcast_title(self, c: Character) -> None:
        """Tell everyone on this map what one player is calling themselves."""
        for viewer in list(self.sessions):
            if (viewer.character and viewer.character.map_id == c.map_id
                    and "actor_titles_v1" in viewer.client_capabilities):
                await viewer.send(p.actor_titles(((c.actor_id, c.title),)))

    async def send_actor_titles(self, session: Session) -> None:
        """Every title worn on this map, for a client that has just arrived.

        One packet for the whole map rather than one per player, and the
        player's own row is included: a window that shows what you are wearing
        should not have to remember it separately from what everyone else is.
        """
        c = session.character
        if not c or "actor_titles_v1" not in session.client_capabilities:
            return
        rows = [(other.character.actor_id, other.character.title)
                for other in self.sessions
                if other.character and other.character.map_id == c.map_id
                and other.character.title]
        if rows:
            await session.send(p.actor_titles(rows))

    async def list_achievements(self, session: Session) -> None:
        c = session.character
        if not c:
            return
        rows = self.achievement_rows(c)
        # Stored by key, shown by name: a catalogue achievement is kept as
        # `keeper_of_secrets` and a quest title as itself, and this is the one
        # place that difference has to stop being visible.
        finished = sorted(self.achievement_catalogue.display_name(name)
                          for name in c.achievements)
        if "achievements_window_v1" in session.client_capabilities:
            await session.send(p.achievements_state(rows, finished))
            return
        for label, value in rows:
            await session.send(p.raw_text(f"{label}: {value}"))
        if finished:
            await session.send(p.raw_text("Completed: " + ", ".join(finished)))

    async def buy_sigil(self, session: Session, name: str):
        c = session.character
        sid = SIGIL_IDS.get(name.casefold().strip())
        if not c or sid is None:
            raise ValueError("Unknown sigil name.")
        seller = next((record for record in self.npcs.values() if record[1] == c.map_id
                       and sid in record[3] and max(abs(c.x-record[0].x), abs(c.y-record[0].y)) <= 3), None)
        if not seller:
            raise ValueError("You must stand near the sigil merchant who sells that sigil.")
        if c.sigils & (1 << sid):
            raise ValueError("You already own that sigil.")
        price = seller[2]
        if c.inventory.get("Gold Coins", 0) < price:
            raise ValueError(f"You need {price} Gold Coins.")
        c.inventory["Gold Coins"] -= price
        if not c.inventory["Gold Coins"]:
            del c.inventory["Gold Coins"]
        c.sigils |= 1 << sid
        session.inventory_slots = self.sync_inventory_slots(c)
        self.db.save(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await session.send(p.sigils(c.sigils))
        await session.send(p.raw_text(f"Purchased the {name.title()} sigil."))

    def standard_spell_targets(
            self, session: Session, scope: str,
            target_id: int | None = None) -> list[Character | Animal]:
        caster = session.character
        if not caster:
            return []
        if scope == "self":
            return [caster]
        if scope == "allies":
            return [
                nearby.character for nearby in self.sessions
                if nearby.character and nearby.character.map_id == caster.map_id
                and max(abs(nearby.character.x-caster.x),
                        abs(nearby.character.y-caster.y)) <= 4
            ]
        if scope != "target" or target_id is None:
            return []
        animal = self.animals.get(target_id)
        if animal and animal.map_id == caster.map_id:
            return [animal]
        target_session = self.find_player_by_actor(target_id)
        if (target_session and target_session.character
                and target_session.character.map_id == caster.map_id):
            return [target_session.character]
        return []

    async def _standard_regeneration(
            self, target_session: Session, amount: int,
            duration: int, tick_seconds: int) -> None:
        target = target_session.character
        try:
            for _ in range(max(1, duration // tick_seconds)):
                await asyncio.sleep(tick_seconds)
                if not target or target.health <= 0:
                    return
                healed = min(amount, target.max_health - target.health)
                if healed:
                    target.health += healed
                    await self.broadcast_map(
                        target.map_id, p.actor_heal(target.actor_id, healed))
                    await target_session.send(stats_packet(target))
        except asyncio.CancelledError:
            raise
        finally:
            if target_session.regeneration_task is asyncio.current_task():
                target_session.regeneration_task = None

    async def broadcast_spell_visual(self, map_id: str, effect: int,
                                     actor_id: int, target_id: int | None,
                                     power: int, *, visual_effect: int | None = None) -> None:
        """Announce the resolved cast investment, gated per watching client."""
        legacy = p.special_effect(effect, actor_id, target_id)
        powered = p.special_effect(
            effect if visual_effect is None else visual_effect,
            actor_id, target_id, power=power)
        for recipient in list(self.sessions):
            if recipient.character and recipient.character.map_id == map_id:
                await self.deliver(
                    recipient, powered if "spell_visuals_v1" in recipient.client_capabilities
                    else legacy)

    @staticmethod
    def spell_visual_effect(spell_id: int) -> int:
        # Stable Godot presentation ids distinguish wards/poison from the
        # legacy ids reused by harvest and other unrelated announcements.
        return {0: 12, 1: 1, 3: 3, 4: 0, 6: 2, 7: 4, 10: 2,
                8: 19, 9: 18, 11: 3, 12: 9, 13: 5, 14: 10,
                15: 6, 16: 3, 17: 72, 18: 73, 19: 74,
                20: 2, 21: 12}.get(spell_id, 255)

    @staticmethod
    async def send_spell_visual_result(session: Session, status: int,
                                       spell_id: int, power: int,
                                       effect: int = 255) -> None:
        await session.send(p.spell_result(
            status, spell_id,
            power=power if "spell_visuals_v1" in session.client_capabilities else None,
            visual_effect=effect))

    async def cast_standard_spell(
            self, session: Session, effect: str, scope: str,
            target_id: int | tuple[int, int] | None = None) -> None:
        """Cast a command/hotkey spell through the shared scalable framework."""
        from .magic_book import SPELLS as book
        from .magic import normalize_spell_effect
        if not session.character:
            return
        canonical = normalize_spell_effect(effect)
        row = next((row for row in book.values() if row['effect'] == canonical and row['scope'] == scope), None)
        if row is not None:
            data = {"id": row['id'], "power": preferred_spell_power(session.character, canonical)}
            if scope in {"burst", "location"} and isinstance(target_id, tuple):
                data.update(x=target_id[0], y=target_id[1])
            elif target_id is not None:
                data['target_id'] = target_id
            return await self.cast_book_spell(session, data)
        caster = session.character
        archetype = spell_archetype(effect)
        if not caster:
            return
        scope = scope.casefold().strip()
        if scope not in archetype.target_scopes:
            allowed = ", ".join(archetype.target_scopes)
            raise ValueError(
                f"{effect.replace('_', ' ').title()} supports: {allowed}.")
        targets = self.standard_spell_targets(session, scope, target_id)
        if not targets:
            raise ValueError("No valid spell target was found.")
        if archetype.hostile:
            if len(targets) != 1 or targets[0] is caster:
                raise ValueError("Hostile spells require another target.")
            if (isinstance(targets[0], Character)
                    and not aggressive_player_magic_allowed(
                        caster, targets[0], 6)):
                raise ValueError(
                    "Aggressive magic can only target another player while "
                    "both players are in the same PK area.")
            mantled = next(
                (connected for connected in self.sessions
                 if connected.character is targets[0]
                 and self.has_buff(connected, BUFF_MAGIC_IMMUNITY)), None)
            if mantled is not None:
                # The spellbook's Null Mantle turns a spell-bar cast aside
                # exactly as it turns a sigil cast aside; a command route that
                # ignored it would be the way around it.
                raise ValueError(
                    f"{targets[0].name} is mantled against magic.")

        power = preferred_spell_power(caster, archetype.effect)
        mana, reagents = standard_spell_cost(
            caster, archetype.effect, power, self.spell_balance)
        # A focus: a secret room where the ether comes cheaper.
        mana = max(1, mana // self.area_multiplier(caster, CHEAP_MAGIC))
        if caster.ether < mana:
            raise ValueError(
                f"You need {mana} ethereal points for this power.")
        missing = []
        for item_id, quantity in reagents:
            item = ITEMS_BY_ID.get(item_id)
            if not item or caster.inventory.get(item.name, 0) < quantity:
                missing.append(
                    f"{quantity} {item.name if item else 'unknown reagent'}")
        if missing:
            raise ValueError("Missing reagents: " + ", ".join(missing))
        focus_name = active_focus(caster, archetype.effect)
        caster.ether -= mana
        for item_id, quantity in reagents:
            item = ITEMS_BY_ID[item_id]
            caster.inventory[item.name] -= quantity
            if caster.inventory[item.name] == 0:
                del caster.inventory[item.name]
            if modern := getattr(self, "modern", None):
                modern.record_economy(
                    "magic_reagent", caster.username,
                    item_name=item.name, quantity=quantity,
                    item_flow="sink",
                    metadata={"effect": archetype.effect,
                              "power": power, "scope": scope})

        if focus_name:
            await session.send(p.raw_text(
                f"{focus_name} consumed one Attunement Charge and replaced the anchor."))

        amount = standard_spell_amount(
            caster, archetype.effect, power, self.spell_balance)
        duration = standard_spell_duration(archetype.effect, power)
        visual_effect = {"heal": 1, "regeneration": 9, "harm": 2,
                         "poison": 0, "mana_drain": 10,
                         "life_drain": 2}.get(archetype.effect, 2 if archetype.hostile else 3)
        for target in targets:
            target_session = (
                next((connected for connected in self.sessions
                      if connected.character is target), None)
                if isinstance(target, Character) else None)
            if archetype.effect == "heal":
                healed = min(amount, target.max_health-target.health)
                target.health += healed
                await self.broadcast_map(
                    target.map_id, p.actor_heal(target.actor_id, healed))
            elif archetype.effect == "regeneration":
                if target_session:
                    if target_session.regeneration_task:
                        target_session.regeneration_task.cancel()
                    target_session.regeneration_task = asyncio.create_task(
                        self._standard_regeneration(
                            target_session, amount, duration,
                            archetype.tick_seconds))
                else:
                    healed = min(amount, target.max_health-target.health)
                    target.health += healed
                    await self.broadcast_map(
                        target.map_id, p.actor_heal(target.actor_id, healed))
            elif archetype.effect in {
                    "shield", "magic_protection", "heat_protection",
                    "cold_protection", "radiation_protection"}:
                buff_ids = {
                    "shield": 0, "magic_protection": 1,
                    "cold_protection": 23, "heat_protection": 24,
                    "radiation_protection": 25}
                if target_session:
                    buff_id = buff_ids[archetype.effect]
                    target_session.magic_buffs[buff_id] = (
                        time.monotonic() + duration)
                    target_session.magic_buff_powers[buff_id] = power
                    await target_session.send(
                        p.active_spell(buff_id, duration))
            elif archetype.effect in {"haste", "element_ward"}:
                # Swiftwend and Thriceward. Both set buffs rather than numbers,
                # and Thriceward sets three, which is what it is for.
                buff_ids = ((BUFF_HASTE,) if archetype.effect == "haste"
                            else (BUFF_COLD_PROTECTION, BUFF_HEAT_PROTECTION,
                                  BUFF_RADIATION_PROTECTION))
                if target_session:
                    for buff_id in buff_ids:
                        target_session.magic_buffs[buff_id] = (
                            time.monotonic() + duration)
                        target_session.magic_buff_powers[buff_id] = power
                        await target_session.send(
                            p.active_spell(buff_id, duration))
                    if archetype.effect == "haste":
                        await self.broadcast_map(
                            target.map_id,
                            p.actor_buffs(target.actor_id, BUFF_DOUBLE_SPEED))
            elif archetype.effect == "accuracy":
                target.temporary_combat["accuracy"] = (
                    target.temporary_combat.get("accuracy", 0) + amount)
            elif archetype.effect == "elemental_weapon":
                for key in ("heat_damage", "cold_damage",
                            "magic_damage", "radiation_damage"):
                    target.temporary_combat[key] = (
                        target.temporary_combat.get(key, 0) + amount)
            elif archetype.effect == "cripple":
                target.temporary_combat["evasion"] = (
                    target.temporary_combat.get("evasion", 0) - amount)
            elif archetype.effect.startswith("expose_"):
                key = archetype.effect.removeprefix("expose_") + "_protection"
                target.temporary_combat[key] = (
                    target.temporary_combat.get(key, 0) - amount)
            elif archetype.effect == "harm":
                damage = amount
                if target_session:
                    await self.damage_player(
                        target_session, damage, cause=caster.name)
                else:
                    target.health = max(1, target.health-damage)
                    await self.broadcast_map(
                        target.map_id,
                        p.actor_damage(target.actor_id, damage))
            elif archetype.effect == "poison":
                if target_session:
                    self.start_poison(target_session, amount)
                else:
                    target.health = max(1, target.health-amount)
                    await self.broadcast_map(
                        target.map_id,
                        p.actor_damage(target.actor_id, amount))

            await self.broadcast_spell_visual(
                caster.map_id, visual_effect, caster.actor_id,
                target.actor_id if target is not caster else None, power)

        caster.quest_state["magic_last_effect"] = archetype.effect
        magic_xp = int(max(1, amount * power)
                       * self.experience_multiplier("magic", caster))
        level_ups = award_magic_xp(caster, magic_xp)
        self.save_soon(caster)
        session.inventory_slots = self.sync_inventory_slots(caster)
        await session.send(p.inventory_packet(
            caster.inventory, ITEMS, caster.equipment,
            session.inventory_slots))
        await session.send(stats_packet(caster))
        await self.announce_levels(session, level_ups)
        await self.record_activity(session, ACTIVITY_SPELLS)
        await self.send_spell_visual_result(session, 1, 0, power, visual_effect)
        await session.send(p.raw_text(
            f"You cast {archetype.effect.replace('_', ' ').title()} "
            f"({scope}) at power {power}."))

    async def cast_spell(self, session: Session, sigils: tuple[int, ...], *,
                         power: int | None = None):
        c = session.character
        source_map = c.map_id if c else None
        token = session.coordinate_token() if session.coordinate_state is not None else None
        spell = self.spells.get(sigils)
        if spell and spell.spell_id == 9:
            self.require_coordinate_destination(session, *home.point(self, "beam", session))
        if spell and spell.effect:
            try:
                return await self.begin_book_spell(session, spell, power)
            except ValueError as exc:
                await session.send(p.raw_text(str(exc)))
                await session.send(p.spell_result(2, spell.spell_id))
                return

        if not c or not spell or any(not c.sigils & (1 << sid) for sid in sigils):
            await session.send(p.spell_result(3, 0)); return
        if self.area_multiplier(c, NO_MAGIC) > 1:
            # A null well: the wards here take the words out of your mouth.
            await session.send(p.raw_text(
                "The wards here take the words out of your mouth. Nothing answers."))
            await session.send(p.spell_result(2, spell.spell_id)); return
        effect = spell_effect(spell)
        if effect is not None:
            c.quest_state["magic_last_effect"] = effect
            try:
                if power is not None:
                    set_preferred_spell_power(c, effect, power)
                    await self.send_spell_power_state(session)
                spell = powered_spell(
                    spell, c, preferred_spell_power(c, effect),
                    self.spell_balance)
            except ValueError as exc:
                await session.send(p.raw_text(str(exc)))
                await session.send(p.spell_result(2, spell.spell_id))
                return
        problem = can_cast(c, spell)
        if problem:
            await session.send(p.raw_text(problem)); await session.send(p.spell_result(2, spell.spell_id)); return
        if not self.location_context_current(session, source_map, token):
            return
        if not spend_cast(c, spell):
            self.save_soon(c)
            await session.send(p.raw_text(f"You failed to cast {spell.name}."))
            await session.send(p.spell_result(2, spell.spell_id)); await session.send(stats_packet(c)); return
        if modern := getattr(self, "modern", None):
            for item_id, quantity in spell.reagents:
                item = ITEMS_BY_ID[item_id]
                modern.record_economy(
                    "magic_reagent", c.username,
                    item_name=item.name, quantity=quantity,
                    item_flow="sink",
                    metadata={"spell_id": spell.spell_id,
                              "spell": spell.name,
                              "power": spell.power})
        if spell.focus_name:
            await session.send(p.raw_text(
                f"{spell.focus_name} consumed one Attunement Charge and replaced the anchor."))
        if not self.location_context_current(session, source_map, token):
            return
        if spell.spell_id == 5:
            session.pending_spell = spell
            await self.send_spell_visual_result(
                session, 5, spell.spell_id, spell.power,
                self.spell_visual_effect(spell.spell_id))
            return
        # Farweave Mend, Venom Thread, Cinder Lance, Siphon Vitality, Sunder
        # Bond, Mindwell Draw and Rotbrand all want an actor named before they
        # do anything, so the cast is held until the client touches one.
        targeted = spell.spell_id in {1, 4, 6, 10, 13, 14, 18}
        if targeted:
            session.pending_spell = spell
            await self.send_spell_visual_result(
                session, 4, spell.spell_id, spell.power,
                self.spell_visual_effect(spell.spell_id))
        else:
            await self.apply_spell(session, spell, c)

    async def apply_spell(self, session: Session, spell: Spell, target):
        if spell.effect:
            import json
            return await self.magic_request(session, json.dumps({"op": "cast", "id": spell.spell_id,
                "power": spell.power, "target_id": target.actor_id}).encode())
        c = session.character
        if not c:
            return
        if (isinstance(target, Character)
                and not aggressive_player_magic_allowed(c, target, spell.spell_id)):
            await session.send(p.raw_text(
                "Aggressive magic can only target another player while both "
                "players are in the same PK area."))
            self.save_soon(c)
            session.inventory_slots = self.sync_inventory_slots(c)
            await session.send(p.inventory_packet(
                c.inventory, ITEMS, c.equipment, session.inventory_slots))
            await session.send(stats_packet(c))
            await session.send(p.spell_result(2, spell.spell_id))
            return
        target_session = (
            next((connected for connected in self.sessions
                  if connected.character is target), None)
            if isinstance(target, Character) else None)
        # Null Mantle. Aegis Veil raises resistance and lets the spell land for
        # less; this refuses it outright, which is the whole difference between
        # the two and the reason one costs sixty ether at level 68.
        if (spell.spell_id in AIMED_OFFENSIVE_SPELL_IDS
                and target_session is not None and target_session is not session
                and self.has_buff(target_session, BUFF_MAGIC_IMMUNITY)):
            await session.send(p.raw_text(
                f"{target.name} is mantled against magic; {spell.name} finds"
                " nothing to hold."))
            await target_session.send(p.raw_text(
                f"Your Null Mantle turned aside {c.name}'s {spell.name}."))
            self.save_soon(c)
            session.inventory_slots = self.sync_inventory_slots(c)
            await session.send(p.inventory_packet(
                c.inventory, ITEMS, c.equipment, session.inventory_slots))
            await session.send(stats_packet(c))
            await session.send(p.spell_result(2, spell.spell_id))
            return
        # Which magic attribute is being asked for depends on what the spell
        # does. One number used to serve both, which made a healer and a
        # battle mage the same build; splitting them is the point of having
        # two. A spell that harms reads Magic Offense, everything else -
        # heals, shields, restores - reads Magic Defense.
        offensive = spell.spell_id in OFFENSIVE_PLAYER_SPELL_IDS
        # Register 020. Two perks for the two halves of that split, so a
        # battle mage and a healer have a perk apiece rather than sharing one.
        caster_rationality = max(1, c.attributes[
            "magic_offense" if offensive else "magic_defense"] + (
                magic_offense_bonus(c) if offensive else magic_defense_bonus(c)))
        target_gear = equipment_stats(target.equipment)
        if isinstance(target, Character):
            # Whatever is coming, the target resists it with their defensive
            # magic; nobody shrugs off a curse by being good at casting one.
            target_rationality = max(
                1, target.attributes["magic_defense"] + magic_defense_bonus(target))
        else:
            # And a creature resists with the same attribute a player does.
            target_rationality = creature_magic_defense(
                self.creatures[target.creature_type])
        target_magic_resistance = int(target_gear["magic_resistance"])

        amount = 0
        if spell.spell_id == 0:
            amount = 10 * spell.power
        elif spell.spell_id == 7:
            amount = (2*c.skills["magic"] + 5*caster_rationality) * spell.power
        elif spell.spell_id == 1:
            amount = remote_heal_amount(
                c.skills["magic"], caster_rationality) * spell.power
        elif spell.spell_id == 12:
            # Wellspring heals deeper than Deep Renewal, and then does the two
            # things nothing else in the game does - see below.
            amount = (3*c.skills["magic"] + 6*caster_rationality) * spell.power
        if amount:
            healed = min(amount, target.max_health-target.health)
            target.health += healed
            await self.broadcast_actor(
                target, p.actor_heal(target.actor_id, healed))
        elif spell.spell_id == 4:
            damage = poison_damage(
                c.skills["magic"], caster_rationality, target_rationality,
                target_magic_resistance) * spell.power
            if target_session:
                self.start_poison(target_session, damage)
                await target_session.send(p.raw_text(
                    f"You have been poisoned by {c.name}."))
            elif isinstance(target, Animal):
                target.health = max(1, target.health-damage)
                await self.broadcast_actor(
                    target, p.actor_damage(target.actor_id, damage))
        elif spell.spell_id == 18:
            # Rotbrand: twice the dose Venom Thread carries, and it keeps
            # eating. A player takes it through the poison loop, which already
            # ticks every ten seconds and weakens on every third bite. A
            # creature has no poison of its own, so the rot runs as its own
            # task on the same cadence.
            damage = 2 * poison_damage(
                c.skills["magic"], caster_rationality, target_rationality,
                target_magic_resistance) * spell.power
            if target_session:
                self.start_poison(target_session, damage)
                await target_session.send(p.raw_text(
                    f"{c.name} has branded you with rot."))
            elif isinstance(target, Animal):
                self.start_creature_rot(target, damage)
        elif spell.spell_id == 6:
            damage = standard_spell_amount(
                c, "harm", spell.power, self.spell_balance)
            if target_session:
                await self.damage_player(target_session, damage, cause=c.name)
            elif isinstance(target, Animal):
                target.health = max(1, target.health-damage)
                await self.broadcast_actor(
                    target, p.actor_damage(target.actor_id, damage))
        elif spell.spell_id == 13:
            # Sunder Bond only has anything to tear at. It refuses a player, a
            # wild creature, and a summon of the caster's own - the reagents
            # are already spent by now, so it says which of the three it was.
            if not isinstance(target, Animal) or not target.summoned:
                await session.send(p.raw_text(
                    "Sunder Bond finds no binding there; it only touches a"
                    " summoned creature."))
            elif target.owner_id == c.actor_id:
                await session.send(p.raw_text(
                    "You will not unmake your own summons."))
            else:
                damage = 2 * standard_spell_amount(
                    c, "harm", spell.power, self.spell_balance)
                target.health = max(1, target.health-damage)
                await self.broadcast_actor(
                    target, p.actor_damage(target.actor_id, damage))
        elif spell.spell_id == 10:
            damage = life_drain_damage(
                c.skills["magic"], caster_rationality, target_rationality,
                target_magic_resistance) * spell.power
            damage = min(damage, target.health)
            target_died = False
            if target_session:
                target_died = await self.damage_player(
                    target_session, damage, cause=c.name)
            elif isinstance(target, Animal):
                target.health -= damage
                await self.broadcast_actor(
                    target, p.actor_damage(target.actor_id, damage))
            if not target_died:
                c.health = min(c.max_health, c.health+damage)
                await self.broadcast_actor(
                    c, p.actor_heal(c.actor_id, damage))
        elif spell.spell_id == 14 and isinstance(target, Character):
            moved = min(target.ether, mana_drain_amount(
                c.skills["magic"], caster_rationality, target_rationality,
                target_magic_resistance) * spell.power)
            target.ether -= moved
            c.ether = min(c.max_ether, c.ether+moved)
        elif spell.spell_id == 8:
            # Marrow Tithe. A night's bones are the one thing a fighter carries
            # out that nothing else wants; this is what pays for the reagents.
            bones = c.inventory.pop("Bones", 0)
            if bones:
                c.inventory["Gold Coins"] = c.inventory.get("Gold Coins", 0) + bones
                if modern := getattr(self, "modern", None):
                    modern.record_economy(
                        "spell_transmute", c.username, item_name="Gold Coins",
                        quantity=bones, item_flow="source",
                        metadata={"spell": spell.name, "power": spell.power})
                await session.send(p.raw_text(
                    f"The tithe renders {bones} Bones into {bones} Gold Coins."))
            else:
                await session.send(p.raw_text(
                    "You carry no bones for the tithe to render."))
        elif spell.spell_id == 16:
            # Glassgaze names who is standing veiled. The buff below is what
            # the client draws; this is what the spell is actually for.
            hidden = sorted(
                other.character.name for other in self.sessions
                if other is not session and other.character
                and other.character.map_id == c.map_id
                and max(abs(other.character.x-c.x),
                        abs(other.character.y-c.y)) <= GLASSGAZE_RADIUS
                and self.has_buff(other, BUFF_INVISIBLE))
            await session.send(p.raw_text(
                "Standing veiled nearby: " + ", ".join(hidden) if hidden
                else "Nobody nearby is standing veiled."))
        elif spell.spell_id == 19:
            # Thriceward sets all three elemental protections at once, which is
            # why it carries no single <buff> of its own.
            duration = 120 * spell.power
            for buff_id in (BUFF_COLD_PROTECTION, BUFF_HEAT_PROTECTION,
                            BUFF_RADIATION_PROTECTION):
                session.magic_buffs[buff_id] = time.monotonic() + duration
                session.magic_buff_powers[buff_id] = spell.power
                await session.send(p.active_spell(buff_id, duration))
        elif spell.spell_id == 20:
            # Ruinfall, the capstone: the only spell in the book that reaches
            # more than one thing. Like every other offensive spell here it
            # wounds rather than kills - a creature is left on one point and
            # the killing blow is still something a player has to land.
            damage = standard_spell_amount(
                c, "harm", spell.power, self.spell_balance)
            struck = 0
            for actor_id in list(self.animals_by_map.get(c.map_id, ())):
                animal = self.animals.get(actor_id)
                if (animal is None or not animal.alive
                        or (animal.summoned and animal.owner_id == c.actor_id)
                        or max(abs(animal.x-c.x),
                               abs(animal.y-c.y)) > SPELL_CIRCLE_RADIUS):
                    continue
                animal.health = max(1, animal.health-damage)
                struck += 1
                await self.broadcast_actor(
                    animal, p.actor_damage(animal.actor_id, damage))
            await session.send(p.raw_text(
                f"Ruin falls on {struck} creature(s) for {damage} each."
                if struck else "Ruin falls on empty ground."))
        elif spell.spell_id == 21:
            # Hearthcircle heals the people standing with you and the creatures
            # they have called up - one spell where Eternal Lands has two,
            # because a summoner in a fight wants both halves at once.
            healed_amount = max(10, c.skills["magic"]) * spell.power
            circle = [nearby for nearby in self.sessions
                      if nearby.character
                      and nearby.character.map_id == c.map_id
                      and max(abs(nearby.character.x-c.x),
                              abs(nearby.character.y-c.y))
                      <= SPELL_CIRCLE_RADIUS]
            owners = {nearby.character.actor_id for nearby in circle}
            for nearby in circle:
                other = nearby.character
                healed = min(healed_amount, other.max_health-other.health)
                other.health += healed
                await self.broadcast_actor(
                    other, p.actor_heal(other.actor_id, healed))
            for actor_id in list(self.animals_by_map.get(c.map_id, ())):
                animal = self.animals.get(actor_id)
                if (animal is None or not animal.alive or not animal.summoned
                        or animal.owner_id not in owners
                        or max(abs(animal.x-c.x),
                               abs(animal.y-c.y)) > SPELL_CIRCLE_RADIUS):
                    continue
                healed = min(healed_amount, animal.max_health-animal.health)
                animal.health += healed
                await self.broadcast_actor(
                    animal, p.actor_heal(animal.actor_id, healed))
        elif spell.spell_id == 9:
            # Gatecall. The long teleport: Blinkstep moves a mage fifteen
            # tiles, this brings them home from anywhere.
            await self.change_map(session, *home.point(self, "beam", session))
        if spell.spell_id == 12:
            # The other two thirds of Wellspring. Nothing else in the game
            # undoes a drained skill or cross attribute, and the poison purge
            # saves carrying an antidote for the one thing a mage can already
            # cure.
            self.stop_poison(session)
            restored = restore_drained_stats(c)
            await session.send(p.raw_text(
                f"The wellspring purges the poison and returns {restored}"
                " drained point(s)." if restored
                else "The wellspring purges what was working in you."))
        effect_by_spell = {0:12, 1:1, 3:3, 4:0, 6:2, 7:4, 8:19, 9:18,
                           10:2, 11:4, 12:9, 13:5, 14:10, 15:6, 16:8,
                           17:14, 18:2, 19:9, 20:17, 21:12}
        effect = effect_by_spell.get(spell.spell_id)
        if effect is not None:
            await self.broadcast_spell_visual(
                c.map_id, effect, c.actor_id,
                target.actor_id if effect in {0, 1, 2, 10} else None,
                spell.power, visual_effect=self.spell_visual_effect(spell.spell_id))
        if spell.buff is not None:
            durations = {0:128, 1:180, 3:90, 7:60, 11:30, 22:90,
                         23:120, 24:120, 25:150}
            duration = durations.get(spell.buff, 60) * spell.power
            session.magic_buffs[spell.buff] = time.monotonic() + duration
            session.magic_buff_powers[spell.buff] = spell.power
            await session.send(p.active_spell(spell.buff, duration))
            if spell.buff == BUFF_HASTE:
                # The client picks its running frames off the actor buff, the
                # same way Speed Hax does; `expire_buffs` clears it again.
                await self.broadcast_map(
                    c.map_id, p.actor_buffs(c.actor_id, BUFF_DOUBLE_SPEED))
        magic_xp = int(BASE_XP.get(spell.spell_id, 1) * spell.power
                       * self.experience_multiplier("magic", c))
        level_ups = award_magic_xp(c, magic_xp)
        self.save_soon(c)
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await session.send(p.partial_stats([(61, c.experience["magic"]),
                                            (55, c.experience["overall"])]))
        await self.announce_levels(session, level_ups)
        await session.send(stats_packet(c))
        await self.send_spell_visual_result(
            session, 1, spell.spell_id, spell.power, self.spell_visual_effect(spell.spell_id))
        await self.record_activity(session, ACTIVITY_SPELLS)
        await session.send(p.raw_text(
            f"You cast {spell.name} at power {spell.power}."))
        await self.walkthrough_event(session, "cast", spell.name)

    async def list_items(self, session: Session, query: str = ""):
        needle = query.casefold().strip()
        matched = [item for item in ITEMS.values()
                   if not needle or needle in item.name.casefold() or needle in str(item.item_id)]
        if not matched:
            await session.send(p.raw_text(f"No items match {query!r}.")); return
        current = None
        for item in sorted(matched, key=lambda value: (value.category.casefold(), value.name.casefold())):
            if item.category != current:
                current = item.category
                await session.send(p.colored_text(f"-- {current} --", 3))
            await session.send(p.raw_text(f"{item.item_id}: {item.name}"))
        await session.send(p.raw_text(f"Listed {len(matched)} item(s)."))

    def arm_report(self, c: Character) -> str:
        stats = equipment_stats(c.equipment)
        stats["accuracy"] = int(stats["accuracy"]) + c.temporary_combat.get("accuracy", 0)
        stats["defense"] = int(stats["defense"]) + c.temporary_combat.get("evasion", 0)
        stats["archery_ap"] = int(stats["archery_ap"]) + c.combat_bonuses.get("archery_ap", 0)
        labels = {
            "armor":"Armor", "damage":"Damage", "accuracy":"Accuracy", "defense":"Defense",
            "cold_damage":"Cold damage", "heat_damage":"Heat damage", "radiation_damage":"Radiation damage",
            "magic_damage":"Magic damage", "magic_resistance":"Magic Resistence",
            "magic_protection":"Magic Protection", "cold_protection":"Cold Protection",
            "heat_protection":"Heat Protection", "radiation_protection":"Radiation Protection",
            "critical_to_hit":"Critical to hit", "critical_to_damage":"Critical to damage",
            "light_modifier":"Light Modifier", "perception_bonus":"Perception Bonus",
            "missile_accuracy":"Missile accuracy", "archery_ap":"Archery AP",
            "missile_protection":"Missile protection", "max_health":"Maximum health",
            "max_ether":"Maximum ethereal points"}
        lines = []
        for key in ARMOR_STAT_KEYS:
            value = stats[key]
            shown = f"{value[0]}/{value[1]}" if isinstance(value, tuple) else str(value)
            lines.append(f"{labels[key]}: {shown}")
        return "\n".join(lines)

    async def food_loop(self):
        """Once a real minute: food, regeneration, reading and buff decay.

        This runs on real time whatever the game clock is doing. `#speed`
        moves the sky for a tester; it must not starve, heal or finish a book
        for anyone faster, so the per-player upkeep that used to ride the
        game-minute tick is kept apart from it.
        """
        while True:
            await asyncio.sleep(60)
            await self.player_minute()

    async def clock_loop(self):
        """Advance the game clock one minute per real minute times its speed.

        Progress through the current game minute is banked whenever the speed
        changes, so going from 1x to 60x half-way through a minute finishes that
        minute in half a real second rather than starting it again, and a
        `#set_clock` restarts the minute it names from the beginning.
        """
        self.clock_mark = time.monotonic()
        while True:
            wake = self._clock_wake_event()
            # Cleared before banking: a speed change that lands while a minute
            # is being broadcast sets it again, and the wait below returns at
            # once instead of sleeping out the old speed's interval.
            wake.clear()
            self._bank_clock_progress()
            while self.clock_progress >= 1.0:
                self.clock_progress -= 1.0
                await self.advance_clock()
            speed = self.clock_speed
            timeout = (None if speed <= 0
                       else (1.0 - self.clock_progress) * 60.0 / speed)
            try:
                await asyncio.wait_for(wake.wait(), timeout)
            except asyncio.TimeoutError:
                pass

    # Read with getattr: tests build worlds with object.__new__, and a world
    # nobody has touched runs its clock at the ordinary speed.
    clock_speed = 1.0
    clock_progress = 0.0
    clock_mark = 0.0
    # `#speed` ceiling: a whole six-hour game day each real minute. Faster
    # only means a NEW_MINUTE broadcast every few frames; `#set_clock` is the
    # way to get somewhere sooner.
    MAX_CLOCK_SPEED = 360.0

    def _clock_wake_event(self) -> asyncio.Event:
        wake = self.__dict__.get("_clock_wake")
        if wake is None:
            wake = self._clock_wake = asyncio.Event()
        return wake

    def _bank_clock_progress(self) -> None:
        now = time.monotonic()
        if self.clock_mark:
            self.clock_progress += (
                (now - self.clock_mark) * self.clock_speed / 60.0)
        self.clock_mark = now

    def set_clock_speed(self, speed: float) -> None:
        """Run the game clock at `speed` times its base rate (0 stops it).

        Only the clock: creatures, regeneration, food, cooldowns and every
        other real-time system keep their pace. Not saved - a forgotten 60x
        should not outlive a restart.
        """
        if not (math.isfinite(speed) and 0.0 <= speed <= self.MAX_CLOCK_SPEED):
            raise ValueError(
                f"Clock speed must be between 0 and {self.MAX_CLOCK_SPEED:g}.")
        self._bank_clock_progress()
        self.clock_speed = float(speed)
        self._clock_wake_event().set()

    async def set_game_clock(self, minute: int) -> None:
        """Jump the clock to `minute` of the day; the date does not change."""
        self.game_minute = int(minute) % 360
        self.clock_progress = 0.0
        self.clock_mark = time.monotonic()
        self._clock_wake_event().set()
        self.save_world_state()
        await self.broadcast(p.new_minute(self.game_minute))

    async def advance_minute(self):
        """One game minute and one real minute's upkeep together."""
        await self.advance_clock()
        await self.player_minute()

    async def advance_clock(self):
        previous_minute = self.game_minute
        self.game_minute = (self.game_minute + 1) % 360
        if previous_minute == 359:
            self.elapsed_days += 1
            # EL special days occupy one complete six-hour game day. Natural
            # special days are deliberately uncommon; stones and moderators
            # remain deterministic ways to select one.
            next_day = random.choice(ALL_SPECIAL_DAYS[1:]) if random.random() < 0.20 else ORDINARY
            await self.set_special_day(next_day)
            await self.turn_weather()
        self.save_world_state()
        await self.broadcast(p.new_minute(self.game_minute))

    async def player_minute(self):
        for session in list(self.sessions):
            c = session.character
            if not c:
                continue
            await self.sync_visible_npcs(session)
            had_positive_food = c.food > 0
            harvesting = (session.harvest_task is not None
                          and not session.harvest_task.done())
            below_level_harvesting = (
                harvesting
                and session.harvest_required_level is not None
                and c.skills["harvesting"] < session.harvest_required_level)
            active = (
                player_in_combat(session)
                or harvesting
                or (session.last_mix_at > 0.0
                    and time.monotonic() - session.last_mix_at <= 60.0))
            self.regenerate_action_points(c, active=active)
            c.food = max(-30, c.food - (random.randint(0, 5) if below_level_harvesting else 1))
            if c.food <= -30:
                await self.disable_speed_hax(session)
            if c.food < landing.LOW_FOOD:
                await landing_runtime.tip(self, session, "food_low")
            temporary_changed = False
            for values, actual in ((c.temporary_skills, c.skills),
                                   (c.temporary_attributes, c.attributes)):
                for key, value in list(values.items()):
                    step = 1 if value > 0 else -1
                    actual[key] -= step
                    values[key] -= step
                    if values[key] == 0:
                        del values[key]
                    temporary_changed = True
            for key, value in list(c.temporary_combat.items()):
                if key == "archery_ap":
                    continue
                value -= self.magic_modifier_amount(c, key)
                if value == 0:
                    continue
                c.temporary_combat[key] -= 1 if value > 0 else -1
                if c.temporary_combat[key] == 0:
                    del c.temporary_combat[key]
                temporary_changed = True
            if temporary_changed:
                refresh_derived_points(c)
            # The area multiplier and the perk stack: standing somewhere
            # restful and having trained for it are different reasons to heal
            # faster, and neither cancels the other.
            regeneration_multiplier = (self.area_multiplier(c, FAST_REGENERATION)
                                       * regeneration_multiplier_perk(c))
            if had_positive_food and c.health < c.max_health:
                base_health = max(1, (c.max_health * 2 + 99) // 100)
                amount = min(c.max_health - c.health,
                             max(1, int(base_health * regeneration_multiplier)))
                c.health += amount
                await self.broadcast_actor(
                    c, p.actor_heal(c.actor_id, amount))
            if had_positive_food and c.ether < c.max_ether:
                base_ether = max(1, (c.max_ether + 9) // 10)
                c.ether = min(c.max_ether,
                              c.ether + max(1, int(base_ether
                                                   * regeneration_multiplier)))
            if had_positive_food and c.reading_book:
                reading_rate = self.research_rate(c)
                c.reading_pages = max(0, c.reading_pages - reading_rate)
                if c.reading_pages == 0:
                    completed = c.reading_book
                    completed_index = c.reading_index
                    c.known_books.add(completed)
                    c.reading_book = ""
                    c.reading_total = 0
                    c.reading_index = 1024
                    if completed_index < 1024:
                        await session.send(p.new_knowledge(completed_index))
                    await session.send(p.colored_text(
                        f"You finished reading {completed}.", 10))
            self.save_soon(c)
            try:
                research_stats = ([(47, c.reading_index),
                                   (65, max(0, c.reading_total - c.reading_pages)),
                                   (66, min(c.reading_total, 0xFFFF))]
                                  if c.reading_book else [(47, 1024), (65, 0), (66, 0)])
                await session.send(p.partial_stats([(46, c.food), (44, c.ether)] + research_stats))
                await self.sync_visible_animals(session)
                if temporary_changed:
                    await self.send_stats(session, force=True)
            except (ConnectionError, asyncio.CancelledError):
                pass

    async def drop_inventory_item(self, session: Session, pos: int, quantity: int):
        c = session.character
        if c and not session.inventory_slots:
            session.inventory_slots = self.sync_inventory_slots(c)
        if not c or not 0 <= pos < len(session.inventory_slots):
            return
        name = session.inventory_slots[pos]
        if name is None or name not in c.inventory:
            return
        amount = min(max(0, quantity), c.inventory[name])
        instance_ids: list[int] = []
        if tracks_instances(name):
            amount = min(amount, 1)
            instance_id = c.inventory_instance_slots[pos]
            instance_ids = [instance_id] if instance_id else []
            if not instance_ids:
                return
        if not amount:
            return
        c.inventory[name] -= amount
        if c.inventory[name] == 0:
            del c.inventory[name]
            session.inventory_slots[pos] = None
            await session.send(p.inventory_remove(pos))
        else:
            item = ITEMS[name]
            await session.send(p.inventory_update(item.image_id, c.inventory[name], pos,
                                                   item.flags))
        await self.record_activity(session, ACTIVITY_DROPS, amount)
        bag_id = await self.drop_into_bag(
            c.x, c.y, [(name, amount)], c.map_id)
        # Handling a bag is a break from the node, both ways: putting
        # something down ends the harvest just as picking something up does.
        self.stop_harvesting(session)
        for instance_id in instance_ids:
            self.db.item_instances.transfer(
                instance_id, 1, "bag", str(bag_id),
                actor=c.username, source="player_drop")
        if modern := getattr(self, "modern", None):
            modern.record_economy(
                "player_drop", c.username, counterparty=f"bag:{bag_id}",
                item_name=name, quantity=amount,
                instance_id=(instance_ids[0] if instance_ids else None),
                gold_flow="none", item_flow="transfer")
        await session.send(stats_packet(c))
        self.db.save(c)

    @staticmethod
    def bag_wire_id(bag_id: int) -> int:
        """Return the stock client's one-byte, map-local bag identifier."""
        return bag_id % BAG_IDS_PER_MAP

    def resolve_bag_id(self, map_id: str, wire_id: int) -> int | None:
        return next((bag_id for bag_id in self.bags
                     if self.bag_maps.get(bag_id, "") == map_id
                     and self.bag_wire_id(bag_id) == wire_id), None)

    def create_tracked_bag_items(
            self, bag_id: int, items: list[tuple[str, int]], *,
            source: str, actor: str = "") -> None:
        for name, quantity in items:
            if not tracks_instances(name):
                continue
            for _ in range(quantity):
                self.db.item_instances.create(
                    name, 1, "bag", str(bag_id),
                    durability=100, max_durability=100,
                    source=source, actor=actor)

    async def drop_into_bag(self, x: int, y: int,
                            items: list[tuple[str, int]], map_id: str) -> int:
        """Put items on a tile, adding them to a bag already lying there.

        Anything that leaves items on the ground - a player's drop, a creature
        killed on a bag, a player dying on one - goes through here. Calling
        `create_bag` on an occupied tile made a second bag at the same spot,
        so a kill on top of a bag looked like it replaced the first one.
        """
        existing = next((bag_id for bag_id, (bag_x, bag_y, _)
                         in self.bags.items()
                         if (bag_x, bag_y) == (x, y)
                         and self.bag_maps.get(bag_id, "") == map_id), None)
        if existing is None:
            return await self.create_bag(x, y, list(items), map_id)
        drops = self.bags[existing][2]
        for name, amount in items:
            if amount <= 0:
                continue
            match = next((index for index, (item_name, item_quantity)
                          in enumerate(drops)
                          if item_quantity > 0 and item_name == name), None)
            if match is not None:
                drops[match] = (name, drops[match][1] + amount)
                continue
            free = next((index for index, (_, item_quantity)
                         in enumerate(drops) if item_quantity <= 0), None)
            if free is None:
                drops.append((name, amount))
            else:
                drops[free] = (name, amount)
        self.bag_activity[existing] = time.monotonic()
        await self.refresh_bag_viewers(existing)
        return existing

    async def create_bag(self, x: int, y: int, items: list[tuple[str, int]],
                         map_id: str) -> int:
        """Drop a bag on a map. The map is named, never assumed.

        `create_bag` records `bag_maps[bag_id]` below, so every bag has a map
        and the lookups elsewhere fall back only for a bag that has lost its
        entry. That fallback used to be the Eternal Lands start map, which
        this profile has no entry for: an orphan bag claimed to be somewhere
        that does not exist, and `== character.map_id` could match a player
        standing there. It is the empty string now, which is no map at all -
        no player is on it, so an orphan is invisible rather than misplaced.
        """
        used_wire_ids = {self.bag_wire_id(bag_id) for bag_id in self.bags
                         if self.bag_maps.get(bag_id, "") == map_id}
        bag_id = None
        for _ in range(MAX_BAGS):
            candidate = self.next_bag_id % MAX_BAGS
            self.next_bag_id += 1
            if (candidate not in self.bags
                    and self.bag_wire_id(candidate) not in used_wire_ids):
                bag_id = candidate
                break
        if bag_id is None:
            raise RuntimeError("No protocol-safe bag ID is available on this map")
        self.bags[bag_id] = (x, y, items)
        self.bag_maps[bag_id] = map_id
        self.bag_activity[bag_id] = time.monotonic()
        await self.broadcast_coordinates(map_id,
            lambda point: p.packet(p.GET_NEW_BAG,
                struct.pack("<HHB", *point(x, y), self.bag_wire_id(bag_id))))
        return bag_id

    async def expire_inactive_bags(self, now: float | None = None) -> None:
        automatic = now is None
        now = time.monotonic() if automatic else now
        if (automatic
                and now - self._last_bag_cleanup_at < BAG_CLEANUP_INTERVAL_SECONDS):
            return
        self._last_bag_cleanup_at = now
        expired = [bag_id for bag_id, changed_at in self.bag_activity.items()
                   if now - changed_at >= BAG_IDLE_TIMEOUT_SECONDS]
        for bag_id in expired:
            if bag_id not in self.bags:
                self.bag_activity.pop(bag_id, None)
                continue
            map_id = self.bag_maps.pop(bag_id, "")
            expired_instances = self.db.item_instances.owned("bag", str(bag_id))
            for item in expired_instances:
                self.db.item_instances.retire(
                    item.instance_id, actor="system", reason="bag_expired")
                if modern := getattr(self, "modern", None):
                    modern.record_economy(
                        "bag_expired", "system",
                        counterparty=f"bag:{bag_id}",
                        item_name=item.definition_name,
                        quantity=1, instance_id=item.instance_id,
                        gold_flow="none", item_flow="sink",
                        metadata={"map_id": map_id})
            del self.bags[bag_id]
            self.bag_activity.pop(bag_id, None)
            for viewer in self.sessions:
                if viewer.open_bag == bag_id:
                    viewer.open_bag = None
                    await viewer.send(p.packet(p.CLOSE_BAG))
                if viewer.pending_bag == bag_id:
                    viewer.pending_bag = None
            await self.broadcast_map(
                map_id,
                p.packet(p.DESTROY_BAG, bytes((self.bag_wire_id(bag_id),))))


    async def inspect_bag(
            self, session: Session, bag_id: int, *, post_combat: bool = False):
        c = session.character
        if not c:
            return
        if bag_id not in self.bags or self.bag_maps.get(bag_id, "") != c.map_id:
            bag_id = self.resolve_bag_id(c.map_id, bag_id)
        if bag_id is None:
            return
        x, y, _ = self.bags[bag_id]
        if not c:
            return
        if (c.x, c.y) != (x, y):
            session.pending_bag = bag_id
            current_task = asyncio.current_task()
            if (session.move_task and session.move_task is not current_task
                    and not session.move_task.done()):
                session.move_task.cancel()
            session.move_task = asyncio.create_task(self._move_and_open_bag(session, bag_id, x, y))
            if post_combat:
                session.post_combat_bag_task = session.move_task
            return
        await self._open_bag(session, bag_id)

    async def _move_and_open_bag(self, session: Session, bag_id: int, x: int, y: int):
        c = session.character
        task = asyncio.current_task()
        if not c:
            return
        try:
            await self.move(c, x, y)
        except asyncio.CancelledError:
            return
        finally:
            if session.post_combat_bag_task is task:
                session.post_combat_bag_task = None

    async def _open_bag(self, session: Session, bag_id: int):
        if bag_id not in self.bags:
            return
        session.open_bag = bag_id
        session.pending_bag = None
        entries = []
        for pos, (name, quantity) in enumerate(self.bags[bag_id][2]):
            if quantity > 0:
                entries.append(struct.pack(
                    "<HIB", ITEMS[name].image_id, quantity, pos))
        await session.send(p.packet(
            p.HERE_YOUR_GROUND_ITEMS,
            bytes((len(entries),)) + b"".join(entries)))

    async def refresh_bag_viewers(self, bag_id: int) -> None:
        if bag_id not in self.bags:
            return
        map_id = self.bag_maps.get(bag_id, "")
        for viewer in self.sessions:
            if (viewer.open_bag == bag_id and viewer.character
                    and viewer.character.map_id == map_id):
                await self._open_bag(viewer, bag_id)

    async def pick_up(self, session: Session, pos: int, quantity: int):
        c, bag_id = session.character, session.open_bag
        if not c or bag_id not in self.bags: return
        x, y, drops = self.bags[bag_id]
        if pos >= len(drops) or (c.x, c.y) != (x, y): return
        name, available = drops[pos]
        amount = min(quantity, available)
        # Clamp to what the character can actually hold, so a whole-stack
        # request (the client's Ctrl+click) delivers what fits instead of
        # refusing outright. The client already promises this: "the server
        # will leave anything that exceeds your free slots or load capacity
        # in the open bag."
        if name in ITEMS:
            emu = ITEMS[name].emu
            if emu > 0:
                free_load = carry_capacity(c) - self.carried_load(c)
                amount = min(amount, max(0, free_load // emu))
            free_slots = 36 - self.inventory_slot_usage(c.inventory)
            if tracks_instances(name):
                amount = min(amount, max(0, free_slots))
            elif name not in c.inventory and free_slots <= 0:
                amount = 0
        bag_instances = [
            item for item in self.db.item_instances.owned("bag", str(bag_id))
            if item.definition_name.casefold() == name.casefold()]
        if tracks_instances(name):
            amount = min(amount, len(bag_instances))
        if not amount or not self.add_inventory(
                c, name, amount, source="bag_pickup",
                create_instances=False):
            await session.send(p.raw_text("Your inventory is full.")); return
        # Taking something out of a bag ends the harvest, the same as
        # dropping into one; a refused pickup above leaves it running.
        self.stop_harvesting(session)
        moved_instance_ids = []
        for item in bag_instances[:amount]:
            moved_instance_ids.append(self.db.item_instances.transfer(
                item.instance_id, 1, "inventory", c.username,
                actor=c.username, source="bag_pickup"))
        if modern := getattr(self, "modern", None):
            modern.record_economy(
                "bag_pickup", c.username, counterparty=f"bag:{bag_id}",
                item_name=name, quantity=amount,
                instance_id=(moved_instance_ids[0] if moved_instance_ids else None),
                gold_flow="none", item_flow="transfer")
        remaining = available - amount
        # Clear an exhausted slot without retaining its item identity.  A later
        # drop can then claim this position regardless of item type.
        drops[pos] = (name, remaining) if remaining else ("", 0)
        session.inventory_slots = self.sync_inventory_slots(c)
        await session.send(p.inventory_packet(c.inventory, ITEMS, c.equipment, c.inventory_slots))
        await session.send(stats_packet(c))
        if any(qty for _, qty in drops):
            self.bag_activity[bag_id] = time.monotonic()
            await self.refresh_bag_viewers(bag_id)
        else:
            await self.walkthrough_event(session, "loot")
            del self.bags[bag_id]
            self.bag_activity.pop(bag_id, None)
            map_id = self.bag_maps.pop(bag_id, c.map_id)
            await self.broadcast_map(
                map_id,
                p.packet(p.DESTROY_BAG, bytes((self.bag_wire_id(bag_id),))))
            session.open_bag = None
            await session.send(p.packet(p.CLOSE_BAG))
        self.db.save(c)

    def attack_anchors(self, map_id: str, start: tuple[int, int],
                       shape: Footprint, target, occupied, *,
                       nearest: int, furthest: int) -> set[tuple[int, int]]:
        """Every anchor a body of `shape` could stand on and attack `target` from.

        A position is valid only if the body fits there - the ground carries
        it and nothing else is standing on it - and only if the two bodies
        would then be between `nearest` and `furthest` tiles apart, measured
        box to box. That is what makes "walk up to it and hit it" a route to
        somewhere rather than a step in the target's direction: something
        reachable only from one side has to be walked around, and something
        drawn over several tiles has no tile in its middle to walk to at all.

        Empty means there is nowhere to attack from, which is a real answer -
        a creature wedged in a doorway with the only approach tile occupied
        cannot be reached until whoever is standing there moves.
        """
        target_shape = footprint_of(target)
        # The widest anchor offset that can still satisfy that, per axis: any
        # wider and the boxes cannot come within reach however they are
        # placed. Measured body to body, so a large body stands off by its own
        # half-width while a small one still walks right up.
        span_x = furthest + max(shape.back_x + target_shape.forward_x,
                                shape.forward_x + target_shape.back_x)
        span_y = furthest + max(shape.back_y + target_shape.forward_y,
                                shape.forward_y + target_shape.back_y)
        return {
            (target.x + dx, target.y + dy)
            for dy in range(-span_y, span_y + 1)
            for dx in range(-span_x, span_x + 1)
            if nearest <= box_distance(target.x + dx, target.y + dy, shape,
                                       target.x, target.y, target_shape) <= furthest
            and not self.anchor_blocked(
                occupied, target.x + dx, target.y + dy, shape, start)
            and self.is_walkable(map_id, target.x + dx, target.y + dy, shape)
        }

    def invasion_pursuit_step(self, animal: Animal, target: Character,
                                occupied: set[tuple[int, int]]) -> tuple[int, int] | None:
        """Return a direct step or consume a short cached route around obstacles."""
        start = (animal.x, animal.y)
        target_id = getattr(target, "actor_id", None)
        shape = footprint_of(animal)
        target_shape = footprint_of(target)
        # The band of anchors this creature could attack the target from.
        #
        # A melee creature wants the ring of tiles touching the target's body:
        # `nearest` and `furthest` are both one, and one means contact. A
        # creature with reach wants the far edge of a wider band and nothing
        # nearer: walking to the closest tile it could shoot from is walking
        # into melee, which is the one place a shooter must not end up.
        # Setting the near edge is also what gives the route somewhere to go -
        # with the whole band admissible a creature already inside it is
        # already at its destination, and would never path around a wall.
        furthest = self.strike_distance_against(animal, target)
        nearest = max(1, min(self.creature_holds_distance(animal), furthest))
        attack_positions = self.attack_anchors(
            animal.map_id, start, shape, target, occupied,
            nearest=nearest, furthest=furthest)
        if not attack_positions:
            animal.pursuit_path.clear()
            return None

        dx = (target.x > animal.x) - (target.x < animal.x)
        dy = (target.y > animal.y) - (target.y < animal.y)
        direct = animal.x + dx, animal.y + dy
        # A step straight at the target is the cheap answer, but for a
        # creature holding a distance it is the wrong one once that step
        # would take it inside the band it is trying to stay on.
        closes_too_far = box_distance(direct[0], direct[1], shape,
                                      target.x, target.y, target_shape) < nearest
        if (not closes_too_far
                and not self.anchor_blocked(occupied, *direct, shape, start)
                and self.can_walk_step(animal.map_id, start, direct, shape)
                and (not dx or not dy
                     or (self.can_walk_step(
                            animal.map_id, start, (animal.x + dx, animal.y), shape)
                         and self.can_walk_step(
                            animal.map_id, start, (animal.x, animal.y + dy), shape)))):
            animal.pursuit_path.clear()
            animal.pursuit_target_id = target_id
            animal.pursuit_target_x, animal.pursuit_target_y = target.x, target.y
            return dx, dy

        target_moved = (
            animal.pursuit_target_id != target_id
            or max(abs(target.x - animal.pursuit_target_x),
                   abs(target.y - animal.pursuit_target_y)) > 2
        )
        if target_moved:
            animal.pursuit_path.clear()

        if animal.pursuit_path:
            nxt = animal.pursuit_path[0]
            cached_dx, cached_dy = nxt[0] - animal.x, nxt[1] - animal.y
            cached_valid = (
                (cached_dx, cached_dy) in DIRS
                and not self.anchor_blocked(occupied, *nxt, shape, start)
                and self.can_walk_step(animal.map_id, start, nxt, shape)
                and (not cached_dx or not cached_dy
                     or (self.can_walk_step(
                            animal.map_id, start,
                            (animal.x + cached_dx, animal.y), shape)
                         and self.can_walk_step(
                            animal.map_id, start,
                            (animal.x, animal.y + cached_dy), shape)))
            )
            if cached_valid:
                animal.pursuit_path.pop(0)
                return cached_dx, cached_dy
            animal.pursuit_path.clear()

        if not self.spend_path_budget():
            return None
        max_steps = self.settings.invasion_max_path_length
        path = self.find_path_to_any(
            animal.map_id, start, attack_positions,
            self.blocked_anchors(occupied, start, shape, max_steps),
            max_steps, shape)
        if not path:
            return None
        animal.pursuit_target_id = target_id
        animal.pursuit_target_x, animal.pursuit_target_y = target.x, target.y
        # Cache only a short runway so moving targets remain responsive.
        animal.pursuit_path = path[:8]
        nxt = animal.pursuit_path.pop(0)
        return nxt[0] - animal.x, nxt[1] - animal.y

    def ranged_hold_target(self, animal: Animal, ordered_targets: list,
                           ) -> tuple[object | None, int]:
        """The player a creature with reach is shooting at, and how far off.

        A shooter commits. Re-picking the nearest player every tick is what
        melee creatures do and it is fine for them, because closing on the
        nearest is the same thing as fighting it - but a creature that holds
        its ground would swap targets every time somebody walked past, and
        never finish anyone.

        So it keeps the player it has until one of the three things that
        should break that hold: the player leaves its pursuit radius, the
        player is gone or dead, or somebody else shoots it - which the caller
        has already turned into a retaliation target and passes in first.

        Returns the target and the gap to it, measured body to body.
        """
        by_actor = {candidate.character.actor_id: candidate
                    for candidate in ordered_targets}
        held = by_actor.get(animal.held_target_id) if animal.held_target_id else None
        reach = self.creature_pursuit_distance(animal)
        # Being hit breaks the hold. `ranged_candidates` has already put
        # the attacker first, so the hold only survives if it is already
        # on them - which is the common case, since the player a shooter
        # is shooting is usually the one shooting back.
        provoked_by = animal.ranged_aggressor_id
        if (provoked_by and provoked_by != animal.held_target_id
                and provoked_by in by_actor):
            held = by_actor[provoked_by]
            animal.held_target_id = provoked_by
        if held is not None:
            gap = actor_distance(animal, held.character)
            if gap <= reach and held.character.health > 0:
                return held, gap
        # The hold is broken. `ordered_targets` is nearest-first, so the next
        # one to take is simply the first still inside the radius.
        for candidate in ordered_targets:
            gap = actor_distance(animal, candidate.character)
            if gap <= reach and candidate.character.health > 0:
                animal.held_target_id = candidate.character.actor_id
                return candidate, gap
        animal.held_target_id = None
        return None, 0

    def ranged_step(self, animal: Animal, target, occupied,
                    gap: int, now: float) -> tuple[int, int] | None:
        """One step of a shooter's footwork, or None to stand and fire.

        Three stances, and which one it is comes from the gap alone:

        * further than it can shoot - close, by the ordinary routed pursuit,
          because getting there may mean going around something;
        * nearer than it wants to be, or backing off from a melee hit - open
          the range, one step directly away and two fallbacks either side of
          that, because a creature retreating into a corner should try the
          corner's edges before giving up;
        * where it wants to be - hold, and let the combat loop shoot.

        Retreating is deliberately not routed. A* away from something has no
        destination to aim at, and a shooter that pathfinds backwards round a
        building reads as fleeing rather than as keeping its distance.
        """
        reach = self.strike_distance_against(animal, target)
        # A shooter pulled in by Closer cannot hold further out than it can
        # shoot from, or it would back away and never fire again.
        hold = min(self.creature_holds_distance(animal), reach)
        if gap > reach:
            return self.invasion_pursuit_step(animal, target, occupied)
        recoiling = now < animal.melee_recoil_until
        if gap >= hold and not recoiling:
            return None
        # Directly away from the target, then the two steps either side of it.
        dx = (animal.x > target.x) - (animal.x < target.x)
        dy = (animal.y > target.y) - (animal.y < target.y)
        if (dx, dy) == (0, 0):
            # Standing on it, which should not happen, but a creature with no
            # opinion about which way is away has to pick one.
            dx, dy = random.choice(DIR_CHOICES)
        shape = footprint_of(animal)
        here = (animal.x, animal.y)
        mask = self.step_mask_at(animal.map_id, animal.x, animal.y, shape)
        for sx, sy in ((dx, dy), (dx, 0), (0, dy)):
            if (sx, sy) == (0, 0):
                continue
            if self.anchor_blocked(occupied, animal.x + sx, animal.y + sy,
                                   shape, here):
                continue
            if self.step_allowed(animal.map_id, animal.x, animal.y,
                                 sx, sy, mask, shape):
                return sx, sy
        # Cornered. Standing and shooting is a better answer than shuffling
        # into the wall it is already against.
        return None

    def ranged_candidates(self, animal: Animal, player_cells: dict) -> list:
        """Players a shooter could take, nearest first, its attacker first.

        Two lists really, in one. The bulk is whoever it would pick a fight
        with unprompted, which is the same aggression test every other
        creature applies. In front of that goes whoever last hit it, distance
        and temperament notwithstanding: being attacked is one of the two
        things that breaks a shooter's hold on its current target, and a
        creature that would not have started the fight still finishes it.
        """
        definition = self.creatures.get(animal.creature_type)
        if definition is None:
            return []
        nearby = self.sessions_near(player_cells.get(animal.map_id, {}),
                                    animal.x, animal.y,
                                    self.creature_pursuit_distance(animal))
        found = []
        for candidate in nearby:
            character = candidate.character
            if character is None or character.health <= 0 or candidate.demigod:
                continue
            # Duskveil. A creature choosing whom to start on does not see a
            # veiled player; one already fighting them keeps fighting, because
            # this list is only ever consulted to begin a fight.
            if self.has_buff(candidate, BUFF_INVISIBLE):
                continue
            if creature_attacks_player(
                    definition,
                    attack=character.skills["attack"],
                    defense=character.skills["defense"],
                    might=character.attributes["might"],
                    toughness=character.attributes["toughness"]):
                found.append(candidate)
        aggressor = animal.ranged_aggressor_id
        if aggressor:
            provoked = next((candidate for candidate in nearby
                             if candidate.character is not None
                             and candidate.character.actor_id == aggressor
                             and candidate.character.health > 0), None)
            if provoked is not None:
                found = [provoked] + [c for c in found if c is not provoked]
        return found

    async def ranged_creature_tick(self, animal: Animal, now: float,
                                   candidates: list, occupied,
                                   movement_commands: dict) -> None:
        """One tick of a creature that fights at a distance.

        Shooters are handled apart from the melee AI rather than threaded
        through it, for one reason above all others: a creature in combat does
        not move. That is right for something that stands and swings, and it
        is precisely wrong here - a shooter's footwork *is* its fight, and a
        kiter that froze the moment it opened fire would be a melee creature
        with a longer arm.

        Three things happen, in this order, because each depends on the last:
        hold or reacquire a target, shoot it if it is in reach, then take a
        step to stay at the range it wants. Shooting does not consume the
        step: backing away while firing is the whole behaviour.
        """
        target, gap = self.ranged_hold_target(animal, candidates)
        if target is None:
            return
        character = target.character
        if actor_distance(animal, character) <= STOP_MOVING_DISTANCE:
            await self.stop_moving_attack_target(animal, character, target)
        # Open fire. `invasion_attack` holds the combat lock and runs its own
        # round timer, so this only ever starts a fight that is not already
        # running; the footwork below carries on underneath it.
        if gap <= self.strike_distance_against(animal, character):
            if animal.actor_id not in self.combatants:
                asyncio.create_task(self.invasion_attack(animal, target))
        if now < animal.next_move_at:
            return
        step_seconds = self.settings.normal_move_interval_ms / 1000.0
        animal.next_move_at = now + step_seconds
        step = self.ranged_step(animal, character, occupied, gap, now)
        if step is None:
            return
        dx, dy = step
        animal.next_move_at += diagonal_step_hold(step_seconds, dx, dy)
        shape = footprint_of(animal)
        nx, ny = animal.x + dx, animal.y + dy
        for tile in shape.tiles(animal.x, animal.y):
            occupied.discard(tile)
        for tile in shape.tiles(nx, ny):
            occupied.add(tile)
        animal.x, animal.y = nx, ny
        animal.rotation = facing_rotation(dx, dy)
        animal.last_moved_at = now
        self.record_actor_move(animal.actor_id, now)
        # Into the tick's batch, the same as every other creature step:
        # movement goes out per map at the end of the tick, and a shooter
        # broadcasting its own would be a second, unbatched path.
        movement_commands.setdefault(
            animal.map_id, {})[animal.actor_id] = DIRS[(dx, dy)]
        # Having opened the range, it is no longer backing off.
        if actor_distance(animal, character) >= self.creature_holds_distance(animal):
            animal.melee_recoil_until = 0.0

    def march_step(self, animal: Animal,
                   occupied: set[tuple[int, int]]) -> tuple[int, int] | None:
        """Return one routed step of a #send_spawn march, or None when done."""
        target = animal.march_target
        if target is None:
            return None
        if max(abs(target[0] - animal.x),
               abs(target[1] - animal.y)) <= self.settings.invasion_wander_radius:
            # Arrived: the group wanders around its relocated anchor again.
            animal.march_target = None
            return None
        start = (animal.x, animal.y)
        if not self.spend_path_budget():
            return None
        shape = footprint_of(animal)
        max_steps = self.settings.invasion_max_path_length
        path = self.find_path_to_any(
            animal.map_id, start, {target},
            self.blocked_anchors(occupied, start, shape, max_steps),
            max_steps, shape)
        if not path:
            # Out of routing range or blocked: the leash step below still
            # walks the creature toward the relocated anchor.
            return None
        return path[0][0] - animal.x, path[0][1] - animal.y

    def leash_home_step(self, animal: Animal, occupied: set[tuple[int, int]],
                        now: float) -> tuple[int, int] | None:
        """One routed step back toward a wild creature's leash, or None.

        A creature outside its `leash:N` - a chase took it there - used to
        walk straight home, and a wall or a shore wider than its few detours
        across that line held it against the obstacle for good. This routes
        it instead: one bounded A* to the square ring the leash draws round
        the spawn, which every way back inside has to cross. A creature
        further out than a search reaches aims at a nearer ring, half a
        search closer, so each search stays short and each step still closes
        on home. None when the creature is inside its leash, when this tick's
        search allowance is spent, or while it waits after finding no route;
        the caller then takes the greedy step home.
        """
        if now < animal.leash_route_retry_at:
            return None
        radius = animal.wander_radius
        sx, sy = animal.spawn_x, animal.spawn_y
        x, y = animal.x, animal.y
        excursion = max(abs(x - sx), abs(y - sy))
        if excursion <= radius:
            return None
        max_steps = self.settings.invasion_max_path_length
        ring = max(radius, excursion - max(1, max_steps // 2))
        # Only the ring's tiles a bounded search could reach at all: the
        # whole ring of a far creature is thousands of tiles.
        low_x, high_x = max(sx - ring, x - max_steps), min(sx + ring, x + max_steps)
        low_y, high_y = max(sy - ring, y - max_steps), min(sy + ring, y + max_steps)
        targets: set[tuple[int, int]] = set()
        for edge_x in (sx - ring, sx + ring):
            if abs(edge_x - x) <= max_steps:
                targets.update((edge_x, ty) for ty in range(low_y, high_y + 1))
        for edge_y in (sy - ring, sy + ring):
            if abs(edge_y - y) <= max_steps:
                targets.update((tx, edge_y) for tx in range(low_x, high_x + 1))
        if not targets or not self.spend_path_budget():
            return None
        start = (x, y)
        shape = footprint_of(animal)
        path = self.find_path_to_any(
            animal.map_id, start, targets,
            self.blocked_anchors(occupied, start, shape, max_steps),
            max_steps, shape)
        if not path:
            animal.leash_route_retry_at = now + LEASH_ROUTE_RETRY_SECONDS
            return None
        return path[0][0] - x, path[0][1] - y

    def return_to_leash(self, animal: Animal,
                        occupied: set[tuple[int, int]], now: float) -> bool:
        """Put a creature stranded outside its leash back at its spawn, unseen.

        The last resort behind leash_home_step, for a way home no bounded
        search can find. Only while no client shows the creature, so nobody
        sees it vanish; a watched one keeps trying and is returned once it is
        out of sight. The tile is the one a respawn would give it. True when
        it moved.
        """
        if self.animal_viewers.get(animal.actor_id):
            return False
        shape = footprint_of(animal)
        try:
            x, y = self.free_creature_tile(
                animal.map_id, animal.spawn_x, animal.spawn_y, shape)
        except NoFreeCreatureTile:
            return False
        for tile in shape.tiles(animal.x, animal.y):
            occupied.discard(tile)
        for tile in shape.tiles(x, y):
            occupied.add(tile)
        animal.x, animal.y = x, y
        animal.wander_steps_remaining = 0
        animal.leash_outside_since = 0.0
        if max(abs(x - animal.spawn_x), abs(y - animal.spawn_y)) > animal.wander_radius:
            # Nothing walkable inside the leash at all (a row stood in water):
            # the respawn tile is as close as it can get. Stop searching for
            # a way in that does not exist, and ask again only rarely.
            animal.leash_outside_since = now
            animal.leash_route_retry_at = now + LEASH_STRANDED_SECONDS
        self.invalidate_creature_index(animal.map_id)
        return True

    async def animal_loop(self):
        """Random wandering plus hostile invasion pursuit and attacks."""
        tick = 0
        while True:
            # Poll frequently for path and combat decisions. Each invasion
            # actor is independently rate-limited below to its animation cycle.
            await asyncio.sleep(self.settings.invasion_ai_tick_ms / 1000.0)
            tick += 1
            # Zero unless ELORIA_METRICS is on, and the truth test below is
            # what decides whether anything is recorded: the load harness has
            # to be able to measure a server nobody built specially for it.
            tick_started = time.perf_counter() if metrics.ENABLED else 0.0
            now = time.monotonic()
            if now - self._last_upkeep_at >= UPKEEP_INTERVAL_SECONDS:
                self._last_upkeep_at = now
                await self.process_spawn_groups(now=now)
                await bell.tick(self)
                await sky.tick(self)
                # No argument: the bag sweep keeps its own automatic interval.
                await self.expire_inactive_bags()
                await self.process_territory_raid()
            # One pass over the world's creatures, as before, plus a note of
            # which maps hold one and which of those hold something that has
            # to keep thinking whether or not a player is standing there.
            # `living` is filtered to the awake maps below, in this order: the
            # tick's shared occupancy set and its A* allowance are order
            # sensitive, so a map that is awake has to be walked in exactly
            # the sequence it always was.
            alive_actors: list[Animal] = []
            holding: set[str] = set()
            self_driven: set[str] = set()
            for animal in self.animals.values():
                if not animal.alive:
                    continue
                alive_actors.append(animal)
                map_id = animal.map_id
                if map_id not in holding:
                    holding.add(map_id)
                if (map_id not in self_driven
                        and (animal.invasion or animal.summoned
                             or animal.instance_name)):
                    self_driven.add(map_id)
            if not alive_actors:
                if tick_started:
                    self._record_tick(tick_started, 0, 0)
                continue
            movement_commands: dict[str, dict[int, int]] = {}
            # Re-read the clock: the upkeep above may have taken a moment, and
            # every movement deadline below is compared against this.
            now = time.monotonic()
            self._creature_index.clear()
            self._index_pinned = True
            # A* is the most expensive thing a creature can ask for - a single
            # 36-tile search costs about half a tick, and an unreachable target
            # costs more than a whole one. Cap how many run per tick so one
            # crowded corner cannot stall every other actor on the server.
            self._path_budget = PATH_SEARCHES_PER_TICK
            self._path_deadline = now + (
                self.settings.invasion_ai_tick_ms / 1000.0 * PATH_TICK_FRACTION)
            occupied_by_map: dict[str, set[tuple[int, int]]] = {}

            def occupied_for(map_id: str) -> set[tuple[int, int]]:
                """Occupied tiles for one map, computed once per tick on demand.

                Building this for every populated map up front spent most of
                its time on maps no creature went on to consult.
                """
                occupied = occupied_by_map.get(map_id)
                if occupied is None:
                    occupied = self.creature_occupied_tiles(map_id)
                    occupied_by_map[map_id] = occupied
                return occupied

            players_by_map: dict[str, list[Session]] = defaultdict(list)
            players_by_actor: dict[int, Character] = {}
            for connected in self.sessions:
                if connected.character:
                    players_by_map[connected.character.map_id].append(connected)
                    players_by_actor[connected.character.actor_id] = connected.character
            # Creatures only ever look for players inside their pursuit radius,
            # so bucket the players once per map instead of having every
            # creature sort the entire population of its map.
            player_cells = {map_id: self.index_sessions(sessions)
                            for map_id, sessions in players_by_map.items()}
            # Twenty-five of the served maps hold wildlife and at most a
            # handful of them hold a player. Walking the rest moves creatures
            # nobody is told about, in a world that will have moved them
            # somewhere else again by the time anybody arrives.
            awake = self.awake_maps(players_by_map, self_driven)
            # When everything holding a creature is awake this is the list the
            # loop has always had, object for object and in the same order.
            living = (alive_actors if holding <= awake else
                      [animal for animal in alive_actors
                       if animal.map_id in awake])
            # A creature reaches a player to pursue it, and stops a moving one
            # slightly sooner; the query radius has to cover both.
            pursuit_reach = max(self.settings.invasion_pursuit_distance,
                                STOP_MOVING_DISTANCE)
            eligible_cache: dict[tuple[str, str | None], list[Session]] = {}

            def eligible_on_map(map_id: str, raid_team) -> list[Session]:
                """Players on a map a creature of this raid team may pursue."""
                key = (map_id, raid_team)
                found = eligible_cache.get(key)
                if found is None:
                    found = [
                        target for target in players_by_map.get(map_id, ())
                        if not target.demigod and not sky.bot(target.character) and not getattr(target.character,"_road_bot",False)
                        and (not raid_team or (
                            self.territory_raids.team_for(
                                target.character.username)
                            not in {None, raid_team}))]
                    eligible_cache[key] = found
                return found

            for animal in living:
                pursuing = False
                # The pace this creature reserved its movement slot at, so the
                # step it settles on can be held for as far as it travels.
                step_seconds = 0.0
                if (animal.summoned
                        and now >= animal.next_summon_decay_at):
                    animal.next_summon_decay_at = (
                        now + SUMMON_DECAY_INTERVAL_SECONDS)
                    decay = min(
                        animal.health,
                        summon_decay_damage(
                            players_by_actor.get(animal.owner_id)))
                    animal.health -= decay
                    decay_owner=self.find_player_by_actor(animal.owner_id)
                    if decay_owner: roads.emit(self,decay_owner,"decay",amount=decay)
                    await self.broadcast_map(
                        animal.map_id,
                        p.actor_damage(animal.actor_id, decay))
                    if animal.health <= 0:
                        animal.alive = False
                        await self.broadcast_map(
                            animal.map_id,
                            p.actor_command(animal.actor_id, p.CMD_DIE1))
                        asyncio.create_task(
                            self._remove_dead_invasion(animal))
                        continue
                if now < animal.frozen_until:
                    continue
                # A creature that fights at a distance is handled apart from
                # everything below, and before the combat lock rather than
                # after it. Both are deliberate. The melee AI closes on a
                # target and then stands still to swing, which is right for a
                # creature whose fight is its reach; for a shooter the
                # footwork *is* the fight, and freezing it the moment it opens
                # fire would make it a melee creature with a longer arm.
                #
                # Exactly one creature in the shipped profile takes this
                # branch - the feral sporefolk - so no existing creature's
                # behaviour passes through here.
                ranged_definition = self.creatures.get(animal.creature_type)
                if ranged_definition is not None and ranged_definition.is_ranged:
                    await self.ranged_creature_tick(
                        animal, now,
                        self.ranged_candidates(animal, player_cells),
                        occupied_for(animal.map_id), movement_commands)
                    continue
                if animal.actor_id in self.combatants:
                    continue
                if animal.invasion or animal.summoned:
                    interval = (
                        self.settings.summon_move_interval_ms
                        if animal.summoned
                        else self.settings.invasion_move_interval_ms
                    ) / 1000.0
                    lead = self.settings.invasion_move_lead_ms / 1000.0
                    if not invasion_movement_due(
                            now, animal.next_move_at, interval, lead):
                        continue
                    # Reserve exactly one animation slot before making the AI
                    # decision. Missed deadlines are skipped, never replayed.
                    animal.next_move_at = next_invasion_movement_at(
                        now, animal.next_move_at, interval)
                    step_seconds = interval
                ranged_target = None
                if animal.ranged_aggressor_id is not None:
                    # Only worth searching when this creature actually has a
                    # ranged aggressor. Running it unconditionally scanned the
                    # whole map's player list once per creature per tick just
                    # to return None for almost every one of them.
                    ranged_target = next((
                        target for target in players_by_map.get(animal.map_id, ())
                        if target.character.actor_id == animal.ranged_aggressor_id
                        and not target.demigod), None)
                    if ranged_target is None:
                        animal.ranged_aggressor_id = None
                regular_targets = []
                if not animal.invasion and not animal.summoned:
                    definition = self.creatures[animal.creature_type]
                    # Only players inside the pursuit radius can ever be
                    # engaged; anyone further away is filtered out again by the
                    # distance break below. Asking the index for the handful
                    # nearby avoids testing every player on the map.
                    regular_targets = [
                        target for target in self.sessions_near(
                            player_cells.get(animal.map_id, {}),
                            animal.x, animal.y,
                            self.settings.invasion_pursuit_distance)
                        if target.character.health > 0 and not target.demigod and not sky.bot(target.character) and not getattr(target.character,"_road_bot",False)
                        and not self.has_buff(target, BUFF_INVISIBLE)
                        and creature_attacks_player(
                            definition,
                            attack=target.character.skills["attack"],
                            defense=target.character.skills["defense"],
                            might=target.character.attributes["might"],
                            toughness=target.character.attributes["toughness"])
                    ]
                    if regular_targets:
                        if now < animal.next_move_at:
                            continue
                        step_seconds = (
                            self.settings.normal_move_interval_ms / 1000.0)
                        animal.next_move_at = now + step_seconds
                summon_target = None
                if animal.summoned:
                    owner = next((session for session in self.sessions
                                  if session.character
                                  and session.character.actor_id == animal.owner_id), None)
                    if owner and owner.character.map_id == animal.map_id:
                        mode = int(owner.character.quest_state.get("summon_behavior", 1))
                        opponents = set(owner.aggressors)
                        if owner.combat_target is not None:
                            opponents.add(owner.combat_target)
                        allies = self.summon_allies(animal.owner_username)
                        creature_candidates = [
                            candidate for candidate in living
                            if candidate.actor_id != animal.actor_id
                            and (candidate.actor_id not in self.combatants
                                 or candidate.actor_id in opponents)
                            and candidate.map_id == animal.map_id
                            and max(abs(candidate.x - owner.character.x),
                                    abs(candidate.y - owner.character.y))
                                <= self.settings.summon_wander_radius
                            and summon_target_allowed(
                                mode, candidate.actor_id,
                                target_summoned=candidate.summoned,
                                target_owner_id=candidate.owner_id,
                                owner_id=animal.owner_id,
                                owner_opponents=opponents,
                                target_allied=self.summon_target_allied(
                                    allies, candidate))]
                        player_candidates = [
                            candidate for candidate in
                            players_by_map.get(animal.map_id, ())
                            if candidate is not owner
                            and candidate.character.health > 0
                            and not candidate.demigod
                            and shared_pk_zone(animal, candidate.character)
                            and shared_pk_zone(
                                owner.character, candidate.character)
                            and max(abs(candidate.character.x-owner.character.x),
                                    abs(candidate.character.y-owner.character.y))
                                <= self.settings.summon_wander_radius
                            and summon_target_allowed(
                                mode, candidate.character.actor_id,
                                target_summoned=False, target_owner_id=None,
                                owner_id=animal.owner_id,
                                owner_opponents=opponents,
                                target_allied=self.summon_target_allied(
                                    allies, candidate.character))]
                        targets = [
                            (candidate, None) for candidate in creature_candidates]
                        targets.extend(
                            (candidate.character, candidate)
                            for candidate in player_candidates)
                        if targets:
                            summon_target, player_target = min(
                                targets, key=lambda entry: (
                                    max(abs(entry[0].x-animal.x),
                                        abs(entry[0].y-animal.y)),
                                    entry[0].actor_id))
                            summon_distance = max(
                                abs(summon_target.x-animal.x),
                                abs(summon_target.y-animal.y))
                            if summon_distance <= 5:
                                await self.stop_moving_attack_target(
                                    animal, summon_target)
                            # Whether it may swing is a question about the two
                            # bodies, not their anchor tiles: `summon_distance`
                            # above is the coarse radius that decides whether
                            # to look at this target at all.
                            if (actor_distance(animal, summon_target)
                                    <= self.strike_distance_against(
                                        animal, summon_target)):
                                if player_target is None:
                                    if self.reserve_summon_combat(
                                            animal, summon_target):
                                        asyncio.create_task(self.summon_attack(
                                            animal, summon_target,
                                            reserved=True))
                                else:
                                    asyncio.create_task(self.summon_attack_player(
                                        animal, player_target))
                                continue
                            occupied = occupied_for(animal.map_id)
                            route_step = self.invasion_pursuit_step(
                                animal, summon_target, occupied)
                            if route_step is not None:
                                pursuing = True
                                target = summon_target
                                animal.wander_steps_remaining = 0
                                dx, dy = route_step
                if pursuing:
                    pass
                elif animal.invasion or ranged_target is not None or regular_targets:
                    raid_team = self.territory_raids.actor_teams.get(animal.actor_id)
                    if ranged_target is not None:
                        # A ranged aggressor is pursued at any range, so it is
                        # deliberately exempt from the radius query below.
                        targets = ordered_targets = [ranged_target]
                    elif regular_targets:
                        # sessions_near already returned these nearest first.
                        targets = ordered_targets = regular_targets
                    else:
                        # Whether this creature has anyone to pursue is a
                        # question about the whole map, and the answer is the
                        # same for every creature on it - so it is computed
                        # once per map and raid team, not once per creature.
                        targets = eligible_on_map(animal.map_id, raid_team)
                        # Which of them it can act on this tick is a question
                        # about its own surroundings. Ordering the whole map's
                        # population only to break at the first candidate past
                        # the pursuit radius was the loop's largest single
                        # cost; the index answers it directly, nearest first.
                        ordered_targets = [
                            candidate for candidate in self.sessions_near(
                                player_cells.get(animal.map_id, {}),
                                animal.x, animal.y, pursuit_reach)
                            if not candidate.demigod and not sky.bot(candidate.character)
                            and (not raid_team or (
                                self.territory_raids.team_for(
                                    candidate.character.username)
                                not in {None, raid_team}))]
                    if targets and now >= animal.pursuit_retry_at:
                        target = None
                        route_step = None
                        attacked = False
                        # Invasion creatures wander rather than close on a
                        # player unless the setting restores the old approach.
                        # A creature retaliating against a ranged attacker
                        # still goes after whoever shot it, and ordinary
                        # creatures are not affected by this at all.
                        may_approach = (self.settings.invasion_pursuit
                                        or not animal.invasion
                                        or ranged_target is not None)
                        occupied = occupied_for(animal.map_id)
                        for candidate in ordered_targets:
                            # Two distances, deliberately. `distance` is the
                            # coarse anchor-to-anchor radius the pursuit and
                            # stop tests have always used; whether the creature
                            # is close enough to *swing* is measured body to
                            # body, so a large one does not open a fight from
                            # across the gap its own footprint hides.
                            distance = max(
                                abs(candidate.character.x - animal.x),
                                abs(candidate.character.y - animal.y))
                            if distance <= STOP_MOVING_DISTANCE:
                                await self.stop_moving_attack_target(
                                    animal, candidate.character, candidate)
                            if (ranged_target is None
                                    and distance > self.settings.invasion_pursuit_distance):
                                break
                            if (actor_distance(animal, candidate.character)
                                    <= self.strike_distance_against(
                                        animal, candidate.character)):
                                asyncio.create_task(self.invasion_attack(animal, candidate))
                                attacked = True
                                break
                            if not may_approach:
                                # Wandering invasion creatures notice a player
                                # this close and stop them, but do not walk to
                                # them: they strike whatever they end up beside
                                # and otherwise carry on wandering.
                                continue
                            candidate_step = self.invasion_pursuit_step(
                                animal, candidate.character, occupied)
                            if candidate_step is not None:
                                target = candidate
                                route_step = candidate_step
                                break
                        if attacked:
                            continue
                        if target is not None:
                            pursuing = True
                            animal.wander_steps_remaining = 0
                            dx, dy = route_step
                        else:
                            animal.pursuit_retry_at = (
                                now + self.settings.invasion_pursuit_retry_ms / 1000.0)
                            if animal.wander_steps_remaining <= 0:
                                animal.wander_dx, animal.wander_dy = random.choice(DIR_CHOICES)
                                animal.wander_steps_remaining = random.randint(
                                    self.settings.invasion_random_walk_min_steps,
                                    self.settings.invasion_random_walk_max_steps)
                            dx, dy = animal.wander_dx, animal.wander_dy
                            animal.wander_steps_remaining -= 1
                    elif (raid_team and self.territory_raids.active
                          and raid_team == self.territory_raids.active.aggressor.key):
                        objective = self.territory_raids.active.defender.objective
                        occupied = occupied_for(animal.map_id)
                        here = (animal.x, animal.y)
                        max_steps = self.settings.invasion_max_path_length
                        raid_shape = footprint_of(animal)
                        path = self.find_path_to_any(
                            animal.map_id, here, {objective},
                            self.blocked_anchors(
                                occupied, here, raid_shape, max_steps),
                            max_steps, raid_shape
                        ) if self.spend_path_budget() else []
                        if path:
                            dx, dy = path[0][0] - animal.x, path[0][1] - animal.y
                        else:
                            dx = dy = 0
                    elif raid_team:
                        # Defending formations hold their configured positions
                        # until an opposing participant enters pursuit range.
                        dx = dy = 0
                    else:
                        if animal.wander_steps_remaining <= 0:
                            animal.wander_dx, animal.wander_dy = random.choice(DIR_CHOICES)
                            animal.wander_steps_remaining = random.randint(
                                self.settings.invasion_random_walk_min_steps,
                                self.settings.invasion_random_walk_max_steps)
                        dx, dy = animal.wander_dx, animal.wander_dy
                        animal.wander_steps_remaining -= 1
                else:
                    definition = self.creatures[animal.creature_type]
                    # Summons reserved their movement slot above; ordinary
                    # creatures are independently paced here.
                    if not animal.summoned and now < animal.next_move_at:
                        continue
                    if animal.wander_steps_remaining <= 0:
                        animal.wander_dx, animal.wander_dy = random.choice(DIR_CHOICES)
                        animal.wander_steps_remaining = random.randint(
                            self.settings.normal_random_walk_min_steps,
                            self.settings.normal_random_walk_max_steps)
                    dx, dy = animal.wander_dx, animal.wander_dy
                    animal.wander_steps_remaining -= 1
                    if not animal.summoned:
                        step_seconds = (
                            self.settings.normal_move_interval_ms / 1000.0)
                        animal.next_move_at = now + step_seconds
                occupied = occupied_for(animal.map_id)
                if animal.invasion and not pursuing and invasion_wait_this_cycle():
                    # Waiting is an ordinary independent AI choice. Staggered
                    # deadlines prevent whole waves from pausing together.
                    continue
                # Set when a wild leash turns this step toward the spawn, so a
                # blocked step home edges round the obstacle (below).
                homing = False
                if not pursuing:
                    summoner = players_by_actor.get(animal.owner_id) if animal.summoned else None
                    if summoner is not None and summoner.map_id == animal.map_id:
                        leashed_dx, leashed_dy = leashed_wander_step(
                            animal.x, animal.y, dx, dy, summoner.x, summoner.y,
                            self.settings.summon_wander_radius)
                        if (leashed_dx, leashed_dy) != (dx, dy):
                            animal.wander_steps_remaining = 0
                        dx, dy = leashed_dx, leashed_dy
                    boss_anchor = self.boss_follow_anchor(animal)
                    if summoner is not None and summoner.map_id == animal.map_id:
                        pass
                    elif boss_anchor is not None:
                        anchor_x, anchor_y = boss_anchor
                        radius = self.settings.boss_follow_radius
                        if max(abs(animal.x + dx - anchor_x),
                               abs(animal.y + dy - anchor_y)) > radius:
                            animal.wander_steps_remaining = 0
                            dx = (anchor_x > animal.x) - (anchor_x < animal.x)
                            dy = (anchor_y > animal.y) - (anchor_y < animal.y)
                    elif animal.invasion and not raid_team:
                        radius = (animal.wander_radius
                                  or self.settings.invasion_wander_radius)
                        march = self.march_step(animal, occupied)
                        if march is not None:
                            animal.wander_steps_remaining = 0
                            dx, dy = march
                        elif max(abs(animal.x + dx - animal.spawn_x),
                                 abs(animal.y + dy - animal.spawn_y)) > radius:
                            animal.wander_steps_remaining = 0
                            dx = (animal.spawn_x > animal.x) - (animal.spawn_x < animal.x)
                            dy = (animal.spawn_y > animal.y) - (animal.spawn_y < animal.y)
                    elif animal.tame and (
                            abs(animal.x + dx - animal.spawn_x) > animal.wander_radius
                            or abs(animal.y + dy - animal.spawn_y) > animal.wander_radius):
                        # Livestock keeps to its pen or its hitching post.
                        animal.wander_steps_remaining = 0
                        continue
                    elif (animal.wander_radius and not animal.tame
                          and not animal.invasion and not animal.summoned):
                        # A wild spawn row's `leash:N` (spawns.py): the
                        # creature's own radius, per axis around its spawn.
                        # A step that would leave it turns home instead of
                        # being refused, so a creature a chase carried past
                        # its leash walks back rather than standing there.
                        routed = None
                        outside = max(abs(animal.x - animal.spawn_x),
                                      abs(animal.y - animal.spawn_y)) > animal.wander_radius
                        if outside:
                            if not animal.leash_outside_since:
                                animal.leash_outside_since = now
                            elif (now - animal.leash_outside_since >= LEASH_STRANDED_SECONDS
                                    and self.return_to_leash(animal, occupied, now)):
                                continue
                            # Routed while outside, not only once the greedy
                            # step is blocked: a greedy step taken between
                            # routed ones undoes them along a wall.
                            routed = self.leash_home_step(animal, occupied, now)
                        else:
                            animal.leash_outside_since = 0.0
                        if routed is not None:
                            animal.wander_steps_remaining = 0
                            homing = True
                            dx, dy = routed
                        else:
                            home_dx, home_dy = leashed_wander_step(
                                animal.x, animal.y, dx, dy,
                                animal.spawn_x, animal.spawn_y, animal.wander_radius)
                            # Outside, the step is a step home even when the
                            # random one already pointed there, and is given
                            # the same fallbacks when it is blocked.
                            if outside or (home_dx, home_dy) != (dx, dy):
                                animal.wander_steps_remaining = 0
                                homing = True
                            dx, dy = home_dx, home_dy
                    elif (abs(animal.x + dx - animal.spawn_x) > self.settings.normal_wander_radius
                          or abs(animal.y + dy - animal.spawn_y) > self.settings.normal_wander_radius):
                        animal.wander_steps_remaining = 0
                        continue
                elif animal.leash_outside_since:
                    # A chase is not a stranding: the clock that returns a
                    # leashed creature to its spawn starts when the chase ends.
                    animal.leash_outside_since = 0.0
                candidates = [(dx, dy)]
                if (animal.invasion or animal.summoned or pursuing or homing) and dx and dy:
                    # If a diagonal pursuit/leash step is obstructed, keep moving
                    # around the obstacle instead of idling for another tick.
                    candidates.extend(((dx, 0), (0, dy)))
                elif homing and (dx or dy):
                    # A straight step home that is blocked edges round the
                    # obstacle on either diagonal, still closing on the spawn.
                    candidates.extend(((dx or 1, dy or 1), (dx or -1, dy or -1)))
                shape = footprint_of(animal)
                here = (animal.x, animal.y)
                step_mask = self.step_mask_at(
                    animal.map_id, animal.x, animal.y, shape)
                step = next(((sx, sy) for sx, sy in candidates
                    if not self.anchor_blocked(
                        occupied, animal.x + sx, animal.y + sy, shape, here)
                    and self.step_allowed(animal.map_id, animal.x, animal.y,
                                          sx, sy, step_mask, shape)), None)
                if step is None and pursuing:
                    route_step = self.invasion_pursuit_step(
                        animal, (target.character if isinstance(target, Session) else target), occupied)
                    if route_step is not None:
                        step = route_step
                    else:
                        # Do not keep pressing into the same wall while a player
                        # is geometrically near but requires an excessive route.
                        animal.pursuit_retry_at = (
                            now + self.settings.invasion_pursuit_retry_ms / 1000.0)
                        pursuing = False
                        animal.wander_dx, animal.wander_dy = random.choice(DIR_CHOICES)
                        animal.wander_steps_remaining = random.randint(
                            self.settings.invasion_random_walk_min_steps,
                            self.settings.invasion_random_walk_max_steps) - 1
                        dx, dy = animal.wander_dx, animal.wander_dy
                        random_candidates = [(dx, dy)]
                        if dx and dy:
                            random_candidates.extend(((dx, 0), (0, dy)))
                        step = next(((sx, sy) for sx, sy in random_candidates
                            if not self.anchor_blocked(
                                occupied, animal.x + sx, animal.y + sy, shape, here)
                            and self.step_allowed(
                                animal.map_id, animal.x, animal.y,
                                sx, sy, step_mask, shape)), None)
                if step is None:
                    if not pursuing:
                        animal.wander_steps_remaining = 0
                    continue
                dx, dy = step
                animal.next_move_at += diagonal_step_hold(step_seconds, dx, dy)
                nx, ny = animal.x + dx, animal.y + dy
                if not roads.movement_allowed(animal, nx, ny):
                    continue
                if not sky.movement_allowed(animal, nx, ny):
                    continue
                if not bell.movement_allowed(animal, nx, ny):
                    animal.wander_steps_remaining = 0
                    continue
                # The whole body moves, not just the anchor: the shared
                # occupancy set is what every other creature on this map tests
                # against for the rest of the tick, so a large creature that
                # released only its anchor tile would leave the rest of itself
                # behind as permanent obstacles.
                for tile in shape.tiles(animal.x, animal.y):
                    occupied.discard(tile)
                for tile in shape.tiles(nx, ny):
                    occupied.add(tile)
                animal.x, animal.y = nx, ny
                # The movement command below states the facing to whoever is
                # watching this step. The stored rotation is what a client that
                # meets the creature later reads, and what every packet that
                # names no direction of its own falls back to, so a creature
                # that has walked must not still claim it faces its spawn.
                animal.rotation = facing_rotation(dx, dy)
                animal.last_moved_at = now
                self.record_actor_move(animal.actor_id, now)
                movement_commands.setdefault(animal.map_id, {})[animal.actor_id] = DIRS[(dx, dy)]
            # Movement for creatures a player already sees goes out every
            # tick. Recomputing which creatures are in view is the expensive
            # half, and it is spread over several ticks so that the cost per
            # tick stays flat as the player count grows.
            try:
                for map_id, sessions in players_by_map.items():
                    commands = movement_commands.get(map_id)
                    for index, session in enumerate(sessions):
                        refresh = (index + tick) % VISIBILITY_REFRESH_TICKS == 0
                        if commands or refresh:
                            await self.sync_visible_animals(
                                session, commands, refresh=refresh)
                        if getattr(session, "visible_adjacent", None):
                            await self.forward_adjacent_movement(session, movement_commands)
                await self.flush_sessions()
            finally:
                self._index_pinned = False
            if tick_started:
                self._record_tick(tick_started, len(alive_actors), len(living),
                                  len(awake & holding), len(holding))

    def _record_tick(self, started: float, alive: int, walked: int,
                     awake: int = 0, holding: int = 0) -> None:
        """Note what one AI tick cost and how much of the world it walked.

        The counts are handed in rather than derived here: anything this
        function worked out for itself would be work the tick does not
        otherwise do, and the point of the switch is that measuring should
        cost what not measuring costs.
        """
        metrics.record("animal_tick", time.perf_counter() - started)
        metrics.record("creatures_alive", float(alive))
        metrics.record("creatures_walked", float(walked))
        metrics.record("maps_awake", float(awake))
        metrics.record("maps_holding_creatures", float(holding))
        metrics.record("sessions", float(len(self.sessions)))

    async def _respawn(self, animal: Animal):
        if animal.species == lantern.BOAR:
            return  # The private encounter is restored only after a novice defeat.
        delay = self.creatures[animal.creature_type].time_to_respawn
        if self.special_day_has("faster_respawns"):
            delay = max(1, delay // 2)
        await asyncio.sleep(delay)
        await self.remove_creature_from_clients(animal)
        # Roll again. A creature that comes back is a fresh one as far as the
        # world is concerned, so the ordinary bear can return as the named one
        # and the named one can return ordinary - otherwise the variants would
        # be whatever the world rolled at startup, for ever.
        #
        # From the variant's base, not from what it happens to be now: rolling
        # a variant against itself would make it permanent once it appeared.
        definition = self.creatures.get(animal.creature_type)
        base = (definition.variant_of if definition and definition.is_variant
                else animal.creature_type)
        if base in self.creatures:
            self.apply_creature_type(animal, self.roll_spawn_species(base))
        animal.x, animal.y = self.free_creature_tile(
            animal.map_id, animal.spawn_x, animal.spawn_y, footprint_of(animal))
        self.equip_creature(animal)
        animal.health, animal.alive = animal.max_health, True
        self.invalidate_creature_index(animal.map_id)
        for session in self.sessions:
            if session.character and (session.character.map_id == animal.map_id
                                      or animal.map_id in self.adjacent_maps(session.character.map_id)):
                await self.sync_visible_animals(session)

    async def _remove_dead_invasion(self, animal: Animal):
        await asyncio.sleep(3)
        await self.remove_creature_from_clients(animal)
        self.remove_animal(animal)
