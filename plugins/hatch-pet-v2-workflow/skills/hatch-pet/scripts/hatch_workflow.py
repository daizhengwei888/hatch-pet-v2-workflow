#!/usr/bin/env python3
"""Resume-safe family workflow for Codex v2 pet generation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


SKILL_DIR = Path(__file__).resolve().parents[1]
PREPARE = SKILL_DIR / "scripts" / "prepare_pet_run.py"
STATE_FILE = "hatch-workflow.json"
MAX_ATTEMPTS = 3
PASS_STATES = {"passed", "packaged"}
MECHANICAL_ROUTES = {
    "component": "repair-extraction",
    "extraction": "repair-extraction",
    "scale": "deterministic-registration",
    "baseline": "deterministic-registration",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path} must use JSON syntax (JSON is also valid YAML): {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain one object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_state(workspace: Path) -> tuple[Path, dict[str, Any]]:
    path = workspace.expanduser().resolve() / STATE_FILE
    if not path.is_file():
        raise SystemExit(f"workflow state not found: {path}")
    return path, read_json(path)


def slug(value: str) -> str:
    result = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", value.lower()))
    return result.strip("-")


def resolve_paths(values: list[str], base: Path) -> list[Path]:
    paths = []
    for value in values:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = base / path
        path = path.resolve()
        if not path.is_file():
            raise SystemExit(f"reference not found: {path}")
        paths.append(path)
    return paths


def prepare_variant(
    config: dict[str, Any], variant: dict[str, Any], run_dir: Path, config_dir: Path
) -> None:
    pet_id = slug(str(variant.get("id", "")))
    display_name = str(variant.get("displayName", pet_id)).strip()
    if not pet_id or not display_name:
        raise SystemExit("each variant requires id and displayName")

    references = resolve_paths(
        [
            *[str(value) for value in config.get("identityReferences", [])],
            *[str(value) for value in variant.get("references", [])],
        ],
        config_dir,
    )
    identity = str(config.get("identityContract", "")).strip()
    outfit = str(variant.get("outfit", "")).strip()
    notes = str(variant.get("petNotes", "")).strip()
    pet_notes = " ".join(
        part for part in (identity, f"Outfit: {outfit}." if outfit else "", notes) if part
    )

    command = [
        sys.executable,
        str(PREPARE),
        "--pet-name",
        display_name,
        "--pet-id",
        pet_id,
        "--display-name",
        display_name,
        "--description",
        str(variant.get("description", pet_notes)),
        "--pet-notes",
        pet_notes,
        "--output-dir",
        str(run_dir),
        "--style-preset",
        str(variant.get("stylePreset", config.get("stylePreset", "auto"))),
        "--style-notes",
        str(variant.get("styleNotes", config.get("styleNotes", ""))),
        "--chroma-key",
        str(variant.get("chromaKey", config.get("chromaKey", "auto"))),
        "--interaction-preset",
        str(variant.get("interactionPreset", "jump")),
    ]
    for reference in references:
        command.extend(["--reference", str(reference)])
    subprocess.run(command, check=True, capture_output=True, text=True)


def manifest_jobs(run_dir: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(run_dir / "imagegen-jobs.json")
    return {str(job["id"]): job for job in manifest["jobs"]}


def initialize(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config).expanduser().resolve()
    config = read_json(config_path)
    workspace = Path(args.workspace).expanduser().resolve()
    state_path = workspace / STATE_FILE
    if state_path.exists() and not args.force:
        raise SystemExit(f"workflow already exists: {state_path}")

    variants = config.get("variants")
    if not isinstance(variants, list) or not variants:
        raise SystemExit("family config requires a non-empty variants list")
    family_id = slug(str(config.get("familyId", "")))
    if not family_id:
        raise SystemExit("family config requires an ASCII familyId")

    workspace.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schemaVersion": 1,
        "familyId": family_id,
        "approvalMode": str(config.get("approvalMode", "base-and-reaction")),
        "qualityPreset": str(config.get("qualityPreset", "production")),
        "createdAt": now(),
        "updatedAt": now(),
        "workspace": str(workspace),
        "variants": {},
    }
    seen: set[str] = set()
    for raw_variant in variants:
        if not isinstance(raw_variant, dict):
            raise SystemExit("each variant must be an object")
        variant_id = slug(str(raw_variant.get("id", "")))
        if not variant_id or variant_id in seen:
            raise SystemExit(f"invalid or duplicate variant id: {variant_id!r}")
        seen.add(variant_id)
        run_dir = workspace / "runs" / variant_id
        if not (
            (run_dir / "pet_request.json").is_file()
            and (run_dir / "imagegen-jobs.json").is_file()
        ):
            prepare_variant(config, raw_variant, run_dir, config_path.parent)
        jobs = manifest_jobs(run_dir)
        state["variants"][variant_id] = {
            "id": variant_id,
            "displayName": str(raw_variant.get("displayName", variant_id)),
            "description": str(raw_variant.get("description", "")),
            "interactionPreset": str(raw_variant.get("interactionPreset", "jump")),
            "mirrorSafe": bool(raw_variant.get("mirrorSafe", False)),
            "approved": state["approvalMode"] != "base-and-reaction",
            "runDir": str(run_dir),
            "jobs": {
                job_id: {
                    "status": "pending",
                    "attempts": 0,
                    "maxAttempts": MAX_ATTEMPTS,
                }
                for job_id in jobs
            },
        }

    write_json(workspace / "family-config.json", config)
    write_json(state_path, state)
    return compact_status(state)


def dependencies_passed(variant: dict[str, Any], manifest_job: dict[str, Any]) -> bool:
    jobs = variant["jobs"]
    return all(jobs[dependency]["status"] in PASS_STATES for dependency in manifest_job["depends_on"])


def approval_allows(state: dict[str, Any], variant: dict[str, Any], job_id: str) -> bool:
    if state["approvalMode"] != "base-and-reaction" or variant["approved"]:
        return True
    base_passed = variant["jobs"]["base"]["status"] in PASS_STATES
    reaction_passed = variant["jobs"]["jumping"]["status"] in PASS_STATES
    if not base_passed:
        return job_id == "base"
    if not reaction_passed:
        return job_id == "jumping"
    return False


def missing_job_inputs(run_dir: Path, job: dict[str, Any]) -> list[str]:
    paths = [job["prompt_file"]]
    paths.extend(item["path"] for item in job.get("input_images", []))
    if job.get("look_mechanics_file"):
        paths.append(job["look_mechanics_file"])
    return [relative for relative in paths if not (run_dir / relative).is_file()]


def ready_jobs(state: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for variant_id, variant in state["variants"].items():
        run_dir = Path(variant["runDir"])
        manifest = manifest_jobs(run_dir)
        for job_id, job in variant["jobs"].items():
            if job["status"] not in {"pending", "retry", "repair"}:
                continue
            if not dependencies_passed(variant, manifest[job_id]):
                continue
            if not approval_allows(state, variant, job_id):
                continue
            source = manifest[job_id]
            missing = missing_job_inputs(run_dir, source)
            if missing:
                blocked.append({"variant": variant_id, "job": job_id, "missing": missing})
                continue
            ready.append(
                {
                    "variant": variant_id,
                    "job": job_id,
                    "attempt": job["attempts"] + 1,
                    "route": job.get("route", "generate"),
                    "prompt": str(Path(variant["runDir"]) / source["prompt_file"]),
                    "inputs": [
                        str(Path(variant["runDir"]) / item["path"])
                        for item in source.get("input_images", [])
                    ],
                    "output": str(Path(variant["runDir"]) / source["output_path"]),
                }
            )
            if len(ready) >= limit:
                return ready, blocked
    return ready, blocked


def descendants(manifest: dict[str, dict[str, Any]], root: str) -> set[str]:
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for job_id, job in manifest.items():
            if job_id in found or job_id == root:
                continue
            if root in job["depends_on"] or any(value in found for value in job["depends_on"]):
                found.add(job_id)
                changed = True
    return found


def invalidate_dependents(variant: dict[str, Any], job_id: str) -> list[str]:
    manifest = manifest_jobs(Path(variant["runDir"]))
    invalidated = sorted(descendants(manifest, job_id))
    for dependent in invalidated:
        if variant["jobs"][dependent]["status"] in PASS_STATES:
            variant["jobs"][dependent]["status"] = "pending"
            variant["jobs"][dependent]["invalidatedBy"] = job_id
    return invalidated


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_file(path: Path, label: str) -> str | None:
    if not path.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = path.parent / "backups" / f"{path.stem}.{label}-{stamp}{path.suffix}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    return str(backup)


def content_addressed_sprite_name(atlas: Path) -> str:
    return f"spritesheet-v2-{sha256(atlas)[:12]}.webp"


def copy_verified(source: Path, destination: Path, expected_hash: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        if sha256(temporary) != expected_hash:
            raise SystemExit(f"copied spritesheet hash mismatch: {destination}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def manifest_atlas_path(package_dir: Path, manifest: dict[str, Any]) -> Path:
    relative = manifest.get("spritesheetPath")
    if not isinstance(relative, str) or not relative.strip():
        raise SystemExit("pet.json requires a non-empty spritesheetPath")
    root = package_dir.resolve()
    atlas = (root / relative).resolve()
    try:
        atlas.relative_to(root)
    except ValueError as exc:
        raise SystemExit("pet.json spritesheetPath must stay inside the pet package") from exc
    if not atlas.is_file():
        raise SystemExit(f"packaged spritesheet not found: {atlas}")
    return atlas


def validate_v2_atlas(atlas: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts/validate_atlas.py"),
            str(atlas),
            "--require-v2",
            "--allow-chroma-leak",
            "--allow-chroma-fringe",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"installed atlas failed v2 validation: {detail}")


def sync_manifest_status(run_dir: Path, job_id: str, status: str) -> None:
    path = run_dir / "imagegen-jobs.json"
    manifest = read_json(path)
    for job in manifest["jobs"]:
        if job["id"] == job_id:
            job["status"] = status
            break
    write_json(path, manifest)


def record_success(args: argparse.Namespace) -> dict[str, Any]:
    state_path, state = load_state(Path(args.workspace))
    variant = state["variants"].get(args.variant)
    if variant is None or args.job not in variant["jobs"]:
        raise SystemExit("unknown variant or job")
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"generated source not found: {source}")

    run_dir = Path(variant["runDir"])
    manifest = manifest_jobs(run_dir)
    destination = run_dir / manifest[args.job]["output_path"]
    previous_hash = sha256(destination) if destination.is_file() else None
    new_hash = sha256(source)
    backup = backup_file(destination, "before-record")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source != destination:
        shutil.copy2(source, destination)
    if args.job == "base":
        canonical = run_dir / "references/canonical-base.png"
        backup_file(canonical, "before-record")
        shutil.copy2(destination, canonical)

    job = variant["jobs"][args.job]
    invalidated = invalidate_dependents(variant, args.job) if previous_hash not in {None, new_hash} else []
    job.update(
        {
            "status": "passed",
            "attempts": max(1, job["attempts"]),
            "sha256": new_hash,
            "recordedAt": now(),
        }
    )
    job.pop("route", None)
    job.pop("lastError", None)
    sync_manifest_status(run_dir, args.job, "complete")
    state["updatedAt"] = now()
    write_json(state_path, state)
    return {
        "ok": True,
        "variant": args.variant,
        "job": args.job,
        "output": str(destination),
        "backup": backup,
        "invalidated": invalidated,
    }


def record_failure(args: argparse.Namespace) -> dict[str, Any]:
    state_path, state = load_state(Path(args.workspace))
    variant = state["variants"].get(args.variant)
    if variant is None or args.job not in variant["jobs"]:
        raise SystemExit("unknown variant or job")
    job = variant["jobs"][args.job]
    if job["status"] in PASS_STATES:
        invalidate_dependents(variant, args.job)
    job["attempts"] += 1
    route = MECHANICAL_ROUTES.get(args.category, "regenerate")
    job.update({"route": route, "lastError": args.reason, "failedAt": now()})
    job["status"] = "blocked" if job["attempts"] >= job["maxAttempts"] else (
        "repair" if args.category in MECHANICAL_ROUTES else "retry"
    )
    sync_manifest_status(Path(variant["runDir"]), args.job, job["status"])
    state["updatedAt"] = now()
    write_json(state_path, state)
    return {
        "ok": job["status"] != "blocked",
        "variant": args.variant,
        "job": args.job,
        "status": job["status"],
        "attempts": job["attempts"],
        "route": route,
    }


def approve(args: argparse.Namespace) -> dict[str, Any]:
    state_path, state = load_state(Path(args.workspace))
    targets = list(state["variants"]) if args.variant == "all" else [args.variant]
    for variant_id in targets:
        variant = state["variants"].get(variant_id)
        if variant is None:
            raise SystemExit(f"unknown variant: {variant_id}")
        for required in ("base", "jumping"):
            if variant["jobs"][required]["status"] not in PASS_STATES:
                raise SystemExit(f"{variant_id} cannot be approved before {required} passes")
        variant["approved"] = True
        variant["approvedAt"] = now()
    state["updatedAt"] = now()
    write_json(state_path, state)
    return {"ok": True, "approved": targets}


def qa_gate(run_dir: Path) -> list[str]:
    errors: list[str] = []
    required = {
        "final/validation-extended.json": True,
        "qa/chroma-despill-extended.json": True,
        "qa/review.json": True,
        "qa/final-animation-qa.json": True,
        "qa/direction-semantics.json": True,
        "qa/cardinal-anchors.json": True,
        "qa/look-continuity.json": True,
    }
    for relative, expected in required.items():
        path = run_dir / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
            continue
        report = read_json(path)
        if report.get("ok") is not expected or report.get("errors"):
            errors.append(f"failed {relative}")
    blind = run_dir / "qa/direction-blind-validation.json"
    resolution = run_dir / "qa/blind-review-resolution.json"
    blind_ok = blind.is_file() and read_json(blind).get("ok") is True
    resolution_ok = resolution.is_file() and read_json(resolution).get("ok") is True
    if not (blind_ok or resolution_ok):
        errors.append("blind direction QA has neither a clean pass nor an accepted resolution")
    if not (run_dir / "final/spritesheet-extended.webp").is_file():
        errors.append("missing final/spritesheet-extended.webp")
    for relative in ("qa/contact-sheet-extended.png", "qa/look-directions.png"):
        if not (run_dir / relative).is_file():
            errors.append(f"missing {relative}")
    for state in (
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
        if not (run_dir / f"qa/previews/{state}.gif").is_file():
            errors.append(f"missing qa/previews/{state}.gif")
    return errors


def package(args: argparse.Namespace) -> dict[str, Any]:
    state_path, state = load_state(Path(args.workspace))
    variant = state["variants"].get(args.variant)
    if variant is None:
        raise SystemExit(f"unknown variant: {args.variant}")
    incomplete = [job_id for job_id, job in variant["jobs"].items() if job["status"] not in PASS_STATES]
    if incomplete:
        raise SystemExit(f"jobs are not complete: {', '.join(incomplete)}")
    run_dir = Path(variant["runDir"])
    request = read_json(run_dir / "pet_request.json")
    subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts/validate_atlas.py"),
            str(run_dir / "final/spritesheet-extended.webp"),
            "--json-out",
            str(run_dir / "qa/package-validation.json"),
            "--chroma-key",
            str(request["chroma_key"]["hex"]),
            "--require-v2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    errors = qa_gate(run_dir)
    if errors:
        raise SystemExit("package blocked: " + "; ".join(errors))

    pets_root = Path(args.pets_root).expanduser().resolve()
    destination = pets_root / args.variant
    destination.mkdir(parents=True, exist_ok=True)
    existing_manifest_path = destination / "pet.json"
    existing_atlas = None
    if existing_manifest_path.is_file():
        try:
            existing_atlas = manifest_atlas_path(
                destination, read_json(existing_manifest_path)
            )
        except SystemExit:
            existing_atlas = None
    elif (destination / "spritesheet.webp").is_file():
        existing_atlas = destination / "spritesheet.webp"
    backups = [
        value
        for value in (
            backup_file(existing_atlas, "before-package") if existing_atlas else None,
            backup_file(existing_manifest_path, "before-package"),
        )
        if value
    ]
    source_atlas = run_dir / "final/spritesheet-extended.webp"
    atlas_name = content_addressed_sprite_name(source_atlas)
    installed_atlas = destination / atlas_name
    source_hash = sha256(source_atlas)
    if not installed_atlas.is_file() or sha256(installed_atlas) != source_hash:
        copy_verified(source_atlas, installed_atlas, source_hash)
    manifest = {
        "id": args.variant,
        "displayName": variant["displayName"],
        "description": variant["description"] or request.get("description", ""),
        "spriteVersionNumber": 2,
        "spritesheetPath": atlas_name,
    }
    write_json(destination / "pet.json", manifest)
    variant["packagedAt"] = now()
    variant["packageDir"] = str(destination)
    for job in variant["jobs"].values():
        if job["status"] == "passed":
            job["status"] = "packaged"
    state["updatedAt"] = now()
    write_json(state_path, state)
    return {
        "ok": True,
        "package": str(destination),
        "spritesheet": str(installed_atlas),
        "sha256": source_hash,
        "backups": backups,
    }


def refresh_install(args: argparse.Namespace) -> dict[str, Any]:
    pet_id = slug(args.pet_id)
    if not pet_id or pet_id != args.pet_id:
        raise SystemExit("--pet-id must be a lowercase ASCII kebab-case id")
    package_dir = Path(args.pets_root).expanduser().resolve() / pet_id
    manifest_path = package_dir / "pet.json"
    if not manifest_path.is_file():
        raise SystemExit(f"pet manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    if manifest.get("id") != pet_id:
        raise SystemExit("pet.json id does not match --pet-id")
    if manifest.get("spriteVersionNumber") != 2:
        raise SystemExit("cache refresh requires spriteVersionNumber: 2")

    current_atlas = manifest_atlas_path(package_dir, manifest)
    validate_v2_atlas(current_atlas)
    atlas_hash = sha256(current_atlas)
    base_name = content_addressed_sprite_name(current_atlas)
    atlas_name = base_name
    if args.force_new_path:
        index = 1
        while (package_dir / atlas_name).exists():
            atlas_name = base_name.removesuffix(".webp") + f"-r{index}.webp"
            index += 1
    refreshed_atlas = package_dir / atlas_name
    changed = manifest.get("spritesheetPath") != atlas_name
    target_backup = None
    if refreshed_atlas.is_file() and sha256(refreshed_atlas) != atlas_hash:
        target_backup = backup_file(refreshed_atlas, "before-cache-refresh")
    if not refreshed_atlas.is_file() or sha256(refreshed_atlas) != atlas_hash:
        copy_verified(current_atlas, refreshed_atlas, atlas_hash)

    manifest_backup = None
    if changed:
        manifest_backup = backup_file(manifest_path, "before-cache-refresh")
        manifest["spritesheetPath"] = atlas_name
        write_json(manifest_path, manifest)
    return {
        "ok": True,
        "changed": changed,
        "package": str(package_dir),
        "previousSpritesheet": str(current_atlas),
        "spritesheet": str(refreshed_atlas),
        "sha256": atlas_hash,
        "backups": [value for value in (target_backup, manifest_backup) if value],
        "restartRequired": changed,
    }


def compact_status(state: dict[str, Any]) -> dict[str, Any]:
    variants = {}
    for variant_id, variant in state["variants"].items():
        counts: dict[str, int] = {}
        for job in variant["jobs"].values():
            counts[job["status"]] = counts.get(job["status"], 0) + 1
        variants[variant_id] = {
            "approved": variant["approved"],
            "interactionPreset": variant["interactionPreset"],
            "jobs": counts,
            "packageDir": variant.get("packageDir"),
        }
    return {"ok": True, "familyId": state["familyId"], "variants": variants}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("config")
    init.add_argument("--workspace", required=True)
    init.add_argument("--force", action="store_true")
    for name in ("status", "ready"):
        command = commands.add_parser(name)
        command.add_argument("workspace")
        if name == "ready":
            command.add_argument("--limit", type=int, default=3)
    approval = commands.add_parser("approve")
    approval.add_argument("workspace")
    approval.add_argument("--variant", default="all")
    for name in ("record", "verify"):
        command = commands.add_parser(name)
        command.add_argument("workspace")
        command.add_argument("--variant", required=True)
        command.add_argument("--job", required=True)
        command.add_argument("--source", required=True)
    failure = commands.add_parser("fail")
    failure.add_argument("workspace")
    failure.add_argument("--variant", required=True)
    failure.add_argument("--job", required=True)
    failure.add_argument(
        "--category",
        choices=["identity", "action", "crop", "direction", *MECHANICAL_ROUTES],
        default="action",
    )
    failure.add_argument("--reason", required=True)
    install = commands.add_parser("package")
    install.add_argument("workspace")
    install.add_argument("--variant", required=True)
    install.add_argument("--pets-root", default="~/.codex/pets")
    refresh = commands.add_parser("refresh-install")
    refresh.add_argument("--pet-id", required=True)
    refresh.add_argument("--pets-root", default="~/.codex/pets")
    refresh.add_argument("--force-new-path", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "init":
        result = initialize(args)
    elif args.command == "status":
        _path, state = load_state(Path(args.workspace))
        result = compact_status(state)
    elif args.command == "ready":
        _path, state = load_state(Path(args.workspace))
        ready, blocked = ready_jobs(state, max(1, min(args.limit, 3)))
        result = {"ok": True, "jobs": ready, "blocked": blocked}
    elif args.command == "approve":
        result = approve(args)
    elif args.command in {"record", "verify"}:
        result = record_success(args)
    elif args.command == "fail":
        result = record_failure(args)
    elif args.command == "package":
        result = package(args)
    else:
        result = refresh_install(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
