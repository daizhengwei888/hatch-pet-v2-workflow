# Fast Family Workflow

Use `scripts/hatch_workflow.py` when one person or mascot has multiple outfits,
when the run must resume safely, or when token cost matters. The workflow owns
state and scheduling; existing image and atlas scripts still own deterministic
processing and validation.

## Family Config

Use JSON syntax. JSON is valid YAML, so the same object may use a `.yaml` suffix
when a surrounding tool expects one.

```json
{
  "schemaVersion": 1,
  "familyId": "mika",
  "identityReferences": ["/absolute/path/face-1.jpg"],
  "identityContract": "Same face shape, long black hair, proportions and sticker style.",
  "approvalMode": "base-and-reaction",
  "qualityPreset": "production",
  "stylePreset": "sticker",
  "variants": [
    {
      "id": "mika-garden",
      "displayName": "Mika Garden",
      "description": "A gentle garden-outfit desktop pet.",
      "outfit": "sun hat, cream top, sage skirt",
      "interactionPreset": "heart-cute"
    },
    {
      "id": "mika-street",
      "displayName": "Mika Street",
      "description": "A crisp streetwear desktop pet.",
      "outfit": "navy cap, thin glasses, charcoal streetwear",
      "interactionPreset": "cool"
    }
  ]
}
```

## Commands

Set `PYTHON` to the exact bundled runtime returned by
`codex_app__load_workspace_dependencies`.

```bash
"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" init family.json \
  --workspace /absolute/path/to/family-run

"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" ready \
  /absolute/path/to/family-run --limit 3

"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" verify \
  /absolute/path/to/family-run \
  --variant mika-garden --job base --source /absolute/generated.png

"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" fail \
  /absolute/path/to/family-run \
  --variant mika-garden --job jumping \
  --category action --reason "gesture is unreadable at pet size"

"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" approve \
  /absolute/path/to/family-run --variant mika-garden

"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" status \
  /absolute/path/to/family-run

"$PYTHON" "$SKILL_DIR/scripts/hatch_workflow.py" package \
  /absolute/path/to/family-run --variant mika-garden
```

`record` is an alias of `verify`. It copies the selected generated artifact,
stores SHA-256, creates the canonical base when appropriate, keeps overwrite
backups, and recursively invalidates already-passed descendants when an upstream
artifact changes.

## Scheduling Contract

- Before approval, each variant exposes only `base`, then `jumping`/reaction.
- One user confirmation approves face, outfit, and reaction. After approval,
  standard rows and cardinal anchors may proceed in parallel.
- At most three ready jobs are returned across the family.
- `look-row-9` waits for all standard rows plus approved cardinals.
- `look-row-10` additionally waits for row 9.
- State persists in `hatch-workflow.json`; `status` and `ready` are read-only.
- Existing prepared variant runs are reused when initialization resumes.

## Failure Routing

| Category | Route |
| --- | --- |
| `component`, `extraction` | deterministic extraction repair |
| `scale`, `baseline` | deterministic registration |
| `identity`, `action`, `crop`, `direction` | regenerate only that row/anchor scope |

For an existing validated v2 pet, replace one repaired standard row with
`scripts/replace_standard_row.py`; this preserves all other standard and
direction rows before the single final chroma/validation pass.

The third failed attempt blocks that job. Do not reset attempts silently. Change
strategy after the same root cause repeats twice.

## Package Gate

`package` requires every tracked job plus:

- `final/validation-extended.json` with `ok: true`;
- `qa/chroma-despill-extended.json` with `ok: true`;
- `qa/review.json`, `qa/final-animation-qa.json`, and
  `qa/direction-semantics.json` with `ok: true` and no errors;
- `qa/blind-review-resolution.json` with `ok: true`;
- `final/spritesheet-extended.webp`.

Installation preserves timestamped backups of any replaced pet files. The final
manifest remains the standard Codex v2 `pet.json`; workflow metadata never leaks
into it. `package` uses a content-addressed atlas filename to prevent stale app
cache reuse. For an already installed pet, use `refresh-install`; add
`--force-new-path` only when a hashed path itself remains cached.
