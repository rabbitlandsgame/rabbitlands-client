"""Storage bodies are solid while their entire nearby use ring is reachable."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frames import Frame
from publish_server import Checker


def checker():
    codes = np.full((12, 12), 13, dtype=np.uint8)
    codes[4:7, 4:7] = 0
    frame = Frame("test", "Test", (0, 12), (12, 12), (0, 0, 0))
    return Checker({"test": codes}, {"test": np.ones((12, 12), dtype=bool)},
                   {"test": frame}, {"test": [[0, 0], [12, 0], [12, 12], [0, 12]]})


def test_solid_chest_with_reachable_approach_is_publishable():
    check = checker()
    assert check.storage("test", (5, 5), "chest")
    assert check.failures == []
    # Other interactives still require their own tile and neighbours to be open.
    assert not check.ring("test", (5, 5), "interactive", "desk")


@pytest.mark.parametrize("problem", ["blocked approach", "unreached approach", "open body", "outside ownership"])
def test_storage_rejects_unusable_or_misstamped_locations(problem):
    check = checker()
    if problem == "blocked approach":
        check.codes["test"][5, 7] = 0
    elif problem == "unreached approach":
        check.reached["test"][5, 7] = False
    elif problem == "open body":
        check.codes["test"][5, 5] = 13
    else:
        check.polygons["test"] = [[0, 0], [7, 0], [7, 12], [0, 12]]
    assert not check.storage("test", (5, 5), "chest")
    assert check.failures
