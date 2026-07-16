#!/usr/bin/env python3
"""Replace pale sticker halos beside dark hair with antialiased hair color."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageFilter

CELL_WIDTH = 192
CELL_HEIGHT = 208
ALGORITHM = "cell-local-dark-hair-halo-reconstruction"


def save_image(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".webp":
        image.save(path, format="WEBP", lossless=True, quality=100, method=6, exact=True)
    else:
        image.save(path)


def edge_band(alpha: Image.Image, radius: int) -> list[bool]:
    visible = [value > 0 for value in alpha.getdata()]
    transparent = Image.new("L", alpha.size)
    transparent.putdata([0 if value else 255 for value in visible])
    expanded = transparent.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    return [is_visible and nearby > 0 for is_visible, nearby in zip(visible, expanded.getdata())]


def dark_distance_masks(dark: Image.Image, radius: int) -> list[list[bool]]:
    previous = [value > 0 for value in dark.getdata()]
    masks: list[list[bool]] = []
    for distance in range(1, radius + 1):
        expanded = dark.filter(ImageFilter.MaxFilter(distance * 2 + 1))
        current = [value > 0 for value in expanded.getdata()]
        masks.append([value and not before for value, before in zip(current, previous)])
        previous = current
    return masks


def clean_cell(
    cell: Image.Image,
    *,
    edge_radius: int,
    hair_radius: int,
    pale_minimum: int,
    pale_spread: int,
    dark_maximum: int,
    minimum_dark_density: float,
    vertical_fraction: float,
    mode: str = "reconstruct",
    scope: str = "hair",
) -> tuple[Image.Image, int]:
    rgba = cell.convert("RGBA")
    pixels = list(rgba.getdata())
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return rgba, 0

    boundary = edge_band(alpha, edge_radius)
    dark_values = [
        255
        if pixel[3] >= 192
        and max(pixel[:3]) <= dark_maximum
        and sum(pixel[:3]) / 3 <= dark_maximum * 0.85
        else 0
        for pixel in pixels
    ]
    dark = Image.new("L", rgba.size)
    dark.putdata(dark_values)
    dark_density = list(dark.filter(ImageFilter.BoxBlur(hair_radius)).getdata())
    distance_masks = dark_distance_masks(dark, hair_radius)

    width, _ = rgba.size
    top_limit = bbox[1]
    bottom_limit = bbox[1] + round((bbox[3] - bbox[1]) * vertical_fraction)
    output = pixels.copy()
    changed = 0

    for index, pixel in enumerate(pixels):
        if pixel[3] == 0 or not boundary[index]:
            continue
        y = index // width
        if scope == "hair" and not top_limit <= y <= bottom_limit:
            continue
        rgb = pixel[:3]
        if min(rgb) < pale_minimum or max(rgb) - min(rgb) > pale_spread:
            continue

        if scope == "all-pale-edge":
            output[index] = (0, 0, 0, 0)
            changed += output[index] != pixel
            continue

        if dark_density[index] / 255 < minimum_dark_density:
            continue

        distance = next(
            (offset + 1 for offset, mask in enumerate(distance_masks) if mask[index]),
            None,
        )
        if distance is None:
            continue

        x = index % width
        references: list[tuple[int, int, int]] = []
        for neighbor_y in range(max(0, y - hair_radius), min(rgba.height, y + hair_radius + 1)):
            for neighbor_x in range(max(0, x - hair_radius), min(width, x + hair_radius + 1)):
                neighbor = neighbor_y * width + neighbor_x
                if dark_values[neighbor]:
                    references.append(pixels[neighbor][:3])
        if not references:
            continue

        if mode == "erase":
            output[index] = (0, 0, 0, 0)
        else:
            hair_color = tuple(
                round(sum(color[channel] for color in references) / len(references))
                for channel in range(3)
            )
            alpha_caps = (210, 145, 80, 32)
            alpha_cap = alpha_caps[min(distance - 1, len(alpha_caps) - 1)]
            output[index] = (*hair_color, min(pixel[3], alpha_cap))
        changed += output[index] != pixel

    output = [(0, 0, 0, 0) if pixel[3] == 0 else pixel for pixel in output]
    cleaned = Image.new("RGBA", rgba.size)
    cleaned.putdata(output)
    return cleaned, changed


def clean_atlas(image: Image.Image, **options: object) -> tuple[Image.Image, dict[str, object]]:
    rgba = image.convert("RGBA")
    if rgba.width % CELL_WIDTH or rgba.height % CELL_HEIGHT:
        raise ValueError("input dimensions must be divisible by 192x208")

    output = Image.new("RGBA", rgba.size)
    changed_by_cell: dict[str, int] = {}
    for row in range(rgba.height // CELL_HEIGHT):
        for column in range(rgba.width // CELL_WIDTH):
            box = (
                column * CELL_WIDTH,
                row * CELL_HEIGHT,
                (column + 1) * CELL_WIDTH,
                (row + 1) * CELL_HEIGHT,
            )
            cleaned, changed = clean_cell(rgba.crop(box), **options)
            output.alpha_composite(cleaned, (box[0], box[1]))
            if changed:
                changed_by_cell[f"r{row}c{column}"] = changed

    report = {
        "ok": True,
        "algorithm": ALGORITHM,
        "changed_pixels": sum(changed_by_cell.values()),
        "changed_cells": len(changed_by_cell),
        "changed_by_cell": changed_by_cell,
        "options": options,
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", required=True)
    parser.add_argument("--webp-output")
    parser.add_argument("--json-out")
    parser.add_argument("--edge-radius", type=int, default=3)
    parser.add_argument("--hair-radius", type=int, default=4)
    parser.add_argument("--pale-minimum", type=int, default=218)
    parser.add_argument("--pale-spread", type=int, default=28)
    parser.add_argument("--dark-maximum", type=int, default=105)
    parser.add_argument("--minimum-dark-density", type=float, default=0.16)
    parser.add_argument("--vertical-fraction", type=float, default=0.82)
    parser.add_argument("--mode", choices=("reconstruct", "erase"), default="reconstruct")
    parser.add_argument("--scope", choices=("hair", "all-pale-edge"), default="hair")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    options = {
        "edge_radius": args.edge_radius,
        "hair_radius": args.hair_radius,
        "pale_minimum": args.pale_minimum,
        "pale_spread": args.pale_spread,
        "dark_maximum": args.dark_maximum,
        "minimum_dark_density": args.minimum_dark_density,
        "vertical_fraction": args.vertical_fraction,
        "mode": args.mode,
        "scope": args.scope,
    }
    with Image.open(input_path) as opened:
        cleaned, report = clean_atlas(opened, **options)

    save_image(cleaned, Path(args.output).expanduser().resolve())
    if args.webp_output:
        save_image(cleaned, Path(args.webp_output).expanduser().resolve())
    if args.json_out:
        report_path = Path(args.json_out).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
