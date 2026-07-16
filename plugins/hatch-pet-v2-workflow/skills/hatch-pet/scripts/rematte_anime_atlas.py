#!/usr/bin/env python3
"""Rematte a Codex pet atlas with isnet-anime and dark-hair edge cleanup."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

try:
    from scipy.ndimage import distance_transform_edt
except ModuleNotFoundError:  # The isolated rembg[cpu] runtime supplies scipy.
    distance_transform_edt = None

CELL_WIDTH = 192
CELL_HEIGHT = 208
# V2 also stores the neutral look frame in idle row column 6.
USED_COUNTS = (7, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)
ALGORITHM = "isnet-anime-neutral-rematte-v1"


def save_image(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".webp":
        image.save(path, format="WEBP", lossless=True, quality=100, method=6, exact=True)
    else:
        image.save(path)


def parse_cells(value: str | None) -> set[tuple[int, int]] | None:
    if not value:
        return None
    result: set[tuple[int, int]] = set()
    for item in value.split(","):
        item = item.strip().lower()
        if not item.startswith("r") or "c" not in item:
            raise ValueError(f"invalid cell {item!r}; expected r0c0,r1c2")
        row_text, column_text = item[1:].split("c", 1)
        result.add((int(row_text), int(column_text)))
    return result


def premultiplied_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize RGBA without pulling hidden RGB into translucent edge pixels."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    alpha = rgba[..., 3:4]
    premultiplied = np.concatenate((rgba[..., :3] * alpha, alpha), axis=2)
    channels = [
        np.asarray(
            Image.fromarray(np.clip(premultiplied[..., index] * 255, 0, 255).astype(np.uint8)).resize(
                size, Image.Resampling.LANCZOS
            ),
            dtype=np.float32,
        )
        / 255.0
        for index in range(4)
    ]
    resized = np.stack(channels, axis=2)
    out_alpha = resized[..., 3:4]
    out_rgb = np.divide(
        resized[..., :3],
        np.maximum(out_alpha, 1 / 255),
        out=np.zeros_like(resized[..., :3]),
        where=out_alpha > 0,
    )
    output = np.concatenate((np.clip(out_rgb, 0, 1), np.clip(out_alpha, 0, 1)), axis=2)
    output[out_alpha[..., 0] <= 0] = 0
    return Image.fromarray(np.rint(output * 255).astype(np.uint8), "RGBA")


def clean_dark_boundary(
    image: Image.Image,
    *,
    boundary_radius: float = 6.5,
    dark_distance: float = 10.0,
    dark_luma: float = 90.0,
    opaque_alpha: int = 220,
) -> tuple[Image.Image, int]:
    """Recolor only boundaries whose nearest opaque interior is dark hair."""
    if distance_transform_edt is None:
        raise RuntimeError("scipy is required; install and run this script with rembg[cpu]")
    data = np.array(image.convert("RGBA"), dtype=np.uint8)
    rgb = data[..., :3]
    alpha = data[..., 3]
    visible = alpha > 0
    if not visible.any():
        return Image.fromarray(data, "RGBA"), 0

    interior_distance = distance_transform_edt(visible)
    boundary = visible & (interior_distance <= boundary_radius)
    luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    # Do not let an opaque sticker/chroma rim classify itself as light interior.
    # The nearest class must come from pixels safely inside the silhouette.
    interior = (alpha >= opaque_alpha) & (interior_distance > boundary_radius)
    dark = interior & (luma < dark_luma)
    light = interior & ~dark
    if not dark.any() or not light.any():
        return Image.fromarray(data, "RGBA"), 0

    dark_distance_map, dark_indices = distance_transform_edt(~dark, return_indices=True)
    light_distance_map = distance_transform_edt(~light)
    _, interior_indices = distance_transform_edt(~interior, return_indices=True)
    green_fringe = (
        (rgb[..., 1].astype(np.int16) > rgb[..., 0].astype(np.int16) + 6)
        & (rgb[..., 1].astype(np.int16) > rgb[..., 2].astype(np.int16) + 6)
    )
    magenta_fringe = (
        (rgb[..., 0].astype(np.int16) > rgb[..., 1].astype(np.int16) + 10)
        & (rgb[..., 2].astype(np.int16) > rgb[..., 1].astype(np.int16) + 8)
    )
    chroma_candidates = visible & (green_fringe | magenta_fringe) & (
        boundary | (dark_distance_map <= 12)
    )
    chroma_near_dark = chroma_candidates & (dark_distance_map <= 12)
    nearest_interior = rgb[interior_indices[0], interior_indices[1]]
    data[..., :3][chroma_candidates] = nearest_interior[chroma_candidates]
    nearest_dark = rgb[dark_indices[0], dark_indices[1]]
    data[..., :3][chroma_near_dark] = nearest_dark[chroma_near_dark]

    candidates = (
        boundary
        & (dark_distance_map <= dark_distance)
        & (dark_distance_map + 0.35 < light_distance_map)
    )
    data[..., :3][candidates] = nearest_dark[candidates]
    data[alpha == 0] = 0
    changed = candidates | chroma_candidates
    return Image.fromarray(data, "RGBA"), int(changed.sum())


def rematte_cell(
    cell: Image.Image,
    *,
    session: object,
    upscale: int,
    background: tuple[int, int, int],
    alpha_matting: bool,
    foreground_threshold: int,
    background_threshold: int,
    erode_size: int,
) -> tuple[Image.Image, int]:
    from rembg import remove

    rgba = cell.convert("RGBA")
    if rgba.getchannel("A").getbbox() is None:
        return Image.new("RGBA", rgba.size), 0
    composite = Image.new("RGBA", rgba.size, (*background, 255))
    composite.alpha_composite(rgba)
    enlarged = composite.convert("RGB").resize(
        (rgba.width * upscale, rgba.height * upscale), Image.Resampling.LANCZOS
    )
    rematted = remove(
        enlarged,
        session=session,
        alpha_matting=alpha_matting,
        alpha_matting_foreground_threshold=foreground_threshold,
        alpha_matting_background_threshold=background_threshold,
        alpha_matting_erode_size=erode_size,
        post_process_mask=False,
    ).convert("RGBA")
    resized = premultiplied_resize(rematted, rgba.size)
    return clean_dark_boundary(resized)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", required=True)
    parser.add_argument("--webp-output")
    parser.add_argument("--json-out")
    parser.add_argument("--model", default="isnet-anime")
    parser.add_argument("--model-home")
    parser.add_argument("--upscale", type=int, default=4)
    parser.add_argument("--background", default="210,210,210")
    parser.add_argument("--cells", help="optional comma-separated cells such as r0c0,r4c2")
    parser.add_argument("--no-alpha-matting", action="store_true")
    parser.add_argument("--foreground-threshold", type=int, default=240)
    parser.add_argument("--background-threshold", type=int, default=10)
    parser.add_argument("--erode-size", type=int, default=3)
    args = parser.parse_args()

    if args.model_home:
        os.environ["U2NET_HOME"] = str(Path(args.model_home).expanduser().resolve())
    selected = parse_cells(args.cells)
    background = tuple(int(item) for item in args.background.split(","))
    if len(background) != 3 or any(not 0 <= item <= 255 for item in background):
        raise SystemExit("--background must be R,G,B with values from 0 to 255")

    input_path = Path(args.input).expanduser().resolve()
    with Image.open(input_path) as opened:
        source = opened.convert("RGBA")
    expected_size = (CELL_WIDTH * 8, CELL_HEIGHT * 11)
    if source.size != expected_size:
        raise SystemExit(f"expected v2 atlas {expected_size[0]}x{expected_size[1]}, got {source.size}")

    from rembg import new_session

    started = time.monotonic()
    session = new_session(args.model)
    output = Image.new("RGBA", source.size)
    processed: list[str] = []
    cleaned_by_cell: dict[str, int] = {}
    for row, used_count in enumerate(USED_COUNTS):
        for column in range(8):
            box = (
                column * CELL_WIDTH,
                row * CELL_HEIGHT,
                (column + 1) * CELL_WIDTH,
                (row + 1) * CELL_HEIGHT,
            )
            cell = source.crop(box)
            should_process = column < used_count and (selected is None or (row, column) in selected)
            if should_process:
                cell, changed = rematte_cell(
                    cell,
                    session=session,
                    upscale=args.upscale,
                    background=background,
                    alpha_matting=not args.no_alpha_matting,
                    foreground_threshold=args.foreground_threshold,
                    background_threshold=args.background_threshold,
                    erode_size=args.erode_size,
                )
                label = f"r{row}c{column}"
                processed.append(label)
                if changed:
                    cleaned_by_cell[label] = changed
            elif column >= used_count:
                cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT))
            output.alpha_composite(cell, (box[0], box[1]))

    output_data = np.array(output, dtype=np.uint8)
    output_data[output_data[..., 3] == 0] = 0
    output = Image.fromarray(output_data, "RGBA")
    save_image(output, Path(args.output).expanduser().resolve())
    if args.webp_output:
        save_image(output, Path(args.webp_output).expanduser().resolve())

    report = {
        "ok": True,
        "algorithm": ALGORITHM,
        "model": args.model,
        "processed_cells": processed,
        "processed_count": len(processed),
        "dark_boundary_pixels": sum(cleaned_by_cell.values()),
        "dark_boundary_by_cell": cleaned_by_cell,
        "settings": {
            "upscale": args.upscale,
            "background": background,
            "alpha_matting": not args.no_alpha_matting,
            "foreground_threshold": args.foreground_threshold,
            "background_threshold": args.background_threshold,
            "erode_size": args.erode_size,
        },
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    if args.json_out:
        report_path = Path(args.json_out).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
