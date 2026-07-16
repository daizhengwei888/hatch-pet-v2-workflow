#!/usr/bin/env python3
"""Replace one standard row in an existing Codex v2 atlas without touching other rows."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_SIZE = (1536, 2288)
ROWS = {
    "idle": (0, 6),
    "running-right": (1, 8),
    "running-left": (2, 8),
    "waving": (3, 4),
    "jumping": (4, 5),
    "failed": (5, 8),
    "waiting": (6, 6),
    "running": (7, 6),
    "review": (8, 6),
}
IMAGE_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}


def frame_paths(root: Path, state: str, expected: int) -> list[Path]:
    directory = root / state
    paths = sorted(path for path in directory.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if len(paths) != expected:
        raise SystemExit(f"{state} requires {expected} frames, found {len(paths)}")
    return paths


def normalize(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    if rgba.size == (CELL_WIDTH, CELL_HEIGHT):
        return rgba
    rgba.thumbnail((CELL_WIDTH, CELL_HEIGHT), Image.Resampling.LANCZOS)
    cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    cell.alpha_composite(
        rgba,
        ((CELL_WIDTH - rgba.width) // 2, (CELL_HEIGHT - rgba.height) // 2),
    )
    return cell


def clear_transparent_rgb(image: Image.Image) -> Image.Image:
    data = bytearray(image.convert("RGBA").tobytes())
    for index in range(0, len(data), 4):
        if data[index + 3] == 0:
            data[index : index + 3] = b"\x00\x00\x00"
    return Image.frombytes("RGBA", image.size, bytes(data))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--frames-root")
    source.add_argument(
        "--row-source-atlas",
        help="Take the already-processed replacement cells from another v2 atlas.",
    )
    parser.add_argument("--state", required=True, choices=sorted(ROWS))
    parser.add_argument("--output", required=True)
    parser.add_argument("--webp-output")
    args = parser.parse_args()

    with Image.open(Path(args.atlas).expanduser().resolve()) as opened:
        atlas = opened.convert("RGBA")
    if atlas.size != ATLAS_SIZE:
        raise SystemExit(f"v2 atlas must be {ATLAS_SIZE[0]}x{ATLAS_SIZE[1]}; got {atlas.size}")

    row, expected = ROWS[args.state]
    top = row * CELL_HEIGHT
    atlas.paste((0, 0, 0, 0), (0, top, ATLAS_SIZE[0], top + CELL_HEIGHT))
    if args.row_source_atlas:
        with Image.open(Path(args.row_source_atlas).expanduser().resolve()) as opened:
            row_source = opened.convert("RGBA")
        if row_source.size != ATLAS_SIZE:
            raise SystemExit("replacement row source must also be a v2 atlas")
        frames = [
            row_source.crop(
                (
                    column * CELL_WIDTH,
                    top,
                    (column + 1) * CELL_WIDTH,
                    top + CELL_HEIGHT,
                )
            )
            for column in range(expected)
        ]
    else:
        frames = []
        for path in frame_paths(
            Path(args.frames_root).expanduser().resolve(), args.state, expected
        ):
            with Image.open(path) as opened:
                frames.append(normalize(opened))
    for column, frame in enumerate(frames):
        atlas.alpha_composite(frame, (column * CELL_WIDTH, top))
    atlas = clear_transparent_rgb(atlas)

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(output)
    if args.webp_output:
        webp = Path(args.webp_output).expanduser().resolve()
        webp.parent.mkdir(parents=True, exist_ok=True)
        atlas.save(webp, format="WEBP", lossless=True, quality=100, method=6, exact=True)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
