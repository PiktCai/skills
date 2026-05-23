---
name: transub
description: Transcribe local media, translate or polish subtitle files, repair subtitle text, and validate SRT/VTT/segments.json outputs with timestamp-safe workflows. Use when a user asks to create, convert, translate, refine, repair, QA, or export subtitles for audio/video files, especially when local ASR, exact timestamp preservation, glossary-aware translation, or subtitle readability checks are needed.
---

# Transub Subtitle Workflow

## Core Rule

Keep deterministic media, parsing, conversion, validation, and export in `scripts/subtitle_workflow.py`. Use the agent for judgment-heavy work: ASR correction, translation, style, terminology, readability, and final QA.

## Quick Start

Resolve the skill directory dynamically instead of assuming a fixed machine path:

```bash
SKILL_DIR=/path/to/transub
python "$SKILL_DIR/scripts/subtitle_workflow.py" doctor
python "$SKILL_DIR/scripts/subtitle_workflow.py" models
python "$SKILL_DIR/scripts/subtitle_workflow.py" validate input.srt
python "$SKILL_DIR/scripts/subtitle_workflow.py" audit input.srt --max-han-chars 20 --max-cps 20
python "$SKILL_DIR/scripts/subtitle_workflow.py" convert input.srt --output input.segments.json
python "$SKILL_DIR/scripts/subtitle_workflow.py" export input.segments.json --format vtt --output input.vtt
```

For transcription, prefer an existing Python environment that already has `faster-whisper`:

```bash
python "$SKILL_DIR/scripts/subtitle_workflow.py" doctor --probe
python "$SKILL_DIR/scripts/subtitle_workflow.py" models
```

If `doctor --probe` reports a usable interpreter, run transcription with that interpreter. If `models` reports cached variants, ask the user which model to use before choosing a default. Install with `uv` or allow model downloads only after checking existing environments/cached models and only when the user is comfortable adding the dependency:

```bash
uv run --with faster-whisper python "$SKILL_DIR/scripts/subtitle_workflow.py" transcribe input.mp4 --output-dir subtitles --model base --device cpu --language auto
```

The helper expects Python 3.10+, `ffmpeg` on `PATH`, and `faster-whisper` only for the `transcribe` command. `validate`, `convert`, `export`, and `doctor --probe` use only the Python standard library.

## Workflow

1. Classify the input:
   - media file: run `doctor --probe` and `models`; reuse an existing interpreter and cached model when available, ask the user to choose if multiple cached model variants exist, then `transcribe`
   - `.srt`, `.vtt`, or `.json`: run `validate`
   - edited JSON: run `export`, then validate the exported subtitle
2. Before text edits, convert SRT/VTT to `segments.json` when useful so every cue has an `index`, `start`, `end`, and `text`.
3. Before translation, build a global brief: source language, target language, style, recurring terms, names, invented concepts, and anything that must not be normalized.
4. If the subtitle file fits comfortably in context, translate or polish the whole file in one structured pass. If it is too large, use overlapping windows, not isolated batches: include the previous and next few cues as context, carry a live term/style ledger forward, and return JSON keyed by original cue IDs.
5. After any windowed work, run a full-file reconciliation pass. Fix terminology drift, tone drift, pronoun/name inconsistencies, and awkward joins at window boundaries before exporting.
6. Reconstruct the full segment list without changing indices or timestamps unless retiming/resegmentation was explicitly requested.
7. Validate and audit the final `segments.json` and exported `.srt`/`.vtt`.
8. Hand back file paths plus a short QA note. Do not paste full subtitle contents unless the user asks.

## Invariants

- Keep subtitle IDs stable during correction, translation, and polishing.
- Keep `start` and `end` timestamps unchanged unless the task is explicitly timing repair.
- Never merge, split, add, or delete lines during translation/polishing without first explaining the consequence.
- Return machine-parseable JSON for transformed windows: keys are original IDs, values are transformed text only.
- Never treat window outputs as final by themselves. The final deliverable must pass a whole-file review for consistency and boundary flow.
- Re-validate after each transformation before exporting final SRT/VTT.
- Do not "correct" product names, coined terms, proper nouns, or brand-new concepts just because they look unusual. Preserve repeated unusual terms unless the user or source evidence says they are wrong.
- Do not infer ASR language failure from unexpected language alone. First consider that the downloaded media, dubbed audio track, or selected YouTube language may actually be in that language.

## Subtitle Quality

- Prefer natural, conversational target-language subtitles over literal phrasing.
- Keep terminology consistent; load glossary files when provided.
- Build a short term list from repeated names and concepts before polishing, and ask or preserve when uncertain instead of normalizing to a familiar term.
- Use surrounding lines as context, but translate only the current window values.
- Avoid overlong lines. For Chinese subtitles, target about 18-20 Han characters per cue; shorter is fine for short utterances, and more than about 20 should be treated as a readability warning rather than a normal default.
- Treat about 20 Han characters, 42 display-width units, or 20 display-width units per second as warning thresholds for single-line subtitles unless the user asks for dense subtitles.
- Flag cues shorter than 1 second, longer than 6 seconds, or above 20 display-width units per second.
- Add spaces between CJK characters and Latin/digit sequences when it improves readability.
- Remove trailing punctuation in translated CJK subtitles only when that matches the requested style.
- Preserve question marks, exclamation marks, ellipses, names, numbers, URLs, and code-like text carefully.

## Reference

Read `references/workflow-rules.md` only when you need prompt patterns, migration rationale, readability defaults, or the full QA checklist.
