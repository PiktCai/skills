# Agent Instructions

- Use `uv` when installing Python packages.
- Keep each skill folder clean and self-contained. Repository-level files such as `README.md`, `.gitignore`, and plugin manifests belong at the repository root, not inside an individual skill folder.
- Before running subtitle transcription with `transub`, check existing Python environments and cached faster-whisper models with `doctor --probe` and `models`; ask before installing dependencies or downloading a new model variant.
- After changing `transub`, sync any external installed copy only when the user is actively testing that installed copy; avoid hard-coding one machine's agent directory into the skill itself.
