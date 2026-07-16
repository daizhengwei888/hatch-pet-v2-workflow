---
name: hatch-pet
description: Create, repair, validate, visually QA, and package Codex-compatible v2 animated pets from character art, generated images, company or prospect brand cues, or visual references. Use for new Codex pets, custom mascots, humanoid or non-pixel pets, multi-outfit pet families, native pointer reactions, existing-pet repair, and v1-to-v2 upgrades.
---

> Modified from OpenAI's Apache-2.0 `hatch-pet` skill. See the repository
> `NOTICE` file for upstream source and modification details.

# Hatch Pet

Create production-ready Codex v2 pets with nine standard animation states,
sixteen clockwise look directions, resumable generation, native row-4 reaction
presets, deterministic atlas processing, independent visual QA, and local
packaging.

## Read First

Before any task action:

1. Call `codex_app__load_workspace_dependencies`.
2. Set `PYTHON` to the exact returned Python executable. Do not substitute
   `python3`, `which python`, or another environment.
3. Use `$imagegen` for all generated or edited raster art. Read the imagegen
   skill completely before the first visual generation.
4. Use absolute paths for files and worker inputs.

Set `SKILL_DIR` to this skill folder's absolute path from the available-skills
catalog. Do not reconstruct it from `CODEX_HOME`; plugins run from an installed
cache and may not live under `~/.codex/skills`.

## Reference Routing

Read only the references needed for the task, but read each selected file fully:

- Always: `references/codex-pet-contract.md`,
  `references/animation-rows.md`, and `references/qa-rubric.md`.
- Multi-outfit, resumable, or low-token production:
  `references/fast-workflow.md`.
- Custom click/hover performance: `references/reaction-presets.md`.
- Subagents or isolated visual QA: `references/worker-prompts.md`.
- Brand-inspired pets: follow the brand-discovery section below, then record
  sources in the run.

## Hard Contract

Every newly created or upgraded pet must satisfy:

- v2 atlas: `1536x2288`, 8 columns × 11 rows, cell `192x208`;
- rows `0-8`: exact standard state ids and frame counts;
- rows `9-10`: all sixteen fixed clockwise look directions;
- `pet.json.spriteVersionNumber: 2`;
- used cells non-empty and unused standard-row cells fully transparent;
- one final chroma decontamination pass only after full 8×11 assembly;
- no crop, overlap, text, UI, guide marks, ground, shadow, speed lines,
  scenery, or detached effects;
- identity, face, proportions, style, palette, hair, costume, accessories, and
  props remain consistent at actual pet size.

Do not package the intermediate 8×9 atlas. Do not add run-only configuration to
the final `pet.json`.

## Native Pointer Reactions

Codex still plays atlas row 4 through its internal `jumping` state. This skill may
change the five cells' meaning without changing the row id or package format:

```text
--interaction-preset jump|heart-cute|cute|cool|cheer|surprise
```

- `jump` is the compatibility default and omits `semanticOverride`.
- Other presets write `semanticOverride: {jumping: reaction}` only to run
  metadata and generation jobs.
- Final `pet.json` stays standard v2.
- Native Codex repeats one fixed five-frame performance; this workflow cannot
  make each click randomly choose another action.

Validate row 4 using `references/reaction-presets.md`. Never require vertical
jump motion when a reaction override exists.

## Choose a Workflow

Use the family workflow by default when there are multiple outfits, a single
approval checkpoint, resumability, or a strict generation budget. Use the direct
single-pet workflow for one-off creation, targeted repair, or an existing run.

### Family / Fast Workflow

Create a JSON family config following `references/fast-workflow.md`, then:

```bash
"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" init /absolute/family.json \
  --workspace /absolute/family-run

"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" ready \
  /absolute/family-run --limit 3
```

The initial approval mode is `base-and-reaction`: generate each variant's base,
then row 4's reaction, show one aggregated confirmation sheet, approve once, and
continue. After approval, standard rows and cardinal anchors may proceed in
parallel. The workflow persists hashes, retries, dependency invalidation,
backups, approval, and package state.

Use `verify` after a selected output passes its immediate visual check:

```bash
"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" verify \
  /absolute/family-run \
  --variant <pet-id> --job <job-id> --source /absolute/generated.png
```

On failure, record one root category. Extraction/component and scale/baseline
failures route to deterministic repair; identity/action/crop/direction failures
regenerate only the failing scope. The third failed attempt blocks the job.

### Direct Single-Pet Workflow

```bash
"$PYTHON" "$SKILL_DIR/scripts/prepare_pet_run.py" \
  --pet-name "<Name>" \
  --pet-id "<ascii-id>" \
  --description "<one sentence>" \
  --reference /absolute/reference.png \
  --output-dir /absolute/run \
  --pet-notes "<identity and outfit contract>" \
  --style-preset sticker \
  --interaction-preset jump
```

