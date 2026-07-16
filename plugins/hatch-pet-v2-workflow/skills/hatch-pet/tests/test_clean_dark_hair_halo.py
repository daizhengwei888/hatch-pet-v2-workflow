import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clean_dark_hair_halo.py"
SPEC = importlib.util.spec_from_file_location("clean_dark_hair_halo", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CleanDarkHairHaloTest(unittest.TestCase):
    def test_recolors_only_pale_boundary_next_to_dark_hair(self):
        atlas = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        draw = ImageDraw.Draw(atlas)
        draw.ellipse((40, 20, 150, 155), fill=(248, 248, 248, 255))
        draw.ellipse((44, 24, 146, 151), fill=(35, 28, 30, 255))
        draw.rectangle((70, 90, 120, 180), fill=(250, 250, 250, 255))

        cleaned, report = MODULE.clean_atlas(
            atlas,
            edge_radius=3,
            hair_radius=4,
            pale_minimum=218,
            pale_spread=28,
            dark_maximum=105,
            minimum_dark_density=0.16,
            vertical_fraction=0.82,
        )

        self.assertGreater(report["changed_pixels"], 0)
        self.assertLess(cleaned.getpixel((42, 80))[0], 218)
        self.assertEqual(cleaned.getpixel((95, 175)), (250, 250, 250, 255))

    def test_all_pale_edge_erases_boundary_but_preserves_white_interior(self):
        atlas = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        draw = ImageDraw.Draw(atlas)
        draw.rectangle((50, 50, 140, 170), fill=(250, 250, 250, 255))

        cleaned, report = MODULE.clean_atlas(
            atlas,
            edge_radius=2,
            hair_radius=4,
            pale_minimum=218,
            pale_spread=28,
            dark_maximum=105,
            minimum_dark_density=0.16,
            vertical_fraction=0.82,
            mode="erase",
            scope="all-pale-edge",
        )

        self.assertGreater(report["changed_pixels"], 0)
        self.assertEqual(cleaned.getpixel((50, 100)), (0, 0, 0, 0))
        self.assertEqual(cleaned.getpixel((95, 110)), (250, 250, 250, 255))


if __name__ == "__main__":
    unittest.main()
