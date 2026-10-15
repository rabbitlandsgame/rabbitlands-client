#!/usr/bin/env python3
"""Compile the server's recipe, knowledge and item data for the Godot client.

The server ships more than one content profile. `config/` is the unmodified
Eternal Lands data the fork was built from; `config/eloria/` is what this
server actually runs, and it is a different game - 187 items against 1270, 32
recipes against 389, and one knowledge book against 385. Compiling the wrong
one gives the player a manufacturing window full of recipes the server has
never heard of, so the profile is named explicitly and defaults to the one
that is served.

Both catalogs come out of a single run, because the recipe catalog's
`knowledgeIndex` is an index into the knowledge catalog: generating them
separately is how the two drift apart.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys


def digest(path: Path) -> str:
    """Hashes the file's content with newlines normalised, so a checkout on
    Windows and one on Linux record the same source."""
    return hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="where to write the recipe catalog")
    parser.add_argument("--knowledge-output", type=Path,
                        help="where to write the knowledge catalog; omitted"
                             " leaves it alone")
    parser.add_argument("--profile", default="eloria",
                        help="content profile directory under config/"
                             " (default: eloria, which is the only one)")
    args = parser.parse_args()
    server_root = args.server_root.resolve()
    sys.path.insert(0, str(server_root))

    from eloria.items import (  # pylint: disable=import-outside-toplevel
        ITEMS,
        configure_items,
    )
    from eloria.knowledge import (  # pylint: disable=import-outside-toplevel
        infer_recipe_knowledge,
        load_books,
    )
    from eloria.recipes import load_recipes  # pylint: disable=import-outside-toplevel

    profile_root = server_root / "config" / args.profile
    if not profile_root.is_dir():
        parser.error(f"no such content profile: {profile_root}")
    recipe_path = profile_root / "recipes.txt"
    item_path = profile_root / "items.txt"
    book_path = profile_root / "books.txt"
    configure_items(item_path)
    recipes = load_recipes(recipe_path)
    books = load_books(str(book_path), ITEMS)

    knowledge_order = [
        book.knowledge for book in books.values() if not book.repeatable
    ]
    knowledge_indexes = {name: index for index, name in enumerate(knowledge_order)}
    names_by_image: dict[int, list[str]] = collections.defaultdict(list)
    for item in ITEMS.values():
        names_by_image[item.image_id].append(item.name)

    def item_definition(name: str, quantity: int = 1) -> dict[str, object]:
        item = ITEMS[name]
        aliases = names_by_image[item.image_id]
        return {
            "name": name,
            "quantity": quantity,
            "imageId": item.image_id,
            "ambiguousImage": len(aliases) > 1,
            "imageAliases": aliases if len(aliases) > 1 else [],
        }

    entries = []
    for index, recipe in enumerate(recipes):
        knowledge = recipe.knowledge or infer_recipe_knowledge(
            recipe.output, recipe.skill, books
        )
        if knowledge and knowledge not in knowledge_indexes:
            raise ValueError(f"missing knowledge index for {knowledge!r}")
        entries.append(
            {
                "id": index,
                "skill": recipe.skill,
                "output": recipe.output,
                "outputImageId": (
                    ITEMS[recipe.output].image_id if recipe.output in ITEMS else -1
                ),
                "level": recipe.level,
                # Summoning is the one skill whose recipes also cost a nexus,
                # and the server refuses the mix without it. Exporting it lets
                # the summoning window say so instead of offering a summon
                # that will be turned down. Zero for every other skill.
                "animalNexus": recipe.animal_nexus,
                "experience": recipe.experience,
                "food": recipe.food,
                "mana": recipe.mana,
                "knowledge": knowledge,
                "knowledgeIndex": knowledge_indexes.get(knowledge, -1),
                "ingredients": [
                    item_definition(name, quantity)
                    for name, quantity in recipe.ingredients
                ],
                "tools": [item_definition(name) for name in recipe.tools],
            }
        )

    sources = {
        "profile": args.profile,
        "recipesSha256": digest(recipe_path),
        "itemsSha256": digest(item_path),
        "booksSha256": digest(book_path),
    }
    document = {
        "schemaVersion": 1,
        "sources": sources,
        "recipes": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} recipes to {args.output}")

    if args.knowledge_output is not None:
        knowledge_document = {
            "version": 1,
            "source": {
                "profile": args.profile,
                "itemsSha256": sources["itemsSha256"],
                "booksSha256": sources["booksSha256"],
                "algorithm": "server load_books insertion order,"
                             " excluding repeatable books",
            },
            "entries": knowledge_order,
        }
        args.knowledge_output.parent.mkdir(parents=True, exist_ok=True)
        args.knowledge_output.write_text(
            json.dumps(knowledge_document, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(knowledge_order)} knowledges"
              f" to {args.knowledge_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
