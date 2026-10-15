"""Logical storage rectangles; never alter the logical-to-world transform.

Publisher layout restrictions (square, multiples of six) belong to the publisher,
not this source/array boundary. Profile serialization belongs to the server codec.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import math


def integer(value, where):
    if type(value) is not int:
        raise ValueError(f"{where} must be an integer")
    return value


def vector(value, size, where, *, integers=False):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{where} must contain {size} numbers")
    for item in value:
        if integers:
            integer(item, where)
        elif type(item) not in (int, float) or not math.isfinite(item):
            raise ValueError(f"{where} must contain finite numbers")
    return tuple(value)


@dataclass(frozen=True)
class StorageBounds:
    width: int
    height: int
    min_x: int = 0
    min_y: int = 0

    def __post_init__(self):
        for name in ("width", "height", "min_x", "min_y"):
            integer(getattr(self, name), name)
        if not (1 <= self.width <= 2048 and 1 <= self.height <= 2048):
            raise ValueError("storage extents must be within 1..2048")
        if any(not -(2**31) <= value <= 2**31 - 1 for value in
               (self.min_x, self.min_y, self.max_x - 1, self.max_y - 1)):
            raise ValueError("logical storage bounds exceed signed 32-bit coordinates")

    @property
    def max_x(self):
        return self.min_x + self.width

    @property
    def max_y(self):
        return self.min_y + self.height

    def contains(self, x, y):
        integer(x, "logical x")
        integer(y, "logical y")
        return self.min_x <= x < self.max_x and self.min_y <= y < self.max_y

    def index_xy(self, x, y):
        """Return (column, row), or None for a logical tile outside storage."""
        return (x - self.min_x, y - self.min_y) if self.contains(x, y) else None

    def index(self, x, y):
        at = self.index_xy(x, y)
        return None if at is None else at[1] * self.width + at[0]

    def logical_xy(self, column, row):
        integer(column, "column")
        integer(row, "row")
        if not (0 <= column < self.width and 0 <= row < self.height):
            raise ValueError("array index outside storage")
        return column + self.min_x, row + self.min_y

    def contains_bounds(self, other):
        return (self.min_x <= other.min_x and self.min_y <= other.min_y
                and self.max_x >= other.max_x and self.max_y >= other.max_y)

    def union(self, other):
        x, y = min(self.min_x, other.min_x), min(self.min_y, other.min_y)
        return StorageBounds(max(self.max_x, other.max_x) - x,
                             max(self.max_y, other.max_y) - y, x, y)

    def metadata(self):
        return {"serverStorageVersion": 1, "serverTileMin": [self.min_x, self.min_y]}

    def physical_origin(self, server_origin):
        """Local X/Z of storage's top-left corner in the supported 1 m frame."""
        x, y = vector(server_origin, 2, "server.origin", integers=True)
        return self.min_x - x, y - self.min_y

    def physical_bounds(self, server_origin):
        x, z = self.physical_origin(server_origin)
        return [[x, z - self.height], [x + self.width, z]]

    @classmethod
    def from_metadata(cls, cells, metadata):
        if not isinstance(metadata, Mapping):
            raise ValueError("storage metadata must be an object")
        width, height = vector(cells, 2, "server.cells", integers=True)
        versioned = "serverStorageVersion" in metadata
        if versioned != ("serverTileMin" in metadata):
            raise ValueError("serverStorageVersion and serverTileMin must be supplied together")
        if not versioned:
            return cls(width, height)
        if integer(metadata["serverStorageVersion"], "serverStorageVersion") != 1:
            raise ValueError("unsupported serverStorageVersion; expected 1")
        minimum = vector(metadata["serverTileMin"], 2, "serverTileMin", integers=True)
        return cls(width, height, *minimum)


def storage_record(cells, metadata):
    """Normalized storage certificate, separate from coordinate/profile codecs."""
    bounds = StorageBounds.from_metadata(cells, metadata)
    record = {'serverCells': [bounds.width, bounds.height], **bounds.metadata()}
    if 'authoringSpecSha256' in metadata:
        digest = metadata['authoringSpecSha256']
        if (not isinstance(digest, str) or len(digest) != 64 or
                any(character not in '0123456789abcdef' for character in digest)):
            raise ValueError('authoringSpecSha256 must be a lowercase SHA-256 digest')
        record['authoringSpecSha256'] = digest
    return record


def authoring_storage(server):
    """Validate the supported authoring frame before deriving physical storage.

The existing source schema has an implicit zero local origin, 1 m tiles and
inverted Y. Explicit incompatible values must not be ignored. walkingHeight,
when supplied by a source, is preserved separately and never derived here.
"""
    if not isinstance(server, Mapping):
        raise ValueError("server must be an object")
    bounds = StorageBounds.from_metadata(server.get("cells"), server)
    origin = vector(server.get("origin"), 2, "server.origin", integers=True)
    local = vector(server.get("localOrigin", [0, 0, 0]), 3, "server.localOrigin")
    scale = vector([server.get("metresPerTile", 1)], 1, "server.metresPerTile")[0]
    if local != (0, 0, 0) or scale != 1 or server.get("invertServerY", True) is not True:
        raise ValueError("authoring storage requires zero localOrigin, one metre tiles and inverted server Y; unsupported explicit frame")
    if "walkingHeight" in server:
        vector([server["walkingHeight"]], 1, "server.walkingHeight")
    collision = vector(server.get("collisionOriginMetres"), 2, "server.collisionOriginMetres")
    if collision != bounds.physical_origin(origin):
        raise ValueError("server.collisionOriginMetres must equal [minX-originX, originY-minY] in the supported authoring frame")
    return bounds


def frame_values(server):
    """Semantic frame identity, retaining presence of optional walkingHeight."""
    return (tuple(server["origin"]), tuple(server.get("localOrigin", [0, 0, 0])),
            server.get("metresPerTile", 1), server.get("invertServerY", True),
            "walkingHeight" in server, server.get("walkingHeight"))
