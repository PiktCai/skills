# Transub Subtitle Workflow Rules

## Migration Rationale

The old Transub project mixed three layers:

- Hard local capabilities: `ffmpeg`, `faster-whisper`, timestamped segment serialization, SRT/VTT export.
- Subtitle craft rules: line independence, glossary consistency, context-aware translation, ASR correction, polish, CJK spacing, punctuation style.
- Product infrastructure: Electron UI, FastAPI server, provider credential UI, app packaging, progress streams, batch/concurrency plumbing.

For a skill, keep the first layer as scripts and the second layer as agent instructions. Defer the product layer unless the user explicitly asks to revive the app.

## Prompt Patterns

### Translation

First build a global brief for the whole file: subject matter, tone, recurring names, coined terms, glossary, and target subtitle style. If the file fits comfortably in context, translate the whole file in one structured pass. If it is too large, use overlapping windows and a live term/style ledger; do not treat windows as independent API batches.

Use this shape for windowed translation:

```text
You are a senior subtitle translator. Translate the values in this JSON object into TARGET_LANGUAGE.
Keep the same keys. Do not add, remove, merge, split, or reorder entries.
Use natural subtitle language, not word-for-word translation.
Follow the glossary exactly when present.
Use previous/next context to disambiguate the current values and keep boundary flow natural.
Preserve the active term/style ledger. If a new repeated term appears, add it to the ledger for later reconciliation.
Return only valid JSON.
```

After windowed translation, run a whole-file reconciliation pass. Check every window boundary, unify terminology and tone, smooth sentence flow across cue boundaries, and shorten overlong cues before export.

### ASR Correction

```text
You are correcting subtitle text produced by ASR.
Fix obvious recognition errors, missing punctuation, and capitalization.
Do not change meaning or style.
Do not normalize coined product names, unusual proper nouns, or repeated new concepts to a more familiar term unless source evidence proves they are wrong.
Do not assume an unexpected spoken language is ASR failure; the media may be dubbed or downloaded with a different audio track.
Do not merge or split lines.
Preserve the original keys exactly.
Return only valid JSON.
```

### Translation Polish

```text
You are polishing translated subtitles.
Make the text natural, concise, and conversational in the target language.
Fix awkward literal translation and punctuation.
For Chinese subtitles, aim for about 18-20 Han characters per cue. For Japanese and Korean, keep cues in a similar compact single-line range. For Latin-script subtitles, prefer concise cues around 35-42 letters or about 6-12 words. Shorter is fine when the utterance is short; avoid drifting far above the relevant range unless timing or meaning truly requires it.
Do not change meaning.
Do not merge or split lines.
Preserve the original keys exactly.
Return only valid JSON.
```

## QA Checklist

Run this checklist before final handoff:

- Same number of lines as source, unless re-segmentation was explicitly requested.
- No missing, duplicated, or reordered indices.
- Timestamps are monotonic and each cue has `end > start`.
- Translation output is valid JSON before reconstruction.
- Windowed translation outputs have received a whole-file reconciliation pass; no raw batch concatenation.
- Window boundaries have been reviewed for broken flow, repeated subjects, inconsistent names, and tone drift.
- No commentary or markdown leaked into subtitle text.
- Glossary terms are consistent.
- Repeated names, products, acronyms, and coined concepts are preserved unless the user confirms a correction.
- Unexpected source language has been treated as media/audio-track evidence before diagnosing ASR language failure.
- Names, acronyms, numbers, URLs, code, and units are preserved or intentionally localized.
- CJK/Latin spacing is readable.
- Very long subtitle lines are flagged or reflowed only when allowed.
- Chinese subtitles are generally around 18-20 Han characters per cue; Japanese/Korean should remain similarly compact; Latin-script subtitles should usually stay around 35-42 letters or 6-12 words. Cues far above the relevant range are flagged unless the user asked for dense subtitles.
- Final `.srt` or `.vtt` validates after export.
- `doctor --probe` and `models` were checked before installing faster-whisper or downloading model variants.

## Readability Defaults

- English/source line display width: about 42 units.
- Chinese translated cue length: about 18-20 Han characters.
- Japanese/Korean translated cue length: similarly compact, roughly low-20s characters for a single-line cue.
- Latin-script translated cue length: about 35-42 letters or 6-12 words.
- Cross-script weighted cue length: about 42 units. This follows the same idea as VideoLingo's weighted subtitle length check: CJK/Japanese count heavier than Latin characters, Korean slightly less than CJK/Japanese, and full-width symbols count heavier than half-width symbols.
- Minimum duration: about 1.0-1.5 seconds when re-timing.
- Maximum CPS risk threshold: about 20 for mixed text; lower for dense CJK-only subtitles.
- Prefer sentence or phrase boundaries when splitting.
- Avoid orphaned one-word lines when reflowing.
