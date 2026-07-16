# Native Pointer Reaction Presets

Codex still addresses atlas row 4 by the internal state id `jumping`. A custom
reaction changes only the visual and QA meaning of those five cells. Do not add
interaction fields to the final `pet.json`.

## Configuration

```json
{
  "interaction": {
    "target": "native-pointer",
    "preset": "heart-cute",
    "semanticOverride": {"jumping": "reaction"},
    "durations_ms": [140, 140, 140, 140, 280]
  }
}
```

`prepare_pet_run.py --interaction-preset <name>` writes this run metadata and
keeps the atlas row/state id as `jumping`. The default `jump` preset omits
`semanticOverride` and preserves legacy generation and QA.

## Presets

| Preset | Five-frame performance | Acceptance cue |
| --- | --- | --- |
| `heart-cute` | prepare → hands rise → chest hand-heart → head tilt and wink → return | heart is formed by or physically joined to hands/chest; never floats |
| `cute` | prepare → hands to cheeks → slight head tilt → blink and soft smile → return | readable from face and hands without symbols |
| `cool` | prepare → touch/tip hat → adjust glasses with slight upper-body turn → confident smile → return | worn accessories stay rigidly registered |
| `cheer` | prepare → compact energy pose → both hands cheer → bright smile → return | no confetti, stars, text, or locomotion jump |
| `surprise` | prepare → eyes widen → hands to cheeks → shy smile → return | no punctuation or detached effects |
| `jump` | anticipation → lift → airborne peak → descent → settle | vertical body motion with no ground shadow or dust |

All reactions use the existing native five-frame timing:

```text
140 ms → 140 ms → 140 ms → 140 ms → 280 ms
```

## QA Override

- If no `semanticOverride` key exists, validate row 4 as a jump.
- If `semanticOverride.jumping == reaction`, validate the configured preset.
- A reaction must read as preparation → peak gesture → return, not five near-static variants.
- First and fifth frames must connect naturally to idle.
- Preserve face, proportions, costume, hair, limbs, hats, glasses, and props.
- Keep reaction effects attached to the silhouette. Floating hearts, text, UI,
  speed lines, floor, shadow, dust, and detached decorations fail.
- At `192x208`, the action must be recognizable without its preset label.

Native Codex repeats one fixed row-4 performance. Random click selection needs a
future native event protocol or a separate runtime and is outside this skill.
