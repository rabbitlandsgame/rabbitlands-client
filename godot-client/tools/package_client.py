#!/usr/bin/env python3
"""Build the client package that installs Rabbit Lands on another Windows or Linux machine.

Added 2026-09-16 for Rabbit Lands Client.

    python godot-client/tools/package_client.py                     # Windows, origin/develop
    python godot-client/tools/package_client.py --platform linux    # Linux
    python godot-client/tools/package_client.py --ref HEAD --installer

The package is built from a commit, never from a working tree. The main
checkout is shared with other sessions and always holds someone's unfinished
edits, so the script keeps its own detached worktree (dist/.build/client-src
beside the repositories), forces it to the commit, imports it and exports it.
Nothing it does touches the checkout it is run from.

What goes in, and why it is more than an export:

  app/RabbitLands.exe (Windows) or app/RabbitLands.x86_64 (Linux), app/RabbitLands.pck
      The Godot export. Scripts, scenes, UI art and data. Linux needs the
      official 4.7.2 export templates installed beside the Windows ones.
      The textures the world's 3D scenes sample (see scene_textures) are
      imported VRAM-compressed with mipmaps, normal maps red-green. The
      editor gives a texture those settings only once it has drawn a
      material using it, and a headless import draws nothing, so the
      packager writes them: a fresh build worktree ships what one an editor
      session touched does, not lossless textures without mipmaps.
      The map editor's region sources (world_authoring: the region scenes,
      their prototype models and textures, the territory catalogs) are not
      exported. Only the editor and its plugins open them, never the game,
      and they were 1.77 GB of the 2.11 GB PCK once the isles joined them
      (EDITOR_ONLY_PCK_DIRS, check_editor_sources_unpacked).
  app/assets, app/data, app/schemas
      Loose copies, and every actor file ships once (or not at all). Actor
      models, hair and equipment are opened with GLTFDocument from
      ProjectSettings.globalize_path("res://assets/..."). An exported build
      has no resource path, so that is a path relative to the folder the game
      starts in, which ResourceLoader never maps back into the pack:
      GlbSceneCache's imported-scene route is only taken in an editor
      checkout, and an imported scene in the PCK would never be read. The
      glTF files therefore ship loose only and are never imported (a folder
      with nothing for the PCK gets a .gdignore, which also keeps ~4 GB out of
      the import; elsewhere each glTF gets a "skip" import). Two kinds of
      actor file are read through ResourceLoader and ship in the PCK only:
      the face masks, which models.json names and replicated_actor_3d.gd
      load()s, and the textures the equipment glTFs name by relative URI.
      GLTFDocument tries ResourceLoader first for an external image, and a
      relative path resolves to res://, so the packager writes those
      textures' import settings (VRAM-compressed, mipmapped: what the editor
      gives a texture it sees used in 3D) and the game uploads the imported
      texture instead of decoding the JPEG with no mip chain. GLTFDocument
      then reads each such texture back with get_image(), a RenderingServer
      call: it stalls the GPU on the main thread and, from a worker, waits
      for the main thread, so an equipment glTF must never be parsed on a
      worker the main thread joins (GlbSceneCache, NativeAnimationImporter).
      Actor images that nothing names - no glTF URI, no catalog, no client
      source, no other text the package carries; the editor's extracted
      copies of embedded glTF images and the race and neck texture sources
      the race models were built from - ship nowhere.
      Other imported resources - audio, UI and world images - ship once too
      (W2-UD-02, loose_duplicate_plan): the export packs each as its .import
      remap and products, so a loose copy serves only a raw read (FileAccess,
      Image.load_from_file, a path from globalize_path), and it is left out
      unless one can happen. That is decided from the running client's path
      literals, each followed to the resource system or else counted as read
      raw, from glTF URIs (a raw read unless the AW-03 actor parse takes the
      image from the import), from the data a package carries, and from the
      installer's own reads of the stage (check_loose_duplicates).
      Creature GLBs ship as verified ordinary uncompressed GLBs after native
      cooking. Their optimized meshes and curves reduce storage without a
      per-load decompression step. Legacy compressed payload readers remain
      compatible with older installs.
      The RL head (the High Human head) ships the same two ways: its head,
      hair and beard GLBs (native/rl_heads) loose only, and its maps
      (native/rl_head_textures, LOADED_IMAGE_FOLDERS) in the PCK only, each
      imported VRAM-compressed with mipmaps by the settings committed beside
      it. Its interactive lab (prototypes/rl_heads) is not exported. The
      hair and beard GLBs lose their embedded copies of those maps in the
      build tree before the import (AT-C0, strip_rl_head_stage and
      tools/strip_rl_head_images.py; check_rl_head_strip_pack after the
      export): the RL contract's shader materials sample the PCK maps, so
      the copies were only decoded and uploaded unused. Receipt:
      logs/rl-head-strip.json.
  eloria-assets/maps, eloria-assets/concepts
      "res://../eloria-assets/..." resolves beside app/. Every map package (a
      folder holding world.json) ships without its authoring snapshots,
      comparison panels, references, captures, sources, reports and unused
      world-lod2.glb; any other file a shipped
      manifest or the map registry names is pulled in even if the filter
      dropped it.
  eloria-assets/maps/.../shared-assets/vram
      VRAM-compressed (BC7/BC5/BC1) copies of the shared map images, made at
      package time by tools/build_vram_textures.py (they are not tracked), so
      the client uploads them as they are instead of decoding each image to
      RGBA8. Checked against their index; --no-vram-textures leaves them out.
  app/assets/actors/native/<dir>/.../vram
      VRAM-compressed sidecars of the actor GLBs' embedded images
      (creatures, races, legacy hair, mounts, held props: ACTOR_SIDECAR_DIRS),
      one index per GLB directory, made at package time by the commit's
      build_vram_textures.py --actor-dir from the build tree's GLBs and
      staged loose beside the staged GLBs, where src/actors/actor_images.gd
      looks (AT-C3, stage_actor_vram_textures). Every embedded image of every
      staged GLB there is indexed for the roles its GLBs sample it in, or
      excluded with a reason (check_actor_vram_coverage), and the smoke
      launch decodes and decompresses one (ELORIA_ACTOR_VRAM_SELF_TEST). They
      update as packages of their own (asset_packages.py actors-*-textures).
      Not release-enabled yet (ACTOR_SIDECARS_RELEASE_ENABLED): only a local
      package asked for with --actor-vram-textures builds them.
  eloria-assets/maps/_shared/meshes
      The prototype meshes map packages name instead of carrying
      (eloria-assets/tools/shared_meshes.py publishes each mesh that repeated
      across map files once, as maps/_shared/meshes/<sha256>.glb with an
      index.json beside it, and a manifest's "externalMeshes" names the ones
      its placements draw). The pool holds no world.json, so it is no map
      package and nothing of it ships by the folder rule: exactly the
      prototypes a shipped manifest names are staged, with the pool's index
      (the client reads a prototype's images from it) and the images a staged
      prototype names. Checked against the sha256 each manifest recorded
      (check_shared_meshes). The build then reports, without failing, how much
      map geometry is still copied between files (report_duplicate_geometry).

A map whose registry row is a client preview (PREVIEW_MAP_STATUSES: a
rebuilt-continent territory, a chunk-streamed package of up to 1.2 GB, with no
server map yet) is left out: its row is dropped from the build tree's registry
before the export, and its map folder is never staged.

A continent-v2 map the server serves (SERVED_V2_STATUSES) ships its client
package - the territory world.json, its chunks and the shared images they name
- and nothing the server alone reads: its collision.bin and served-grid.escg.gz
(SERVER_ONLY_FILES; the client never opens either, and sw_isle's collision.bin
alone is 16.7 MB) are not staged, the collision block of its manifests is not
followed for files, and the territory folder around the package (the editor's
stub world.json, the server content tables) is left out. Staged, the package
is checked for exactly that (check_served_packages).

Only files tracked at the commit are shipped. Before zipping, the package is
checked - every registry manifest, the files each manifest names, and every
external texture a GLB references must be present - and the exported game is
started headless once with a throwaway user directory, failing on any script
error. The Linux build is started under WSL (Ubuntu-24.04) when it is present.

Windows ships as a zip with .bat launchers. Linux ships as a .tar.gz with .sh
launchers: a zip made on Windows cannot mark the game executable.

--installer also compiles an Inno Setup installer (per-user, no admin, Start
menu shortcut, uninstaller) when ISCC.exe is available. Inno Setup is not part
of the repository: https://jrsoftware.org/isdl.php
"""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import macos_package
import tarfile
import tempfile
import time
import zipfile
import client_release
import release_storage
import runner_source
import benchmark_package
import client_runtime_package
import prepared_content_package
import creature_compression
import full_optimization_package
import release_world_preparation
import map_background_package
import strip_rl_head_images
import build_vram_textures as vram_tool
from road_ground_dependencies import dependencies as road_dependencies, RoadGroundDependencyError
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

CLIENT = Path(__file__).resolve().parents[1]
REPO = CLIENT.parent
PROJECT = REPO.parent
DIST = PROJECT / "dist"
GODOT_EXE = "Godot_v4.7.2-stable_win64_console.exe"
MARKER = ".eloria-package"
STORAGE = None  # Only runner_release.py supplies a bounded, disposable build context.
BENCHMARK_LINKS = False  # Local test packages reuse immutable staged asset bytes.
BENCHMARK_ACTOR_PLANS: dict[Path, dict] | None = None  # One local benchmark invocation only.
ASSET_REF = re.compile(r"res://\.\./(eloria-assets/[^\"'\s]+)")

# The installer's identity. Keep it fixed: Windows matches upgrades and the
# uninstaller entry on it.
INSTALLER_APP_ID = "{6B1E9F4C-3A52-4D8E-9C71-5E0B2F8A4D17}"
INSTALLER_MUTEX = "RabbitLandsSetup-" + INSTALLER_APP_ID.strip("{}")

# Leave local editing snapshots and review art in the repository, not in a
# release. These are folder defaults: an explicit client/manifest dependency
# still ships and is checked by shipped_eloria_assets, including road styles.
MAP_EXCLUDED_DIRS = {"authoring", "comparison", "references", "captures",
                     "godot-captures", "source", "sources", "qa", "reports",
                     "review", "renders"}
MAP_EXCLUDED_SUFFIXES = {".py", ".md", ".gd", ".c", ".txt", ".gitignore"}
# Reduced-detail map packages (world-lod2.glb, 335 MB across eleven maps) and
# their manifests and statistics. Manifests list them under lodGroups and the
# registry names Sunmane's under "lod2", but no client code loads either.
MAP_LOD_PACKAGE = re.compile(r"^(world-lod\d+|build-statistics-lod\d+)\b")
# Registry rows with these statuses are previews: never shipped (see the module notes).
PREVIEW_MAP_STATUSES = {"continent-v2-client-preview"}
# Registry rows with these statuses are continent-v2 maps the server serves: their client package ships without the
# files only the server reads (see the module notes).
SERVED_V2_STATUSES = {"continent-v2-served"}
SERVER_ONLY_FILES = {"collision.bin", "served-grid.escg.gz"}
REGISTRY_FILE = "godot-client/data/maps/registry.json"
# Manifest keys that describe provenance, or files the client never opens.
# conceptArt retains the source boards' provenance in the repository; runtime
# pictures/textures declared independently still enter the verified closure.
MANIFEST_SKIPPED_KEYS = {"sources", "provenance", "conceptArt", "knownLimitations", "lodGroups"}
# The manifest key naming the prototype meshes a package does not carry
# (eloria-assets/tools/shared_meshes.py): URI relative to the manifest's folder
# -> sha256 of the prototype GLB it names. The pool keeps index.json beside the
# prototypes; external_mesh_pool.gd reads a prototype's images from it.
SHARED_MESH_KEY = "externalMeshes"
SHARED_MESH_INDEX = "index.json"
FILE_LIKE = re.compile(r"^[^:*?\"<>|\s]+\.(glb|gltf|bin|json|webp|png|jpg|jpeg|gz|escg|ogg|wav)$", re.I)
# "Can't open file" is GLTFDocument's error when a loose actor GLB is missing.
# The last four are WARNING-level: an actor part that fell back rather than
# failed. A torso cover profile whose fingerprint does not match drops a whole
# reviewed surface (the packaged Orun male did, for every class loadout), and
# a scene that cannot be packed or a hairstyle that cannot be bound simply
# goes missing. None of them is a load error, so the old list let them pass.
SMOKE_FAILURES = ("SCRIPT ERROR", "Parse Error", "Failed to load script",
                  "No loader found", "Cannot open file", "Can't open file",
                  "Failed loading resource",
                  "Ignoring torso cover profile", "glb cache: pack failed",
                  "Native hairstyle failed to load",
                  "Fitted hairstyle has an incompatible skeleton", "Creature payload rejected")

ACTOR_ROOT = "godot-client/assets/actors/native"
ACTOR_CATALOGS = ("godot-client/data/actors/models.json", "godot-client/data/actors/equipment.json")
GLTF_SUFFIXES = (".glb", ".gltf")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
# Files the export's include filter packs whether or not they are imported.
PLAIN_EXPORT_SUFFIXES = (".json", ".bin")
# Client files whose string literals may name an actor file the game opens:
# the scripts, scenes, resources, shaders and settings the export packs from
# anywhere in the project (src, addons, assets), and the native extension's
# sources. The export's exclude filter keeps docs, tests and tools out of a
# package, so nothing a package runs is written there. It keeps the map
# editor's region sources (world_authoring) out too, but they are still read
# here and by scene_textures: a name there only keeps a file, never drops one.
SOURCE_SUFFIXES = (".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc", ".godot", ".cfg",
                   ".gdextension", ".cpp", ".h")
UNSHIPPED_CLIENT_DIRS = ("godot-client/docs/", "godot-client/tests/", "godot-client/tools/",
                         "godot-client/test-artifacts/")
# Data the game reads as text beside its JSON (the localisation table).
PLAIN_TEXT_SUFFIXES = (".csv", ".txt")
# A string literal in either quote style (GDScript takes both).
SOURCE_LITERAL = re.compile(r"""(["'])((?:(?!\1)[^\\\n])*)\1""")
# Where a string names a path under the actor tree: "res://assets/actors/...",
# "assets/actors", ".../godot-client/assets/actors/..." - not eloria-assets/actors.
ACTOR_PATH_IN_TEXT = re.compile(r"(?<![\w.-])assets/actors(?=/|$)", re.I)
# A path literal compared against another path reaches nothing.
COMPARED_BEFORE = re.compile(r"(begins_with|ends_with|contains|find|rfind|==|!=)\(?\s*$")
# A literal joined to more text builds a path from its start.
JOINED_AFTER = re.compile(r"\s*(\+|%|\.path_join|\.plus_file|\.format)")
# A literal inside a "/".join([...]) list is one piece of a built path.
JOIN_LIST_BEFORE = re.compile(r"\.join\(\s*\[[^\]\)]*$")

# Actor folders whose glTF files' URI-named textures are imported into the
# PCK (owner call, 2026-10-05: "keep equipment textures imported", +95 MB).
# GLTFDocument asks ResourceLoader for an external image before it reads the
# file, and the relative path an export globalizes to resolves to res://, so
# the 384 equipment textures load VRAM-compressed with mip chains, as the
# stage-1 package (every actor imported) loaded them, rather than as raw JPEG
# decodes without mips. Other folders' URI images (the 12 the shared
# Superhero glTFs name; no catalog names those glTFs) stay loose, as before.
IMPORTED_URI_TEXTURE_FOLDERS = ("equipment",)
# Actor folders whose images the client load()s through ResourceLoader by a
# path it builds at runtime, so no catalog or literal names each file: every
# image there ships in the PCK (a .json beside them is packed by the include
# filter), and each must be imported VRAM-compressed with mipmaps by the
# import settings committed beside it, so a checkout draws what a package
# ships (check_actor_imports). The RL head's maps: RLHeadLibrary.texture()
# joins its texture folder to the names rl_head_textures/manifest.json, the
# hairstyles' and beards' material extras and its own conventions give.
LOADED_IMAGE_FOLDERS = ("rl_head_textures",)
# The import settings those textures get: what the editor's 3D detection
# writes for a texture a material uses (VRAM Compressed - S3TC/BPTC in the
# preset - plus mipmaps). Godot reads [params] from an existing .import, and
# imports again only when they change, so a rebuild keeps its imports.
URI_TEXTURE_IMPORT_PARAMS = (
    ("compress/mode", "2"), ("compress/high_quality", "false"), ("compress/lossy_quality", "0.7"),
    ("compress/uastc_level", "0"), ("compress/rdo_quality_loss", "0.0"),
    ("compress/hdr_compression", "1"), ("compress/normal_map", "0"), ("compress/channel_pack", "0"),
    ("mipmaps/generate", "true"), ("mipmaps/limit", "-1"), ("roughness/mode", "0"),
    ("roughness/src_normal", '""'), ("process/channel_remap/red", "0"),
    ("process/channel_remap/green", "1"), ("process/channel_remap/blue", "2"),
    ("process/channel_remap/alpha", "3"), ("process/fix_alpha_border", "true"),
    ("process/premult_alpha", "false"), ("process/normal_map_invert_y", "false"),
    ("process/hdr_as_srgb", "false"), ("process/hdr_clamp_exposure", "false"),
    ("process/size_limit", "0"), ("detect_3d/compress_to", "0"),
)
# The same for a texture sampled as a normal map: the editor's normal-map
# detection adds red-green compression (RGTC), as for the continent's normals.
NORMAL_MAP_IMPORT_PARAMS = tuple((k, "1" if k == "compress/normal_map" else v)
                                 for k, v in URI_TEXTURE_IMPORT_PARAMS)
SKIP_IMPORT = '[remap]\n\nimporter="skip"\n'
# Where the textures the world's 3D scenes sample live (scene_textures). The
# editor imports a texture VRAM-compressed with mipmaps only after drawing a
# material that uses it, which a headless --import never does: a package of
# d50c3d8b1 built in a fresh worktree shipped 184 of them lossless without
# mipmaps (continent, harvestables, interactives, the map-authoring pilot)
# where the long-lived build worktree, touched by editor sessions, shipped
# them compressed, and no build had compressed the six landing-isle
# harvestables. world_authoring - the map editor's region sources, which only
# the editor plugins and src/dev's editor tools load - is not exported at all
# (EDITOR_ONLY_PCK_DIRS), and scene_textures does not read it either: what the
# game samples decides a texture's import, not what the editor draws.
SCENE_TEXTURE_ROOTS = ("godot-client/assets/world", "godot-client/src/dev")
# Folders a script loads 3D material textures from by a built path no scene or
# glTF names: MapAuthoringTexturePresets (src/dev/map_authoring_pilot/style/
# texture_presets.gd) loads _TEXTURE_ROOT + "<family>-<basecolor|normal|orm>.png".
RUNTIME_SCENE_TEXTURE_FOLDERS = ("godot-client/src/dev/map_authoring_pilot/style/textures",)
# Scripts that name 3D material textures by res:// literal, outside any scene
# or glTF: MapAuthoringTexturePresets' albedo_path entries are the texture
# packs (style/texture_packs) its materials sample. The biome-blend terrain
# loads the same files by the res:// path its map data records: BiomeBlend-
# Material._apply_palette reads each palette record's "albedoTexture" from
# assets/world/biome_blend/catalog.json and the chunks' world.json, so those
# values count too (RUNTIME_TEXTURE_DATA_ROOTS, RUNTIME_TEXTURE_KEYS). Until
# 2026-10-05 only world_authoring's region scenes named six of those packs in
# a material.
RUNTIME_SCENE_TEXTURE_SOURCES = ("godot-client/src/dev/map_authoring_pilot/style/texture_presets.gd",)
RES_IMAGE_LITERAL = re.compile(r"""["']res://([^"'\s]+\.(?:png|jpe?g|webp))["']""", re.I)
# Where the game reads map data that names 3D material textures by res:// path,
# and the keys that hold them (only those: map data names 2D pictures too).
RUNTIME_TEXTURE_DATA_ROOTS = ("godot-client/assets/world", "eloria-assets/maps")
RUNTIME_TEXTURE_KEYS = {"albedoTexture"}
RUNTIME_NORMAL_MAP = re.compile(r"-normal\.\w+$", re.I)
# BaseMaterial3D slots sampled as normal maps (hint_normal, hint_roughness_normal).
NORMAL_MAP_PROPERTIES = {"normal_texture", "detail_normal", "bent_normal_texture"}
SCENE_EXT_RESOURCE = re.compile(r"^\[ext_resource\b([^\]]*)\]", re.M)
SCENE_SECTION = re.compile(r"^\[(gd_resource|sub_resource|resource|node)\b([^\]]*)\]", re.M)
SCENE_ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
SCENE_PROPERTY = re.compile(r"^([\w/]+)\s*=\s*(.*)$", re.M)
SHADER_TYPE = re.compile(r"\bshader_type\s+(\w+)")
SHADER_SAMPLER = re.compile(r"\buniform\s+sampler2D\s+(\w+)\s*(?::([^;=]*))?")
# Characters String.validate_filename() turns into "_" in an extracted image's name.
INVALID_FILENAME = re.compile(r'[:/\\?*"|%<>]')
# Actor folders whose unnamed images ship nowhere (owner call, 2026-10-05:
# "verify, then drop", ~116 MB). In these folders an image that no actor glTF
# names by URI, no catalog names and no client source names is never read by
# a package: the equipment and creature PNGs are the editor's extracted copies
# of images their GLBs embed (a package parses the GLB and uses the embedded
# bytes), race_textures holds the sources the Luminous race models were built
# from, and neck_textures the bakes no model names any more (models.json has
# no faceAppearance.neckTexture). A catalog or source reference keeps a file;
# a client literal that builds paths under one of these folders keeps all of
# its images. Proven unused statically and on a package without them, in
# work-output/integration-2026-10-04/stage2b.
UNREFERENCED_IMAGE_FOLDERS = ("creatures", "equipment", "neck_textures", "race_textures")

# The export preset is not tracked, so the build writes its own. The pack
# leaves out dev material, including the map editor's review notes
# (<region>.editor-notes.json beside each region scene): editor-only, never read
# by the game. So are the region sources themselves (world_authoring, owner
# call 2026-10-05: "exclude them now"): main.tscn, the autoloads and the data
# the game reads reach no file there, and the 2.11 GB PCK of 91ce68374 held
# 1.77 GB of them. A filter leaves them in the import, where the editor plugins
# still read them, but no packaging decision rests on them: the scene textures
# are found from what the game samples (scene_textures). The RL head's lab
# (prototypes/rl_heads: open-rl-head-lab.bat's scene and the stage the RL
# tests share) is left out too; only the lab and tests load it. Actor files
# are kept out of the import, and so out of the pack, by a .gdignore per
# folder or a "skip" import per file (see actor_shipping), not by a filter, so
# the face masks, equipment textures and RL head maps still import.
EXPORT_PRESETS = """[preset.0]

name="Windows Desktop"
platform="Windows Desktop"
runnable=true
advanced_options=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="*.json,*.bin,assets/audio/*.txt,assets/audio/licenses/*.txt"
exclude_filter="Godot_v*.exe,docs/*,tests/*,tools/*,test-artifacts/*,world_authoring/*,prototypes/rl_heads/*,*.md,*.editor-notes.json"
export_path=""
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.0.options]

custom_template/debug=""
custom_template/release=""
debug/export_console_wrapper=2
binary_format/embed_pck=false
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
binary_format/architecture="x86_64"
application/modify_resources=true
application/icon="res://assets/branding/rabbitlands-icon.ico"
application/console_wrapper_icon="res://assets/branding/rabbitlands-icon.ico"
application/icon_interpolation=4
application/file_version=""
application/product_version=""
application/company_name="Rabbit Lands"
application/product_name="Rabbit Lands"
application/file_description="Rabbit Lands Client"
application/copyright=""
application/trademarks=""
application/export_angle=0
application/export_d3d12=0
application/d3d12_agility_sdk_multiarch=true
ssh_remote_deploy/enabled=false

[preset.1]

name="Linux"
platform="Linux"
runnable=false
advanced_options=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="*.json,*.bin,assets/audio/*.txt,assets/audio/licenses/*.txt"
exclude_filter="Godot_v*.exe,docs/*,tests/*,tools/*,test-artifacts/*,world_authoring/*,prototypes/rl_heads/*,*.md,*.editor-notes.json"
export_path=""
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.1.options]

custom_template/debug=""
custom_template/release=""
debug/export_console_wrapper=0
binary_format/embed_pck=false
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
binary_format/architecture="x86_64"
ssh_remote_deploy/enabled=false
"""

# What the export's exclude filter keeps out of the PCK that a package must never carry
# (check_editor_sources_unpacked): the map editor's region sources.
EDITOR_ONLY_PCK_DIRS = ("world_authoring/",)
# Map files that name those sources as provenance only: each legacy map's
# authoring/continent-authoring.json records the region scene and prototypes it
# was published from. They ship, but no file the game reaches opens them
# (check_map_data_names_no_editor_sources, scene_textures).
EDITOR_SOURCE_PROVENANCE = re.compile(r"(^|/)authoring/continent-authoring\.json$")

PLATFORMS = {
    "windows": {"preset": "Windows Desktop", "binary": "RabbitLands.exe", "folder": "RabbitLands-Windows"},
    "linux": {"preset": "Linux", "binary": "RabbitLands.x86_64", "folder": "RabbitLands-Linux"},
    "macos": {"preset": "macOS", "binary": "RabbitLands", "folder": "RabbitLands-macOS"},
}
# Kept separate so Windows/Linux export presets and their installer helpers
# retain their existing behavior.
EXPORT_PRESETS += macos_package.EXPORT_PRESET
# The full world generation is a loose, independently updated resource tree.
# Exclude it explicitly even when a disposable editor has indexed its files.
EXPORT_PRESETS = EXPORT_PRESETS.replace('exclude_filter="',
    'exclude_filter="prepared-world/*,.prepared-world-owner.json,')
WSL_DISTRO = "Ubuntu-24.04"


class PackageError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def git(*args: str, cwd: Path = REPO, capture: bool = True) -> str:
    config = ["-c", "core.longpaths=true"] if STORAGE and os.name == "nt" else []
    result = subprocess.run(["git", *config, *args], cwd=cwd, text=True,
                            capture_output=capture, encoding="utf-8")
    if result.returncode != 0:
        raise PackageError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout if capture else ""


def tracked(tree: Path, *pathspecs: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z", "--", *pathspecs], cwd=tree,
                         capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def _catalog_strings(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _catalog_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _catalog_strings(child)
    elif isinstance(value, str):
        yield value


def gltf_document(path: Path) -> dict:
    """glTF JSON; raw GLBs read only JSON, compressed creatures verify/decode first."""
    try:
        if path.suffix.lower() == ".glb":
            with open(path, "rb") as handle:
                header = handle.read(20)
                if header.startswith(creature_compression.MAGIC[:4]):
                    raw = creature_compression.read_bytes(path)
                    length = struct.unpack_from("<I", raw, 12)[0]
                    document = json.loads(raw[20:20 + length].rstrip(b"\0 ").decode("utf-8"))
                else:
                    if len(header) < 20 or header[:4] != b"glTF":
                        return {}
                    length = struct.unpack("<I", header[12:16])[0]
                    document = json.loads(handle.read(length).rstrip(b"\0 ").decode("utf-8"))
        else:
            document = json.loads(path.read_text(encoding="utf-8"))
    except creature_compression.PayloadError as error:
        raise PackageError(f"Invalid compressed creature {path}: {error}") from error
    except (OSError, ValueError, struct.error):
        return {}
    return document if isinstance(document, dict) else {}


def gltf_image_uris(path: Path) -> list[str]:
    """The relative image URIs a .glb/.gltf names (decoded; data: URIs left out).

    Reads only the JSON chunk. A file that is not glTF names nothing.
    """
    document = gltf_document(path)
    uris = []
    for image in document.get("images", []):
        uri = image.get("uri") if isinstance(image, dict) else None
        if isinstance(uri, str) and uri and not uri.startswith("data:"):
            uris.append(unquote(uri))
    return uris


def _resolve(base: str, relative: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), relative.replace("\\", "/")))


def shipped_client_files(build_dir: Path, suffixes: tuple[str, ...]) -> list[str]:
    """Tracked godot-client files with these suffixes that a package carries (not docs/tests/tools).

    world_authoring is listed although the export leaves it out (EDITOR_ONLY_PCK_DIRS): what its
    sources name only keeps an actor file loose, never drops one (SOURCE_SUFFIXES); scene_textures
    skips it.
    """
    return [p for p in tracked(build_dir, "godot-client")
            if p.lower().endswith(suffixes) and not p.startswith(UNSHIPPED_CLIENT_DIRS)
            and not p.lower().endswith(".md")]


def _actor_path(literal: str) -> str | None:
    """The repository path an actor path string names or starts, or None.

    Takes res://, repository, project and absolute forms ("res://assets/actors/
    native/x", "assets/actors", ".../godot-client/assets/actors/...").
    """
    text = literal.replace("\\", "/")
    match = ACTOR_PATH_IN_TEXT.search(text)
    return "godot-client/" + text[match.start():] if match else None


def _actor_prefix(build_dir: Path, path: str) -> str | None:
    """The start of the actor paths `path` builds at runtime, or None when it names one file.

    A format placeholder (%s, {0}) builds from the text before it; a path
    ending in "/", "_" or "-", or naming a directory (its last part has no
    suffix, or it is one in the tree), is joined to more at runtime.
    """
    placeholder = re.search(r"%|\{", path)
    if placeholder:
        return path[:placeholder.start()]
    if path.endswith(("/", "_", "-")) or not PurePosixPath(path).suffix or (build_dir / path).is_dir():
        return path
    return None


def source_actor_literals(build_dir: Path) -> tuple[set[str], set[str]]:
    """Actor paths the client source names: (files, prefixes) as repository paths.

    Every string literal, in either quote style, in every source file a
    package carries (SOURCE_SUFFIXES outside docs/tests/tools: src, addons,
    world_authoring, the native extension, project.godot). A literal naming an
    actor file is a file the game may open. A literal that is only the start
    of actor paths builds paths at runtime, so it can reach any file under it:
    one that names a directory ("res://assets/actors/native", "...race_textures"
    kept in a const and path_join()ed later), ends in "/", "_" or "-", holds a
    format placeholder, is joined to more text (+, %, path_join, format) or
    sits in a "/".join([...]) list. One compared against a path (begins_with
    and the like) reaches nothing. Paths built with no literal naming
    assets/actors at all are beyond this: shipped_text_names() and the
    packaged-route checks are the net under it.
    """
    files: set[str] = set()
    prefixes: set[str] = set()
    for relative in shipped_client_files(build_dir, SOURCE_SUFFIXES):
        text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
        if not ACTOR_PATH_IN_TEXT.search(text):
            continue
        for match in SOURCE_LITERAL.finditer(text):
            path = _actor_path(match.group(2))
            if path is None:
                continue
            before = text[max(0, match.start() - 200):match.start()]
            after = text[match.end():match.end() + 16]
            if COMPARED_BEFORE.search(before[-16:]):
                continue
            prefix = _actor_prefix(build_dir, path)
            if prefix is not None:
                prefixes.add(prefix)
            elif JOINED_AFTER.match(after) or JOIN_LIST_BEFORE.search(before):
                prefixes.add(path)
            else:
                files.add(path)
    return files, prefixes


