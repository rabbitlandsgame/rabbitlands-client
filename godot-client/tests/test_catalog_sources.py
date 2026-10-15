#!/usr/bin/env python3
"""The client's item catalogs were generated from the server's own tables.

`data/manufacturing/recipes.json` and `data/knowledge/catalog.json` are written
by tools/generate_manufacturing_catalog.py from the server profile's
recipes.txt, items.txt and books.txt, and each records the SHA-256 of what it
was built from (`sources` and `source`). The server records the same digests
in `config/eloria/client_content_manifest.json` under `catalog_sources`, and
its content-sync test holds those to its own tables. Nothing compared the two
halves: when the landing isle's Olive and Lemon changed items.txt, the client
catalogs stayed a table behind and no test said so. This compares them.

The server repository is found as test_world_object_models.py finds it
(ELORIA_SERVER_ROOT, or a `<worktree>-server` or `eloria-server` checkout
beside this one); without one the checks skip with a message. A failure means
the catalogs were built from other tables than the server's: regenerate them
with tools/generate_manufacturing_catalog.py --server-root <that server>.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_world_object_models import CLIENT, server_root  # noqa: E402

RECIPES = CLIENT / "data/manufacturing/recipes.json"
KNOWLEDGE = CLIENT / "data/knowledge/catalog.json"
MANIFEST = "config/eloria/client_content_manifest.json"
REGENERATE = ("regenerate the client catalogs with tools/generate_manufacturing_catalog.py "
              "--server-root {root}")


class CatalogSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        root = server_root()
        if root is None:
            self.skipTest("eloria-server is not checked out beside the client")
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        self.served = manifest["catalog_sources"]
        self.hint = REGENERATE.format(root=root)
        self.assertEqual(sorted(self.served), ["booksSha256", "itemsSha256", "recipesSha256"])

    def test_the_recipe_catalog_names_the_server_s_recipes_items_and_books(self) -> None:
        sources = json.loads(RECIPES.read_text(encoding="utf-8"))["sources"]
        self.assertEqual({key: sources.get(key) for key in self.served}, self.served, self.hint)

    def test_the_knowledge_catalog_names_the_server_s_items_and_books(self) -> None:
        source = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))["source"]
        expected = {key: self.served[key] for key in ("itemsSha256", "booksSha256")}
        self.assertEqual({key: source.get(key) for key in expected}, expected, self.hint)


if __name__ == "__main__":
    unittest.main(verbosity=2)
