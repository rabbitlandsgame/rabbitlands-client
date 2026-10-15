/* Offline software rasteriser used to art-direct and verify Amberwood.
 *
 * This is a preview renderer, not the game renderer. It exists because the
 * build environment has no GPU and no Godot binary, and the region still has
 * to be looked at from the player's eye level while it is being authored.
 *
 * Pipeline: shadow-map depth pass -> forward z-buffered pass with bilinear
 * texture sampling, alpha-mask cut-out, hemispheric ambient, one directional
 * sun with PCF shadows, Blinn specular, and height-attenuated distance fog.
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef struct {
    float base[4];
    float roughness;
    float metallic;
    float emissive[3];
    int   albedo_layer;   /* -1 = none */
    int   orm_layer;      /* -1 = none */
    int   alpha_mode;     /* 0 opaque, 1 mask, 2 blend */
    float alpha_cutoff;
    int   double_sided;
} Material;

typedef struct {
    const float *positions;   /* 3 * vertex_count */
    const float *normals;
    const float *uvs;
    const int32_t *indices;   /* 3 * triangle_count */
    const int32_t *tri_material;
    int vertex_count;
    int triangle_count;
} Geometry;

typedef struct {
    const uint8_t *data;      /* layers * size * size * 4 */
    int size;
    int layers;
} TextureArray;

static inline float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static void sample_bilinear(const TextureArray *tex, int layer, float u, float v,
                            float out[4]) {
    int s = tex->size;
    float x = u * s - 0.5f;
    float y = v * s - 0.5f;
    int x0 = (int)floorf(x), y0 = (int)floorf(y);
    float fx = x - x0, fy = y - y0;
    const uint8_t *base = tex->data + (size_t)layer * s * s * 4;
    float acc[4] = {0, 0, 0, 0};
    for (int j = 0; j < 2; ++j) {
        for (int i = 0; i < 2; ++i) {
            int xi = ((x0 + i) % s + s) % s;
            int yi = ((y0 + j) % s + s) % s;
            const uint8_t *p = base + ((size_t)yi * s + xi) * 4;
            float w = (i ? fx : 1.0f - fx) * (j ? fy : 1.0f - fy);
            acc[0] += w * p[0]; acc[1] += w * p[1];
            acc[2] += w * p[2]; acc[3] += w * p[3];
        }
    }
    out[0] = acc[0] / 255.0f; out[1] = acc[1] / 255.0f;
    out[2] = acc[2] / 255.0f; out[3] = acc[3] / 255.0f;
}

/* ---- matrix helpers (column-major 4x4 applied as m * v) ---- */
static void mat_mul_vec4(const float *m, const float *v, float *out) {
    for (int r = 0; r < 4; ++r)
        out[r] = m[r * 4 + 0] * v[0] + m[r * 4 + 1] * v[1]
               + m[r * 4 + 2] * v[2] + m[r * 4 + 3] * v[3];
}

typedef struct {
    float clip[4];
    float world[3];
    float normal[3];
    float uv[2];
    float color[4];
} Vertex;

static void lerp_vertex(const Vertex *a, const Vertex *b, float t, Vertex *out) {
    for (int i = 0; i < 4; ++i) out->clip[i] = a->clip[i] + (b->clip[i] - a->clip[i]) * t;
    for (int i = 0; i < 3; ++i) out->world[i] = a->world[i] + (b->world[i] - a->world[i]) * t;
    for (int i = 0; i < 3; ++i) out->normal[i] = a->normal[i] + (b->normal[i] - a->normal[i]) * t;
    for (int i = 0; i < 2; ++i) out->uv[i] = a->uv[i] + (b->uv[i] - a->uv[i]) * t;
    for (int i = 0; i < 4; ++i) out->color[i] = a->color[i] + (b->color[i] - a->color[i]) * t;
}

