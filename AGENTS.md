# Agent Instructions

This repository contains reusable agent skills. Treat it as a public skill collection, not as a single-skill project.

- Use `uv` when installing Python packages.
- Keep each skill folder clean and self-contained. A skill folder should contain `SKILL.md` plus only files that directly support that skill, such as `scripts/`, `references/`, `assets/`, and optional agent UI metadata.
- Keep repository-level files at the repository root: `README.md`, `.gitignore`, `.claude-plugin/`, `LICENSE`, and repo-wide agent instructions.
- Every public skill must be listed in the top-level `README.md` with a link to its `SKILL.md`, and must be included in `.claude-plugin/plugin.json`.
- If category folders are introduced later, add a short `README.md` to each category and keep the top-level README as the canonical public index.
- Keep drafts, personal experiments, and deprecated skills out of the public index and plugin manifest until they are ready to ship.
- Avoid hard-coded personal paths, local cache paths, machine-specific agent directories, credentials, and one-off test artifacts in committed files.
- Prefer standard-library scripts when practical. If a script needs external Python packages, document the dependency path and use `uv` for installation or execution.
- For local tooling skills, prefer discovery before installation: check existing environments, cached models, binaries, and config before downloading or installing new dependencies.
- After changing a skill, validate it and update any external installed copy only when the user is actively testing that installed copy.
