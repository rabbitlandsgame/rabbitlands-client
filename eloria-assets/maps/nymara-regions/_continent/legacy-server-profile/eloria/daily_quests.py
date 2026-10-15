"""Profile-aware daily quest assignment pools and persistent state helpers."""

from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Iterable

from .stats import award_experience


@dataclass(frozen=True)
class DailyTask:
    client: str
    kind: str
    target: str
    amount: int
    map_id: str
    x: int
    y: int
    xp_rate: int = 0
    gold: int = 0
    min_level: int = 0
    reward_skill: str = ""
    base_xp: int = 0
    special_reward: str = ""


# Haidir's forty-seven kill assignments, Xaquelina's thirty harvests,
# Daritha's and Dorel's deliveries, Minel's engineering runs and Kaleb's one
# errand all lived here. Every client, every destination and every one of the
# six NPCs who handed them out belonged to the Eternal Lands profile: nothing
# in that set was reachable on the profile this server runs, so none of those
# assignments could be taken, let alone finished.
#
# The Nymara pools below are the live ones - their clients and their maps are
# all served. Kill-a-spawn-group and continue-a-quest-line are the two kinds
# still to be authored; they go here as further pools rather than as changes
# to the three that work.
# The harvest tasks point at a patch that exists: each tile is the centre of a
# cluster tools/author_region_content.py laid on that map, and the recording
# rule accepts a harvest within eight tiles of it. Re-derive them when the
# clusters move; a task nobody can complete is worse than none.
NYMARA_HARVEST_TASKS = (
    DailyTask("Sister Arel","harvest","Silverleaf",12,"whitehorn_range",363,304,48,240),
    DailyTask("Ione Brass","harvest","Crystal",10,"amethyst_barrens",229,308,56,300),
    DailyTask("Elder Sura","harvest","Seed",18,"sunmane_steppe",205,76,38,220),
    DailyTask("Mora Fen","harvest","Orchid",10,"grey_moors",60,90,52,280),
    DailyTask("Tessara","harvest","Venom Bulb",8,"verdant_stair",85,188,64,360),
    DailyTask("Mara Tide","harvest","Lotus",16,"manymouth_delta",142,304,44,250),
)

NYMARA_HUNT_TASKS = (
    DailyTask("Sister Arel","kill","Glacier Ram",8,"whitehorn_range",0,0,110,300),
    DailyTask("Ione Brass","kill","Crystal Mite",12,"amethyst_barrens",0,0,110,320),
    DailyTask("Elder Sura","kill","Dunrunner",12,"sunmane_steppe",0,0,105,300),
    DailyTask("Mora Fen","kill","Moor Wisp Hound",8,"grey_moors",0,0,180,420),
    DailyTask("Archivist Sesh","kill","Scalevine Stalker",8,"ssarathi_ruins",0,0,210,480),
    DailyTask("Mara Tide","kill","Mangrove Crab",12,"manymouth_delta",0,0,120,340),
)

NYMARA_SUPPLY_TASKS = (
    DailyTask("Daro Pell","delivery","Bandage",12,"crownwater",64,60,0,260,0,"manufacturing",400),
    DailyTask("Korrin","delivery","Frost Distillate",4,"whitehorn_range",70,69,0,420,0,"alchemy",650),
    DailyTask("Varric Lens","delivery","Quartz Lens",4,"amethyst_barrens",73,70,0,460,0,"crafting",700),
    DailyTask("Pell Wick","delivery","Gloam Wax",3,"grey_moors",64,72,0,520,0,"alchemy",800),
    DailyTask("Orru Moss","delivery","Antidote",8,"verdant_stair",69,60,0,440,0,"potion",700),
    DailyTask("Jori Reed","delivery","Woven Charm",4,"manymouth_delta",89,37,0,480,0,"tailoring",750),
)
QUEST_TASKS = {
    "nymara_harvest": NYMARA_HARVEST_TASKS,
    "nymara_hunt": NYMARA_HUNT_TASKS,
    "nymara_supply": NYMARA_SUPPLY_TASKS,
}
START_NPCS = {
    "nymara_harvest": "Vestra", "nymara_hunt": "Toran",
    "nymara_supply": "Maelis",
}
# How long a cancelled assignment locks its pool. One value now that the pool
# that wanted forty-eight hours is gone.
CANCEL_WAIT_HOURS = 24


def active_key(c) -> str | None:
    value = c.quest_state.get("daily_active")
    return str(value) if value in QUEST_TASKS else None


def current_task(c) -> DailyTask | None:
    key = active_key(c)
    if not key:
        return None
    index = int(c.quest_state.get("daily_task_index", -1))
    tasks = QUEST_TASKS[key]
    return tasks[index] if 0 <= index < len(tasks) else None


def available_tasks(c, key: str, npc_names: Iterable[str],
                    map_ids: Iterable[str]) -> list[tuple[int, DailyTask]]:
    npcs, maps = {x.casefold() for x in npc_names}, set(map_ids)
    result = []
    for index, task in enumerate(QUEST_TASKS[key]):
        level = c.skills["manufacturing"] if key == "daritha" else c.skills["engineering"]
        if task.min_level and level < task.min_level:
            continue
        if task.client.casefold() not in npcs or task.map_id not in maps:
            continue
        result.append((index, task))
    return result


