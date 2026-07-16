import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
PREPARE = SKILL_DIR / "scripts" / "prepare_pet_run.py"


class ReactionPresetTest(unittest.TestCase):
    def prepare(self, root: Path, *extra: str) -> Path:
        run_dir = root / "run"
        subprocess.run(
            [
                sys.executable,
                str(PREPARE),
                "--pet-name",
                "Reaction Test",
                "--pet-notes",
                "a compact chibi person",
                "--output-dir",
                str(run_dir),
                *extra,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return run_dir

    def test_default_preserves_legacy_jump(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = self.prepare(Path(temporary_directory))
            request = json.loads((run_dir / "pet_request.json").read_text())
            prompt = (run_dir / "prompts/rows/jumping.md").read_text()
            jobs = json.loads((run_dir / "imagegen-jobs.json").read_text())["jobs"]
            jumping = next(job for job in jobs if job["id"] == "jumping")

        self.assertEqual(request["interaction"]["preset"], "jump")
        self.assertNotIn("semanticOverride", request["interaction"])
        self.assertIn("airborne peak", prompt)
        self.assertEqual(jumping["semantic_role"], "jumping")
        self.assertNotIn("semanticOverride", jumping)

    def test_heart_cute_uses_native_reaction_without_floating_heart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = self.prepare(
                Path(temporary_directory), "--interaction-preset", "heart-cute"
            )
            request = json.loads((run_dir / "pet_request.json").read_text())
            prompt = (run_dir / "prompts/rows/jumping.md").read_text()
            jobs = json.loads((run_dir / "imagegen-jobs.json").read_text())["jobs"]
            jumping = next(job for job in jobs if job["id"] == "jumping")

        self.assertEqual(request["interaction"]["target"], "native-pointer")
        self.assertEqual(
            request["interaction"]["semanticOverride"], {"jumping": "reaction"}
        )
        self.assertEqual(request["interaction"]["durations_ms"], [140, 140, 140, 140, 280])
        self.assertIn("form a clear heart with both hands at the chest", prompt)
        self.assertIn("never draw a detached or floating heart", prompt)
        self.assertIn("non-jumping pointer reaction", prompt)
        self.assertEqual(jumping["semantic_role"], "reaction")
        self.assertEqual(jumping["interaction_preset"], "heart-cute")
        self.assertEqual(jumping["semanticOverride"], {"jumping": "reaction"})

    def test_every_reaction_preset_updates_main_and_retry_prompts(self) -> None:
        for preset in ("heart-cute", "cute", "cool", "cheer", "surprise"):
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as temporary_directory:
                run_dir = self.prepare(
                    Path(temporary_directory), "--interaction-preset", preset
                )
                for prompt_path in (
                    run_dir / "prompts/rows/jumping.md",
                    run_dir / "prompts/row-retries/jumping.md",
                ):
                    prompt = prompt_path.read_text()
                    self.assertIn("semanticOverride", prompt)
                    self.assertIn("reaction", prompt)
                    self.assertIn("return", prompt.lower())

    def test_cardinals_and_standard_rows_can_start_together_after_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = self.prepare(Path(temporary_directory))
            jobs = json.loads((run_dir / "imagegen-jobs.json").read_text())["jobs"]
            by_id = {job["id"]: job for job in jobs}

        self.assertEqual(by_id["look-cardinals"]["depends_on"], ["base"])
        self.assertNotIn(
            "qa/contact-sheet.png",
            [image["path"] for image in by_id["look-cardinals"]["input_images"]],
        )
        self.assertIn("look-cardinals", by_id["look-row-9"]["depends_on"])
        self.assertIn("idle", by_id["look-row-9"]["depends_on"])
        self.assertIn("look-row-9", by_id["look-row-10"]["depends_on"])


if __name__ == "__main__":
    unittest.main()
