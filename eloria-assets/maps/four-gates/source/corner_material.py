"""Bounded Four-only ordinary PBR material baked from existing source recipes.

No runtime shader: both gameplay and the atlas consume the same embedded
albedo/normal/ORM images. Albedo mixing happens in linear light. Texture UV
sampling retains the old recipe phase; only the local image coordinates differ.
"""
from io import BytesIO
from functools import lru_cache
import numpy as np
from PIL import Image

PREFIX = 'four_corner_blend_'
TEXELS_PER_METRE = 32


def affine_uv(mesh):
    ids = np.unique(mesh.indices)
    design = np.column_stack((mesh.positions[ids, 0], mesh.positions[ids, 2], np.ones(len(ids))))
    fit = np.linalg.lstsq(design, mesh.uvs[ids], rcond=None)[0]
    tolerance = float(np.max(np.spacing(np.abs(mesh.uvs[ids]).astype(np.float32)))) + 1e-8
    if abs(design@fit-mesh.uvs[ids]).max() > max(tolerance, 1e-8):
        raise ValueError('Local corner source UVs are not affine within encoded float precision')
    # The local image U/V axes are +X/+Z. Keep the source tangent frame:
    # positive independent axes differ only in scale, not handedness/rotation.
    if min(fit[0, 0], fit[1, 1]) <= 0 or max(abs(fit[0, 1]), abs(fit[1, 0])) > 1e-6:
        raise ValueError('Local corner UV axes require explicit normal-frame conversion')
    return fit.tolist()


def sample(image, uv):
    """GL-style repeated bilinear sampling at texel centres."""
    pixels = np.asarray(image.convert('RGB'), dtype=float)/255
    h, w = pixels.shape[:2]
    xy = (uv % 1)*np.array([w, h])-.5
    lo = np.floor(xy).astype(np.int64); f = xy-lo
    a = pixels[lo[..., 1] % h, lo[..., 0] % w]
    b = pixels[lo[..., 1] % h, (lo[..., 0]+1) % w]
    c = pixels[(lo[..., 1]+1) % h, lo[..., 0] % w]
    d = pixels[(lo[..., 1]+1) % h, (lo[..., 0]+1) % w]
    return (a*(1-f[..., 0, None])+b*f[..., 0, None])*(1-f[..., 1, None])+(c*(1-f[..., 0, None])+d*f[..., 0, None])*f[..., 1, None]


def linear(rgb):
    return np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)


def srgb(rgb):
    rgb = np.clip(rgb, 0, 1)
    return np.where(rgb <= .0031308, rgb*12.92, 1.055*rgb**(1/2.4)-.055)


def unit(v):
    return v/np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


@lru_cache(maxsize=1)
def field():
    import corner_paint as P
    x0, x1, z0, z1 = P.BOUNDS
    width, height = int((x1-x0)*TEXELS_PER_METRE), int((z1-z0)*TEXELS_PER_METRE)
    x, z = np.meshgrid(x0+(np.arange(width)+.5)/TEXELS_PER_METRE,
                       z0+(np.arange(height)+.5)/TEXELS_PER_METRE)
    flat = np.column_stack((x.ravel(), z.ravel()))
    distances = np.concatenate([np.stack([P.C.G.boundary_sample(P.REGION, part, maximum=np.inf, peer=p)[0]
                                          for p in P.PEERS], axis=1) for part in np.array_split(flat, 64)])
    weights = {peer: P.coverage(flat, distances, peer).reshape(height, width, 1) for peer in P.PEERS}
    return np.stack((x, z, np.ones_like(x)), axis=-1), weights