def assign(c, key: str, npc_names: Iterable[str], map_ids: Iterable[str],
           *, chooser=random.choice) -> DailyTask:
    if active_key(c):
        raise ValueError("You already have an active daily quest.")
    now = int(time.time())
    ready = int(c.quest_state.get(f"daily_{key}_ready_at", 0))
    if now < ready:
        hours = max(1, (ready - now + 3599) // 3600)
        raise ValueError(f"You must wait about {hours} more hours for another assignment.")
    choices = available_tasks(c, key, npc_names, map_ids)
    if key == "minel" and c.skills["engineering"] < 25:
        raise ValueError("You need base Engineering level 25.")
    if not choices:
        raise ValueError("No assignment suitable for your level is currently reachable.")
    index, task = chooser(choices)
    c.quest_state.update({
        "daily_active": key, "daily_task_index": index,
        "daily_progress": 0, "daily_positions": "",
    })
    return task


def cancel(c) -> str:
    key = active_key(c)
    if not key:
        raise ValueError("You do not have an active daily quest.")
    delay = CANCEL_WAIT_HOURS * 3600
    clear(c)
    c.quest_state[f"daily_{key}_ready_at"] = int(time.time()) + delay
    return key


def clear(c) -> None:
    for name in ("daily_active","daily_task_index","daily_progress","daily_positions"):
        c.quest_state.pop(name, None)


def task_text(task: DailyTask, progress: int = 0) -> str:
    map_name = task.map_id.replace("_", " ").title()
    if task.kind == "kill":
        objective = f"Kill {task.amount} {task.target} in {map_name}."
    elif task.kind == "harvest":
        objective = (f"Harvest {task.amount} {task.target} near "
                     f"[{task.x}, {task.y}] in {map_name}.")
    elif task.kind == "engineering":
        objective = (f"Place {task.amount} {task.target} near "
                     f"[{task.x}, {task.y}] in {map_name}.")
    else:
        objective = f"Deliver {task.amount} {task.target} to {task.client}."
    destination = (f" Return to {task.client}."
                   if task.kind != "delivery" else "")
    return (f"{objective} Progress: {progress}/{task.amount}."
            f"{destination}")


def record_kill(c, species: str, map_id: str) -> bool:
    task = current_task(c)
    if not task or task.kind != "kill":
        return False
    if species.casefold() != task.target.casefold() or map_id != task.map_id:
        return False
    c.quest_state["daily_progress"] = min(
        task.amount, int(c.quest_state.get("daily_progress", 0)) + 1)
    return int(c.quest_state["daily_progress"]) >= task.amount


def record_harvest(c, resource: str, map_id: str, x: int, y: int) -> bool:
    task = current_task(c)
    if not task or task.kind != "harvest":
        return False
    if resource.casefold() != task.target.casefold() or map_id != task.map_id:
        return False
    if max(abs(x-task.x), abs(y-task.y)) > 8:
        return False
    previous = int(c.quest_state.get("daily_progress", 0))
    c.quest_state["daily_progress"] = min(task.amount, previous + 1)
    return previous < task.amount <= int(c.quest_state["daily_progress"])


def record_engineering(c, item: str, map_id: str, x: int, y: int) -> tuple[bool, bool]:
    task = current_task(c)
    if not task or task.kind != "engineering" or item.casefold() != task.target.casefold():
        return False, False
    if map_id != task.map_id or max(abs(x-task.x), abs(y-task.y)) > 10:
        return True, False
    position = f"{map_id}:{x}:{y}"
    used = set(filter(None, str(c.quest_state.get("daily_positions", "")).split(",")))
    if position in used:
        return True, False
    used.add(position)
    c.quest_state["daily_positions"] = ",".join(sorted(used))
    c.quest_state["daily_progress"] = min(
        task.amount, int(c.quest_state.get("daily_progress", 0)) + 1)
    return True, int(c.quest_state["daily_progress"]) >= task.amount


def can_complete(c, npc_name: str) -> bool:
    task = current_task(c)
    if not task or npc_name.casefold() != task.client.casefold():
        return False
    if task.kind in {"kill","harvest","engineering"}:
        return int(c.quest_state.get("daily_progress", 0)) >= task.amount
    return c.inventory.get(task.target, 0) >= task.amount


def reward(c) -> tuple[DailyTask, dict[str, int], int, str]:
    key, task = active_key(c), current_task(c)
    if not key or not task:
        raise ValueError("You do not have an active daily quest.")
    if task.kind == "delivery":
        if c.inventory.get(task.target, 0) < task.amount:
            raise ValueError(f"You need {task.amount} {task.target}.")
        c.inventory[task.target] -= task.amount
        if not c.inventory[task.target]:
            del c.inventory[task.target]
    elif int(c.quest_state.get("daily_progress", 0)) < task.amount:
        raise ValueError("The assignment is not complete.")

    # What a finished assignment pays. This was a branch per Eternal Lands
    # pool, so with those retired the Nymara pools fell through it and paid no
    # skill experience at all - their gold arrived, their `reward_skill` and
    # `xp_rate` were never read.
    xp: dict[str, int] = {}
    if key == "nymara_hunt":
        xp = {"attack": task.xp_rate * c.skills["attack"],
              "defense": task.xp_rate * c.skills["defense"]}
    elif key == "nymara_harvest":
        xp = {"harvesting": task.xp_rate * c.skills["harvesting"]}
    elif key == "nymara_supply" and task.reward_skill:
        xp = {task.reward_skill: task.base_xp}
    award_experience(c, xp.items())
    if task.gold:
        c.inventory["Gold Coins"] = c.inventory.get("Gold Coins", 0) + task.gold
    clear(c)
    c.quest_state[f"daily_{key}_ready_at"] = int(time.time()) + 24 * 3600
    return task, xp, task.gold, key