def _json_strings(value):
    """Every key and string value in a JSON document."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _json_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_strings(child)
    elif isinstance(value, str):
        yield value


def shipped_text_names(build_dir: Path, candidates: set[str]) -> dict[str, set[str]]:
    """Which of `candidates` (actor images about to be dropped) shipped text names, and where.

    The drop is decided from the actor catalogs, the client source's actor
    path literals and the actor glTFs' URIs. This is the wider net under that
    decision - the scan the stage-2b static proof made - so that an image some
    other shipped text names is kept rather than silently left out:

      * every JSON a package carries, keys and values: godot-client outside
        docs/tests/tools (data, schemas, assets, world_authoring, the actor
        manifests) and the eloria-assets files that ship (shipped_eloria_assets:
        provenance, QA and review records stay out of a package, and their
        paths name nothing the game reads), plus the plain-text data (the
        localisation CSV);
      * every string literal, either quote style, in the source files a package
        carries (see source_actor_literals);
      * the image URIs of every other glTF a package carries.

    A string names a candidate when it is the image's path or a tail of it -
    its bare file name, "race_textures/x/body.png", a res://, repository or
    absolute path - or when, holding assets/actors, it is a directory, a path
    prefix or a format string the image lies under (JSON and plain text only;
    source prefixes are source_actor_literals', which knows a comparison from
    a built path). A bare stem ("orun_male") is not a name: stems are model
    keys and face-mask names, and a path built from a stem needs a folder,
    which these rules look for. Returns {candidate: {"<file>: <string>", ...}}.
    """
    if not candidates:
        return {}
    tails: dict[str, set[str]] = {}
    for candidate in candidates:
        parts = candidate.lower().split("/")
        for index in range(len(parts)):
            tails.setdefault("/".join(parts[index:]), set()).add(candidate)
    lowered = sorted((c.lower(), c) for c in candidates)
    named: dict[str, set[str]] = {}

    def note(hits, where: str, token: str) -> None:
        for hit in hits:
            named.setdefault(hit, set()).add(f"{where}: {token[:160]}")

    def visit(token: str, where: str, prefixes: bool) -> None:
        original = unquote(token).replace("\\", "/").strip()
        if not original or len(original) > 1024:
            return
        if original[:6].lower() == "res://":
            original = original[6:]
        original = original.removeprefix("./")
        hits = set(tails.get(original.lower(), ()))
        path = _actor_path(original)
        if path is not None:
            hits |= tails.get(path.lower(), set())
            prefix = _actor_prefix(build_dir, path) if prefixes else None
            if prefix is not None:
                prefix = prefix.lower()
                hits |= {c for low, c in lowered if low.startswith(prefix)}
        if hits:
            note(hits, where, token)

    # Of a served continent-v2 map only its client package ships, not the
    # territory's editor stub or the server's content tables.
    served = read_served_v2_packages(build_dir) if (build_dir / REGISTRY_FILE).is_file() else []
    map_files = sorted(shipped_eloria_assets(build_dir, served=served)[0])
    json_files = shipped_client_files(build_dir, (".json",)) + [
        p for p in map_files if p.lower().endswith(".json")]
    for relative in json_files:
        try:
            document = json.loads((build_dir / relative).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
            for match in SOURCE_LITERAL.finditer(text):
                visit(match.group(2), relative, True)
            continue
        for value in _json_strings(document):
            visit(value, relative, True)
    for relative in shipped_client_files(build_dir, PLAIN_TEXT_SUFFIXES):
        text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
        for token in re.split(r"[\s\"',;=()\[\]{}<>|]+", text):
            visit(token, relative, True)
    for relative in shipped_client_files(build_dir, SOURCE_SUFFIXES):
        text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
        for match in SOURCE_LITERAL.finditer(text):
            visit(match.group(2), relative, False)
    gltf_files = [p for p in shipped_client_files(build_dir, GLTF_SUFFIXES) + map_files
                  if p.lower().endswith(GLTF_SUFFIXES) and not p.startswith(ACTOR_ROOT + "/")]
    for relative in gltf_files:
        for uri in gltf_image_uris(build_dir / relative):
            target = _resolve(relative, uri)
            if target in candidates:
                note({target}, relative, uri)
            elif ACTOR_PATH_IN_TEXT.search(uri):
                visit(uri, relative, False)
    return named


def actor_shipping(build_dir: Path) -> dict:
    # Runners and explicit local benchmark builds own one committed input
    # generation. Reuse its pure reference proof while imports and test export
    # pruning leave runtime catalogs/references unchanged. Ordinary packages
    # still recompute; neither cache changes staging/export validation.
    plans = STORAGE.actor_plans if STORAGE else BENCHMARK_ACTOR_PLANS
    if plans is None:
        return _actor_shipping(build_dir)
    resolved = build_dir.resolve()
    if resolved not in plans:
        plans[resolved] = _actor_shipping(build_dir)
    return plans[resolved]


def _actor_shipping(build_dir: Path) -> dict:
    """Decide, per actor file, whether it ships in the PCK, loose or nowhere - never twice.

    The client reaches actor files three ways. glTF files (models, hair,
    equipment, animation libraries, held props) go through GlbSceneCache and
    NativeAnimationImporter with ProjectSettings.globalize_path(), which in an
    exported build is relative to the working folder: they are read loose,
    and a PCK copy would never be read. An actor file the catalogs or the
    client source name by res:// path (today the face masks), and every image
    in LOADED_IMAGE_FOLDERS (the RL head's maps, named by paths the client
    builds), is load()ed through ResourceLoader and must be in the PCK. And
    the images a glTF names by relative URI are asked of ResourceLoader
    first, at that relative path, which resolves to res://: in
    IMPORTED_URI_TEXTURE_FOLDERS they are imported into the PCK; elsewhere
    they are read loose beside their glTF.
    An image in UNREFERENCED_IMAGE_FOLDERS that none of these names, and no
    runtime-built source path can reach, ships nowhere - unless any other text
    a package carries names it (shipped_text_names), which keeps it loose,
    as every actor image shipped before the drop.

    A folder under assets/actors/native with nothing for the PCK gets a
    .gdignore (neither imported nor exported); in a folder that has, each
    other importable file gets a "skip" import, and its .json/.bin files are
    packed by the export's include filter, so they ship in the PCK. Returns
    {"pck", "loose", "dropped"} (tracked files), "uri_textures" (the imported
    URI textures, a subset of "pck"), "folder_textures" (the images of
    LOADED_IMAGE_FOLDERS, also a subset of "pck"), "kept" ({image: where it
    is named} for the images the wider scan kept loose) and {"pck_folders",
    "loose_folders"}.
    """
    # Import settings and authoring reports are not runtime actor files;
    # stage_loose_client_files also leaves these metadata files out.
    actor_files = [relative for relative in tracked(build_dir, ACTOR_ROOT)
                   if not relative.endswith((".import", ".report.json"))]
    folders: dict[str, list[str]] = {}
    for relative in actor_files:
        parts = PurePosixPath(relative).relative_to(ACTOR_ROOT).parts
        if len(parts) < 2:
            raise PackageError(f"{relative} sits outside an actor folder; it would ship nowhere")
        folders.setdefault(f"{ACTOR_ROOT}/{parts[0]}", []).append(relative)
    tracked_set = set(actor_files)
    loaded: set[str] = set()
    for catalog in ACTOR_CATALOGS:
        document = json.loads((build_dir / catalog).read_text(encoding="utf-8"))
        for value in _catalog_strings(document):
            if value.startswith("res://assets/actors/") and not value.lower().endswith(GLTF_SUFFIXES):
                loaded.add("godot-client/" + value[len("res://"):])
    missing = sorted(loaded - tracked_set)
    if missing:
        raise PackageError("actor resources the catalogs load are not in the commit:\n  "
                           + "\n  ".join(missing[:40]))
    source_files, source_prefixes = source_actor_literals(build_dir)
    loaded |= {f for f in source_files & tracked_set if not f.lower().endswith(GLTF_SUFFIXES)}
    uri_named: dict[str, str] = {}
    for relative in actor_files:
        if relative.lower().endswith(GLTF_SUFFIXES):
            for uri in gltf_image_uris(build_dir / relative):
                target = _resolve(relative, uri)
                if target in tracked_set:
                    uri_named.setdefault(target, relative)

    def folder_name(relative: str) -> str:
        return PurePosixPath(relative).relative_to(ACTOR_ROOT).parts[0]

    folder_textures = {f for f in actor_files if folder_name(f) in LOADED_IMAGE_FOLDERS
                       and f.lower().endswith(IMAGE_SUFFIXES)}
    loaded |= folder_textures
    uri_textures = {f for f in uri_named
                    if folder_name(f) in IMPORTED_URI_TEXTURE_FOLDERS and f not in loaded}
    reached = tuple(p for p in source_prefixes if p.startswith(ACTOR_ROOT + "/")
                    or (ACTOR_ROOT + "/").startswith(p))
    unnamed = {f for f in actor_files
               if f.lower().endswith(IMAGE_SUFFIXES) and folder_name(f) in UNREFERENCED_IMAGE_FOLDERS
               and f not in uri_named and f not in loaded and not f.startswith(reached)}
    # Any other shipped text that names one keeps it, loose, as before the drop.
    kept = shipped_text_names(build_dir, unnamed)
    dropped = unnamed - set(kept)
    pck_folders = {folder for folder, files in folders.items()
                   if (loaded | uri_textures).intersection(files)}
    for folder in sorted(pck_folders):
        # A .gltf reads its .bin buffers loose, but the include filter would
        # pack them (a .glb carries its own).
        gltf = [f for f in folders[folder] if f.lower().endswith(".gltf")]
        if gltf:
            raise PackageError(f"{folder} ships files in the PCK and holds {gltf[0]}, whose "
                               "buffers the export would pack instead of shipping beside it; "
                               "split the folder")
    pck = loaded | uri_textures | {f for folder in pck_folders for f in folders[folder]
                                   if f.lower().endswith(PLAIN_EXPORT_SUFFIXES)}
    loose_folders = set(folders) - pck_folders
    return {"pck": pck, "uri_textures": uri_textures, "folder_textures": folder_textures,
            "dropped": dropped, "kept": kept, "loose": tracked_set - pck - dropped,
            "pck_folders": pck_folders, "loose_folders": loose_folders}


def _gltf_normal_images(document: dict) -> set[int]:
    """The images a glTF's materials sample as normal maps (by index)."""
    sources: list[set] = []
    for texture in document.get("textures", []):
        texture = texture if isinstance(texture, dict) else {}
        found = {texture.get("source")}
        for extension in (texture.get("extensions") or {}).values():  # EXT_texture_webp and the like
            if isinstance(extension, dict):
                found.add(extension.get("source"))
        sources.append({s for s in found if isinstance(s, int)})
    normals: set[int] = set()
    for material in document.get("materials", []):
        normal = material.get("normalTexture") if isinstance(material, dict) else None
        index = normal.get("index") if isinstance(normal, dict) else None
        if isinstance(index, int) and 0 <= index < len(sources):
            normals |= sources[index]
    return normals


def _extracted_image_names(document: dict) -> list[str | None]:
    """Per image, the name the editor extracts an embedded glTF image under (None for a URI image).

    GLTFDocument (4.7) names an image by its "name" - file part, extension
    dropped, made a valid file name - or else its index, made unique with
    "_<index>", and the scene import saves it beside the glTF as
    "<glTF stem>_<name>.png" (or .jpg ...). The import then reads that file,
    so the imported scene samples it like any other texture.
    """
    names: list[str | None] = []
    used: set[str] = set()
    for index, image in enumerate(document.get("images", [])):
        image = image if isinstance(image, dict) else {}
        if "name" in image:
            name = PurePosixPath(str(image["name"]).replace("\\", "/")).name
            name = INVALID_FILENAME.sub("_", (name.rsplit(".", 1)[0] if "." in name else name).strip())
        else:
            name = str(index)
        while name in used:
            name += f"_{index}"
        used.add(name)
        names.append(None if image.get("uri") else name)
    return names


WORLD_ASSET_ROOT = "godot-client/assets/world/"
WORLD_RESOURCE_LITERAL = re.compile(r"res://(assets/world/[^\"'\s]+\.(?:glb|gltf|png|jpg|jpeg|webp))", re.I)
WORLD_LOAD_LITERAL = re.compile(r"\b(?:load|preload)\s*\(\s*['\"]res://(assets/world/[^'\"]+\.(?:glb|gltf))['\"]", re.I)


def _possible_gltf_uris(path: Path) -> list[str]:
    """Read URI strings without materializing unrelated actors' huge curve JSON."""
    if path.suffix.lower() == ".glb":
        with path.open("rb") as handle:
            header = handle.read(20)
            if len(header) < 20 or header[:4] != b"glTF":
                return gltf_image_uris(path)  # Preserve legacy compressed-container support.
            raw = handle.read(struct.unpack_from("<I", header, 12)[0])
    else:
        raw = path.read_bytes()
    return [unquote(json.loads(match.group(1))) for match in re.finditer(rb'"uri"\s*:\s*("(?:\\.|[^"\\])*")', raw)]


def world_import_shipping(build_dir: Path) -> dict[str, set[str]]:
    # A runner owns one immutable committed input generation. Complete this
    # reference proof before its verified map/editor source retirement, as we
    # already do for actor_shipping. Later checks still hash actual staged
    # models/images and inspect the real PCK. Ordinary local builds recompute.
    if STORAGE is None:
        return _world_import_shipping(build_dir)
    plans = STORAGE.world_import_plans
    resolved = build_dir.resolve()
    if resolved not in plans:
        result = _world_import_shipping(build_dir)
        plans[resolved] = {key: frozenset(value) for key, value in result.items()}
    return {key: set(value) for key, value in plans[resolved].items()}


def _world_import_shipping(build_dir: Path) -> dict[str, set[str]]:
    """Raw scenery needs no editor scene import; explicit resource users win.

    An image is dropped only when its encoded bytes exactly match an embedded
    source image and no independent shipped text/glTF reference names it.
    Names alone never establish that a source texture is disposable.
    """
    files = tracked(build_dir, "godot-client")
    models = {path for path in files if path.startswith(WORLD_ASSET_ROOT) and path.lower().endswith(GLTF_SUFFIXES)}
    images = {path for path in files if path.startswith(WORLD_ASSET_ROOT) and path.lower().endswith(IMAGE_SUFFIXES)}
    imported: set[str] = set()
    independent: set[str] = set()
    reader_path = "godot-client/src/actors/glb_scene_cache.gd"
    reader = build_dir / reader_path
    reader_text = reader.read_text(encoding="utf-8", errors="replace") if reader.is_file() else ""
    raw_reader_known = 'if not resource_path.begins_with("res://assets/actors/")' in reader_text
    texts = [path for path in files if path.lower().endswith((".gd", ".tscn", ".tres", ".gdshader", ".json"))
             and not path.startswith((*UNSHIPPED_CLIENT_DIRS, "godot-client/world_authoring/"))]
    texts += [path for path in tracked(build_dir, "eloria-assets/maps") if path.endswith(".json")
              and is_shipped_map_file(PurePosixPath(path).relative_to("eloria-assets/maps"))]
    for path in texts:
        text = (build_dir / path).read_text(encoding="utf-8-sig", errors="replace")
        if path != reader_path or not raw_reader_known:
            for _quote, literal in SOURCE_LITERAL.findall(text):
                if literal.startswith("res://assets/world/") and (literal.endswith("/") or "%" in literal or "{" in literal):
                    prefix = "godot-client/" + re.split(r"[%{]", literal[6:], maxsplit=1)[0]
                    imported.update(model for model in models if model.startswith(prefix))
                    independent.update(image for image in images if image.startswith(prefix))
        for target in WORLD_RESOURCE_LITERAL.findall(text):
            target = "godot-client/" + target
            if target in images:
                independent.add(target)
            elif path.endswith((".tscn", ".tres")) and target in models:
                imported.add(target)
        if path.endswith(".gd"):
            imported.update("godot-client/" + target for target in WORLD_LOAD_LITERAL.findall(text))
            if re.search(r"\b(?:load|preload)\s*\(\s*[A-Za-z_]", text):
                # A constant/variable resource path is still an explicit user.
                # Conservatively keep every world-model literal in that script.
                imported.update("godot-client/" + target for target in WORLD_RESOURCE_LITERAL.findall(text)
                                if target.lower().endswith(GLTF_SUFFIXES))
    if not raw_reader_known:
        # Packaging another revision must not assume the current raw-world
        # reader. An unrecognized/imported world reader keeps its old imports.
        imported.update(models)
    expected: dict[str, set[str]] = {}
    imported_images: set[str] = set()
    for path in shipped_client_files(build_dir, GLTF_SUFFIXES):
        if path.startswith("godot-client/world_authoring/"):
            continue
        if path not in models:
            independent.update(_resolve(path, uri) for uri in _possible_gltf_uris(build_dir / path))
            continue
        document = gltf_document(build_dir / path)
        for uri in [unquote(image["uri"]) for image in document.get("images", [])
                    if isinstance(image, dict) and isinstance(image.get("uri"), str)]:
            independent.add(_resolve(path, uri))
        if path in imported:
            stems = {path.rsplit(".", 1)[0] + "_" + name for name in _extracted_image_names(document) if name is not None}
            imported_images.update(image for image in images if image.rsplit(".", 1)[0] in stems)
        if path not in models - imported or not path.endswith(".glb"):
            continue
        if "rabbitlands_scenery_images" in (document.get("extras") or {}):
            from scenery_image_sources import validate
            try:
                closure = validate(build_dir, build_dir / path, document)
            except (OSError, ValueError) as error:
                raise PackageError(f"{path}: invalid scenery image closure: {error}") from error
            # Externalization preserves image names and exact encoded hashes.
            # A matching old extraction is still redundant; an original URI
            # remains independently referenced above and can never be dropped.
            names = _extracted_image_names({"images": [{key: value for key, value in image.items() if key != "uri"}
                                                       for image in document.get("images", [])]})
            for image in closure["images"]:
                name = names[image["index"]]
                if name is not None:
                    expected.setdefault(path.rsplit(".", 1)[0] + "_" + name, set()).add(image["sha256"])
            continue
        raw = (build_dir / path).read_bytes()
        offset = 12
        binary = b""
        while offset + 8 <= len(raw):
            length, kind = struct.unpack_from("<II", raw, offset)
            if offset + 8 + length > len(raw):
                break
            if kind == 0x004E4942:
                binary = raw[offset + 8:offset + 8 + length]
                break
            offset += 8 + length
        views = document.get("bufferViews", [])
        for image, name in zip(document.get("images", []), _extracted_image_names(document)):
            if name is None or not isinstance(image, dict) or "bufferView" not in image:
                continue
            index = image["bufferView"]
            if not isinstance(index, int) or not 0 <= index < len(views):
                continue
            view = views[index]
            start, size = view.get("byteOffset", 0), view.get("byteLength", 0)
            if view.get("buffer", 0) != 0 or not isinstance(start, int) or not isinstance(size, int) \
                    or start < 0 or size <= 0 or start + size > len(binary):
                continue
            stem = path.rsplit(".", 1)[0] + "_" + name
            expected.setdefault(stem, set()).add(hashlib.sha256(binary[start:start + size]).hexdigest())
    dropped = {path for path in images if path not in independent and path.rsplit(".", 1)[0] in expected
               and hashlib.sha256((build_dir / path).read_bytes()).hexdigest() in expected[path.rsplit(".", 1)[0]]}
    return {"raw_models": models - imported, "imported_models": models & imported,
            "dropped_images": dropped, "independent_images": (independent & images) | imported_images}