def bake(recipe, providers):
    design, weights = field()
    weight = weights[recipe['peer']]
    albedos, normals, orms = [], [], []
    for label in ('base', 'paint'):
        source = providers[recipe[label+'Material']]
        uv = design @ np.asarray(recipe[label+'Uv'])
        # Decode before filtering: GPU sRGB textures filter in linear light.
        # Existing material images are sampled at higher detail than this
        # bounded atlas; the local image gains ordinary generated mipmaps.
        raw = np.asarray(source['albedo'].convert('RGB'), dtype=float)/255
        # Interpolate the linear source array directly, without an 8-bit
        # intermediate that would lose precision in the darker meadow.
        albedos.append(_sample_array(linear(raw), uv)*np.asarray(source.get('baseColorFactor', [1, 1, 1, 1]))[:3])
        normal = sample(source['normal'], uv)*2-1
        normal[..., :2] *= source.get('normalScale', 1.)
        normals.append(unit(normal))
        orm = sample(source['orm'], uv)
        orm[..., 1] *= source.get('roughnessFactor', 1.)
        orm[..., 2] *= source.get('metallicFactor', 1.)
        orms.append(orm)
    images = {'albedo': srgb(albedos[0]*(1-weight)+albedos[1]*weight),
              'normal': unit(normals[0]*(1-weight)+normals[1]*weight)*.5+.5,
              'orm': orms[0]*(1-weight)+orms[1]*weight}
    return {key: Image.fromarray(np.rint(np.clip(value, 0, 1)*255).astype(np.uint8), 'RGB') for key, value in images.items()}


def _sample_array(pixels, uv):
    h, w = pixels.shape[:2]; xy = (uv % 1)*np.array([w, h])-.5
    lo = np.floor(xy).astype(np.int64); f = xy-lo
    a = pixels[lo[..., 1] % h, lo[..., 0] % w]
    b = pixels[lo[..., 1] % h, (lo[..., 0]+1) % w]
    c = pixels[(lo[..., 1]+1) % h, lo[..., 0] % w]
    d = pixels[(lo[..., 1]+1) % h, (lo[..., 0]+1) % w]
    return (a*(1-f[..., 0, None])+b*f[..., 0, None])*(1-f[..., 1, None])+(c*(1-f[..., 0, None])+d*f[..., 0, None])*f[..., 1, None]


def png(image):
    data = BytesIO(); image.save(data, format='PNG'); return data.getvalue()


def register(builder, build, materials):
    from amberwood import materials as MAT, gltf as G
    import preview
    sets = preview.texture_sets(); providers = {}
    recipes = build.four_corner_materials
    for name in materials:
        for label in ('base', 'paint'):
            material = recipes[name][label+'Material']
            if material in providers:
                continue
            spec = MAT.BY_NAME[MAT.base_material(material)]
            images = sets[spec.texture].images()
            def read(suffix, default):
                blob = images.get(spec.texture+suffix)
                return Image.open(BytesIO(blob)).convert('RGB') if blob else Image.new('RGB', (1, 1), default)
            providers[material] = {'albedo': read('_basecolor', (255, 255, 255)),
                'normal': read('_normal', (128, 128, 255)), 'orm': read('_orm', (255, 255, 0)),
                'baseColorFactor': spec.base_color, 'normalScale': spec.normal_scale,
                'roughnessFactor': spec.roughness, 'metallicFactor': spec.metallic}
    image_ids = set()
    for name in sorted(materials):
        images = bake(recipes[name], providers)
        for key, image in images.items():
            image_ids.add(builder.add_image(name+'_'+key, png(image)))
        builder.add_material(G.Material(name, base_color=(1., 1., 1., 1.), metallic=1., roughness=1.,
            base_color_texture=name+'_albedo', normal_texture=name+'_normal', orm_texture=name+'_orm',
            normal_scale=1., alpha_mode='OPAQUE'))
    clamp_images(builder, image_ids)


def clamp_images(builder, image_ids):
    """This nonperiodic geographic bake must not wrap at any mip level.

    Use a Four-local sampler for only its new images. Native repeated recipe
    textures and every existing sampler retain their original definitions.
    """
    sampler = len(builder._samplers)
    builder._samplers.append({'magFilter': 9729, 'minFilter': 9987,
                             'wrapS': 33071, 'wrapT': 33071})
    for texture in builder._textures:
        if texture['source'] in image_ids:
            texture['sampler'] = sampler
