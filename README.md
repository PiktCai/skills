# Agent Skills

Reusable, cross-agent skills for local workflows.

Each skill is self-contained in its own folder. The folder that contains `SKILL.md` is the skill root; it may include `scripts/`, `references/`, `assets/`, and agent metadata when those files directly support the skill.

## Skills

- [`transub`](./transub/SKILL.md): local subtitle transcription, translation, polishing, repair, validation, and SRT/VTT export.

## Install

Use any Agent Skills-compatible installer, or copy the specific skill folder into your agent's skills directory.

```bash
npx skills add <repo-or-local-path>
```

For manual installs, copy only the skill folder you need. For example, copy `transub/` if you want the Transub subtitle workflow.

## Repository Layout

```text
.
├── AGENTS.md
├── README.md
├── .claude-plugin/plugin.json
└── transub/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/workflow-rules.md
    └── scripts/subtitle_workflow.py
```

## Transub Quick Commands

```bash
python transub/scripts/subtitle_workflow.py doctor --probe
python transub/scripts/subtitle_workflow.py models
python transub/scripts/subtitle_workflow.py validate input.srt
python transub/scripts/subtitle_workflow.py audit input.srt --max-han-chars 20 --max-cps 20
```

Before transcription, check existing Python environments and cached faster-whisper models. If more than one cached model is available, ask which model variant to use instead of silently downloading or choosing a default.

## Transub Requirements

- Python 3.10+
- `ffmpeg` on `PATH`
- `faster-whisper` only for media transcription

Validation, conversion, export, model discovery, and readability audit use only the Python standard library.

## License

MIT