def write_world_import_settings(build_dir: Path, shipping: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    """Apply only to an owned build tree, before its first editor import."""
    shipping = world_import_shipping(build_dir) if shipping is None else shipping
    for relative in sorted(shipping["raw_models"] | shipping["dropped_images"]):
        (build_dir / (relative + ".import")).write_text(SKIP_IMPORT, encoding="utf-8", newline="\n")
    for relative in sorted(shipping["imported_models"] | shipping["independent_images"]):
        path = build_dir / (relative + ".import")
        if path.is_file() and _import_settings(path)[0] == "skip":
            path.unlink()
    log(f"world import policy: {len(shipping['raw_models'])} raw models, "
        f"{len(shipping['imported_models'])} explicit imported models, {len(shipping['dropped_images'])} unused exact extracted copies")
    return shipping


def scenery_image_resources(build_dir: Path) -> set[str]:
    """Verified tagged scenery image closure, including pools outside Godot."""
    resources: set[str] = set()
    files = set(tracked(build_dir, "godot-client/assets/world", "eloria-assets"))
    for relative in sorted(path for path in files if path.startswith(WORLD_ASSET_ROOT) and path.lower().endswith(GLTF_SUFFIXES)):
        document = gltf_document(build_dir / relative)
        if "rabbitlands_scenery_images" not in (document.get("extras") or {}):
            continue
        from scenery_image_sources import validate
        try:
            closure = validate(build_dir, build_dir / relative, document)
            for path in {image["path"] for image in closure["images"]}:
                name = path.relative_to(build_dir.resolve()).as_posix()
                if name not in files:
                    raise PackageError(f"{relative}: scenery image {name} is not in the commit")
                resources.add(name)
        except (OSError, ValueError) as error:
            raise PackageError(f"{relative}: invalid scenery image closure: {error}") from error
    return resources


def check_loose_scenery_images(build_dir: Path, stage: Path) -> None:
    """The actual raw-model copy and every declared image retain source hashes."""
    for relative in tracked(build_dir, "godot-client/assets/world"):
        if not relative.lower().endswith(GLTF_SUFFIXES):
            continue
        source = build_dir / relative
        document = gltf_document(source)
        if "rabbitlands_scenery_images" not in (document.get("extras") or {}):
            continue
        from scenery_image_sources import validate
        target = stage / "app" / PurePosixPath(relative).relative_to("godot-client")
        if not target.is_file() or hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
            raise PackageError(f"{relative}: staged raw scenery model is missing or changed")
        try:
            validate(build_dir, source, document)
            validate(stage, target, document, client_directory="app")
        except (OSError, ValueError) as error:
            raise PackageError(f"{relative}: staged scenery images: {error}") from error


def check_world_import_pack(build_dir: Path, app_dir: Path) -> None:
    """Raw scenery and unused exact derivatives never gain parallel PCK copies."""
    shipping = world_import_shipping(build_dir)
    paths = pck_paths(app_dir / "RabbitLands.pck")
    problems = []
    for relative in sorted(shipping["raw_models"] | shipping["dropped_images"]):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        if local in paths or local + ".import" in paths or local + ".remap" in paths:
            problems.append(f"{local}: unused editor resource is in the PCK")
        loose = app_dir / local
        if relative in shipping["raw_models"]:
            if not loose.is_file() or hashlib.sha256(loose.read_bytes()).digest() != hashlib.sha256((build_dir / relative).read_bytes()).digest():
                problems.append(f"{local}: raw source is missing or changed beside the PCK")
        elif loose.exists():
            problems.append(f"{local}: unused exact extracted image was staged loose")
    for relative in sorted(shipping["imported_models"]):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        products = _import_products(build_dir / (relative + ".import"))
        if not products or local + ".import" not in paths or any(path not in paths for path in products):
            problems.append(f"{local}: explicit imported resource dependency is absent")
    if problems:
        raise PackageError("world import shipping failed:\n  " + "\n  ".join(problems[:40]))
    log(f"checked {len(shipping['raw_models'])} raw world models without unused editor copies")


def _material_textures(text: str, shader_code) -> list[tuple[str, bool]]:
    """(res:// path, sampled as a normal map) of each image a 3D material in a .tscn/.tres names.

    A StandardMaterial3D or ORMMaterial3D samples every texture slot in 3D,
    the normal-map slots as normal maps; a ShaderMaterial does so when its
    shader is a spatial one, each sampler2D parameter a normal map when its
    hint says so. shader_code(path) reads an external shader.
    """
    resources = {}
    for match in SCENE_EXT_RESOURCE.finditer(text):
        attributes = dict(SCENE_ATTRIBUTE.findall(match.group(1)))
        resources[attributes.get("id")] = attributes.get("path", "")
    sections = list(SCENE_SECTION.finditer(text))
    header_type = ""
    bodies: list[tuple[str, str, str]] = []
    for index, match in enumerate(sections):
        attributes = dict(SCENE_ATTRIBUTE.findall(match.group(2)))
        if match.group(1) == "gd_resource":
            header_type = attributes.get("type", "")
            continue
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        kind = header_type if match.group(1) == "resource" else attributes.get("type", "")
        bodies.append((kind, attributes.get("id", ""), text[match.end():end]))
    inline_shaders = {resource_id: body for kind, resource_id, body in bodies if kind == "Shader"}
    found: list[tuple[str, bool]] = []
    for kind, _resource_id, body in bodies:
        samplers = None
        if kind == "ShaderMaterial":
            shader = re.search(r'^shader\s*=\s*(Ext|Sub)Resource\("([^"]+)"\)', body, re.M)
            if not shader:
                continue
            code = (shader_code(resources.get(shader.group(2), "")) if shader.group(1) == "Ext"
                    else inline_shaders.get(shader.group(2), ""))
            shader_type = SHADER_TYPE.search(code)
            if not shader_type or shader_type.group(1) != "spatial":
                continue
            samplers = dict(SHADER_SAMPLER.findall(code))
        elif kind not in ("StandardMaterial3D", "ORMMaterial3D"):
            continue
        for prop, value in SCENE_PROPERTY.findall(body):
            for reference in re.findall(r'ExtResource\("([^"]+)"\)', value):
                path = resources.get(reference, "")
                if not path.lower().endswith(IMAGE_SUFFIXES):
                    continue
                if samplers is None:
                    found.append((path, prop in NORMAL_MAP_PROPERTIES))
                elif prop.startswith("shader_parameter/") and prop[17:] in samplers:
                    hints = samplers[prop[17:]] or ""
                    found.append((path, re.search(r"\bhint_(roughness_)?normal\b", hints) is not None))
    return found


def scene_textures(build_dir: Path) -> dict[str, bool]:
    """The textures the world's 3D scenes sample: {repository path: sampled as a normal map}.

    Tracked images under SCENE_TEXTURE_ROOTS that
      * a glTF the package carries names by URI (outside the actor tree,
        which actor_shipping decides), or that the editor extracted from one
        of its embedded images (<stem>_<image name>.png beside it);
      * a 3D material in a .tscn/.tres the package carries names;
      * sit in RUNTIME_SCENE_TEXTURE_FOLDERS, the preset library's built paths
        (its "-normal" maps are normal maps);
      * a script in RUNTIME_SCENE_TEXTURE_SOURCES names by res:// literal, or
        the map data under RUNTIME_TEXTURE_DATA_ROOTS records under one of
        RUNTIME_TEXTURE_KEYS (the texture packs the presets and the
        biome-blend terrain sample).
    The map editor's region sources (world_authoring, EDITOR_ONLY_PCK_DIRS) are
    not read: the package leaves them out, and the game never draws them.
    The editor gives each of them VRAM compression and mipmaps once it draws
    a material using it (and red-green compression to a normal map); a
    headless import draws nothing, so the packager writes those settings
    (scene_texture_import_params). A texture whose .import the commit tracks
    keeps the settings committed with it (the biome masks).
    """
    editor_sources = tuple("godot-client/" + folder for folder in EDITOR_ONLY_PCK_DIRS)
    tracked_files = tracked(build_dir, "godot-client")
    tracked_set = set(tracked_files)
    roots = tuple(root + "/" for root in SCENE_TEXTURE_ROOTS)
    images = {p for p in tracked_files if p.startswith(roots) and p.lower().endswith(IMAGE_SUFFIXES)}
    by_stem: dict[str, list[str]] = {}
    for image in images:
        by_stem.setdefault(image.rsplit(".", 1)[0], []).append(image)
    found: dict[str, bool] = {}
    dropped_world_images = world_import_shipping(build_dir)["dropped_images"]

    def add(path: str, normal_map: bool) -> None:
        if path in images:
            found[path] = found.get(path, False) or normal_map

    for relative in shipped_client_files(build_dir, GLTF_SUFFIXES):
        if relative.startswith((ACTOR_ROOT + "/", *editor_sources)):
            continue
        document = gltf_document(build_dir / relative)
        normals = _gltf_normal_images(document)
        stem = relative.rsplit(".", 1)[0]
        for index, (image, name) in enumerate(zip(document.get("images", []),
                                                  _extracted_image_names(document))):
            uri = image.get("uri") if isinstance(image, dict) else None
            if isinstance(uri, str) and uri and not uri.startswith("data:"):
                add(_resolve(relative, unquote(uri)), index in normals)
            elif name is not None:
                for extracted in by_stem.get(f"{stem}_{name}", ()):
                    if extracted not in dropped_world_images:
                        add(extracted, index in normals)
    shaders: dict[str, str] = {}

    def shader_code(path: str) -> str:
        if path not in shaders:
            source = build_dir / "godot-client" / path.removeprefix("res://")
            shaders[path] = (source.read_text(encoding="utf-8", errors="replace")
                             if path.startswith("res://") and source.is_file() else "")
        return shaders[path]

    for relative in shipped_client_files(build_dir, (".tscn", ".tres")):
        if relative.startswith(editor_sources):
            continue
        text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
        if "Material" in text:
            for path, normal_map in _material_textures(text, shader_code):
                if path.startswith("res://"):
                    add("godot-client/" + path[len("res://"):], normal_map)
    for folder in RUNTIME_SCENE_TEXTURE_FOLDERS:
        for image in images:
            if image.startswith(folder + "/"):
                add(image, RUNTIME_NORMAL_MAP.search(image) is not None)
    for relative in RUNTIME_SCENE_TEXTURE_SOURCES:
        if relative in tracked_set:
            text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
            for literal in RES_IMAGE_LITERAL.findall(text):
                add("godot-client/" + literal, RUNTIME_NORMAL_MAP.search(literal) is not None)
    for relative in tracked(build_dir, *RUNTIME_TEXTURE_DATA_ROOTS) if RUNTIME_TEXTURE_DATA_ROOTS else ():
        if not relative.lower().endswith(".json") or EDITOR_SOURCE_PROVENANCE.search(relative):
            continue
        try:
            raw = (build_dir / relative).read_bytes()
            if not any(key.encode("utf-8") in raw for key in RUNTIME_TEXTURE_KEYS):
                continue
            data = json.loads(raw.decode("utf-8-sig"))
        except (OSError, ValueError):
            continue
        for key, value in json_strings(data, set()):
            if key in RUNTIME_TEXTURE_KEYS and value.startswith("res://"):
                add("godot-client/" + value[len("res://"):], RUNTIME_NORMAL_MAP.search(value) is not None)
    return {p: normal for p, normal in found.items() if p + ".import" not in tracked_set}


def scene_texture_import_params(normal_map: bool) -> tuple[tuple[str, str], ...]:
    return NORMAL_MAP_IMPORT_PARAMS if normal_map else URI_TEXTURE_IMPORT_PARAMS


def find_godot(explicit: str | None) -> Path:
    candidates = [Path(explicit)] if explicit else [
        CLIENT / GODOT_EXE, CLIENT / GODOT_EXE.replace("_console", ""),
        PROJECT / "rabbitlands-client" / "godot-client" / GODOT_EXE]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PackageError("Godot not found; pass --godot <path to " + GODOT_EXE + ">")


def find_iscc(explicit: str | None) -> Path | None:
    candidates = [Path(explicit)] if explicit else [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"]
    found = shutil.which("iscc")
    if found and not explicit:
        candidates.insert(0, Path(found))
    return next((c for c in candidates if c.is_file()), None)


# --- build tree ------------------------------------------------------------

def recover_build_worktree(build_dir: Path, sha: str) -> None:
    """Re-register a broken build worktree while retaining its import cache.

    Register an empty worktree in the current repository, transfer only its
    .git link, and let Git repair the backlink. Existing files never move.
    """
    marker = build_dir / ".git"
    if not marker.is_file() or not marker.read_text(encoding="utf-8").startswith("gitdir: "):
        raise PackageError(f"{build_dir} is not a recoverable build worktree")
    original = marker.read_bytes()
    def replace_link(data: bytes) -> None:
        # Git marks .git links hidden on Windows. Opening an existing hidden
        # file with "wb" fails; update it in place without changing attributes.
        with marker.open("r+b") as handle:
            handle.write(data)
            handle.truncate()
    registration = Path(tempfile.mkdtemp(prefix="client-src-registration-", dir=build_dir.parent))
    log(f"re-registering orphaned build worktree {build_dir}; retaining its import cache")
    try:
        git("worktree", "add", "--detach", "--no-checkout", str(registration), sha)
        replace_link((registration / ".git").read_bytes())
        git("worktree", "repair", str(build_dir))
        actual = Path(git("rev-parse", "--show-toplevel", cwd=build_dir).strip()).resolve()
        if actual != build_dir.resolve():
            raise PackageError("recovered worktree has an unexpected root")
    except (OSError, PackageError):
        replace_link(original)
        # Leave the tiny registration for diagnosis. Never remove a worktree
        # through a potentially half-repaired backlink.
        raise
    (registration / ".git").unlink()
    registration.rmdir()  # --no-checkout created only the .git link.


def prepare_build_tree(build_dir: Path, sha: str) -> Path:
    if build_dir.resolve() == REPO.resolve():
        raise PackageError("the build directory must not be the source checkout")
    # A checkout/reset begins a new source generation even if a caller reuses
    # this build path inside one invocation. Never reuse its earlier proof.
    if BENCHMARK_ACTOR_PLANS is not None:
        BENCHMARK_ACTOR_PLANS.pop(build_dir.resolve(), None)
    if STORAGE is not None:
        STORAGE.world_import_plans.pop(build_dir.resolve(), None)
    if not (build_dir / ".git").exists():
        log(f"creating build worktree {build_dir}")
        build_dir.parent.mkdir(parents=True, exist_ok=True)
        if STORAGE:
            git("worktree", "add", "--detach", "--no-checkout", str(build_dir), sha)
            runner_source.materialize(build_dir, sha, git, STORAGE)
        else:
            git("worktree", "add", "--detach", str(build_dir), sha)
    else:
        if STORAGE:
            raise PackageError("Runner builds require a fresh disposable build worktree.")
        log(f"moving build worktree to {sha[:9]}")
        try:
            git("rev-parse", "--git-dir", cwd=build_dir)
        except PackageError:
            recover_build_worktree(build_dir, sha)
        git("checkout", "--detach", "--force", sha, cwd=build_dir)
        # Untracked, unignored leftovers (a file deleted since the last build)
        # would otherwise be exported. Ignored files - .godot and the .import
        # sidecars - survive, which is what keeps a rebuild's import short.
        git("clean", "-ffd", "-q", cwd=build_dir)
    project = build_dir / "godot-client"
    release_world_preparation.reset_build(project)
    if STORAGE:
        # Keep authoring sources available for static reference checks, but
        # never import their unused models/textures or run editor plugins.
        for folder in EDITOR_ONLY_PCK_DIRS:
            (project / folder / ".gdignore").write_text("", encoding="utf-8")
        config = project / "project.godot"
        text = config.read_text(encoding="utf-8")
        text = re.sub(r'(\[editor_plugins\]\s*)enabled\s*=\s*[^\n]*', r'\1enabled=PackedStringArray()', text)
        config.write_text(text, encoding="utf-8")
    (project / "export_presets.cfg").write_text(EXPORT_PRESETS, encoding="utf-8", newline="\n")
    # The loose-only actor folders are neither imported nor exported. git
    # clean preserves ignored files, so set every marker explicitly: an older
    # build's assets/actors/.gdignore would also hide the face masks.
    shipping = actor_shipping(build_dir)
    (project / "assets" / "actors" / ".gdignore").unlink(missing_ok=True)
    for folder in shipping["pck_folders"]:
        (build_dir / folder / ".gdignore").unlink(missing_ok=True)
    for folder in shipping["loose_folders"]:
        (build_dir / folder / ".gdignore").write_text("", encoding="utf-8")
    write_actor_import_settings(build_dir, shipping)
    write_world_import_settings(build_dir)
    write_scene_texture_import_settings(build_dir, scene_textures(build_dir))
    for image, where in sorted(shipping["kept"].items()):
        log(f"kept loose, named outside the catalogs: {image} ({'; '.join(sorted(where)[:3])})")
    if STORAGE:
        STORAGE.retire_editor_sources(project)
    return project


def _import_settings(sidecar: Path) -> tuple[str, dict[str, str]]:
    """(importer, [params]) of a .import file, as raw text values."""
    importer = ""
    params: dict[str, str] = {}
    section = ""
    for line in sidecar.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line:
            key, _, value = line.partition("=")
            if section == "remap" and key == "importer":
                importer = value.strip('"')
            elif section == "params":
                params[key] = value
    return importer, params


def pck_folder_others(build_dir: Path, shipping: dict) -> list[str]:
    """Every file on disk in an actor folder the PCK draws on that must not be imported.

    Not only the tracked loose files: the build worktree keeps ignored files,
    and an earlier import's extracted images (equipment/*_0.jpg, gitignored)
    sit there too. Godot imports whatever it finds in a folder without a
    .gdignore, so each of them needs its "skip" as much as a tracked glTF
    does. A .json or .bin that is not a PCK file stops the build: the
    export's include filter would pack it whatever its import says.
    """
    others: list[str] = []
    for folder in sorted(shipping["pck_folders"]):
        for path in sorted((build_dir / folder).rglob("*")):
            relative = path.relative_to(build_dir).as_posix()
            if not path.is_file() or path.name == ".gdignore" or path.suffix in {".import", ".uid"}:
                continue
            if relative in shipping["pck"]:
                continue
            if relative.lower().endswith(PLAIN_EXPORT_SUFFIXES):
                raise PackageError(f"{relative} is not a PCK file, but the export would pack it "
                                   "from a folder the PCK draws on; remove it from the build worktree")
            others.append(relative)
    return others


def write_actor_import_settings(build_dir: Path, shipping: dict) -> dict:
    """Write the import settings of every file in an actor folder the PCK draws on.

    The URI textures get URI_TEXTURE_IMPORT_PARAMS and every other file there
    a "skip" import (glTF scenes would never be read from the PCK, and
    dropped images ship nowhere); a load()ed resource keeps the editor's
    defaults, so a "skip" left by an older build is removed. A .import that
    already says what is wanted is left alone - Godot rewrites it with the
    imported product's paths, and rewriting it here would import again.
    Returns counts of what was written.
    """
    counts = {"texture": 0, "skip": 0, "default": 0, "kept": 0}
    for relative in sorted(shipping["uri_textures"]):
        if _write_texture_import(build_dir / (relative + ".import"), URI_TEXTURE_IMPORT_PARAMS):
            counts["texture"] += 1
        else:
            counts["kept"] += 1
    for relative in pck_folder_others(build_dir, shipping):
        sidecar = build_dir / (relative + ".import")
        if sidecar.is_file() and _import_settings(sidecar)[0] == "skip":
            counts["kept"] += 1
            continue
        sidecar.write_text(SKIP_IMPORT, encoding="utf-8", newline="\n")
        counts["skip"] += 1
    for relative in sorted(shipping["pck"] - shipping["uri_textures"]):
        sidecar = build_dir / (relative + ".import")
        if sidecar.is_file() and _import_settings(sidecar)[0] == "skip":
            sidecar.unlink()
            counts["default"] += 1
    log(f"actor import settings: {counts['texture']} URI textures and {counts['skip']} skipped files "
        f"written, {counts['default']} skips removed, {counts['kept']} already right")
    return counts


IMPORT_UID = re.compile(r'^uid="(uid://[0-9a-z]+)"\s*$', re.M)


def _write_texture_import(sidecar: Path, params: tuple[tuple[str, str], ...]) -> bool:
    """Give a texture these import settings; False when its .import already has them.

    A .import that says what is wanted is left alone: Godot rewrites it with
    the imported product's paths, and rewriting it here would import again.
    A rewritten .import keeps the texture's uid. Without it Godot 4.7.2 gives
    the texture a new uid in a tree whose cache already knows the texture (a
    fresh tree gets the same uid as every other checkout), and a scene that
    names the texture by its old uid then warns and falls back to the path.
    """
    uid = None
    if sidecar.is_file():
        importer, current = _import_settings(sidecar)
        if importer == "texture" and all(current.get(k) == v for k, v in params):
            return False
        match = IMPORT_UID.search(sidecar.read_text(encoding="utf-8", errors="replace").split("\n[", 1)[0])
        uid = match.group(1) if match else None
    sidecar.write_text('[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\n'
                       + (f'uid="{uid}"\n' if uid else "") + "\n[params]\n\n"
                       + "".join(f"{k}={v}\n" for k, v in params), encoding="utf-8", newline="\n")
    return True


def write_scene_texture_import_settings(build_dir: Path, textures: dict[str, bool]) -> dict:
    """Write the import settings of the textures the world's 3D scenes sample (scene_textures).

    Every setting is compared, so a texture an editor session imported with
    other settings is imported once more: its roughness detection (Godot
    4.7.2 takes the material's last texture slot) writes roughness modes 1
    and 8, which change no pixel but differ from a fresh worktree's.
    """
    counts = {"texture": 0, "normal_map": 0, "kept": 0}
    for relative, normal_map in sorted(textures.items()):
        if _write_texture_import(build_dir / (relative + ".import"), scene_texture_import_params(normal_map)):
            counts["texture"] += 1
            counts["normal_map"] += normal_map
        else:
            counts["kept"] += 1
    log(f"scene texture import settings: {counts['texture']} written ({counts['normal_map']} normal "
        f"maps), {counts['kept']} already right")
    return counts


def run_godot(godot: Path, args: list[str], log_file: Path, timeout: int,
              env: dict | None = None, cwd: Path | None = None) -> str:
    with open(log_file, "w", encoding="utf-8", errors="replace") as handle:
        try:
            result = subprocess.run([str(godot), *args], stdout=handle, stderr=subprocess.STDOUT,
                                    timeout=timeout, env=env, cwd=cwd)
        except subprocess.TimeoutExpired:
            raise PackageError(f"Godot timed out after {timeout}s; log: {log_file}")
    text = log_file.read_text(encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise PackageError(f"Godot exited {result.returncode}; log: {log_file}\n{text[-2000:]}")
    return text


def import_project(godot: Path, project: Path, logs: Path) -> None:
    # --import can exit 0 long before the scan finishes; repeat until the
    # imported set stops growing.
    imported = project / ".godot" / "imported"
    previous = -1
    for attempt in range(1, 7):
        log(f"importing (pass {attempt})")
        run_godot(godot, ["--headless", "--path", str(project), "--import"],
                  logs / f"import-{attempt}.log", timeout=3600)
        count = sum(1 for _ in imported.iterdir()) if imported.is_dir() else 0
        log(f"  {count} imported files")
        if count == previous:
            return
        previous = count
    raise PackageError("import never settled after 6 passes; see import-*.log")


def _import_products(sidecar: Path) -> list[str]:
    text = sidecar.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?m)^dest_files=\[(.*)\]\s*$", text)
    return re.findall(r'"res://([^"]+)"', match.group(1)) if match else []


def check_actor_imports(project: Path) -> None:
    """Require every actor resource that ships in the PCK to be imported, as intended.

    The PCK-only actor files (the face masks, the equipment URI textures, the
    RL head's maps) are read through ResourceLoader, which in an export finds
    them only as imported resources. A stale .gdignore or a partial import
    would otherwise ship a client whose faces render without their masks, or
    whose equipment falls back to raw JPEG decodes; a URI texture or an RL head
    map imported without VRAM compression or mipmaps (an RL map's settings are
    committed; it also needs its S3TC/BPTC product), or a glTF imported after
    all, would ship the wrong thing. Called on the build worktree, so the
    repository root is the project's parent.
    """
    build_dir = project.parent
    shipping = actor_shipping(build_dir)
    failures: list[str] = []
    checked = 0
    for folder in sorted(shipping["pck_folders"]):
        if (build_dir / folder / ".gdignore").exists():
            failures.append(f"{folder}: .gdignore keeps it out of the import")
    wanted = dict(URI_TEXTURE_IMPORT_PARAMS)
    for relative in sorted(shipping["pck"]):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        if local.endswith(PLAIN_EXPORT_SUFFIXES):
            continue  # exported as plain files by the include filter
        checked += 1
        sidecar = project / (local + ".import")
        if not sidecar.is_file():
            failures.append(f"{local}: missing .import remap")
            continue
        products = _import_products(sidecar)
        if not products or any(not (project / PurePosixPath(p)).is_file()
                               or (project / PurePosixPath(p)).stat().st_size == 0
                               for p in products):
            failures.append(f"{local}: imported resource is missing")
        folder_texture = relative in shipping.get("folder_textures", ())
        if relative in shipping["uri_textures"] or folder_texture:
            importer, params = _import_settings(sidecar)
            wrong = [k for k in ("compress/mode", "mipmaps/generate") if params.get(k) != wanted[k]]
            if importer != "texture" or wrong:
                failures.append(f"{local}: imported as {importer or '?'} with "
                                f"{', '.join(f'{k}={params.get(k)}' for k in wrong) or 'other settings'}, "
                                "not a VRAM-compressed, mipmapped texture"
                                + (" (commit its import settings beside it)" if folder_texture else ""))
            elif folder_texture and not any(re.search(r"\.(s3tc|bptc)\.ctex$", p) for p in products):
                failures.append(f"{local}: no VRAM-compressed import product ({', '.join(products) or 'none'})")
    skipped = 0
    for relative in pck_folder_others(build_dir, shipping):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        sidecar = project / (local + ".import")
        if sidecar.is_file() and _import_settings(sidecar)[0] == "skip":
            skipped += 1
        else:
            failures.append(f"{local}: imported, but it ships loose or nowhere")
    if not shipping["pck_folders"]:
        failures.append("no actor folder ships in the PCK; the face masks would be missing")
    if failures:
        raise PackageError("PCK actor imports are incomplete:\n  " + "\n  ".join(failures[:40]))
    log(f"checked {checked} imported actor resources ({len(shipping['uri_textures'])} URI textures, "
        f"{len(shipping['folder_textures'])} RL head maps) in "
        f"{', '.join(PurePosixPath(f).name for f in sorted(shipping['pck_folders']))}, "
        f"{skipped} files there skipped; {len(shipping['loose_folders'])} actor folders ship loose only")


def check_scene_texture_imports(project: Path) -> None:
    """Require every texture the world's 3D scenes sample to be imported VRAM-compressed with mipmaps.

    The settings are written before the import (scene_textures), but a
    .import Godot never re-read, or an import that did not run again, would
    still name the lossless product of an earlier import. Normal maps must be
    red-green compressed. Called on the build worktree.
    """
    textures = scene_textures(project.parent)
    failures: list[str] = []
    for relative, normal_map in sorted(textures.items()):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        sidecar = project / (local + ".import")
        if not sidecar.is_file():
            failures.append(f"{local}: missing .import remap")
            continue
        importer, params = _import_settings(sidecar)
        wanted = dict(scene_texture_import_params(normal_map))
        wrong = [k for k in ("compress/mode", "mipmaps/generate", "compress/normal_map")
                 if params.get(k) != wanted[k]]
        if importer != "texture" or wrong:
            failures.append(f"{local}: imported as {importer or '?'} with "
                            f"{', '.join(f'{k}={params.get(k)}' for k in wrong) or 'other settings'}")
        products = _import_products(sidecar)
        if not any(".s3tc." in p for p in products) or any(
                not (project / PurePosixPath(p)).is_file() or (project / PurePosixPath(p)).stat().st_size == 0
                for p in products):
            failures.append(f"{local}: no VRAM-compressed import product ({', '.join(products) or 'none'})")
    if failures:
        raise PackageError(f"{len(failures)} scene textures are not imported for 3D:\n  "
                           + "\n  ".join(failures[:40]))
    log(f"checked {len(textures)} scene textures ({sum(textures.values())} normal maps): "
        "VRAM-compressed with mipmaps")


def export_project(godot: Path, project: Path, app_dir: Path, logs: Path, platform: dict) -> None:
    if platform.get("preset") == "macOS":
        macos_package.export(godot, project, app_dir, logs, run_godot)
        return
    log(f"exporting ({platform['preset']})")
    app_dir.mkdir(parents=True, exist_ok=True)
    text = run_godot(godot, ["--headless", "--path", str(project), "--export-release",
                             platform["preset"], str(app_dir / platform["binary"])],
                     logs / "export.log", timeout=3600)
    for name in (platform["binary"], "RabbitLands.pck"):
        if not (app_dir / name).is_file():
            raise PackageError(f"export did not write {name}; log: {logs / 'export.log'}\n{text[-2000:]}")


# --- loose duplicates of PCK-imported resources (W2-UD-02) -------------------
#
# The export packs an imported resource as its .import remap plus the products
# that names (.godot/imported/...), and the resource system - load(),
# preload(), a scene's ext_resource, anything on ResourceLoader - finds it
# there. The loose copy beside the PCK is read only by a raw read: FileAccess,
# DirAccess, Image/AudioStream load_from_file, an Image's or ConfigFile's
# load(), anything through ProjectSettings.globalize_path(). In an export a
# res:// path the PCK does not hold as itself falls through to the folder the
# game starts in, so even a raw res:// read - FileAccess.file_exists() too -
# finds exactly the loose copy. A loose copy nothing reads raw is the same bytes
# twice: 132 MB in release 4a57cea4, 83 MB of it audio.
#
# So a loose file of these types is left out of app/ when its .import and every
# product it names are in the PCK and nothing can read it raw
# (loose_duplicate_plan). Other imported types (glTF scenes, fonts) still ship
# loose: GlbSceneCache reads world glTFs raw whatever the PCK holds.
LOOSE_DUPLICATE_SUFFIXES = (".ogg", ".wav", ".mp3", ".png", ".jpg", ".jpeg", ".webp", ".svg")
# Loose whatever the PCK holds (godot-client-relative): the game data and
# schemas, text records the launcher, the updater and the packager's own steps
# read from disk (AUDIO-CREDITS is built from assets/audio/*.txt and
# provenance.json) and the branding icon.
LOOSE_ALWAYS_ROOTS = ("data", "schemas")
LOOSE_ALWAYS_SUFFIXES = (".json", ".txt", ".csv")
LOOSE_ALWAYS_FILES = ("assets/branding/rabbitlands-icon.ico",)
# Staged files something other than the game reads from app/ (godot-client-
# relative -> reader): the online installer helper copies both branding files
# from the stage (client_release.export_installer_helper) and Inno Setup takes
# its SetupIconFile there. export_launcher copies its branding from the build
# tree, not the stage.
LOOSE_STAGE_READERS = {
    "assets/branding/rabbitlands-icon.ico": "Inno Setup SetupIconFile; client_release.export_installer_helper",
    "assets/branding/rabbitlands-mark-64.png": "client_release.export_installer_helper",
}
# Data files whose content can name a loose file a raw read then opens.
LOOSE_DATA_SUFFIXES = (".json", ".txt", ".csv", ".cfg")
# A string naming a path under the client's assets folder ("res://assets/...",
# "assets/...", ".../godot-client/assets/..."), not eloria-assets/.
ASSET_PATH_IN_TEXT = re.compile(r"(?<![\w.-])assets(?=/|$)")
DATA_PATH_IN_TEXT = re.compile(r"(?<![\w.-])(?:data|schemas)(?=/)")
# One GDScript token. Strings keep their quotes and prefixes (&"", ^"", r"").
GD_TOKEN = re.compile(r"""
    (?P<comment>\#[^\n]*)
  | (?P<string>[&^]?r?(?:\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'))
  | (?P<name>[A-Za-z_]\w*)
  | (?P<number>\d[\w.]*)
  | (?P<newline>\n)
  | (?P<space>[ \t\r\f]+|\\\r?\n)
  | (?P<op>->|:=|==|!=|<=|>=|\+=|-=|\*=|/=|%=|\*\*|<<|>>|&&|\|\||\S)
""", re.X)
# How _LiteralUses judges a call a path literal's value reaches:
#   raw reads - the path is read from disk: any static FileAccess or DirAccess call,
#     load_from_file and the font loaders on any receiver, and a load()/open()-style
#     method on any receiver but ResourceLoader (globalize_path() only builds the disk
#     path: what consumes that decides);
RAW_READ_STATICS = ("FileAccess", "DirAccess")
RAW_READ_ANY_METHODS = ("load_from_file", "load_dynamic_font", "load_bitmap_font")
RAW_READ_RECEIVER_METHODS = ("load", "load_encrypted", "load_encrypted_pass", "open", "open_compressed",
                             "open_encrypted", "open_encrypted_with_pass")
#   resource loads - the PCK answers: bare load()/preload() and every ResourceLoader call;
RESOURCE_LOAD_CALLS = ("load", "preload")
#   consumers that neither read nor pass the value on (logging, measuring, testing),
#   and predicates on it;
SAFE_CALLS = {"print", "prints", "printt", "printerr", "printraw", "print_rich", "print_verbose", "push_error",
              "push_warning", "assert", "len", "hash", "typeof", "is_instance_valid", "int", "float", "bool",
              "abs", "clamp", "clampi", "clampf", "min", "max", "mini", "maxi", "minf", "maxf", "range",
              "round", "floor", "ceil", "sign", "posmod", "fmod", "snapped", "lerp", "is_same", "type_string",
              "error_string", "Color", "Vector2", "Vector2i", "Vector3", "Vector3i", "Rect2", "Rect2i"}
PREDICATE_METHODS = {"begins_with", "ends_with", "contains", "containsn", "find", "findn", "rfind", "rfindn",
                     "has", "has_all", "is_empty", "match", "matchn", "is_absolute_path", "is_relative_path",
                     "is_valid_filename", "length", "size", "count", "countn", "hash", "casecmp_to",
                     "nocasecmp_to", "naturalcasecmp_to", "erase", "find_key", "is_valid_identifier"}
#   string methods that take it as a pattern to compare, search or strip (replace()
#   only as what it replaces: its replacement is passed on);
PATTERN_METHODS = PREDICATE_METHODS | {"trim_prefix", "trim_suffix", "replace", "replacen", "split", "rsplit",
                                       "get_slice", "get_slice_count", "lstrip", "rstrip"}
#   functions and methods whose result still holds the value (a path built from it, a
#   container holding it), of which JOINING_CALLS make it the start of a longer path;
TRANSPARENT_CALLS = {"str", "String", "StringName", "NodePath", "Array", "PackedStringArray", "Dictionary",
                     "var_to_str", "str_to_var", "parse_string", "stringify", "localize_path", "globalize_path",
                     "simplify_path", "path_join", "plus_file", "format", "get_base_dir", "get_file",
                     "get_basename", "get_extension", "replace", "replacen", "strip_edges", "to_lower",
                     "to_upper", "uri_decode", "uri_file_decode", "uri_encode", "join", "left", "right", "substr",
                     "duplicate", "get", "get_value", "keys", "values", "pick_random", "front", "back", "slice",
                     "filter", "map", "get_as_text", "get_buffer", "get_line", "get_csv_line",
                     "get_as_utf8_string", "get_string_from_utf8", "merged", "sorted"}
JOINING_CALLS = {"path_join", "plus_file", "format", "get_base_dir"}
#   and anything else - another script's function the scan cannot resolve, an engine
#   method, a dynamic call or signal - counts as reading it raw.
GD_SKIP_NAMES = {
    "true", "false", "null", "self", "and", "or", "not", "in", "is", "as", "if", "elif", "else",
    "for", "while", "return", "var", "const", "static", "func", "await", "match", "break", "continue",
    "pass", "super", "PI", "TAU", "INF", "NAN", "when",
}
# Holders (locals, members) a literal is followed through, at most.
LITERAL_USE_DEPTH = 6
GD_COMPARISONS = {"==", "!=", "<", ">", "<=", ">=", "in", "not", "is", "and", "or"}
# Native sources that read files themselves.
NATIVE_RAW_READ = re.compile(r"FileAccess::|DirAccess::|\bfopen\b|\b_wfopen\b|ifstream|CreateFileW?\b")
RES_SCRIPT_LITERAL = re.compile(r"""["'](res://[^"'\s]+\.(?:gd|tscn|tres|scn|res))["']""")


def _gd_string(token: str) -> str:
    text = token.lstrip("&^")
    if text.startswith("r"):
        text = text[1:]
    quote = 3 if text[:3] in ('"""', "'''") else 1
    return text[quote:-quote].replace("\\\\", "\\").replace('\\"', '"').replace("\\'", "'")


def _gd_lines(text: str) -> list[tuple[int, int, list[tuple[str, str]]]]:
    """GDScript as statements: (indent, first line, tokens), comments dropped.

    A statement continues while a bracket is open or after a backslash; ";" splits one.
    """
    lines: list[tuple[int, int, list[tuple[str, str]]]] = []
    tokens: list[tuple[str, str]] = []
    depth = indent = 0
    number = start = 1
    at_start = True
    for match in GD_TOKEN.finditer(text):
        kind, value = match.lastgroup, match.group()
        if kind == "newline":
            number += 1
            if depth == 0:
                if tokens:
                    lines.append((indent, start, tokens))
                tokens, indent, at_start = [], 0, True
            continue
        if kind == "space":
            number += value.count("\n")
            if at_start and not tokens:
                indent = len(value.expandtabs(4))
            continue
        if kind == "comment":
            continue
        if not tokens:
            start = number
        at_start = False
        if kind == "string":
            number += value.count("\n")
        elif value in ("(", "[", "{"):
            depth += 1
        elif value in (")", "]", "}"):
            depth = max(0, depth - 1)
        if value == ";" and depth == 0:
            if tokens:
                lines.append((indent, start, tokens))
            tokens = []
            continue
        tokens.append((kind, value))
    if tokens:
        lines.append((indent, start, tokens))
    return lines


def _gd_close(tokens: list, index: int) -> int:
    """The index of the bracket closing the one at `index` (or the last token)."""
    depth = 0
    for position in range(index, len(tokens)):
        value = tokens[position][1]
        if value in ("(", "[", "{"):
            depth += 1
        elif value in (")", "]", "}"):
            depth -= 1
            if depth == 0:
                return position
    return len(tokens) - 1


def _gd_arguments(tokens: list) -> list[list]:
    """A call's argument tokens split at top-level commas."""
    arguments, current, depth = [], [], 0
    for token in tokens:
        if token[1] in ("(", "[", "{"):
            depth += 1
        elif token[1] in (")", "]", "}"):
            depth -= 1
        if token[1] == "," and depth == 0:
            arguments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        arguments.append(current)
    return arguments


class _GdFunction:
    def __init__(self, name: str, line: int, params: list[str], defaults: dict):
        self.name, self.line, self.params, self.defaults = name, line, params, defaults
        self.statements: list[tuple[int, list]] = []  # (line, tokens)
        self.locals: set[str] = set()  # var/const/for names


class _GdFile:
    """One GDScript as the forward scan reads it: its functions (statements, locals,
    parameters and their defaults), the script's and its inner classes' members, its
    class_name, its base script and its preload aliases. `top` holds the statements
    outside functions (the member declarations)."""

    def __init__(self, relative: str, text: str):
        self.relative = relative
        self.functions: list[_GdFunction] = []
        self.by_name: dict[str, list[int]] = {}
        self.members: set[str] = set()
        self.aliases: dict[str, str] = {}  # NAME -> res:// path of a script it preloads
        self.class_name = ""
        self.extends = ""
        self.top = _GdFunction("", 0, [], {})
        current: _GdFunction | None = None
        body_indent = -1
        for indent, number, tokens in _gd_lines(text):
            head = 0
            while head < len(tokens) and tokens[head][1] in ("@", "static"):
                if tokens[head][1] == "@":
                    head += 2
                    if head < len(tokens) and tokens[head][1] == "(":
                        head = _gd_close(tokens, head) + 1
                else:
                    head += 1
            if current is not None and indent <= body_indent:
                current = None
            if head + 2 < len(tokens) and tokens[head][1] == "func" and tokens[head + 1][0] == "name" \
                    and tokens[head + 2][1] == "(":
                close = _gd_close(tokens, head + 2)
                params, defaults = [], {}
                for argument in _gd_arguments(tokens[head + 3:close]):
                    if argument and argument[0][0] == "name":
                        params.append(argument[0][1])
                        for split, token in enumerate(argument):
                            if token[1] in ("=", ":="):
                                defaults[argument[0][1]] = argument[split + 1:]
                                break
                current = _GdFunction(tokens[head + 1][1], number, params, defaults)
                body_indent = indent
                self.by_name.setdefault(current.name, []).append(len(self.functions))
                self.functions.append(current)
                colon = close + 1
                while colon < len(tokens) and tokens[colon][1] != ":":
                    colon += 1
                if colon + 1 < len(tokens):  # a one-line body
                    self._statement(current, number, tokens[colon + 1:])
                continue
            if current is None:
                if indent == 0 and len(tokens) >= 2 and tokens[0][1] == "class_name":
                    self.class_name = tokens[1][1]
                elif indent == 0 and len(tokens) >= 2 and tokens[0][1] == "extends":
                    self.extends = _gd_string(tokens[1][1]) if tokens[1][0] == "string" else tokens[1][1]
                elif head + 1 < len(tokens) and tokens[head][1] in ("const", "var") and tokens[head + 1][0] == "name":
                    self.members.add(tokens[head + 1][1])
                    value = tokens[head + 2:]
                    assigned = next((i for i, token in enumerate(value) if token[1] in ("=", ":=")), None)
                    value = value[assigned + 1:] if assigned is not None else []
                    if len(value) == 4 and value[0][1] in ("preload", "load") and value[2][0] == "string" \
                            and _gd_string(value[2][1]).endswith(".gd"):
                        self.aliases[tokens[head + 1][1]] = _gd_string(value[2][1])
                self.top.statements.append((number, tokens))
            else:
                self._statement(current, number, tokens)

    @staticmethod
    def _statement(function: _GdFunction, number: int, tokens: list) -> None:
        function.statements.append((number, tokens))
        for position in range(len(tokens) - 1):
            if tokens[position][1] in ("var", "const", "for") and tokens[position + 1][0] == "name":
                function.locals.add(tokens[position + 1][1])


def _path_like(literal: str) -> bool:
    """Whether a string can be a path: it has a separator or a resource scheme."""
    return "/" in literal or "\\" in literal or literal.startswith(("res:", "user:", "uid:"))


def _literal_repo_path(literal: str) -> str | None:
    """The repository path a path literal names under godot-client (res://, assets/... or
    data/... forms), or None."""
    text = unquote(literal).replace("\\", "/").strip()
    if text.startswith("res://"):
        rest = text[len("res://"):]
        return None if rest.startswith("../") else "godot-client/" + rest
    if "/" not in text:
        return None  # a bare word ("assets" as a JSON key) is no path
    match = ASSET_PATH_IN_TEXT.search(text) or DATA_PATH_IN_TEXT.search(text)
    return "godot-client/" + text[match.start():] if match else None


def _literal_reach(build_dir: Path, literal: str, joined: bool) -> tuple[set[str], set[str]]:
    """({file}, {prefix}) a path literal can name, as repository paths.

    A literal holding a format placeholder names everything starting with its text
    before it. One the path is built on (joined) names its folder's contents if it names
    a file, else everything starting with it. A whole literal names its file, or
    everything in the folder it names.
    """
    path = _literal_repo_path(literal)
    if path is None:
        return set(), set()
    placeholder = re.search(r"%|\{", path)
    if placeholder:
        return set(), {path[:placeholder.start()]}
    file_like = bool(PurePosixPath(path).suffix) and not path.endswith("/") and not (build_dir / path).is_dir()
    if joined:
        return set(), {posixpath.dirname(path) + "/" if file_like else path}
    if not file_like:
        return set(), {path.rstrip("/") + "/"}
    return {posixpath.normpath(path)}, set()


def _data_names(build_dir: Path, relative: str) -> tuple[set[str], set[str]]:
    """({file}, {prefix}) under godot-client a data file names: every JSON key and value,
    or text token, as a res://, assets/ or data/ path, or relative to the file's folder."""
    path = build_dir / relative
    strings: list[str] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if relative.lower().endswith(".json"):
        try:
            strings = list(_json_strings(json.loads(text)))
        except ValueError:
            strings = [m.group(2) for m in SOURCE_LITERAL.finditer(text)]
    else:
        strings = re.split(r"[\s\"',;=()\[\]{}<>|]+", text)
    files: set[str] = set()
    prefixes: set[str] = set()
    folder = posixpath.dirname(relative)
    for value in strings:
        if not value or len(value) > 1024:
            continue
        named, under = _literal_reach(build_dir, value, False)
        if not named and not under and "." in value and ":" not in value and not value.startswith(("/", "res:")):
            target = posixpath.normpath(posixpath.join(folder, value.replace("\\", "/")))
            if target.startswith("godot-client/"):
                named = {target}
        files |= named
        prefixes |= under
    return files, prefixes


def runtime_client_sources(build_dir: Path) -> list[str]:
    """The client sources a package runs: everything under godot-client/src, the project
    settings, and every other shipped script or scene those name by res:// path, transitively.

    The map editor's plugins (addons) and the developer prototypes stay out unless the
    runtime names them: they run in the editor or from an explicit command line only.
    """
    sources = shipped_client_files(build_dir, SOURCE_SUFFIXES)
    shipped = {"res://" + relative.removeprefix("godot-client/"): relative for relative in sources}
    included = {relative for relative in sources
                if relative.startswith("godot-client/src/") or relative == "godot-client/project.godot"}
    queue = sorted(included)
    while queue:
        relative = queue.pop()
        text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
        for path in RES_SCRIPT_LITERAL.findall(text):
            named = shipped.get(path)
            if named is not None and named not in included:
                included.add(named)
                queue.append(named)
    return sorted(included)


class _LiteralUses:
    """Where each path literal of the running client is used, one statement at a time.

    A literal is followed outward through its statement: postfix calls on it (predicates
    end the use; path_join, format and get_base_dir make it the start of a longer path,
    "joined"; other string and container methods pass it on), subscripts, list and
    dictionary literals, "+" and "%" (joined), str() and the like. The use ends safely at
    the resource system (load, preload, ResourceLoader.*), a comparison, a predicate, a
    subscript key or logging. Held in a local, a for variable or a script member (const or
    var), every use of that name is followed the same way - a member's uses in the script,
    its subclasses and through any other script's reference to it - up to
    LITERAL_USE_DEPTH holders deep. A raw read whose whole path argument folds to a
    constant (literals and constants joined by "+" and path_join) reads that exact file: a
    data file read so is a "data" read, whose content is judged by the data rules. Any
    other use - a raw read of a built path, a return, a call to any other function or
    method, a dynamic call, an assignment into another object - counts as reading the
    literal's file (or, joined, its folder) raw. So a literal is only ever cleared by
    following it to the resource system; anything the scan does not understand keeps it.
    A call on the script itself is followed into its definition and every subclass's
    override (virtual dispatch), super.f() into the base's; a bare super(...) call, a match
    branch's one-line body and a recursive call count as raw reads, and a holder extended in
    place ("+=", "%=") is joined.
    """

    def __init__(self, files: dict[str, str], autoloads: dict[str, str]):
        self.files = {relative: _GdFile(relative, text) for relative, text in sorted(files.items())}
        self.by_path = {"res://" + relative.removeprefix("godot-client/"): gd for relative, gd in self.files.items()}
        self.by_class = {gd.class_name: gd for gd in self.files.values() if gd.class_name}
        self.by_class.update({name: self.by_path[path] for name, path in autoloads.items() if path in self.by_path})
        self._subclass_map: dict[str, list[_GdFile]] | None = None
        # name -> [(script, function index, statement index, token position)] of every name token.
        self.mentions: dict[str, list[tuple[_GdFile, int, int, int]]] = {}
        for gd in self.files.values():
            for index, function in self._functions(gd):
                for statement, (_line, tokens) in enumerate(function.statements):
                    for position, (kind, value) in enumerate(tokens):
                        if kind == "name":
                            self.mentions.setdefault(value, []).append((gd, index, statement, position))

    @staticmethod
    def _functions(gd: _GdFile):
        yield -1, gd.top
        yield from enumerate(gd.functions)

    @staticmethod
    def _function(gd: _GdFile, index: int) -> _GdFunction:
        return gd.top if index < 0 else gd.functions[index]

    def _base(self, gd: _GdFile) -> _GdFile | None:
        base = self.by_path.get(gd.extends) if gd.extends.startswith("res://") else self.by_class.get(gd.extends)
        return base if base is not gd else None

    def _chain(self, gd: _GdFile):
        seen = set()
        while gd is not None and gd.relative not in seen:
            seen.add(gd.relative)
            yield gd
            gd = self._base(gd)

    def _script(self, gd: _GdFile, name: str) -> _GdFile | None:
        """The script a name stands for in `gd`: a preload alias, a class_name or an autoload."""
        if name in gd.aliases:
            return self.by_path.get(gd.aliases[name])
        return self.by_class.get(name)

    def _member_owner(self, gd: _GdFile, name: str) -> _GdFile | None:
        return next((script for script in self._chain(gd) if name in script.members), None)

    @staticmethod
    def _local(function: _GdFunction, top: bool, name: str) -> bool:
        return not top and (name in function.locals or name in function.params)

    @staticmethod
    def _assignments(function: _GdFunction, name: str) -> list[list]:
        """The expressions a function assigns to its local `name` (var, const or "=")."""
        found = []
        for _line, tokens in function.statements:
            for position in range(len(tokens) - 1):
                if tokens[position][1] != name or tokens[position][0] != "name" \
                        or (position and tokens[position - 1][1] == "."):
                    continue
                declared = position and tokens[position - 1][1] in ("var", "const")
                if declared or (tokens[position + 1][1] in ("=", "+=") and _gd_depth(tokens, position) == 0):
                    assigned = next((p for p in range(position + 1, len(tokens))
                                     if tokens[p][1] in ("=", ":=", "+=") and _gd_depth(tokens, p) == 0), None)
                    found.append(tokens[assigned + 1:] if assigned is not None else [])
                elif position and tokens[position - 1][1] == "for":
                    found.append([])
        return found

    def _constant(self, gd: _GdFile, function: _GdFunction | None, token, seen: frozenset) -> str | None:
        """The literal a string token is, or a local assigned once or a script constant that
        is one whole literal."""
        kind, value = token
        if kind == "string":
            return _gd_string(value)
        if kind != "name" or value in seen:
            return None
        if function is not None and (value in function.locals or value in function.params):
            if value in function.params:
                return None
            assignments = self._assignments(function, value)
            return self.fold(gd, assignments[0], seen | {value}, function) if len(assignments) == 1 else None
        owner = self._member_owner(gd, value)
        if owner is None:
            return None
        for _line, tokens in owner.top.statements:
            head = next((p for p, token in enumerate(tokens) if token[1] in ("const", "var")), None)
            if head is not None and head + 1 < len(tokens) and tokens[head + 1][1] == value \
                    and tokens[head][1] == "const":
                assigned = next((p for p in range(head, len(tokens)) if tokens[p][1] in ("=", ":=")), None)
                if assigned is not None:
                    return self.fold(owner, tokens[assigned + 1:], seen | {value})
        return None

    def fold(self, gd: _GdFile, tokens: list, seen: frozenset = frozenset(),
             function: _GdFunction | None = None) -> str | None:
        """A constant path: one literal, constant or once-assigned local, or such parts joined
        by "+" and path_join()."""
        if not tokens:
            return None
        text = self._constant(gd, function, tokens[0], seen)
        position = 1
        while text is not None and position < len(tokens):
            if tokens[position][1] == "+" and position + 1 < len(tokens):
                part = self._constant(gd, function, tokens[position + 1], seen)
                text = None if part is None else text + part
                position += 2
            elif tokens[position][1] == "." and position + 3 < len(tokens) \
                    and tokens[position + 1][1] in ("path_join", "plus_file") and tokens[position + 2][1] == "(":
                close = _gd_close(tokens, position + 2)
                inner = tokens[position + 3:close]
                part = self._constant(gd, function, inner[0], seen) if len(inner) == 1 else None
                text = None if part is None else text.rstrip("/") + "/" + part.lstrip("/")
                position = close + 1
            else:
                return None
        return text

    def uses(self, relevant) -> dict:
        """{literal: {"raw": {(joined, where)}, "exact": {(path, where)}, "data": {(path, where)},
        "safe": count}} for every relevant literal in the runtime scripts (see the class notes):
        raw uses, raw reads of the exact constant path it builds, and data files read so."""
        found: dict[str, dict] = {}
        for gd in self.files.values():
            for index, function in self._functions(gd):
                for statement, (line, tokens) in enumerate(function.statements):
                    for position, (kind, value) in enumerate(tokens):
                        if kind != "string":
                            continue
                        literal = _gd_string(value)
                        if not relevant(literal):
                            continue
                        record = found.setdefault(literal, {"raw": set(), "exact": set(), "data": set(), "safe": 0})
                        self._follow(gd, index, statement, position, position, False, 0, record, {})
                for name, default in function.defaults.items():
                    for kind, value in default:
                        if kind == "string" and relevant(_gd_string(value)):
                            record = found.setdefault(_gd_string(value), {"raw": set(), "exact": set(), "data": set(),
                                                                         "safe": 0})
                            self._follow_local(gd, index, name, False, 1, record, {})
        return found

    def _function_owners(self, gd: _GdFile | None, name: str, overrides: bool = False) -> list[tuple[_GdFile, int]]:
        """The definition of `name` a call in `gd` binds to: the nearest in its chain and, with
        overrides (a call on self dispatches virtually), every subclass's override of it too."""
        found: list[tuple[_GdFile, int]] = []
        for script in self._chain(gd):
            if name in script.by_name:
                found = [(script, index) for index in script.by_name[name]]
                break
        if overrides and gd is not None:
            for script in self._subclasses(gd):
                found += [(script, index) for index in script.by_name.get(name, ())]
        return found

    def _subclasses(self, gd: _GdFile) -> list[_GdFile]:
        """Every script whose base chain holds `gd` (not `gd` itself)."""
        if self._subclass_map is None:
            self._subclass_map = {}
            for script in self.files.values():
                for base in list(self._chain(script))[1:]:
                    self._subclass_map.setdefault(base.relative, []).append(script)
        return self._subclass_map.get(gd.relative, [])

    def _callees(self, gd, function, top, dotted, receiver, callee) -> list[tuple[_GdFile, int]]:
        """The functions a call can only be: the script's own (or its base's) and any
        subclass's override of it, the base's for super, or another script's through its
        class_name, autoload or preload alias. An instance call on a value of unknown type
        has none."""
        if dotted and receiver == "super":
            return self._function_owners(self._base(gd), callee)
        if not dotted or receiver == "self":
            return self._function_owners(gd, callee, overrides=True)
        if not receiver or self._local(function, top, receiver):
            return []
        alias = next((script for script in self._chain(gd) if receiver in script.aliases), None)
        if alias is not None:
            script = self.by_path.get(alias.aliases[receiver])
        elif self._member_owner(gd, receiver) is None:
            script = self.by_class.get(receiver)
        else:
            script = None  # a member holding an instance of unknown type
        return self._function_owners(script, callee) if script is not None else []

    def _follow(self, gd, index, statement, start, end, joined, depth, record, visited, ret=None) -> None:
        function = self._function(gd, index)
        line, tokens = function.statements[statement]
        where = f"{gd.relative.removeprefix('godot-client/')}:{line}"
        top = index < 0
        for _guard in range(len(tokens) + 4):
            while end + 1 < len(tokens):
                following = tokens[end + 1][1]
                if following == "." and end + 2 < len(tokens) and tokens[end + 2][0] == "name":
                    method = tokens[end + 2][1]
                    if end + 3 < len(tokens) and tokens[end + 3][1] == "(":
                        if method in PREDICATE_METHODS:
                            record["safe"] += 1
                            return
                        joined = joined or method in JOINING_CALLS
                        end = _gd_close(tokens, end + 3)
                    else:
                        end += 2
                elif following == "[":
                    end = _gd_close(tokens, end + 1)
                else:
                    break
            before = tokens[start - 1][1] if start else ""
            after = tokens[end + 1][1] if end + 1 < len(tokens) else ""
            if before in ("+", "%") or after in ("+", "%"):
                joined = True
            opener, depth_seen = None, 0
            for position in range(start - 1, -1, -1):
                value = tokens[position][1]
                if value in (")", "]", "}"):
                    depth_seen += 1
                elif value in ("(", "[", "{"):
                    if depth_seen == 0:
                        opener = position
                        break
                    depth_seen -= 1
            in_for = opener is None and tokens[0][1] == "for" and before == "in"
            if (before in GD_COMPARISONS or after in GD_COMPARISONS) and not in_for:
                record["safe"] += 1
                return
            if opener is None:
                self._statement_use(gd, index, statement, start, joined, depth, record, visited, where, ret)
                return
            close = _gd_close(tokens, opener)
            keyword = opener > 0 and tokens[opener - 1][1] in GD_SKIP_NAMES
            if tokens[opener][1] == "{" or (tokens[opener][1] == "[" and (
                    not opener or keyword or not (tokens[opener - 1][0] == "name"
                                                 or tokens[opener - 1][1] in (")", "]")))):
                start, end = opener, close  # a list or dictionary holding it
                continue
            if tokens[opener][1] == "[":
                record["safe"] += 1  # a subscript: the value is a key
                return
            if opener and tokens[opener - 1][1] == "super" and not (opener >= 2 and tokens[opener - 2][1] == "."):
                record["raw"].add((joined, f"{where} passed to super()"))  # the base's own version
                return
            if not opener or tokens[opener - 1][0] != "name" or keyword:
                start, end = opener, close  # a parenthesised expression
                continue
            callee = tokens[opener - 1][1]
            dotted = opener >= 2 and tokens[opener - 2][1] == "."
            receiver = tokens[opener - 3][1] if dotted and opener >= 3 else ""
            if (not dotted and callee in RESOURCE_LOAD_CALLS) or receiver == "ResourceLoader" \
                    or (not dotted and callee in SAFE_CALLS):
                record["safe"] += 1
                return
            if receiver in RAW_READ_STATICS or callee in RAW_READ_ANY_METHODS \
                    or (dotted and callee in RAW_READ_RECEIVER_METHODS and self._script(gd, receiver) is None):
                arguments = _gd_arguments(tokens[opener + 1:close])
                first = opener + 1 + len(arguments[0]) if arguments else opener + 1
                path = self.fold(gd, arguments[0], function=None if top else function) \
                    if arguments and end < first else None
                if path is not None:
                    target = _literal_repo_path(path)
                    if target is not None and target.lower().endswith(LOOSE_DATA_SUFFIXES):
                        record["data"].add((posixpath.normpath(target), where))
                    else:  # exactly that file
                        record["exact"].add((path, f"{where} {receiver + '.' if receiver else ''}{callee}"))
                    return
                record["raw"].add((joined, f"{where} {receiver + '.' if receiver else ''}{callee}"))
                return
            level = _gd_depth(tokens, start)
            argument = sum(1 for position in range(opener + 1, start)
                           if tokens[position][1] == "," and _gd_depth(tokens, position) == level)
            if dotted and callee in PATTERN_METHODS and not (callee in ("replace", "replacen") and argument):
                record["safe"] += 1  # the literal is what a path is compared with or stripped of
                return
            if callee in TRANSPARENT_CALLS:
                joined = joined or callee in JOINING_CALLS
                start, end = opener - 1, close
                while start >= 2 and tokens[start - 1][1] == "." and tokens[start - 2][0] == "name":
                    start -= 2
                continue
            callees = self._callees(gd, function, top, dotted, receiver, callee)
            if callees and depth < LITERAL_USE_DEPTH:
                # Into the parameter it fills; what the function returns of it comes back here.
                returned: list = []
                for script, callee_index in callees:
                    params = script.functions[callee_index].params
                    if argument < len(params):
                        self._follow_local(script, callee_index, params[argument], joined, depth + 1, record,
                                           visited, returned)
                    else:
                        record["raw"].add((joined, f"{where} passed to {callee}() beyond its parameters"))
                if not returned:
                    return
                joined = joined or any(returned)
                start, end = opener - 1, close
                while start >= 2 and tokens[start - 1][1] == "." and tokens[start - 2][0] == "name":
                    start -= 2
                continue
            record["raw"].add((joined, f"{where} passed to {receiver + '.' if receiver else ''}{callee}()"))
            return
        record["raw"].add((joined, f"{where} (not followed)"))

    def _statement_use(self, gd, index, statement, start, joined, depth, record, visited, where, ret=None) -> None:
        function = self._function(gd, index)
        tokens = function.statements[statement][1]
        top = index < 0
        head = tokens[0][1]
        if head in ("if", "elif", "while", "for", "else", "match"):
            first = 0
            if head == "for":
                first = next((p for p in range(len(tokens)) if tokens[p][1] == "in"
                              and _gd_depth(tokens, p) == 0), len(tokens))
            colon = next((p for p in range(first + 1, len(tokens)) if tokens[p][1] == ":"
                          and _gd_depth(tokens, p) == 0), None)
            if head == "for" and len(tokens) > 1 and tokens[1][0] == "name" and first < start \
                    and (colon is None or start < colon):
                self._follow_local(gd, index, tokens[1][1], joined, depth + 1, record, visited, ret)
            elif colon is not None and start > colon:
                record["raw"].add((joined, f"{where} (one-line block)"))
            else:
                record["safe"] += 1  # a condition
            return
        declaration = head in ("static", "@") or head in ("var", "const") and any(
            token[1] in ("=", ":=") and _gd_depth(tokens, p) == 0 for p, token in enumerate(tokens))
        if head != "return" and not declaration:
            # A match branch with its body on the pattern's line ("a": return PATH, also after a
            # "var x when ..." binding): only the body after the pattern's colon uses the value.
            branch = next((p for p in range(start) if tokens[p][1] == ":" and _gd_depth(tokens, p) == 0), None)
            if branch is not None:
                if branch + 1 < len(tokens) and tokens[branch + 1][1] == "return" and ret is not None:
                    ret.append(joined)
                else:
                    record["raw"].add((joined, f"{where} (one-line block)"))
                return
        if head == "return":
            if ret is not None:
                ret.append(joined)  # back to the call being followed
            else:
                record["raw"].add((joined, f"{where} returned"))
            return
        assign = next((p for p, token in enumerate(tokens)
                       if token[1] in ("=", ":=", "+=") and _gd_depth(tokens, p) == 0), None)
        if assign is None:
            record["safe"] += 1  # an expression statement whose value is not kept
            return
        if start < assign:
            record["safe"] += 1  # on the left: a key
            return
        target = list(tokens[:assign])
        while target and target[0][1] in ("@", "static"):
            if target[0][1] == "@":
                target = target[2:]
                if target and target[0][1] == "(":
                    target = target[_gd_close(target, 0) + 1:]
            else:
                target = target[1:]
        declared = bool(target) and target[0][1] in ("var", "const") and len(target) > 1
        name = target[1][1] if declared else (target[0][1] if len(target) == 1 and target[0][0] == "name" else "")
        if declared and not top or (name and not declared and self._local(function, top, name)):
            self._follow_local(gd, index, name, joined, depth + 1, record, visited, ret)
            return
        if declared and top or (name and self._member_owner(gd, name) is not None):
            owner = self._member_owner(gd, name) or gd
            self._follow_member(owner, name, joined, depth + 1, record, visited)
            return
        if len(target) == 3 and target[0][1] == "self" and target[1][1] == "." and target[2][0] == "name":
            owner = self._member_owner(gd, target[2][1]) or gd
            self._follow_member(owner, target[2][1], joined, depth + 1, record, visited)
            return
        record["raw"].add((joined, f"{where} stored in {''.join(t[1] for t in target)[:60]}"))

    def _follow_local(self, gd, index, name, joined, depth, record, visited, ret=None) -> None:
        function = self._function(gd, index)
        mentions = [(statement, position) for statement, (_line, tokens) in enumerate(function.statements)
                    for position, (kind, value) in enumerate(tokens)
                    if kind == "name" and value == name and not (position and tokens[position - 1][1] == ".")]
        # "name += more" builds a longer path on what it holds.
        joined = joined or any(_gd_compound(function.statements[statement][1], position)
                               for statement, position in mentions)
        # `visited` remembers what each followed parameter returned: a second call of the same
        # function takes the same returns (a value returned to a load() at one call and to a raw
        # read at another is followed at both); one still being followed is a recursion.
        key = ("local", gd.relative, index, name, joined, ret is not None)
        if key in visited:
            if ret is not None:
                if visited[key] is None:
                    record["raw"].add((joined, f"{gd.relative.removeprefix('godot-client/')}: {name} (recursive)"))
                else:
                    ret.extend(visited[key])
            return
        visited[key] = None
        returns = [] if ret is not None else None
        if depth > LITERAL_USE_DEPTH:
            record["raw"].add((joined, f"{gd.relative.removeprefix('godot-client/')}: {name} (too deep)"))
        else:
            for statement, position in mentions:
                if not self._assigned_here(function.statements[statement][1], position):
                    self._follow(gd, index, statement, position, position, joined, depth, record, visited, returns)
        visited[key] = returns or []
        if ret is not None:
            ret.extend(returns)

    def _follow_member(self, owner, name, joined, depth, record, visited) -> None:
        key = ("member", owner.relative, name, joined)
        if key in visited:
            return
        visited[key] = []
        if depth > LITERAL_USE_DEPTH:
            record["raw"].add((joined, f"{owner.relative.removeprefix('godot-client/')}: {name} (too deep)"))
            return
        if not joined and any(_gd_compound(self._function(gd, index).statements[statement][1], position)
                              for gd, index, statement, position in self.mentions.get(name, [])
                              if self._member_owner(gd, name) is owner):
            self._follow_member(owner, name, True, depth, record, visited)  # "name += more"
            return
        for gd, index, statement, position in self.mentions.get(name, []):
            function = self._function(gd, index)
            tokens = function.statements[statement][1]
            dotted = position and tokens[position - 1][1] == "."
            if dotted:
                receiver = tokens[position - 2] if position >= 2 else ("", "")
                if receiver[1] != "self":
                    target = self._script(gd, receiver[1]) if receiver[0] == "name" else None
                    if target is not None and self._member_owner(target, name) is not owner:
                        continue  # another script's member of that name
                elif self._member_owner(gd, name) is not owner:
                    continue
            else:
                if self._local(function, index < 0, name) or self._member_owner(gd, name) is not owner:
                    continue
            if self._assigned_here(tokens, position):
                continue
            start = position - 2 if dotted else position
            self._follow(gd, index, statement, start, position, joined, depth, record, visited)

    @staticmethod
    def _assigned_here(tokens: list, position: int) -> bool:
        """Whether the name at `position` is what its statement declares or assigns."""
        if position and tokens[position - 1][1] in ("var", "const", "for", "func"):
            return True
        after = tokens[position + 1][1] if position + 1 < len(tokens) else ""
        if after in ("=", ":=", "+=", "%=") and _gd_depth(tokens, position) == 0:
            return True
        return after == ":" and position and tokens[position - 1][1] in ("var", "const")


def _gd_compound(tokens: list, position: int) -> bool:
    """Whether the name at `position` is extended in place ("name += ...", "name %= ...")."""
    return position + 1 < len(tokens) and tokens[position + 1][1] in ("+=", "%=") and _gd_depth(tokens, position) == 0


def _gd_depth(tokens: list, position: int) -> int:
    """The bracket depth at `position` in a statement."""
    depth = 0
    for value in tokens[:position]:
        if value[1] in ("(", "[", "{"):
            depth += 1
        elif value[1] in (")", "]", "}"):
            depth -= 1
    return depth


def loose_read_allowlist(build_dir: Path, candidates: set[str]) -> dict:
    """What of `candidates` (repository paths) the running client may read raw, from its
    code (W2-UD-02): a generated allowlist.

    Every literal in a runtime GDScript (runtime_client_sources) that names a candidate,
    a folder or prefix holding one, or a data file (LOOSE_DATA_SUFFIXES) under godot-client,
    is followed by _LiteralUses. One with any use that is not the resource system names its
    file - joined, its folder - as read raw; if it names a data file, so is everything that
    file names, and its folder. A data file read by its exact constant path is a "data"
    read (data_reads). A folder or prefix literal used only by the resource system is
    "resource only": composing paths under it never reads raw (resource_prefixes, used by
    loose_data_names). Also read raw: the asset paths project.godot names (the engine reads
    its icon and boot splash as images), any asset path in a scene or resource outside an
    ext_resource header, every asset path a native source that reads files itself names,
    and LOOSE_STAGE_READERS. Returns {"files": {repository path: {where}}, "prefixes":
    {repository prefix: {where}}, "data_reads": {data file: {where}}, "resource_prefixes":
    {prefix}, "literals": count}.
    """
    files: dict[str, set[str]] = {}
    prefixes: dict[str, set[str]] = {}

    def note(named, under, where) -> None:
        for name in named:
            files.setdefault(name, set()).update(where)
        for name in under:
            prefixes.setdefault(name, set()).update(where)

    lowered = sorted(candidate.lower() for candidate in candidates)
    candidate_set = set(lowered)
    data_names: dict[str, tuple[set[str], set[str]]] = {}
    for relative in tracked(build_dir, "godot-client"):
        if relative.lower().endswith(LOOSE_DATA_SUFFIXES) and not relative.startswith(UNSHIPPED_CLIENT_DIRS):
            data_names[relative.lower()] = _data_names(build_dir, relative)
    naming = sorted(data for data, (named, under) in data_names.items()
                    if {n.lower() for n in named} & candidate_set
                    or any(c.startswith(u.lower()) for u in under for c in lowered))

    def reaches(named: set[str], under: set[str]) -> bool:
        if any(path.lower() in candidate_set or path.lower() in data_names and path.lower() in naming
               for path in named):
            return True
        return any(any(c.startswith(prefix.lower()) for c in lowered)
                   or any(d.startswith(prefix.lower()) for d in naming) for prefix in under)

    relevant_cache: dict[str, bool] = {}

    def relevant(literal: str) -> bool:
        # The bare project root ("res://") names nothing by itself: what is joined to it
        # does, and an asset path in data is loose_data_names' (a code literal naming
        # assets/ or a folder under it is followed here).
        if literal not in relevant_cache:
            root = (_literal_repo_path(literal) or "").rstrip("/") in ("godot-client", "godot-client/.")
            relevant_cache[literal] = _path_like(literal) and not root \
                and (reaches(*_literal_reach(build_dir, literal, False))
                     or reaches(*_literal_reach(build_dir, literal, True)))
        return relevant_cache[literal]

    def data_files_named(named: set[str], under: set[str]) -> list[str]:
        found = [name.lower() for name in named if name.lower() in data_names]
        found += [data for prefix in under for data in data_names if data.startswith(prefix.lower())]
        return sorted(set(found))

    sources = runtime_client_sources(build_dir)
    scripts = {relative: (build_dir / relative).read_text(encoding="utf-8", errors="replace")
               for relative in sources if relative.endswith(".gd")}
    settings = build_dir / "godot-client/project.godot"
    autoloads = dict(re.findall(r'(?m)^(\w+)="\*?(res://[^"]+\.gd)"', settings.read_text(encoding="utf-8"))) \
        if settings.is_file() else {}
    data_reads: dict[str, set[str]] = {}
    resource_prefixes: set[str] = set()
    for literal, record in sorted(_LiteralUses(scripts, autoloads).uses(relevant).items()):
        for path, where in record["data"]:
            data_reads.setdefault(path.lower(), set()).add(where)
        for path, where in record["exact"]:
            note(*_literal_reach(build_dir, path, False), {where})
        if not record["raw"] and not record["exact"]:
            named, under = _literal_reach(build_dir, literal, False)
            if under and not named:
                resource_prefixes |= {prefix.lower() for prefix in under}
            continue
        for joined, where in record["raw"]:
            named, under = _literal_reach(build_dir, literal, joined)
            note(named, under, {where})
            for data in data_files_named(*_literal_reach(build_dir, literal, False)):
                note(*data_names[data], {f"{where} via {data.removeprefix('godot-client/')}"})
                note(set(), {posixpath.dirname(data) + "/"}, {f"{where} beside {data.removeprefix('godot-client/')}"})
    for relative in sources:
        if relative.endswith(".gd"):
            continue
        text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
        if relative.endswith((".tscn", ".tres")):
            text = SCENE_EXT_RESOURCE.sub("", text)  # what a scene loads, the resource system loads
        elif relative != "godot-client/project.godot" and not NATIVE_RAW_READ.search(text):
            continue
        for match in SOURCE_LITERAL.finditer(text):
            if relevant(match.group(2)):
                note(*_literal_reach(build_dir, match.group(2), False), {relative.removeprefix("godot-client/")})
    for local, reader in LOOSE_STAGE_READERS.items():
        files.setdefault("godot-client/" + local, set()).add(reader)
    return {"files": files, "prefixes": prefixes, "data_reads": data_reads,
            "resource_prefixes": resource_prefixes, "literals": sum(relevant_cache.values())}


def loose_data_names(build_dir: Path, candidates: set[str], resource_prefixes: set[str] = frozenset(),
                     served=None) -> dict[str, set[str]]:
    """{candidate: {data file}}: the candidates the data a package carries names (W2-UD-02).

    Map data and the client's data drive raw reads whose path no code literal holds (a map
    manifest's externalResources are hashed from disk, a registry names manifests), so:
    a candidate any shipped data names by a res://, assets/ or data/ path - a godot-client
    data file (LOOSE_DATA_SUFFIXES) outside docs/tests/tools, or an eloria-assets JSON that
    ships - stays loose. A name relative to its data file's folder keeps a candidate too,
    unless the data file's own folder is one the code uses only through the resource
    system (loose_read_allowlist "resource_prefixes": the audio catalog names its tracks
    relative to assets/audio/, and every literal naming that folder ends in a load()); a
    data file another data file names by path has no such code, so its relative names
    always count.
    """
    if not candidates:
        return {}
    lowered = {candidate.lower(): candidate for candidate in candidates}
    resource_prefixes = {prefix.lower() for prefix in resource_prefixes}
    if served is None:
        served = read_served_v2_packages(build_dir) if (build_dir / REGISTRY_FILE).is_file() else []
    data_files = [p for p in tracked(build_dir, "godot-client") if p.lower().endswith(LOOSE_DATA_SUFFIXES)
                  and not p.startswith(UNSHIPPED_CLIENT_DIRS)]
    data_files += [p for p in sorted(shipped_eloria_assets(build_dir, served=served)[0])
                   if p.lower().endswith(".json")]
    named: dict[str, set[str]] = {}
    indirect: set[str] = set()
    relative_names: dict[str, set[str]] = {}
    for relative in data_files:
        path = build_dir / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        try:
            strings = list(_json_strings(json.loads(text))) if relative.lower().endswith(".json") else \
                re.split(r"[\s\"',;=()\[\]{}<>|]+", text)
        except ValueError:
            strings = [m.group(2) for m in SOURCE_LITERAL.finditer(text)]
        folder = posixpath.dirname(relative)
        for value in strings:
            if not value or len(value) > 1024:
                continue
            path_value = _literal_repo_path(value)
            if path_value is not None:
                low = posixpath.normpath(path_value).lower()
                if low in lowered:
                    named.setdefault(lowered[low], set()).add(relative)
                if low.endswith(LOOSE_DATA_SUFFIXES):
                    indirect.add(low)
            elif "." in value and ":" not in value and not value.startswith("/") \
                    and relative.startswith("godot-client/"):
                target = posixpath.normpath(posixpath.join(folder, value.replace("\\", "/"))).lower()
                if target in lowered:
                    relative_names.setdefault(relative.lower(), set()).add(lowered[target])
    for data, names in relative_names.items():
        # Code that joins these names to exactly this folder only to load them clears them.
        cleared = data not in indirect and posixpath.dirname(data) + "/" in resource_prefixes
        for name in names:
            if not cleared:
                named.setdefault(name, set()).add(data)
    return named


# actor_images.gd PIXEL_READING_MATERIALS: material extensions that make it leave URI images to
# GLTFDocument's own (raw) read.
ACTOR_PIXEL_READING_MATERIALS = (b"KHR_materials_pbrSpecularGlossiness",)


def _actor_glb_reads_imports(build_dir: Path) -> bool:
    """Whether the build tree parses actor glTFs through actor_images.gd (AW-03), which loads
    a URI image through ResourceLoader at the path GLTFDocument resolves before any raw read."""
    images = build_dir / "godot-client/src/actors/actor_images.gd"
    cache = build_dir / "godot-client/src/actors/glb_scene_cache.gd"
    if not images.is_file() or not cache.is_file():
        return False
    text = images.read_text(encoding="utf-8", errors="replace")
    return ("func resolve_uri" in text and "ResourceLoader.load(path" in text
            and "ActorImages.enable(" in cache.read_text(encoding="utf-8", errors="replace"))


def gltf_uri_raw_reads(build_dir: Path, imported: set[str]) -> dict[str, set[str]]:
    """{repository path: {"<glTF> -> <uri>"}} of the images shipped glTFs name by URI and read raw.

    A glTF URI is a raw read unless it resolves through an import: only an actor glTF
    (under assets/actors, parsed by the AW-03 actor-parse path, actor_images.gd) takes a
    URI image from ResourceLoader at the path GLTFDocument resolves, and only an image in
    `imported` (repository paths whose .import and products the PCK holds) is there to take.
    Every other glTF a package carries - world models through the scenery image pass, the
    editor's imported scenes, anything else - reads the file. In a build tree without the
    AW-03 path every URI counts as a raw read.
    """
    actor_imports = _actor_glb_reads_imports(build_dir)
    reads: dict[str, set[str]] = {}
    for relative in shipped_client_files(build_dir, GLTF_SUFFIXES):
        # "unchecked" until a URI of an actor document names an imported image; then "imports"
        # or, for a document with a pixel-reading material (actor_images.gd
        # PIXEL_READING_MATERIALS: spec-gloss, left to GLTFDocument's own raw read), "raw".
        actor = "unchecked" if actor_imports and relative.startswith("godot-client/assets/actors/") else "raw"
        for uri in _possible_gltf_uris(build_dir / relative):
            if not uri or uri.startswith("data:"):
                continue
            target = _resolve(relative, uri)
            if actor != "raw" and target in imported:
                if actor == "unchecked":
                    text = _gltf_json_bytes(build_dir / relative)
                    actor = "raw" if any(name in text for name in ACTOR_PIXEL_READING_MATERIALS) else "imports"
                if actor == "imports":
                    continue
            reads.setdefault(target, set()).add(f"{relative.removeprefix('godot-client/')} -> {uri}")
    return reads


def loose_duplicate_candidates(build_dir: Path, packed: set[str], platform: str = "") -> dict[str, str]:
    """{repository path: godot-client-relative path} of the loose files the PCK also holds
    imported: a tracked file of LOOSE_DUPLICATE_SUFFIXES under godot-client/assets, outside
    the actor tree (actor_shipping decides those) and LOOSE_ALWAYS_*, whose .import remap
    and every product it names (exported_import_products) are in `packed` (pck_paths)."""
    project = build_dir / "godot-client"
    candidates: dict[str, str] = {}
    for relative in tracked(build_dir, "godot-client/assets"):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        if relative.startswith(ACTOR_ROOT + "/") or not local.lower().endswith(LOOSE_DUPLICATE_SUFFIXES) \
                or local in LOOSE_ALWAYS_FILES or local + ".import" not in packed:
            continue
        sidecar = project / (local + ".import")
        products = exported_import_products(sidecar, platform) if sidecar.is_file() else []
        if products and all(product in packed for product in products):
            candidates[relative] = local
    return candidates


# One build tree's reads per candidate set: the check after a re-export asks again.
# _main clears it, so a later run on the same build folder (another commit) reads afresh.
_LOOSE_READ_CACHE: dict = {}


def loose_duplicate_plan(build_dir: Path, packed: set[str], platform: str = "") -> dict:
    """Which loose duplicates of PCK-imported resources ship in the PCK only (W2-UD-02).

    Of loose_duplicate_candidates, a file stays loose when anything may read it raw: the
    running client's code (loose_read_allowlist), a glTF URI that does not resolve
    through an import (gltf_uri_raw_reads), the data a package carries
    (loose_data_names) or a reader of the stage (LOOSE_STAGE_READERS). Every other one is
    dropped from app/. Returns {"drop": {godot-client-relative: bytes}, "keep":
    {godot-client-relative: [why]}, "literals": path literals followed}.
    """
    candidates = loose_duplicate_candidates(build_dir, packed, platform)
    key = (str(build_dir.resolve()), frozenset(candidates))
    if key not in _LOOSE_READ_CACHE:
        allowlist = loose_read_allowlist(build_dir, set(candidates))
        _LOOSE_READ_CACHE.clear()
        _LOOSE_READ_CACHE[key] = (allowlist, gltf_uri_raw_reads(build_dir, set(candidates)),
                                  loose_data_names(build_dir, set(candidates), allowlist["resource_prefixes"]))
    allowlist, uri_reads, data_reads = _LOOSE_READ_CACHE[key]
    prefixes = sorted((prefix.lower(), where) for prefix, where in allowlist["prefixes"].items())
    files: dict[str, set[str]] = {}
    for path, where in allowlist["files"].items():
        files.setdefault(path.lower(), set()).update(where)
    drop: dict[str, int] = {}
    keep: dict[str, list[str]] = {}
    for relative, local in sorted(candidates.items()):
        lowered = relative.lower()
        why = sorted(files.get(lowered, ()))
        why += sorted(w for prefix, where in prefixes if lowered.startswith(prefix) for w in where)
        why += sorted(uri_reads.get(relative, ()))
        why += sorted(f"named by {data.removeprefix('godot-client/')}" for data in data_reads.get(relative, ()))
        if why:
            keep[local] = why
        else:
            drop[local] = (build_dir / relative).stat().st_size
    return {"drop": drop, "keep": keep, "literals": allowlist["literals"]}


def check_loose_duplicates(build_dir: Path, app_dir: Path, platform: str = "") -> dict:
    """Every tracked file under godot-client/assets outside the actor tree ships somewhere,
    and a file a raw read may open ships loose (W2-UD-02).

    Run on the final PCK. A file not staged loose must be in the PCK as itself or as an
    import whose products are all there, and must not be one loose_duplicate_plan keeps
    (a raw read, a URI, data or a stage reader names it); LOOSE_ALWAYS_* and
    LOOSE_STAGE_READERS files must be staged. Returns the plan.
    """
    packed = pck_paths(app_dir / "RabbitLands.pck")
    plan = loose_duplicate_plan(build_dir, packed, platform)
    world = world_import_shipping(build_dir)
    project = build_dir / "godot-client"
    problems: list[str] = []
    for relative in tracked(build_dir, "godot-client/assets"):
        if relative.endswith((".import", ".report.json")) or relative.startswith(ACTOR_ROOT + "/") \
                or relative in world["dropped_images"]:
            continue
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        loose = (app_dir / local).is_file()
        always = local in LOOSE_ALWAYS_FILES or local in LOOSE_STAGE_READERS \
            or local.lower().endswith(LOOSE_ALWAYS_SUFFIXES)
        if loose:
            continue
        if always:
            problems.append(f"{local}: must ship loose ({LOOSE_STAGE_READERS.get(local, 'always loose')})")
        elif local in plan["keep"]:
            problems.append(f"{local}: read raw ({plan['keep'][local][0]}) but not staged loose")
        elif local not in packed:
            sidecar = project / (local + ".import")
            products = exported_import_products(sidecar, platform) if sidecar.is_file() else []
            if local + ".import" not in packed or not products or any(p not in packed for p in products):
                problems.append(f"{local}: neither loose nor in the PCK")
    if problems:
        raise PackageError(f"{len(problems)} client assets are not shipped where they are read:\n  "
                           + "\n  ".join(problems[:40]))
    log(f"checked loose duplicates: {len(plan['drop'])} imported resources ({sum(plan['drop'].values()) / 1e6:.1f} MB) "
        f"ship in the PCK only, {len(plan['keep'])} kept loose for raw reads "
        f"({plan['literals']} path literals followed)")
    return plan


# --- staging -----------------------------------------------------------------

def copy_file(source: Path, target: Path) -> int:
    if STORAGE or (BENCHMARK_LINKS and source.suffix.lower() in {
            ".glb", ".gltf", ".png", ".jpg", ".jpeg", ".webp", ".ktx", ".ktx2",
            ".ogg", ".ogv", ".wav", ".mp3"}):
        return release_storage.link_file(source, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return source.stat().st_size


def stage_loose_client_files(build_dir: Path, app_dir: Path, platform: str = "") -> dict:
    # Actor files ship once: the PCK-only ones (face masks, equipment URI
    # textures) and the dropped images stay out of app/.
    shipping = actor_shipping(build_dir)
    world = world_import_shipping(build_dir)
    loose_actors = shipping["loose"]
    # Anything the export recognised as a resource is IN the pack and loaded
    # from it (`load("res://assets/ui/start_screen/....ogv")`), so a loose copy
    # is the same bytes twice: the six start-screen videos alone were 142 MB.
    # So is an imported resource nothing reads raw (W2-UD-02,
    # loose_duplicate_plan): its .import and products are in the pack.
    # Text records stay loose wherever they live, whatever the pack holds:
    # the launcher, the updater and the packager's own steps read them from
    # disk rather than through Godot (AUDIO-CREDITS is built from the staged
    # assets/audio/provenance.json, which the pack also carries).
    packed = pck_paths(app_dir / "RabbitLands.pck")
    duplicates = loose_duplicate_plan(build_dir, packed, platform)
    total = staged = pck_only = dropped = dropped_bytes = packed_only = packed_bytes = 0
    files = tracked(build_dir, "godot-client/assets", "godot-client/data", "godot-client/schemas")
    for relative in files:
        if relative.endswith((".import", ".report.json")):
            continue
        if relative in world["dropped_images"]:
            continue
        if relative.startswith(ACTOR_ROOT + "/") and relative not in loose_actors:
            if relative in shipping["dropped"]:
                dropped += 1
                dropped_bytes += (build_dir / relative).stat().st_size
            else:
                pck_only += 1
            continue
        inside = PurePosixPath(relative).relative_to("godot-client")
        local = inside.as_posix()
        if local in duplicates["drop"] or (
                local in packed and inside.parts[0] not in LOOSE_ALWAYS_ROOTS
                and inside.suffix.lower() not in LOOSE_ALWAYS_SUFFIXES
                and local not in LOOSE_ALWAYS_FILES and local not in LOOSE_STAGE_READERS):
            packed_only += 1
            packed_bytes += (build_dir / relative).stat().st_size
            continue
        total += copy_file(build_dir / relative, app_dir / inside)
        staged += 1
    log(f"staged {staged} loose client files ({total / 1e9:.2f} GB); "
        f"{pck_only} actor files ship in the PCK only; {dropped} unnamed actor images "
        f"({dropped_bytes / 1e6:.0f} MB) ship nowhere; {packed_only} resources "
        f"({packed_bytes / 1e6:.0f} MB) ship in the PCK only, of them {len(duplicates['drop'])} imported "
        f"duplicates ({sum(duplicates['drop'].values()) / 1e6:.0f} MB); {len(duplicates['keep'])} imported "
        "resources stay loose for raw reads")
    return duplicates


def strip_rl_head_stage(build_dir: Path, logs: Path, platform: str = "") -> dict:
    """Strip the build tree's RL hair and beard GLBs' embedded copies of the RL head maps (AT-C0).

    The first package-time actor transform, on the disposable build tree
    before the import (wave-2 schedule 1.1 #6: RL image strip, attribute
    quantisation, import, actor geometry cook, actor VRAM sidecars, export),
    so the import, every cook and stage_loose_client_files see the stripped
    bytes. The maps compared against are the RL head maps this package ships
    in the PCK (actor_shipping's folder_textures); a removed copy's map must
    have a committed import naming its products, and check_rl_head_strip_pack
    proves them in the exported PCK. Files are replaced by new ones, so a
    hard-linked source never writes through. The receipt is
    logs/rl-head-strip.json.
    """
    folder = f"godot-client/{strip_rl_head_images.MAP_DIR}/"
    maps: dict[str, list[str]] = {}
    for relative in sorted(actor_shipping(build_dir)["folder_textures"]):
        if relative.startswith(folder) and "/" not in relative[len(folder):]:
            digest = hashlib.sha256((build_dir / relative).read_bytes()).hexdigest()
            maps.setdefault(digest, []).append(PurePosixPath(relative).name)
    project = build_dir / "godot-client"

    def will_pack(local: str) -> bool:  # every map compared against is one the PCK ships
        sidecar = project / (local + ".import")
        return sidecar.is_file() and bool(exported_import_products(sidecar, platform))

    try:
        return strip_rl_head_images.strip_stage(
            project, build_dir, receipt=logs / "rl-head-strip.json", pck_has=will_pack, maps=maps,
            budget=STORAGE.check if STORAGE else None, log=log)
    except strip_rl_head_images.StripError as error:
        raise PackageError(f"RL head image strip: {error}") from error


def check_rl_head_strip_pack(build_dir: Path, app_dir: Path, logs: Path, platform: str = "") -> int:
    """Every map whose embedded copy strip_rl_head_stage removed is in the exported PCK
    as its .import remap and every product it names (AT-C0); returns how many."""
    receipt = json.loads((logs / "rl-head-strip.json").read_text(encoding="utf-8"))
    named = sorted({f"{strip_rl_head_images.MAP_DIR}/{name}" for row in receipt["files"]
                    for image in row["removed"] for name in image["named"]})
    packed = pck_paths(app_dir / "RabbitLands.pck")
    project = build_dir / "godot-client"
    missing = []
    for local in named:
        sidecar = project / (local + ".import")
        products = exported_import_products(sidecar, platform) if sidecar.is_file() else []
        if local + ".import" not in packed or not products or any(p not in packed for p in products):
            missing.append(local)
    if missing:
        raise PackageError(f"{len(missing)} RL head maps lost their embedded copies but are not imported in the "
                           "PCK:\n  " + "\n  ".join(missing[:40]))
    return len(named)


def pck_paths(pck: Path) -> set[str]:
    """Every path in a Godot 4 PCK's directory (formats 2 to 4), without res://."""
    with open(pck, "rb") as handle:
        if handle.read(4) != b"GDPC":
            raise PackageError(f"{pck} is not a Godot PCK")
        version = struct.unpack("<4I", handle.read(16))[0]
        flags = 0
        directory = None
        if version >= 2:
            flags, = struct.unpack("<I", handle.read(4))
            handle.read(8)  # file base
        if version >= 3:
            directory, = struct.unpack("<Q", handle.read(8))
        handle.read(16 * 4)
        if directory is not None:
            handle.seek(directory)
        if flags & 1:
            raise PackageError(f"{pck} has an encrypted directory")
        count, = struct.unpack("<I", handle.read(4))
        paths = set()
        for _ in range(count):
            length, = struct.unpack("<I", handle.read(4))
            name = handle.read(length).rstrip(b"\0").decode("utf-8", "replace")
            handle.read(16 + 16 + (4 if version >= 2 else 0))  # offset, size, md5, flags
            paths.add(name.removeprefix("res://"))
    return paths


def exported_import_products(sidecar: Path, platform: str = "") -> list[str]:
    products = _import_products(sidecar)
    if platform == "macos":
        # Godot 4.7.2 declares s3tc/bptc for universal Mac presets. Both
        # texture families must be imported for export validation, but the
        # universal PCK intentionally omits the mobile variants.
        products = [path for path in products if not path.endswith((".etc2.ctex", ".astc.ctex"))]
    return products


def check_actor_pack(build_dir: Path, app_dir: Path, platform: str = "") -> None:
    """Each actor file is in exactly one place - the PCK or app/assets - or, if dropped, in none.

    The PCK must hold every PCK-only actor resource (as its .import remap and
    the imported product it names or, for .json/.bin, the file itself) and no
    other actor entry; app/assets must hold every loose file and no other
    actor file.
    """
    shipping = actor_shipping(build_dir)
    paths = pck_paths(app_dir / "RabbitLands.pck")
    project = build_dir / "godot-client"
    problems: list[str] = []
    expected: set[str] = set()
    for relative in sorted(shipping["pck"]):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        entry = local if local.endswith(PLAIN_EXPORT_SUFFIXES) else local + ".import"
        expected.add(entry)
        if entry not in paths:
            problems.append(f"{local}: not in the PCK")
        elif entry.endswith(".import"):
            sidecar = project / entry
            products = exported_import_products(sidecar, platform) if sidecar.is_file() else []
            if not products or any(p not in paths for p in products):
                problems.append(f"{local}: its imported product is not in the PCK")
        if (app_dir / local).exists():
            problems.append(f"{local}: also staged loose")
    # An imported file reaches the PCK with its remap under its own path, so
    # anything else under assets/actors in the PCK leaked into the import.
    actor_prefix = PurePosixPath(ACTOR_ROOT).relative_to("godot-client").as_posix() + "/"
    leaked = sorted(p for p in paths if p.startswith(actor_prefix) and p not in expected)
    problems.extend(f"{p}: an actor file that ships loose or nowhere is in the PCK" for p in leaked[:20])
    for relative in sorted(shipping["loose"]):
        if not (app_dir / PurePosixPath(relative).relative_to("godot-client")).is_file():
            problems.append(f"{relative}: not staged loose")
    for relative in sorted(shipping["dropped"]):
        if (app_dir / PurePosixPath(relative).relative_to("godot-client")).exists():
            problems.append(f"{relative}: a dropped image was staged loose")
    if problems:
        raise PackageError(f"{len(problems)} actor files are not shipped exactly once:\n  "
                           + "\n  ".join(problems[:40]))
    log(f"checked actor files: {len(shipping['pck'])} in the PCK only "
        f"({len(shipping['uri_textures'])} URI textures, {len(shipping['folder_textures'])} RL head maps), "
        f"{len(shipping['loose'])} loose only, "
        f"{len(shipping['dropped'])} dropped")


def check_scene_texture_pack(build_dir: Path, app_dir: Path, platform: str = "") -> None:
    """Every scene texture is in the PCK as its .import remap and the VRAM product it names."""
    paths = pck_paths(app_dir / "RabbitLands.pck")
    project = build_dir / "godot-client"
    textures = scene_textures(build_dir)
    problems: list[str] = []
    for relative in sorted(textures):
        local = PurePosixPath(relative).relative_to("godot-client").as_posix()
        products = exported_import_products(project / (local + ".import"), platform)
        if local + ".import" not in paths:
            problems.append(f"{local}: not in the PCK")
        elif not products or any(p not in paths for p in products):
            problems.append(f"{local}: its imported product is not in the PCK")
    if problems:
        raise PackageError(f"{len(problems)} scene textures are missing from the PCK:\n  "
                           + "\n  ".join(problems[:40]))
    log(f"checked {len(textures)} scene textures in the PCK")


def check_editor_sources_unpacked(app_dir: Path) -> None:
    """The PCK holds nothing of the map editor's sources (EDITOR_ONLY_PCK_DIRS).

    The export's exclude filter keeps them out; this catches a preset written
    without it. Their imported products sit under .godot and are packed only
    with the remap of a source the export keeps, so the remaps tell.
    """
    stray = sorted(p for p in pck_paths(app_dir / "RabbitLands.pck") if p.startswith(EDITOR_ONLY_PCK_DIRS))
    if stray:
        raise PackageError(f"{len(stray)} files of the map editor's sources are in the PCK:\n  "
                           + "\n  ".join(stray[:40]))
    log(f"checked the PCK: nothing under {', '.join(EDITOR_ONLY_PCK_DIRS)}")


def stage_audio_credits(app_dir: Path, stage: Path) -> None:
    """Fail the build if licensed audio would ship without its notices."""
    audio = app_dir / "assets/audio"
    provenance = json.loads((audio / "provenance.json").read_text(encoding="utf-8"))
    credits = (audio / "CREDITS.txt").read_text(encoding="utf-8")
    for source in provenance["sources"].values():
        if not (audio / "licenses" / (source["license"] + ".txt")).is_file():
            raise PackageError("missing audio license: " + source["license"])
        if any(source[key] not in credits for key in ("creator", "url", "license_url")):
            raise PackageError("missing audio attribution: " + source["title"])
    copy_file(audio / "CREDITS.txt", stage / "AUDIO-CREDITS.txt")


def is_shipped_map_file(relative: PurePosixPath) -> bool:
    if any(part in MAP_EXCLUDED_DIRS for part in relative.parts[:-1]):
        return False
    name = relative.name
    if relative.suffix.lower() in MAP_EXCLUDED_SUFFIXES or name == ".gitignore":
        return False
    if MAP_LOD_PACKAGE.match(name):
        return False
    return not (name.endswith(".validator.json") or name.endswith("report.json"))


def json_strings(value, skip: set[str], key: str = ""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key not in skip:
                yield from json_strings(child, skip, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from json_strings(child, skip, key)
    elif isinstance(value, str):
        yield key, value


def preview_map_folders(registry: dict) -> list[str]:
    """The map folders of the registry's preview rows (PREVIEW_MAP_STATUSES): the folder its manifest names, or its
    parent when that folder is the region's client/ package (the editor stub beside it is not shipped either)."""
    folders = []
    for entry in registry.get("maps", {}).values():
        if not isinstance(entry, dict) or entry.get("status") not in PREVIEW_MAP_STATUSES:
            continue
        match = ASSET_REF.search(str(entry.get("manifest", "")))
        if not match:
            continue
        folder = PurePosixPath(match.group(1)).parent
        if folder.name == "client":
            folder = folder.parent
        folders.append(str(folder))
    return sorted(set(folders))


def drop_preview_maps(build_dir: Path) -> list[str]:
    """Removes the preview rows from the build tree's registry (a detached worktree of the packaged commit; the export
    reads it from there) and returns their map folders, which stage_eloria_assets leaves out."""
    path = build_dir / REGISTRY_FILE
    registry = json.loads(path.read_text(encoding="utf-8"))
    folders = preview_map_folders(registry)
    previews = [key for key, entry in registry.get("maps", {}).items()
                if isinstance(entry, dict) and entry.get("status") in PREVIEW_MAP_STATUSES]
    if previews:
        for key in previews:
            del registry["maps"][key]
        path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        log(f"left out {len(previews)} preview maps ({', '.join(previews)}): {', '.join(folders)}")
    return folders


def served_v2_packages(registry: dict) -> list[tuple[str, str]]:
    """(package folder, territory folder) of each registry row a continent-v2 server map has (SERVED_V2_STATUSES):
    the folder its manifest names, and the territory folder that holds it when it is the territory's client/ package
    (else the package folder itself)."""
    packages = []
    for entry in registry.get("maps", {}).values():
        if not isinstance(entry, dict) or entry.get("status") not in SERVED_V2_STATUSES:
            continue
        match = ASSET_REF.search(str(entry.get("manifest", "")))
        if not match:
            continue
        folder = PurePosixPath(match.group(1)).parent
        territory = folder.parent if folder.name == "client" else folder
        packages.append((str(folder), str(territory)))
    return sorted(set(packages))


def read_served_v2_packages(build_dir: Path) -> list[tuple[str, str]]:
    """served_v2_packages of the build tree's registry."""
    return served_v2_packages(json.loads((build_dir / REGISTRY_FILE).read_text(encoding="utf-8")))


def _under(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def _ships_asset(path: str, excluded: list[str] = (), served: list[tuple[str, str]] = ()) -> bool:
    """Whether a package may ship the eloria-assets file `path`: nothing under an `excluded` map folder, and of a
    `served` continent-v2 map (served_v2_packages) only its client package, without SERVER_ONLY_FILES."""
    if any(_under(path, folder) for folder in excluded):
        return False
    for package, territory in served:
        if _under(path, package):
            return PurePosixPath(path).name not in SERVER_ONLY_FILES
        if _under(path, territory):
            return False
    return True


def shipped_eloria_assets(build_dir: Path, excluded: list[str] = (),
                          served: list[tuple[str, str]] = ()) -> tuple[set[str], list[str], list[str]]:
    """The eloria-assets files a package ships: (files, errors, warnings).

    Every map package's shipped files, every file the client names, and the
    closure of the files those manifests name - none under an `excluded` map
    folder, and of a `served` continent-v2 map (served_v2_packages) only its
    client package, without SERVER_ONLY_FILES (_ships_asset). A manifest that
    ships pulls in the shared prototype meshes it names (SHARED_MESH_KEY) from
    the pool, which is in no map package of its own.
    """
    served_folders = [package for package, _ in served]
    all_tracked = {p for p in tracked(build_dir, "eloria-assets") if _ships_asset(p, excluded, served)}
    wanted: set[str] = set()
    wanted.update(path for path in scenery_image_resources(build_dir) if path.startswith("eloria-assets/"))
    package_dirs = {str(PurePosixPath(p).parent) for p in all_tracked
                    if p.startswith("eloria-assets/maps/") and p.endswith("/world.json")}
    for path in all_tracked:
        for package in package_dirs:
            if path.startswith(package + "/"):
                if is_shipped_map_file(PurePosixPath(path).relative_to(package)):
                    wanted.add(path)
                break

    # Literal references from the client: registry, cartography, scripts.
    errors: list[str] = []
    warnings: list[str] = []
    client_sources = tracked(build_dir, "godot-client/data", "godot-client/src")
    for relative in client_sources:
        if not relative.endswith((".json", ".gd")):
            continue
        text = (build_dir / relative).read_text(encoding="utf-8", errors="replace")
        for match in ASSET_REF.finditer(text):
            target = match.group(1).rstrip("/")
            if MAP_LOD_PACKAGE.match(PurePosixPath(target).name):
                continue
            if target in all_tracked:
                wanted.add(target)
            elif not any(p.startswith(target + "/") for p in all_tracked):
                (errors if relative.endswith(".json") else warnings).append(
                    f"{relative} names {target}, which is not in the commit")

    # Files a shipped manifest names, relative to the manifest. Follow the
    # closure, since a pulled-in JSON can name more files.
    queue = sorted(p for p in wanted if p.endswith(".json"))
    seen: set[str] = set()
    pooled: set[str] = set()
    while queue:
        manifest = queue.pop()
        if manifest in seen:
            continue
        seen.add(manifest)
        try:
            data = json.loads((build_dir / manifest).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        base = PurePosixPath(manifest).parent
        is_world = manifest.endswith("/world.json")
        if is_world and isinstance(data, dict) and "roadGround" in data:
            try:
                closure = road_dependencies(build_dir, build_dir / manifest, data["roadGround"])
                for dependency in closure:
                    target = dependency.relative_to(build_dir.resolve()).as_posix()
                    if target not in all_tracked:
                        errors.append(f"{manifest} roadGround -> {target} is not in the commit")
                    elif target not in wanted:
                        wanted.add(target)
                        if target.endswith(".json"):
                            queue.append(target)
            except RoadGroundDependencyError as exc:
                errors.append(f"{manifest} roadGround: {exc}")
        # A served continent-v2 package's collision block names what only the server reads, and its territory
        # manifest streams chunks and has no master GLB: asset.glb names none the client opens (its map digest is
        # empty without one, map_scene_cache.package_digest).
        served_manifest = any(_under(manifest, folder) for folder in served_folders)
        skipped = MANIFEST_SKIPPED_KEYS | {"collision"} if served_manifest else MANIFEST_SKIPPED_KEYS
        chunk_streamed = served_manifest and isinstance(data, dict) and "streamingChunks" in data
        for key, value in json_strings(data, skipped):
            match = ASSET_REF.search(value)
            if match:
                target = match.group(1)
            elif FILE_LIKE.match(value) and not value.startswith(("res://", "user://", "/")):
                target = os.path.normpath(str(base / value)).replace("\\", "/")
            else:
                continue
            if MAP_LOD_PACKAGE.match(PurePosixPath(target).name):
                continue
            if target in all_tracked:
                if target not in wanted:
                    wanted.add(target)
                    if target.endswith(".json"):
                        queue.append(target)
            elif chunk_streamed and key == "glb":
                continue
            elif is_world and key in {"glb", "binary", "image", "file"}:
                errors.append(f"{manifest} {key} -> {target} is not in the commit")
            elif is_world:
                warnings.append(f"{manifest} {key} -> {target} not found")
        # externalResources names its files as keys (URI -> sha256), relative
        # to the GLB, so the value walk above never sees them: the continent's
        # shared images (_continent/shared-assets, in no package folder of
        # their own) were left out, and the client refuses a chunk whose
        # external images are missing (WorldManifest.verify_external_resources).
        resources = data.get("externalResources") if is_world and isinstance(data, dict) else None
        if isinstance(resources, dict):
            glb_dir = base / PurePosixPath(str(data.get("asset", {}).get("glb", "world.glb"))).parent
            for uri in resources:
                target = os.path.normpath(str(glb_dir / str(uri))).replace("\\", "/")
                if target in all_tracked:
                    wanted.add(target)
                else:
                    errors.append(f"{manifest} externalResources -> {target} is not in the commit")
        # externalMeshes names its prototypes as keys as well (URI -> sha256),
        # relative to the manifest's own folder, so the value walk misses them
        # too - and the pool they live in (maps/_shared/meshes) holds no
        # world.json, so no package folder carries it: without this a map that
        # names prototypes would ship none of them and every placement that
        # draws one would draw nothing. Only what a shipped manifest names is
        # staged: the pool is shared by every package, so copying it whole
        # would carry the preview maps' prototypes too.
        prototypes = data.get(SHARED_MESH_KEY) if isinstance(data, dict) else None
        if isinstance(prototypes, dict):
            for uri in prototypes:
                target = os.path.normpath(str(base / str(uri))).replace("\\", "/")
                # A prototype is named by hundreds of manifests; cost it once.
                if target in pooled:
                    continue
                pooled.add(target)
                if target not in all_tracked:
                    errors.append(f"{manifest} {SHARED_MESH_KEY} -> {target} is not in the commit")
                    continue
                wanted.add(target)
                pool_index = str(PurePosixPath(target).parent / SHARED_MESH_INDEX)
                if pool_index in all_tracked:
                    wanted.add(pool_index)
                else:
                    errors.append(f"{manifest} {SHARED_MESH_KEY} -> {pool_index} is not in the commit")
                # A prototype keeps the image URIs its package had, rewritten
                # relative to the pool: those images are the content-addressed
                # shared ones the packages name as well, so this adds nothing
                # in practice and is the safety net for a prototype whose last
                # naming package is a preview.
                for image in gltf_image_uris(build_dir / target):
                    named = os.path.normpath(str(PurePosixPath(target).parent / image)).replace("\\", "/")
                    if named in all_tracked:
                        wanted.add(named)
                    else:
                        warnings.append(f"{target} names {image}, which the package does not ship")

    return wanted, errors, warnings


def stage_eloria_assets(build_dir: Path, stage: Path, excluded: list[str] = (),
                        served: list[tuple[str, str]] = ()) -> list[str]:
    """Copy map packages and every eloria-assets file the client names, none under an `excluded` map folder, and
    of a `served` continent-v2 map (served_v2_packages) only its client package, without SERVER_ONLY_FILES
    (shipped_eloria_assets).

    Returns warnings; raises when a reference the client will open is missing.
    """
    wanted, errors, warnings = shipped_eloria_assets(build_dir, excluded, served)
    if errors:
        raise PackageError("missing map files:\n  " + "\n  ".join(errors[:40]))
    total = sum(copy_file(build_dir / p, stage / p) for p in sorted(wanted))
    # Verify the bytes that will ship as well as the source selection. Road
    # style images can live outside the chunk's folder and their URI keys are
    # not covered by the generic JSON value walk.
    for relative in sorted(p for p in wanted if p.endswith("/world.json")):
        path = stage / relative
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and "roadGround" in data:
            try:
                road_dependencies(stage, path, data["roadGround"])
            except RoadGroundDependencyError as exc:
                raise PackageError(f"staged {relative} roadGround: {exc}") from exc
    package_dirs = {str(PurePosixPath(p).parent) for p in tracked(build_dir, "eloria-assets/maps")
                    if p.endswith("/world.json") and _ships_asset(p, excluded, served)}
    log(f"staged {len(wanted)} eloria-assets files from {len(package_dirs)} map packages "
        f"({total / 1e9:.2f} GB)")
    return warnings


def check_glb_textures(app_dir: Path) -> None:
    """Every image a shipped glTF names by URI is loose beside it or imported in the PCK.

    GLTFDocument asks ResourceLoader for the image at the glTF's relative
    path first (res:// in an export, so the PCK's import), then reads the
    file there.
    """
    pck = app_dir / "RabbitLands.pck"
    packed = pck_paths(pck) if pck.is_file() else set()
    missing: list[str] = []
    count = imported = 0
    for gltf in sorted((*(app_dir / "assets").rglob("*.glb"), *(app_dir / "assets").rglob("*.gltf"))):
        for uri in gltf_image_uris(gltf):
            count += 1
            target = gltf.parent / uri
            local = posixpath.normpath(target.relative_to(app_dir).as_posix())
            if local + ".import" in packed:
                imported += 1
            elif not target.is_file():
                missing.append(f"{gltf.relative_to(app_dir).as_posix()} -> {uri}")
    if missing:
        raise PackageError(f"{len(missing)} glTF textures missing:\n  " + "\n  ".join(missing[:40]))
    log(f"checked {count} external glTF textures: {imported} imported in the PCK, "
        f"{count - imported} loose")


def check_served_packages(stage: Path, served: list[tuple[str, str]]) -> None:
    """Each served continent-v2 map (served_v2_packages) ships its client package and nothing only the server reads:
    its territory manifest and every chunk its streamingChunks lists are staged; no SERVER_ONLY_FILES and nothing of
    the territory folder outside the package is; and no staged chunk manifest names a collision binary or a served
    grid (publish_client.py keeps them out of the chunks; a chunk naming one would mean an unchecked package)."""
    problems: list[str] = []
    for package, territory in served:
        root = stage / package
        manifest_path = root / "world.json"
        if not manifest_path.is_file():
            problems.append(f"{package}/world.json is not staged")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        chunks = (manifest.get("streamingChunks") or {}).get("chunks") or []
        for chunk in chunks:
            chunk_path = root / str(chunk.get("manifest", ""))
            if not chunk_path.is_file():
                problems.append(f"{package}: chunk {chunk.get('id')} ({chunk.get('manifest')}) is not staged")
                continue
            collision = json.loads(chunk_path.read_text(encoding="utf-8-sig")).get("collision") or {}
            if "binary" in collision or "servedGrid" in collision:
                problems.append(f"{chunk_path.relative_to(stage).as_posix()} names a collision binary")
        if (stage / territory).is_dir():
            for path in (stage / territory).rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(stage).as_posix()
                if path.name in SERVER_ONLY_FILES:
                    problems.append(f"{relative} is read by the server only, and is staged")
                elif not _under(relative, package):
                    problems.append(f"{relative} lies outside the client package {package}, and is staged")
    if problems:
        raise PackageError(f"{len(problems)} served continent-v2 package problems:\n  " + "\n  ".join(problems[:40]))
    if served:
        log(f"checked {len(served)} served continent-v2 packages: {', '.join(p for p, _ in served)}")


def _gltf_json_bytes(path: Path) -> bytes:
    """A .gltf's bytes, or a .glb's JSON chunk (b"" for a file that is not glTF)."""
    if path.suffix.lower() != ".glb":
        return path.read_bytes()
    with open(path, "rb") as handle:
        header = handle.read(20)
        if len(header) < 20 or header[:4] != b"glTF":
            return b""
        return handle.read(struct.unpack("<I", header[12:16])[0])


def check_map_data_names_no_editor_sources(stage: Path) -> None:
    """No staged map file names a file of the map editor's sources (EDITOR_ONLY_PCK_DIRS) by res:// path.

    The game loads what the map data names by res:// path from the PCK (the
    biome-blend records' "albedoTexture", BiomeBlendMaterial._apply_palette, is
    a terrain base material's texture path as the editor published it), and the
    PCK leaves the editor's sources out: such a path would fail to load in the
    package while every check of the import and the PCK passed. The legacy maps'
    provenance files (EDITOR_SOURCE_PROVENANCE) are the exception; no file the
    game reaches opens them. JSON and .gltf files are read whole, a .glb's JSON
    chunk only.
    """
    needles = [b"res://" + folder.encode("utf-8") for folder in EDITOR_ONLY_PCK_DIRS]
    problems: list[str] = []
    provenance = scanned = 0
    for path in sorted((stage / "eloria-assets").rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".json", ".gltf", ".glb"):
            continue
        relative = path.relative_to(stage).as_posix()
        data = path.read_bytes() if path.suffix.lower() == ".json" else _gltf_json_bytes(path)
        scanned += 1
        if not any(needle in data for needle in needles):
            continue
        if EDITOR_SOURCE_PROVENANCE.search(relative):
            provenance += 1
            continue
        first = min(data.find(needle) for needle in needles if needle in data)
        named = data[first:first + 160].split(b'"')[0].decode("utf-8", "replace")
        problems.append(f"{relative} names {named}")
    if problems:
        raise PackageError(f"{len(problems)} staged map files name the map editor's sources, which the package "
                           "leaves out:\n  " + "\n  ".join(problems[:40]))
    log(f"checked {scanned} staged map files: none names {', '.join(EDITOR_ONLY_PCK_DIRS)} "
        f"({provenance} provenance files aside)")


def check_registry(build_dir: Path, stage: Path) -> None:
    registry = json.loads((build_dir / "godot-client/data/maps/registry.json").read_text(encoding="utf-8"))
    missing = []
    for map_id, entry in registry.get("maps", {}).items():
        match = ASSET_REF.search(str(entry.get("manifest", "")))
        if match and not (stage / match.group(1)).is_file():
            missing.append(f"{map_id}: {match.group(1)}")
    if missing:
        raise PackageError("registry manifests missing from package:\n  " + "\n  ".join(missing))
    log(f"checked {len(registry.get('maps', {}))} registry maps")


def check_map_backgrounds(build_dir: Path, stage: Path | None = None) -> None:
    """Every registry map/section has a current image, and those pixels ship.

    Source validation happens before preview pruning or storage retirement.
    Staged validation checks the registry still selected for this package and
    reads actual loose pixels, not the PCK's catalog references alone.
    """
    try:
        errors = (map_background_package.validate_catalog(build_dir) if stage is None
                  else map_background_package.staged_image_errors(build_dir, stage))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PackageError(f"Cannot validate prerendered map backgrounds: {error}") from error
    if errors:
        raise PackageError("prerendered map backgrounds are incomplete or stale:\n  " + "\n  ".join(errors[:40]))
    log("checked " + ("current source coverage for all prerendered maps/sections" if stage is None
                       else "all prerendered map/section images in staged loose assets"))


def check_map_background_export(build_dir: Path, app_dir: Path) -> None:
    inside = "data/maps/map-backgrounds.json"
    source = build_dir / map_background_package.CATALOG
    loose = app_dir / inside
    if inside not in pck_paths(app_dir / "RabbitLands.pck"):
        raise PackageError("Prerendered map background catalog is missing from the PCK")
    if not loose.is_file() or source.read_bytes() != loose.read_bytes():
        raise PackageError("Prerendered map background catalog differs in staged client data")
    log("checked the prerendered map catalog in the PCK and loose client data")


def check_shared_meshes(build_dir: Path, stage: Path) -> None:
    """Every prototype mesh a staged manifest names is in the package, and is the file the manifest was written
    against.

    A placement whose prototype did not ship, or whose prototype is a
    different build of the same prop, draws nothing while every other check
    passes: the node keeps its name and transform, so collision, navigation
    and the look pass are all satisfied and only the geometry is gone. The
    manifests are found by scanning the staged map JSON for the key instead of
    walking the registry, so a chunk manifest is checked exactly like the
    territory manifest above it. Checked with them: the pool's index.json
    ships beside its prototypes (external_mesh_pool.gd reads a prototype's
    images from it), the index describes what shipped, and the package carries
    no prototype no staged manifest names - the pool is shared by every
    package, and the preview maps' prototypes are in it too. `build_dir` is
    the commit's own pool, for how much of it the package left behind.
    """
    problems: list[str] = []
    digests: dict[Path, str] = {}
    pools: set[Path] = set()
    references = 0
    for manifest_path in sorted((stage / "eloria-assets").rglob("*.json")):
        try:
            raw = manifest_path.read_bytes()
        except OSError:
            continue
        # Most staged JSON names no prototype: the substring is what keeps
        # this off the thousands of chunk manifests' parse path.
        if SHARED_MESH_KEY.encode("utf-8") not in raw:
            continue
        try:
            manifest = json.loads(raw.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            continue
        prototypes = manifest.get(SHARED_MESH_KEY) if isinstance(manifest, dict) else None
        if not isinstance(prototypes, dict):
            continue
        named = manifest_path.relative_to(stage).as_posix()
        for uri, sha in prototypes.items():
            references += 1
            path = Path(os.path.normpath(manifest_path.parent / str(uri)))
            try:
                path.relative_to(stage)
            except ValueError:
                problems.append(f"{named}: prototype {uri} resolves outside the package")
                continue
            pools.add(path.parent)
            if not path.is_file():
                problems.append(f"{named}: prototype {uri} is not in the package")
                continue
            if path not in digests:
                digests[path] = hashlib.sha256(path.read_bytes()).hexdigest()
            if digests[path] != sha:
                problems.append(f"{path.relative_to(stage).as_posix()}: sha256 differs from the one "
                                f"{named} names")
    published = 0
    for pool in sorted(pools):
        relative = pool.relative_to(stage).as_posix()
        index_path = pool / SHARED_MESH_INDEX
        if not index_path.is_file():
            problems.append(f"{relative}/{SHARED_MESH_INDEX} is not in the package")
            continue
        try:
            index = json.loads(index_path.read_text(encoding="utf-8")).get("prototypes", {})
        except (OSError, ValueError):
            problems.append(f"{relative}/{SHARED_MESH_INDEX} cannot be read")
            continue
        # The index is keyed on a prototype's identity, which is its file name:
        # shared_meshes.py hashes a mesh's geometry and appearance for the
        # identity and the written file's bytes for "sha256", and they differ.
        for path, digest in digests.items():
            if path.parent != pool:
                continue
            entry = index.get(path.stem)
            if not isinstance(entry, dict):
                problems.append(f"{relative}/{SHARED_MESH_INDEX} does not list {path.name}")
            elif entry.get("sha256") != digest:
                problems.append(f"{relative}/{SHARED_MESH_INDEX}: sha256 of {path.name} differs from the file")
        for path in sorted(pool.glob("*.glb")):
            if path not in digests:
                problems.append(f"{path.relative_to(stage).as_posix()}: in the package, and no staged "
                                "manifest names it")
        commit_index = build_dir / relative / SHARED_MESH_INDEX
        if commit_index.is_file():
            try:
                published += len(json.loads(commit_index.read_text(encoding="utf-8")).get("prototypes", {}))
            except (OSError, ValueError):
                pass
    if problems:
        raise PackageError(f"{len(problems)} shared prototype mesh problems:\n  " + "\n  ".join(problems[:40]))
    if references:
        log(f"checked {references} shared mesh references: {len(digests)} prototypes staged of "
            f"{published} published, with their index")
    else:
        log("checked shared mesh references: no staged manifest names a prototype")


# The reporting scan of what map geometry is still copied between files. Only
# shared_meshes.py --apply removes it, so this never fails a build and never
# costs one: a primitive smaller than this is not worth a prototype file of its
# own (shared_meshes.py MIN_BYTES) and hashing the long tail of them is most of
# the work, and a scan that runs out of its budget reports the sample it got.
DUPLICATE_SCAN_MIN_BYTES = 4096
DUPLICATE_SCAN_SECONDS = 30.0
# glTF component and element widths, for the bytes an accessor occupies.
ACCESSOR_WIDTHS = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
ACCESSOR_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def _primitive_digests(path: Path) -> dict[bytes, int]:
    """digest -> byte length of each primitive's accessor data in a map GLB, the small ones left out.

    Hashes the bytes a primitive's attributes, indices and morph targets
    occupy and nothing else. Two bakes of the same prop differ in the mesh's
    name and in the nodes that place it, never in those bytes, so this finds
    the copies; what may actually share one prototype is shared_meshes.py's
    call (mesh_identity hashes a mesh's appearance as well), which is why this
    only reports a size and never acts on it.
    """
    out: dict[bytes, int] = {}
    try:
        data = path.read_bytes()
        if len(data) < 20 or data[:4] != b"glTF":
            return out
        json_length = struct.unpack("<I", data[12:16])[0]
        document = json.loads(data[20:20 + json_length].rstrip(b"\0 ").decode("utf-8"))
        binary = b""
        offset = 20 + json_length
        if offset + 8 <= len(data):
            binary = data[offset + 8:offset + 8 + struct.unpack("<I", data[offset:offset + 4])[0]]
        accessors = document.get("accessors", [])
        views = document.get("bufferViews", [])

        def accessor_bytes(index) -> bytes:
            accessor = accessors[index]
            if "bufferView" not in accessor:
                return b""
            view = views[accessor["bufferView"]]
            element = ACCESSOR_WIDTHS[accessor["componentType"]] * ACCESSOR_COUNTS[accessor["type"]]
            stride = view.get("byteStride", element)
            start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            count = accessor["count"]
            return binary[start:start + (stride * (count - 1) + element if count else 0)]

        for mesh in document.get("meshes", []):
            for primitive in mesh.get("primitives", []):
                digest = hashlib.sha256()
                size = 0
                indexed = [primitive["attributes"][semantic] for semantic in sorted(primitive["attributes"])]
                if "indices" in primitive:
                    indexed.append(primitive["indices"])
                indexed += [target[semantic] for target in primitive.get("targets", [])
                            for semantic in sorted(target)]
                for index in indexed:
                    chunk = accessor_bytes(index)
                    size += len(chunk)
                    digest.update(chunk)
                if size >= DUPLICATE_SCAN_MIN_BYTES:
                    out[digest.digest()] = size
    except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error):
        return out
    return out


def report_duplicate_geometry(stage: Path, budget: float = DUPLICATE_SCAN_SECONDS) -> dict:
    """Log how much of the staged map geometry is byte-identical to another staged file's. Fails nothing.

    glTF shares a mesh between the nodes of one file but has no way to reach
    another file's, so a kit prop baked into a hundred chunks ships a hundred
    times; eloria-assets/tools/shared_meshes.py --apply is what turns those
    into one prototype the manifests name. This line is how a build says what
    is left to win - and what a future bake has quietly reintroduced.
    """
    # A scan cut short by the budget must still span every package, so the
    # order is spread by the digest of the path rather than alphabetical:
    # stopping then samples the whole tree instead of the first maps.
    try:
        order = sorted((p for p in (stage / "eloria-assets").rglob("*.glb") if p.is_file()),
                       key=lambda p: hashlib.sha256(p.as_posix().encode("utf-8")).digest())
    except OSError:
        # A report must never be what fails a package that is already built.
        order = []
    if not order:
        return {"bytes": 0, "files": 0, "scanned": 0, "total": 0}
    sizes: dict[bytes, int] = {}
    holder: dict[bytes, Path] = {}
    copied: set[Path] = set()
    duplicate = scanned = 0
    deadline = time.time() + budget
    for path in order:
        for digest, size in _primitive_digests(path).items():
            if digest not in sizes:
                sizes[digest] = size
                holder[digest] = path
                continue
            # The file that held this geometry first is a copy only once a
            # second one turns up, so it is held until then and then let go:
            # one path per digest rather than the set of every file.
            held = holder.pop(digest, None)
            if held is not None:
                copied.add(held)
            copied.add(path)
            duplicate += size
        scanned += 1
        if time.time() > deadline:
            break
    sampled = ("" if scanned == len(order)
               else f", sampled {scanned} of {len(order)} files ({budget:.0f} s budget)")
    log(f"duplicate map geometry: {duplicate / 1e6:.0f} MB across {len(copied)} files{sampled} "
        "(shared_meshes.py --apply removes it)")
    return {"bytes": duplicate, "files": len(copied), "scanned": scanned, "total": len(order)}


VRAM_SELF_TEST_OK = "vram_textures self_test ok"
VRAM_SELF_TEST_POOL_OK = "vram_textures self_test pool ok"
# Maps whose images in the skipped shared pool maps/_shared/images still ship sidecars (build_vram_textures.py
# --unskip-map): Landfall Town's room shells, one whole-map interior whose 27 decoded images held about 90 MiB of
# GPU memory (BC7: about 22 MiB; about 18 MB of sidecars to download).
UNSKIPPED_SHARED_IMAGE_MAPS = ("continent-v2/landfall_town",)
# Scenery configs whose GLBs' embedded images ship sidecars, loose beside the GLBs (app/assets/world/<dir>/vram;
# world_object_images.gd reads them): the town's scenery held about 270 MiB decoded, about 65 MiB as sidecars
# (about 45 MB to download). Measured 2026-10-27 with the town's scratch town_vram.gd.
SCENERY_SIDECAR_CONFIGS = ("godot-client/data/world/town-scenery.json",)


def stage_vram_textures(build_dir: Path, stage: Path, godot: Path, cache: Path, logs: Path,
                        tool: Path | None = None, app_dir: Path | None = None) -> dict:
    """Build the VRAM-compressed sidecars of the shared map images into the stage.

    The sidecars are not tracked (eloria-assets/maps/**/shared-assets/vram/ is
    ignored), so stage_eloria_assets never copies them: they are made here, by
    the commit's own tools/build_vram_textures.py, from the build worktree's
    images, straight into <stage>/eloria-assets/maps/.../vram, with a
    persistent encode cache outside every repository. Only index.json and the
    .evt files ship; the quality report goes to the logs.
    """
    tool = tool or build_dir / "godot-client" / "tools" / "build_vram_textures.py"
    log("building VRAM texture sidecars")
    cache.mkdir(parents=True, exist_ok=True)
    runner_args = []
    if STORAGE:
        remaining = (STORAGE.budget.capacity - STORAGE.budget.reserve
                     - release_storage.unique_bytes(STORAGE.budget.roots) - 64 * 1024**2)
        # The retained cache is already counted in the working set. The child
        # measures its whole cache, so add those existing bytes to its ceiling.
        ceiling = remaining + release_storage.unique_bytes([cache])
        runner_args = ["--link-output", "--cache-budget-bytes", str(ceiling)]
    started = time.time()
    with open(logs / "vram-textures.log", "w", encoding="utf-8", errors="replace") as handle:
        # maps/_shared/images holds the textures shared_images.py moved out of
        # the GLBs that embedded them. Embedded, the client always decoded
        # them, and externalising alone already shares them across maps in
        # ExternalTexturePool; sidecars for the whole pool would add 490 MB to
        # the download for a win those maps never had. The pools that were
        # sidecar-backed before stay sidecar-backed.
        # The stage is the proved shipping closure. Runner source-only map
        # inputs have retired by now, and must not add unshipped encode work.
        maps = (stage if STORAGE else build_dir) / "eloria-assets/maps"
        # A few maps' images in that pool are worth their download (UNSKIPPED_SHARED_IMAGE_MAPS), and the
        # scenery of SCENERY_SIDECAR_CONFIGS gets sidecars beside its loose GLBs in app/ (once app/ exists).
        unskip = [arg for name in UNSKIPPED_SHARED_IMAGE_MAPS for arg in ("--unskip-map", name)]
        scenery = []
        if app_dir is not None:
            for config in SCENERY_SIDECAR_CONFIGS:
                if (build_dir / config).is_file():
                    scenery += ["--scenery-config", str(build_dir / config)]
            if scenery:
                scenery += ["--scenery-out-root", str(app_dir / "assets" / "world")]
        result = subprocess.run([sys.executable, str(tool), "--maps", str(maps),
                                 "--out-root", str(stage / "eloria-assets" / "maps"), "--cache", str(cache),
                                 "--godot", str(godot), "--skip-dir", "_shared/images", *unskip, *scenery,
                                 *runner_args],
                                stdout=handle, stderr=subprocess.STDOUT, timeout=3600,
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    text = (logs / "vram-textures.log").read_text(encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise PackageError(f"build_vram_textures.py failed; log: {logs / 'vram-textures.log'}\n{text[-2000:]}")
    files = 0
    size = 0
    for report in (stage / "eloria-assets").rglob("vram/report.json"):
        # Named after the pool's path: more than one pool is called shared-assets.
        pool = report.parent.parent.relative_to(stage / "eloria-assets")
        target = logs / ("vram-report-" + "__".join(pool.parts) + ".json")
        shutil.move(str(report), target)
    scenery_files = scenery_bytes = 0
    if app_dir is not None and (app_dir / "assets").is_dir():
        for report in (app_dir / "assets").rglob("vram/report.json"):
            folder = report.parent.parent.relative_to(app_dir)
            shutil.move(str(report), logs / ("vram-report-app__" + "__".join(folder.parts) + ".json"))
        for path in (app_dir / "assets").rglob("vram/*"):
            if path.is_file():
                scenery_files += 1
                scenery_bytes += path.stat().st_size
        if scenery_files:
            log(f"staged {scenery_files} scenery sidecar files ({scenery_bytes / 1e6:.0f} MB) beside their GLBs in app/")
    shared = {"files": 0, "bytes": 0, "directories": []}
    if client_reads_pooled_sidecars(build_dir):
        shared = share_identical_sidecars(stage)
    else:
        log("the packaged client does not read pooled sidecars (INDEX_FEATURES): every pool ships its own")
    if shared["files"]:
        log(f"shipped {shared['files']} sidecar files once that two pools hold ({shared['bytes'] / 1e6:.0f} MB)")
    for path in (stage / "eloria-assets").rglob("vram/*"):
        if path.is_file():
            files += 1
            size += path.stat().st_size
    log(f"staged {files} VRAM sidecar files ({size / 1e6:.0f} MB, already zstd: the zip grows by about "
        f"as much) in {time.time() - started:.0f} s")
    return {"files": files, "bytes": size, "sceneryFiles": scenery_files, "sceneryBytes": scenery_bytes}


def check_loose_vram_textures(app_dir: Path) -> None:
    """Every sidecar index in app/assets - the scenery's (world_object_images.gd reads them) and the actors'
    (actor_images.gd, AT-C3) - names files that are staged beside it, byte for byte, by plain file names, nothing
    else sits in its vram/ folder, and no vram/ folder lacks its index (a broken one only costs a decode)."""
    import hashlib
    problems: list[str] = []
    sidecars = 0
    assets = app_dir / "assets"
    for folder in sorted(assets.rglob(vram_tool.SIDECAR_DIR)) if assets.is_dir() else []:
        if folder.is_dir() and not (folder / "index.json").is_file():
            problems.append(f"{folder.relative_to(app_dir).as_posix()}: a sidecar folder without its index.json")
    for index_path in sorted(assets.rglob("vram/index.json")) if assets.is_dir() else []:
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index, dict) or not isinstance(index.get("images", {}), dict):
                raise ValueError("not an index object")
        except (OSError, ValueError) as error:
            problems.append(f"{index_path.relative_to(app_dir).as_posix()}: unreadable sidecar index: {error}")
            continue
        listed = set()
        for entry in index.get("images", {}).values():
            name = entry.get("file") if isinstance(entry, dict) else None
            if (not isinstance(name, str) or name in ("", ".", "..", "index.json")
                    or "/" in name or "\\" in name or ":" in name):
                problems.append(f"{index_path.relative_to(app_dir).as_posix()}: names an unsafe sidecar file {name!r}")
                continue
            path = index_path.parent / name
            listed.add(name)
            if not path.is_file():
                problems.append(f"{path.relative_to(app_dir)}: listed in the index but missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
                # A missing or wrong sha256 is a build problem, not a KeyError traceback.
                problems.append(f"{path.relative_to(app_dir)}: sha256 differs from the index")
            else:
                sidecars += 1
        for path in index_path.parent.iterdir():
            if path.name != "index.json" and path.name not in listed:
                problems.append(f"{path.relative_to(app_dir)}: not named by the index")
    # Only the configured scenery previously received sidecars. Converted
    # embedded images retain that coverage; original URI uses retain fallback.
    for name in SCENERY_SIDECAR_CONFIGS:
        config = app_dir / PurePosixPath(name).relative_to("godot-client")
        if not config.is_file():
            continue
        try:
            assets = json.loads(config.read_text(encoding="utf-8")).get("assets", {})
            for uri in set(assets.values()):
                if not isinstance(uri, str) or not uri.startswith("res://assets/world/"):
                    continue
                source = app_dir / uri.removeprefix("res://")
                document = gltf_document(source)
                if "rabbitlands_scenery_images" not in (document.get("extras") or {}):
                    continue
                from scenery_image_sources import validate
                closure = validate(app_dir.parent, source, document, client_directory="app")
                index_path = source.parent / "vram/index.json"
                index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
                for image in closure["images"]:
                    if image["sidecar_eligible"] and image["sha256"] not in index.get("images", {}) \
                            and image["sha256"] not in index.get("excluded", {}):
                        problems.append(f"{source.relative_to(app_dir)}: converted image has no original-directory sidecar/exclusion")
        except (OSError, ValueError, TypeError) as error:
            problems.append(f"{config.relative_to(app_dir)}: invalid scenery image sidecar closure: {error}")
    if problems:
        raise PackageError(f"{len(problems)} loose sidecar problems:\n  " + "\n  ".join(problems[:40]))
    log(f"checked {sidecars} loose sidecars in app/assets")


# The name before AT-C3 added the actor sidecars it also checks.
check_scenery_vram_textures = check_loose_vram_textures


# --- actor VRAM sidecars (wave-2 actor textures, AT-C3) ----------------------------------------------------------

# The folders below godot-client/assets/actors/native whose GLBs' embedded images ship VRAM sidecars, loose beside
# the GLBs in app/assets/actors/native/<folder>/.../vram (build_vram_textures.py --actor-dir; read by
# src/actors/actor_images.gd). Phasing them is the owner's download decision (actor-textures open question 1).
# Sidecar bytes measured on the wave-2 tree at the map floors (AT-C1): creatures 455.4 MB, equipment (held props)
# 134.9 MB, races 40.8 MB, mounts 1.0 MB, hair 0.7 MB; without "creatures" (the plan's phase A) +177.4 MB instead of
# +632.8 MB. rl_heads is never one of them (strip_rl_head_images.py removes its embedded copies instead).
ACTOR_SIDECAR_DIRS = ("creatures", "races", "hair", "mounts", "equipment")
# Quality floors of the actor run only (build_vram_textures.py --floors); None keeps the map floors. The plan's
# relaxed actor normal floors await the owner (open question 2; AT-C1: 678 of 697 images get sidecars at the map
# floors, 691 with {"normal_mean_deg": 1.5, "normal_p99_deg": 8.0, "normal_mean_deg_mips": 2.0,
# "normal_p99_deg_mips": 10.0}, +13.4 MB).
ACTOR_SIDECAR_FLOORS: dict | None = None
# The release switch (wave-2 schedule 1.1 #20). The packaging lands before its consumers are ready: with a BC7 race
# atlas the wardrobe dye readback needs AT-C4's SHA-keyed cache (stage C) or the template's BCn decompressor, which
# the smoke self-test below proves. While False, actor sidecars are built only for a local package that asks for
# them (--actor-vram-textures), never for a --release-build or a runner build. True makes them the default of every
# package that ships VRAM sidecars, and --no-actor-vram-textures opts out.
ACTOR_SIDECARS_RELEASE_ENABLED = False
# The client's smoke line (actor_images.gd, AT-C2) when ELORIA_ACTOR_VRAM_SELF_TEST names a folder: it decoded that
# folder's index and a sidecar, and Image.decompress() of a copy worked in the shipped template.
ACTOR_VRAM_SELF_TEST_VARIABLE = "ELORIA_ACTOR_VRAM_SELF_TEST"
ACTOR_VRAM_SELF_TEST_OK = "actor_images self_test ok"
ACTOR_VRAM_SELF_TEST_LINE = re.compile(r"actor_images self_test ok entries=([1-9][0-9]*) format=(\S+) "
                                       r"mips=([1-9][0-9]*) decompress=ok(?=\s|$)")
# The folder the smoke launch self-tests: races first (its BC7 atlases are what the wardrobe reads back).
ACTOR_VRAM_SELF_TEST_PREFERENCE = ("races",)
ACTOR_VRAM_SELF_TEST_PATH = re.compile(r"^assets/actors/native/[A-Za-z0-9_][A-Za-z0-9_./-]*$")
# What the commit being packaged must have: the client reader with its self-test, and the builder's actor mode.
ACTOR_VRAM_READER = "godot-client/src/actors/actor_images.gd"
ACTOR_VRAM_TOOL = "godot-client/tools/build_vram_textures.py"
ACTOR_VRAM_TOOL_FEATURE = '"--actor-dir"'
# Runner disk allowance before the actor encode (bytes): a cold cache adds about 0.63 GB of encodes (hard-linked into
# the stage), about 0.13 GB of extracted images and bounded quality scratch; a warm runner cache adds little.
ACTOR_ENCODE_ALLOWANCE = 1024**3
ACTOR_ENCODE_ALLOWANCE_WARM = 256 * 1024**2
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def actor_sidecar_support(build_dir: Path) -> str:
    """"" when the commit being packaged can build and read actor sidecars, else what it lacks."""
    reader = build_dir / ACTOR_VRAM_READER
    if not reader.is_file() or ACTOR_VRAM_SELF_TEST_OK not in reader.read_text(encoding="utf-8", errors="replace"):
        return "has no actor sidecar reader with its smoke self-test (src/actors/actor_images.gd, AT-C2)"
    tool = build_dir / ACTOR_VRAM_TOOL
    if not tool.is_file() or ACTOR_VRAM_TOOL_FEATURE not in tool.read_text(encoding="utf-8", errors="replace"):
        return "has no actor mode in tools/build_vram_textures.py (AT-C1)"
    return ""


def actor_sidecar_dirs(build_dir: Path, requested: bool | None, *, no_vram: bool, release_build: bool,
                       runner: bool) -> tuple[str, ...]:
    """The actor folders this package builds sidecars for; () for none.

    requested is --actor-vram-textures (True), --no-actor-vram-textures (False) or neither (None: the release
    switch's default). An explicit request that cannot be honoured fails the build before the import."""
    if any(name in vram_tool.ACTOR_NEVER_PLANNED or not name or "/" in name or "\\" in name
           for name in ACTOR_SIDECAR_DIRS):
        raise PackageError(f"ACTOR_SIDECAR_DIRS names a folder that is never planned: {ACTOR_SIDECAR_DIRS}")
    wanted = ACTOR_SIDECARS_RELEASE_ENABLED if requested is None else requested
    if not wanted:
        return ()
    if no_vram:
        if requested:
            raise PackageError("--actor-vram-textures needs the VRAM sidecars, which this package leaves out "
                               "(--no-vram-textures, or macOS)")
        return ()
    if not ACTOR_SIDECARS_RELEASE_ENABLED and (release_build or runner):
        raise PackageError("actor VRAM sidecars are not release-enabled yet (wave-2 schedule 1.1 #20: AT-C4 and the "
                           "smoke self-test first); build them in a local package only")
    missing = actor_sidecar_support(build_dir)
    if missing:
        if requested:
            raise PackageError(f"--actor-vram-textures: the commit being packaged {missing}")
        log(f"no actor VRAM sidecars: the commit being packaged {missing}")
        return ()
    return ACTOR_SIDECAR_DIRS


def _tool_summary(text: str) -> dict:
    """The summary object build_vram_textures.py prints last (json.dumps(..., indent=1) after its log lines)."""
    start = text.rfind("\n{\n")
    start = start + 1 if start >= 0 else (0 if text.startswith("{\n") else -1)
    try:
        summary = json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        summary = None
    if not isinstance(summary, dict):
        raise PackageError("build_vram_textures.py printed no summary")
    return summary


def actor_self_test_directory(app_dir: Path, dirs: tuple[str, ...]) -> str | None:
    """The app-relative folder (assets/actors/native/...) the smoke launch self-tests: the first folder of a preferred
    family, then of the others in order (in each, the shallowest first), whose staged index lists a sidecar; None
    when none does."""
    native = app_dir / "assets" / "actors" / "native"
    order = [name for name in ACTOR_VRAM_SELF_TEST_PREFERENCE if name in dirs]
    order += [name for name in dirs if name not in order]
    for name in order:
        found = (native / name).rglob("vram/index.json") if (native / name).is_dir() else []
        for index_path in sorted(found, key=lambda path: (len(path.parts), path.as_posix())):
            try:
                images = json.loads(index_path.read_text(encoding="utf-8")).get("images") or {}
            except (OSError, ValueError, AttributeError):
                continue
            if images:
                return index_path.parent.parent.relative_to(app_dir).as_posix()
    return None


def stage_actor_vram_textures(build_dir: Path, stage: Path, godot: Path, cache: Path, logs: Path, app_dir: Path,
                              dirs: tuple[str, ...] = ACTOR_SIDECAR_DIRS, tool: Path | None = None,
                              procs: int | None = None, measure_procs: int | None = None) -> dict:
    """Build the VRAM sidecars of the actor GLBs' embedded images into app/assets/actors (AT-C3).

    A run of its own of the commit's tools/build_vram_textures.py (--actor-dir per folder of `dirs` the build tree
    has, --actor-out-root app/assets/actors), after the map run and with the same encode cache (actor encodes live
    in its _actors/ folder, so neither run prunes the other's). It plans the build tree's tracked GLBs, after the RL
    strip; the GLBs staged in app/ are those bytes (check_actor_vram_coverage proves it per image). Only index.json
    and the .evt files ship; each folder's quality report goes to the logs. The log is logs/actor-vram-textures.log
    and the receipt logs/actor-vram-textures.json (sizes per family, the tool's summary, the self-test folder)."""
    tool = tool or build_dir / ACTOR_VRAM_TOOL
    native = build_dir / ACTOR_ROOT
    present = tuple(name for name in dirs if (native / name).is_dir())
    skipped = [name for name in dirs if name not in present]
    if skipped:
        log(f"actor VRAM sidecars: the build tree has no {', '.join(skipped)} folder")
    out_root = app_dir / "assets" / "actors"
    receipt = {"schema": 1, "dirs": list(present), "skipped": skipped,
               "floors": ACTOR_SIDECAR_FLOORS, "families": {}, "files": 0, "bytes": 0, "sidecars": 0,
               "gpuBytes": 0, "summary": {}, "selfTest": None}
    if not present:
        (logs / "actor-vram-textures.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return receipt
    log(f"building actor VRAM texture sidecars ({', '.join(present)})")
    cache.mkdir(parents=True, exist_ok=True)
    runner_args = []
    if STORAGE:
        remaining = (STORAGE.budget.capacity - STORAGE.budget.reserve
                     - release_storage.unique_bytes(STORAGE.budget.roots) - 64 * 1024**2)
        # As for the map run: the child measures its whole cache, retained bytes included.
        runner_args = ["--link-output", "--cache-budget-bytes", str(remaining + release_storage.unique_bytes([cache]))]
    options = [arg for name in present for arg in ("--actor-dir", name)]
    if ACTOR_SIDECAR_FLOORS:
        options += ["--floors", json.dumps(ACTOR_SIDECAR_FLOORS, sort_keys=True)]
    if procs:
        options += ["--procs", str(procs)]
    if measure_procs:
        options += ["--measure-procs", str(measure_procs)]
    started = time.time()
    log_path = logs / "actor-vram-textures.log"
    with open(log_path, "w", encoding="utf-8", errors="replace") as handle:
        result = subprocess.run([sys.executable, str(tool), *options, "--actor-out-root", str(out_root),
                                 "--cache", str(cache), "--godot", str(godot), *runner_args],
                                stdout=handle, stderr=subprocess.STDOUT, timeout=3600,
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise PackageError(f"build_vram_textures.py --actor-dir failed; log: {log_path}\n{text[-2000:]}")
    summary = _tool_summary(text)
    receipt["summary"] = {key: summary[key] for key in (
        "encoded", "cached", "remeasured", "encodeSeconds", "seconds", "actorGlbs", "actorImages", "actorAccepted",
        "actorExcluded", "actorGpuBytes", "actorFileBytes", "basePsnrMedian") if key in summary}
    for report in sorted((out_root / "native").rglob("vram/report.json")):
        folder = report.parent.parent.relative_to(app_dir)
        shutil.move(str(report), logs / ("vram-report-app__" + "__".join(folder.parts) + ".json"))
    for folder in sorted((out_root / "native").rglob(vram_tool.SIDECAR_DIR)):
        if not folder.is_dir():
            continue
        family = folder.relative_to(out_root / "native").parts[0]
        row = receipt["families"].setdefault(family, {"indexes": 0, "files": 0, "bytes": 0, "sidecars": 0,
                                                      "excluded": 0, "gpuBytes": 0})
        for path in folder.iterdir():
            if path.is_file():
                row["files"] += 1
                row["bytes"] += path.stat().st_size
        index_path = folder / "index.json"
        if index_path.is_file():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            row["indexes"] += 1
            row["sidecars"] += len(index.get("images", {}))
            row["excluded"] += len(index.get("excluded", {}))
            row["gpuBytes"] += sum(int(entry.get("gpuBytes", 0)) for entry in index.get("images", {}).values())
    for key in ("files", "bytes", "sidecars", "gpuBytes"):
        receipt[key] = sum(row[key] for row in receipt["families"].values())
    receipt["selfTest"] = actor_self_test_directory(app_dir, present)
    receipt["seconds"] = round(time.time() - started, 1)
    log(f"staged {receipt['files']} actor VRAM sidecar files ({receipt['bytes'] / 1e6:.0f} MB, already zstd: the "
        f"download grows by about as much; {receipt['sidecars']} sidecars, {receipt['gpuBytes'] / 1048576:.0f} MiB "
        f"on the GPU) in {receipt['seconds']:.0f} s: "
        + ", ".join(f"{name} {row['bytes'] / 1e6:.1f} MB" for name, row in sorted(receipt["families"].items())))
    (logs / "actor-vram-textures.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def _glb_embedded_images(path: Path) -> tuple[dict, list[tuple[int, str]]]:
    """A GLB's JSON document and (image index, sha256) for each bufferView image build_vram_textures.py plans (its
    embedded_images rule: the declared PNG/JPEG/WebP type, else the bytes' signature), reading only the JSON and the
    image byte ranges. A staged RLCZ creature envelope is decoded first. Raises ValueError on a malformed file."""
    with open(path, "rb") as raw:
        if raw.read(4) == vram_tool.RLCZ_MAGIC:
            return _glb_stream_images(io.BytesIO(creature_compression.decode(path.read_bytes())))
        raw.seek(0)
        return _glb_stream_images(raw)


def _glb_stream_images(stream) -> tuple[dict, list[tuple[int, str]]]:
    header = stream.read(20)
    if len(header) < 20 or header[:4] != b"glTF":
        raise ValueError("not a GLB")
    length = struct.unpack_from("<I", header, 12)[0]
    data = stream.read(length)
    if len(data) != length:
        raise ValueError("truncated JSON chunk")
    document = json.loads(data.decode("utf-8"))
    chunk = stream.read(8)
    binary_start = binary_length = None
    if len(chunk) == 8 and struct.unpack_from("<I", chunk, 4)[0] == 0x004E4942:
        binary_start, binary_length = 20 + length + 8, struct.unpack_from("<I", chunk)[0]
    views = document.get("bufferViews", [])
    found = []
    for index, image in enumerate(document.get("images", [])):
        view_index = image.get("bufferView")
        if not isinstance(view_index, int) or not 0 <= view_index < len(views):
            continue
        view = views[view_index]
        if view.get("buffer", 0) != 0 or binary_start is None:
            raise ValueError(f"image {index} lives outside the GLB's BIN chunk")
        start, size = int(view.get("byteOffset", 0)), int(view["byteLength"])
        if start < 0 or start + size > binary_length:
            raise ValueError(f"image {index}'s bufferView runs past the BIN chunk")
        stream.seek(binary_start + start)
        payload = stream.read(size)
        if len(payload) != size:
            raise ValueError(f"image {index}'s bytes are truncated")
        if (vram_tool.EMBEDDED_TYPES.get(str(image.get("mimeType", "")).lower()) is None
                and payload[:8] != PNG_SIGNATURE and payload[:3] != b"\xff\xd8\xff" and payload[8:12] != b"WEBP"):
            continue  # not an image the client decodes either
        found.append((index, hashlib.sha256(payload).hexdigest()))
    return document, found


def _retired_actor_files(build_dir: Path) -> set[str]:
    """The paths (relative to res://assets, e.g. actors/native/creatures/x.glb) the retirement index retires."""
    path = build_dir / "godot-client" / "data" / "assets" / "retired_procedural_models.json"
    if not path.is_file():
        return set()
    try:
        paths = json.loads(path.read_text(encoding="utf-8-sig")).get("runtimePaths", [])
        if not isinstance(paths, list):
            raise ValueError("runtimePaths is not a list")
    except (OSError, ValueError, AttributeError) as error:
        raise PackageError(f"cannot read the retirement index {path}: {error}") from error
    return {PurePosixPath(item).as_posix() for item in paths if isinstance(item, str) and item}


def check_actor_vram_coverage(build_dir: Path, app_dir: Path, dirs: tuple[str, ...]) -> dict:
    """Every embedded image of every staged, non-retired GLB below app/assets/actors/native/<dir> (dirs) has a
    sidecar in its GLB directory's vram/index.json whose roles cover every role a GLB of that directory samples it
    in, or an exclusion with a reason (the client decodes those); no index names an image no GLB beside it embeds,
    and no actor sidecar index sits outside those directories. Run after check_loose_vram_textures (files and
    hashes). Returns and logs the coverage counts."""
    assets = app_dir / "assets"
    native = assets / "actors" / "native"
    retired = _retired_actor_files(build_dir)
    problems: list[str] = []
    needs: dict[Path, dict[str, set[str]]] = {}
    families: dict[str, dict] = {}
    glbs = 0
    for name in dirs:
        family = native / name
        row = families.setdefault(name, {"glbs": 0, "images": 0, "sidecars": 0, "excluded": {}})
        for glb in sorted(family.rglob("*.glb")) if family.is_dir() else []:
            if vram_tool.SIDECAR_DIR in glb.relative_to(family).parts[:-1]:
                problems.append(f"{glb.relative_to(app_dir).as_posix()}: a GLB inside a sidecar folder")
                continue
            if glb.relative_to(assets).as_posix() in retired:
                continue
            glbs += 1
            row["glbs"] += 1
            try:
                document, images = _glb_embedded_images(glb)
            except (OSError, ValueError, KeyError, TypeError) as error:
                problems.append(f"{glb.relative_to(app_dir).as_posix()}: cannot read its images: {error}")
                continue
            roles = vram_tool.image_roles(document)
            wanted = needs.setdefault(glb.parent, {})
            for index, sha in images:
                wanted.setdefault(sha, set()).update(vram_tool.role_names(roles.get(index, set())))
    counts = {"glbs": glbs, "directories": 0, "images": 0, "sidecars": 0, "excluded": {}, "families": families}
    for directory, wanted in sorted(needs.items()):
        if not wanted:
            continue
        label = directory.relative_to(app_dir).as_posix()
        row = families[directory.relative_to(native).parts[0]]
        index_path = directory / vram_tool.SIDECAR_DIR / "index.json"
        if not index_path.is_file():
            problems.append(f"{label}: {len(wanted)} embedded images and no vram/index.json")
            continue
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as error:
            problems.append(f"{label}: unreadable vram/index.json: {error}")
            continue
        images = index.get("images") if isinstance(index.get("images"), dict) else {}
        excluded = index.get("excluded") if isinstance(index.get("excluded"), dict) else {}
        counts["directories"] += 1
        for sha, roles in sorted(wanted.items()):
            counts["images"] += 1
            row["images"] += 1
            if sha in images:
                listed = set(images[sha].get("roles") or []) if isinstance(images[sha], dict) else set()
                if not roles <= listed:
                    problems.append(f"{label}: the sidecar of {sha[:12]} is for {sorted(listed)}, its GLBs sample "
                                    f"it as {sorted(roles)}")
                    continue
                counts["sidecars"] += 1
                row["sidecars"] += 1
            elif sha in excluded and str(excluded[sha]).strip():
                reason = str(excluded[sha]).split(":")[0]
                counts["excluded"][reason] = counts["excluded"].get(reason, 0) + 1
                row["excluded"][reason] = row["excluded"].get(reason, 0) + 1
            else:
                problems.append(f"{label}: embedded image {sha[:12]} has no sidecar and no exclusion reason")
        for sha in sorted((set(images) | set(excluded)) - set(wanted)):
            problems.append(f"{label}: its index names {sha[:12]}, which no GLB in that folder embeds")
    for index_path in sorted((assets / "actors").rglob("vram/index.json")) if (assets / "actors").is_dir() else []:
        directory = index_path.parent.parent
        if not needs.get(directory):
            problems.append(f"{directory.relative_to(app_dir).as_posix()}: an actor sidecar index outside the "
                            f"GLB folders of {', '.join(dirs) or 'no actor folder'}")
    if problems:
        raise PackageError(f"{len(problems)} actor sidecar coverage problems:\n  " + "\n  ".join(problems[:40]))
    reasons = ", ".join(f"{reason} {n}" for reason, n in sorted(counts["excluded"].items())) or "none"
    log(f"checked actor VRAM coverage: {glbs} GLBs, {counts['images']} embedded images in {counts['directories']} "
        f"folders: {counts['sidecars']} sidecars, {sum(counts['excluded'].values())} decoded ({reasons})")
    return counts


TEXTURE_POLICY_DIRECTORY_KEY = "rl_texture_policy_directory"


def external_image_policy_directories(base: Path, resources: dict, policies, asset_root: Path) -> dict[str, set[Path]]:
    """Original sidecar directories, independent of a canonical image's URI.

    An unannotated image keeps the legacy directory beside its source pixels.
    Directory metadata never supplies an alternative source or expected hash.
    """
    if policies is None:
        policies = {}
    if not isinstance(policies, dict):
        raise PackageError("externalImagePolicies must be an object")
    unknown = set(policies) - set(resources)
    if unknown:
        raise PackageError("externalImagePolicies names an undeclared image: " + str(sorted(unknown)[0]))
    root = asset_root.resolve()

    def path_for(uri: str) -> Path:
        if (not isinstance(uri, str) or not uri or "\\" in uri or ":" in uri or "%" in uri
                or PurePosixPath(uri).is_absolute()):
            raise PackageError(f"unsafe external image policy path: {uri!r}")
        path = (base / uri).resolve()
        if not path.is_relative_to(root):
            raise PackageError(f"external image policy path resolves outside eloria-assets: {uri}")
        return path

    result = {}
    for uri in resources:
        image = path_for(uri)
        if uri not in policies:
            result[uri] = {image.parent}
            continue
        values = policies[uri]
        if not isinstance(values, list) or not values:
            raise PackageError(f"externalImagePolicies[{uri!r}] must be a nonempty array")
        result[uri] = {path_for(value) for value in values}
    return result


def _check_image_policy_descriptors(document: dict, base: Path, policies: dict[str, set[Path]],
                                    asset_root: Path, label: str, problems: list[str]) -> None:
    """An image's actual runtime policy must be one its manifest/index declares."""
    root = asset_root.resolve()
    for image in document.get("images", []):
        if not isinstance(image, dict):
            continue
        uri = image.get("uri")
        if not isinstance(uri, str) or not uri or uri.startswith("data:"):
            continue
        extras = image.get("extras") or {}
        if not isinstance(extras, dict):
            problems.append(f"{label}: image {uri} extras must be an object")
            continue
        tagged = TEXTURE_POLICY_DIRECTORY_KEY in extras
        if uri not in policies:
            if tagged:
                problems.append(f"{label}: policy-tagged image {uri} has no declared source/policy")
            continue
        policy = extras.get(TEXTURE_POLICY_DIRECTORY_KEY)
        if tagged and (not isinstance(policy, str) or not policy or "\\" in policy or ":" in policy or "%" in policy
                       or PurePosixPath(policy).is_absolute()):
            problems.append(f"{label}: image {uri} has unsafe {TEXTURE_POLICY_DIRECTORY_KEY}")
            continue
        directory = (base / policy).resolve() if tagged else (base / uri).resolve().parent
        if not directory.is_relative_to(root) or directory not in policies[uri]:
            problems.append(f"{label}: image {uri} policy directory disagrees with declared image policies")


def check_vram_textures(stage: Path) -> None:
    """Every external map image a staged manifest names is staged, has a
    sidecar or a reason it has none, and every staged sidecar is the file its
    index names, byte for byte."""
    stage = stage.resolve()
    problems: list[str] = []
    indexes: dict[Path, dict] = {}
    digests: dict[Path, str] = {}
    asset_root = (stage / "eloria-assets").resolve()
    checked = 0

    def check_sources(base: Path, resources: dict, policies, label: str, *, sidecars: bool = True):
        nonlocal checked
        try:
            directories = external_image_policy_directories(base, resources, policies, asset_root)
        except PackageError as error:
            problems.append(f"{label}: {error}")
            return {}
        for uri, sha in resources.items():
            image = (base / uri).resolve()
            if not image.is_file():
                problems.append(f"{label}: external image {uri} is not in the package")
                continue
            if image not in digests:
                digests[image] = hashlib.sha256(image.read_bytes()).hexdigest()
            if digests[image] != sha:
                problems.append(f"{image.relative_to(stage)}: source sha256 differs from the manifest")
            if not sidecars:
                continue
            for directory in sorted(directories[uri]):
                if directory not in indexes:
                    index_path = directory / "vram" / "index.json"
                    try:
                        indexes[directory] = (json.loads(index_path.read_text(encoding="utf-8"))
                                              if index_path.is_file() else {})
                        if not isinstance(indexes[directory], dict):
                            raise ValueError("sidecar index must be an object")
                    except (OSError, ValueError):
                        problems.append(f"{index_path.relative_to(stage)}: cannot read sidecar index")
                        indexes[directory] = {}
                index = indexes[directory]
                checked += 1
                if sha not in index.get("images", {}) and sha not in index.get("excluded", {}):
                    problems.append(f"{image.relative_to(stage)}: no sidecar and no exclusion reason in "
                                    f"{directory.relative_to(stage)}")
        return directories

    for manifest_path in (stage / "eloria-assets").rglob("world.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        resources = manifest.get("externalResources") or {}
        if not isinstance(resources, dict) or "streamingChunks" in manifest:
            continue
        glb = manifest_path.parent / str(manifest.get("asset", {}).get("glb", "world.glb"))
        label = manifest_path.relative_to(stage).as_posix()
        policies = check_sources(glb.parent, resources, manifest.get("externalImagePolicies"), label)
        _check_image_policy_descriptors(gltf_document(glb), glb.parent, policies, asset_root, label, problems)
        # Road-only style uses retain their original source fallback. Validate
        # the source/policy metadata without creating a new sidecar requirement.
        road = manifest.get("roadGround")
        if isinstance(road, dict):
            try:
                road_dependencies(stage, manifest_path, road)
                path = manifest_path.parent / road["metadata"]
                metadata = json.loads(path.read_text(encoding="utf-8"))
                road_resources = {uri: sha for style in metadata.get("styles", [])
                                  for uri, sha in style.get("externalResources", {}).items()}
                road_policies = check_sources(path.parent, road_resources, metadata.get("externalImagePolicies"),
                                              path.relative_to(stage).as_posix(), sidecars=False)
                for style in metadata.get("styles", []):
                    _check_image_policy_descriptors(style.get("material_document", {}), path.parent, road_policies,
                                                    asset_root, label + " roadGround", problems)
            except (RoadGroundDependencyError, OSError, ValueError, KeyError, TypeError) as error:
                problems.append(f"{label} roadGround: {error}")
    # A shared prototype can be the only consumer of an image. Its source and
    # original policy are recorded by the pool index, not by its parent map.
    for index_path in (stage / "eloria-assets/maps/_shared/meshes").glob("index.json"):
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8")).get("prototypes", {})
        except (OSError, ValueError):
            continue  # check_shared_meshes reports an unreadable pool index.
        for identity, entry in entries.items():
            glb = index_path.parent / (identity + ".glb")
            if not glb.is_file() or not isinstance(entry, dict):
                continue
            resources = entry.get("images") or {}
            if not isinstance(resources, dict):
                continue
            label = glb.relative_to(stage).as_posix()
            policies = check_sources(glb.parent, resources, entry.get("imagePolicies"), label)
            _check_image_policy_descriptors(gltf_document(glb), glb.parent, policies, asset_root, label, problems)
    sidecars = 0
    for directory, index in indexes.items():
        for sha, entry in index.get("images", {}).items():
            # A "pool" entry's file is the one another pool ships (share_identical_sidecars).
            path = Path(os.path.normpath(directory / entry.get("pool", ".") / "vram" / entry["file"]))
            if not path.resolve().is_relative_to(asset_root):
                problems.append(f"{directory.relative_to(stage)}: sidecar path resolves outside eloria-assets")
                continue
            if not path.is_file():
                problems.append(f"{path.relative_to(stage)}: listed in the index but missing")
                continue
            sidecars += 1
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                problems.append(f"{path.relative_to(stage)}: sha256 differs from the index")
        listed = {entry["file"] for entry in index.get("images", {}).values() if "pool" not in entry}
        for path in (directory / "vram").glob("*"):
            if path.name != "index.json" and path.name not in listed:
                problems.append(f"{path.relative_to(stage)}: not named by the index")
    if problems:
        raise PackageError(f"{len(problems)} VRAM sidecar problems:\n  " + "\n  ".join(problems[:40]))
    log(f"checked VRAM sidecars: {checked} external image references, {sidecars} sidecars")


# The pool of every legacy map's images (vram_textures.gd SHARED_ASSETS): its sidecars are never moved or rewritten.
PRIMARY_SIDECAR_POOL = "eloria-assets/maps/nymara-regions/_continent/shared-assets"
# What must agree between two index entries before one file serves both.
SHARED_SIDECAR_KEYS = ("file", "sha256", "recipe", "format", "width", "height", "mipmaps", "gpuBytes")
# The packaged client's declaration that it reads an index entry's "pool" (vram_textures.gd INDEX_FEATURES).
POOL_FEATURE = re.compile(r'const INDEX_FEATURES\b[^\n]*"pool"')


def client_reads_pooled_sidecars(build_dir: Path) -> bool:
    """True when the commit being packaged has a client that reads "pool" entries. The share step runs from the
    packager invoked, whatever --ref it packages (the sidecars themselves come from the commit's own
    build_vram_textures.py); a client without the feature would miss every shared file and decode those images."""
    script = build_dir / "godot-client" / "src" / "world" / "vram_textures.gd"
    return script.is_file() and POOL_FEATURE.search(script.read_text(encoding="utf-8")) is not None


def share_identical_sidecars(stage: Path, primary: str = PRIMARY_SIDECAR_POOL) -> dict:
    """Ships each sidecar file once. build_vram_textures.py plans every image
    directory on its own, so an image two pools hold gets the same .evt file in
    both vram/ folders (continent-v2's _continent_v2/shared-assets shares 308
    encodes, 124.7 MiB, with the primary pool). For each other pool's index
    entry whose file is byte for byte the primary pool's entry for that sha
    (SHARED_SIDECAR_KEYS agree and the bytes are equal), the staged copy is
    removed and the entry names the primary pool instead: "pool" is the primary
    source directory relative to the entry's own, where vram_textures.gd reads
    the file and still checks its sha256. The entry keeps its own roles. The
    primary pool's index and files are never touched, so a legacy map loads
    exactly what it loaded before. Returns the files and bytes removed and the
    source directories (stage-relative) whose index now names the primary pool."""
    shared = {"files": 0, "bytes": 0, "directories": []}
    primary_dir = stage / primary
    primary_index = primary_dir / "vram" / "index.json"
    if not primary_index.is_file():
        return shared
    twins = json.loads(primary_index.read_text(encoding="utf-8")).get("images", {})
    for index_path in sorted((stage / "eloria-assets").rglob("vram/index.json")):
        directory = index_path.parent.parent
        if os.path.samefile(directory, primary_dir):
            continue
        index = json.loads(index_path.read_text(encoding="utf-8"))
        changed = False
        for sha, entry in index.get("images", {}).items():
            twin = twins.get(sha)
            if not twin or "pool" in entry or any(twin.get(key) != entry.get(key) for key in SHARED_SIDECAR_KEYS):
                continue
            mine, theirs = index_path.parent / entry["file"], primary_index.parent / twin["file"]
            if not mine.is_file() or not theirs.is_file() or mine.read_bytes() != theirs.read_bytes():
                continue
            shared["files"] += 1
            shared["bytes"] += mine.stat().st_size
            mine.unlink()
            entry["pool"] = Path(os.path.relpath(primary_dir, directory)).as_posix()
            changed = True
        if changed:
            index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8", newline="\n")
            shared["directories"].append(directory.relative_to(stage).as_posix())
    return shared


def pooled_sidecar_directory(stage: Path) -> str | None:
    """The first staged image directory (stage-relative) whose sidecar index names another pool's file ("pool"), for
    the smoke launch's pooled decode; None when nothing was shared."""
    for index_path in sorted((stage / "eloria-assets").rglob("vram/index.json")):
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if any("pool" in entry for entry in index.get("images", {}).values()):
            return index_path.parent.parent.relative_to(stage).as_posix()
    return None


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"


def smoke_launch(app_dir: Path, logs: Path, platform: dict, vram_textures: bool = False,
                 pool_test: str | None = None, *, actor_test: str | None = None,
                 clean_feature_environment: bool = False,
                 optimization_profile: str | None = None, log_name: str = "smoke.log") -> None:
    # The launch must leave the package exactly as it was: a user:// that
    # falls back to a relative path writes settings and caches into app/,
    # and they would ship in the archive.
    #
    # With sidecars staged it also proves the shipped binary decodes one: the
    # client logs VramTextures.self_test() when ELORIA_VRAM_SELF_TEST=1. The
    # launch is headless, so this covers the decode, not the GPU upload.
    # pool_test (a stage-relative source directory whose index names another
    # pool's sidecars) makes it also decode one of those, from where it ships.
    # actor_test (an app-relative actor folder, assets/actors/native/races)
    # sets ELORIA_ACTOR_VRAM_SELF_TEST: the client must read that folder's
    # actor sidecar index, decode a sidecar and Image.decompress() a copy in
    # the shipped template (ACTOR_VRAM_SELF_TEST_LINE, AT-C3).
    before = {p for p in app_dir.parent.rglob("*")}
    try:
        text = _launch(app_dir, logs, platform, vram_textures, pool_test, actor_test=actor_test,
                       clean_feature_environment=clean_feature_environment,
                       optimization_profile=optimization_profile, log_name=log_name)
        for wanted, what in ((VRAM_SELF_TEST_OK, "a VRAM sidecar"),
                             (VRAM_SELF_TEST_POOL_OK if pool_test else None, "a sidecar another pool ships")):
            if wanted and vram_textures and text is not None and wanted not in text:
                lines = [line for line in text.splitlines() if "vram_textures" in line]
                raise PackageError(f"the exported client did not decode {what}:\n  "
                                   + "\n  ".join(lines[:10] or ["(no vram_textures line)"])
                                   + f"\nfull log: {logs / log_name}")
        if actor_test and text is not None and not any(ACTOR_VRAM_SELF_TEST_LINE.search(line)
                                                       for line in text.splitlines()):
            lines = [line for line in text.splitlines() if "actor_images" in line]
            raise PackageError(f"the exported client did not decode and decompress an actor sidecar of {actor_test}:"
                               "\n  " + "\n  ".join(lines[:10] or ["(no actor_images line)"])
                               + f"\nfull log: {logs / log_name}")
    finally:
        added = sorted(p for p in app_dir.parent.rglob("*") if p not in before)
        if added:
            raise PackageError("the smoke launch wrote into the package:\n  "
                               + "\n  ".join(str(p.relative_to(app_dir.parent)) for p in added[:20]))


def _launch(app_dir: Path, logs: Path, platform: dict, vram_textures: bool = False,
            pool_test: str | None = None, *, actor_test: str | None = None,
            clean_feature_environment: bool = False,
            optimization_profile: str | None = None, log_name: str = "smoke.log") -> str | None:
    if optimization_profile not in (None, "legacy", "human-testing") or Path(log_name).name != log_name:
        raise PackageError("smoke checks require a known profile and a scoped log filename")
    if actor_test is not None and (not ACTOR_VRAM_SELF_TEST_PATH.match(actor_test)
                                   or ".." in actor_test.split("/") or "//" in actor_test):
        raise PackageError(f"the actor sidecar self-test folder is not an app-relative actor folder: {actor_test!r}")
    profile_args = [] if optimization_profile is None else ["--", "--optimization-profile=" + optimization_profile]
    if platform.get("preset") == "macOS":
        return macos_package.smoke(app_dir, logs, run_godot, SMOKE_FAILURES)
    self_test = "ELORIA_VRAM_SELF_TEST=1 " if vram_textures else ""
    pool_dir = f"res://../{pool_test}" if vram_textures and pool_test else ""
    if pool_dir:
        self_test += f"ELORIA_VRAM_SELF_TEST_POOL={pool_dir} "
    if actor_test:
        self_test += f"{ACTOR_VRAM_SELF_TEST_VARIABLE}={actor_test} "
    base_env = full_optimization_package.clean_environment() if clean_feature_environment else dict(os.environ)
    if platform["binary"].endswith(".exe"):
        log("smoke launch (headless)")
        with tempfile.TemporaryDirectory(prefix="eloria-smoke-") as appdata:
            # A throwaway APPDATA keeps user:// away from the real client settings.
            env = dict(base_env, APPDATA=appdata, LOCALAPPDATA=appdata)
            if vram_textures:
                env["ELORIA_VRAM_SELF_TEST"] = "1"
            if pool_dir:
                env["ELORIA_VRAM_SELF_TEST_POOL"] = pool_dir
            if actor_test:
                env[ACTOR_VRAM_SELF_TEST_VARIABLE] = actor_test
            text = run_godot(app_dir / platform["binary"], ["--headless", "--quit-after", "600", *profile_args],
                             logs / log_name, timeout=300, env=env)
    elif os.name != "nt":
        log("smoke launch (headless, native Linux)")
        with tempfile.TemporaryDirectory(prefix="rabbitlands-smoke-") as userdir:
            env = dict(base_env, HOME=userdir, XDG_DATA_HOME=userdir, XDG_CONFIG_HOME=userdir)
            if vram_textures:
                env["ELORIA_VRAM_SELF_TEST"] = "1"
            if pool_dir:
                env["ELORIA_VRAM_SELF_TEST_POOL"] = pool_dir
            if actor_test:
                env[ACTOR_VRAM_SELF_TEST_VARIABLE] = actor_test
            binary = app_dir / platform["binary"]
            binary.chmod(binary.stat().st_mode | 0o111)
            text = run_godot(binary, ["--headless", "--quit-after", "600", *profile_args],
                             logs / log_name, timeout=300, env=env, cwd=app_dir)
    else:
        # The Linux binary runs under WSL, with a throwaway HOME for user://.
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        if not wsl or subprocess.run([wsl, "-d", WSL_DISTRO, "--exec", "true"],
                                     capture_output=True).returncode != 0:
            log(f"smoke launch skipped: WSL distribution {WSL_DISTRO} is not available")
            return None
        log(f"smoke launch (headless, WSL {WSL_DISTRO})")
        command = (f'rl_smoke_userdata=$(mktemp -d) && cd "{wsl_path(app_dir)}" && '
                   f'HOME="$rl_smoke_userdata" XDG_DATA_HOME="$rl_smoke_userdata" XDG_CONFIG_HOME="$rl_smoke_userdata" {self_test}'
                   f'./{platform["binary"]} --headless --quit-after 600 {" ".join(profile_args)}; '
                   f'status=$?; rm -rf "$rl_smoke_userdata"; exit $status')
        # --exec, not --: "--" hands the line to the distro's login shell
        # first, which expands $home to nothing before sh ever sees it.
        text = run_godot(Path(wsl), ["-d", WSL_DISTRO, "--exec", "sh", "-c", command],
                         logs / log_name, timeout=300)
    hits = [line for line in text.splitlines() if any(f in line for f in SMOKE_FAILURES)]
    if hits:
        raise PackageError("the exported client reported errors at startup:\n  "
                           + "\n  ".join(hits[:30]) + f"\nfull log: {logs / log_name}")
    return text


def default_server(build_dir: Path) -> tuple[str, str]:
    scene = (build_dir / "godot-client/src/app/main.tscn").read_text(encoding="utf-8")
    host = re.search(r'\[node name="Host"[^\]]*\]\s*(?:[^\[]*?)text = "([^"]*)"', scene)
    # Anchored: "min_value = 1.0" ends with "value = 1.0", and an unanchored
    # match took it, so every README built without --server said "Port: 1".
    port = re.search(r'\[node name="Port"[^\]]*\]\s*(?:[^\[]*?)(?m:^)value = ([0-9.]+)', scene)
    return (host.group(1) if host else "?", str(int(float(port.group(1)))) if port else "2000")


def write_compatibility_launchers(stage: Path, args: list[str], platform: dict,
                                 updating: bool) -> None:
    """Force renderer selection before Godot initializes, also through updates."""
    windows = platform["binary"].endswith(".exe")
    # Additional launcher arguments are game/user arguments even when there is
    # no baked server. Keep their separator before forwarding them on both OSes.
    extra = " --" + (" " + " ".join(args) if args else "")
    renderer = "--rendering-method gl_compatibility --rendering-driver opengl3"
    safe_environment = {"ELORIA_LOOK": "0", "ELORIA_LOOK_QUALITY": "low",
                        "ELORIA_VRAM_TEXTURES": "0", "ELORIA_NO_MAP_CACHE": "1"}
    for safe in (False, True):
        label = "safe mode" if safe else "compatibility"
        slug = "safe-mode" if safe else "compatibility"
        option = "--client-safe-mode" if safe else "--client-compatibility"
        log_name = f"eloria-{slug}.log"
        if windows:
            command = (f'"%~dp0RabbitLands-updater.exe" -- --launch-only {option}' if updating else
                       f'"%~dp0app\\RabbitLands.exe" {renderer} --verbose --log-file "%~dp0{log_name}"{extra}')
            environment = ("" if updating or not safe else "".join(
                f'set "{key}={value}"\r\n' for key, value in safe_environment.items()))
            (stage / f"RabbitLands ({label}).bat").write_text(
                '@echo off\r\nsetlocal\r\ncd /d "%~dp0app"\r\n' + environment +
                f'echo Starting Rabbit Lands in {label} mode. Close the game to view the log.\r\n' +
                command + ' %*\r\nset "ELORIA_EXIT_CODE=%errorlevel%"\r\n' +
                'echo Rabbit Lands exited with status %ELORIA_EXIT_CODE%.\r\n' +
                f'type "%~dp0{log_name}"\r\necho.\r\necho Log saved as {log_name}.\r\n' +
                'pause >nul\r\nexit /b %ELORIA_EXIT_CODE%\r\n', encoding="ascii")
        else:
            command = (f'../RabbitLands-updater.x86_64 -- --launch-only {option} "$@"' if updating else
                       f'./{platform["binary"]} {renderer} --verbose --log-file "../{log_name}"{extra} "$@"')
            environment = ("" if updating or not safe else "".join(
                f'export {key}={value}\n' for key, value in safe_environment.items()))
            (stage / f"RabbitLands-{slug}.sh").write_text(
                '#!/bin/sh\ncd "$(dirname "$0")/app" || exit 1\n' + environment +
                f'echo "Starting Rabbit Lands in {label} mode; log: {log_name}."\n' +
                command + '\nstatus=$?\necho "Rabbit Lands exited with status $status."\nexit "$status"\n',
                encoding="ascii", newline="\n")


def write_launchers(stage: Path, server: str | None, build_dir: Path, version: str,
                    platform: dict) -> list[str]:
    args = []
    if server:
        host, _, port = server.partition(":")
        args = [f"--server={host}"] + ([f"--port={port}"] if port else [])
        shown_host, shown_port = host, port or default_server(build_dir)[1]
    else:
        shown_host, shown_port = default_server(build_dir)
    extra = " --" + (" " + " ".join(args) if args else "")
    updating = (stage / ("RabbitLands-updater.exe" if platform["binary"].endswith(".exe") else "RabbitLands-updater.x86_64")).is_file()
    if updating:
        extra = " -- --launch-only" + (" " + " ".join(args) if args else "")
    (stage / "launcher-defaults.json").write_text(json.dumps({"args": args}), encoding="utf-8")
    write_compatibility_launchers(stage, args, platform, updating)
    if not platform["binary"].endswith(".exe"):
        (stage / "RabbitLands.sh").write_text(
            '#!/bin/sh\n'
            'cd "$(dirname "$0")/app" || exit 1\n'
            f'exec {"../RabbitLands-updater.x86_64" if updating else "./" + platform["binary"]}{extra} "$@"\n', encoding="ascii", newline="\n")
        (stage / "RabbitLands-debug.sh").write_text(
            '#!/bin/sh\n'
            'cd "$(dirname "$0")/app" || exit 1\n'
            'echo "Rabbit Lands is running; its log is saved as eloria-debug.log beside this script."\n'
            + (f'../RabbitLands-updater.x86_64 -- --launch-only --client-debug {" ".join(args)} "$@"\n' if updating else
               f'./{platform["binary"]} --verbose --log-file ../eloria-debug.log{extra} "$@"\n') +
            'status=$?\n'
            'echo "Rabbit Lands exited with status $status."\n'
            'exit $status\n', encoding="ascii", newline="\n")
        (stage / "README.txt").write_text(
            README_LINUX.format(version=version, host=shown_host, port=shown_port,
                                archive=f"{stage.name}.tar.gz", folder=stage.name, binary=platform["binary"]),
            encoding="utf-8", newline="\n")
        if updating:
            append_update_readme(stage, "x86_64")
        return args
    (stage / "RabbitLands.bat").write_text(
        '@echo off\r\ncd /d "%~dp0app"\r\n' +
        f'start "" "%~dp0{"RabbitLands-updater.exe" if updating else "app" + chr(92) + "RabbitLands.exe"}"{extra} %*\r\n', encoding="ascii")
    # The installed export templates carry no console wrapper, and a GUI exe
    # prints nothing to the window that started it, so the log goes to a file
    # that is shown once the game exits.
    (stage / "RabbitLands (debug console).bat").write_text(
        '@echo off\r\ncd /d "%~dp0app"\r\n'
        'echo Rabbit Lands is running; its log will appear here when it exits.\r\n'
        + (f'"%~dp0RabbitLands-updater.exe" -- --launch-only --client-debug {" ".join(args)} %*\r\n' if updating else
           f'RabbitLands.exe --verbose --log-file "%~dp0eloria-debug.log"{extra} %*\r\n') +
        'type "%~dp0eloria-debug.log"\r\n'
        'echo.\r\necho The log is saved as eloria-debug.log. Press any key to close this window.\r\n'
        'pause >nul\r\n',
        encoding="ascii")
    (stage / "README.txt").write_text(README.format(version=version, host=shown_host, port=shown_port),
                                      encoding="utf-8", newline="\r\n")
    if updating:
        append_update_readme(stage, "exe")
    return args


def append_update_readme(stage: Path, extension: str) -> None:
    with (stage / "README.txt").open("a", encoding="utf-8") as output:
        output.write(f"\nUpdates and removal\n-------------------\n"
                     "The game checks the latest published release when it opens and asks before updating.\n"
                     "Accepting closes the game, updates it, and reopens in the same launch mode.\n"
                     f"RabbitLands-updater.{extension} checks for updates, replaces itself when needed,\n"
                     "and downloads only changed game packages.\n"
                     f"Run RabbitLands-uninstall.{extension} to remove this installation.\n"
                     "Player settings outside the game folder are kept.\n")


README = """Rabbit Lands - Windows Client
=======================
Build {version}

Requirements
------------
Windows 10 or 11, 64-bit, with Vulkan or OpenGL 3.3 graphics support. The
normal launcher uses Forward+; compatibility mode explicitly uses OpenGL.

Install
-------
From the zip: unzip the whole folder anywhere (no admin rights needed) and
double-click RabbitLands.bat. Keep the folder together - the game reads the app and
eloria-assets folders that sit beside it.

From the installer: run it and start Rabbit Lands from the Start menu.

The first time you run it, Windows SmartScreen may say "Windows protected your
PC" because the program is not code-signed. Click "More info", then "Run
anyway".

Playing
-------
The login screen is pre-filled with the server:

    Host: {host}
    Port: {port}

Enter a username and password and press Connect, or create a character.

What is in this folder
----------------------
  RabbitLands.bat                    Start the game.
  RabbitLands (debug console).bat    Start with a log window, for troubleshooting.
  RabbitLands (compatibility).bat    Force OpenGL 3.3 and save a diagnostic log.
  RabbitLands (safe mode).bat        OpenGL, low quality, painted look off,
                               map cache bypassed, original map textures.
  app\\                          The game executable and its data.
  eloria-assets\\                World maps and region artwork.

Troubleshooting
---------------
Nothing happens when I start it
    Run "RabbitLands (debug console).bat". It keeps a window open with the error.

It cannot connect
    Check that outbound TCP to the port above is not blocked by a firewall.

Blue, black or empty viewport after login
    Close the game, run "RabbitLands (debug console).bat", and reproduce the issue.
    Next try "RabbitLands (compatibility).bat", then "RabbitLands (safe mode).bat".
    Send eloria-debug.log, eloria-compatibility.log and eloria-safe-mode.log
    from this folder, and say which mode worked. These modes preserve your
    saved graphics preferences. Safe mode may load slower and use more texture
    memory because it bypasses the cache and compressed map textures.
    An incomplete extraction can also cause missing models; extract again.

Logs from normal launches
    Paste %APPDATA%\\Godot\\app_userdata\\Eloria\\logs into File Explorer.
    client.log records hardware, login, map loading, viewport state and errors;
    up to five logs are kept. Diagnostic launches write to this game folder.
    Added diagnostics omit passwords, login names, chat and packet contents.
"""


README_LINUX = """Rabbit Lands - Linux Client
=====================
Build {version}

Requirements
------------
64-bit x86 Linux with a desktop session (X11, or Wayland with XWayland) and
a GPU driver supporting Vulkan or OpenGL 3.3. The normal launcher uses
Forward+; RabbitLands-compatibility.sh explicitly uses OpenGL.

Install
-------
Extract the whole folder anywhere you can write to, for example:

    tar -xzf {archive} -C ~/Games

then start the game:

    ~/Games/{folder}/RabbitLands.sh

Keep the folder together - the game reads the app and eloria-assets folders
that sit beside the scripts. If your desktop does not run .sh files on
double-click, start it from a terminal as above.

If RabbitLands.sh says "Permission denied", the archive was extracted by a tool
that dropped file permissions. Fix it with:

    chmod +x RabbitLands*.sh app/{binary}

Playing
-------
The login screen is pre-filled with the server:

    Host: {host}
    Port: {port}

Enter a username and password and press Connect, or create a character.

What is in this folder
----------------------
  RabbitLands.sh          Start the game.
  RabbitLands-debug.sh    Start with verbose logging to eloria-debug.log.
  RabbitLands-compatibility.sh   Force OpenGL; log: eloria-compatibility.log.
  RabbitLands-safe-mode.sh       OpenGL, low quality, painted look off,
                           cache bypassed, original map textures;
                           log: eloria-safe-mode.log.
  app/               The game executable and its data.
  eloria-assets/     World maps and region artwork.

Troubleshooting
---------------
Nothing happens when I start it
    Run ./RabbitLands-debug.sh from a terminal and read eloria-debug.log.

It cannot connect
    Check that outbound TCP to the port above is not blocked by a firewall.

Blue, black or empty viewport after login
    Reproduce with ./RabbitLands-debug.sh, then try ./RabbitLands-compatibility.sh and
    ./RabbitLands-safe-mode.sh. Send the three eloria-*.log files from this folder
    and say which mode worked. Saved graphics preferences are preserved.
    Safe mode can load slower and use more texture memory. An incomplete
    extraction can also cause missing models; extract again.

Logs from normal launches
    ~/.local/share/godot/app_userdata/Eloria/logs/client.log records hardware,
    login, map loading, viewport state and errors; up to five logs are kept.
    With XDG_DATA_HOME set, use $XDG_DATA_HOME/godot/app_userdata/Eloria/logs.
    Diagnostic launches write to this game folder. Added diagnostics omit
    passwords, login names, chat and packet contents.
"""


# --- outputs ------------------------------------------------------------------

def tar_filter(platform: dict):
    executables = {platform["binary"], "RabbitLands-updater.x86_64", "RabbitLands-uninstall.x86_64", "RabbitLands.sh", "RabbitLands-debug.sh",
                   "RabbitLands-compatibility.sh", "RabbitLands-safe-mode.sh"}

    def normalise(info):
        if Path(info.name).name == MARKER:
            return None
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mode = 0o755 if info.isdir() or Path(info.name).name in executables else 0o644
        # Staging hard links are a build optimization, never tar link entries.
        return info
    return normalise


def make_tarball_parts(stage: Path, platform: dict, base: str, accept_part, budget) -> dict:
    archive = stage.parent / f"{stage.name}.tar.gz"
    with release_storage.PartWriter(archive, base, client_release.PART_BYTES, accept_part, budget) as writer:
        with tarfile.open(fileobj=writer, mode="w|gz", compresslevel=1, dereference=True) as handle:
            handle.add(stage, arcname=stage.name, filter=tar_filter(platform))
    return {"parts": writer.parts, "size": writer.size, "sha256": writer.sha256}


def make_tarball(stage: Path, platform: dict) -> Path:
    """A .tar.gz, because a zip made on Windows cannot mark files executable."""
    archive = stage.parent / f"{stage.name}.tar.gz"
    archive.unlink(missing_ok=True)
    log(f"archiving {archive.name}")
    with tarfile.open(archive, "w:gz", compresslevel=1) as handle:
        handle.add(stage, arcname=stage.name, filter=tar_filter(platform))
    return archive


def make_zip(stage: Path) -> Path:
    archive = stage.with_suffix(".zip")
    archive.unlink(missing_ok=True)
    seven = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe"
    log(f"zipping {archive.name}")
    if seven.is_file():
        result = subprocess.run([str(seven), "a", "-tzip", "-mx=1", "-bso0", "-bsp0",
                                 str(archive), stage.name, f"-xr!{MARKER}"], cwd=stage.parent)
        if result.returncode != 0:
            raise PackageError("7-Zip failed")
    else:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as handle:
            for path in sorted(stage.rglob("*")):
                if path.is_file() and path.name != MARKER:
                    handle.write(path, path.relative_to(stage.parent))
    return archive


def make_installer(stage: Path, iscc: Path, version: str, launch_args: list[str], logs: Path) -> Path:
    # Inno Setup 6 cannot read every long asset path through a release's full
    # commit-qualified directory. A short junction retains the original files.
    DIST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inno-", dir=DIST) as temporary:
        source = Path(temporary) / "src"
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        command = f"New-Item -ItemType Junction -Path {quote(source)} -Target {quote(stage.resolve())} -ErrorAction Stop | Out-Null"
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], check=True,
                       stdout=subprocess.DEVNULL)
        try:
            return _compile_installer(stage, source, iscc, version, launch_args, logs)
        finally:
            source.rmdir()  # Remove only the junction, never the staged files.


def _compile_installer(stage: Path, source: Path, iscc: Path, version: str, launch_args: list[str], logs: Path) -> Path:
    size = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
    parameters = " ".join(launch_args).replace('"', '""')
    spanning = size > client_release.PART_BYTES - 8 * 1024**2
    launch_binary = "RabbitLands-updater.exe" if (stage / "RabbitLands-updater.exe").is_file() else "app\\RabbitLands.exe"
    launch_parameters = ('-- ' + parameters) if parameters else ''
    if launch_binary == "RabbitLands-updater.exe":
        launch_parameters = '-- --launch-only' + (' ' + parameters if parameters else '')
    script = f"""; Generated by godot-client/tools/package_client.py
[Setup]
AppId={INSTALLER_APP_ID.replace('{', '{{')}
AppName=Rabbit Lands
AppVersion={version}
AppPublisher=Rabbit Lands
DefaultDirName={{localappdata}}\\Programs\\RabbitLands
DefaultGroupName=Rabbit Lands
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupMutex={INSTALLER_MUTEX}
OutputDir={stage.parent}
OutputBaseFilename={stage.name}-setup
Compression=lzma2/fast
SolidCompression=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={{app}}\\app\\RabbitLands.exe
SetupIconFile={source}\\app\\assets\\branding\\rabbitlands-icon.ico
{"DiskSpanning=yes" + chr(10) + f"DiskSliceSize={client_release.PART_BYTES}" if spanning else ""}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the game data wholesale so files a newer build dropped
; do not linger.
Type: filesandordirs; Name: "{{app}}\\app"
Type: filesandordirs; Name: "{{app}}\\eloria-assets"

[Files]
Source: "{source}\\*"; DestDir: "{{app}}"; Excludes: "{MARKER}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{{group}}\\RabbitLands"; Filename: "{{app}}\\{launch_binary}"; Parameters: "{launch_parameters}"; WorkingDir: "{{app}}\\app"
Name: "{{group}}\\RabbitLands (debug console)"; Filename: "{{app}}\\RabbitLands (debug console).bat"; WorkingDir: "{{app}}\\app"; IconFilename: "{{app}}\\app\\RabbitLands.exe"
Name: "{{group}}\\RabbitLands (compatibility)"; Filename: "{{app}}\\RabbitLands (compatibility).bat"; WorkingDir: "{{app}}\\app"; IconFilename: "{{app}}\\app\\RabbitLands.exe"
Name: "{{group}}\\RabbitLands (safe mode)"; Filename: "{{app}}\\RabbitLands (safe mode).bat"; WorkingDir: "{{app}}\\app"; IconFilename: "{{app}}\\app\\RabbitLands.exe"
Name: "{{userdesktop}}\\RabbitLands"; Filename: "{{app}}\\{launch_binary}"; Parameters: "{launch_parameters}"; WorkingDir: "{{app}}\\app"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{launch_binary}"; Parameters: "{launch_parameters}"; WorkingDir: "{{app}}\\app"; Description: "Start Rabbit Lands"; Flags: nowait postinstall skipifsilent
"""
    iss = logs / "eloria.iss"
    iss.write_text(script, encoding="utf-8-sig")
    log("compiling installer" + (" (disk-spanned: setup exe + .bin slices)" if spanning else ""))
    with open(logs / "iscc.log", "w", encoding="utf-8", errors="replace") as handle:
        result = subprocess.run([str(iscc), str(iss)], stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise PackageError(f"ISCC failed; log: {logs / 'iscc.log'}")
    return stage.parent / f"{stage.name}-setup.exe"


def online_installer_space(payload: dict) -> int:
    """Extra free space (bytes) the online setup asks for: its peak disk use plus 512 MiB.

    Setup keeps its verified downloads in {tmp} until it exits, and its helper
    copies each part into the update cache, so the download is on disk twice.
    A schema-2 release then joins each multi-part package beside its parts (one
    package at a time, parts deleted afterwards) and only then unpacks into
    `.eloria-update-stage/`, which is renamed into place. The join and the
    unpacked files never coexist, so the peak adds the larger of the unpacked
    files and the largest joined package, not both (measured for UD-04i).
    Over an existing installation the per-file update (W2-UD-04) stages only
    changed members and moves the originals, so a fresh install is the worst
    case. Schema 1 keeps its original formula.
    """
    size, unpacked = int(payload["size"]), int(payload["unpacked_size"])
    if payload.get("schema") != 2:
        return unpacked + 2 * size + 512 * 1024**2
    joined = max((int(p["size"]) for p in payload["packages"] if len(p["parts"]) > 1), default=0)
    return 2 * size + max(unpacked, joined) + 512 * 1024**2


def online_installer_script(stage: Path, helper: Path, version: str,
                            launch_args: list[str], payload: dict) -> str:
    root_files = "\n".join(
        f'Source: "{path}"; DestDir: "{{app}}"; Flags: ignoreversion'
        for path in sorted(stage.iterdir()) if path.is_file() and path.name != MARKER)
    package_checks = ""
    if payload.get("schema") == 2:
        checks, queues = [], []
        for index, package in enumerate(payload["packages"]):
            lines = [f"function PackageCurrent{index}: Boolean;", "begin", "  Result := False;"]
            for entry in package["files"]:
                name = entry["path"].replace("/", "\\").replace("'", "''")
                lines.append(f"  if not InstalledFileMatches(ExpandConstant('{{app}}') + '\\{name}', '{entry['sha256']}') then Exit;")
            lines.extend(["  Result := True;", "end;"])
            checks.append("\n".join(lines))
            queues.append(f"  if not PackageCurrent{index} then begin")
            queues.extend(f"    DownloadPage.Add('{part['url']}', '{part['url'].rsplit('/', 1)[1]}', '{part['sha256']}');" for part in package["parts"])
            queues.append("  end;")
        package_checks = """function InstalledFileMatches(const Name, Hash: String): Boolean;
begin
  Result := False;
  if FileExists(Name) then begin
    try
      Result := CompareText(GetSHA256OfFile(Name), Hash) = 0;
    except
      Result := False;
    end;
  end;
end;
""" + "\n\n".join(checks)
        downloads = "\n".join(queues)
    else:
        downloads = "\n".join(
            f"  DownloadPage.Add('{part['url']}', '{part['url'].rsplit('/', 1)[1]}', '{part['sha256']}');"
            for part in payload["parts"])
    parameters = ("-- --launch-only " + " ".join(launch_args)).strip().replace('"', '""')
    space = online_installer_space(payload)
    return f'''[Setup]
AppId={INSTALLER_APP_ID.replace('{', '{{')}
AppName=Rabbit Lands
AppVersion={version}
AppPublisher=Rabbit Lands
DefaultDirName={{localappdata}}\\Programs\\RabbitLands
DefaultGroupName=Rabbit Lands
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupMutex={INSTALLER_MUTEX}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={stage.parent}
OutputBaseFilename={stage.name}-setup
Compression=lzma2/fast
SolidCompression=yes
ExtraDiskSpaceRequired={space}
SetupIconFile={stage}\\app\\assets\\branding\\rabbitlands-icon.ico
UninstallDisplayIcon={{app}}\\app\\RabbitLands.exe
InfoBeforeFile={stage.parent / (stage.name + '-online-install.txt')}

[Files]
Source: "{helper}"; Flags: dontcopy
{root_files}

[Icons]
Name: "{{group}}\\RabbitLands"; Filename: "{{app}}\\RabbitLands-updater.exe"; Parameters: "{parameters}"; WorkingDir: "{{app}}\\app"
Name: "{{group}}\\Uninstall Rabbit Lands"; Filename: "{{app}}\\RabbitLands-uninstall.exe"; WorkingDir: "{{app}}"
Name: "{{group}}\\RabbitLands (debug console)"; Filename: "{{app}}\\RabbitLands (debug console).bat"; WorkingDir: "{{app}}\\app"; IconFilename: "{{app}}\\app\\RabbitLands.exe"
Name: "{{group}}\\RabbitLands (compatibility)"; Filename: "{{app}}\\RabbitLands (compatibility).bat"; WorkingDir: "{{app}}\\app"; IconFilename: "{{app}}\\app\\RabbitLands.exe"
Name: "{{group}}\\RabbitLands (safe mode)"; Filename: "{{app}}\\RabbitLands (safe mode).bat"; WorkingDir: "{{app}}\\app"; IconFilename: "{{app}}\\app\\RabbitLands.exe"

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}\\app"
Type: filesandordirs; Name: "{{app}}\\eloria-assets"
Type: filesandordirs; Name: "{{app}}\\.eloria-previous"
Type: filesandordirs; Name: "{{app}}\\.eloria-update-stage"
Type: filesandordirs; Name: "{{app}}\\.eloria-update-backup"
Type: filesandordirs; Name: "{{app}}\\.rabbitlands-bootstrap-previous"
Type: files; Name: "{{app}}\\.rabbitlands-install.json"
Type: files; Name: "{{app}}\\.eloria-update-journal.json"
Type: files; Name: "{{app}}\\.eloria-update-journal-v2.json"
Type: files; Name: "{{app}}\\.eloria-update-journal*.tmp"

[Run]
Filename: "{{app}}\\RabbitLands-updater.exe"; Parameters: "{parameters}"; WorkingDir: "{{app}}\\app"; Description: "Start Rabbit Lands"; Flags: nowait postinstall skipifsilent

[Code]
var
  DownloadPage: TDownloadWizardPage;
  InstallPage: TOutputProgressWizardPage;
  InstallingPayload: Boolean;
  InstallError: String;

{package_checks}

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Downloading Rabbit Lands', 'Downloading and verifying the game files. An internet connection is required.', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  InstallPage := CreateOutputProgressPage('Installing Rabbit Lands',
    'Verifying and unpacking the downloaded game files.');
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if InstallingPayload then begin
    Cancel := False;
    Confirm := False;
  end;
end;

procedure InstallLog(const S: String; const Error, FirstLine: Boolean);
var
  Line, Message: String;
  Separator, Percent: Integer;
begin
  Log(S);
  if Pos('RL_ERROR|', S) = 1 then
    InstallError := Copy(S, 10, Length(S));
  if Pos('RL_PROGRESS|', S) <> 1 then Exit;
  Line := Copy(S, 13, Length(S));
  Separator := Pos('|', Line);
  if Separator = 0 then Exit;
  Percent := StrToIntDef(Copy(Line, 1, Separator - 1), -1);
  if (Percent < 0) or (Percent > 100) then Exit;
  Message := Copy(Line, Separator + 1, Length(Line));
  InstallPage.SetText(Message, 'Please keep setup open until this step finishes.');
  InstallPage.SetProgress(Percent, 100);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  CancelWasEnabled: Boolean;
begin
  Result := '';
  DownloadPage.Clear;
{downloads}
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
    except
      if DownloadPage.AbortedByUser then
        Result := 'The download was cancelled. Run setup again to continue.'
      else
        Result := GetExceptionMessage;
    end;
  finally
    DownloadPage.Hide;
  end;
  if Result <> '' then Exit;
  ExtractTemporaryFile('{helper.name}');
  ResultCode := -1;
  InstallError := '';
  InstallingPayload := True;
  CancelWasEnabled := WizardForm.CancelButton.Enabled;
  InstallPage.SetText('Starting game file verification...', 'Please keep setup open until this step finishes.');
  InstallPage.SetProgress(0, 100);
  InstallPage.Show;
  WizardForm.CancelButton.Enabled := False;
  try
    try
      if not ExecAndLogOutput(ExpandConstant('{{tmp}}\\{helper.name}'),
        ExpandConstant('--headless --log-file "{{tmp}}\\RabbitLands-install.log" -- --root "{{app}}" --parts "{{tmp}}"'),
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode, @InstallLog) or (ResultCode <> 0) then begin
        if InstallError <> '' then
          Result := InstallError
        else
          Result := ExpandConstant('The game files could not be installed. See {{tmp}}\\RabbitLands-install.log for details.');
      end;
    except
      Result := GetExceptionMessage;
    end;
  finally
    InstallPage.Hide;
    InstallingPayload := False;
    WizardForm.CancelButton.Enabled := CancelWasEnabled;
  end;
end;
'''


def make_online_installer(stage: Path, godot: Path, iscc: Path, version: str,
                           launch_args: list[str], logs: Path) -> Path:
    manifest = stage.parent / f"{stage.name}-windows.json"
    payload = json.loads(base64.b64decode(json.loads(manifest.read_text(encoding="utf-8"))["payload"], validate=True))
    metadata = json.loads((stage / "app/client-release.json").read_text(encoding="utf-8"))
    if payload["commit"] != metadata["commit"] or payload["platform"] != "windows":
        raise PackageError("The online installer manifest does not match the staged client.")
    base = f"https://github.com/{metadata['repository']}/releases/download/client-{metadata['commit']}/"
    import shared_release_assets as shared
    for part in payload["parts"]:
        name = part["url"].rsplit("/", 1)[-1]
        if (not part["url"].startswith(base) and not shared.matches(part, metadata["repository"])) or Path(name).name != name:
            raise PackageError("Unexpected online installer download URL.")
        path = stage.parent / name
        if STORAGE and STORAGE.part_matches(name, part):
            continue
        if path.stat().st_size != part["size"] or client_release.digest(path) != part["sha256"]:
            raise PackageError("An online installer download changed after signing.")
    helper = client_release.export_installer_helper(stage, godot, STORAGE.source if STORAGE else CLIENT,
                                                   EXPORT_PRESETS, run_godot, logs)
    (stage.parent / f"{stage.name}-online-install.txt").write_text(
        "Rabbit Lands will download and verify its game files during setup.\n\n"
        f"Download size: approximately {payload['size'] / 1024**3:.1f} GiB. An internet connection is required.\n"
        "You do not need to download the accompanying update files yourself.\n", encoding="utf-8")
    script = logs / "online-installer.iss"
    script.write_text(online_installer_script(stage, helper, version, launch_args, payload), encoding="utf-8-sig")
    log("compiling small online installer")
    with (logs / "iscc-online.log").open("w", encoding="utf-8", errors="replace") as output:
        result = subprocess.run([str(iscc), str(script)], stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise PackageError(f"Online installer compilation failed; see {logs / 'iscc-online.log'}")
    receipt = {"schema": 1, "mode": "online", "commit": metadata["commit"], "manifest": manifest.name,
               "parts": [{"name": part["url"].rsplit("/", 1)[1], "size": part["size"], "sha256": part["sha256"]}
                         for part in payload["parts"]]}
    (stage.parent / f"{stage.name}-setup-downloads.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return stage.parent / f"{stage.name}-setup.exe"


def _main(argv=None, storage=None) -> int:
    global BENCHMARK_LINKS, BENCHMARK_ACTOR_PLANS
    _LOOSE_READ_CACHE.clear()  # one build tree's commit per run
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--platform", choices=sorted(PLATFORMS), default="windows",
                        help="windows: folder + zip; linux: folder + tar.gz; macos: native app bundle")
    parser.add_argument("--distribution", choices=("github", "steam", "standalone"), default="github",
                        help="update owner: GitHub updater (default), Steam, or manual bundle replacement")
    parser.add_argument("--ref", default="origin/develop", help="commit to package (default origin/develop)")
    parser.add_argument("--no-fetch", action="store_true", help="do not fetch origin first")
    parser.add_argument("--godot", help="Godot console exe (default: the one in the client checkout)")
    parser.add_argument("--build-dir", type=Path, default=DIST / ".build" / "client-src",
                        help="persistent build worktree (default dist/.build/client-src)")
    parser.add_argument("--out", type=Path, default=DIST, help="output folder (default: workspace dist/ beside the client repository)")
    parser.add_argument("--server", help="bake HOST[:PORT] into the launchers instead of the login default")
    parser.add_argument("--force", action="store_true", help="replace an existing package for this commit")
    parser.add_argument("--no-smoke", action="store_true", help="skip the headless launch check")
    parser.add_argument("--online-installer", action="store_true", help="with --installer: small setup downloads signed game files")
    parser.add_argument("--no-vram-textures", action="store_true",
                        help="ship no VRAM-compressed texture sidecars, of maps, scenery or actors "
                             "(the client decodes every image)")
    actor_vram = parser.add_mutually_exclusive_group()
    actor_vram.add_argument("--actor-vram-textures", dest="actor_vram_textures", action="store_true", default=None,
                            help="also ship VRAM sidecars of the actor GLBs' embedded images (ACTOR_SIDECAR_DIRS); "
                                 "not release-enabled yet: a local package only")
    actor_vram.add_argument("--no-actor-vram-textures", dest="actor_vram_textures", action="store_false",
                            help="ship no actor VRAM sidecars")
    parser.add_argument("--vram-cache", type=Path, default=DIST / ".build" / "vram-cache",
                        help="encode cache for the sidecars (default dist/.build/vram-cache)")
    parser.add_argument("--no-zip", action="store_true", help="leave the folder unarchived")
    parser.add_argument("--benchmark-profile", action="store_true",
                        help="standalone local test export with allowlisted performance workloads")
    parser.add_argument("--client-runtime", type=Path,
                        help="optional verified native payload built from the selected commit")
    parser.add_argument("--prepared-catalog", type=Path,
                        help="optional exact native pilot generation; raw content remains present")
    parser.add_argument("--full-optimizations", action="store_true",
                        help="build and qualify the native runtime and fresh prepared pilot on native Windows/Linux")
    parser.add_argument("--native-runtime-cache", type=Path,
                        help="verified payload-only cache for full optimization builds")
    world_group = parser.add_mutually_exclusive_group()
    world_group.add_argument("--prepared-world", dest="prepared_world", action="store_true", default=None,
                             help="ship the complete lean geometry/collision/paving cache (native Windows/Linux default)")
    world_group.add_argument("--no-prepared-world", dest="prepared_world", action="store_false",
                             help="custom/local package only: retain raw fallback without shipping the world cache")
    parser.add_argument("--prepared-world-catalog", type=Path,
                        help="matching prebuilt complete world catalog instead of a native cook")
    parser.add_argument("--world-preparation-cache", type=Path,
                        help="persistent per-engine/producer world cache, independent of release revisions")
    parser.add_argument("--software-gpu-index", type=int,
                        help="optional Windows WARP index; default identifies system WARP by DXGI identity")
    parser.add_argument("--installer", action="store_true", help="also build an Inno Setup installer")
    parser.add_argument("--iscc", help="path to Inno Setup's ISCC.exe")
    parser.add_argument("--no-client-updates", action="store_true", help="build a client without the restart updater")
    parser.add_argument("--update-signing-key", type=Path, default=PROJECT / "work-output/client-updates/signing-private.pem",
                        help="private RSA signing key, never shipped")
    parser.add_argument("--update-public-key", type=Path, default=CLIENT / "data/update_public.pem")
    parser.add_argument("--github-repository", default="rabbitlandsgame/rabbitlands-client", help="public GitHub release repository (OWNER/REPO)")
    parser.add_argument("--release-build", action="store_true", help="mark an official release; normal local builds require manual updates")
    parser.add_argument("--shared-release-assets", action="store_true", help="reuse checksum-named packages in the shared downloads release")
    options = parser.parse_args(argv)

    started = time.time()
    platform = PLATFORMS[options.platform]
    try:
        want_prepared_world = (options.prepared_world if options.prepared_world is not None
                               else options.platform in {"windows", "linux"} or bool(options.prepared_world_catalog))
        if storage and options.platform in {"windows", "linux"} and not want_prepared_world:
            raise PackageError("Official runner builds require the complete prepared world cache.")
        if options.prepared_world_catalog and not want_prepared_world:
            raise PackageError("A prepared world catalog conflicts with --no-prepared-world.")
        if want_prepared_world and not options.prepared_world_catalog:
            native_platform = "windows" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else "macos"
            if options.platform not in {"windows", "linux"} or options.platform != native_platform:
                raise PackageError("World cooking requires native Windows/Linux; supply a matching --prepared-world-catalog "
                                   "or use --no-prepared-world for a custom package.")
        if options.benchmark_profile and (options.distribution != "standalone" or storage):
            raise PackageError("--benchmark-profile is a local standalone test export only")
        # These local packages are identity-verified before and after a run.
        # Hard links avoid copying several GB of unchanged raw assets into
        # every phase checkpoint. Normal distributable builds keep copying.
        BENCHMARK_LINKS = options.benchmark_profile
        BENCHMARK_ACTOR_PLANS = {} if options.benchmark_profile else None
        if options.full_optimizations and (options.platform not in {"windows", "linux"}
                or options.client_runtime or options.prepared_catalog or options.no_smoke
                or options.no_vram_textures or options.benchmark_profile):
            raise PackageError("Full optimization builds require native Windows/Linux, fresh generated payloads, VRAM and all qualification checks.")
        if options.prepared_catalog and (options.platform != "windows" or storage or options.distribution != "standalone"):
            raise PackageError("Prepared pilot currently requires a local standalone Windows package; release/storage/platform integrations remain unqualified.")
        updating = options.distribution == "github" and not options.no_client_updates
        if options.platform == "macos":
            if sys.platform != "darwin":
                raise PackageError("Build macOS on a Mac or the macOS Actions runner; native bundle validation is required.")
            if options.distribution == "github":
                raise PackageError("macOS currently uses --distribution steam or standalone (manual bundle replacement).")
            # Existing BC-only map sidecars are not portable across all Apple
            # GPUs. Universal exports include both desktop and mobile imports.
            options.no_vram_textures = True
        if options.distribution != "github" and (options.installer or options.online_installer):
            raise PackageError("Steam/standalone builds contain the full game; GitHub installers are a separate build.")
        if options.installer and options.platform != "windows":
            raise PackageError("--installer builds a Windows installer only")
        if options.online_installer and (not options.installer or options.no_client_updates):
            raise PackageError("--online-installer requires --installer and signed client updates")
        godot = find_godot(options.godot)
        if updating and (not options.update_signing_key.is_file() or not options.update_public_key.is_file()):
            raise PackageError("automatic updates need an RSA signing key pair; see docs/client-updates.md, or use --no-client-updates")
        iscc = find_iscc(options.iscc) if options.installer else None
        if options.installer and iscc is None:
            raise PackageError("--installer needs Inno Setup 6 (ISCC.exe); install it from "
                               "https://jrsoftware.org/isdl.php or pass --iscc")
        if not options.no_fetch and options.ref.startswith("origin/"):
            log("fetching origin")
            git("fetch", "-q", "origin")
        sha = git("rev-parse", "--verify", options.ref + "^{commit}").strip()
        stamp = datetime.date.today().strftime("%Y%m%d")
        version = f"{stamp}-{sha[:9]}"
        suffix = "" if options.distribution == "github" else "-" + options.distribution
        if options.benchmark_profile:
            suffix += "-benchmark"
        stage = options.out.resolve() / f"{platform['folder']}-{version}{suffix}"
        log(f"packaging {options.ref} = {sha[:9]} into {stage}")
        if stage.exists():
            if not options.force:
                raise PackageError(f"{stage} already exists; pass --force to rebuild it")
            if not (stage / MARKER).is_file():
                raise PackageError(f"{stage} was not made by this script; refusing to delete it")
            shutil.rmtree(stage)
        logs = options.out.resolve() / ".build" / "logs" / f"{options.platform}-{version}"
        logs.mkdir(parents=True, exist_ok=True)
        stage.mkdir(parents=True)
        (stage / MARKER).write_text(sha + "\n", encoding="utf-8")

        build_dir = options.build_dir.resolve()
        project = prepare_build_tree(build_dir, sha)
        if (project / "prepared-content").exists():
            raise PackageError("Disposable build has an old prepared-content directory; use a fresh build checkout to avoid unintended export.")
        # Decided before the import, so a request this commit or build cannot honour fails in seconds.
        actor_dirs = actor_sidecar_dirs(build_dir, options.actor_vram_textures, no_vram=options.no_vram_textures,
                                        release_build=options.release_build, runner=bool(storage))
        actor_receipt = None
        check_map_backgrounds(build_dir)
        optimization = None
        if options.full_optimizations:
            optimization = full_optimization_package.FullOptimizationBuild(project, stage, godot,
                options.platform, sha, logs / "optimizations",
                options.native_runtime_cache or options.out.resolve() / ".build/native-runtime-cache",
                storage.check if storage else None, software_gpu_index=options.software_gpu_index,
                native_bootstrap=getattr(storage, "native_bootstrap", None))
            options.client_runtime = optimization.prepare_native()
        if options.benchmark_profile:
            benchmark_package.prepare_export(project)
        if options.distribution != "github" and "const DISTRIBUTION_SCHEMA := 1" not in (project / "src/updates/release.gd").read_text(encoding="utf-8"):
            raise PackageError("The selected commit predates store-managed updates; select a commit containing the distribution support.")
        if options.platform == "macos":
            macos_package.prepare_import(project)
        if storage:
            storage.check("source ready", 1024**3)  # Allow imports/export scratch before starting Godot.
        metadata = client_release.identity(REPO, sha, options.platform,
                    # Read-only discovery still needs the public trust key in
                    # custom builds that omit the managed updater entirely.
                    options.update_public_key if options.update_public_key.is_file() else None,
                    options.github_repository, options.distribution, release_build=options.release_build)
        (project / "data/client_release.json").write_text(json.dumps(metadata), encoding="utf-8")
        previews = drop_preview_maps(build_dir)
        served = read_served_v2_packages(build_dir)
        # Capture every production leaf/scenery input while immutable source is
        # still complete. Protect only this exact closure during retirement.
        world_plan = release_world_preparation.capture(project) if want_prepared_world else None
        world_receipt = None
        asset_cache = getattr(storage, "asset_cache", None)
        if asset_cache:
            asset_cache.restore_imports(project)
        # Package-time actor transforms run on the build tree before the import,
        # in the wave-2 order (schedule 1.1 #6): the RL image strip first.
        strip_rl_head_stage(build_dir, logs, options.platform)
        import_project(godot, project, logs)
        if optimization:
            optimization.check_native()
        if storage:
            storage.check("import complete")
        check_actor_imports(project)
        check_scene_texture_imports(project)
        if storage and optimization:
            # Stage/prove map shipping before the first export reservation, so
            # warm import+graphics caches do not overlap unused map sources.
            warnings = stage_eloria_assets(build_dir, stage, previews, served)
            check_map_backgrounds(build_dir, stage)
            check_served_packages(stage, served)
            check_map_data_names_no_editor_sources(stage)
            check_registry(build_dir, stage)
            check_shared_meshes(build_dir, stage)
            protected = full_optimization_package.release_prepared_content.selected_source_inputs(project)
            if world_plan:
                protected.update(release_world_preparation.selected_source_inputs(project, world_plan))
            storage.retire_unstaged_maps(project, stage, sha, protected)
        if storage:
            storage.check("before export", 1_500_000_000)
        app_dir = stage / "app"
        export_project(godot, project, app_dir, logs, platform)
        stage_loose_client_files(build_dir, app_dir, options.platform)
        check_rl_head_strip_pack(build_dir, app_dir, logs, options.platform)
        if options.client_runtime:
            client_runtime_package.stage_payload(options.client_runtime.resolve(), build_dir, app_dir, options.platform)
        (app_dir / "client-release.json").write_text(json.dumps(metadata), encoding="utf-8")
        stage_audio_credits(app_dir, stage)
        if options.platform == "macos":
            check_actor_pack(build_dir, app_dir, "macos")
            check_scene_texture_pack(build_dir, app_dir, "macos")
        else:
            check_actor_pack(build_dir, app_dir)
            check_scene_texture_pack(build_dir, app_dir)
        check_editor_sources_unpacked(app_dir)
        check_world_import_pack(build_dir, app_dir)
        check_loose_duplicates(build_dir, app_dir, options.platform)
        if storage:
            storage.check("export and staging validated")
            if not optimization and not want_prepared_world:
                storage.clear_cache(project / ".godot")
            storage.check("export validated")
        if not (storage and optimization):
            warnings = stage_eloria_assets(build_dir, stage, previews, served)
            check_map_backgrounds(build_dir, stage)
            check_served_packages(stage, served)
            check_map_data_names_no_editor_sources(stage)
        check_loose_scenery_images(build_dir, stage)
        if not options.no_vram_textures:
            if storage:
                storage.check("before graphics encoding", 512 * 1024**2 if asset_cache and asset_cache.hit else 1024**3)
            stage_vram_textures(build_dir, stage, godot, options.vram_cache.resolve(), logs, app_dir=app_dir)
            if actor_dirs:
                if storage:
                    storage.check("before actor graphics encoding", ACTOR_ENCODE_ALLOWANCE_WARM
                                  if asset_cache and asset_cache.hit else ACTOR_ENCODE_ALLOWANCE)
                actor_receipt = stage_actor_vram_textures(build_dir, stage, godot, options.vram_cache.resolve(),
                                                          logs, app_dir, actor_dirs)
            check_vram_textures(stage)
            check_loose_vram_textures(app_dir)
            if actor_receipt is not None:
                actor_receipt["coverage"] = check_actor_vram_coverage(build_dir, app_dir, actor_dirs)
                (logs / "actor-vram-textures.json").write_text(json.dumps(actor_receipt, indent=2) + "\n",
                                                               encoding="utf-8")
            if storage:
                storage.clear_cache(options.vram_cache.resolve())
                storage.check("graphics prepared")
        if world_plan:
            world_receipt = release_world_preparation.prepare(project, stage, godot,
                platform=options.platform, plan=world_plan,
                cache_root=options.world_preparation_cache or options.out.resolve() / ".build/world-preparation-cache",
                work_root=logs / "world-preparation", check_budget=storage.check if storage else None,
                software_gpu_index=options.software_gpu_index, catalog_path=options.prepared_world_catalog,
                links=bool(storage))
            # The immutable native payloads live outside the PCK. Only the
            # small generated descriptor must be picked up by the final export.
            copy_file(project / release_world_preparation.DESCRIPTOR,
                      app_dir / release_world_preparation.DESCRIPTOR)
            log(f"prepared world: {world_receipt['targets']} targets, {world_receipt['bytes'] / 1e6:.1f} MB; "
                f"{world_receipt.get('prepared', 0)} cooked, {world_receipt.get('reused', 0)} reused")
        if optimization:
            options.prepared_catalog = optimization.prepare_content()
        if options.prepared_catalog:
            try:
                prepared_receipt = prepared_content_package.install_generation(
                    options.prepared_catalog.resolve(), project, stage, **({"link_payloads": True} if optimization else {}))
                # Two-pass pilot: final map/sidecar generation now exists.
                # Import/export only the newly copied native resources; retain
                # raw actor/map payloads and all ordinary package checks.
                (logs / "prepared").mkdir(parents=True, exist_ok=True)
                import_project(godot, project, logs / "prepared")
                if storage and optimization:
                    optimization.retire_intermediate_pck(prepared_receipt)
                export_project(godot, project, app_dir, logs / "prepared", platform)
                check_actor_pack(build_dir, app_dir)
                check_world_import_pack(build_dir, app_dir)
                check_loose_duplicates(build_dir, app_dir, options.platform)
                check_scene_texture_pack(build_dir, app_dir)
                check_editor_sources_unpacked(app_dir)
                prepared_receipt["export"] = prepared_content_package.check_export(
                    project / "prepared-content/index.json", stage)
                if optimization:
                    optimization.record_export(prepared_receipt)
                (logs / "prepared-content.json").write_text(json.dumps(prepared_receipt, indent=2), encoding="utf-8")
            except prepared_content_package.PreparedError as error:
                raise PackageError(str(error)) from error
        elif world_receipt:
            # Ordinary packages also need their actual exported descriptor;
            # world cooking never writes to an existing PCK in place.
            (logs / "prepared-world").mkdir(parents=True, exist_ok=True)
            import_project(godot, project, logs / "prepared-world")
            export_project(godot, project, app_dir, logs / "prepared-world", platform)
            check_actor_pack(build_dir, app_dir)
            check_world_import_pack(build_dir, app_dir)
            check_loose_duplicates(build_dir, app_dir, options.platform)
            check_scene_texture_pack(build_dir, app_dir)
            check_editor_sources_unpacked(app_dir)
        # Keep loose creatures as ordinary GLBs after native cooking. Optimized
        # meshes/curves are already smaller; avoid per-load RLCZ decoding.
        try:
            # Actor GLBs always ship loose. A scoped tracked-file list avoids
            # repeating the full actor/image dependency scan after cooking.
            creature_files = set(tracked(build_dir, creature_compression.CREATURE_ROOT.rstrip("/")))
            creature_receipt = creature_compression.stage(build_dir, app_dir, creature_files, compress=False)
        except creature_compression.PayloadError as error:
            raise PackageError(str(error)) from error
        (logs / "creature-compression.json").write_text(json.dumps(creature_receipt, indent=2), encoding="utf-8")
        log(f"creature GLBs: {creature_receipt['source_bytes'] / 1e9:.2f} GB -> "
            f"{creature_receipt['installed_bytes'] / 1e9:.2f} GB, ordinary uncompressed GLBs verified")
        if options.prepared_catalog:
            prepared_content_package.check_export(project / "prepared-content/index.json", stage)
        if world_receipt:
            world_receipt["export"] = release_world_preparation.check_export(project, stage, world_receipt,
                plan=world_plan, platform=options.platform)
            release_world_preparation.write_json(logs / "prepared-world.json", world_receipt)
            if storage:
                storage.world_preparation = world_receipt
        check_registry(build_dir, stage)
        check_map_background_export(build_dir, app_dir)
        check_glb_textures(app_dir)
        check_shared_meshes(build_dir, stage)
        if updating:
            client_release.export_launcher(stage, metadata, godot, project, EXPORT_PRESETS,
                                           platform["preset"], run_godot, logs,
                                           **({"cache": asset_cache.root / "helpers"} if asset_cache else {}))
        launch_args = ([] if options.platform == "macos" else
                       write_launchers(stage, options.server, build_dir, version, platform))
        if options.client_runtime:
            client_runtime_package.write_launchers(stage, options.platform)
        if options.distribution == "steam" and options.platform != "macos":
            (stage / "README.txt").write_text(
                "Rabbit Lands - Steam build\n"
                "Start and update the game through your Steam Library.\n"
                "To repair an installation, use Steam's Verify integrity of game files.\n"
                "Keep app/ and eloria-assets/ together. Player settings remain in user storage.\n",
                encoding="utf-8")
        if options.platform == "linux" and os.name != "nt":
            for script in stage.glob("RabbitLands*.sh"):
                script.chmod(0o755)
        actor_test = actor_receipt["selfTest"] if actor_receipt else None
        if actor_receipt is not None and actor_test is None:
            log("warning: no staged actor sidecar index lists a sidecar; the smoke launch self-tests none")
        if not options.no_smoke and options.platform != "macos":
            smoke_launch(app_dir, logs, platform, vram_textures=not options.no_vram_textures,
                         pool_test=pooled_sidecar_directory(stage), actor_test=actor_test,
                         **({"clean_feature_environment": True} if optimization else {}))
        if optimization:
            optimization.record_startup(logs / "smoke.log")
            smoke_launch(app_dir, logs, platform, vram_textures=not options.no_vram_textures,
                pool_test=pooled_sidecar_directory(stage), actor_test=actor_test, clean_feature_environment=True,
                optimization_profile="human-testing", log_name="smoke-human-testing.log")
            optimization.record_startup(logs / "smoke-human-testing.log", profile="human-testing")
            optimization.check_final_package()
            write_json = full_optimization_package.write_json
            write_json(logs / "optimization-proof.json", optimization.proof())
            if storage:
                storage.optimization_proof = optimization.proof()
                storage.clear_cache(project / ".godot")
                optimization.retire_prepared_sources()
                storage.check("full optimization package qualified before signing")

        if options.benchmark_profile:
            benchmark_package.write_manifest(stage, sha)

        outputs = [stage]
        if options.platform == "macos":
            macos_package.finish(stage, project, metadata)
            if not options.no_smoke:
                macos_package.smoke_binary(macos_package.bundle(stage) / "Contents/MacOS/RabbitLands",
                    stage, logs / "smoke-bundle.log", run_godot, SMOKE_FAILURES)
                subprocess.run(["codesign", "--verify", "--deep", "--strict", str(macos_package.bundle(stage))], check=True)
        if updating:
            outputs.extend(client_release.publish_artifacts(stage, metadata, options.update_signing_key,
                                                            godot, project, run_godot, logs,
                shared="partitioned" if STORAGE else options.shared_release_assets,
                **({"accept_part": storage.accept_part, "budget": storage.budget} if storage else {}),
                **({"previous_packages": storage.previous_packages, "reuse_package": storage.reuse_package}
                   if asset_cache else {})))
        if not options.no_zip:
            if options.platform == "macos":
                outputs.append(macos_package.archive(stage))
            elif storage:
                if options.platform != "linux":
                    raise PackageError("Runner Windows builds use the online installer, without an additional ZIP.")
                base = f"https://github.com/{metadata['repository']}/releases/download/client-{sha}"
                storage.linux_archive = make_tarball_parts(stage, platform, base, storage.accept_part, storage.budget)
            else:
                outputs.append(make_zip(stage) if options.platform == "windows" else make_tarball(stage, platform))
        if iscc:
            if storage:
                storage.check("before installer", 512 * 1024**2)
            outputs.append(make_online_installer(stage, godot, iscc, version, launch_args, logs)
                           if options.online_installer else make_installer(stage, iscc, version, launch_args, logs))
        # Last, and after the archive: a report on what the next
        # shared_meshes.py pass would still win, never a reason to fail here.
        report_duplicate_geometry(stage)
    except (PackageError, ValueError, subprocess.CalledProcessError) as error:
        log(f"FAILED: {error}")
        return 1

    for warning in warnings[:20]:
        log(f"warning: {warning}")
    if len(warnings) > 20:
        log(f"... {len(warnings) - 20} more warnings")
    log(f"done in {(time.time() - started) / 60:.1f} min; logs in {logs}")
    for output in outputs:
        if storage and not output.exists():
            log(f"  {output.name} uploaded and verified; local part released")
            continue
        size = (sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
                if output.is_dir() else output.stat().st_size)
        log(f"  {output}  ({size / 1e9:.2f} GB)")
    return 0


def main(argv=None, storage=None) -> int:
    global STORAGE, BENCHMARK_LINKS, BENCHMARK_ACTOR_PLANS
    previous = STORAGE
    previous_links = BENCHMARK_LINKS
    previous_actor_plans = BENCHMARK_ACTOR_PLANS
    STORAGE = storage
    BENCHMARK_ACTOR_PLANS = None
    try:
        return _main(argv, storage)
    finally:
        STORAGE = previous
        BENCHMARK_LINKS = previous_links
        BENCHMARK_ACTOR_PLANS = previous_actor_plans


if __name__ == "__main__":
    sys.exit(main())