/* clip a polygon against w > epsilon (near plane) */
static int clip_near(Vertex *poly, int count, Vertex *out) {
    const float eps = 1e-4f;
    int n = 0;
    for (int i = 0; i < count; ++i) {
        const Vertex *a = &poly[i];
        const Vertex *b = &poly[(i + 1) % count];
        float da = a->clip[3] - eps;
        float db = b->clip[3] - eps;
        if (da >= 0) out[n++] = *a;
        if ((da >= 0) != (db >= 0)) {
            float t = da / (da - db);
            lerp_vertex(a, b, t, &out[n++]);
        }
    }
    return n;
}

/* ---------------- shadow pass ---------------- */
void render_shadow(const Geometry *geo, const float *light_matrix,
                   float *depth, int size) {
    for (int i = 0; i < size * size; ++i) depth[i] = 1e30f;
    for (int t = 0; t < geo->triangle_count; ++t) {
        Vertex poly[8], clipped[8];
        for (int k = 0; k < 3; ++k) {
            int vi = geo->indices[t * 3 + k];
            float v[4] = {geo->positions[vi * 3], geo->positions[vi * 3 + 1],
                          geo->positions[vi * 3 + 2], 1.0f};
            mat_mul_vec4(light_matrix, v, poly[k].clip);
            poly[k].world[0] = v[0]; poly[k].world[1] = v[1]; poly[k].world[2] = v[2];
        }
        int n = clip_near(poly, 3, clipped);
        for (int f = 2; f < n; ++f) {
            Vertex *tri[3] = {&clipped[0], &clipped[f - 1], &clipped[f]};
            float sx[3], sy[3], sz[3];
            for (int k = 0; k < 3; ++k) {
                float w = tri[k]->clip[3];
                sx[k] = (tri[k]->clip[0] / w * 0.5f + 0.5f) * size;
                sy[k] = (1.0f - (tri[k]->clip[1] / w * 0.5f + 0.5f)) * size;
                sz[k] = tri[k]->clip[2];   /* orthographic light depth */
            }
            float area = (sx[1] - sx[0]) * (sy[2] - sy[0]) - (sx[2] - sx[0]) * (sy[1] - sy[0]);
            if (fabsf(area) < 1e-9f) continue;
            int minx = (int)floorf(fminf(fminf(sx[0], sx[1]), sx[2]));
            int maxx = (int)ceilf(fmaxf(fmaxf(sx[0], sx[1]), sx[2]));
            int miny = (int)floorf(fminf(fminf(sy[0], sy[1]), sy[2]));
            int maxy = (int)ceilf(fmaxf(fmaxf(sy[0], sy[1]), sy[2]));
            if (minx < 0) minx = 0; if (miny < 0) miny = 0;
            if (maxx > size - 1) maxx = size - 1;
            if (maxy > size - 1) maxy = size - 1;
            float inv_area = 1.0f / area;
            for (int y = miny; y <= maxy; ++y) {
                for (int x = minx; x <= maxx; ++x) {
                    float px = x + 0.5f, py = y + 0.5f;
                    float w0 = ((sx[1] - px) * (sy[2] - py) - (sx[2] - px) * (sy[1] - py)) * inv_area;
                    float w1 = ((sx[2] - px) * (sy[0] - py) - (sx[0] - px) * (sy[2] - py)) * inv_area;
                    float w2 = 1.0f - w0 - w1;
                    if (w0 < 0 || w1 < 0 || w2 < 0) continue;
                    float z = w0 * sz[0] + w1 * sz[1] + w2 * sz[2];
                    int idx = y * size + x;
                    if (z < depth[idx]) depth[idx] = z;
                }
            }
        }
    }
}

/* ---------------- main pass ---------------- */
typedef struct {
    float sun_direction[3];   /* points from surface toward the sun */
    float sun_color[3];
    float sky_color[3];
    float ground_color[3];
    float fog_color[3];
    float fog_density;
    float fog_height_falloff;
    float exposure;
    float ambient_strength;
    float shadow_bias;
    float shadow_strength;
} Lighting;

