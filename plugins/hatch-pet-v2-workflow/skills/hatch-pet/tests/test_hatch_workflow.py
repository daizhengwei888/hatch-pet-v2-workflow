import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SKILL_DIR = Path(__file__).resolve().parents[1]
WORKFLOW = SKILL_DIR / "scripts/hatch_workflow.py"


class HatchWorkflowTest(unittest.TestCase):
    def command(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(WORKFLOW), *arguments],
            check=check,
            capture_output=True,
            text=True,
        )

    def initialize(self, root: Path) -> Path:
        config = {
            "schemaVersion": 1,
            "familyId": "workflow-test",
            "identityContract": "same round face and proportions",
            "approvalMode": "base-and-reaction",
            "qualityPreset": "production",
            "stylePreset": "sticker",
            "variants": [
                {
                    "id": "variant-a",
                    "displayName": "Variant A",
                    "outfit": "outfit A",
                    "interactionPreset": "heart-cute",
                },
                {
                    "id": "variant-b",
                    "displayName": "Variant B",
                    "outfit": "outfit B",
                    "interactionPreset": "cool",
                },
            ],
        }
        config_path = root / "family.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False))
        workspace = root / "workflow"
        self.command("init", str(config_path), "--workspace", str(workspace))
        return workspace

    def image(self, path: Path, color: str = "#334455") -> Path:
        Image.new("RGB", (256, 256), color).save(path)
        return path

    def v2_atlas(
        self, path: Path, color: tuple[int, int, int, int] = (30, 60, 90, 255)
    ) -> Path:
        atlas = Image.new("RGBA", (1536, 2288), (0, 0, 0, 0))
        draw = ImageDraw.Draw(atlas)
        counts = [7, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]
        for row, count in enumerate(counts):
            for column in range(count):
                left = column * 192 + 50
                top = row * 208 + 30
                draw.rectangle(
                    (left, top, left + 90, top + 150), fill=color
                )
        path.parent.mkdir(parents=True, exist_ok=True)
        atlas.save(path, format="WEBP", lossless=True, exact=True)
        return path

    def test_family_init_approval_gate_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = self.initialize(root)
            initial = json.loads(self.command("ready", str(workspace)).stdout)
            self.assertEqual({job["job"] for job in initial["jobs"]}, {"base"})
            self.assertLessEqual(len(initial["jobs"]), 3)

            source = self.image(root / "base.png")
            self.command(
                "record",
                str(workspace),
                "--variant",
                "variant-a",
                "--job",
                "base",
                "--source",
                str(source),
            )
            ready = json.loads(self.command("ready", str(workspace)).stdout)
            variant_jobs = [
                job["job"] for job in ready["jobs"] if job["variant"] == "variant-a"
            ]
            self.assertEqual(variant_jobs, ["jumping"])

            reaction = self.image(root / "reaction.png", "#556677")
            self.command(
                "verify",
                str(workspace),
                "--variant",
                "variant-a",
                "--job",
                "jumping",
                "--source",
                str(reaction),
            )
            ready = json.loads(self.command("ready", str(workspace)).stdout)
            self.assertFalse(
                any(job["variant"] == "variant-a" for job in ready["jobs"])
            )

            self.command("approve", str(workspace), "--variant", "variant-a")
            ready = json.loads(self.command("ready", str(workspace)).stdout)
            self.assertTrue(
                any(job["variant"] == "variant-a" for job in ready["jobs"])
            )

            state_before = (workspace / "hatch-workflow.json").read_text()
            status = json.loads(self.command("status", str(workspace)).stdout)
            self.assertEqual(status["familyId"], "workflow-test")
            self.assertEqual(state_before, (workspace / "hatch-workflow.json").read_text())

    def test_third_failure_blocks_and_mechanical_failure_routes_to_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.initialize(Path(temporary_directory))
            for attempt in range(1, 4):
                result = json.loads(
                    self.command(
                        "fail",
                        str(workspace),
                        "--variant",
                        "variant-a",
                        "--job",
                        "base",
                        "--category",
                        "extraction" if attempt == 1 else "identity",
                        "--reason",
                        f"attempt {attempt}",
                    ).stdout
                )
                if attempt == 1:
                    self.assertEqual(result["route"], "repair-extraction")
                    self.assertEqual(result["status"], "repair")
            self.assertEqual(result["status"], "blocked")
            ready = json.loads(self.command("ready", str(workspace)).stdout)
            self.assertFalse(
                any(job["variant"] == "variant-a" for job in ready["jobs"])
            )

    def test_replacing_passed_base_invalidates_dependents_and_keeps_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = self.initialize(root)
            first = self.image(root / "first.png", "#111111")
            second = self.image(root / "second.png", "#eeeeee")
            reaction = self.image(root / "reaction.png", "#555555")
            for job, source in (("base", first), ("jumping", reaction)):
                self.command(
                    "record",
                    str(workspace),
                    "--variant",
                    "variant-a",
                    "--job",
                    job,
                    "--source",
                    str(source),
                )
            result = json.loads(
                self.command(
                    "record",
                    str(workspace),
                    "--variant",
                    "variant-a",
                    "--job",
                    "base",
                    "--source",
                    str(second),
                ).stdout
            )
            state = json.loads((workspace / "hatch-workflow.json").read_text())

        self.assertTrue(result["backup"])
        self.assertIn("jumping", result["invalidated"])
        self.assertEqual(
            state["variants"]["variant-a"]["jobs"]["jumping"]["status"],
            "pending",
        )

    def test_package_revalidates_v2_and_requires_complete_qa(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = self.initialize(root)
            state_path = workspace / "hatch-workflow.json"
            state = json.loads(state_path.read_text())
            variant = state["variants"]["variant-a"]
            for job in variant["jobs"].values():
                job["status"] = "passed"
            variant["approved"] = True
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            run_dir = Path(variant["runDir"])

            final = run_dir / "final/spritesheet-extended.webp"
            self.v2_atlas(final)

            for relative in (
                "final/validation-extended.json",
                "qa/chroma-despill-extended.json",
                "qa/review.json",
                "qa/final-animation-qa.json",
                "qa/direction-semantics.json",
                "qa/cardinal-anchors.json",
                "qa/look-continuity.json",
                "qa/direction-blind-validation.json",
            ):
                path = run_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"ok": True, "errors": []}))
            for relative in ("qa/contact-sheet-extended.png", "qa/look-directions.png"):
                path = run_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (10, 10), "white").save(path)
            previews = run_dir / "qa/previews"
            previews.mkdir(parents=True, exist_ok=True)
            for name in (
                "idle",
                "running-right",
                "running-left",
                "waving",
                "jumping",
                "failed",
                "waiting",
                "running",
                "review",
            ):
                (previews / f"{name}.gif").write_bytes(b"GIF89a")

            pets_root = root / "pets"
            legacy_package = pets_root / "variant-a"
            legacy_package.mkdir(parents=True)
            (legacy_package / "pet.json").write_text(
                json.dumps(
                    {
                        "id": "variant-a",
                        "displayName": "Variant A",
                        "description": "broken old install",
                        "spriteVersionNumber": 2,
                        "spritesheetPath": "missing.webp",
                    },
                    ensure_ascii=False,
                )
            )
            completed = self.command(
                "package",
                str(workspace),
                "--variant",
                "variant-a",
                "--pets-root",
                str(pets_root),
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            manifest = json.loads((pets_root / "variant-a/pet.json").read_text())
            expected_hash = hashlib.sha256(final.read_bytes()).hexdigest()

        self.assertTrue(result["ok"])
        self.assertEqual(manifest["spriteVersionNumber"], 2)
        self.assertEqual(
            manifest["spritesheetPath"], f"spritesheet-v2-{expected_hash[:12]}.webp"
        )
        self.assertEqual(result["sha256"], expected_hash)

    def test_refresh_install_cache_busts_valid_v2_package_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "pets/variant-a"
            original = self.v2_atlas(
                package / "spritesheet.webp", color=(0, 255, 0, 255)
            )
            original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
            expected_target = package / f"spritesheet-v2-{original_hash[:12]}.webp"
            expected_target.write_bytes(b"stale-corrupt-cache")
            manifest_path = package / "pet.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "id": "variant-a",
                        "displayName": "Variant A",
                        "description": "test pet",
                        "spriteVersionNumber": 2,
                        "spritesheetPath": "spritesheet.webp",
                    },
                    ensure_ascii=False,
                )
            )

            first = json.loads(
                self.command(
                    "refresh-install",
                    "--pet-id",
                    "variant-a",
                    "--pets-root",
                    str(root / "pets"),
                ).stdout
            )
            refreshed_manifest = json.loads(manifest_path.read_text())
            refreshed = package / refreshed_manifest["spritesheetPath"]
            second = json.loads(
                self.command(
                    "refresh-install",
                    "--pet-id",
                    "variant-a",
                    "--pets-root",
                    str(root / "pets"),
                ).stdout
            )
            forced = json.loads(
                self.command(
                    "refresh-install",
                    "--pet-id",
                    "variant-a",
                    "--pets-root",
                    str(root / "pets"),
                    "--force-new-path",
                ).stdout
            )

            self.assertTrue(first["changed"])
            self.assertTrue(first["restartRequired"])
            self.assertTrue(first["backups"])
            self.assertTrue(original.is_file())
            self.assertTrue(refreshed.is_file())
            self.assertEqual(original.read_bytes(), refreshed.read_bytes())
            self.assertFalse(second["changed"])
            self.assertFalse(second["restartRequired"])
            self.assertTrue(forced["changed"])
            self.assertTrue(forced["restartRequired"])
            self.assertNotEqual(forced["spritesheet"], str(refreshed))
            self.assertTrue(Path(forced["spritesheet"]).is_file())

    def test_refresh_install_rejects_intermediate_eight_by_nine_atlas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "pets/variant-a"
            package.mkdir(parents=True)
            Image.new("RGBA", (1536, 1872), (0, 0, 0, 0)).save(
                package / "spritesheet.webp", format="WEBP", lossless=True, exact=True
            )
            manifest_path = package / "pet.json"
            original_manifest = {
                "id": "variant-a",
                "displayName": "Variant A",
                "description": "test pet",
                "spriteVersionNumber": 2,
                "spritesheetPath": "spritesheet.webp",
            }
            manifest_path.write_text(json.dumps(original_manifest, ensure_ascii=False))

            result = self.command(
                "refresh-install",
                "--pet-id",
                "variant-a",
                "--pets-root",
                str(root / "pets"),
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("failed v2 validation", result.stderr)
            self.assertEqual(json.loads(manifest_path.read_text()), original_manifest)

    def test_refresh_install_rejects_spritesheet_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "pets/variant-a"
            package.mkdir(parents=True)
            outside = self.v2_atlas(root / "outside.webp")
            manifest_path = package / "pet.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "id": "variant-a",
                        "displayName": "Variant A",
                        "description": "test pet",
                        "spriteVersionNumber": 2,
                        "spritesheetPath": "../../outside.webp",
                    },
                    ensure_ascii=False,
                )
            )
            before = hashlib.sha256(outside.read_bytes()).hexdigest()

            result = self.command(
                "refresh-install",
                "--pet-id",
                "variant-a",
                "--pets-root",
                str(root / "pets"),
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must stay inside", result.stderr)
            self.assertEqual(hashlib.sha256(outside.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