Omit `--reference` for text-only original concepts. Add repeated references for
identity views. Do not use `--force` on a valid resumable run.

## Brand-Inspired Pets

Inspect official sources first. Record cited URLs, palette, mascot/icon cues,
product personality, and a drawable `avatar_seed`. Use broad public cues only;
do not copy protected logos, readable marks, UI screenshots, or private imagery.
Pass the brief with `--brand-name`, `--brand-brief`, repeated `--brand-source`,
and optionally `--brand-discovery-file`.

## Generation Scheduler

Read `imagegen-jobs.json`. A job is ready only when every `depends_on` job has
passed and all listed prompt/input files exist.

Generation order:

1. `base` first; copy it to both `decoded/base.png` and
   `references/canonical-base.png`.
2. With one-step approval enabled, generate `jumping`/reaction next.
3. After approval, keep up to three isolated generation workers active across
   independent standard rows and `look-cardinals`.
4. Generate `running-left` independently when hats, text-like asymmetric marks,
   prop handedness, lighting, or identity make mirroring unsafe. Otherwise use
   the provided framewise mirror script with explicit approval.
5. Generate row 9 only after all standard rows and the four cardinal anchors
   pass; generate row 10 only after row 9 passes registration and semantic QA.

Every worker receives only its current prompt file and the listed input images.
It returns the selected generated path and one sentence of QA. The parent reads
aggregated previews rather than opening every raw generation.

If image generation returns a transport-level `Bad Request`, retry that job once
with its `retry_prompt_file`, same canonical base, same frame count, and same
chroma key. Do not switch image backends.

## Immediate Standard-Row QA

After selecting a standard row, copy it to `decoded/<state>.png`, then run:

```bash
ROW_QA_DIR="$RUN_DIR/qa/rows/$JOB_ID"
"$PYTHON" "$SKILL_DIR/scripts/extract_strip_frames.py" \
  --decoded-dir "$RUN_DIR/decoded" \
  --output-dir "$ROW_QA_DIR/frames" \
  --states "$JOB_ID" --method auto

"$PYTHON" "$SKILL_DIR/scripts/inspect_frames.py" \
  --frames-root "$ROW_QA_DIR/frames" \
  --json-out "$ROW_QA_DIR/review.json" \
  --states "$JOB_ID" --require-components
```

If only component extraction fails and the source poses have stable slots, rerun
that row with `--method stable-slots` and inspect with
`--allow-stable-slots`. Chroma fringe is not a row-generation failure.

Immediate visual QA must confirm:

- exact frame count and one complete pose per slot;
- readable state action and real animation progression;
- stable identity, scale, baseline, costume, and attached accessories;
- no crop, overlap, extra limbs, new props, shadows, text, or detached effects;
- row 4 follows either jump semantics or its configured reaction preset.

Retry or repair only the failing row. If the same root cause repeats twice,
change strategy rather than paraphrasing the same prompt.

## Standard 8×9 Assembly

After all nine rows pass:

```bash
"$PYTHON" "$SKILL_DIR/scripts/extract_strip_frames.py" \
  --decoded-dir "$RUN_DIR/decoded" \
  --output-dir "$RUN_DIR/frames" --states all --method auto

"$PYTHON" "$SKILL_DIR/scripts/inspect_frames.py" \
  --frames-root "$RUN_DIR/frames" \
  --json-out "$RUN_DIR/qa/review.json" --require-components

"$PYTHON" "$SKILL_DIR/scripts/compose_atlas.py" \
  --frames-root "$RUN_DIR/frames" \
  --output "$RUN_DIR/final/spritesheet.png" \
  --webp-output "$RUN_DIR/final/spritesheet.webp"

"$PYTHON" "$SKILL_DIR/scripts/make_contact_sheet.py" \
  "$RUN_DIR/final/spritesheet.webp" \
  --output "$RUN_DIR/qa/contact-sheet.png"

"$PYTHON" "$SKILL_DIR/scripts/render_animation_previews.py" \
  --frames-root "$RUN_DIR/frames" --output-dir "$RUN_DIR/qa/previews"
```

Inspect the contact sheet and all GIFs. This atlas is QA evidence only and must
never be installed.

## Cardinal Anchors and Look Mechanics

Write `qa/look-mechanics.md` for this exact pet before direction generation:

- what stays planted;
- whether eyes, eyelids, head, neck, hair, ears, upper body, or prop leads;
- rigid versus flexible attachment behavior;
- how worn hats/glasses stay registered;
- how `000 up`, `090 screen-right`, `180 down`, and `270 screen-left` differ.