static void render_scene_impl(const Geometry *geo, const Material *materials, int material_count,
                  const TextureArray *tex, const float *view_projection,
                  const float *camera_position, const Lighting *light,
                  const float *light_matrix, const float *shadow_depth, int shadow_size,
                  float *color_buffer, float *depth_buffer, int width, int height,
                  const float *vertex_colors) {
    const int orthographic = fabsf(view_projection[12]) + fabsf(view_projection[13])
        + fabsf(view_projection[14]) < 1e-9f;
    for (int i = 0; i < width * height; ++i) depth_buffer[i] = 1e30f;

    for (int t = 0; t < geo->triangle_count; ++t) {
        int material_index = geo->tri_material[t];
        if (material_index < 0 || material_index >= material_count) continue;
        const Material *mat = &materials[material_index];
        Vertex poly[8], clipped[8];
        for (int k = 0; k < 3; ++k) {
            int vi = geo->indices[t * 3 + k];
            float v[4] = {geo->positions[vi * 3], geo->positions[vi * 3 + 1],
                          geo->positions[vi * 3 + 2], 1.0f};
            mat_mul_vec4(view_projection, v, poly[k].clip);
            poly[k].world[0] = v[0]; poly[k].world[1] = v[1]; poly[k].world[2] = v[2];
            poly[k].normal[0] = geo->normals[vi * 3];
            poly[k].normal[1] = geo->normals[vi * 3 + 1];
            poly[k].normal[2] = geo->normals[vi * 3 + 2];
            poly[k].uv[0] = geo->uvs[vi * 2];
            poly[k].uv[1] = geo->uvs[vi * 2 + 1];
            for (int c = 0; c < 4; ++c)
                poly[k].color[c] = vertex_colors ? vertex_colors[vi * 4 + c] : 1.0f;
        }
        int n = clip_near(poly, 3, clipped);
        for (int f = 2; f < n; ++f) {
            Vertex *tri[3] = {&clipped[0], &clipped[f - 1], &clipped[f]};
            float sx[3], sy[3], iw[3];
            for (int k = 0; k < 3; ++k) {
                float w = tri[k]->clip[3];
                sx[k] = (tri[k]->clip[0] / w * 0.5f + 0.5f) * width;
                sy[k] = (1.0f - (tri[k]->clip[1] / w * 0.5f + 0.5f)) * height;
                iw[k] = 1.0f / w;
            }
            float area = (sx[1] - sx[0]) * (sy[2] - sy[0]) - (sx[2] - sx[0]) * (sy[1] - sy[0]);
            if (fabsf(area) < 1e-9f) continue;
            if (area > 0 && !mat->double_sided) continue;   /* backface cull (CCW front) */
            int minx = (int)floorf(fminf(fminf(sx[0], sx[1]), sx[2]));
            int maxx = (int)ceilf(fmaxf(fmaxf(sx[0], sx[1]), sx[2]));
            int miny = (int)floorf(fminf(fminf(sy[0], sy[1]), sy[2]));
            int maxy = (int)ceilf(fmaxf(fmaxf(sy[0], sy[1]), sy[2]));
            if (minx < 0) minx = 0; if (miny < 0) miny = 0;
            if (maxx > width - 1) maxx = width - 1;
            if (maxy > height - 1) maxy = height - 1;
            if (minx > maxx || miny > maxy) continue;
            float inv_area = 1.0f / area;

            for (int y = miny; y <= maxy; ++y) {
                for (int x = minx; x <= maxx; ++x) {
                    float px = x + 0.5f, py = y + 0.5f;
                    float b0 = ((sx[1] - px) * (sy[2] - py) - (sx[2] - px) * (sy[1] - py)) * inv_area;
                    float b1 = ((sx[2] - px) * (sy[0] - py) - (sx[0] - px) * (sy[2] - py)) * inv_area;
                    float b2 = 1.0f - b0 - b1;
                    if (b0 < 0 || b1 < 0 || b2 < 0) continue;
                    float w_interp = b0 * iw[0] + b1 * iw[1] + b2 * iw[2];
                    if (w_interp <= 0) continue;
                    /* Perspective uses camera distance; an orthographic camera
                     * has constant clip.w and must compare interpolated clip.z.
                     * Otherwise the first triangle wins even below a roof. */
                    float depth = orthographic
                        ? b0 * tri[0]->clip[2] * iw[0]
                          + b1 * tri[1]->clip[2] * iw[1]
                          + b2 * tri[2]->clip[2] * iw[2]
                        : 1.0f / w_interp;
                    int idx = y * width + x;
                    if (depth >= depth_buffer[idx]) continue;

                    float p0 = b0 * iw[0] / w_interp;
                    float p1 = b1 * iw[1] / w_interp;
                    float p2 = b2 * iw[2] / w_interp;

                    float uv[2];
                    uv[0] = p0 * tri[0]->uv[0] + p1 * tri[1]->uv[0] + p2 * tri[2]->uv[0];
                    uv[1] = p0 * tri[0]->uv[1] + p1 * tri[1]->uv[1] + p2 * tri[2]->uv[1];

                    float albedo[4] = {mat->base[0], mat->base[1], mat->base[2], mat->base[3]};
                    if (mat->albedo_layer >= 0) {
                        float texel[4];
                        sample_bilinear(tex, mat->albedo_layer, uv[0], uv[1], texel);
                        albedo[0] *= texel[0]; albedo[1] *= texel[1];
                        albedo[2] *= texel[2]; albedo[3] *= texel[3];
                    }
                    for (int c = 0; c < 4; ++c)
                        albedo[c] *= p0 * tri[0]->color[c]
                            + p1 * tri[1]->color[c] + p2 * tri[2]->color[c];
                    if (mat->alpha_mode == 1 && albedo[3] < mat->alpha_cutoff) continue;

                    float occlusion = 1.0f, roughness = mat->roughness;
                    if (mat->orm_layer >= 0) {
                        float orm[4];
                        sample_bilinear(tex, mat->orm_layer, uv[0], uv[1], orm);
                        occlusion = 0.35f + 0.65f * orm[0];
                        roughness = clampf(roughness * (0.55f + 0.9f * orm[1]), 0.03f, 1.0f);
                    }

                    float nx = p0 * tri[0]->normal[0] + p1 * tri[1]->normal[0] + p2 * tri[2]->normal[0];
                    float ny = p0 * tri[0]->normal[1] + p1 * tri[1]->normal[1] + p2 * tri[2]->normal[1];
                    float nz = p0 * tri[0]->normal[2] + p1 * tri[1]->normal[2] + p2 * tri[2]->normal[2];
                    float nl = sqrtf(nx * nx + ny * ny + nz * nz);
                    if (nl < 1e-6f) { nx = 0; ny = 1; nz = 0; nl = 1; }
                    nx /= nl; ny /= nl; nz /= nl;

                    float wx = p0 * tri[0]->world[0] + p1 * tri[1]->world[0] + p2 * tri[2]->world[0];
                    float wy = p0 * tri[0]->world[1] + p1 * tri[1]->world[1] + p2 * tri[2]->world[1];
                    float wz = p0 * tri[0]->world[2] + p1 * tri[1]->world[2] + p2 * tri[2]->world[2];

                    float vx = camera_position[0] - wx;
                    float vy = camera_position[1] - wy;
                    float vz = camera_position[2] - wz;
                    float vlen = sqrtf(vx * vx + vy * vy + vz * vz) + 1e-6f;
                    vx /= vlen; vy /= vlen; vz /= vlen;

                    /* two-sided shading for cut-out foliage */
                    if (mat->double_sided) {
                        float facing = nx * vx + ny * vy + nz * vz;
                        if (facing < 0) { nx = -nx; ny = -ny; nz = -nz; }
                    }

                    const float *L = light->sun_direction;
                    float ndl = nx * L[0] + ny * L[1] + nz * L[2];
                    float wrapped = clampf((ndl + 0.32f) / 1.32f, 0.0f, 1.0f);
                    ndl = clampf(ndl, 0.0f, 1.0f);

                    float shadow = 1.0f;
                    if (shadow_depth) {
                        float v[4] = {wx, wy, wz, 1.0f}, lc[4];
                        mat_mul_vec4(light_matrix, v, lc);
                        if (lc[3] > 0) {
                            float lx = (lc[0] / lc[3] * 0.5f + 0.5f) * shadow_size;
                            float ly = (1.0f - (lc[1] / lc[3] * 0.5f + 0.5f)) * shadow_size;
                            float lz = lc[2];
                            if (lx >= 1 && ly >= 1 && lx < shadow_size - 1 && ly < shadow_size - 1) {
                                float lit = 0.0f;
                                int taps = 0;
                                for (int dy = -1; dy <= 1; ++dy)
                                    for (int dx = -1; dx <= 1; ++dx) {
                                        int si = ((int)ly + dy) * shadow_size + ((int)lx + dx);
                                        lit += (lz - light->shadow_bias <= shadow_depth[si]) ? 1.0f : 0.0f;
                                        taps++;
                                    }
                                shadow = lit / taps;
                                shadow = 1.0f - (1.0f - shadow) * light->shadow_strength;
                            }
                        }
                    }

                    float hemi = 0.5f + 0.5f * ny;
                    float ambient[3];
                    for (int c = 0; c < 3; ++c)
                        ambient[c] = (light->ground_color[c] * (1.0f - hemi)
                                      + light->sky_color[c] * hemi)
                                     * light->ambient_strength * occlusion;

                    float diffuse = (mat->double_sided ? wrapped : ndl) * shadow;

                    float hx = L[0] + vx, hy = L[1] + vy, hz = L[2] + vz;
                    float hlen = sqrtf(hx * hx + hy * hy + hz * hz) + 1e-6f;
                    hx /= hlen; hy /= hlen; hz /= hlen;
                    float ndh = clampf(nx * hx + ny * hy + nz * hz, 0.0f, 1.0f);
                    float gloss = 2.0f / (roughness * roughness + 1e-4f);
                    if (gloss > 512.0f) gloss = 512.0f;
                    float spec = powf(ndh, gloss) * (1.0f - roughness) * shadow * ndl;

                    float out[3];
                    for (int c = 0; c < 3; ++c) {
                        float lit = albedo[c] * (ambient[c] + light->sun_color[c] * diffuse);
                        lit += light->sun_color[c] * spec * (0.25f + 0.75f * mat->metallic);
                        lit += mat->emissive[c];
                        out[c] = lit;
                    }

                    /* height-attenuated exponential fog */
                    float height_factor = expf(-clampf(wy, -50.0f, 400.0f) * light->fog_height_falloff);
                    float fog = 1.0f - expf(-depth * light->fog_density * height_factor);
                    fog = clampf(fog, 0.0f, 1.0f);
                    for (int c = 0; c < 3; ++c)
                        out[c] = out[c] * (1.0f - fog) + light->fog_color[c] * fog;

                    depth_buffer[idx] = depth;
                    color_buffer[idx * 3 + 0] = out[0];
                    color_buffer[idx * 3 + 1] = out[1];
                    color_buffer[idx * 3 + 2] = out[2];
                }
            }
        }
    }
}

/* Keep the original ABI for every existing preview builder. */
void render_scene(const Geometry *geo, const Material *materials, int material_count,
                  const TextureArray *tex, const float *view_projection,
                  const float *camera_position, const Lighting *light,
                  const float *light_matrix, const float *shadow_depth, int shadow_size,
                  float *color_buffer, float *depth_buffer, int width, int height) {
    render_scene_impl(geo, materials, material_count, tex, view_projection,
        camera_position, light, light_matrix, shadow_depth, shadow_size,
        color_buffer, depth_buffer, width, height, NULL);
}

/* GLB vertex colors are optional; the caller supplies four floats per vertex. */
void render_scene_colored(const Geometry *geo, const Material *materials, int material_count,
                  const TextureArray *tex, const float *view_projection,
                  const float *camera_position, const Lighting *light,
                  const float *light_matrix, const float *shadow_depth, int shadow_size,
                  float *color_buffer, float *depth_buffer, int width, int height,
                  const float *vertex_colors) {
    render_scene_impl(geo, materials, material_count, tex, view_projection,
        camera_position, light, light_matrix, shadow_depth, shadow_size,
        color_buffer, depth_buffer, width, height, vertex_colors);
}
