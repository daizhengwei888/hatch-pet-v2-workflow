#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rematte_anime_atlas.py"
SPEC = importlib.util.spec_from_file_location("rematte_anime_atlas", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RematteAnimeAtlasTests(unittest.TestCase):
    def test_v2_neutral_look_cell_is_used(self) -> None:
        self.assertEqual(MODULE.USED_COUNTS[0], 7)

    def test_parse_cells(self) -> None:
        self.assertEqual(MODULE.parse_cells("r0c0,r4c2"), {(0, 0), (4, 2)})
        self.assertIsNone(MODULE.parse_cells(None))

    def test_premultiplied_resize_zeros_hidden_rgb(self) -> None:
        image = Image.new("RGBA", (4, 4), (255, 255, 255, 0))
        image.putpixel((1, 1), (20, 30, 40, 255))
        resized = MODULE.premultiplied_resize(image, (2, 2))
        data = np.array(resized)
        self.assertTrue(np.all(data[data[..., 3] == 0, :3] == 0))

    @unittest.skipIf(MODULE.distance_transform_edt is None, "scipy is not installed")
    def test_dark_cleanup_does_not_recolor_nearer_light_edge(self) -> None:
        data = np.zeros((40, 48, 4), dtype=np.uint8)
        data[6:34, 4:20] = (20, 20, 24, 255)
        data[6:34, 28:44] = (240, 240, 240, 255)
        data[6:34, 3] = (220, 220, 220, 160)
        data[6:34, 44] = (220, 220, 220, 160)
        cleaned, changed = MODULE.clean_dark_boundary(Image.fromarray(data, "RGBA"))
        output = np.array(cleaned)
        self.assertGreater(changed, 0)
        self.assertLess(int(output[20, 3, :3].max()), 100)
        self.assertGreater(int(output[20, 44, :3].min()), 200)


if __name__ == "__main__":
    unittest.main()