Humanoid pets should use eyes and eyelids first, then restrained head/neck and
upper-body follow-through. Do not stretch a face, slide replacement pupils, or
rotate the entire sprite.

Generate `look-cardinals`, then:

```bash
CHROMA_KEY=$(jq -r '.chroma_key.hex' "$RUN_DIR/pet_request.json")
"$PYTHON" "$SKILL_DIR/scripts/extract_cardinal_anchors.py" \
  --strip "$RUN_DIR/decoded/look-cardinals.png" \
  --output-dir "$RUN_DIR/decoded/look-anchors" \
  --chroma-key "$CHROMA_KEY" \
  --json-out "$RUN_DIR/qa/cardinal-anchors.json"

"$PYTHON" "$SKILL_DIR/scripts/compose_cardinal_anchor_strip.py" \
  --anchors-dir "$RUN_DIR/decoded/look-anchors" \
  --output "$RUN_DIR/decoded/look-anchors-approved.png"
```

Approve all four at normal pet size. A wrong or ambiguous cardinal is a hard
failure. Repair only that anchor, rebuild the approved strip, then continue.

## Look Rows

Direction order is fixed:

```text
row 9:  000, 022.5, 045, 067.5, 090, 112.5, 135, 157.5
row 10: 180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5
```

Generate each row as one coherent eight-pose family. Intermediate directions
interpolate between approved cardinal pose families. Keep body scale, lower-body
anchor, baseline, face construction, hair, accessories, materials, and prop
attachments continuous. Never patch a newly generated look row with isolated
replacement final cells.

Register and edge-check row 9 before generating row 10:

```bash
"$PYTHON" "$SKILL_DIR/scripts/assemble_extended_atlas.py" \
  --base-atlas "$RUN_DIR/final/spritesheet.webp" \
  --look-row-9 "$RUN_DIR/decoded/look-row-9.png" \
  --neutral-cell "$RUN_DIR/frames/idle/00.png" \
  --chroma-key "$CHROMA_KEY" --chroma-threshold 96 \
  --registered-row-output "$RUN_DIR/qa/look-row-9-registered.png" \
  --registration-manifest-output "$RUN_DIR/qa/look-row-9-registration.json"
```

Reject wrong quadrant, loop reversal, identity drift, scale pop, baseline jump,
broken attachment, whole-sprite rotation, replacement eyes, clipping, or a
visible seam. Intermediate blind ambiguity is a review warning only when labeled
normal-size review confirms the intended ordered loop.

## Final V2 Assembly and One Chroma Pass

```bash
"$PYTHON" "$SKILL_DIR/scripts/assemble_extended_atlas.py" \
  --base-atlas "$RUN_DIR/final/spritesheet.webp" \
  --registered-row-9 "$RUN_DIR/qa/look-row-9-registered.png" \
  --row-9-registration "$RUN_DIR/qa/look-row-9-registration.json" \
  --look-row-10 "$RUN_DIR/decoded/look-row-10.png" \
  --neutral-cell "$RUN_DIR/frames/idle/00.png" \
  --chroma-key "$CHROMA_KEY" --chroma-threshold 96 \
  --output "$RUN_DIR/final/spritesheet-extended.png" \
  --webp-output "$RUN_DIR/final/spritesheet-extended.webp" \
  --manifest-output "$RUN_DIR/final/spritesheet-extended.json"

"$PYTHON" "$SKILL_DIR/scripts/despill_chroma_edges.py" \
  "$RUN_DIR/final/spritesheet-extended.png" \
  --output "$RUN_DIR/final/spritesheet-extended.png" \
  --webp-output "$RUN_DIR/final/spritesheet-extended.webp" \
  --chroma-key "$CHROMA_KEY" \
  --json-out "$RUN_DIR/qa/chroma-despill-extended.json"

# Optional anime/chibi hair rematte when pale or chroma fringe remains.
# Set REMBG_PYTHON to an isolated Python with numpy, rembg, and its model runtime;
# otherwise skip this optional step.
"$REMBG_PYTHON" "$SKILL_DIR/scripts/rematte_anime_atlas.py" \
  "$RUN_DIR/final/spritesheet-extended.png" \
  --output "$RUN_DIR/final/spritesheet-extended.png" \
  --webp-output "$RUN_DIR/final/spritesheet-extended.webp" \
  --model-home ~/codex-outputs/hatch-pet-runtime/models \
  --json-out "$RUN_DIR/qa/rematte-report.json"

"$PYTHON" "$SKILL_DIR/scripts/validate_atlas.py" \
  "$RUN_DIR/final/spritesheet-extended.webp" \
  --json-out "$RUN_DIR/final/validation-extended.json" \
  --chroma-key "$CHROMA_KEY" --require-v2

"$PYTHON" "$SKILL_DIR/scripts/make_contact_sheet.py" \
  "$RUN_DIR/final/spritesheet-extended.webp" \
  --output "$RUN_DIR/qa/contact-sheet-extended.png"

"$PYTHON" "$SKILL_DIR/scripts/make_direction_qa_sheet.py" \
  "$RUN_DIR/final/spritesheet-extended.webp" \
  --output "$RUN_DIR/qa/look-directions.png"

"$PYTHON" "$SKILL_DIR/scripts/make_direction_blind_qa_sheet.py" \
  "$RUN_DIR/final/spritesheet-extended.webp" \
  --output "$RUN_DIR/qa/direction-blind-pairs.png" \
  --answer-key "$RUN_DIR/qa/direction-blind-answer-key.json"
```

