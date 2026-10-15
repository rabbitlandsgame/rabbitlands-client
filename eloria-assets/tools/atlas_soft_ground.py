"""Deterministic atlas-only specialization of the frozen CPU rasterizer.

No copy of the engine is maintained here. Verified fragment and sampler hooks are
expanded for the runtime soft-ground shader and opaque glTF clamp sampling, then compiled into the requested
artifact cache, and recorded with its source/compiler/binary provenance.
The shared raster source and library are never written.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

VERSION = 2
HOOK = '''                    for (int c = 0; c < 4; ++c)
                        albedo[c] *= p0 * tri[0]->color[c]
                            + p1 * tri[1]->color[c] + p2 * tri[2]->color[c];'''
_LOADED = {}
SAMPLER_HOOK = '/* ---- matrix helpers (column-major 4x4 applied as m * v) ---- */'
ALBEDO_HOOK = 'sample_bilinear(tex, mat->albedo_layer, uv[0], uv[1], texel);'
CLAMP_S = 4
CLAMP_T = 8


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def specialize(source: str, shader: str) -> str:
    """Fail closed if either the fragment hook or shader semantics changed."""
    if source.count(HOOK) != 1:
        raise ValueError('Atlas soft-ground hook must occur exactly once in frozen raster.c')
    patterns = (
        r'vec2 grain = floor\(UV \* ([\d.]+)\);',
        r'float threshold = fract\(sin\(dot\(grain, vec2\(([\d.]+),([\d.]+)\)\)\) \* ([\d.]+)\);',
        r'if \(COLOR\.a < threshold\) \{ discard; \}',
        r'ALBEDO = texture\(soil_texture, UV\)\.rgb \* soil_color\.rgb;',
    )
    matches = [list(re.finditer(pattern, shader)) for pattern in patterns]
    if any(len(items) != 1 for items in matches):
        raise ValueError('Runtime soft-ground shader no longer matches supported UV-dither semantics')
    scale = matches[0][0].group(1)
    x, y, multiplier = matches[1][0].groups()
    fragment = f'''                    if (mat->alpha_mode == 3) {{
                        /* Runtime soft_ground.gdshader: UV-locked opaque discard.
                         * Only COLOR.a controls coverage; RGB/texture alpha do not. */
                        float gx = floorf(uv[0] * {scale}f);
                        float gy = floorf(uv[1] * {scale}f);
                        float phase = gx * {x}f + gy * {y}f;
                        float random_value = sinf(phase) * {multiplier}f;
                        float threshold = random_value - floorf(random_value);
                        float coverage = p0 * tri[0]->color[3]
                            + p1 * tri[1]->color[3] + p2 * tri[2]->color[3];
                        if (coverage < threshold) continue;
                    }} else {{
{HOOK}
                    }}'''
    for hook in (SAMPLER_HOOK, ALBEDO_HOOK):
        if source.count(hook) != 1:
            raise ValueError('Atlas clamp sampler hook must occur exactly once in frozen raster.c')
    sampler = '''/* Atlas-only flags in the existing alpha_mode integer: opaque clamp S=4, T=8.
 * Clamp to edge texel centres before the unchanged repeat bilinear sampler.
 * Repeat flags are zero, preserving its original arithmetic and mask semantics. */
static void atlas_sample_albedo(const TextureArray *tex, int layer, float u, float v,
                                float out[4], int flags) {
    float half_texel = 0.5f / tex->size;
    if (flags & 4) u = clampf(u, half_texel, 1.0f - half_texel);
    if (flags & 8) v = clampf(v, half_texel, 1.0f - half_texel);
    sample_bilinear(tex, layer, u, v, out);
}

'''
    return (source.replace(HOOK, fragment).replace(SAMPLER_HOOK, sampler+SAMPLER_HOOK)
            .replace(ALBEDO_HOOK, 'atlas_sample_albedo(tex, mat->albedo_layer, uv[0], uv[1], texel, mat->alpha_mode);'))


def compiler():
    requested = os.environ.get('ELORIA_ATLAS_CC')
    found = (shutil.which(requested) or requested) if requested else (
        shutil.which('gcc') or shutil.which('clang') or shutil.which('cc'))
    if not found and os.name == 'nt':
        for path in ('C:/msys64/mingw64/bin/gcc.exe', 'C:/msys64/ucrt64/bin/gcc.exe'):
            if Path(path).is_file():
                found = path
                break
    if not found:
        raise RuntimeError('Atlas soft-ground renderer needs a C compiler; set ELORIA_ATLAS_CC to gcc or clang')
    path = Path(found).resolve()
    if not path.is_file():
        raise RuntimeError(f'Atlas C compiler does not exist: {path}')
    return path


def load(source_path: Path, shader_path: Path, cache: Path):
    source_bytes, shader_bytes = source_path.read_bytes(), shader_path.read_bytes()
    source = specialize(source_bytes.decode('utf-8').replace('\r\n','\n'),
                        shader_bytes.decode('utf-8'))
    cc = compiler()
    flags = ['-O3', '-ffast-math', '-shared']
    flags += ['-static-libgcc', '-static', '-Wl,--no-insert-timestamp',
              '-Wl,--image-base,0x180000000'] if os.name == 'nt' else ['-fPIC']
    fingerprint = {
        'version': VERSION, 'adapterSha256': sha(__file__),
        'baseRasterSha256': hashlib.sha256(source_bytes).hexdigest(),
        'runtimeShaderSha256': hashlib.sha256(shader_bytes).hexdigest(),
        'specializedSourceSha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
        'compilerSha256': sha(cc), 'flags': flags,
    }
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    folder = cache.resolve()/key
    if str(folder) in _LOADED:
        return _LOADED[str(folder)]
    library = folder/'atlas-raster.so'
    receipt = folder/'build.json'
    generated = folder/'atlas-raster.c'
    if receipt.exists():
        proof = json.loads(receipt.read_text(encoding='utf-8'))
        if any(proof.get(k) != v for k,v in fingerprint.items()) or not library.is_file() or not generated.is_file():
            raise RuntimeError(f'Atlas native cache provenance is incomplete or stale: {folder}')
        if sha(library) != proof['librarySha256'] or sha(generated) != fingerprint['specializedSourceSha256']:
            raise RuntimeError(f'Atlas native cache bytes changed: {folder}')
    else:
        folder.mkdir(parents=True, exist_ok=True)
        generated.write_text(source, encoding='utf-8', newline='\n')
        env = dict(os.environ)
        env['PATH'] = str(cc.parent)+os.pathsep+env.get('PATH','')
        temporary = folder/'atlas-raster-building.so'
        command = [str(cc), *flags, '-o', str(temporary), str(generated), '-lm']
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        (folder/'compiler.log').write_text(result.stdout+result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(f'Atlas native specialization failed: {result.stderr}')
        temporary.replace(library)
        version = subprocess.run([str(cc),'--version'], capture_output=True, text=True, check=True, env=env)
        proof = dict(fingerprint, compiler=str(cc), compilerVersion=version.stdout.splitlines()[0],
                     command=command, librarySha256=sha(library))
        receipt.write_text(json.dumps(proof,indent=2)+'\n', encoding='utf-8')
    lib = ctypes.CDLL(str(library))
    if not hasattr(lib, 'render_scene_colored'):
        raise RuntimeError('Atlas native specialization has no colored raster entry point')
    _LOADED[str(folder)] = lib, dict(proof, cacheReceipt=str(receipt))
    return _LOADED[str(folder)]


def publication_provenance(proof):
    """Portable certificate fields; artifact/compiler paths remain in render reports."""
    return {k:v for k,v in proof.items() if k not in ('compiler','command','cacheReceipt')}
