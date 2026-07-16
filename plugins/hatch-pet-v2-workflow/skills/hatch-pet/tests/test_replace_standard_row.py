import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts/replace_standard_row.py"


class ReplaceStandardRowTest(unittest.TestCase):
    def test_replaces_only_requested_row_and_clears_unused_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.png"
            output = root / "output.png"
            frames = root / "frames/jumping"
            frames.mkdir(parents=True)
            atlas = Image.new("RGBA", (1536, 2288), (0, 0, 0, 0))
            for row in range(11):
                atlas.paste((row + 1, 20, 30, 255), (0, row * 208, 1536, (row + 1) * 208))
            atlas.save(source)
            for index in range(5):
                Image.new("RGBA", (192, 208), (100 + index, 80, 60, 255)).save(
                    frames / f"{index:02d}.png"
                )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--atlas",
                    str(source),
                    "--frames-root",
                    str(root / "frames"),
                    "--state",
                    "jumping",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            with Image.open(source) as before, Image.open(output) as after:
                before = before.convert("RGBA")
                after = after.convert("RGBA")
                for row in (*range(4), *range(5, 11)):
                    box = (0, row * 208, 1536, (row + 1) * 208)
                    self.assertEqual(before.crop(box).tobytes(), after.crop(box).tobytes())
                self.assertEqual(after.getpixel((0, 4 * 208)), (100, 80, 60, 255))
                self.assertEqual(after.getpixel((5 * 192, 4 * 208)), (0, 0, 0, 0))

    def test_can_take_cleaned_row_from_another_v2_atlas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.png"
            replacement = root / "replacement.png"
            output = root / "output.webp"
            Image.new("RGBA", (1536, 2288), (10, 20, 30, 255)).save(source)
            Image.new("RGBA", (1536, 2288), (90, 80, 70, 255)).save(replacement)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--atlas",
                    str(source),
                    "--row-source-atlas",
                    str(replacement),
                    "--state",
                    "jumping",
                    "--output",
                    str(root / "output.png"),
                    "--webp-output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            with Image.open(output) as after:
                after = after.convert("RGBA")
                self.assertEqual(after.getpixel((10, 3 * 208)), (10, 20, 30, 255))
                self.assertEqual(after.getpixel((10, 4 * 208)), (90, 80, 70, 255))


if __name__ == "__main__":
    unittest.main()
