# Transub Subtitle Workflow Rules

## Migration Rationale

The old Transub project mixed three layers:

- Hard local capabilities: `ffmpeg`, `faster-whisper`, timestamped segment serialization, SRT/VTT export.
- Subtitle craft rules: line independence, glossary consistency, context-aware translation, ASR correction, polish, CJK spacing, punctuation style.
- Product infrastructure: Electron UI, FastAPI server, provider credential UI, app packaging, progress streams, batch/concurrency plumbing.

For a skill, keep the first layer as scripts and the second layer as agent instructions. Defer the product layer unless the user explicitly asks to revive the app.

## Prompt Patterns

### Translation

Use this shape for chunked translation:

```text
You are a senior subtitle translator. Translate the values in this JSON object into TARGET_LANGUAGE.
Keep the same keys. Do not add, remove, merge, split, or reorder entries.
Use natural subtitle language, not word-for-word translation.
Follow the glossary exactly when present.
Use previous/next context only to disambiguate the current values.
Return only valid JSON.
```

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
- No commentary or markdown leaked into subtitle text.
- Glossary terms are consistent.
- Repeated names, products, acronyms, and coined concepts are preserved unless the user confirms a correction.
- Unexpected source language has been treated as media/audio-track evidence before diagnosing ASR language failure.
- Names, acronyms, numbers, URLs, code, and units are preserved or intentionally localized.
- CJK/Latin spacing is readable.
- Very long subtitle lines are flagged or reflowed only when allowed.
- Final `.srt` or `.vtt` validates after export.
- `doctor --probe` and `models` were checked before installing faster-whisper or downloading model variants.

## Readability Defaults

- English/source line display width: about 42 units.
- CJK translated line display width: about 30 units.
- Minimum duration: about 1.0-1.5 seconds when re-timing.
- Maximum CPS risk threshold: about 20 for mixed text; lower for dense CJK-only subtitles.
- Prefer sentence or phrase boundaries when splitting.
- Avoid orphaned one-word lines when reflowing.