The optional rematter uses neutral-background `isnet-anime` inference, alpha
matting, premultiplied downsampling, and nearest-interior dark-edge assignment.
Keep the pre-rematte atlas as a backup and inspect black, mid-gray, and white
composites. Reject colored fringe, lost accessories, missing hands, or a damaged
reaction silhouette.

Do not rerun the chroma pass after it reports `ok: true` and v2 validation passes.

## Independent QA

1. Give three fresh isolated workers only the blind-pairs sheet. Combine their
   per-cell majority, then validate against the hidden answer key with the
   existing direction consensus scripts.
2. Cardinals are hard gates. Intermediate uncertainty may be resolved only by
   labeled normal-size direction and continuity review.
3. Record sixteen labeled semantic verdicts in `qa/direction-semantics.json`.
4. Run adjacent continuity measurement and visually resolve any flagged snap,
   center/area jump, alpha hole, or closure break.
5. Give one separate final worker the extended contact sheet, nine GIFs,
   direction sheet, and row-4 interaction config. Save
   `qa/final-animation-qa.json`.

Use `references/worker-prompts.md` for compact worker contracts. A repair worker
must not approve its own result.

## Repair Policy

- Structural/extraction fault: use deterministic scripts first.
- Identity, action, crop, wrong direction, or broken attachment: regenerate the
  smallest packaging-eligible scope.
- Standard animation: one row.
- Cardinal: one anchor, then rebuild the cardinal strip.
- Look-direction failure: resynthesize the complete affected eight-frame row.
- Re-run all downstream assembly and QA after an upstream replacement.
- Preserve passing artifacts and timestamped backups.

### Installed Cache Repair

If a valid v2 pet is cropped, uses the wrong row count, or briefly loses body
parts only at app startup, treat it as a stale installed-atlas cache before
regenerating art. Validate the installed atlas and switch `pet.json` to a
content-addressed filename atomically:

```bash
"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" refresh-install \
  --pet-id <pet-id> --pets-root "${CODEX_HOME:-$HOME/.codex}/pets"
```

The command rejects v1 and intermediate 8×9 atlases, keeps the original atlas,
backs up the manifest, and is idempotent. Restart Codex only when its JSON result
reports `restartRequired: true`. If the app still reuses an already hashed path,
rerun with `--force-new-path` to allocate a never-before-used filename.

## Package

Install only after every deterministic and visual gate passes:

```text
${CODEX_HOME:-$HOME/.codex}/pets/<pet-id>/
├── pet.json
└── spritesheet-v2-<sha256-prefix>.webp
```

Required manifest:

```json
{
  "id": "pet-id",
  "displayName": "Pet Name",
  "description": "One short sentence.",
  "spriteVersionNumber": 2,
  "spritesheetPath": "spritesheet-v2-<sha256-prefix>.webp"
}
```

For family workflows, prefer the `package` command in
`references/fast-workflow.md`; it checks required QA and preserves replaced-file
backups. It installs a content-addressed atlas filename so an app restart cannot
reuse an older 8×9 or v1 binary under the same path. For direct runs, copy only
the validated extended WebP and standard manifest, then run `refresh-install`.
Never package prompts, workflow metadata, intermediate atlases, or chroma-key
strips.

After installation, tell the user the exact absolute path and enable via
`⌘K` → **Show pet**. If the custom list is stale, restart Codex.

## Done Criteria

Do not report completion until:

- both atlas and package contract validate;
- all nine state rows pass semantic motion QA;
- row 4 matches jump or its declared reaction preset at `192x208`;
- all sixteen directions, four cardinals, blind consensus, labeled semantics,
  continuity, and loop closure pass;
- `qa/review.json` has no errors;
- final chroma report is `ok: true`;
- independent final animation QA is `ok: true`;
- installed `pet.json` points to a content-addressed WebP matching the validated
  final artifact.
