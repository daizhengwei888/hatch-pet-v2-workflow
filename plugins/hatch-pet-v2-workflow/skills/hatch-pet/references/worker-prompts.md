# Lightweight Worker Contracts

Keep generation and visual QA in isolated lightweight workers. The parent should
read only aggregated previews and compact verdicts.

## Generation Worker

Give the worker:

- one job id;
- the exact prompt file;
- every input path and role from `imagegen-jobs.json`;
- the instruction to use `$imagegen` and return only the selected generated path
  plus one sentence of pet-size QA.

The worker must reject wrong frame count, cropped or overlapping poses, identity
drift, new props, text, guide marks, shadows, scenery, detached effects, or an
unreadable action. It does not assemble the atlas.

For a transport-level `Bad Request`, retry once with `retry_prompt_file` and the
same canonical base. Do not change image generation backend.

## Row QA Worker

Give the worker the row contact preview or GIF, state name, expected frame count,
and—only for row 4—the interaction preset/semantic override. Ask for:

```text
verdict=pass|fail
semantic=<one sentence>
identity=<one sentence>
repair=<none or smallest failing scope>
```

If row 4 has a reaction override, never fail it merely for lacking vertical
jump motion. Validate the configured preset from `reaction-presets.md`.

## Blind Direction Worker

Give each of three fresh isolated workers only
`qa/direction-blind-pairs.png`. Do not reveal degrees, labels, answer key,
labeled direction sheet, or another worker's verdict. Each worker classifies A
and B as `screen-left`, `screen-right`, `up`, `down`, or `ambiguous` for the axis
shown in that pair.

## Final Animation Worker

Give one independent worker:

- `qa/contact-sheet-extended.png`;
- all nine standard-row GIFs;
- `qa/look-directions.png`;
- the interaction config from `pet_request.json`.

Require a compact JSON verdict covering every standard row, the fixed clockwise
16-direction loop, identity/accessory continuity, cropping, unused transparency,
and forbidden effects. For row 4, apply legacy jump QA only when no semantic
override exists.
