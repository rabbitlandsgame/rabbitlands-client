"""Give the march stones rooted verges beside the continental cartways."""
import numpy as np
from verify_runtime import VerticalRayIndex


def apply(build):
    from road_profiles import _stations
    road = next(r for r in build.geography_roads if r['id'] == 'amethyst-sunmane')
    if 'contactStations' in road:
        raise ValueError('Sunmane northern approach authored twice')
    points, length = _stations(road['stations'], spacing=.5)
    meshes = [m for n, m in build.terrain_meshes.items()
              if n.startswith('Walk_ContinentRoad_amethyst-sunmane') and m.triangle_count]
    ray = VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1, 3)] for m in meshes]))
    for point in points:
        height = ray.top_hit(*point[[0, 2]])
        if height is not None:
            point[1] = height - .03

    def smooth(value):
        value = np.clip(value, 0., 1.)
        return value * value * (3. - 2. * value)

    # The broad northwestern bend leaves both standing stones rooted. Its
    # displacement returns to zero before the straight border approach.
    weight = smooth((length - 1.) / 6.) * (1. - smooth((length - 13.) / 12.))
    points[:, 0] -= 4.5 * weight / np.sqrt(2.)
    points[:, 2] -= 4.5 * weight / np.sqrt(2.)
    road['contactStations'] = points.tolist()
    road['contactNote'] = ('The cartway rounds northwest of the intact northern march stones, '
                           'leaving clear shoulders and their original foundations.')
    _seat_western_stones(build)
    _seat_southern_stones(build)


def _seat_western_stones(build):
    """Retain the landing marker on the dry knoll, clear of the lower road."""
    marker = next(p for p in build.placements
                  if p.node == 'Landmark_sunmane_march_west-landing')
    x, _, z = marker.position
    x += 3.
    _seat_stones(build, marker, x, z, .035)


def _seat_southern_stones(build):
    """Mark the level crest with a stone pair parallel to the cartway."""
    marker = next(p for p in build.placements
                  if p.node == 'Landmark_sunmane_march_south-track')
    marker.rotation_y = np.pi / 2.
    # The old marker sat in the new climbing embankment. This surveyed crest
    # leaves two metres of verge outside the full cartway and keeps both feet
    # within this region. Bury the rough bases into the graded shoulder.
    _seat_stones(build, marker, 174.5, 113., .38)


def _seat_stones(build, marker, x, z, embed):
    from amberwood.mesh import rotation_y
    mesh = build.meshes[marker.mesh]
    vertices = np.concatenate([part.positions for part in getattr(mesh, 'all_parts', [mesh])])
    vertices = vertices * marker.scale @ rotation_y(marker.rotation_y)[:3, :3].T
    feet = vertices[vertices[:, 1] <= vertices[:, 1].min() + .08]
    ground_meshes = [part for name, part in build.terrain_meshes.items()
                     if name.startswith('Terrain_') and not any(
                         suffix in name for suffix in ('_Road', '_Turf')) and part.triangle_count]
    ground = VerticalRayIndex(np.concatenate([
        part.positions[part.indices.reshape(-1, 3)] for part in ground_meshes]))
    heights = [ground.top_hit(x + foot[0], z + foot[2]) for foot in feet]
    if not heights or any(height is None for height in heights):
        raise ValueError('March stones must remain on their surveyed dry shoulder')
    # The low, uneven rock feet are set slightly into their actual soil.
    y = min(height - foot[1] for height, foot in zip(heights, feet)) - embed
    marker.position = (float(x), float(y), float(z))
    import landscape_plan
    for landmark in build.landmarks:
        if landmark.get('node') == marker.node:
            landmark.update(position=list(marker.position), serverTile=landscape_plan.tile(x, z),
                            rotationDegrees=float(np.degrees(marker.rotation_y)))
