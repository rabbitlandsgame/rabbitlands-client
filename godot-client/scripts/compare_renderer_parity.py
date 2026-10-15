#!/usr/bin/env python3
"""Compare the paired deterministic crowd renderer captures.

This is an evidence summarizer, not a whole-game renderer-parity gate. It
verifies that both captures describe the same fixed fixture state, emits
per-region pixel statistics, and compares three unsaturated uses of the
production vertex-color shader against matched StandardMaterial controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops, ImageEnhance


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _srgb_encode(value: np.ndarray) -> np.ndarray:
    return np.where(
        value <= 0.0031308,
        value * 12.92,
        1.055 * np.power(np.maximum(value, 0.0), 1.0 / 2.4) - 0.055,
    )


def _srgb_decode(value: np.ndarray) -> np.ndarray:
    return np.where(
        value <= 0.04045,
        value / 12.92,
        np.power((np.maximum(value, 0.0) + 0.055) / 1.055, 2.4),
    )


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _round(values: np.ndarray | float) -> list[float] | float:
    if isinstance(values, np.ndarray):
        return [round(float(value), 6) for value in values]
    return round(float(values), 6)


def _load_capture(directory: Path) -> tuple[dict[str, Any], Image.Image, Path, Path]:
    metadata_path = directory / "renderer-parity.json"
    image_path = directory / "renderer-parity.png"
    if not metadata_path.is_file() or not image_path.is_file():
        raise ValueError(
            f"{directory} must contain renderer-parity.json and renderer-parity.png"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    image = Image.open(image_path).convert("RGB")
    return metadata, image, metadata_path, image_path


def _region_metrics(
    compatibility: np.ndarray, forward: np.ndarray, rectangle: list[int]
) -> dict[str, Any]:
    x, y, width, height = rectangle
    compat = compatibility[y : y + height, x : x + width]
    plus = forward[y : y + height, x : x + width]
    if compat.size == 0 or plus.size == 0:
        raise ValueError(f"empty region {rectangle}")
    compat_mean = compat.mean(axis=(0, 1))
    forward_mean = plus.mean(axis=(0, 1))
    delta = plus - compat
    identity_error = float(np.sqrt(np.mean((forward_mean - compat_mean) ** 2)))
    encoded_error = float(
        np.sqrt(np.mean((forward_mean - _srgb_encode(compat_mean)) ** 2))
    )
    changed = np.max(np.abs(delta), axis=2) > (1.0 / 255.0)
    return {
        "rectangle": rectangle,
        "compatibilityMeanRgb": _round(compat_mean),
        "forwardPlusMeanRgb": _round(forward_mean),
        "compatibilityMeanEncodedLuma": _round(_luminance(compat).mean()),
        "forwardPlusMeanEncodedLuma": _round(_luminance(plus).mean()),
        "meanRgbDelta": _round(delta.mean(axis=(0, 1))),
        "pixelRmse": _round(math.sqrt(float(np.mean(delta * delta)))),
        "changedPixelFraction": _round(changed.mean()),
        "meanIdentityError": _round(identity_error),
        "meanSrgbEncodingHypothesisError": _round(encoded_error),
        "meanCloserToSrgbEncoding": encoded_error < identity_error,
    }


def _probe_comparison(
    compatibility: np.ndarray,
    forward: np.ndarray,
    regions: dict[str, list[int]],
    definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    def compatibility_mean(rectangle: list[int]) -> np.ndarray:
        x, y, width, height = rectangle
        return compatibility[y : y + height, x : x + width].mean(axis=(0, 1))

    def forward_mean(rectangle: list[int]) -> np.ndarray:
        x, y, width, height = rectangle
        return forward[y : y + height, x : x + width].mean(axis=(0, 1))

    ground_rect = regions["ground"]
    compat_ground = compatibility_mean(ground_rect)
    forward_ground = forward_mean(ground_rect)

    def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
        return math.sqrt(float(np.mean((actual - predicted) ** 2)))

    probes: list[dict[str, Any]] = []
    for definition in definitions:
        standard_rect = regions[definition["standardRegion"]]
        vertex_rect = regions[definition["vertexRegion"]]
        compat_standard = compatibility_mean(standard_rect)
        compat_vertex = compatibility_mean(vertex_rect)
        forward_standard = forward_mean(standard_rect)
        forward_vertex = forward_mean(vertex_rect)
        source_rgba = np.asarray(definition["inputSrgb"], dtype=np.float64)
        source = source_rgba[:3]
        alpha = float(source_rgba[3])
        tolerance = float(definition["maximumChannelTolerance"])
        compat_delta = compat_vertex - compat_standard
        forward_delta = forward_vertex - forward_standard
        compat_max = float(np.max(np.abs(compat_delta)))
        forward_max = float(np.max(np.abs(forward_delta)))
        # Both probes use additive blending over the same controlled ground.
        # Compatibility blends encoded values. Forward+ blends in linear space
        # and encodes for display. The raw model records what the pre-fix shader
        # did; the decoded model is what StandardMaterial and the fixed shader do.
        compat_prediction = np.minimum(1.0, compat_ground + source * alpha)
        forward_decoded_prediction = _srgb_encode(
            _srgb_decode(forward_ground) + _srgb_decode(source) * alpha
        )
        forward_raw_prediction = _srgb_encode(
            _srgb_decode(forward_ground) + source * alpha
        )
        probes.append(
            {
                "id": definition["id"],
                "inputSrgb": _round(source_rgba),
                "maximumChannelTolerance": _round(tolerance),
                "compatibility": {
                    "standardMeanRgb": _round(compat_standard),
                    "vertexShaderMeanRgb": _round(compat_vertex),
                    "vertexMinusStandardRgb": _round(compat_delta),
                    "maximumAbsoluteRgbDelta": _round(compat_max),
                    "passed": compat_max <= tolerance,
                    "encodedAddPrediction": _round(compat_prediction),
                    "standardPredictionRmse": _round(
                        rmse(compat_standard, compat_prediction)
                    ),
                    "vertexPredictionRmse": _round(
                        rmse(compat_vertex, compat_prediction)
                    ),
                },
                "forwardPlus": {
                    "standardMeanRgb": _round(forward_standard),
                    "vertexShaderMeanRgb": _round(forward_vertex),
                    "vertexMinusStandardRgb": _round(forward_delta),
                    "maximumAbsoluteRgbDelta": _round(forward_max),
                    "passed": forward_max <= tolerance,
                    "decodedSrgbPrediction": _round(forward_decoded_prediction),
                    "standardDecodedPredictionRmse": _round(
                        rmse(forward_standard, forward_decoded_prediction)
                    ),
                    "vertexDecodedPredictionRmse": _round(
                        rmse(forward_vertex, forward_decoded_prediction)
                    ),
                    "preFixRawColorAsLinearPrediction": _round(forward_raw_prediction),
                    "vertexPreFixRawPredictionRmse": _round(
                        rmse(forward_vertex, forward_raw_prediction)
                    ),
                },
            }
        )
    all_passed = all(
        probe[renderer]["passed"]
        for probe in probes
        for renderer in ("compatibility", "forwardPlus")
    )
    return {
        "allRendererPairsPassed": all_passed,
        "probes": probes,
        "interpretation": (
            "All production vertex-color shader probes match their StandardMaterial "
            "controls in both renderers within the fixture tolerance."
            if all_passed
            else "At least one production vertex-color shader probe differs from its "
            "StandardMaterial control beyond the fixture tolerance."
        ),
    }


def _contact_sheet(
    compatibility: Image.Image, forward: Image.Image, destination: Path
) -> None:
    difference = ImageChops.difference(compatibility, forward)
    difference = ImageEnhance.Brightness(difference).enhance(4.0)
    width, height = compatibility.size
    sheet = Image.new("RGB", (width * 3, height), (0, 0, 0))
    sheet.paste(compatibility, (0, 0))
    sheet.paste(forward, (width, 0))
    sheet.paste(difference, (width * 2, 0))
    sheet.save(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compatibility", type=Path, required=True)
    parser.add_argument("--forward-plus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    compat_meta, compat_image, compat_meta_path, compat_image_path = _load_capture(
        arguments.compatibility
    )
    forward_meta, forward_image, forward_meta_path, forward_image_path = _load_capture(
        arguments.forward_plus
    )
    if compat_meta.get("actualRenderingMethod") != "gl_compatibility":
        raise ValueError("compatibility input did not run gl_compatibility")
    if forward_meta.get("actualRenderingMethod") != "forward_plus":
        raise ValueError("Forward+ input did not run forward_plus")
    for key in (
        "fixture",
        "fixtureVersion",
        "screenSize",
        "fixedState",
        "observedState",
        "regions",
        "colorProbeDefinitions",
    ):
        if compat_meta.get(key) != forward_meta.get(key):
            raise ValueError(f"fixture metadata differs for {key}")
    if compat_image.size != forward_image.size:
        raise ValueError("capture dimensions differ")

    compatibility = np.asarray(compat_image, dtype=np.float64) / 255.0
    forward = np.asarray(forward_image, dtype=np.float64) / 255.0
    regions = {
        name: _region_metrics(compatibility, forward, rectangle)
        for name, rectangle in compat_meta["regions"].items()
    }
    whole_frame = _region_metrics(
        compatibility,
        forward,
        [0, 0, compat_image.width, compat_image.height],
    )
    arguments.output.mkdir(parents=True, exist_ok=True)
    contact_sheet_path = arguments.output / "renderer-parity-contact-sheet.png"
    _contact_sheet(compat_image, forward_image, contact_sheet_path)
    report = {
        "schemaVersion": 3,
        "scope": (
            "Focused fixed-state comparison of representative crowd equipment, "
            "name/health overheads, energy flight/contact effects, ground, and "
            "matched StandardMaterial/vertex-color shader probes."
        ),
        "limitations": [
            "This does not establish whole-game renderer parity.",
            "Screenshot differences combine renderer color handling, lighting, "
            "tone mapping, blending, and rasterization.",
            "The isolated probes test this shader path; they do not validate other "
            "custom shaders or materials.",
        ],
        "fixedState": compat_meta["fixedState"],
        "adapter": compat_meta.get("videoAdapter", ""),
        "inputs": {
            "compatibility": {
                "metadata": str(compat_meta_path.resolve()),
                "metadataSha256": _sha256(compat_meta_path),
                "image": str(compat_image_path.resolve()),
                "imageSha256": _sha256(compat_image_path),
            },
            "forwardPlus": {
                "metadata": str(forward_meta_path.resolve()),
                "metadataSha256": _sha256(forward_meta_path),
                "image": str(forward_image_path.resolve()),
                "imageSha256": _sha256(forward_image_path),
            },
        },
        "wholeFrame": whole_frame,
        "regions": regions,
        "colorProbes": _probe_comparison(
            compatibility,
            forward,
            compat_meta["regions"],
            compat_meta["colorProbeDefinitions"],
        ),
        "contactSheet": str(contact_sheet_path.resolve()),
        "contactSheetColumns": ["Compatibility", "Forward+", "4x absolute difference"],
    }
    report_path = arguments.output / "renderer-parity-comparison.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
