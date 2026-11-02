# Versions and reviewed publication

Use semantic source versions: **0.3.0** introduces the fixed project-entry contract and managed temp worktrees. Patch versions fix behavior within that contract; minor versions add/change workflow capabilities. Before 1.0, changes can still require explicit migration notes. A version is not a promise of compatibility with every future native harness.

The package version in pyproject.toml and the internal `__version__` must agree. Record changes and limits in CHANGELOG.md. The installed release adds a content digest; `current` and the running daemon are separate facts exposed by doctor. A Git pull does not install or restart anything.

Public changes use reviewed generic source snapshots/commits. Scan outgoing files and full history/identities before a push; never merge private deployment history. Source versions can exist without a GitHub Release or published package. `v0.3.0` is the conventional tag name when a maintainer explicitly chooses to tag a tested revision; this change does not add automatic tags, releases or uploads.

Record tested Claude CLI, Codex CLI/backend and independent GUI builds where observed. Keep unknowns and limitations explicit. Migration notes describe actual state/thread handling, private backups and rollback, without putting real sessions, paths, credentials or provider configuration in public history. See [compatibility](harness-compatibility.md).
